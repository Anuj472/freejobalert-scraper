"""Google Drive uploader for FreeJobAlert PDF files."""

import logging
import os
import json
import tempfile
import time
from typing import Optional, Dict
from pathlib import Path

import requests
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from config import Config

logger = logging.getLogger(__name__)

class GoogleDriveUploader:
    """Upload PDFs to Google Drive and get shareable links."""
    
    SCOPES = ['https://www.googleapis.com/auth/drive']
    REQUIRED_FIELDS = ['type', 'project_id', 'private_key_id', 'private_key', 
                       'client_email', 'client_id', 'auth_uri', 'token_uri']
    
    def __init__(self):
        """Initialize Google Drive service."""
        self.service = None
        self.folder_id = Config.GOOGLE_DRIVE_FOLDER_ID
        self._validate_and_authenticate()
    
    def _validate_and_authenticate(self):
        """Authenticate with Google Drive using OAuth 2.0 (token.json) or Service Account."""
        credentials_path = Config.GOOGLE_CREDENTIALS_PATH
        token_path = "token.json"

        # ── Prefer OAuth 2.0 (token.json) when it exists ─────────────────────
        if os.path.exists(token_path):
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request

                creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)

                # Refresh if expired
                if not creds.valid:
                    if creds.expired and creds.refresh_token:
                        logger.info("OAuth token expired — refreshing...")
                        creds.refresh(Request())
                        # Persist the refreshed token
                        with open(token_path, "w") as f:
                            f.write(creds.to_json())
                        logger.info("✓ OAuth token refreshed and saved")
                    else:
                        raise ValueError("OAuth token invalid and cannot be refreshed. Re-run the OAuth flow.")

                self.service = build("drive", "v3", credentials=creds)
                logger.info("✓ Google Drive authenticated via OAuth 2.0 (using your personal Drive quota)")
                if self.folder_id:
                    logger.info(f"   Target folder ID: {self.folder_id}")
                return

            except Exception as e:
                logger.warning(f"⚠️  OAuth auth failed ({e}), falling back to service account...")

        # ── Fallback: Service Account ────────────────────────────────────────
        if not os.path.exists(credentials_path):
            error_msg = (
                f"\n\n{'='*70}\n"
                f"ERROR: No credentials found!\n"
                f"{'='*70}\n"
                f"Either:\n"
                f"  A) Provide token.json (OAuth 2.0) — run the OAuth flow once\n"
                f"  B) Provide {credentials_path} (Service Account) and share\n"
                f"     the Drive folder with the service account email\n"
                f"{'='*70}\n"
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        try:
            with open(credentials_path, "r") as f:
                creds_data = json.load(f)

            missing_fields = [field for field in self.REQUIRED_FIELDS if field not in creds_data]
            if missing_fields:
                raise ValueError(f"Missing required service account fields: {', '.join(missing_fields)}")

            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=self.SCOPES
            )
            self.service = build("drive", "v3", credentials=credentials)
            logger.info("✓ Google Drive authenticated via Service Account")
            logger.info(f"   Service account: {creds_data.get('client_email')}")
            logger.warning(
                "⚠️  Service accounts have no Drive storage quota.\n"
                "   Make sure your Drive folder is shared with the service account as Editor,\n"
                "   OR use OAuth 2.0 by placing a valid token.json in the project root."
            )
            if self.folder_id:
                logger.info(f"   Target folder ID: {self.folder_id}")

        except Exception as e:
            logger.error(f"Service account authentication failed: {e}")
            raise
    
    def upload_pdf_from_url(
        self,
        pdf_url: str,
        filename: Optional[str] = None,
        job_title: Optional[str] = None
    ) -> Optional[str]:
        """
        Download PDF from URL and upload to Google Drive.
        
        Args:
            pdf_url: URL of the PDF to download
            filename: Optional custom filename (auto-generated if not provided)
            job_title: Optional job title for naming
        
        Returns:
            Shareable Google Drive link, or None if failed
        """
        temp_file = None
        
        try:
            # Generate filename
            if not filename:
                # Extract filename from URL or use timestamp
                url_filename = pdf_url.split('/')[-1].split('?')[0]
                if url_filename.endswith('.pdf'):
                    filename = url_filename
                else:
                    timestamp = int(time.time())
                    filename = f"job_{timestamp}.pdf"
            
            # Ensure .pdf extension
            if not filename.lower().endswith('.pdf'):
                filename += '.pdf'
            
            # Sanitize filename
            filename = self._sanitize_filename(filename)
            
            # Add job title prefix if provided
            if job_title:
                safe_title = self._sanitize_filename(job_title)[:50]
                filename = f"{safe_title}_{filename}"
            
            logger.info(f"Downloading PDF from: {pdf_url[:80]}...")
            
            # Download PDF to temporary file
            temp_file = self._download_pdf(pdf_url)
            if not temp_file:
                return None
            
            # Upload to Google Drive
            logger.info(f"Uploading to Google Drive: {filename}")
            drive_link = self._upload_file(temp_file, filename)
            
            if drive_link:
                logger.info(f"Upload successful: {drive_link}")
            
            return drive_link
            
        except Exception as e:
            logger.error(f"Error uploading PDF from {pdf_url}: {e}")
            return None
        
        finally:
            # Cleanup temporary file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")
    
    def _download_pdf(self, pdf_url: str) -> Optional[str]:
        """Download PDF to temporary file."""
        try:
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd)
            
            # Download with timeout and retry
            session = requests.Session()
            session.headers.update({
                'User-Agent': Config.USER_AGENT
            })
            
            response = session.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Write to temporary file
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(temp_path)
            logger.debug(f"Downloaded PDF: {file_size} bytes")
            
            # Validate it's actually a PDF
            with open(temp_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    logger.error("Downloaded file is not a valid PDF")
                    os.remove(temp_path)
                    return None
            
            return temp_path
            
        except requests.RequestException as e:
            logger.error(f"Error downloading PDF: {e}")
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading PDF: {e}")
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return None
    
    def _upload_file(self, file_path: str, filename: str) -> Optional[str]:
        """Upload file to Google Drive and return shareable link.
        
        Tries target folder first; if the folder is inaccessible (404),
        falls back to uploading to the root of Drive so scraping is never blocked.
        """
        def _do_upload(parents: list) -> Optional[str]:
            """Inner helper that performs the actual upload with given parents list."""
            file_metadata = {
                'name': filename,
                'mimeType': 'application/pdf'
            }
            if parents:
                file_metadata['parents'] = parents

            media = MediaFileUpload(
                file_path,
                mimetype='application/pdf',
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()

            file_id = file.get('id')

            # Make file publicly accessible (anyone with link can view)
            self.service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()

            shareable_link = f"https://drive.google.com/file/d/{file_id}/view"
            logger.info(f"File uploaded successfully with ID: {file_id}")
            return shareable_link

        try:
            # ── Attempt 1: upload into configured folder ──────────────────────
            if self.folder_id:
                try:
                    return _do_upload([self.folder_id])
                except HttpError as e:
                    if e.resp.status == 404:
                        logger.warning(
                            f"Folder {self.folder_id} not accessible (404). "
                            "Make sure the folder is shared with the service account as Editor. "
                            "Falling back to Drive root upload..."
                        )
                    else:
                        raise  # Re-raise non-404 HTTP errors

            # ── Attempt 2: fallback – upload to Drive root (no parents) ───────
            return _do_upload([])

        except HttpError as e:
            logger.error(f"Google Drive API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error uploading to Google Drive: {e}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove multiple spaces/underscores
        filename = ' '.join(filename.split())
        filename = '_'.join(filter(None, filename.split('_')))
        
        # Limit length
        max_length = 200
        if len(filename) > max_length:
            name, ext = os.path.splitext(filename)
            filename = name[:max_length - len(ext)] + ext
        
        return filename
    
    def get_file_info(self, file_id: str) -> Optional[Dict]:
        """Get file information from Google Drive."""
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields='id, name, size, createdTime, webViewLink'
            ).execute()
            return file
        except HttpError as e:
            logger.error(f"Error getting file info: {e}")
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file from Google Drive."""
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file: {file_id}")
            return True
        except HttpError as e:
            logger.error(f"Error deleting file: {e}")
            return False


def main():
    """Test the uploader."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Usage: python gdrive_uploader.py <pdf_url>")
        sys.exit(1)
    
    pdf_url = sys.argv[1]
    
    try:
        uploader = GoogleDriveUploader()
        link = uploader.upload_pdf_from_url(pdf_url, job_title="Test Job")
        
        if link:
            print(f"\n✅ Upload successful!")
            print(f"Shareable link: {link}")
        else:
            print("\n❌ Upload failed")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
