"""Web scraper for FreeJobAlert.com."""

import logging
import time
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config

logger = logging.getLogger(__name__)

class FreeJobAlertScraper:
    """Scraper for FreeJobAlert.com job listings."""
    
    BASE_URL = "https://www.freejobalert.com"
    
    def __init__(self):
        """Initialize the scraper with session and retry logic."""
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
        
        for table in tables:
            # Skip if table doesn't have proper headers
            thead = table.find('thead')
            if not thead:
                continue
            
            # Get table body
            tbody = table.find('tbody')
            if not tbody:
                continue
            
            # Extract rows
            rows = tbody.find_all('tr')
            
            for row in rows:
                try:
                    job_data = self._extract_job_from_row(row, category)
                    if job_data:
                        jobs.append(job_data)
                except Exception as e:
                    logger.warning(f"Error extracting job from row: {e}")
                    continue
        
        return jobs
    
    def _extract_job_from_row(self, row, category: str) -> Optional[dict]:
        """Extract job data from a table row."""
        cells = row.find_all('td')
        
        if len(cells) < 7:
            return None
        
        # Extract "Get Details" link
        more_info_cell = cells[-1]
        details_link = more_info_cell.find('a')
        
        if not details_link or 'Get Details' not in details_link.get_text():
            return None
        
        details_url = details_link.get('href', '')
        if not details_url:
            return None
        
        # Make absolute URL
        if not details_url.startswith('http'):
            details_url = urljoin(self.BASE_URL, details_url)
        
        # Extract basic info from table
        post_date = cells[0].get_text(strip=True)
        recruitment_board = cells[1].get_text(strip=True)
        exam_post_name = cells[2].get_text(strip=True)
        qualification = cells[3].get_text(strip=True)
        advt_no = cells[4].get_text(strip=True)
        last_date = cells[5].get_text(strip=True)
        
        return {
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
    
    def get_job_details(self, details_url: str) -> Optional[dict]:
        """
        Fetch detailed job information from the job details page.
        
        Args:
            details_url: URL of the job details page
        
        Returns:
            Dictionary with detailed job information
        """
        try:
            logger.info(f"Fetching job details from: {details_url}")
            
            response = self.session.get(details_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract details
            details = {
                'job_url': details_url,
                'description': '',
                'official_notification_pdf': '',
                'official_website': '',
                'important_dates': {},
                'application_fee': '',
                'age_limit': '',
                'vacancy_details': ''
            }
            
            # Extract PDF link - look for "Official Notification PDF" link
            pdf_links = soup.find_all('a', href=True)
            for link in pdf_links:
                link_text = link.get_text(strip=True).lower()
                href = link.get('href', '')
                
                if 'notification' in link_text and 'pdf' in link_text:
                    if href and not href.startswith('#'):
                        details['official_notification_pdf'] = urljoin(self.BASE_URL, href)
                        break
                elif 'click here' in link_text and href.endswith('.pdf'):
                    details['official_notification_pdf'] = urljoin(self.BASE_URL, href)
                    break
            
            # Extract official website link
            for link in pdf_links:
                link_text = link.get_text(strip=True).lower()
                href = link.get('href', '')
                
                if 'official website' in link_text or 'apply online' in link_text:
                    if href and not href.startswith('#') and not href.endswith('.pdf'):
                        details['official_website'] = urljoin(self.BASE_URL, href)
                        break
            
            # Extract job description
            content_div = soup.find('div', class_='entry-content')
            if content_div:
                # Get text content, skip scripts and styles
                for script in content_div(["script", "style"]):
                    script.decompose()
                details['description'] = content_div.get_text(separator='\n', strip=True)[:2000]
            
            # Extract structured data from tables
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        
                        if 'age' in key:
                            details['age_limit'] = value
                        elif 'fee' in key:
                            details['application_fee'] = value
                        elif 'vacancy' in key or 'post' in key:
                            details['vacancy_details'] = value
                        elif 'date' in key:
                            details['important_dates'][cells[0].get_text(strip=True)] = value
            
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
            
            # Check if content is actually a PDF
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and not pdf_url.lower().endswith('.pdf'):
                logger.warning(f"URL does not appear to be a PDF: {pdf_url}")
                return False
            
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
