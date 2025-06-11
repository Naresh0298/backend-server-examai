from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
from datetime import datetime
import uuid
import io

from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
# Load environment variables from .env file


from .gcs_service import GCSService
from .vision_service import VisionService # Import the new VisionService

from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
import os
from dotenv import load_dotenv

current_script_dir = Path(__file__).resolve().parent
backend_dir = current_script_dir.parent
project_root_dir = backend_dir.parent

env_path = project_root_dir / 'backend/app/.env'

print(f"DEBUG: Attempting to load .env from: {env_path}")
# This is the ONLY call needed to load from a specific path
load_success = load_dotenv(dotenv_path=env_path)
print(f"DEBUG: load_dotenv() successful: {load_success}")

# Now, test if your variables are loaded
# For example, if you have API_KEY in your .env
# print(f"DEBUG: API_KEY loaded: {os.getenv('API_KEY')}")
load_dotenv()


app = FastAPI(title="File Upload API with GCS and OCR", version="1.0.0")



# --- CORS Configuration START ---
# Define the list of origins that should be allowed to make cross-origin requests.
# You should be specific in production, but for development, localhost:3000 is key.
origins = [
    "http://localhost:3000", # Your frontend origin
    # You might want to add other origins if needed, e.g.:
    "http://169.254.9.73:3000",
    "http://127.0.0.1:3000",
    
    # "https://examai-frontend.vercel.app/",
    # "http://localhost", # If frontend runs without port sometimes
    # "https://your-production-frontend.com" # For production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,   # List of origins that are allowed to make requests
    allow_credentials=True, # Allow cookies to be included in requests
    allow_methods=["*"],    # Allow all standard methods (GET, POST, PUT, etc.)
    allow_headers=["*"],    # Allow all headers
)
# --- CORS Configuration END ---



# Configuration - Make sure these environment variables are set
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_OCR")

if not BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")


# Initialize GCS service
def get_gcs_service():
    """Dependency injection for GCSService."""
    return GCSService(
        bucket_name=BUCKET_NAME,
        credentials_path=CREDENTIALS_PATH
    )

# Initialize Vision service
def get_vision_service():
    """Dependency injection for VisionService."""
    return VisionService()

@app.get("/")
async def root():
    return {"message": "File Upload API with Google Cloud Storage and OCR"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder: Optional[str] = None,
    gcs_service: GCSService = Depends(get_gcs_service),
    vision_service: VisionService = Depends(get_vision_service) # Inject VisionService
):
    """
    Upload a file to Google Cloud Storage and perform OCR on it.
    
    Args:
        file: The file to upload.
        folder: Optional folder path in GCS bucket.
        
    Returns:
        JSON response with upload status, file information, and OCR results.
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Read file content for both GCS upload and OCR
        file_content = await file.read()
        file.file.seek(0) # Reset file pointer for subsequent reads if needed, though GCS upload is done
                          # and vision service uses the read content directly.

        # Generate unique filename to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        file_extension = os.path.splitext(file.filename)[1]
        
        # Create destination blob name
        if folder:
            destination_blob_name = f"{folder}/{timestamp}_{unique_id}_{file.filename}"
        else:
            destination_blob_name = f"{timestamp}_{unique_id}_{file.filename}"
        
        # --- UPLOAD TO GCS ---
        # The file.file object is an in-memory BytesIO after the first read,
        # so we pass file_content as BytesIO for GCS to read from.
        gcs_upload_result = gcs_service.upload_file(
            file_data=io.BytesIO(file_content), # Pass BytesIO object
            destination_blob_name=destination_blob_name,
            content_type=file.content_type
        )
        
        if not gcs_upload_result["success"]:
            raise HTTPException(
                status_code=500, 
                detail=f"GCS upload failed: {gcs_upload_result['message']}"
            )
        
        # --- PERFORM OCR ---
        # You can choose between detect_text (general) or detect_document_text (dense documents)
        # For exam papers, detect_document_text is usually more appropriate.
        ocr_result = vision_service.detect_document_text(file_content)

        return JSONResponse(
            status_code=200,
            content={
                "message": "File uploaded and OCR processed successfully",
                "original_filename": file.filename,
                "gcs_info": {
                    "gcs_filename": destination_blob_name,
                    "bucket": gcs_upload_result["bucket"],
                    "size": gcs_upload_result["size"],
                    "content_type": file.content_type
                },
                "ocr_results": ocr_result
            }
        )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    folder: Optional[str] = None,
    gcs_service: GCSService = Depends(get_gcs_service),
    vision_service: VisionService = Depends(get_vision_service) # Inject VisionService
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
            
            # Read file content for both GCS upload and OCR
            file_content = await file.read()
            file.file.seek(0) # Reset file pointer for subsequent reads if needed

            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            
            if folder:
                destination_blob_name = f"{folder}/{timestamp}_{unique_id}_{file.filename}"
            else:
                destination_blob_name = f"{timestamp}_{unique_id}_{file.filename}"
            
            # --- UPLOAD TO GCS ---
            gcs_upload_result = gcs_service.upload_file(
                file_data=io.BytesIO(file_content), # Pass BytesIO object
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
                # --- PERFORM OCR ---
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
    This endpoint now explicitly lists all files without filtering by folder.
    """
    try:
        # Call list_files with prefix=None to retrieve all files in the bucket.
        result = gcs_service.list_files(prefix=None)
        
        if result["success"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        else:
            # If the service indicates failure, raise an HTTP exception.
            raise HTTPException(status_code=500, detail=result["message"])
            
    except Exception as e:
        # Catch any unexpected errors during the process.
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

