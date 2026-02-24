"""Supabase database client for storing job data."""

import logging
import json
from typing import Dict, List, Optional
from supabase import create_client, Client
from datetime import datetime
import re

from config import Config
from slug_generator import generate_slug, validate_slug

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
            self.client.table('jobs').select('freejobalert_url').limit(1).execute()
            self.has_fja_url_column = True
            logger.info("\u2713 freejobalert_url column exists")
        except Exception as e:
            self.has_fja_url_column = False
            logger.warning("\u26a0\ufe0f  freejobalert_url column not found - run MIGRATION_ADD_FJA_URL.sql to add it")
            logger.info("   Deduplication will use job_url field (less reliable)")

    # -------------------------------------------------------------------------
    # Slug uniqueness
    # -------------------------------------------------------------------------

    def _ensure_unique_slug(self, base_slug: str) -> str:
        """
        Return `base_slug` if no other job uses it, otherwise return
        `base_slug-2`, `base_slug-3`, … until a free slot is found.

        The primary slug (base_slug) matches exactly what the frontend's
        createSlug() generates as a fallback, so most jobs will resolve
        correctly even if job.slug is NULL in the DB.
        """
        slug = base_slug
        counter = 2
        while True:
            try:
                result = (
                    self.client.table('jobs')
                    .select('id')
                    .eq('slug', slug)
                    .execute()
                )
                if not result.data:          # slug is free
                    return slug
                # collision — try the next counter
                slug = f"{base_slug}-{counter}"
                counter += 1
                if counter > 99:             # safety valve
                    logger.warning(f"Slug collision limit reached for: {base_slug}")
                    return slug
            except Exception as exc:
                logger.warning(f"Slug uniqueness check failed ({exc}), using base slug")
                return base_slug

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def get_jobs_with_null_slugs(self, limit: int = 100) -> List[Dict]:
        """
        Get jobs that have NULL slugs and need slug generation.
        """
        try:
            result = self.client.table('jobs') \
                .select('id, title, organization, freejobalert_url') \
                .is_('slug', 'null') \
                .limit(limit) \
                .execute()
            
            jobs = result.data if result.data else []
            logger.info(f"Found {len(jobs)} jobs with NULL slugs")
            return jobs
        except Exception as e:
            logger.error(f"Error fetching jobs with null slugs: {e}")
            return []
    
    def update_slug(self, job_id: str, slug: str) -> bool:
        """
        Update the slug for a specific job.
        """
        try:
            if not validate_slug(slug):
                logger.error(f"Invalid slug format: {slug}")
                return False
            
            result = self.client.table('jobs') \
                .update({'slug': slug}) \
                .eq('id', job_id) \
                .execute()
            
            if result.data:
                logger.info(f"\u2713 Slug updated for job {job_id}: {slug}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating slug for job {job_id}: {e}")
            return False
    
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
        """Extract number from vacancy string like '260 Posts' or '01 Posts'."""
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
        """Insert a new job into the database.
        
        CRITICAL: job_url must be Apply Online link, never FreeJobAlert URL.
        SLUG: Generated to exactly match frontend createSlug() in JobCard.tsx.
              Uniqueness ensured via DB check + numeric counter (not hash suffix).
        """
        try:
            fja_url = job_data.get('freejobalert_url') or job_data.get('details_url')
            
            if not fja_url:
                logger.error("Job data missing FreeJobAlert source URL")
                return None
            
            if self.job_exists(fja_url):
                logger.info(f"Job already exists: {job_data.get('title')}")
                return None
            
            post_date = self._parse_date(job_data.get('post_date'))
            last_date = self._parse_date(job_data.get('last_date'))
            
            vacancies = job_data.get('vacancies')
            if vacancies is None and job_data.get('title'):
                vacancies = self._parse_vacancies(job_data['title'])
            
            insert_data = {
                'title': job_data.get('title'),
                'organization': job_data.get('organization'),
                'qualification': job_data.get('qualification'),
                'category': job_data.get('category'),
                'advt_no': job_data.get('advt_no'),
            }
            
            # ── Slug generation ──────────────────────────────────────────────
            # generate_slug() now mirrors the frontend createSlug() exactly.
            # _ensure_unique_slug() adds -2 / -3 counters only when needed,
            # so the base slug always matches the frontend fallback.
            title = job_data.get('title')
            org   = job_data.get('organization')
            if title and org:
                base_slug = generate_slug(title, org)        # no hash suffix
                if base_slug:
                    slug = self._ensure_unique_slug(base_slug)
                    insert_data['slug'] = slug
                    logger.info(f"\u2713 Generated slug: {slug}")
                else:
                    logger.warning("Failed to generate slug")
            else:
                logger.warning(
                    f"Missing title or org for slug generation: "
                    f"title={bool(title)}, org={bool(org)}"
                )
            
            # ── Apply Online URL ─────────────────────────────────────────────
            job_url = job_data.get('job_url')
            if job_url:
                if self._is_freejobalert_url(job_url):
                    logger.error(f"\U0001f6a8 CRITICAL: job_url contains FreeJobAlert link! {job_url[:70]}")
                    job_url = None
                else:
                    insert_data['job_url'] = job_url
                    logger.info(f"\u2713 Apply Online link: {job_url[:70]}...")
            else:
                logger.info("\u26a0\ufe0f  No Apply Online link found - job_url will be NULL")
            
            if self.has_fja_url_column:
                insert_data['freejobalert_url'] = fja_url
                logger.debug(f"FreeJobAlert source: {fja_url[:70]}...")
            
            if post_date:
                insert_data['post_date'] = post_date
            if last_date:
                insert_data['last_date'] = last_date
            
            if vacancies:
                insert_data['vacancies'] = vacancies
            
            if job_data.get('location'):
                insert_data['location'] = job_data.get('location')
            
            pdf_url = job_data.get('pdf_url') or job_data.get('official_notification_pdf')
            if pdf_url:
                if self._is_freejobalert_url(pdf_url):
                    logger.warning(f"\U0001f6a8 Rejected FreeJobAlert PDF URL: {pdf_url[:70]}")
                else:
                    insert_data['pdf_url'] = pdf_url
                    pdf_source = "Google Drive" if 'drive.google.com' in pdf_url else "Organization"
                    logger.debug(f"PDF URL ({pdf_source}): {pdf_url[:70]}...")
            
            official_website = job_data.get('official_website')
            if official_website:
                if self._is_freejobalert_url(official_website):
                    logger.warning(f"\U0001f6a8 Rejected FreeJobAlert official_website: {official_website[:70]}")
                else:
                    insert_data['official_website'] = official_website
            
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
            
            if job_data.get('important_dates'):
                important_dates = job_data.get('important_dates')
                if isinstance(important_dates, dict) and important_dates:
                    insert_data['important_dates'] = json.dumps(important_dates)
            
            if job_data.get('vacancy_details'):
                vacancy_details = job_data.get('vacancy_details')
                if isinstance(vacancy_details, dict) and vacancy_details:
                    insert_data['vacancy_details'] = json.dumps(vacancy_details)
            
            if job_data.get('seo_title'):
                insert_data['seo_title'] = job_data.get('seo_title')
            if job_data.get('meta_description'):
                insert_data['meta_description'] = job_data.get('meta_description')
            if job_data.get('blog_article'):
                insert_data['blog_article'] = job_data.get('blog_article')
            
            if job_data.get('highlights'):
                highlights = job_data.get('highlights')
                if isinstance(highlights, list) and highlights:
                    insert_data['highlights'] = json.dumps(highlights)
            
            if job_data.get('faqs'):
                faqs = job_data.get('faqs')
                if isinstance(faqs, list) and faqs:
                    insert_data['faqs'] = json.dumps(faqs)
            
            if job_data.get('data_source'):
                insert_data['data_source'] = job_data.get('data_source')
            
            insert_data = {k: v for k, v in insert_data.items() if v is not None}
            
            if insert_data.get('blog_article'):
                blog_len = len(insert_data['blog_article'])
                logger.info(f"\u2713 Blog content included ({blog_len} chars)")
                if insert_data.get('data_source'):
                    logger.info(f"   Data source: {insert_data['data_source']}")
            
            result = self.client.table('jobs').insert(insert_data).execute()
            
            if result.data:
                logger.info(f"Successfully inserted job: {job_data.get('title')}")
                if insert_data.get('slug'):
                    logger.info(f"  - Slug: {insert_data['slug']}")
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
        """Update an existing job in the database."""
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
    
    def batch_insert_jobs(self, jobs: List[Dict]) -> int:
        """Insert multiple jobs in batch."""
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
