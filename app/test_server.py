import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient # Import AsyncIOMotorClient
from pymongo.server_api import ServerApi

# Replace with your actual connection string
# It's best to load this from an environment variable
# For testing, you can hardcode it, but remove it afterward.
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://nareshmahendhar22878:HA6X0KXrl5xk6QQl@exam.uoknysm.mongodb.net/?retryWrites=true&w=majority&appName=exam")

async def test_mongodb_connection():
    client = None
    try:
        print(f"Attempting to connect to MongoDB using URI: {MONGO_URI}")
        # Use AsyncIOMotorClient for asynchronous operations
        client = AsyncIOMotorClient(MONGO_URI, server_api=ServerApi('1'))
        
        # Now, client.admin.command('ping') is awaitable
        await client.admin.command('ping') 
        print("Successfully connected to MongoDB!")
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
    finally:
        if client:
            client.close()

if __name__ == "__main__":
    asyncio.run(test_mongodb_connection())