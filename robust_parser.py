"""Robust CSS-only parser for FreeJobAlert - NO LLM dependency.

Extracts all fields using CSS selectors, regex patterns, and HTML parsing.
Special focus on vacancies field to avoid extracting year (2026).

CRITICAL: Filters out ALL FreeJobAlert links.
CRITICAL: job_url must be the Apply Online link, NOT FreeJobAlert URL.
"""

import logging
import re
from typing import Dict, Optional, List
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


class RobustJobParser:
    """Robust parser for job details without LLM."""
    
    BASE_URL = "https://www.freejobalert.com"
    
    # Patterns for extracting vacancies
    VACANCY_PATTERNS = [
        # "Total Posts: 150" or "Total Vacancies: 80"
        r'total\s+(?:posts?|vacanc(?:y|ies))\s*:?\s*(\d+)',
        # "150 Posts" or "80 Vacancies"
        r'(\d+)\s+(?:posts?|vacanc(?:y|ies))',
        # "Posts: 40" or "Vacancies: 20"
        r'(?:posts?|vacanc(?:y|ies))\s*:?\s*(\d+)',
        # "Apply for 150 Posts"
        r'apply\s+(?:for\s+)?(\d+)\s+posts?',
        # "150 positions" or "80 openings"
        r'(\d+)\s+(?:positions?|openings?)',
    ]
    
    # Date patterns (DD-MM-YYYY, DD/MM/YYYY, etc.)
    DATE_PATTERNS = [
        r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',  # DD-MM-YYYY or DD/MM/YYYY
        r'(\d{1,2}\s+\w+\s+\d{4})',  # DD Month YYYY
    ]
    
    # Common Indian states and major cities for location detection
    LOCATION_KEYWORDS = [
        # States
        'andhra pradesh', 'arunachal pradesh', 'assam', 'bihar', 'chhattisgarh',
        'goa', 'gujarat', 'haryana', 'himachal pradesh', 'jharkhand', 'karnataka',
        'kerala', 'madhya pradesh', 'maharashtra', 'manipur', 'meghalaya', 'mizoram',
        'nagaland', 'odisha', 'punjab', 'rajasthan', 'sikkim', 'tamil nadu',
        'telangana', 'tripura', 'uttar pradesh', 'uttarakhand', 'west bengal',
        # UTs
        'delhi', 'jammu and kashmir', 'ladakh', 'chandigarh', 'puducherry',
        'lakshadweep', 'andaman and nicobar',
        # Major cities
        'mumbai', 'bangalore', 'bengaluru', 'hyderabad', 'chennai', 'kolkata',
        'pune', 'ahmedabad', 'surat', 'jaipur', 'lucknow', 'kanpur', 'nagpur',
        'indore', 'thane', 'bhopal', 'visakhapatnam', 'pimpri-chinchwad', 'patna',
        'vadodara', 'ghaziabad', 'ludhiana', 'agra', 'nashik', 'faridabad',
        'meerut', 'rajkot', 'varanasi', 'srinagar', 'aurangabad', 'dhanbad',
        'amritsar', 'navi mumbai', 'allahabad', 'ranchi', 'howrah', 'coimbatore',
        'jabalpur', 'gwalior', 'vijayawada', 'jodhpur', 'madurai', 'raipur',
        'kota', 'chandigarh', 'guwahati', 'dehradun', 'noida', 'greater noida',
        # Multi-location patterns
        'all india', 'pan india', 'across india', 'various locations', 'multiple locations'
    ]
    
    def __init__(self):
        """Initialize parser."""
        pass
    
    def _is_freejobalert_link(self, url: str) -> bool:
        """CRITICAL: Check if URL is from FreeJobAlert domain.
        
        Returns True if link should be BLOCKED.
        """
        if not url:
            return False
        
        url_lower = url.lower()
        blocked_domains = [
            'freejobalert.com',
            'www.freejobalert.com',
        ]
        
        for domain in blocked_domains:
            if domain in url_lower:
                logger.info(f"🚫 BLOCKED FreeJobAlert link: {url[:70]}...")
                return True
        
        return False
    
    def parse_job_details(self, html: str, details_url: str) -> Dict:
        """Parse job details from HTML using CSS selectors only.
        
        Args:
            html: HTML content of job page
            details_url: URL of the job page (FreeJobAlert source)
            
        Returns:
            Dictionary with extracted job data (NO FreeJobAlert links)
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Initialize result
        # CRITICAL: job_url will be set to "Apply Online" link, NOT details_url
        details = {
            'job_url': None,  # Will be set to Apply Online link (or NULL)
            'freejobalert_url': details_url,  # FreeJobAlert source page (for tracking)
            'vacancies': None,
            'title': '',
            'organization': '',
            'post_date': '',
            'last_date': '',
            'qualification': '',
            'location': '',
            'salary': '',
            'age_limit': '',
            'advt_no': '',
            'application_fee': '',
            'selection_process': '',
            'how_to_apply': '',
            'official_website': '',  # ONLY official website (no FreeJobAlert)
            'pdf_url': '',  # ONLY PDF URL (no FreeJobAlert)
            'official_notification_pdf': '',
            'important_dates': {},
            'vacancy_details': {},
            'full_description': ''
        }
        
        # Extract title
        title_tag = soup.find('h1', class_='entry-title')
        if title_tag:
            details['title'] = title_tag.get_text(strip=True)
        
        # Find main content
        content = soup.find('div', class_='entry-content') or soup.find('article')
        if not content:
            logger.warning("No content div found")
            return details
        
        # Get all text content for pattern matching
        full_text = content.get_text(separator=' ', strip=True)
        
        # Extract vacancies (CRITICAL - multiple methods)
        details['vacancies'] = self._extract_vacancies(details['title'], full_text, content)
        
        # Extract organization from title or content
        details['organization'] = self._extract_organization(details['title'], full_text)
        
        # Extract dates
        dates = self._extract_dates(full_text, content)
        if dates.get('post_date'):
            details['post_date'] = dates['post_date']
        if dates.get('last_date'):
            details['last_date'] = dates['last_date']
        details['important_dates'] = dates.get('all_dates', {})
        
        # Extract URLs (PDF, Apply Online, official website) - WITH STRICT FILTERING
        urls = self._extract_urls(content)
        details.update(urls)
        
        # Extract from tables
        tables = content.find_all('table')
        for table in tables:
            table_data = self._extract_table_data(table)
            
            # Try to identify table type and extract relevant data
            table_text = str(table).lower()
            
            if 'vacancy' in table_text or 'post' in table_text:
                # Vacancy details table
                details['vacancy_details'].update(table_data)
                # Also try to get total from table
                if not details['vacancies']:
                    details['vacancies'] = self._get_total_from_table(table_data)
            
            elif 'date' in table_text:
                # Dates table
                details['important_dates'].update(table_data)
            
            # Extract specific fields from any table
            for key, value in table_data.items():
                key_lower = key.lower()
                
                if 'organization' in key_lower or 'department' in key_lower or 'board' in key_lower:
                    if not details['organization']:
                        details['organization'] = value
                
                elif 'qualification' in key_lower or 'eligibility' in key_lower:
                    if not details['qualification']:
                        details['qualification'] = value
                
                elif 'salary' in key_lower or 'pay' in key_lower or 'stipend' in key_lower:
                    if not details['salary']:
                        details['salary'] = value
                
                elif 'age' in key_lower:
                    if not details['age_limit']:
                        details['age_limit'] = value
                
                elif 'fee' in key_lower:
                    if not details['application_fee']:
                        details['application_fee'] = value
                
                elif 'location' in key_lower or 'place' in key_lower or 'posting' in key_lower:
                    if not details['location']:
                        details['location'] = value
                
                elif 'advt' in key_lower or 'advertisement' in key_lower:
                    if not details['advt_no']:
                        details['advt_no'] = value
                
                elif 'last date' in key_lower or 'closing date' in key_lower:
                    if not details['last_date']:
                        details['last_date'] = value
                
                elif 'post date' in key_lower or 'publish' in key_lower:
                    if not details['post_date']:
                        details['post_date'] = value
        
        # Extract from headings and sections
        headings = content.find_all(['h2', 'h3', 'h4', 'strong'])
        for heading in headings:
            heading_text = heading.get_text(strip=True).lower()
            
            # Get content after this heading
            section_content = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h2', 'h3', 'h4']:
                    break
                if sibling.name in ['p', 'ul', 'ol', 'div']:
                    section_content.append(sibling.get_text(separator=' ', strip=True))
            
            section_text = ' '.join(section_content)
            
            if 'selection' in heading_text or 'exam pattern' in heading_text:
                details['selection_process'] = section_text[:500]
            
            elif 'how to apply' in heading_text:
                details['how_to_apply'] = section_text[:500]
            
            elif 'salary' in heading_text and not details['salary']:
                details['salary'] = section_text[:200]
            
            elif 'age limit' in heading_text and not details['age_limit']:
                details['age_limit'] = section_text[:200]
            
            elif 'qualification' in heading_text and not details['qualification']:
                details['qualification'] = section_text[:300]
            
            elif ('location' in heading_text or 'place' in heading_text or 'posting' in heading_text) and not details['location']:
                details['location'] = section_text[:200]
        
        # Extract location using multiple methods if not found yet
        if not details['location']:
            details['location'] = self._extract_location(details['title'], full_text, content)
        
        # Full description (for reference)
        for script in content(["script", "style", "iframe"]):
            script.decompose()
        details['full_description'] = content.get_text(separator='\n', strip=True)[:2000]
        
        # Fallback: Extract organization from title if still missing
        if not details['organization'] and details['title']:
            # Try to get first part before "Recruitment" or "Notification"
            match = re.search(r'^([^\(\-]+?)(?:Recruitment|Notification|Job)', details['title'], re.IGNORECASE)
            if match:
                details['organization'] = match.group(1).strip()
        
        return details
    
    def _extract_location(self, title: str, full_text: str, content: BeautifulSoup) -> str:
        """Extract location using multiple detection methods.
        
        Methods:
        1. Pattern matching ("Location:", "Job Location:", etc.)
        2. Known state/city names in text
        3. Organization name patterns (e.g., "Delhi Police", "Punjab Government")
        """
        # Method 1: Direct location patterns
        location_patterns = [
            r'(?:job\s+)?location\s*:?\s*([A-Za-z\s,/&\-]+?)(?:\.|\n|$)',
            r'place\s+of\s+posting\s*:?\s*([A-Za-z\s,/&\-]+?)(?:\.|\n|$)',
            r'work\s+location\s*:?\s*([A-Za-z\s,/&\-]+?)(?:\.|\n|$)',
            r'posting\s+location\s*:?\s*([A-Za-z\s,/&\-]+?)(?:\.|\n|$)',
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Clean up and validate
                location = re.sub(r'\s+', ' ', location)
                if len(location) > 3 and len(location) < 100:
                    logger.info(f"  [OK] Found location from pattern: {location}")
                    return location
        
        # Method 2: Search for known states/cities in content
        full_text_lower = full_text.lower()
        found_locations = []
        
        for location in self.LOCATION_KEYWORDS:
            if location in full_text_lower:
                found_locations.append(location.title())
        
        if found_locations:
            # Return first found or combine if multiple
            if len(found_locations) == 1:
                logger.info(f"  [OK] Found location from keywords: {found_locations[0]}")
                return found_locations[0]
            elif len(found_locations) <= 3:
                combined = ', '.join(found_locations[:3])
                logger.info(f"  [OK] Found multiple locations: {combined}")
                return combined
        
        # Method 3: Extract from organization name in title
        # E.g., "Delhi Police Recruitment" -> "Delhi"
        if title:
            for location in self.LOCATION_KEYWORDS:
                if location in title.lower():
                    logger.info(f"  [OK] Found location from title: {location.title()}")
                    return location.title()
        
        logger.debug("  [WARN] Could not extract location")
        return ''
    
    def _extract_vacancies(self, title: str, full_text: str, content: BeautifulSoup) -> Optional[int]:
        """Extract vacancy count using multiple methods.
        
        Returns the NUMBER of vacancies, NOT the year.
        """
        # Method 1: Extract from title
        if title:
            vacancy = self._extract_vacancies_from_text(title)
            if vacancy:
                logger.info(f"  [OK] Found vacancies in title: {vacancy}")
                return vacancy
        
        # Method 2: Look in content for explicit vacancy mentions
        # Find paragraph or div containing "total post" or "total vacanc"
        for element in content.find_all(['p', 'div', 'span', 'strong']):
            text = element.get_text(strip=True)
            if re.search(r'total\s+(?:post|vacanc)', text, re.IGNORECASE):
                vacancy = self._extract_vacancies_from_text(text)
                if vacancy:
                    logger.info(f"  [OK] Found vacancies in content: {vacancy}")
                    return vacancy
        
        # Method 3: Search in full text
        vacancy = self._extract_vacancies_from_text(full_text)
        if vacancy:
            logger.info(f"  [OK] Found vacancies in full text: {vacancy}")
            return vacancy
        
        # Method 4: Look in tables
        tables = content.find_all('table')
        for table in tables:
            table_data = self._extract_table_data(table)
            vacancy = self._get_total_from_table(table_data)
            if vacancy:
                logger.info(f"  [OK] Found vacancies in table: {vacancy}")
                return vacancy
        
        logger.debug("  [WARN] Could not extract vacancies")
        return None
    
    def _extract_vacancies_from_text(self, text: str) -> Optional[int]:
        """Extract vacancy count from text using patterns.
        
        Filters out years (2024-2030) and returns actual vacancy count.
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Try each pattern
        for pattern in self.VACANCY_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            
            for match in matches:
                try:
                    num = int(match)
                    
                    # Filter out years (2024-2030)
                    if 2024 <= num <= 2030:
                        continue
                    
                    # Filter out unreasonably large numbers
                    if num > 50000:
                        continue
                    
                    # Valid vacancy number found
                    if num > 0:
                        return num
                        
                except ValueError:
                    continue
        
        return None
    
    def _get_total_from_table(self, table_data: Dict[str, str]) -> Optional[int]:
        """Calculate total vacancies from table data."""
        total = 0
        
        for key, value in table_data.items():
            key_lower = key.lower()
            
            # Look for "Total" row
            if 'total' in key_lower:
                numbers = re.findall(r'\d+', value)
                for num_str in numbers:
                    num = int(num_str)
                    if 1 <= num < 50000 and (num < 2024 or num > 2030):
                        return num
            
            # Or sum up individual post counts
            if 'post' in key_lower or 'position' in key_lower:
                # Extract number from value
                numbers = re.findall(r'\d+', value)
                for num_str in numbers:
                    num = int(num_str)
                    if 1 <= num < 10000 and (num < 2024 or num > 2030):
                        total += num
        
        return total if total > 0 else None
    
    def _extract_organization(self, title: str, full_text: str) -> str:
        """Extract organization name."""
        if not title:
            return ''
        
        # Common patterns: "[ORG NAME] Recruitment 2026"
        match = re.search(r'^([A-Z][A-Za-z\s&\-\.]+?)(?:Recruitment|Notification|Job|Apply|–|\()', title)
        if match:
            org = match.group(1).strip()
            # Clean up
            org = re.sub(r'\s+', ' ', org)
            return org
        
        return ''
    
    def _extract_dates(self, full_text: str, content: BeautifulSoup) -> Dict:
        """Extract important dates."""
        dates = {
            'post_date': '',
            'last_date': '',
            'all_dates': {}
        }
        
        # Look for date mentions in text
        date_keywords = {
            'last date': 'last_date',
            'closing date': 'last_date',
            'end date': 'last_date',
            'post date': 'post_date',
            'publish date': 'post_date',
            'start date': 'Application Start',
            'exam date': 'Exam Date',
            'result date': 'Result Date'
        }
        
        for keyword, field in date_keywords.items():
            # Find text around keyword
            pattern = rf'{keyword}\s*:?\s*([\d\-/]+(?:\s+to\s+[\d\-/]+)?|\d{{1,2}}\s+\w+\s+\d{{4}})'
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                date_value = match.group(1).strip()
                
                if field in ['last_date', 'post_date']:
                    dates[field] = date_value
                else:
                    dates['all_dates'][field] = date_value
        
        return dates
    
    def _extract_urls(self, content: BeautifulSoup) -> Dict:
        """Extract URLs with CRITICAL FreeJobAlert filtering.
        
        Extracts:
        - job_url: "Apply Online" link (official application portal)
        - pdf_url: Official PDF notification
        - official_website: Official organization website
        
        ALL FreeJobAlert links are BLOCKED.
        """
        urls = {
            'job_url': None,  # Apply Online link (NULL if not found)
            'pdf_url': '',
            'official_notification_pdf': '',
            'official_website': '',
            'pdf_needs_upload': False
        }
        
        links = content.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '').strip()
            text = link.get_text(strip=True).lower()
            
            if not href or href.startswith('#'):
                continue
            
            # Make absolute URL
            if not href.startswith('http'):
                href = urljoin(self.BASE_URL, href)
            
            # CRITICAL: Block FreeJobAlert links immediately
            if self._is_freejobalert_link(href):
                continue  # Skip this link completely
            
            # Get parent context
            parent_text = ''
            if link.parent:
                parent_text = link.parent.get_text(strip=True).lower()
            
            # Identify link type based on text and context
            
            # 1. Apply Online button/link (HIGHEST PRIORITY)
            if any(keyword in text for keyword in ['apply online', 'click here to apply', 'apply now', 'apply here']):
                if not urls['job_url']:
                    urls['job_url'] = href
                    logger.info(f"✓ Found Apply Online link: {href[:70]}...")
            
            elif 'apply' in parent_text and ('online' in parent_text or 'click' in text):
                if not urls['job_url']:
                    urls['job_url'] = href
                    logger.info(f"✓ Found Apply Online link (from context): {href[:70]}...")
            
            # 2. PDF - Only from official sources
            elif '.pdf' in href.lower():
                if not urls['pdf_url']:
                    urls['pdf_url'] = href
                    urls['official_notification_pdf'] = href
                    logger.info(f"✓ Found official PDF: {href[:70]}...")
            
            # 3. Official Website - Only official domain links
            elif 'official website' in parent_text or 'official website' in text or 'official site' in text or 'visit website' in text:
                if not urls['official_website']:
                    urls['official_website'] = href
                    logger.info(f"✓ Found official website: {href[:70]}...")
        
        # Log if Apply Online link not found
        if not urls['job_url']:
            logger.warning("⚠️  Apply Online link not found - job_url will be NULL")
        
        return urls
    
    def _extract_table_data(self, table) -> Dict[str, str]:
        """Extract key-value pairs from table."""
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
                # First cell is key, rest are values
                key = cells[0].get_text(strip=True)
                values = [c.get_text(strip=True) for c in cells[1:]]
                if key and any(values):
                    data[key] = ' | '.join(v for v in values if v)
        
        return data
