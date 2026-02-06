"""Web scraper for FreeJobAlert.com."""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
import os

from config import Config

logger = logging.getLogger(__name__)

class FreeJobAlertScraper:
    """Scraper for FreeJobAlert.com job listings."""
    
    def __init__(self):
        self.base_url = Config.BASE_URL
        self.headers = {
            'User-Agent': Config.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Create PDF download directory
        os.makedirs(Config.PDF_DOWNLOAD_DIR, exist_ok=True)
    
    def get_page(self, url: str, retries: int = Config.MAX_RETRIES) -> Optional[str]:
        """Fetch a web page with retry logic."""
        for attempt in range(retries):
            try:
                response = self.session.get(
                    url,
                    timeout=Config.REQUEST_TIMEOUT
                )
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(Config.REQUEST_DELAY * (attempt + 1))
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
    
    def scrape_listing_page(self, url: str) -> List[Dict]:
        """Scrape jobs from a listing page with tables."""
        logger.info(f"Scraping listing page: {url}")
        html = self.get_page(url)
        
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'lxml')
        jobs = []
        
        # Find all tables containing job listings
        tables = soup.find_all('table')
        
        for table in tables:
            # Check if this is a job listing table (has specific headers)
            headers = table.find_all('th')
            if not headers:
                continue
            
            header_text = ' '.join([h.get_text(strip=True) for h in headers]).lower()
            
            # Look for tables with job-related headers
            if 'post date' in header_text or 'recruitment' in header_text or 'last date' in header_text:
                jobs.extend(self.parse_job_table(table))
        
        logger.info(f"Found {len(jobs)} jobs on page")
        return jobs
    
    def parse_job_table(self, table) -> List[Dict]:
        """Parse individual job table."""
        jobs = []
        rows = table.find_all('tr')
        
        # Skip header row
        for row in rows[1:]:
            cells = row.find_all('td')
            
            if len(cells) < 5:  # Need at least basic info
                continue
            
            try:
                job_data = self.extract_from_table_row(cells)
                if job_data:
                    jobs.append(job_data)
            except Exception as e:
                logger.error(f"Error parsing table row: {e}")
                continue
        
        return jobs
    
    def extract_from_table_row(self, cells) -> Optional[Dict]:
        """Extract job data from table row cells."""
        try:
            # Typical structure: Post Date | Recruitment Board | Exam/Post Name | Qualification | Advt No | Last Date | More Information
            
            post_date = cells[0].get_text(strip=True) if len(cells) > 0 else None
            organization = cells[1].get_text(strip=True) if len(cells) > 1 else None
            title = cells[2].get_text(strip=True) if len(cells) > 2 else None
            qualification = cells[3].get_text(strip=True) if len(cells) > 3 else None
            advt_no = cells[4].get_text(strip=True) if len(cells) > 4 else None
            last_date = cells[5].get_text(strip=True) if len(cells) > 5 else None
            
            # Find "Get Details" link
            detail_link = None
            if len(cells) > 6:
                link_elem = cells[6].find('a')
                if link_elem:
                    detail_link = link_elem.get('href')
            
            # If no detail link found in last cell, search all cells
            if not detail_link:
                for cell in cells:
                    link = cell.find('a')
                    if link and link.get('href'):
                        detail_link = link.get('href')
                        break
            
            if not detail_link or not title:
                return None
            
            # Make absolute URL
            job_url = urljoin(self.base_url, detail_link)
            
            job_data = {
                'title': title,
                'organization': organization,
                'post_date': self.parse_date(post_date),
                'last_date': self.parse_date(last_date),
                'qualification': qualification,
                'advt_no': advt_no,
                'job_url': job_url,
                'pdf_url': None,  # Will be extracted from detail page
                'official_website': None,  # Will be extracted from detail page
            }
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error extracting from table row: {e}")
            return None
    
    def scrape_detail_page(self, job_data: Dict) -> Dict:
        """Scrape additional details from job detail page."""
        logger.info(f"Scraping details for: {job_data['title']}")
        
        html = self.get_page(job_data['job_url'])
        if not html:
            return job_data
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Extract PDF notification link
        pdf_link = self.find_pdf_notification(soup)
        if pdf_link:
            job_data['pdf_url'] = urljoin(self.base_url, pdf_link)
            logger.info(f"Found PDF: {job_data['pdf_url']}")
        
        # Extract official website link
        official_site = self.find_official_website(soup)
        if official_site:
            job_data['official_website'] = official_site
            logger.info(f"Found official website: {official_site}")
        
        # Extract additional details from the page
        job_data.update(self.extract_additional_details(soup))
        
        return job_data
    
    def find_pdf_notification(self, soup) -> Optional[str]:
        """Find Official Notification PDF link."""
        # Look for links with text like "Official Notification", "Notification PDF", "Click here" near PDF
        patterns = [
            r'official\s+notification',
            r'notification\s+pdf',
            r'download\s+notification',
            r'advertisement',
        ]
        
        # Find all links
        links = soup.find_all('a', href=True)
        
        for link in links:
            link_text = link.get_text(strip=True).lower()
            href = link.get('href', '')
            
            # Check if link text matches patterns
            for pattern in patterns:
                if re.search(pattern, link_text, re.IGNORECASE):
                    # Check if it's a PDF link or leads to PDF
                    if '.pdf' in href.lower() or 'pdf' in link_text:
                        return href
            
            # Also check for direct PDF links
            if href.endswith('.pdf'):
                return href
        
        return None
    
    def find_official_website(self, soup) -> Optional[str]:
        """Find Official Website link."""
        patterns = [
            r'official\s+website',
            r'apply\s+online',
            r'registration',
        ]
        
        links = soup.find_all('a', href=True)
        
        for link in links:
            link_text = link.get_text(strip=True).lower()
            href = link.get('href', '')
            
            for pattern in patterns:
                if re.search(pattern, link_text, re.IGNORECASE):
                    # Exclude PDF links
                    if not href.endswith('.pdf'):
                        return href
        
        return None
    
    def extract_additional_details(self, soup) -> Dict:
        """Extract additional job details from detail page."""
        details = {}
        
        # Extract vacancies
        text = soup.get_text()
        vacancies_match = re.search(r'(\d+)\s+(?:vacancies|posts|vacancy|post)', text, re.IGNORECASE)
        if vacancies_match:
            try:
                details['vacancies'] = int(vacancies_match.group(1))
            except ValueError:
                pass
        
        # Extract location (common patterns)
        location_match = re.search(r'location[:\s]+([A-Za-z\s,]+?)(?:\n|\.|,)', text, re.IGNORECASE)
        if location_match:
            details['location'] = location_match.group(1).strip()
        
        return details
    
    def parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to standard format."""
        if not date_str or date_str.strip() in ['', '–', '-']:
            return None
        
        try:
            # Try DD/MM/YYYY format
            if re.match(r'\d{2}/\d{2}/\d{4}', date_str):
                return date_str
            
            # Try DD-MM-YYYY format
            if re.match(r'\d{2}-\d{2}-\d{4}', date_str):
                return date_str.replace('-', '/')
            
            return date_str
        except:
            return None
    
    def download_pdf(self, pdf_url: str, job_title: str) -> Optional[str]:
        """Download PDF file."""
        if not pdf_url:
            return None
        
        try:
            # Create safe filename
            safe_title = re.sub(r'[^\w\s-]', '', job_title)[:50]
            safe_title = re.sub(r'[-\s]+', '_', safe_title)
            filename = f"{safe_title}_{int(time.time())}.pdf"
            filepath = os.path.join(Config.PDF_DOWNLOAD_DIR, filename)
            
            logger.info(f"Downloading PDF from {pdf_url}")
            response = self.session.get(pdf_url, timeout=Config.REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()
            
            # Check if response is actually a PDF
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and not pdf_url.endswith('.pdf'):
                logger.warning(f"URL doesn't seem to be a PDF: {pdf_url}")
                return None
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"PDF saved to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to download PDF from {pdf_url}: {e}")
            return None
    
    def scrape_category(self, category: str, max_pages: int = 1) -> List[Dict]:
        """Scrape jobs from the view-all page of a category."""
        # The view-all URL structure
        url = f"{self.base_url}/view-all/"
        
        logger.info(f"Scraping view-all page: {url}")
        
        # Get all jobs from the view-all page
        jobs = self.scrape_listing_page(url)
        
        # Now fetch details for each job
        detailed_jobs = []
        for i, job in enumerate(jobs[:50]):  # Limit to first 50 jobs for testing
            try:
                logger.info(f"Processing job {i+1}/{min(len(jobs), 50)}: {job['title']}")
                detailed_job = self.scrape_detail_page(job)
                detailed_job['category'] = category
                detailed_jobs.append(detailed_job)
                
                # Respectful delay
                time.sleep(Config.REQUEST_DELAY)
                
            except Exception as e:
                logger.error(f"Error processing job {job.get('title')}: {e}")
                continue
        
        logger.info(f"Scraped {len(detailed_jobs)} jobs with details")
        return detailed_jobs
    
    def scrape_all_categories(self, categories: List[str] = None, max_pages: int = 1) -> List[Dict]:
        """Scrape the main view-all page."""
        logger.info("Starting scrape of FreeJobAlert view-all page")
        
        # FreeJobAlert has a main "view-all" page with all recent jobs
        all_jobs = self.scrape_category('all', max_pages)
        
        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        return all_jobs