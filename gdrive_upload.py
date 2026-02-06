"""Google Drive upload functionality."""

import os
import logging
from typing import Optional
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import pickle

from config import Config

logger = logging.getLogger(__name__)

class GoogleDriveUploader:
    """Upload files to Google Drive."""
    
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    
    def __init__(self):
        """Initialize Google Drive client."""
        self.service = None
        self.authenticate()
    
    def authenticate(self):
        """Authenticate with Google Drive API."""
        creds = None
        
        # Token file stores the user's access and refresh tokens
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refreshing credentials: {e}")
                    creds = None
            
            if not creds:
                # Try service account first
                if os.path.exists(Config.GOOGLE_CREDENTIALS_PATH):
                    try:
                        creds = service_account.Credentials.from_service_account_file(
                            Config.GOOGLE_CREDENTIALS_PATH,
                            scopes=self.SCOPES
                        )
                        logger.info("Authenticated using service account")
                    except Exception as e:
                        logger.warning(f"Service account auth failed: {e}")
                        # Fall back to OAuth flow
                        flow = InstalledAppFlow.from_client_secrets_file(
                            Config.GOOGLE_CREDENTIALS_PATH,
                            self.SCOPES
                        )
                        creds = flow.run_local_server(port=0)
                else:
                    raise FileNotFoundError(
                        f"Credentials file not found: {Config.GOOGLE_CREDENTIALS_PATH}"
                    )
            
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        try:
            self.service = build('drive', 'v3', credentials=creds)
            logger.info("Google Drive service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to build Google Drive service: {e}")
            raise
    
    def upload_file(
        self,
        file_path: str,
        folder_id: str = None,
        file_name: str = None
    ) -> Optional[str]:
        """Upload a file to Google Drive and return shareable link."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        
        try:
            # Use provided filename or extract from path
            if not file_name:
                file_name = os.path.basename(file_path)
            
            # File metadata
            file_metadata = {'name': file_name}
            
            # Add to specific folder if provided
            if folder_id:
                file_metadata['parents'] = [folder_id]
            elif Config.GOOGLE_DRIVE_FOLDER_ID:
                file_metadata['parents'] = [Config.GOOGLE_DRIVE_FOLDER_ID]
            
            # Upload file
            media = MediaFileUpload(file_path, resumable=True)
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()
            
            file_id = file.get('id')
            
            # Make file publicly accessible (optional - adjust permissions as needed)
            try:
                self.service.permissions().create(
                    fileId=file_id,
                    body={'type': 'anyone', 'role': 'reader'}
                ).execute()
                logger.info(f"File made publicly accessible: {file_name}")
            except HttpError as e:
                logger.warning(f"Could not set public permissions: {e}")
            
            # Get shareable link
            shareable_link = file.get('webViewLink')
            
            logger.info(f"File uploaded successfully: {file_name}")
            logger.info(f"Shareable link: {shareable_link}")
            
            return shareable_link
            
        except HttpError as error:
            logger.error(f"An error occurred during upload: {error}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during upload: {e}")
            return None
    
    def upload_pdf_and_get_link(self, pdf_path: str) -> Optional[str]:
        """Convenience method to upload PDF and return link."""
        return self.upload_file(pdf_path)
    
    def delete_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive."""
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"File deleted: {file_id}")
            return True
        except HttpError as error:
            logger.error(f"An error occurred during deletion: {error}")
            return False
    
    def list_files(self, folder_id: str = None, max_results: int = 100) -> list:
        """List files in Google Drive."""
        try:
            query = "trashed=false"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            elif Config.GOOGLE_DRIVE_FOLDER_ID:
                query += f" and '{Config.GOOGLE_DRIVE_FOLDER_ID}' in parents"
            
            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, webViewLink, createdTime)"
            ).execute()
            
            files = results.get('files', [])
            logger.info(f"Found {len(files)} files")
            return files
            
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            return []