"""Configuration settings for the FreeJobAlert scraper."""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Main configuration class."""
    
    # Supabase Configuration
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    # Google Drive Configuration
    GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
    GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    
    # Scraper Configuration
    BASE_URL = 'https://www.freejobalert.com'
    USER_AGENT = os.getenv(
        'SCRAPER_USER_AGENT',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Request settings
    REQUEST_DELAY = int(os.getenv('SCRAPER_DELAY', 3))  # Increased to 3 seconds
    MAX_RETRIES = int(os.getenv('SCRAPER_MAX_RETRIES', 3))
    REQUEST_TIMEOUT = int(os.getenv('SCRAPER_TIMEOUT', 30))
    
    # Main page URLs
    VIEW_ALL_URL = f'{BASE_URL}/view-all/'
    
    # Categories (sections on the page)
    CATEGORIES = [
        'Banks',
        'Other Govt Finance',
        'UPSC',
        'SSC',
        'Other All India',
        'All India Fellow',
        'Defence',
        'Railways',
    ]
    
    # Pagination
    MAX_PAGES_PER_CATEGORY = 1
    MAX_JOBS_PER_RUN = 50  # Limit jobs per run to avoid overload
    
    # File storage
    PDF_DOWNLOAD_DIR = 'pdfs'
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'scraper.log')
    
    @staticmethod
    def validate():
        """Validate required configuration."""
        errors = []
        
        if not Config.SUPABASE_URL:
            errors.append('SUPABASE_URL is not set')
        if not Config.SUPABASE_KEY:
            errors.append('SUPABASE_KEY is not set')
        
        # Google Drive is optional for testing
        if not Config.GOOGLE_DRIVE_FOLDER_ID:
            logger.warning('GOOGLE_DRIVE_FOLDER_ID is not set - PDF upload will be skipped')
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True

import logging
logger = logging.getLogger(__name__)