"""Supabase database client for storing job data."""

import logging
import json
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
            self._check_freejobalert_url_column()
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    def _check_freejobalert_url_column(self):
        """Check if freejobalert_url column exists in jobs table."""
        try:
            # Try to query with freejobalert_url field
            self.client.table('jobs').select('freejobalert_url').limit(1).execute()
            self.has_fja_url_column = True
            logger.info("✓ freejobalert_url column exists")
        except Exception as e:
            self.has_fja_url_column = False
            logger.warning("⚠️  freejobalert_url column not found - run MIGRATION_ADD_FJA_URL.sql to add it")
            logger.info("   Deduplication will use job_url field (less reliable)")
    
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
    
    def _parse_vacancies(self, vacancies_str: str) -> Optional[int]:
        """Extract number from vacancy string like '260 Posts' or '01 Posts'."""
        if not vacancies_str:
            return None
        
        # Extract numbers from string
        numbers = re.findall(r'\d+', str(vacancies_str))
        if numbers:
            try:
                return int(numbers[0])
            except ValueError:
                return None
        return None
    
    def _is_freejobalert_url(self, url: str) -> bool:
        """Check if URL is from FreeJobAlert domain."""
        if not url:
            return False
        return 'freejobalert.com' in url.lower()
    
    def job_exists(self, fja_url: str) -> bool:
        """Check if a job already exists by FreeJobAlert source URL."""
        try:
            # Try to check by freejobalert_url field (if column exists)
            if self.has_fja_url_column:
                try:
                    result = self.client.table('jobs').select('id').eq('freejobalert_url', fja_url).execute()
                    if len(result.data) > 0:
                        return True
                except Exception:
                    # Column check failed, skip
                    pass
            
            # Fallback: check by job_url if it's a FreeJobAlert URL (old records or no fja_url column)
            if self._is_freejobalert_url(fja_url):
                result = self.client.table('jobs').select('id').eq('job_url', fja_url).execute()
                return len(result.data) > 0
            
            return False
        except Exception as e:
            logger.error(f"Error checking if job exists: {e}")
            return False
    
    def insert_job(self, job_data: Dict) -> Optional[Dict]:
        """Insert a new job into the database."""
        try:
            # Get URLs
            fja_url = job_data.get('job_url') or job_data.get('details_url')  # FreeJobAlert article URL
            application_url = job_data.get('application_url')  # Organization's application URL
            official_website = job_data.get('official_website') or job_data.get('organization_url')
            
            if not fja_url:
                logger.error("Job data missing FreeJobAlert URL")
                return None
            
            # Check if job already exists using FreeJobAlert URL
            if self.job_exists(fja_url):
                logger.info(f"Job already exists: {job_data.get('title')}")
                return None
            
            # Parse dates to proper format
            post_date = self._parse_date(job_data.get('post_date'))
            last_date = self._parse_date(job_data.get('last_date'))
            
            # Extract vacancies count from title or vacancy_details
            vacancies = None
            if job_data.get('title'):
                vacancies = self._parse_vacancies(job_data['title'])
            
            # Build insert data with all schema fields
            insert_data = {
                'title': job_data.get('title'),
                'organization': job_data.get('organization'),
                'qualification': job_data.get('qualification'),
                'category': job_data.get('category'),
                'advt_no': job_data.get('advt_no'),
            }
            
            # IMPORTANT: job_url should be the organization's application URL, NOT FreeJobAlert URL
            # Priority: application_url > official_website > fja_url (fallback)
            if application_url:
                insert_data['job_url'] = application_url
                logger.info(f"Using application URL as job_url: {application_url[:80]}")
            elif official_website:
                insert_data['job_url'] = official_website
                logger.info(f"Using official website as job_url: {official_website[:80]}")
            else:
                # Fallback to FreeJobAlert URL if no organization URL found
                insert_data['job_url'] = fja_url
                logger.warning(f"No organization URL found, using FreeJobAlert URL: {fja_url[:80]}")
            
            # Store FreeJobAlert source URL for tracking (ONLY if column exists)
            if self.has_fja_url_column:
                insert_data['freejobalert_url'] = fja_url
            
            # Add dates
            if post_date:
                insert_data['post_date'] = post_date
            if last_date:
                insert_data['last_date'] = last_date
            
            # Add vacancies count
            if vacancies:
                insert_data['vacancies'] = vacancies
            
            # Location
            if job_data.get('location'):
                insert_data['location'] = job_data.get('location')
            
            # PDF URLs - Handle FreeJobAlert PDFs specially
            pdf_needs_upload = job_data.get('pdf_needs_upload', False)
            official_pdf = job_data.get('official_notification_pdf')
            
            if official_pdf:
                if pdf_needs_upload:
                    # FreeJobAlert hosted PDF - don't save, will be uploaded to Drive later
                    logger.info(f"FreeJobAlert PDF detected (will be uploaded to Drive): {official_pdf[:60]}")
                    # Leave pdf_url empty, will be filled with Drive link later
                else:
                    # External PDF - save directly
                    insert_data['pdf_url'] = official_pdf
            
            # Application and website URLs
            if application_url:
                insert_data['application_url'] = application_url
            
            if official_website:
                insert_data['official_website'] = official_website
            
            if job_data.get('organization_url'):
                insert_data['organization_url'] = job_data.get('organization_url')
            
            # Google Drive link (if already provided)
            if job_data.get('gdrive_link'):
                insert_data['gdrive_link'] = job_data.get('gdrive_link')
            
            # Text fields
            if job_data.get('full_description'):
                insert_data['full_description'] = job_data.get('full_description')
            
            if job_data.get('salary'):
                insert_data['salary'] = job_data.get('salary')
            
            if job_data.get('age_limit'):
                insert_data['age_limit'] = job_data.get('age_limit')
            
            if job_data.get('application_fee'):
                insert_data['application_fee'] = job_data.get('application_fee')
            
            if job_data.get('selection_process'):
                insert_data['selection_process'] = job_data.get('selection_process')
            
            if job_data.get('how_to_apply'):
                insert_data['how_to_apply'] = job_data.get('how_to_apply')
            
            # JSON fields
            if job_data.get('important_dates'):
                important_dates = job_data.get('important_dates')
                if isinstance(important_dates, dict) and important_dates:
                    insert_data['important_dates'] = json.dumps(important_dates)
            
            if job_data.get('vacancy_details'):
                vacancy_details = job_data.get('vacancy_details')
                if isinstance(vacancy_details, dict) and vacancy_details:
                    insert_data['vacancy_details'] = json.dumps(vacancy_details)
            
            # Remove None values
            insert_data = {k: v for k, v in insert_data.items() if v is not None}
            
            # Log what we're inserting for debugging
            logger.debug(f"Inserting job with {len(insert_data)} fields")
            logger.info(f"Job URL (organization): {insert_data.get('job_url', 'N/A')[:80]}")
            if self.has_fja_url_column:
                logger.info(f"Source URL (FreeJobAlert): {fja_url[:80]}")
            
            # Insert into database
            result = self.client.table('jobs').insert(insert_data).execute()
            
            if result.data:
                logger.info(f"Successfully inserted job: {job_data.get('title')}")
                if insert_data.get('pdf_url'):
                    logger.info(f"  - PDF URL: {insert_data['pdf_url'][:80]}")
                if insert_data.get('application_url'):
                    logger.info(f"  - Apply URL: {insert_data['application_url'][:80]}")
                if pdf_needs_upload:
                    logger.info(f"  ⚠️ FreeJobAlert PDF needs Drive upload")
                return result.data[0]
            else:
                logger.warning(f"No data returned after inserting: {job_data.get('title')}")
                return None
                
        except Exception as e:
            logger.error(f"Error inserting job {job_data.get('title')}: {e}")
            logger.error(f"Insert data keys: {list(insert_data.keys()) if 'insert_data' in locals() else 'N/A'}")
            return None
    
    def update_job(self, job_identifier: str, update_data: Dict, by_fja_url: bool = False) -> Optional[Dict]:
        """Update an existing job in the database.
        
        Args:
            job_identifier: job_url or freejobalert_url depending on by_fja_url flag
            update_data: Dictionary of fields to update
            by_fja_url: If True, search by freejobalert_url field, else by job_url
        """
        try:
            if by_fja_url and self.has_fja_url_column:
                result = self.client.table('jobs').update(update_data).eq('freejobalert_url', job_identifier).execute()
            else:
                result = self.client.table('jobs').update(update_data).eq('job_url', job_identifier).execute()
            
            if result.data:
                logger.info(f"Successfully updated job: {job_identifier[:80]}")
                return result.data[0]
            else:
                logger.warning(f"No data returned after updating: {job_identifier[:80]}")
                return None
                
        except Exception as e:
            logger.error(f"Error updating job {job_identifier}: {e}")
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
        """Get jobs that don't have a Google Drive link yet but have empty pdf_url.
        These are jobs with FreeJobAlert PDFs that need to be uploaded.
        """
        try:
            result = self.client.table('jobs') \
                .select('*') \
                .is_('gdrive_link', 'null') \
                .is_('pdf_url', 'null') \
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
                .order('scraped_at', desc=True) \
                .limit(limit) \
                .execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error fetching recent jobs: {e}")
            return []
