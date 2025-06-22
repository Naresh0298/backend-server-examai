# app/tasks.py
import os
import io
from .celery_worker import celery_app
from .gcs_service import GCSService
from .vision_service import VisionService
from .claude_service import ClaudeService
from .mongodb_service import MongoDB, ExamPaper # Import if you want to interact with MongoDB directly in tasks
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

# Initialize services within the task module, or pass them as args if needed
# For simplicity, we'll re-initialize them here based on env vars
# Note: For production, consider using dependency injection or proper singleton patterns
# if these services hold state or connection pools that should be reused.
# For Celery tasks, re-initialization is often simpler unless connections are persistent.

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required in app/tasks.py")

# Define a function to get MongoDB service for tasks
# This avoids circular imports with get_mongodb_service in main_server's lifespan
def get_mongodb_service_for_task():
    # This ensures a new MongoDB connection for the worker process if needed
    # For long-running workers, you might want to manage this connection carefully
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME")
    if not mongo_uri or not db_name:
        raise ValueError("MONGO_URI or MONGO_DB_NAME not set for task MongoDB access.")
    return MongoDB(mongo_uri=mongo_uri, db_name=db_name)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60) # Bind=True to access self (for retry), retry on failure
async def process_document_task(self, file_content_bytes: bytes, original_filename: str, file_content_type: str, folder: str | None = None):
    """
    Celery task to handle the long-running processing of an uploaded document:
    1. Uploads to GCS.
    2. Performs OCR.
    3. Calls Claude AI for exam paper generation.
    4. Stores result in MongoDB (via ClaudeService).
    """
    logger.info(f"Starting document processing task for {original_filename}...")
    gcs_service = GCSService(bucket_name=BUCKET_NAME, credentials_path=CREDENTIALS_PATH)
    vision_service = VisionService()
    # Create ClaudeService with a new MongoDB instance for the task context
    mongodb_service_for_task = get_mongodb_service_for_task()
    claude_service = ClaudeService(mongodb_service=mongodb_service_for_task)


    file_extension = os.path.splitext(original_filename)[1].lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]

    if folder:
        destination_blob_name = f"{folder}/{timestamp}_{unique_id}_{original_filename}"
    else:
        destination_blob_name = f"{timestamp}_{unique_id}_{original_filename}"

    try:
        # --- UPLOAD TO GCS ---
        logger.info(f"Uploading {original_filename} to GCS...")
        gcs_upload_result = gcs_service.upload_file(
            file_data=io.BytesIO(file_content_bytes),
            destination_blob_name=destination_blob_name,
            content_type=file_content_type
        )

        if not gcs_upload_result["success"]:
            raise RuntimeError(f"GCS upload failed: {gcs_upload_result['message']}")

        gcs_bucket_name = gcs_upload_result.get("bucket", BUCKET_NAME)
        gcs_input_uri = f"gs://{gcs_bucket_name}/{destination_blob_name}"
        logger.info(f"File uploaded to GCS: {gcs_input_uri}")

        ocr_results = {
            "full_text": "",
            "structured_data": [],
            "error": None
        }

        # --- PERFORM OCR BASED ON FILE TYPE ---
        logger.info("Performing OCR...")
        if file_extension == ".pdf":
            gcs_output_prefix = f"ocr_results/{timestamp}_{unique_id}/"
            gcs_output_uri = f"gs://{gcs_bucket_name}/{gcs_output_prefix}"

            ocr_operation_result = vision_service.process_pdf_from_gcs(
                gcs_source_uri=gcs_input_uri,
                gcs_destination_uri=gcs_output_uri
            )

            if ocr_operation_result["status"] == "completed":
                ocr_data = vision_service.read_ocr_results_from_gcs(
                    gcs_output_uri_prefix=gcs_output_uri,
                    bucket_name=gcs_bucket_name
                )
                ocr_results["full_text"] = ocr_data["full_text"]
                ocr_results["error"] = ocr_data["error"]
            else:
                ocr_results["error"] = ocr_operation_result["error"]
                raise RuntimeError(f"PDF OCR operation failed: {ocr_results['error']}")

        elif file_extension in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"]:
            ocr_data = vision_service.detect_document_text(file_content_bytes)
            ocr_results["full_text"] = ocr_data["full_text"]
            ocr_results["error"] = ocr_data["error"]

            if ocr_results["error"]:
                raise RuntimeError(f"Image OCR failed: {ocr_results['error']}")
        else:
            raise RuntimeError("Unsupported file type for OCR. Only images and PDFs are supported.")

        # --- Pass extracted text to Claude AI ---
        if ocr_results["full_text"]:
            logger.info("Sending extracted text to Claude for exam paper generation...")
            generated_exam_paper = await claude_service.generate_and_store_exam_paper(ocr_results["full_text"])
            logger.info("Claude AI generation and storage complete.")

            # Close MongoDB connection specific to this task if not managed by pool
            await mongodb_service_for_task.close()

            return {
                "status": "success",
                "message": "File processed, OCR completed, and exam paper generated.",
                "original_filename": original_filename,
                "gcs_path": gcs_input_uri,
                "extracted_text_length": len(ocr_results["full_text"]),
                "exam_paper_id": str(generated_exam_paper.id) if generated_exam_paper and generated_exam_paper.id else None
            }
        else:
            raise RuntimeError("No text extracted from OCR to send to Claude.")

    except Exception as e:
        logger.error(f"Task failed for {original_filename}: {e}", exc_info=True)
        # Try to retry the task if it's a transient error
        try:
            # Pass the current arguments for retry
            raise self.retry(exc=e, countdown=60)
        except Exception as retry_e:
            logger.error(f"Exhausted retries or non-retryable error for {original_filename}: {retry_e}")
            # Final failure, close connection before returning
            await mongodb_service_for_task.close()
            return {
                "status": "failed",
                "message": f"Processing failed: {str(e)}",
                "original_filename": original_filename
            }

    finally:
        # Ensure MongoDB connection is closed in all cases, even if successful
        # This might need refinement if MongoDB service uses connection pooling that needs explicit management
        try:
            await mongodb_service_for_task.close()
            logger.info("MongoDB connection closed in task.")
        except Exception as close_e:
            logger.error(f"Error closing MongoDB connection in task: {close_e}")