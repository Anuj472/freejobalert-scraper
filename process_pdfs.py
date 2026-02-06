#!/usr/bin/env python
"""Process jobs and upload FreeJobAlert PDFs to Google Drive."""

import logging
import sys
import time
import argparse
from typing import List, Dict

from config import Config
from supabase_client import SupabaseClient
from gdrive_uploader import GoogleDriveUploader
from scraper import FreeJobAlertScraper

logger = logging.getLogger(__name__)

def setup_logging(log_level: str = 'INFO'):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('pdf_processor.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def is_freejobalert_pdf(url: str) -> bool:
    """Check if URL is a FreeJobAlert hosted PDF."""
    if not url:
        return False
    url_lower = url.lower()
    return 'freejobalert.com' in url_lower or 'img2.freejobalert.com' in url_lower

def process_job_pdfs(batch_size: int = 10, max_jobs: int = None):
    """
    Process jobs with FreeJobAlert PDFs and upload them to Google Drive.
    
    Args:
        batch_size: Number of jobs to process in one batch
        max_jobs: Maximum number of jobs to process (None = all)
    """
    try:
        # Validate configuration
        Config.validate()
        
        # Initialize clients
        logger.info("Initializing clients...")
        db_client = SupabaseClient()
        drive_uploader = GoogleDriveUploader()
        scraper = FreeJobAlertScraper()
        
        # Get jobs that need PDF processing
        # These are jobs where pdf_url is NULL and gdrive_link is NULL
        logger.info("Fetching jobs that need PDF processing...")
        jobs = db_client.get_jobs_without_gdrive_link(limit=batch_size)
        
        if not jobs:
            logger.info("No jobs found that need PDF processing")
            return
        
        logger.info(f"Found {len(jobs)} jobs to process")
        
        # Limit to max_jobs if specified
        if max_jobs:
            jobs = jobs[:max_jobs]
            logger.info(f"Processing {len(jobs)} jobs (limited by max_jobs)")
        
        processed_count = 0
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for idx, job in enumerate(jobs, 1):
            job_url = job.get('job_url')
            job_title = job.get('title', 'Unknown')
            
            logger.info(f"\n{'='*80}")
            logger.info(f"Processing job {idx}/{len(jobs)}: {job_title}")
            logger.info(f"Job URL: {job_url}")
            
            try:
                # Fetch fresh job details to get PDF URL
                logger.info("Fetching fresh job details...")
                job_details = scraper.get_job_details(job_url)
                
                if not job_details:
                    logger.warning(f"Could not fetch details for job: {job_title}")
                    failed_count += 1
                    continue
                
                pdf_url = job_details.get('official_notification_pdf')
                
                if not pdf_url:
                    logger.info(f"No PDF URL found for job: {job_title}")
                    skipped_count += 1
                    continue
                
                # Check if it's a FreeJobAlert PDF
                if not is_freejobalert_pdf(pdf_url):
                    logger.info(f"PDF is external (not FreeJobAlert): {pdf_url[:80]}")
                    # Update with external PDF URL
                    db_client.update_job(job_url, {'pdf_url': pdf_url})
                    logger.info("Updated job with external PDF URL")
                    success_count += 1
                    processed_count += 1
                    continue
                
                # FreeJobAlert PDF - needs upload
                logger.info(f"FreeJobAlert PDF detected: {pdf_url[:80]}")
                logger.info("Uploading to Google Drive...")
                
                # Upload to Google Drive
                drive_link = drive_uploader.upload_pdf_from_url(
                    pdf_url=pdf_url,
                    job_title=job_title[:50]  # Limit title length
                )
                
                if drive_link:
                    # Update database with Google Drive link
                    logger.info(f"Upload successful! Drive link: {drive_link}")
                    db_client.update_job(job_url, {'gdrive_link': drive_link})
                    logger.info("✅ Job updated with Google Drive link")
                    success_count += 1
                else:
                    logger.error("❌ Failed to upload PDF to Google Drive")
                    failed_count += 1
                
                processed_count += 1
                
                # Rate limiting to avoid overwhelming services
                if idx < len(jobs):
                    logger.info(f"Waiting {Config.REQUEST_DELAY} seconds before next job...")
                    time.sleep(Config.REQUEST_DELAY)
                
            except Exception as e:
                logger.error(f"Error processing job {job_title}: {e}")
                failed_count += 1
                processed_count += 1
                continue
        
        # Summary
        logger.info(f"\n{'='*80}")
        logger.info("PDF Processing Complete!")
        logger.info(f"{'='*80}")
        logger.info(f"Total jobs processed: {processed_count}")
        logger.info(f"Successfully uploaded: {success_count}")
        logger.info(f"Failed: {failed_count}")
        logger.info(f"Skipped (no PDF): {skipped_count}")
        
    except Exception as e:
        logger.error(f"Fatal error in process_job_pdfs: {e}")
        raise

def get_upload_stats():
    """Get statistics about PDF upload status."""
    try:
        db_client = SupabaseClient()
        
        # Get counts
        logger.info("\nPDF Upload Statistics:")
        logger.info("="*60)
        
        # Jobs needing upload (NULL pdf_url and NULL gdrive_link)
        needs_upload = db_client.get_jobs_without_gdrive_link(limit=1000)
        logger.info(f"Jobs needing PDF processing: {len(needs_upload)}")
        
        # Jobs with external PDFs
        result = db_client.client.table('jobs') \
            .select('id') \
            .not_.is_('pdf_url', 'null') \
            .execute()
        external_pdf_count = len(result.data) if result.data else 0
        logger.info(f"Jobs with external PDFs: {external_pdf_count}")
        
        # Jobs with Drive links
        result = db_client.client.table('jobs') \
            .select('id') \
            .not_.is_('gdrive_link', 'null') \
            .execute()
        drive_link_count = len(result.data) if result.data else 0
        logger.info(f"Jobs with Google Drive links: {drive_link_count}")
        
        # Total jobs
        result = db_client.client.table('jobs').select('id').execute()
        total_count = len(result.data) if result.data else 0
        logger.info(f"Total jobs in database: {total_count}")
        
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Process FreeJobAlert PDFs and upload to Google Drive'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of jobs to process per batch (default: 10)'
    )
    parser.add_argument(
        '--max-jobs',
        type=int,
        default=None,
        help='Maximum number of jobs to process (default: all in batch)'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show statistics only, do not process'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    logger.info("FreeJobAlert PDF Processor")
    logger.info("="*80)
    
    try:
        if args.stats:
            get_upload_stats()
        else:
            process_job_pdfs(
                batch_size=args.batch_size,
                max_jobs=args.max_jobs
            )
    
    except KeyboardInterrupt:
        logger.info("\nProcess interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
