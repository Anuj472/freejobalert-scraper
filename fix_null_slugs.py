#!/usr/bin/env python3
"""Script to fix jobs with NULL slugs.

This script:
1. Fetches all jobs with NULL slugs from Supabase
2. Generates slugs from title + organization
3. Updates the database with new slugs
"""

import sys
import logging
import argparse

from config import Config
from supabase_client import SupabaseClient
from slug_generator import generate_slug

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('slug_fix.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def fix_null_slugs(limit: int = 100, dry_run: bool = False):
    """
    Find and fix jobs with NULL slugs.
    
    Args:
        limit: Maximum number of jobs to process
        dry_run: If True, only show what would be done without making changes
    """
    try:
        # Initialize Supabase client
        supabase_client = SupabaseClient()
        
        # Get jobs with NULL slugs
        logger.info(f"Fetching jobs with NULL slugs (limit: {limit})...")
        jobs = supabase_client.get_jobs_with_null_slugs(limit)
        
        if not jobs:
            logger.info("No jobs with NULL slugs found!")
            return
        
        logger.info(f"Found {len(jobs)} jobs with NULL slugs")
        
        if dry_run:
            logger.info("[DRY RUN MODE] - No changes will be made")
        
        # Process each job
        success_count = 0
        skip_count = 0
        
        for job in jobs:
            job_id = job.get('id')
            title = job.get('title')
            org = job.get('organization')
            fja_url = job.get('freejobalert_url') or job_id  # Use fja_url for hash, fallback to job_id
            
            if not title or not org:
                logger.warning(f"Skipping job {job_id}: missing title or organization")
                skip_count += 1
                continue
            
            # Generate slug
            slug = generate_slug(title, org, fja_url)
            
            if not slug:
                logger.warning(f"Failed to generate slug for job {job_id}: {title}")
                skip_count += 1
                continue
            
            logger.info(f"Job: {title[:50]}...")
            logger.info(f"  Org: {org[:50]}...")
            logger.info(f"  Slug: {slug}")
            
            if not dry_run:
                # Update the database
                if supabase_client.update_slug(job_id, slug):
                    success_count += 1
                else:
                    skip_count += 1
            else:
                success_count += 1
            
            logger.info("")
        
        # Summary
        logger.info("="*60)
        logger.info("SUMMARY")
        logger.info("="*60)
        logger.info(f"Total jobs processed: {len(jobs)}")
        logger.info(f"Successfully {'generated' if dry_run else 'updated'}: {success_count}")
        logger.info(f"Skipped: {skip_count}")
        
        if dry_run:
            logger.info("")
            logger.info("This was a DRY RUN. No changes were made to the database.")
            logger.info("Run without --dry-run to apply changes.")
        
    except Exception as e:
        logger.error(f"Error fixing null slugs: {e}", exc_info=True)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Fix jobs with NULL slugs')
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Maximum number of jobs to process (default: 100)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    args = parser.parse_args()
    
    try:
        Config.validate()
        fix_null_slugs(args.limit, args.dry_run)
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(0)

if __name__ == '__main__':
    main()
