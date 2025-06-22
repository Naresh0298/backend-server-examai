

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
from datetime import datetime
import uuid
import io
import json # For custom JSON encoder
from dotenv import load_dotenv
from pathlib import Path

# Import GCS, Vision, Claude services
from .gcs_service import GCSService
from .vision_service import VisionService
from .claude_service import ClaudeService, get_claude_service

# Import MongoDB service and Pydantic models from it
from .mongodb_service import MongoDB, get_mongodb_service, ExamPaper # Import get_mongodb_service and ExamPaper model

from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager # For lifespan
from bson import ObjectId # for _id conversion
from pydantic import BaseModel # For new request body model

# --- Environment Variable Loading ---
current_script_dir = Path(__file__).resolve().parent
backend_dir = current_script_dir.parent
project_root_dir = backend_dir.parent

env_path = project_root_dir / 'backend-server-examai/app/.env'

# Use this to load environment variables from the specific path
load_dotenv(dotenv_path=env_path)

# Ensure required environment variables are loaded
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_OCR")
# MONGO_URI and DB_NAME are now primarily read from .env in mongodb_service.py
# but it's good to keep checks here if main.py directly depends on them
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME")


if not BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")
# Removed direct MONGO_URI and DB_NAME checks here as mongodb_service handles defaults/errors


# --- FastAPI Lifespan (for MongoDB connection) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize and connect MongoDB service during startup
    mongodb_service = await get_mongodb_service()
    app.mongodb_service = mongodb_service # Make it accessible on the app object
    yield
    # Close MongoDB connection during shutdown
    await app.mongodb_service.close()

app = FastAPI(title="File Upload API with GCS, OCR, and AI", version="1.0.0", lifespan=lifespan)

# --- CORS Configuration ---
origins = [
    "http://localhost:3000",
    "http://169.254.9.73:3000",
    "http://127.0.0.1:3000",
    # Add your Vercel frontend URL for production if needed
    # "https://examai-frontend.vercel.app",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency Injections ---
def get_gcs_service():
    return GCSService(bucket_name=BUCKET_NAME, credentials_path=CREDENTIALS_PATH)

def get_vision_service():
    return VisionService()

# --- Pydantic Models ---
# Pydantic model for User (if needed), adjusted for ExamPaper
class User(BaseModel):
    gen_info: ExamPaper # Change this from str to ExamPaper

# Pydantic model for the new /gen-response endpoint request body
class GenerateRequest(BaseModel):
    extracted_text: str

# Custom JSON encoder to handle ObjectId, useful for consistent responses
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


# --- API Endpoints ---
@app.get("/")
async def root():
    return {"message": "File Upload API with Google Cloud Storage, OCR, and AI"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder: Optional[str] = None,
    gcs_service: GCSService = Depends(get_gcs_service),
    vision_service: VisionService = Depends(get_vision_service),
    claude_service: ClaudeService = Depends(get_claude_service) # Now get_claude_service correctly injects MongoDB
):
    """
    Upload a file to Google Cloud Storage, perform OCR, and then use the extracted text
    to generate an exam paper with Claude AI.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    original_filename = file.filename
    file_extension = os.path.splitext(original_filename)[1].lower()

    file_content = await file.read()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]

    if folder:
        destination_blob_name = f"{folder}/{timestamp}_{unique_id}_{original_filename}"
    else:
        destination_blob_name = f"{timestamp}_{unique_id}_{original_filename}"

    # --- UPLOAD TO GCS ---
    gcs_upload_result = gcs_service.upload_file(
        file_data=io.BytesIO(file_content),
        destination_blob_name=destination_blob_name,
        content_type=file.content_type
    )

    if not gcs_upload_result["success"]:
        raise HTTPException(
            status_code=500,
            detail=f"GCS upload failed: {gcs_upload_result['message']}"
        )

    gcs_bucket_name = gcs_upload_result.get("bucket", os.getenv("GCS_BUCKET_NAME"))
    gcs_input_uri = f"gs://{gcs_bucket_name}/{destination_blob_name}"

    ocr_results = {
        "full_text": "",
        "structured_data": [],
        "error": None
    }

    claude_response = {"exam_paper": None, "error": None}


    # --- PERFORM OCR BASED ON FILE TYPE ---
    try:
        if file_extension == ".pdf":
            print(f"Processing PDF from GCS: {gcs_input_uri}")

            gcs_output_prefix = f"ocr_results/{timestamp}_{unique_id}/"
            gcs_output_uri = f"gs://{gcs_bucket_name}/{gcs_output_prefix}"

            ocr_operation_result = vision_service.process_pdf_from_gcs(
                gcs_source_uri=gcs_input_uri,
                gcs_destination_uri=gcs_output_uri
            )

            if ocr_operation_result["status"] == "completed":
                print(f"Reading OCR results from GCS output: {gcs_output_uri}")
                ocr_data = vision_service.read_ocr_results_from_gcs(
                    gcs_output_uri_prefix=gcs_output_uri,
                    bucket_name=gcs_bucket_name
                )
                ocr_results["full_text"] = ocr_data["full_text"]
                ocr_results["error"] = ocr_data["error"]
            else:
                ocr_results["error"] = ocr_operation_result["error"]
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF OCR operation failed: {ocr_results['error']}"
                )

        elif file_extension in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"]:
            print(f"Processing image with direct OCR: {original_filename}")
            ocr_data = vision_service.detect_document_text(file_content)
            ocr_results["full_text"] = ocr_data["full_text"]
            ocr_results["error"] = ocr_data["error"]

            if ocr_results["error"]:
                 raise HTTPException(
                    status_code=500,
                    detail=f"Image OCR failed: {ocr_results['error']}"
                )
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type for OCR. Only images and PDFs are supported.")

    except HTTPException:
        raise
    except Exception as e:
        print(f"An unexpected error occurred during OCR processing: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during OCR processing: {e}")

    # --- Pass extracted text to Claude AI ---
    if ocr_results["full_text"]:
        try:
            print("Sending extracted text to Claude for exam paper generation and storage...")
            # This will now call generate_and_store_exam_paper which handles DB insertion
            generated_exam_paper = await claude_service.generate_and_store_exam_paper(ocr_results["full_text"])
            claude_response["exam_paper"] = generated_exam_paper
        except RuntimeError as e: # Catch the specific RuntimeError from ClaudeService
            claude_response["error"] = str(e)
            print(f"Error during Claude AI generation: {e}")
        except Exception as e:
            claude_response["error"] = f"An unexpected error occurred during Claude AI generation: {e}"
            print(f"An unexpected error occurred during Claude AI generation: {e}")
    else:
        claude_response["error"] = "No text extracted from OCR to send to Claude."
        print("No text extracted from OCR to send to Claude.")


    # --- FIX HERE: Apply CustomJSONEncoder to the response content ---
    response_content = {
        "message": "File uploaded, OCR processed, and AI generation attempted.",
        "original_filename": original_filename,
        "gcs_info": {
            "gcs_filename": destination_blob_name,
            "bucket": gcs_upload_result["bucket"],
            "size": gcs_upload_result["size"],
            "content_type": file.content_type
        },
        "ocr_results": ocr_results,
        "claude_ai_response": claude_response
    }

    # Manually dump the content using the CustomJSONEncoder and then load it back
    # so JSONResponse receives a dict where ObjectIds are already strings.
    return JSONResponse(
        status_code=200,
        content=json.loads(json.dumps(response_content, cls=CustomJSONEncoder))
    )

@app.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    folder: Optional[str] = None,
    gcs_service: GCSService = Depends(get_gcs_service),
    vision_service: VisionService = Depends(get_vision_service)
):
    """
    Upload multiple files to Google Cloud Storage and perform OCR on each.
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        upload_results = []

        for file in files:
            if not file.filename:
                continue

            file_content = await file.read()
            file.file.seek(0) # Reset file pointer for subsequent reads if needed

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]

            if folder:
                destination_blob_name = f"{folder}/{timestamp}_{unique_id}_{file.filename}"
            else:
                destination_blob_name = f"{timestamp}_{unique_id}_{file.filename}"

            gcs_upload_result = gcs_service.upload_file(
                file_data=io.BytesIO(file_content),
                destination_blob_name=destination_blob_name,
                content_type=file.content_type
            )

            file_processed_result = {
                "original_filename": file.filename,
                "gcs_filename": destination_blob_name,
                "gcs_success": gcs_upload_result["success"],
                "gcs_message": gcs_upload_result["message"],
                "ocr_results": {}
            }

            if gcs_upload_result["success"]:
                ocr_result = vision_service.detect_document_text(file_content)
                file_processed_result["ocr_results"] = ocr_result

            upload_results.append(file_processed_result)

        return JSONResponse(
            status_code=200,
            content={
                "message": f"Processed {len(upload_results)} files with GCS upload and OCR",
                "results": upload_results
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/files")
async def list_all_files(
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    List all files in the GCS bucket.
    """
    try:
        result = gcs_service.list_files(prefix=None)

        if result["success"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        else:
            raise HTTPException(status_code=500, detail=result["message"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.delete("/files/{file_path:path}")
async def delete_file(
    file_path: str,
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Delete a file from GCS bucket
    """
    try:
        result = gcs_service.delete_file(file_path)

        if result["success"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        else:
            raise HTTPException(status_code=404, detail=result["message"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/files/{file_path:path}/exists")
async def check_file_exists(
    file_path: str,
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Check if a file exists in the GCS bucket
    """
    try:
        exists = gcs_service.file_exists(file_path)
        return JSONResponse(
            status_code=200,
            content={
                "file_path": file_path,
                "exists": exists
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- User Management (using the new MongoDB service) ---
@app.post("/api/v1/create-user", response_model=User)
async def insert_user(user: User, mongodb_service: MongoDB = Depends(get_mongodb_service)):
    # Corrected check: Check if mongodb_service.db is properly initialized
    if mongodb_service.db is None: # Corrected check
        raise HTTPException(status_code=500, detail="Database client not initialized or connected.")

    users_collection = mongodb_service.get_collection("users") # Use the service to get the collection
    result = await users_collection.insert_one(user.dict())
    inserted_user_data = await users_collection.find_one({"_id": result.inserted_id})

    # Convert ObjectId to string for Pydantic model response
    if inserted_user_data:
        # Use json.dumps with CustomJSONEncoder to ensure ObjectId is serialized correctly
        return JSONResponse(content=json.loads(json.dumps(inserted_user_data, cls=CustomJSONEncoder)), status_code=200)
    else:
        raise HTTPException(status_code=500, detail="Failed to retrieve inserted user data.")

@app.get("/gen")
async def generate_and_get_latest_exam_paper(
    # This endpoint now only depends on the MongoDB service to read data
    mongodb_service: MongoDB = Depends(get_mongodb_service)
):
    """
    Reads the latest exam paper from MongoDB and returns it.
    This endpoint no longer generates new exam papers.
    """

    # 1. Fetch the Latest Pushed Data from MongoDB
    try:
        exam_paper_collection = mongodb_service.get_collection("exam_papers") # Ensure this matches the collection name in ClaudeService
        # --- THIS IS WHERE THE DATABASE QUERY BELONGS, INSIDE THE FUNCTION BODY ---
        latest_paper = await exam_paper_collection.find_one(
            {}, # Empty query to get all documents
            sort=[('_id', -1)] # Sort by _id descending to get the latest
        )

        if latest_paper is None:
            raise HTTPException(status_code=404, detail="No exam papers found in the database.")

        # Return the latest paper, ensuring ObjectId is serialized
        return JSONResponse(
            status_code=200,
            content=json.loads(json.dumps(latest_paper, cls=CustomJSONEncoder))
        )
    except Exception as e:
        print(f"Error fetching latest exam paper from MongoDB: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve latest exam paper: {e}")



if __name__ == "__main__":
    import uvicorn
    # Make sure to run with `uvicorn main:app --reload` to trigger lifespan events
    uvicorn.run(app, host="0.0.0.0", port=8000)

