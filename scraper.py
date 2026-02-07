"""Web scraper for FreeJobAlert.com using robust CSS-only parsing.

NO LLM required - all extraction done with CSS selectors and regex.
Properly extracts vacancies without confusing with year.
"""

import logging
import time
import re
from typing import List, Optional, Dict
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config
from robust_parser import RobustJobParser

logger = logging.getLogger(__name__)

class FreeJobAlertScraper:
    """Scraper for FreeJobAlert.com job listings."""
    
    BASE_URL = "https://www.freejobalert.com"
    
    def __init__(self):
        """Initialize the scraper with session and parser."""
        self.session = requests.Session()
        
        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set headers to mimic a browser
        self.session.headers.update({
            'User-Agent': Config.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Initialize robust parser (no LLM)
        self.parser = RobustJobParser()
        logger.info("[OK] Using robust CSS-only parser (no LLM required)")
    
    def scrape_category(
        self,
        category: str,
        max_pages: int = None
    ) -> List[dict]:
        """
        Scrape jobs from a specific category.
        
        Args:
            category: Category slug (e.g., 'latest-notifications')
            max_pages: Maximum number of pages to scrape (None = all)
        
        Returns:
            List of job dictionaries
        """
        jobs = []
        page = 1
        
        logger.info(f"Starting scrape for category: {category}")
        
        while True:
            if max_pages and page > max_pages:
                break
            
            # Construct page URL
            if page == 1:
                url = f"{self.BASE_URL}/{category}/"
            else:
                url = f"{self.BASE_URL}/{category}/page/{page}/"
            
            logger.info(f"Scraping {category} page {page}: {url}")
            
            try:
                # Fetch page
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract job rows from tables
                page_jobs = self._extract_jobs_from_tables(soup, category)
                
                if not page_jobs:
                    logger.info(f"No more jobs found on page {page}")
                    break
                
                logger.info(f"Found {len(page_jobs)} jobs on page {page}")
                jobs.extend(page_jobs)
                
                # Rate limiting
                time.sleep(Config.REQUEST_DELAY)
                page += 1
                
            except requests.RequestException as e:
                logger.error(f"Error fetching page {page}: {e}")
                break
        
        logger.info(f"Total jobs scraped from {category}: {len(jobs)}")
        return jobs
    
    def _extract_jobs_from_tables(self, soup: BeautifulSoup, category: str) -> List[dict]:
        """Extract job listings from tables on the page."""
        jobs = []
        
        # Find all tables with job listings
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables on page")
        
        for idx, table in enumerate(tables):
            # Get all rows
            rows = table.find_all('tr')
            
            if len(rows) < 2:  # Need at least header + 1 data row
                continue
            
            # Check if first row is a header row (has th elements)
            first_row = rows[0]
            header_cells = first_row.find_all('th')
            
            if not header_cells:
                # Not a job table if first row doesn't have headers
                continue
            
            # Get header text
            headers = [th.get_text(strip=True).lower() for th in header_cells]
            
            # Verify this is a job table by checking headers
            job_table_keywords = ['post date', 'recruitment', 'exam', 'post name', 'qualification']
            if not any(keyword in ' '.join(headers) for keyword in job_table_keywords):
                logger.debug(f"Table {idx}: Not a job table, headers: {headers}")
                continue
            
            logger.info(f"Found job table {idx} with {len(rows)-1} potential job rows")
            
            # Process data rows (skip first row which is header)
            for row_idx, row in enumerate(rows[1:], start=1):
                try:
                    job_data = self._extract_job_from_row(row, category)
                    if job_data:
                        # Validate that this is a real job, not a navigation element
                        if self._is_valid_job(job_data):
                            jobs.append(job_data)
                            logger.debug(f"Valid job found: {job_data['title']}")
                        else:
                            logger.debug(f"Filtered out non-job entry: {job_data.get('title')}")
                except Exception as e:
                    logger.debug(f"Error extracting job from row {row_idx}: {e}")
                    continue
        
        return jobs
    
    def _is_valid_job(self, job_data: dict) -> bool:
        """Validate if the extracted data is actually a job posting."""
        title = job_data.get('title', '').lower()
        url = job_data.get('details_url', '').lower()
        
        # Filter out navigation/promotional items
        invalid_keywords = [
            'download', 'mobile app', 'sarkari result',
            'latest notifications', 'click here',
            'play.google.com'
        ]
        
        # Check if title contains invalid keywords
        for keyword in invalid_keywords:
            if keyword in title:
                return False
        
        # Check if URL points to actual job article
        if '/articles/' not in url and '/online-form/' not in url:
            return False
        
        # Valid job should have organization name
        org = job_data.get('organization', '')
        if not org or len(org) < 3:
            return False
        
        # Filter out generic organization names
        if org.lower() in ['eligibility', 'notification', 'result']:
            return False
        
        return True
    
    def _extract_job_from_row(self, row, category: str) -> Optional[dict]:
        """Extract job data from a table row."""
        cells = row.find_all('td')
        
        # Need at least 6 cells for a valid job row
        if len(cells) < 6:
            return None
        
        # Extract "More Info" or "Get Details" link from the last cell
        more_info_cell = cells[-1]
        details_link = more_info_cell.find('a')
        
        if not details_link:
            return None
        
        details_url = details_link.get('href', '')
        if not details_url:
            return None
        
        # Make absolute URL
        if not details_url.startswith('http'):
            details_url = urljoin(self.BASE_URL, details_url)
        
        # Extract basic info from table cells
        # Format: Post Date | Recruitment Board | Exam/Post Name | Qualification | Advt No | Last Date | More Info
        post_date = cells[0].get_text(strip=True)
        recruitment_board = cells[1].get_text(strip=True)
        exam_post_name = cells[2].get_text(strip=True)
        qualification = cells[3].get_text(strip=True)
        
        # Handle variable column counts (some tables may have different structures)
        if len(cells) >= 7:
            advt_no = cells[4].get_text(strip=True)
            last_date = cells[5].get_text(strip=True)
        else:
            advt_no = cells[4].get_text(strip=True) if len(cells) > 4 else ''
            last_date = cells[5].get_text(strip=True) if len(cells) > 5 else ''
        
        job_data = {
            'title': exam_post_name,
            'organization': recruitment_board,
            'qualification': qualification,
            'post_date': post_date,
            'last_date': last_date,
            'advt_no': advt_no,
            'details_url': details_url,
            'category': category,
            'source': 'freejobalert'
        }
        
        return job_data
    
    def get_job_details(self, details_url: str) -> Optional[dict]:
        """
        Fetch detailed job information from the job details page.
        Uses robust CSS-only parser (no LLM required).
        
        Args:
            details_url: URL of the job details page
        
        Returns:
            Dictionary with detailed job information
        """
        try:
            logger.info(f"Fetching job details from: {details_url}")
            
            response = self.session.get(details_url, timeout=30)
            response.raise_for_status()
            
            html_content = response.text
            
            # Use robust parser to extract all fields
            details = self.parser.parse_job_details(html_content, details_url)
            
            # Count extracted fields
            field_count = sum(1 for v in details.values() if v and str(v).strip())
            logger.info(f"[OK] Extracted {field_count} non-empty fields")
            
            # Log vacancies if found
            if details.get('vacancies'):
                logger.info(f"  [OK] Vacancies: {details['vacancies']}")
            
            time.sleep(Config.REQUEST_DELAY)
            return details
            
        except requests.RequestException as e:
            logger.error(f"Error fetching job details from {details_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing job details: {e}")
            return None
    
    def download_pdf(self, pdf_url: str, output_path: str) -> bool:
        """
        Download PDF file from URL.
        
        Args:
            pdf_url: URL of the PDF file
            output_path: Local path to save the PDF
        
        Returns:
            True if download successful, False otherwise
        """
        try:
            logger.info(f"Downloading PDF from: {pdf_url}")
            
            response = self.session.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Write to file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"PDF downloaded successfully to: {output_path}")
            return True
            
        except requests.RequestException as e:
            logger.error(f"Error downloading PDF: {e}")
            return False
        except Exception as e:
            logger.error(f"Error saving PDF: {e}")
            return False
