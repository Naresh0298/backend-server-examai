# app/main_server.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
from datetime import datetime
import uuid
import io
import json # For custom JSON encoder
from dotenv import load_dotenv
from pathlib import Path

# Import GCS, Vision, Claude services (still needed for dependencies for other endpoints or if you decide to keep partial sync logic)
from .gcs_service import GCSService
from .vision_service import VisionService
from .claude_service import ClaudeService, get_claude_service # get_claude_service is now used for /gen endpoint's dependency

# Import MongoDB service and Pydantic models from it
from .mongodb_service import MongoDB, get_mongodb_service, ExamPaper

from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from bson import ObjectId
from pydantic import BaseModel

# --- NEW: Import Celery related components ---
from .celery_worker import celery_app
from .tasks import process_document_task # Import your specific task

# --- Environment Variable Loading ---
current_script_dir = Path(__file__).resolve().parent
backend_dir = current_script_dir.parent
project_root_dir = backend_dir.parent

env_path = project_root_dir / 'backend-server-examai/app/.env'

load_dotenv(dotenv_path=env_path)

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_OCR")
# MONGO_URI and DB_NAME are now primarily read from .env in mongodb_service.py
# but it's good to keep checks here if main.py directly depends on them
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME")


if not BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")

# --- FastAPI Lifespan (for MongoDB connection for the web dyno) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    mongodb_service = await get_mongodb_service()
    app.mongodb_service = mongodb_service
    yield
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

# --- Dependency Injections (still useful for other endpoints or if you need them) ---
def get_gcs_service_sync(): # Renamed to avoid confusion with async task
    return GCSService(bucket_name=BUCKET_NAME, credentials_path=CREDENTIALS_PATH)

def get_vision_service_sync(): # Renamed to avoid confusion
    return VisionService()

# --- Pydantic Models ---
class User(BaseModel):
    gen_info: ExamPaper

class GenerateRequest(BaseModel):
    extracted_text: str

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

# --- API Endpoints ---
@app.get("/")
async def root():
    return {"message": "File Upload API with Google Cloud Storage, OCR, and AI (Celery Enabled)"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder: Optional[str] = None
):
    """
    Uploads a file and enqueues a background task for GCS upload, OCR, and AI generation.
    Returns an immediate response with a task ID.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    file_content = await file.read() # Read file content once
    file_content_type = file.content_type
    original_filename = file.filename

    # Enqueue the long-running task to Celery
    # The file content (bytes) is passed directly to the task
    task = process_document_task.delay(
        file_content_bytes=file_content,
        original_filename=original_filename,
        file_content_type=file_content_type,
        folder=folder
    )

    # Return an immediate 202 Accepted response
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "File upload received. Processing initiated in background.",
            "original_filename": original_filename,
            "task_id": task.id, # The ID of the Celery task
            "status_check_url": f"/tasks/{task.id}/status" # Endpoint to check status
        }
    )

@app.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """
    Check the status of a background task by its ID.
    """
    task_result = process_document_task.AsyncResult(task_id)

    response_data = {
        "task_id": task_id,
        "status": task_result.status,
        "ready": task_result.ready()
    }

    if task_result.ready():
        # Task is finished (SUCCESS, FAILURE, RETRY, etc.)
        response_data["successful"] = task_result.successful() # True if status is SUCCESS
        response_data["result"] = task_result.result # Contains the return value or exception

        # If result is bytes (e.g. error message), convert to string for JSON serialization
        if isinstance(response_data["result"], bytes):
            try:
                response_data["result"] = response_data["result"].decode('utf-8')
            except UnicodeDecodeError:
                response_data["result"] = str(response_data["result"]) # Fallback to string representation

    return JSONResponse(content=response_data, status_code=200)


@app.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    folder: Optional[str] = None,
    # Dependencies for GCS/Vision are no longer needed here if processing is async
    # gcs_service: GCSService = Depends(get_gcs_service_sync),
    # vision_service: VisionService = Depends(get_vision_service_sync)
):
    """
    Upload multiple files and enqueue background tasks for each.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    enqueued_tasks = []
    for file in files:
        if not file.filename:
            continue

        file_content = await file.read()
        file_content_type = file.content_type
        original_filename = file.filename

        task = process_document_task.delay(
            file_content_bytes=file_content,
            original_filename=original_filename,
            file_content_type=file_content_type,
            folder=folder
        )
        enqueued_tasks.append({
            "original_filename": original_filename,
            "task_id": task.id,
            "status_check_url": f"/tasks/{task.id}/status"
        })

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": f"Processing initiated for {len(enqueued_tasks)} files.",
            "tasks": enqueued_tasks
        }
    )

@app.get("/files")
async def list_all_files(
    gcs_service: GCSService = Depends(get_gcs_service_sync)
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
    gcs_service: GCSService = Depends(get_gcs_service_sync)
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
    gcs_service: GCSService = Depends(get_gcs_service_sync)
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
    if mongodb_service.db is None:
        raise HTTPException(status_code=500, detail="Database client not initialized or connected.")

    users_collection = mongodb_service.get_collection("users")
    result = await users_collection.insert_one(user.dict())
    inserted_user_data = await users_collection.find_one({"_id": result.inserted_id})

    if inserted_user_data:
        return JSONResponse(content=json.loads(json.dumps(inserted_user_data, cls=CustomJSONEncoder)), status_code=200)
    else:
        raise HTTPException(status_code=500, detail="Failed to retrieve inserted user data.")

@app.get("/gen")
async def generate_and_get_latest_exam_paper(
    mongodb_service: MongoDB = Depends(get_mongodb_service)
):
    """
    Reads the latest exam paper from MongoDB and returns it.
    This endpoint no longer generates new exam papers.
    """
    try:
        exam_paper_collection = mongodb_service.get_collection("exam_papers")
        latest_paper = await exam_paper_collection.find_one(
            {},
            sort=[('_id', -1)]
        )

        if latest_paper is None:
            raise HTTPException(status_code=404, detail="No exam papers found in the database.")

        return JSONResponse(
            status_code=200,
            content=json.loads(json.dumps(latest_paper, cls=CustomJSONEncoder))
        )
    except Exception as e:
        print(f"Error fetching latest exam paper from MongoDB: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve latest exam paper: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)