"""Configuration settings for the FreeJobAlert scraper.

Updated to use robust CSS-only parser by default (no LLM required).
"""

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
    
    # LLM Configuration (DISABLED BY DEFAULT - robust CSS parser is more reliable)
    USE_LLM_FALLBACK = os.getenv('USE_LLM_FALLBACK', 'false').lower() == 'true'
    
    # Only used if USE_LLM_FALLBACK=true
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b')
    OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
    LLM_ALWAYS_ENABLED = os.getenv('LLM_ALWAYS_ENABLED', 'false').lower() == 'true'
    
    # All fields to extract (matches database schema)
    ALL_EXTRACTION_FIELDS = [
        'title', 'organization', 'post_date', 'last_date', 'vacancies',
        'qualification', 'location', 'job_url', 'application_url',
        'official_website', 'pdf_url', 'category', 'advt_no',
        'salary', 'age_limit', 'application_fee', 'selection_process',
        'how_to_apply', 'important_dates', 'vacancy_details'
    ]
    
    # Critical fields (must be extracted)
    LLM_CRITICAL_FIELDS = ['title', 'organization', 'last_date', 'application_url']
    
    # Optional threshold for fallback mode
    LLM_OPTIONAL_THRESHOLD = 3
    
    # Scraper Configuration
    BASE_URL = 'https://www.freejobalert.com'
    USER_AGENT = os.getenv(
        'SCRAPER_USER_AGENT',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Request settings
    REQUEST_DELAY = int(os.getenv('SCRAPER_DELAY', 2))  # seconds between requests
    MAX_RETRIES = int(os.getenv('SCRAPER_MAX_RETRIES', 3))
    REQUEST_TIMEOUT = int(os.getenv('SCRAPER_TIMEOUT', 30))
    
    # Main page URLs
    VIEW_ALL_URL = f'{BASE_URL}/view-all/'
    
    # Categories (URL slugs)
    CATEGORIES = [
        'latest-notifications',
        'government-jobs',
        'bank-jobs',
        'railway-jobs',
        'teaching-jobs',
        'police-jobs',
        'engineering-jobs',
        'it-software-jobs',
        'defence-jobs',
        'medical-jobs',
        'law-jobs',
        'private-jobs'
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
        
        # Google Drive is optional
        if not Config.GOOGLE_DRIVE_FOLDER_ID:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning('GOOGLE_DRIVE_FOLDER_ID not set - PDF upload will be skipped')
        
        # Log parser being used
        import logging
        logger = logging.getLogger(__name__)
        if Config.USE_LLM_FALLBACK:
            logger.info(f'Parser: CSS + LLM fallback ({Config.OLLAMA_MODEL})')
        else:
            logger.info('Parser: Robust CSS-only (no LLM required) ✓')
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True
