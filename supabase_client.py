"""Supabase database client for storing job data."""

import logging
from typing import Dict, List, Optional
from supabase import create_client, Client
from datetime import datetime
import re

from config import Config

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Client for interacting with Supabase database."""
    
    def __init__(self):
        """Initialize Supabase client."""
        try:
            self.client: Client = create_client(
                Config.SUPABASE_URL,
                Config.SUPABASE_KEY
            )
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Convert date from DD-MM-YYYY or DD/MM/YYYY to YYYY-MM-DD."""
        if not date_str or date_str.strip() == '':
            return None
        
        try:
            # Try DD-MM-YYYY format
            if '-' in date_str:
                parts = date_str.strip().split('-')
                if len(parts) == 3:
                    day, month, year = parts
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Try DD/MM/YYYY format
            elif '/' in date_str:
                parts = date_str.strip().split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Try YYYY-MM-DD (already correct)
            elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_str.strip()):
                return date_str.strip()
            
            # If all else fails, return None
            logger.warning(f"Could not parse date: {date_str}")
            return None
            
        except Exception as e:
            logger.warning(f"Error parsing date '{date_str}': {e}")
            return None
    
    def job_exists(self, job_url: str) -> bool:
        """Check if a job already exists in the database by job_url."""
        try:
            result = self.client.table('jobs').select('id').eq('job_url', job_url).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Error checking if job exists: {e}")
            return False
    
    def insert_job(self, job_data: Dict) -> Optional[Dict]:
        """Insert a new job into the database."""
        try:
            # Check if job already exists
            job_url = job_data.get('job_url') or job_data.get('details_url')
            if not job_url:
                logger.error("Job data missing job_url")
                return None
            
            if self.job_exists(job_url):
                logger.info(f"Job already exists: {job_data.get('title')}")
                return None
            
            # Parse dates to proper format
            post_date = self._parse_date(job_data.get('post_date'))
            last_date = self._parse_date(job_data.get('last_date'))
            
            # Only use columns that exist in your current schema
            insert_data = {
                'title': job_data.get('title'),
                'organization': job_data.get('organization'),
                'qualification': job_data.get('qualification'),
                'job_url': job_url,
                'category': job_data.get('category'),
                
                # PDF and website URLs
                'pdf_url': job_data.get('official_notification_pdf') or job_data.get('pdf_url'),
                'gdrive_link': job_data.get('pdf_link') or job_data.get('gdrive_link'),
            }
            
            # Add dates only if successfully parsed
            if post_date:
                insert_data['post_date'] = post_date
            if last_date:
                insert_data['last_date'] = last_date
            
            # Try to add location if column exists
            if job_data.get('location'):
                insert_data['location'] = job_data.get('location')
            
            # Remove None values
            insert_data = {k: v for k, v in insert_data.items() if v is not None}
            
            # Log what we're inserting for debugging
            logger.debug(f"Inserting job with fields: {list(insert_data.keys())}")
            
            # Insert into database
            result = self.client.table('jobs').insert(insert_data).execute()
            
            if result.data:
                logger.info(f"Successfully inserted job: {job_data.get('title')}")
                if insert_data.get('pdf_url'):
                    logger.info(f"  - PDF URL: {insert_data['pdf_url'][:80]}...")
                return result.data[0]
            else:
                logger.warning(f"No data returned after inserting: {job_data.get('title')}")
                return None
                
        except Exception as e:
            logger.error(f"Error inserting job {job_data.get('title')}: {e}")
            return None
    
    def update_job(self, job_url: str, update_data: Dict) -> Optional[Dict]:
        """Update an existing job in the database."""
        try:
            result = self.client.table('jobs').update(update_data).eq('job_url', job_url).execute()
            
            if result.data:
                logger.info(f"Successfully updated job: {job_url}")
                return result.data[0]
            else:
                logger.warning(f"No data returned after updating: {job_url}")
                return None
                
        except Exception as e:
            logger.error(f"Error updating job {job_url}: {e}")
            return None
    
    def update_gdrive_link(self, job_url: str, gdrive_link: str) -> bool:
        """Update Google Drive link for a job."""
        try:
            result = self.update_job(job_url, {'gdrive_link': gdrive_link})
            return result is not None
        except Exception as e:
            logger.error(f"Error updating Google Drive link: {e}")
            return False
    
    def batch_insert_jobs(self, jobs: List[Dict]) -> int:
        """Insert multiple jobs in batch."""
        inserted_count = 0
        
        for job in jobs:
            result = self.insert_job(job)
            if result:
                inserted_count += 1
        
        logger.info(f"Batch insert complete: {inserted_count}/{len(jobs)} jobs inserted")
        return inserted_count
    
    def get_jobs_without_gdrive_link(self, limit: int = 100) -> List[Dict]:
        """Get jobs that don't have a Google Drive link yet."""
        try:
            result = self.client.table('jobs') \
                .select('*') \
                .is_('gdrive_link', 'null') \
                .not_.is_('pdf_url', 'null') \
                .limit(limit) \
                .execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error fetching jobs without Google Drive links: {e}")
            return []
    
    def get_recent_jobs(self, days: int = 7, limit: int = 100) -> List[Dict]:
        """Get recently scraped jobs."""
        try:
            result = self.client.table('jobs') \
                .select('*') \
                .order('created_at', desc=True) \
                .limit(limit) \
                .execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error fetching recent jobs: {e}")
            return []