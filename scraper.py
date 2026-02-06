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
    
    def scrape_category(self, category: str, max_pages: int = Config.MAX_PAGES_PER_CATEGORY) -> List[Dict]:
        """Scrape jobs from a specific category."""
        jobs = []
        
        for page in range(1, max_pages + 1):
            if page == 1:
                url = f"{self.base_url}/{category}/"
            else:
                url = f"{self.base_url}/{category}/page/{page}/"
            
            logger.info(f"Scraping {category} page {page}: {url}")
            html = self.get_page(url)
            
            if not html:
                logger.warning(f"No content received for {url}")
                break
            
            page_jobs = self.parse_job_listings(html, category)
            
            if not page_jobs:
                logger.info(f"No more jobs found on page {page} of {category}")
                break
            
            jobs.extend(page_jobs)
            logger.info(f"Found {len(page_jobs)} jobs on page {page}")
            
            # Respectful delay between requests
            time.sleep(Config.REQUEST_DELAY)
        
        logger.info(f"Total jobs scraped from {category}: {len(jobs)}")
        return jobs
    
    def parse_job_listings(self, html: str, category: str) -> List[Dict]:
        """Parse job listings from HTML."""
        soup = BeautifulSoup(html, 'lxml')
        jobs = []
        
        # Find job listing containers - adjust selectors based on actual site structure
        # This is a generic approach - you may need to inspect and adjust
        job_cards = soup.find_all(['article', 'div'], class_=re.compile(r'post|job|item|card'))
        
        for card in job_cards:
            try:
                job_data = self.extract_job_data(card, category)
                if job_data:
                    jobs.append(job_data)
            except Exception as e:
                logger.error(f"Error parsing job card: {e}")
                continue
        
        return jobs
    
    def extract_job_data(self, card, category: str) -> Optional[Dict]:
        """Extract job data from a job card element."""
        try:
            # Find job title and URL
            title_elem = card.find(['h2', 'h3', 'h4', 'a'], class_=re.compile(r'title|heading'))
            if not title_elem:
                title_elem = card.find('a')
            
            if not title_elem:
                return None
            
            # Get the link
            link = title_elem.get('href') if title_elem.name == 'a' else None
            if not link:
                link_elem = card.find('a')
                link = link_elem.get('href') if link_elem else None
            
            if not link:
                return None
            
            # Make absolute URL
            job_url = urljoin(self.base_url, link)
            
            # Get title text
            title = title_elem.get_text(strip=True)
            
            # Try to extract additional details
            details_text = card.get_text()
            
            # Extract organization (common patterns)
            organization = self.extract_organization(details_text)
            
            # Extract dates
            post_date = self.extract_date(details_text, 'post')
            last_date = self.extract_date(details_text, 'last')
            
            # Extract vacancies
            vacancies = self.extract_vacancies(details_text)
            
            # Find PDF link
            pdf_url = self.find_pdf_link(card)
            
            job_data = {
                'title': title,
                'organization': organization,
                'post_date': post_date,
                'last_date': last_date,
                'vacancies': vacancies,
                'job_url': job_url,
                'pdf_url': pdf_url,
                'category': category,
            }
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error extracting job data: {e}")
            return None
    
    def extract_organization(self, text: str) -> Optional[str]:
        """Extract organization name from text."""
        # Common patterns for organization names
        patterns = [
            r'(?:in|by|at)\s+([A-Z][A-Za-z\s&]+(?:Ltd|Limited|Corporation|Corp|Inc|Bank|Railway|Police|Commission))',
            r'([A-Z][A-Za-z\s&]+(?:Ltd|Limited|Corporation|Corp|Inc|Bank|Railway|Police|Commission))'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return None
    
    def extract_date(self, text: str, date_type: str = 'post') -> Optional[str]:
        """Extract dates from text."""
        # Common date patterns
        date_patterns = [
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})',
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Return first or last date based on type
                return matches[0] if date_type == 'post' else matches[-1]
        
        return None
    
    def extract_vacancies(self, text: str) -> Optional[int]:
        """Extract number of vacancies from text."""
        patterns = [
            r'(\d+)\s+(?:vacancies|vacancy|posts|post|positions|opening)',
            r'(?:vacancies|vacancy|posts|post|positions|opening)[:\s]+(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        
        return None
    
    def find_pdf_link(self, card) -> Optional[str]:
        """Find PDF download link in the card."""
        # Look for PDF links
        pdf_links = card.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
        
        if pdf_links:
            return urljoin(self.base_url, pdf_links[0].get('href'))
        
        # Look for notification/advertisement links
        notification_links = card.find_all('a', string=re.compile(r'notification|advertisement|download', re.IGNORECASE))
        
        if notification_links:
            href = notification_links[0].get('href')
            if href:
                return urljoin(self.base_url, href)
        
        return None
    
    def download_pdf(self, pdf_url: str, job_title: str) -> Optional[str]:
        """Download PDF file."""
        if not pdf_url:
            return None
        
        try:
            # Create safe filename
            safe_title = re.sub(r'[^\w\s-]', '', job_title)[:50]
            filename = f"{safe_title}_{int(time.time())}.pdf"
            filepath = os.path.join(Config.PDF_DOWNLOAD_DIR, filename)
            
            logger.info(f"Downloading PDF from {pdf_url}")
            response = self.session.get(pdf_url, timeout=Config.REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"PDF saved to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to download PDF from {pdf_url}: {e}")
            return None
    
    def scrape_all_categories(self, categories: List[str] = None, max_pages: int = Config.MAX_PAGES_PER_CATEGORY) -> List[Dict]:
        """Scrape all specified categories."""
        if categories is None:
            categories = Config.CATEGORIES
        
        all_jobs = []
        
        for category in categories:
            logger.info(f"Starting scrape for category: {category}")
            jobs = self.scrape_category(category, max_pages)
            all_jobs.extend(jobs)
            
            # Delay between categories
            time.sleep(Config.REQUEST_DELAY * 2)
        
        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        return all_jobs