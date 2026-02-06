#!/usr/bin/env python3
"""Test script to verify connections to Supabase and Google Drive."""

import sys
import logging
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_configuration():
    """Test if configuration is valid."""
    logger.info("Testing configuration...")
    try:
        Config.validate()
        logger.info("✓ Configuration is valid")
        return True
    except Exception as e:
        logger.error(f"❌ Configuration error: {e}")
        return False

def test_supabase():
    """Test Supabase connection."""
    logger.info("\nTesting Supabase connection...")
    try:
        from supabase_client import SupabaseClient
        client = SupabaseClient()
        
        # Try a simple query
        result = client.client.table('jobs').select('id').limit(1).execute()
        
        logger.info("✓ Supabase connection successful")
        logger.info(f"  Database is accessible (found {len(result.data)} test records)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Supabase connection failed: {e}")
        logger.error("  Please check your SUPABASE_URL and SUPABASE_KEY in .env")
        return False

def test_google_drive():
    """Test Google Drive connection."""
    logger.info("\nTesting Google Drive connection...")
    try:
        from gdrive_upload import GoogleDriveUploader
        uploader = GoogleDriveUploader()
        
        # Try to list files
        files = uploader.list_files(max_results=1)
        
        logger.info("✓ Google Drive connection successful")
        logger.info(f"  Can access Drive (found {len(files)} files in target folder)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Google Drive connection failed: {e}")
        logger.error("  Please check your credentials.json and GOOGLE_DRIVE_FOLDER_ID")
        return False

def test_scraper():
    """Test basic scraper functionality."""
    logger.info("\nTesting scraper...")
    try:
        from scraper import FreeJobAlertScraper
        scraper = FreeJobAlertScraper()
        
        # Test fetching the homepage
        html = scraper.get_page(Config.BASE_URL)
        
        if html and len(html) > 0:
            logger.info("✓ Scraper can fetch pages")
            logger.info(f"  Retrieved {len(html)} bytes from homepage")
            return True
        else:
            logger.error("❌ Scraper failed to fetch pages")
            return False
            
    except Exception as e:
        logger.error(f"❌ Scraper test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("="*60)
    print("FreeJobAlert Scraper - Connection Tests")
    print("="*60)
    
    results = {
        'Configuration': test_configuration(),
        'Supabase': test_supabase(),
        'Google Drive': test_google_drive(),
        'Scraper': test_scraper()
    }
    
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:20s} {status}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\n✓ All tests passed! You're ready to run the scraper.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please fix the issues before running the scraper.")
        sys.exit(1)

if __name__ == '__main__':
    main()