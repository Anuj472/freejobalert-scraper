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
    
    # LLM Configuration (Groq/Ollama)
    GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')  # Get from https://console.groq.com/
    GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')  # Best free model
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')  # Local model
    OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')  # Ollama server
    
    # LLM Strategy
    USE_LLM_FALLBACK = os.getenv('USE_LLM_FALLBACK', 'true').lower() == 'true'
    LLM_ALWAYS_ENABLED = os.getenv('LLM_ALWAYS_ENABLED', 'true').lower() == 'true'  # NEW: Use LLM for all jobs
    
    # Fallback thresholds (only used if LLM_ALWAYS_ENABLED=false)
    LLM_CRITICAL_FIELDS = ['title', 'organization', 'last_date', 'application_url']  # Must extract
    LLM_OPTIONAL_THRESHOLD = 3  # Use LLM if more than N optional fields missing
    
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
        
        # Google Drive is optional for testing
        if not Config.GOOGLE_DRIVE_FOLDER_ID:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning('GOOGLE_DRIVE_FOLDER_ID is not set - PDF upload will be skipped')
        
        # LLM is optional
        if not Config.GROQ_API_KEY and Config.USE_LLM_FALLBACK:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning('GROQ_API_KEY not set - LLM fallback will use Ollama if available')
            logger.info('Get free Groq API key: https://console.groq.com/')
            if Config.LLM_ALWAYS_ENABLED:
                logger.info('LLM_ALWAYS_ENABLED=true: LLM will be used for all jobs for best data quality')
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True