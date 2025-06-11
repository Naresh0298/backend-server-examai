# # main.py (updated)
# from datetime import datetime
# import uuid
# from fastapi import FastAPI, File, UploadFile, HTTPException
# from google.cloud import storage
# from google.cloud.exceptions import GoogleCloudError
# from dotenv import load_dotenv
# from config import settings
# import os

# load_dotenv()

# app = FastAPI(
#     title="File Upload API",
#     description="API for uploading files to Google Cloud Storage",
#     version="1.0.0"
# )

# # Global GCS client
# gcs_client = None
# gcs_bucket = None

# def initialize_gcs():
#     """Initialize Google Cloud Storage client and bucket"""
#     global gcs_client, gcs_bucket
    
#     try:
#         # Create client using service account credentials
#         gcs_client = storage.Client.from_service_account_json(
#             settings.GOOGLE_APPLICATION_CREDENTIALS
#         )
        
#         # Get bucket reference
#         gcs_bucket = gcs_client.bucket(settings.GCS_BUCKET_NAME)
        
#         # Test bucket access
#         if not gcs_bucket.exists():
#             raise Exception(f"Bucket '{settings.GCS_BUCKET_NAME}' does not exist")
            
#         print(f"✅ Successfully connected to GCS bucket: {settings.GCS_BUCKET_NAME}")
        
#     except Exception as e:
#         print(f"❌ Failed to initialize GCS: {str(e)}")
#         raise

# # Initialize GCS on startup
# @app.on_event("startup")
# async def startup_event():
#     """Initialize services on application startup"""
#     initialize_gcs()

# @app.get("/")
# async def root():
#     return {
#         "message": "Welcome to File Upload API",
#         "docs": "/docs",
#         "version": "1.0.0"
#     }

# @app.get("/health")
# async def health_check():
#     """Enhanced health check with GCS status"""
#     try:
#         # Test GCS connection
#         bucket_exists = gcs_bucket.exists() if gcs_bucket else False
        
#         return {
#             "status": "healthy",
#             "service": "file-upload-api",
#             "gcs_connected": bucket_exists,
#             "bucket_name": settings.GCS_BUCKET_NAME
#         }
#     except Exception as e:
#         return {
#             "status": "unhealthy",
#             "service": "file-upload-api",
#             "gcs_connected": False,
#             "error": str(e)
#         }
    

# def generate_unique_filename(original_filename:str) ->str:
#     """ generate a unique filename to prevent conflicts"""

#     #get file extension
#     if "." in original_filename:
#         file_extension = "." + original_filename.split(".")[-1]

#     # Create unique identifier
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     unique_id = str(uuid.uuid4())[:8]
    
#     # Combine: timestamp_uniqueid.extension
#     return f"{timestamp}_{unique_id}{file_extension}"

# # Add this endpoint
# @app.post("/upload")
# async def upload_file(file: UploadFile = File(...)):
#     """Upload a single file to Google Cloud Storage
    
#     This is our first file upload endpoint. Let's break it down:
#     - file: UploadFile = File(...) means we expect a file upload
#     - UploadFile is FastAPI's way of handling uploaded files
#     - File(...) makes the file parameter required
#     """
    
#     try:
#         # Step 1: Read the file content
#         file_content = await file.read()
#         print(f"📁 Received file: {file.filename} ({len(file_content)} bytes)")
        
#         # Step 2: Generate unique filename
#         unique_filename = generate_unique_filename(file.filename)
#         print(f"🔄 Generated unique filename: {unique_filename}")
        
#         # Step 3: Create a blob (file object) in GCS
#         blob = gcs_bucket.blob(unique_filename)
        
#         # Step 4: Upload the file content
#         blob.upload_from_string(
#             file_content,
#             content_type=file.content_type  # Preserve original file type
#         )
        
#         print(f"✅ File uploaded successfully: {unique_filename}")
        
#         # Step 5: Return success response
#         return {
#             "success": True,
#             "message": "File uploaded successfully",
#             "data": {
#                 "original_filename": file.filename,
#                 "stored_filename": unique_filename,
#                 "size_bytes": len(file_content),
#                 "content_type": file.content_type,
#                 "bucket": settings.GCS_BUCKET_NAME,
#                 "public_url": f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{unique_filename}"
#             }
#         }
        
#     except Exception as e:
#         print(f"❌ Upload failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
# @app.get("/files")
# async def list_files(
#     folder: str = None,
#     limit: int = 100
# ):
#     """List files in the bucket
    
#     This endpoint allows you to:
#     - List all files in the bucket
#     - Filter by folder (prefix)
#     - Limit the number of results
#     """
    
#     try:
#         # Set up the query
#         prefix = f"{folder.strip('/')}/" if folder else None
        
#         # Get list of blobs (files) from GCS
#         blobs = gcs_bucket.list_blobs(prefix=prefix, max_results=limit)
        
#         # Convert blobs to a list of file information
#         files = []
#         for blob in blobs:
#             files.append({
#                 "name": blob.name,
#                 "size_bytes": blob.size,
#                 "content_type": blob.content_type,
#                 "created": blob.time_created.isoformat() if blob.time_created else None,
#                 "updated": blob.updated.isoformat() if blob.updated else None,
#                 "public_url": f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{blob.name}"
#             })
        
#         return {
#             "success": True,
#             "data": {
#                 "files": files,
#                 "count": len(files),
#                 "folder": folder,
#                 "bucket": settings.GCS_BUCKET_NAME
#             }
#         }
        
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")

# # @app.post("/upload/organized")
# # async def upload_file_organized(
# #     file: UploadFile = File(...),
# #     folder: str = "uploads"
# # ):
# #     """Upload file with folder organization
    
# #     This version allows organizing files into folders:
# #     - folder parameter specifies the folder name
# #     - Files are stored as: folder/filename
# #     """
    
# #     try:
# #         # Read file content
# #         file_content = await file.read()
        
# #         # Generate unique filename
# #         unique_filename = generate_unique_filename(file.filename)
        
# #         # Create blob path with folder
# #         blob_path = f"{folder.strip('/')}/{unique_filename}"
        
# #         # Upload to GCS
# #         blob = gcs_bucket.blob(blob_path)
# #         blob.upload_from_string(
# #             file_content,
# #             content_type=file.content_type
# #         )
        
# #         return {
# #             "success": True,
# #             "message": "File uploaded successfully",
# #             "data": {
# #                 "original_filename": file.filename,
# #                 "stored_path": blob_path,
# #                 "folder": folder,
# #                 "size_bytes": len(file_content),
# #                 "content_type": file.content_type,
# #                 "public_url": f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{blob_path}"
# #             }
# #         }
        
# #     except Exception as e:
# #         raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)