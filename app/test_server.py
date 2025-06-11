# D:\Projects\Exam Ai\backend\app\main_server.py (or test_server.py)

from dotenv import load_dotenv
import os
from fastapi import FastAPI
from pathlib import Path # Ensure this is imported

# --- THIS IS THE CRITICAL PATH CALCULATION FIX ---
# Get the directory where the current script (main_server.py) resides:
# D:\Projects\Exam Ai\backend\app
current_script_dir = Path(__file__).resolve().parent

# Go up one level to the 'backend' directory:
# D:\Projects\Exam Ai\backend
project_root_dir = current_script_dir.parent

# Combine the project root with the .env filename:
# D:\Projects\Exam Ai\backend\.env
env_path = project_root_dir / '.env'
# --- END CRITICAL PATH CALCULATION FIX ---


# Add these debug prints to confirm the path and loading success
print(f"DEBUG: Attempting to load .env from: {env_path}")
load_success = load_dotenv(dotenv_path=env_path)
print(f"DEBUG: load_dotenv() successful: {load_success}")

CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
gcs_bucket_name = os.getenv("GCS_BUCKET_NAME")
print(f"DEBUG: Value of GOOGLE_APPLICATION_CREDENTIALS after load_dotenv(): {gcs_bucket_name}")

# Your check for the variable
if not gcs_bucket_name:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")

# IMPORTANT: Define your FastAPI app instance and name it 'app'
app = FastAPI()

# Your routes and other application logic go here
@app.get("/")
async def read_root():
    return {f"message": "Welcome to Exam AI backend! " + CREDENTIALS_PATH}

