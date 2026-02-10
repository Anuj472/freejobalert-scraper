"""Supabase database client with integrated content validation.

IMPORTANT CHANGES:
- Added content_validator import
- Added sanitize_job_data() call before insert
- Two-stage validation ensures NO freejobalert references reach database
"""

import logging
import json
from typing import Dict, List, Optional
from supabase import create_client, Client
from datetime import datetime
import re

from config import Config
from content_validator import sanitize_job_data  # ← NEW IMPORT

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
            logger.info("✅ Content validator integrated")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    def _check_freejobalert_url_column(self):
        """Check if freejobalert_url column exists in jobs table."""
        try:
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
            if '-' in date_str:
                parts = date_str.strip().split('-')
                if len(parts) == 3:
                    day, month, year = parts
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif '/' in date_str:
                parts = date_str.strip().split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_str.strip()):
                return date_str.strip()
            
            logger.warning(f"Could not parse date: {date_str}")
            return None
        except Exception as e:
            logger.warning(f"Error parsing date '{date_str}': {e}")
            return None
    
    def _parse_vacancies(self, vacancies_str: str) -> Optional[int]:
        """Extract number from vacancy string."""
        if not vacancies_str:
            return None
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
            if self.has_fja_url_column:
                try:
                    result = self.client.table('jobs').select('id').eq('freejobalert_url', fja_url).execute()
                    if len(result.data) > 0:
                        return True
                except Exception:
                    pass
            
            if self._is_freejobalert_url(fja_url):
                result = self.client.table('jobs').select('id').eq('job_url', fja_url).execute()
                return len(result.data) > 0
            
            return False
        except Exception as e:
            logger.error(f"Error checking if job exists: {e}")
            return False
    
    def insert_job(self, job_data: Dict) -> Optional[Dict]:
        """Insert a new job into the database with content validation.
        
        CRITICAL CHANGES:
        - Sanitizes all content before insert
        - Validates NO freejobalert references exist
        - Logs validation results
        """
        try:
            fja_url = job_data.get('freejobalert_url') or job_data.get('details_url')
            
            if not fja_url:
                logger.error("Job data missing FreeJobAlert source URL")
                return None
            
            if self.job_exists(fja_url):
                logger.info(f"Job already exists: {job_data.get('title')}")
                return None
            
            # Parse dates
            post_date = self._parse_date(job_data.get('post_date'))
            last_date = self._parse_date(job_data.get('last_date'))
            
            # Extract vacancies
            vacancies = job_data.get('vacancies')
            if vacancies is None and job_data.get('title'):
                vacancies = self._parse_vacancies(job_data['title'])
            
            # Build insert data
            insert_data = {
                'title': job_data.get('title'),
                'organization': job_data.get('organization'),
                'qualification': job_data.get('qualification'),
                'category': job_data.get('category'),
                'advt_no': job_data.get('advt_no'),
            }
            
            # Job URL validation
            job_url = job_data.get('job_url')
            if job_url:
                if self._is_freejobalert_url(job_url):
                    logger.error(f"🚨 CRITICAL: job_url contains FreeJobAlert link! {job_url[:70]}")
                    job_url = None
                else:
                    insert_data['job_url'] = job_url
                    logger.info(f"✓ Apply Online link: {job_url[:70]}...")
            else:
                logger.info("⚠️  No Apply Online link found - job_url will be NULL")
            
            # Store FreeJobAlert source URL
            if self.has_fja_url_column:
                insert_data['freejobalert_url'] = fja_url
                logger.debug(f"FreeJobAlert source: {fja_url[:70]}...")
            
            # Add dates
            if post_date:
                insert_data['post_date'] = post_date
            if last_date:
                insert_data['last_date'] = last_date
            if vacancies:
                insert_data['vacancies'] = vacancies
            
            # Location
            if job_data.get('location'):
                insert_data['location'] = job_data.get('location')
            
            # PDF URL validation
            pdf_url = job_data.get('pdf_url') or job_data.get('official_notification_pdf')
            if pdf_url:
                if self._is_freejobalert_url(pdf_url):
                    logger.warning(f"🚨 Rejected FreeJobAlert PDF URL: {pdf_url[:70]}")
                else:
                    insert_data['pdf_url'] = pdf_url
                    pdf_source = "Google Drive" if 'drive.google.com' in pdf_url else "Organization"
                    logger.debug(f"PDF URL ({pdf_source}): {pdf_url[:70]}...")
            
            # Official website validation
            official_website = job_data.get('official_website')
            if official_website:
                if self._is_freejobalert_url(official_website):
                    logger.warning(f"🚨 Rejected FreeJobAlert official_website: {official_website[:70]}")
                else:
                    insert_data['official_website'] = official_website
            
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
            
            # Blog-related fields
            if job_data.get('seo_title'):
                insert_data['seo_title'] = job_data.get('seo_title')
            if job_data.get('meta_description'):
                insert_data['meta_description'] = job_data.get('meta_description')
            if job_data.get('blog_article'):
                insert_data['blog_article'] = job_data.get('blog_article')
            
            # Highlights and FAQs
            if job_data.get('highlights'):
                highlights = job_data.get('highlights')
                if isinstance(highlights, list) and highlights:
                    insert_data['highlights'] = json.dumps(highlights)
            if job_data.get('faqs'):
                faqs = job_data.get('faqs')
                if isinstance(faqs, list) and faqs:
                    insert_data['faqs'] = json.dumps(faqs)
            
            # Data source
            if job_data.get('data_source'):
                insert_data['data_source'] = job_data.get('data_source')
            
            # 🛡️ CRITICAL: SANITIZE ALL CONTENT BEFORE INSERT
            logger.info("🛡️ Running content validation...")
            insert_data = sanitize_job_data(insert_data)
            logger.info("✅ Content validation complete")
            
            # Remove None values
            insert_data = {k: v for k, v in insert_data.items() if v is not None}
            
            logger.debug(f"Inserting job with {len(insert_data)} fields")
            
            # Log blog status
            if insert_data.get('blog_article'):
                blog_len = len(insert_data['blog_article'])
                logger.info(f"✓ Blog content included ({blog_len} chars)")
                if insert_data.get('data_source'):
                    logger.info(f"   Data source: {insert_data['data_source']}")
            
            # Insert into database
            result = self.client.table('jobs').insert(insert_data).execute()
            
            if result.data:
                logger.info(f"Successfully inserted job: {job_data.get('title')}")
                if insert_data.get('pdf_url'):
                    pdf_source = "Google Drive" if 'drive.google.com' in insert_data['pdf_url'] else "External"
                    logger.info(f"  - PDF ({pdf_source}): {insert_data['pdf_url'][:80]}")
                if insert_data.get('job_url'):
                    logger.info(f"  - Apply URL: {insert_data['job_url'][:80]}")
                if insert_data.get('official_website'):
                    logger.info(f"  - Official Site: {insert_data['official_website'][:80]}")
                if insert_data.get('blog_article'):
                    logger.info(f"  - Blog: {len(insert_data['blog_article'])} chars")
                return result.data[0]
            else:
                logger.warning(f"No data returned after inserting: {job_data.get('title')}")
                return None
                
        except Exception as e:
            logger.error(f"Error inserting job {job_data.get('title')}: {e}")
            logger.error(f"Insert data keys: {list(insert_data.keys()) if 'insert_data' in locals() else 'N/A'}")
            return None
    
    def update_job(self, job_identifier: str, update_data: Dict, by_fja_url: bool = False) -> Optional[Dict]:
        """Update an existing job with content validation."""
        try:
            # Sanitize update data
            update_data = sanitize_job_data(update_data)
            
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
    
    def batch_insert_jobs(self, jobs: List[Dict]) -> int:
        """Insert multiple jobs in batch with validation."""
        inserted_count = 0
        
        for job in jobs:
            result = self.insert_job(job)
            if result:
                inserted_count += 1
        
        logger.info(f"Batch insert complete: {inserted_count}/{len(jobs)} jobs inserted")
        return inserted_count
    
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
