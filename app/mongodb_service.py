# app/mongodb_service.py

from fastapi import HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, PyMongoError
import os
from dotenv import load_dotenv

# Load environment variables (ensure this is done once in the app's entry point)
load_dotenv()

# --- MongoDB Configuration (prioritize env vars) ---
MONGO_URI = os.getenv("MONGO_CLIENT","mongodb+srv://nareshmahendhar22878:HA6X0KXrl5xk6QQl@exam.uoknysm.mongodb.net/?retryWrites=true&w=majority&appName=exam")
DB_NAME = os.getenv("MONGO_DB_NAME", "examai")


# --- Pydantic Models for Exam Paper Structure ---
class QuestionSection(BaseModel):
    title: str
    child: int
    questions: Dict[str, str]

class QuestionsData(BaseModel):
    num_of_section: int
    section_a: QuestionSection
    section_b: QuestionSection # Assuming always section_b, adjust if it can be optional or a list

class InfrontPage(BaseModel):
    title: str
    subject: str
    total_marks: int
    exam_time: str
    description: str
    secondary_description: str

class ExamPaper(BaseModel):
    infront_page: InfrontPage
    questions_data: QuestionsData

# --- MongoDB Service Class ---
class MongoDB:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.mongo_uri = mongo_uri
        self.db_name = db_name

    async def connect(self):
        """Establishes the MongoDB connection."""
        try:
            self.client = AsyncIOMotorClient(self.mongo_uri)
            # The ismaster command is cheap and does not require auth.
            await self.client.admin.command('ismaster')
            self.db = self.client.get_database(self.db_name)
            print("MongoDB connected successfully.")
        except ConnectionFailure as e:
            print(f"MongoDB connection failed: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not connect to MongoDB.")
        except PyMongoError as e:
            print(f"MongoDB error during connection: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"MongoDB error: {e}")


    async def close(self):
        """Closes the MongoDB connection."""
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")

    def get_collection(self, collection_name: str):
        """Returns a specific collection from the database."""
        # Change 'if not self.db:' to 'if self.db is None:'
        if self.db is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MongoDB database not initialized.")
        return self.db.get_collection(collection_name)

# --- Dependency for MongoDB Service (Singleton Pattern) ---
_mongodb_instance: Optional[MongoDB] = None

async def get_mongodb_service() -> MongoDB:
    """
    Returns the singleton MongoDB service instance.
    Initializes it if not already initialized and connects.
    """
    global _mongodb_instance
    if _mongodb_instance is None:
        _mongodb_instance = MongoDB(mongo_uri=MONGO_URI, db_name=DB_NAME)
        await _mongodb_instance.connect() # Ensure connection is established on first access
    return _mongodb_instance

