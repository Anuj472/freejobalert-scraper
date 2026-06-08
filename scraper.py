"""Web scraper for FreeJobAlert.com with smart processing.

Features:
- PDF-first extraction using Gemma 4 multimodal
- Fallback to HTML text + LLM
- Always generates SEO blog
- Duplicate-page detection: stops pagination when site serves same content
"""

import logging
import time
import re
from typing import List, Optional, Dict, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config
from smart_processor import SmartJobProcessor

logger = logging.getLogger(__name__)


class FreeJobAlertScraper:
    """Scraper for FreeJobAlert.com job listings."""

    BASE_URL = "https://www.freejobalert.com"

    # If this fraction of a page's URLs already exist in seen_urls → it's a
    # duplicate page (site returned same HTML for every page number).
    DUPLICATE_PAGE_THRESHOLD = 0.70

    def __init__(self):
        """Initialize the scraper with session and smart processor."""
        self.session = requests.Session()

        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.session.headers.update({
            'User-Agent': Config.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        self.processor = SmartJobProcessor()
        logger.info("[OK] Scraper initialized with Smart Processor")
        logger.info("     - PDF-first extraction (Gemma 4 multimodal)")
        logger.info("     - HTML fallback (CSS parser)")
        logger.info("     - Always generates SEO blog")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_category(
        self,
        category: str,
        max_pages: int = None,
    ) -> List[dict]:
        """
        Scrape jobs from a specific category.

        Stops early if the site returns the same page for every URL (e.g.
        `latest-notifications` serves one giant page regardless of /page/N/).

        Args:
            category : Category slug, e.g. 'latest-notifications'
            max_pages: Hard ceiling on pages to fetch (None = unlimited)

        Returns:
            Deduplicated list of job dicts.
        """
        jobs: List[dict] = []
        seen_urls: Set[str] = set()   # all details_urls collected so far
        page = 1

        logger.info(f"Starting scrape for category: {category}")

        while True:
            if max_pages and page > max_pages:
                break

            url = (
                f"{self.BASE_URL}/{category}/"
                if page == 1
                else f"{self.BASE_URL}/{category}/page/{page}/"
            )
            logger.info(f"Scraping {category} page {page}: {url}")

            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                page_jobs = self._extract_jobs_from_tables(soup)

                if not page_jobs:
                    logger.info(f"No jobs found on page {page} — stopping.")
                    break

                # ── Duplicate-page detection ────────────────────────────
                # FreeJobAlert's listing pages (e.g. latest-notifications)
                # sometimes serve identical HTML for every /page/N/ URL.
                # Detect this by measuring URL overlap with previous pages.
                page_urls: Set[str] = {j['details_url'] for j in page_jobs}

                if seen_urls:  # skip check on page 1 (nothing to compare)
                    overlap = len(page_urls & seen_urls)
                    overlap_pct = overlap / len(page_urls) if page_urls else 1.0

                    if overlap_pct >= self.DUPLICATE_PAGE_THRESHOLD:
                        logger.warning(
                            f"\u26a0\ufe0f  Page {page} is {overlap_pct:.0%} duplicate "
                            f"({overlap}/{len(page_urls)} URLs already seen). "
                            f"Site is not paginating — stopping."
                        )
                        break

                # ── Add only genuinely new jobs ─────────────────────────
                new_jobs = [j for j in page_jobs if j['details_url'] not in seen_urls]
                seen_urls.update(page_urls)

                logger.info(
                    f"Page {page}: {len(page_jobs)} total, "
                    f"{len(new_jobs)} new, {len(seen_urls)} unique so far"
                )
                jobs.extend(new_jobs)

                time.sleep(Config.REQUEST_DELAY)
                page += 1

            except requests.RequestException as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        logger.info(f"Total unique jobs scraped from {category}: {len(jobs)}")
        return jobs

    # ------------------------------------------------------------------
    # Table extraction helpers
    # ------------------------------------------------------------------

    def _extract_jobs_from_tables(self, soup: BeautifulSoup) -> List[dict]:
        """Extract job listings from all job tables on a page."""
        jobs = []
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables on page")

        for idx, table in enumerate(tables):
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue

            first_row = rows[0]
            header_cells = first_row.find_all('th')
            if not header_cells:
                continue

            headers = [th.get_text(strip=True).lower() for th in header_cells]
            job_table_keywords = ['post date', 'recruitment', 'exam', 'post name', 'qualification']
            if not any(kw in ' '.join(headers) for kw in job_table_keywords):
                logger.debug(f"Table {idx}: Not a job table, headers: {headers}")
                continue

            logger.info(f"Found job table {idx} with {len(rows) - 1} potential job rows")

            for row_idx, row in enumerate(rows[1:], start=1):
                try:
                    job_data = self._extract_job_from_row(row)
                    if job_data and self._is_valid_job(job_data):
                        jobs.append(job_data)
                        logger.debug(f"Valid job: {job_data['title']}")
                    elif job_data:
                        logger.debug(f"Filtered out: {job_data.get('title')}")
                except Exception as e:
                    logger.debug(f"Error extracting row {row_idx}: {e}")

        return jobs

    def _is_valid_job(self, job_data: dict) -> bool:
        """Return True only for real job postings (not nav/promo entries)."""
        title = job_data.get('title', '').lower()
        url   = job_data.get('details_url', '').lower()

        invalid_keywords = [
            'download', 'mobile app', 'sarkari result',
            'latest notifications', 'click here', 'play.google.com',
        ]
        if any(kw in title for kw in invalid_keywords):
            return False

        if '/articles/' not in url and '/online-form/' not in url:
            return False

        org = job_data.get('organization', '')
        if not org or len(org) < 3:
            return False

        if org.lower() in ['eligibility', 'notification', 'result']:
            return False

        return True

    def _extract_job_from_row(self, row) -> Optional[dict]:
        """Extract one job dict from a <tr>. Category is left to the LLM."""
        cells = row.find_all('td')
        if len(cells) < 6:
            return None

        more_info_cell = cells[-1]
        details_link = more_info_cell.find('a')
        if not details_link:
            return None

        details_url = details_link.get('href', '').strip()
        if not details_url:
            return None

        if not details_url.startswith('http'):
            details_url = urljoin(self.BASE_URL, details_url)

        # Columns: Post Date (ignored) | Recruitment Board | Exam/Post Name |
        #          Qualification | Advt No | Last Date | More Info
        recruitment_board = cells[1].get_text(strip=True)
        exam_post_name   = cells[2].get_text(strip=True)
        qualification    = cells[3].get_text(strip=True)

        advt_no   = cells[4].get_text(strip=True) if len(cells) > 4 else ''
        last_date = cells[5].get_text(strip=True) if len(cells) > 5 else ''

        return {
            'title':        exam_post_name,
            'organization': recruitment_board,
            'qualification': qualification,
            'last_date':    last_date,
            'advt_no':      advt_no,
            'details_url':  details_url,
            # category intentionally omitted — let the LLM decide
            'source':       'freejobalert',
        }

    # ------------------------------------------------------------------
    # Detail-page fetching
    # ------------------------------------------------------------------

    def get_job_details(
        self,
        details_url: str,
        job_listing: dict,
    ) -> Optional[dict]:
        """
        Fetch full job details via the smart processor (PDF → HTML fallback).

        Returns a dict with all job fields + blog content, or None on failure.
        """
        try:
            logger.info(f"Fetching job details from: {details_url}")
            response = self.session.get(details_url, timeout=30)
            response.raise_for_status()

            details = self.processor.process_job(
                job_listing, response.text, details_url
            )

            time.sleep(Config.REQUEST_DELAY)
            return details

        except requests.RequestException as e:
            logger.error(f"Error fetching job details from {details_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing job details: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    # ------------------------------------------------------------------
    # PDF download helper (used by main.py for GDrive upload flow)
    # ------------------------------------------------------------------

    def download_pdf(self, pdf_url: str, output_path: str) -> bool:
        """Download a PDF to a local path. Returns True on success."""
        try:
            logger.info(f"Downloading PDF from: {pdf_url}")
            response = self.session.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"PDF downloaded to: {output_path}")
            return True

        except requests.RequestException as e:
            logger.error(f"Error downloading PDF: {e}")
            return False
        except Exception as e:
            logger.error(f"Error saving PDF: {e}")
            return False
