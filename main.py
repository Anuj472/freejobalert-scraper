#!/usr/bin/env python3
"""Main execution script for FreeJobAlert scraper.

Fixed: Google Drive upload logic
- FreeJobAlert PDFs → Upload to Drive → Save in gdrive_link
- External PDFs → Keep original URL in pdf_url
"""

import sys
import logging
import argparse
import os
from typing import List
from datetime import datetime
from urllib.parse import urlparse

from config import Config
from scraper import FreeJobAlertScraper
from supabase_client import SupabaseClient
from gdrive_upload import GoogleDriveUploader

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def is_freejobalert_pdf(url: str) -> bool:
    """Check if PDF is hosted on FreeJobAlert domain."""
    if not url:
        return False
    parsed = urlparse(url.lower())
    return 'freejobalert.com' in parsed.netloc

def process_job(
    job: dict,
    scraper: FreeJobAlertScraper,
    supabase_client: SupabaseClient,
    gdrive_uploader: GoogleDriveUploader = None
) -> bool:
    """Process a single job: fetch details, download PDF, upload to Drive, save to DB.
    
    Logic:
    - If PDF is from FreeJobAlert → Download + Upload to Drive → Save in gdrive_link
    - If PDF is external → Keep original URL in pdf_url
    """
    try:
        # Fetch detailed job information
        logger.info(f"Processing: {job['title']}")
        details = scraper.get_job_details(job['details_url'])
        
        if not details:
            logger.warning(f"Could not fetch details for: {job['title']}")
            return False
        
        # Merge basic info with details
        job_data = {**job, **details}
        
        # Initialize PDF-related fields
        job_data['gdrive_link'] = None
        
        # Handle PDF based on source
        pdf_url = job_data.get('pdf_url') or job_data.get('official_notification_pdf')
        
        if pdf_url and gdrive_uploader:
            # Check if PDF needs to be uploaded to Google Drive
            needs_upload = is_freejobalert_pdf(pdf_url) or job_data.get('pdf_needs_upload', False)
            
            if needs_upload:
                # FreeJobAlert PDF → Upload to Google Drive
                logger.info(f"FreeJobAlert PDF detected: {pdf_url[:60]}...")
                logger.info(f"Downloading and uploading to Google Drive...")
                
                # Create temp filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                org_name = job_data.get('organization', 'Job').replace(' ', '_')[:30]
                pdf_filename = f"{org_name}_{timestamp}.pdf"
                pdf_path = os.path.join('temp', pdf_filename)
                
                # Ensure temp directory exists
                os.makedirs('temp', exist_ok=True)
                
                # Download PDF
                if scraper.download_pdf(pdf_url, pdf_path):
                    # Upload to Google Drive
                    gdrive_link = gdrive_uploader.upload_pdf_and_get_link(pdf_path)
                    
                    if gdrive_link:
                        # Save Google Drive link
                        job_data['gdrive_link'] = gdrive_link
                        logger.info(f"✓ PDF uploaded to Google Drive: {gdrive_link[:60]}...")
                    else:
                        logger.warning(f"Failed to upload PDF to Google Drive")
                    
                    # Clean up temp file
                    try:
                        os.remove(pdf_path)
                    except:
                        pass
                else:
                    logger.warning(f"Failed to download PDF from: {pdf_url[:60]}...")
            else:
                # External PDF → Keep original URL
                logger.info(f"External PDF (no upload needed): {pdf_url[:60]}...")
                job_data['pdf_url'] = pdf_url
        
        # Insert into Supabase
        if supabase_client.insert_job(job_data):
            logger.info(f"Successfully saved: {job['title']}")
            if job_data.get('gdrive_link'):
                logger.info(f"  → Google Drive: {job_data['gdrive_link'][:60]}...")
            if job_data.get('pdf_url'):
                logger.info(f"  → PDF URL: {job_data['pdf_url'][:60]}...")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error processing job {job.get('title')}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Scrape jobs from FreeJobAlert.com')
    parser.add_argument(
        '--category',
        type=str,
        help='Specific category to scrape (e.g., latest-notifications)'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=Config.MAX_PAGES_PER_CATEGORY,
        help=f'Maximum pages to scrape per category (default: {Config.MAX_PAGES_PER_CATEGORY})'
    )
    parser.add_argument(
        '--no-pdf',
        action='store_true',
        help='Skip PDF download and Google Drive upload'
    )
    
    args = parser.parse_args()
    
    try:
        # Validate configuration
        Config.validate()
        logger.info("Configuration validated successfully")
        
        # Initialize components
        logger.info("Initializing scraper components...")
        scraper = FreeJobAlertScraper()
        supabase_client = SupabaseClient()
        
        # Initialize Google Drive uploader if not disabled
        gdrive_uploader = None
        if not args.no_pdf:
            try:
                gdrive_uploader = GoogleDriveUploader()
                logger.info("✓ Google Drive uploader initialized")
            except Exception as e:
                logger.warning(f"Google Drive uploader not available: {e}")
                logger.warning("PDFs will not be uploaded to Drive (URLs will still be saved)")
        
        # Determine categories to scrape
        if args.category:
            categories = [args.category]
        else:
            categories = Config.CATEGORIES
        
        logger.info(f"Starting scrape for categories: {categories}")
        
        # Scrape jobs from all categories
        all_jobs = []
        for category in categories:
            try:
                jobs = scraper.scrape_category(category, args.max_pages)
                all_jobs.extend(jobs)
            except Exception as e:
                logger.error(f"Error scraping category {category}: {e}")
                continue
        
        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        
        if not all_jobs:
            logger.warning("No jobs found")
            return
        
        logger.info(f"Found {len(all_jobs)} jobs. Processing...")
        
        # Process each job
        processed = 0
        skipped = 0
        
        for job in all_jobs:
            try:
                # Check if already exists
                if supabase_client.job_exists(job['details_url']):
                    logger.info(f"Job already exists: {job['title']}")
                    skipped += 1
                    continue
                
                # Process the job
                if process_job(job, scraper, supabase_client, gdrive_uploader):
                    processed += 1
                    
            except Exception as e:
                logger.error(f"Error processing job: {e}")
                continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Scraping complete!")
        logger.info(f"Total jobs found: {len(all_jobs)}")
        logger.info(f"Jobs processed: {processed}")
        logger.info(f"Jobs skipped (already exist): {skipped}")
        logger.info(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        logger.info("\nScraping interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
