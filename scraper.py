"""Web scraper for FreeJobAlert.com."""

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
                'full_description': '',
                'official_notification_pdf': '',
                'official_website': '',
                'application_link': '',
                'important_dates': {},
                'vacancy_details': {},
                'salary': '',
                'age_limit': '',
                'application_fee': '',
                'selection_process': '',
                'how_to_apply': ''
            }
            
            # Extract title from h1 or title tag
            title_tag = soup.find('h1', class_='entry-title')
            if title_tag:
                details['title'] = title_tag.get_text(strip=True)
            
            # Find the main content area
            content_div = soup.find('div', class_='entry-content') or soup.find('article')
            
            if content_div:
                # Extract all links from content
                links = content_div.find_all('a', href=True)
                
                for link in links:
                    link_text = link.get_text(strip=True).lower()
                    href = link.get('href', '')
                    
                    # Skip empty or anchor links
                    if not href or href.startswith('#'):
                        continue
                    
                    # Make absolute URL
                    absolute_url = urljoin(self.BASE_URL, href)
                    
                    # Identify link type based on text and URL
                    if 'notification' in link_text and ('pdf' in link_text or href.lower().endswith('.pdf')):
                        details['official_notification_pdf'] = absolute_url
                    elif href.lower().endswith('.pdf') and 'click here' in link_text:
                        if not details['official_notification_pdf']:
                            details['official_notification_pdf'] = absolute_url
                    elif 'official website' in link_text or 'click here' in link_text:
                        if 'apply' not in link_text and not href.lower().endswith('.pdf'):
                            details['official_website'] = absolute_url
                    elif 'apply online' in link_text or 'application' in link_text:
                        details['application_link'] = absolute_url
                
                # Extract structured data from tables
                tables = content_div.find_all('table')
                for table in tables:
                    table_data = self._extract_table_data(table)
                    
                    # Identify table purpose by headers or content
                    if 'vacancy' in str(table).lower() or 'posts' in str(table).lower():
                        details['vacancy_details'].update(table_data)
                    elif 'date' in str(table).lower():
                        details['important_dates'].update(table_data)
                    elif 'salary' in str(table).lower() or 'stipend' in str(table).lower():
                        for k, v in table_data.items():
                            if 'salary' in k.lower() or 'stipend' in k.lower():
                                details['salary'] = v
                    
                    # Extract age, fee from any table
                    for key, value in table_data.items():
                        key_lower = key.lower()
                        if 'age' in key_lower and not details['age_limit']:
                            details['age_limit'] = value
                        elif 'fee' in key_lower and not details['application_fee']:
                            details['application_fee'] = value
                
                # Extract section-based content
                headings = content_div.find_all(['h2', 'h3', 'h4'])
                for heading in headings:
                    heading_text = heading.get_text(strip=True).lower()
                    
                    # Get content after heading until next heading
                    content_parts = []
                    for sibling in heading.find_next_siblings():
                        if sibling.name in ['h2', 'h3', 'h4']:
                            break
                        if sibling.name in ['p', 'ul', 'ol', 'table']:
                            content_parts.append(sibling.get_text(separator=' ', strip=True))
                    
                    section_content = ' '.join(content_parts)
                    
                    if 'selection' in heading_text or 'exam pattern' in heading_text:
                        details['selection_process'] = section_content[:500]
                    elif 'how to apply' in heading_text or 'application procedure' in heading_text:
                        details['how_to_apply'] = section_content[:500]
                    elif 'important date' in heading_text:
                        # Try to extract dates from this section
                        self._extract_dates_from_text(section_content, details['important_dates'])
                
                # Get full description (first 2000 chars)
                for script in content_div(["script", "style", "iframe"]):
                    script.decompose()
                details['full_description'] = content_div.get_text(separator='\n', strip=True)[:2000]
            
            time.sleep(Config.REQUEST_DELAY)
            return details
            
        except requests.RequestException as e:
            logger.error(f"Error fetching job details from {details_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing job details: {e}")
            return None
    
    def _extract_table_data(self, table) -> Dict[str, str]:
        """Extract key-value pairs from a table."""
        data = {}
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key and value:
                    data[key] = value
            elif len(cells) > 2:
                # Multi-column table - use first cell as key, rest as value
                key = cells[0].get_text(strip=True)
                value = ' | '.join([c.get_text(strip=True) for c in cells[1:]])
                if key and value:
                    data[key] = value
        
        return data
    
    def _extract_dates_from_text(self, text: str, dates_dict: dict):
        """Extract dates from text using patterns."""
        # Common date patterns
        date_patterns = [
            (r'last date[:\s]+([\d\-/]+)', 'Last Date'),
            (r'start date[:\s]+([\d\-/]+)', 'Start Date'),
            (r'closing date[:\s]+([\d\-/]+)', 'Closing Date'),
            (r'exam date[:\s]+([\d\-/]+)', 'Exam Date'),
        ]
        
        for pattern, key in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                dates_dict[key] = match.group(1)
    
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
                # Try anyway - sometimes PDFs are served with wrong content-type
            
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
