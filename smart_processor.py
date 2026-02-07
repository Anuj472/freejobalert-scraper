"""Smart Job Processor - CORRECT FLOW:

1. FIRST: Find PDF link in detail page HTML
2. If PDF found → Download and give to Gemma for ALL content extraction
3. Then extract ONLY links + dates from HTML
4. If NO PDF → Parse HTML content + Gemma determines category
"""

import logging
import re
import json
import requests
from typing import Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from gemma_processor import GemmaProcessor
from robust_parser import RobustJobParser

logger = logging.getLogger(__name__)

class SmartJobProcessor:
    """Smart processor: Find PDF first, then decide extraction strategy."""
    
    def __init__(self):
        """Initialize processors."""
        self.gemma = GemmaProcessor()
        self.html_parser = RobustJobParser()
        
        if self.gemma.is_available():
            logger.info("✓ Smart processor initialized with Gemma 3")
        else:
            logger.warning("⚠️  Gemma 3 not available, will use HTML parser only")
    
    def _is_freejobalert_link(self, url: str) -> bool:
        """Check if URL is from FreeJobAlert (should be filtered)."""
        if not url:
            return False
        return 'freejobalert.com' in url.lower()
    
    def _find_pdf_link_in_html(self, html: str, base_url: str) -> Optional[str]:
        """STEP 1: Find PDF notification link in HTML.
        
        Returns:
            PDF URL or None
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for PDF links
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '').strip()
                text = link.get_text(strip=True).lower()
                
                if not href:
                    continue
                
                # Make absolute URL
                if not href.startswith('http'):
                    href = urljoin(base_url, href)
                
                # Check if it's a PDF
                if '.pdf' in href.lower():
                    # Prefer official notification PDFs
                    if any(keyword in text for keyword in ['notification', 'download', 'official', 'advt', 'advertisement']):
                        logger.info(f"✓ Found PDF link: {href[:70]}...")
                        return href
            
            # If no keyword match, return first PDF found
            for link in all_links:
                href = link.get('href', '').strip()
                if href and '.pdf' in href.lower():
                    if not href.startswith('http'):
                        href = urljoin(base_url, href)
                    logger.info(f"✓ Found PDF link: {href[:70]}...")
                    return href
            
            logger.info("ℹ️  No PDF link found in HTML")
            return None
            
        except Exception as e:
            logger.debug(f"Error finding PDF link: {e}")
            return None
    
    def _extract_links_only_from_html(self, html: str, base_url: str) -> Dict:
        """Extract ONLY links from HTML (NO content parsing)."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            links = {
                'pdf_url': None,
                'application_url': None,
                'official_website': None,
                'organization_url': None,
            }
            
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '').strip()
                text = link.get_text(strip=True).lower()
                
                if not href or href.startswith('#'):
                    continue
                
                # Make absolute URL
                if not href.startswith('http'):
                    href = urljoin(base_url, href)
                
                # Skip FreeJobAlert links
                if self._is_freejobalert_link(href):
                    continue
                
                # Identify link type
                if '.pdf' in href.lower() and not links['pdf_url']:
                    links['pdf_url'] = href
                elif 'apply' in text and not links['application_url']:
                    links['application_url'] = href
                elif 'official website' in text or 'official site' in text:
                    if not links['official_website']:
                        links['official_website'] = href
                    if not links['organization_url']:
                        links['organization_url'] = href
            
            return links
            
        except Exception as e:
            logger.debug(f"Error extracting links: {e}")
            return {}
    
    def _extract_post_date_from_html(self, html: str) -> Optional[str]:
        """Extract article publish date from HTML metadata."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            date_selectors = [
                'time[datetime]',
                'meta[property="article:published_time"]',
                'meta[name="publish_date"]',
                'meta[name="date"]',
                '.post-date',
                '.published',
                '.entry-date',
            ]
            
            for selector in date_selectors:
                element = soup.select_one(selector)
                if element:
                    date_str = element.get('datetime') or element.get('content') or element.text
                    if date_str:
                        date_str = date_str.strip()
                        
                        for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d-%m-%Y', '%d/%m/%Y']:
                            try:
                                dt = datetime.strptime(date_str.split('T')[0], fmt.split('T')[0])
                                return dt.strftime('%d-%m-%Y')
                            except:
                                continue
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting post_date: {e}")
            return None
    
    def _extract_last_date_from_html(self, html: str) -> Optional[str]:
        """Extract last date from HTML if not in PDF."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text()
            
            pattern = r'(?:last date|closing date|end date)[:\s]*([\d\-/]+)'
            match = re.search(pattern, text, re.IGNORECASE)
            
            if match:
                date_str = match.group(1).strip()
                for fmt in ['%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d']:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        return dt.strftime('%d-%m-%Y')
                    except:
                        continue
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting last_date: {e}")
            return None
    
    def _extract_category_from_text(self, text: str, organization: str) -> Optional[str]:
        """Use Gemma to extract category from text when no PDF."""
        if not self.gemma.is_available():
            return None
        
        try:
            text_sample = text[:3000]
            
            prompt = f"""Analyze this government job recruitment text and determine its CATEGORY.

ORGANIZATION: {organization}

TEXT SAMPLE:
{text_sample}

Based on the organization name, choose the MOST APPROPRIATE category:

- "banking" - Banks: SBI, IBPS, RBI, PNB, Bank of India, Canara Bank, etc.
- "defence" - Armed Forces: Indian Army, Navy, Air Force, DRDO, NDA, Coast Guard
- "railway" - Indian Railways, RRB, Railway Recruitment Board
- "ssc" - Staff Selection Commission
- "upsc" - Union Public Service Commission
- "police" - Police Department, State/Central Police
- "teaching" - Universities, Schools, Education Dept, UGC, NCERT
- "psu" - PSUs: NTPC, ONGC, SAIL, BHEL, Coal India
- "state-govt" - State Government Departments
- "central-govt" - Central Government Departments

Return ONLY the category name (e.g., "banking" or "railway").

CATEGORY:"""

            response = requests.post(
                f"{self.gemma.ollama_url}/api/generate",
                json={
                    "model": self.gemma.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 50}
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                category = result.get('response', '').strip().lower()
                category = re.sub(r'[^a-z\-]', '', category)
                
                valid_categories = [
                    'banking', 'defence', 'railway', 'ssc', 'upsc',
                    'police', 'teaching', 'psu', 'state-govt', 'central-govt'
                ]
                
                if category in valid_categories:
                    logger.info(f"  ✓ Category detected: {category}")
                    return category
            
        except Exception as e:
            logger.debug(f"Error extracting category: {e}")
        
        return None
    
    def process_job(self, job_listing: Dict, html: str, details_url: str) -> Dict:
        """
        CORRECT FLOW:
        
        STEP 1: Find PDF link in detail page HTML
        STEP 2: If PDF found → Gemma extracts ALL content from PDF
        STEP 3: HTML extracts ONLY links + dates
        STEP 4: If NO PDF → Full HTML parsing + Gemma for category
        
        Args:
            job_listing: Basic job info from listing page
            html: HTML content of job details page
            details_url: URL of the job details page
            
        Returns:
            Complete job data with blog content
        """
        
        logger.info("="*60)
        logger.info("STEP 1: Finding PDF link in detail page HTML...")
        
        # STEP 1: Find PDF link in the detail page HTML
        pdf_url = self._find_pdf_link_in_html(html, details_url)
        
        structured_data = None
        source = None
        
        # STEP 2: If PDF found → Download and give to Gemma
        if pdf_url and self.gemma.is_available():
            logger.info("="*60)
            logger.info("🎯 SCENARIO: PDF Found")
            logger.info("STEP 2: Downloading PDF and giving to Gemma...")
            logger.info(f"PDF URL: {pdf_url[:70]}...")
            
            # Download PDF and extract ALL content with Gemma
            structured_data = self.gemma.process_pdf_url(pdf_url)
            
            if structured_data:
                source = 'pdf_gemma3'
                logger.info("✓ Gemma extracted ALL content from PDF")
                logger.info(f"   Extracted {len([v for v in structured_data.values() if v])} fields")
                
                if structured_data.get('category'):
                    logger.info(f"   ✓ Category: {structured_data['category']}")
                if structured_data.get('location'):
                    logger.info(f"   ✓ Location: {structured_data['location']}")
                if structured_data.get('vacancies'):
                    logger.info(f"   ✓ Vacancies: {structured_data['vacancies']}")
                
                # STEP 3: Extract ONLY links + dates from HTML
                logger.info("")
                logger.info("STEP 3: Extracting ONLY links + dates from HTML...")
                logger.info("(NOT parsing content - already have it from PDF)")
                
                html_links = self._extract_links_only_from_html(html, details_url)
                for field, value in html_links.items():
                    if value and not structured_data.get(field):
                        structured_data[field] = value
                        logger.info(f"   + {field}: {value[:60]}...")
                
                # Extract dates
                post_date = self._extract_post_date_from_html(html)
                if post_date:
                    structured_data['post_date'] = post_date
                    logger.info(f"   + post_date: {post_date}")
                
                if not structured_data.get('last_date'):
                    last_date = self._extract_last_date_from_html(html)
                    if last_date:
                        structured_data['last_date'] = last_date
                        logger.info(f"   + last_date: {last_date}")
                
            else:
                logger.warning("⚠️  PDF extraction failed!")
                logger.info("Falling back to HTML parsing...")
        
        elif pdf_url and not self.gemma.is_available():
            logger.warning("⚠️  PDF found but Gemma not available")
            logger.info("Falling back to HTML parsing...")
        
        # STEP 4: NO PDF or PDF extraction failed → Full HTML parsing
        if not structured_data:
            logger.info("="*60)
            logger.info("📄 SCENARIO: NO PDF or PDF failed")
            logger.info("STEP 4: Full HTML content parsing...")
            
            structured_data = self.html_parser.parse_job_details(html, details_url)
            source = 'html_css'
            
            if structured_data:
                logger.info("✓ HTML parser extracted content")
                logger.info(f"   Extracted {len([v for v in structured_data.values() if v])} fields")
                
                # Use Gemma to determine category from HTML text
                if not structured_data.get('category'):
                    logger.info("")
                    logger.info("🤖 Using Gemma to detect category from HTML text...")
                    organization = structured_data.get('organization', '')
                    full_text = structured_data.get('full_description', '')
                    
                    if organization and full_text:
                        category = self._extract_category_from_text(full_text, organization)
                        if category:
                            structured_data['category'] = category
                
                # Extract dates
                post_date = self._extract_post_date_from_html(html)
                if post_date:
                    structured_data['post_date'] = post_date
        
        # Merge with job listing data
        final_data = {**job_listing, **structured_data}
        final_data['data_source'] = source
        
        # Filter FreeJobAlert links
        link_fields = ['application_url', 'official_website', 'organization_url', 'pdf_url']
        for field in link_fields:
            url = final_data.get(field)
            if url and self._is_freejobalert_link(url):
                logger.info(f"🚫 Filtered FreeJobAlert link from {field}")
                final_data[field] = None
        
        # Log final summary
        logger.info("="*60)
        logger.info("📦 FINAL EXTRACTED DATA:")
        logger.info(f"   Source: {source}")
        if final_data.get('category'):
            logger.info(f"   ✓ Category: {final_data['category']}")
        if final_data.get('location'):
            logger.info(f"   ✓ Location: {final_data['location']}")
        if final_data.get('vacancies'):
            logger.info(f"   ✓ Vacancies: {final_data['vacancies']}")
        if final_data.get('post_date'):
            logger.info(f"   ✓ Post Date: {final_data['post_date']}")
        logger.info("="*60)
        
        # Generate SEO blog
        if self.gemma.is_available():
            logger.info("🤖 Generating SEO blog...")
            blog_content = self.gemma.generate_blog(final_data)
            
            if blog_content:
                final_data['seo_title'] = blog_content.get('seo_title')
                final_data['meta_description'] = blog_content.get('meta_description')
                final_data['blog_article'] = blog_content.get('article')
                final_data['highlights'] = blog_content.get('highlights')
                final_data['faqs'] = blog_content.get('faqs')
                
                logger.info(f"✓ Blog generated ({len(blog_content.get('article', ''))} chars)")
            else:
                final_data.update(self._generate_template_blog(final_data))
        else:
            final_data.update(self._generate_template_blog(final_data))
        
        return final_data
    
    def _generate_template_blog(self, data: Dict) -> Dict:
        """Generate simple template-based blog as fallback."""
        
        title = data.get('title', 'Job Recruitment')
        org = data.get('organization', 'Organization')
        vacancies = data.get('vacancies', 'multiple')
        last_date = data.get('last_date', 'Check notification')
        
        seo_title = f"{title[:60]}..."
        meta_description = f"{org} recruitment. Apply for {vacancies} posts. Last date: {last_date}."
        
        article = f"""# {title}

## Overview
{org} has announced recruitment for {vacancies} posts. Last date: {last_date}.

## Key Highlights
- Total Posts: {vacancies}
- Last Date: {last_date}
- Organization: {org}
"""
        
        highlights = [
            f"Total Posts: {vacancies}",
            f"Last Date: {last_date}",
            f"Organization: {org}"
        ]
        
        faqs = [
            {"question": "What is the last date?", "answer": f"Last date is {last_date}."}
        ]
        
        return {
            'seo_title': seo_title,
            'meta_description': meta_description[:160],
            'blog_article': article,
            'highlights': highlights,
            'faqs': faqs
        }
