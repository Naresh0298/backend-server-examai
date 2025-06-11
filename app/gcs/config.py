# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Google Cloud Storage
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    PROJECT_ID: str = os.getenv("PROJECT_ID")
    
    # File Upload Settings
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", 10))
    ALLOWED_FILE_TYPES: list = os.getenv("ALLOWED_FILE_TYPES", "").split(",")
    
    def __init__(self):
        # Validate required settings
        if not self.GCS_BUCKET_NAME:
            raise ValueError("GCS_BUCKET_NAME environment variable is required")
        if not self.GOOGLE_APPLICATION_CREDENTIALS:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable is required")

# Create settings instance
settings = Settings()