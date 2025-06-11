# server.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
from datetime import datetime
import uuid

from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
# Load environment variables from .env file


from .gcs_service import GCSService

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


app = FastAPI(title="File Upload API with GCS", version="1.0.0")



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
    allow_origins=origins,  # List of origins that are allowed to make requests
    allow_credentials=True, # Allow cookies to be included in requests
    allow_methods=["*"],    # Allow all standard methods (GET, POST, PUT, etc.)
    allow_headers=["*"],    # Allow all headers
)
# --- CORS Configuration END ---



# Configuration - Make sure these environment variables are set
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if not BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")



# Initialize GCS service
def get_gcs_service():
    return GCSService(
        bucket_name=BUCKET_NAME,
        credentials_path=CREDENTIALS_PATH
    )

@app.get("/")
async def root():
    return {"message": "File Upload API with Google Cloud Storage"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder: Optional[str] = None,
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Upload a file to Google Cloud Storage
    
    Args:
        file: The file to upload
        folder: Optional folder path in GCS bucket
        
    Returns:
        JSON response with upload status and file information
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Generate unique filename to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        file_extension = os.path.splitext(file.filename)[1]
        
        # Create destination blob name
        if folder:
            destination_blob_name = f"{folder}/{timestamp}_{unique_id}_{file.filename}"
        else:
            destination_blob_name = f"{timestamp}_{unique_id}_{file.filename}"
        
        # Upload file to GCS
        result = gcs_service.upload_file(
            file_data=file.file,
            destination_blob_name=destination_blob_name,
            content_type=file.content_type
        )
        
        if result["success"]:
            return JSONResponse(
                status_code=200,
                content={
                    "message": "File uploaded successfully",
                    "original_filename": file.filename,
                    "gcs_filename": destination_blob_name,
                    "bucket": result["bucket"],
                    "size": result["size"],
                    "content_type": file.content_type
                }
            )
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Upload failed: {result['message']}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    folder: Optional[str] = None,
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Upload multiple files to Google Cloud Storage
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        upload_results = []
        
        for file in files:
            if not file.filename:
                continue
                
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            
            if folder:
                destination_blob_name = f"{folder}/{timestamp}_{unique_id}_{file.filename}"
            else:
                destination_blob_name = f"{timestamp}_{unique_id}_{file.filename}"
            
            # Upload file
            result = gcs_service.upload_file(
                file_data=file.file,
                destination_blob_name=destination_blob_name,
                content_type=file.content_type
            )
            
            upload_results.append({
                "original_filename": file.filename,
                "gcs_filename": destination_blob_name,
                "success": result["success"],
                "message": result["message"]
            })
        
        return JSONResponse(
            status_code=200,
            content={
                "message": f"Processed {len(upload_results)} files",
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