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
    REQUEST_DELAY = int(os.getenv('SCRAPER_DELAY', 2))  # Seconds between requests
    MAX_RETRIES = int(os.getenv('SCRAPER_MAX_RETRIES', 3))
    REQUEST_TIMEOUT = int(os.getenv('SCRAPER_TIMEOUT', 30))
    
    # Categories to scrape
    CATEGORIES = [
        'latest-notifications',
        'government-jobs',
        'bank-jobs',
        'railway-jobs',
        'teaching-jobs',
        'police-jobs',
        'engineering-jobs'
    ]
    
    # Pagination
    MAX_PAGES_PER_CATEGORY = 5
    
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
        if not Config.GOOGLE_DRIVE_FOLDER_ID:
            errors.append('GOOGLE_DRIVE_FOLDER_ID is not set')
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True