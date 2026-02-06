#!/usr/bin/env python3
"""Main execution script for FreeJobAlert scraper."""

import sys
import logging
import argparse
import os
from typing import List
from datetime import datetime

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

def process_job(
    job: dict,
    scraper: FreeJobAlertScraper,
    supabase_client: SupabaseClient,
    gdrive_uploader: GoogleDriveUploader = None
) -> bool:
    """Process a single job: fetch details, download PDF, upload to Drive, save to DB."""
    try:
        # Fetch detailed job information
        logger.info(f"Processing: {job['title']}")
        details = scraper.get_job_details(job['details_url'])
        
        if not details:
            logger.warning(f"Could not fetch details for: {job['title']}")
            return False
        
        # Merge basic info with details
        job_data = {**job, **details}
        
        # Handle PDF download and Google Drive upload
        if gdrive_uploader and job_data.get('official_notification_pdf'):
            pdf_url = job_data['official_notification_pdf']
            
            # Create temp filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_filename = f"{job['organization'].replace(' ', '_')}_{timestamp}.pdf"
            pdf_path = os.path.join('temp', pdf_filename)
            
            # Ensure temp directory exists
            os.makedirs('temp', exist_ok=True)
            
            # Download PDF
            logger.info(f"Downloading PDF from: {pdf_url}")
            if scraper.download_pdf(pdf_url, pdf_path):
                # Upload to Google Drive
                logger.info(f"Uploading PDF to Google Drive")
                gdrive_link = gdrive_uploader.upload_pdf_and_get_link(pdf_path)
                
                if gdrive_link:
                    job_data['pdf_link'] = gdrive_link
                    logger.info(f"PDF uploaded: {gdrive_link}")
                
                # Clean up temp file
                try:
                    os.remove(pdf_path)
                except:
                    pass
        
        # Insert into Supabase
        if supabase_client.insert_job(job_data):
            logger.info(f"Successfully saved: {job['title']}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error processing job {job.get('title')}: {e}")
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
        gdrive_uploader = GoogleDriveUploader() if not args.no_pdf else None
        
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
        for job in all_jobs:
            try:
                # Check if already exists
                if supabase_client.job_exists(job['details_url']):
                    logger.info(f"Job already exists: {job['title']}")
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
        logger.info(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        logger.info("\nScraping interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()