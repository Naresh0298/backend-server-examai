# gcs/gcs_service.py
from google.cloud import storage
from google.api_core.exceptions import NotFound # Corrected import for NotFound
import os
from typing import Optional, BinaryIO
import logging
from google.oauth2 import service_account
import json


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GCSService:
    def __init__(self, bucket_name: str, credentials_path: Optional[str] = None):
        self.bucket_name = bucket_name
        print("bucket_name",bucket_name)

        # credentials = None

        if credentials_path and os.path.exists(credentials_path):
            credentials = service_account.Credentials.from_service_account_file(credentials_path)

        elif "GOOGLE_APPLICATION_CREDENTIALS_OCR" in os.environ:
            # Try to load JSON from env var
            try:
                credentials_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_OCR"])
                credentials = service_account.Credentials.from_service_account_info(credentials_info)
            except json.JSONDecodeError as e:
                raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS_OCR is not valid JSON.") from e
        else:
            raise RuntimeError("No valid Google Cloud credentials found.", credentials_path)

        self.client = storage.Client(credentials=credentials, project=credentials.project_id)
        self.bucket = self.client.bucket(bucket_name)
    
    def upload_file(self, file_data: BinaryIO, destination_blob_name: str, content_type: str = None) -> dict:
        """
        Upload a file to GCS bucket
        
        Args:
            file_data: File data (binary)
            destination_blob_name: Name for the file in GCS
            content_type: MIME type of the file
            
        Returns:
            dict: Upload result with status and file info
        """
        try:
            blob = self.bucket.blob(destination_blob_name)
            
            if content_type:
                blob.content_type = content_type
            
            # Upload the file
            blob.upload_from_file(file_data, rewind=True)
            
            logger.info(f"File {destination_blob_name} uploaded successfully to {self.bucket_name}")
            
            return {
                "success": True,
                "message": f"File uploaded successfully",
                "file_name": destination_blob_name,
                "bucket": self.bucket_name,
                "public_url": f"gs://{self.bucket_name}/{destination_blob_name}",
                "size": blob.size
            }
            
        except Exception as e:
            logger.error(f"Error uploading file {destination_blob_name}: {str(e)}")
            return {
                "success": False,
                "message": f"Upload failed: {str(e)}",
                "file_name": destination_blob_name
            }
    
    def download_file(self, source_blob_name: str, destination_file_path: str) -> dict:
        """
        Download a file from GCS bucket
        
        Args:
            source_blob_name: Name of the file in GCS
            destination_file_path: Local path to save the file
            
        Returns:
            dict: Download result
        """
        try:
            blob = self.bucket.blob(source_blob_name)
            blob.download_to_filename(destination_file_path)
            
            logger.info(f"File {source_blob_name} downloaded to {destination_file_path}")
            
            return {
                "success": True,
                "message": "File downloaded successfully",
                "local_path": destination_file_path
            }
            
        except NotFound:
            return {
                "success": False,
                "message": f"File {source_blob_name} not found in bucket {self.bucket_name}"
            }
        except Exception as e:
            logger.error(f"Error downloading file {source_blob_name}: {str(e)}")
            return {
                "success": False,
                "message": f"Download failed: {str(e)}"
            }
    
    def delete_file(self, blob_name: str) -> dict:
        """
        Delete a file from GCS bucket
        
        Args:
            blob_name: Name of the file to delete
            
        Returns:
            dict: Delete result
        """
        try:
            blob = self.bucket.blob(blob_name)
            blob.delete()
            
            logger.info(f"File {blob_name} deleted successfully")
            
            return {
                "success": True,
                "message": f"File {blob_name} deleted successfully"
            }
            
        except NotFound:
            return {
                "success": False,
                "message": f"File {blob_name} not found in bucket {self.bucket_name}"
            }
        except Exception as e:
            logger.error(f"Error deleting file {blob_name}: {str(e)}")
            return {
                "success": False,
                "message": f"Delete failed: {str(e)}"
            }
    
    def list_files(self, prefix: str = None) -> dict:
        """
        List files in the GCS bucket
        
        Args:
            prefix: Optional prefix to filter files
            
        Returns:
            dict: List of files
        """
        try:
            blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
            
            files = []
            for blob in blobs:
                files.append({
                    "name": blob.name,
                    "size": blob.size,
                    "created": blob.time_created.isoformat() if blob.time_created else None,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "content_type": blob.content_type
                })
            
            return {
                "success": True,
                "files": files,
                "count": len(files)
            }
            
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to list files: {str(e)}"
            }
    
    def file_exists(self, blob_name: str) -> bool:
        """
        Check if a file exists in the bucket
        
        Args:
            blob_name: Name of the file to check
            
        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            blob = self.bucket.blob(blob_name)
            return blob.exists()
        except Exception:
            return False
        
   