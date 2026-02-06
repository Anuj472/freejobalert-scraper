#!/usr/bin/env python3
"""Main execution script for FreeJobAlert scraper."""

import sys
import logging
import argparse
from typing import List

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

def process_jobs(jobs: List[dict], supabase_client: SupabaseClient, gdrive_uploader: GoogleDriveUploader, scraper: FreeJobAlertScraper):
    """Process scraped jobs: download PDFs, upload to Drive, save to Supabase."""
    processed = 0
    
    for job in jobs:
        try:
            # Check if job already exists
            if supabase_client.job_exists(job['job_url']):
                logger.info(f"Skipping existing job: {job['title']}")
                continue
            
            # Download PDF if available
            pdf_path = None
            gdrive_link = None
            
            if job.get('pdf_url'):
                logger.info(f"Downloading PDF for: {job['title']}")
                pdf_path = scraper.download_pdf(job['pdf_url'], job['title'])
                
                if pdf_path:
                    # Upload to Google Drive
                    logger.info(f"Uploading PDF to Google Drive: {job['title']}")
                    gdrive_link = gdrive_uploader.upload_pdf_and_get_link(pdf_path)
                    
                    if gdrive_link:
                        job['gdrive_link'] = gdrive_link
                        logger.info(f"PDF uploaded successfully: {gdrive_link}")
                    else:
                        logger.warning(f"Failed to upload PDF to Google Drive: {job['title']}")
                else:
                    logger.warning(f"Failed to download PDF: {job['title']}")
            
            # Insert job into Supabase
            result = supabase_client.insert_job(job)
            
            if result:
                processed += 1
                logger.info(f"Successfully processed job: {job['title']}")
            
        except Exception as e:
            logger.error(f"Error processing job {job.get('title')}: {e}")
            continue
    
    return processed

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Scrape jobs from FreeJobAlert.com')
    parser.add_argument(
        '--category',
        type=str,
        help='Specific category to scrape (e.g., government-jobs)'
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
        gdrive_uploader = GoogleDriveUploader() if not args.no_pdf else None
        
        # Determine categories to scrape
        if args.category:
            categories = [args.category]
        else:
            categories = Config.CATEGORIES
        
        logger.info(f"Starting scrape for categories: {categories}")
        
        # Scrape jobs
        jobs = scraper.scrape_all_categories(categories, args.max_pages)
        
        if not jobs:
            logger.warning("No jobs found")
            return
        
        logger.info(f"Found {len(jobs)} jobs. Processing...")
        
        # Process jobs
        if gdrive_uploader:
            processed = process_jobs(jobs, supabase_client, gdrive_uploader, scraper)
        else:
            # Just insert into Supabase without PDF handling
            processed = supabase_client.batch_insert_jobs(jobs)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Scraping complete!")
        logger.info(f"Total jobs found: {len(jobs)}")
        logger.info(f"Jobs processed: {processed}")
        logger.info(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        logger.info("\nScraping interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()