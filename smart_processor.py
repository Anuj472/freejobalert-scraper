"""Smart Job Processor - IMPROVED with link filtering, post_date extraction, and category detection.

Architecture:
1. Priority: Extract CONTENT from PDF using Gemma 3 (includes location, category, no URLs, no post_date)
2. If no PDF: Extract from HTML + use Gemma to determine category from content
3. Extract LINKS and POST_DATE from HTML using CSS parser
4. Filter out FreeJobAlert links
5. Generate SEO blog using Gemma 3 (concise, <1000 words)
"""

import logging
import re
import json
import requests
from typing import Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup

from gemma_processor import GemmaProcessor
from robust_parser import RobustJobParser

logger = logging.getLogger(__name__)

class SmartJobProcessor:
    """Smart processor with PDF priority, category detection, link filtering, and post_date extraction."""
    
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
    
    def _clean_links(self, data: Dict) -> Dict:
        """Remove FreeJobAlert links, keep only organization links."""
        
        # Fields that might contain links
        link_fields = [
            'application_url',
            'official_website',
            'organization_url',
            'pdf_url',
            'official_notification_pdf'
        ]
        
        for field in link_fields:
            url = data.get(field)
            if url and self._is_freejobalert_link(url):
                logger.info(f"🚫 Filtered FreeJobAlert link from {field}: {url[:60]}...")
                data[field] = None  # Remove FreeJobAlert links
        
        return data
    
    def _extract_category_from_text(self, text: str, organization: str) -> Optional[str]:
        """Use Gemma to extract category from text content when no PDF is available."""
        if not self.gemma.is_available():
            return None
        
        try:
            # Truncate text to reasonable length
            text_sample = text[:3000]
            
            prompt = f"""Analyze this government job recruitment text and determine its CATEGORY.

ORGANIZATION: {organization}

TEXT SAMPLE:
{text_sample}

Based on the organization name and content, what is the MOST APPROPRIATE category?

Choose ONE from:
- "banking" - Banks: SBI, IBPS, RBI, PNB, Bank of India, Canara Bank, etc.
- "defence" - Armed Forces: Indian Army, Navy, Air Force, DRDO, NDA, Coast Guard, etc.
- "railway" - Indian Railways, RRB, Railway Recruitment Board, IRCTC
- "ssc" - Staff Selection Commission
- "upsc" - Union Public Service Commission
- "police" - Police Department, State/Central Police
- "teaching" - Universities, Schools, Education Dept, UGC, NCERT
- "psu" - PSUs: NTPC, ONGC, SAIL, BHEL, Coal India, etc.
- "state-govt" - State Government Departments
- "central-govt" - Central Government Departments
- "admit-card" - If this is an admit card document
- "result" - If this is a result document

Return ONLY the category name as a single word (e.g., "banking" or "railway").

CATEGORY:"""

            response = requests.post(
                f"{self.gemma.ollama_url}/api/generate",
                json={
                    "model": self.gemma.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 50
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                category = result.get('response', '').strip().lower()
                
                # Clean up response
                category = re.sub(r'[^a-z\-]', '', category)
                
                # Validate category
                valid_categories = [
                    'banking', 'defence', 'railway', 'ssc', 'upsc',
                    'police', 'teaching', 'psu', 'state-govt', 'central-govt',
                    'admit-card', 'result'
                ]
                
                if category in valid_categories:
                    logger.info(f"  ✓ Category detected by Gemma: {category}")
                    return category
                else:
                    logger.warning(f"  ⚠️ Invalid category from Gemma: {category}")
                    return None
            
        except Exception as e:
            logger.debug(f"Error extracting category with Gemma: {e}")
        
        return None
    
    def _extract_post_date_from_html(self, html: str) -> Optional[str]:
        """Extract article publish date from HTML metadata."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try multiple selectors for post date
            date_selectors = [
                'time[datetime]',  # Standard HTML5 time tag
                'meta[property="article:published_time"]',  # Open Graph
                'meta[name="publish_date"]',
                'meta[name="date"]',
                '.post-date',
                '.published',
                '.entry-date',
                'span.date',
                'time.published'
            ]
            
            for selector in date_selectors:
                element = soup.select_one(selector)
                if element:
                    # Get datetime attribute or text content
                    date_str = element.get('datetime') or element.get('content') or element.text
                    if date_str:
                        # Try to parse and convert to DD-MM-YYYY
                        date_str = date_str.strip()
                        
                        # Try various date formats
                        for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z', 
                                   '%d-%m-%Y', '%d/%m/%Y', '%B %d, %Y', '%d %B %Y']:
                            try:
                                dt = datetime.strptime(date_str.split('T')[0], fmt.split('T')[0])
                                return dt.strftime('%d-%m-%Y')
                            except:
                                continue
            
            # Fallback: Look for date patterns in text
            date_pattern = r'(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})'
            matches = re.findall(date_pattern, html[:5000])  # Search first 5KB
            if matches:
                date_str = matches[0]
                if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                    # YYYY-MM-DD format
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    return dt.strftime('%d-%m-%Y')
                elif re.match(r'\d{1,2}-\d{1,2}-\d{4}', date_str):
                    # DD-MM-YYYY format (already correct)
                    return date_str
            
            logger.debug("Could not extract post_date from HTML")
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting post_date: {e}")
            return None
    
    def process_job(self, job_listing: Dict, html: str, details_url: str) -> Dict:
        """
        Process job with smart priority, category detection, and link filtering.
        
        IMPROVED WORKFLOW:
        1. PDF extracts CONTENT (job details, location, category, NO URLs, NO post_date)
        2. If NO PDF: Extract from HTML + use Gemma to determine category from content
        3. HTML extracts LINKS + POST_DATE
        4. Filter out FreeJobAlert links
        5. Generate concise blog (<1000 words)
        
        Args:
            job_listing: Basic job info from listing page
            html: HTML content of job details page
            details_url: URL of the job details page
            
        Returns:
            Complete job data with blog content and category
        """
        
        structured_data = None
        source = None
        
        # Get PDF URL from various possible fields
        pdf_url = (job_listing.get('pdf_url') or 
                   job_listing.get('official_notification_pdf') or
                   job_listing.get('official_pdf'))
        
        # Filter FreeJobAlert PDF links
        if pdf_url and self._is_freejobalert_link(pdf_url):
            logger.info(f"✓ PDF URL from FreeJobAlert: {pdf_url[:60]}")
            # Keep it - we'll process PDF but won't save this URL to database
        
        # PRIORITY 1: Extract CONTENT from PDF using Gemma 3 (includes location, category, no URLs, no post_date)
        if pdf_url and self.gemma.is_available():
            logger.info(f"🎯 Priority 1: Extracting CONTENT (with location & category) from PDF")
            logger.info(f"   (URLs and post_date will be extracted from HTML)")
            
            structured_data = self.gemma.process_pdf_url(pdf_url)
            
            if structured_data:
                source = 'pdf_gemma3'
                logger.info(f"✓ Successfully extracted content from PDF")
                logger.info(f"   Extracted {len(structured_data)} fields")
                
                # Log important extracted fields
                if structured_data.get('category'):
                    logger.info(f"   ✓ Category extracted: {structured_data['category']}")
                else:
                    logger.warning(f"   ⚠️ Category not found in PDF")
                    
                if structured_data.get('location'):
                    logger.info(f"   ✓ Location extracted: {structured_data['location']}")
                else:
                    logger.warning(f"   ⚠️ Location not found in PDF")
            else:
                logger.warning("⚠️  PDF extraction failed, falling back to HTML parser")
        elif pdf_url:
            logger.info(f"⚠️  PDF found but Gemma 3 not available")
        
        # PRIORITY 2: Extract from HTML (includes links + post_date)
        if not structured_data:
            logger.info(f"📄 Priority 2: Extracting from HTML using CSS parser")
            structured_data = self.html_parser.parse_job_details(html, details_url)
            source = 'html_css'
            
            if structured_data:
                non_empty = len([v for v in structured_data.values() if v])
                logger.info(f"✓ Successfully extracted from HTML")
                logger.info(f"   Extracted {non_empty} non-empty fields")
                
                # CRITICAL: Use Gemma to extract category from HTML content
                if not structured_data.get('category'):
                    logger.info(f"🤖 No PDF available - using Gemma to detect category from HTML...")
                    organization = structured_data.get('organization', '')
                    full_text = structured_data.get('full_description', '')
                    
                    if organization and full_text:
                        category = self._extract_category_from_text(full_text, organization)
                        if category:
                            structured_data['category'] = category
                        else:
                            logger.warning(f"   ⚠️ Could not determine category from HTML")
        else:
            # PDF gave us content, HTML gives us links + post_date
            logger.info(f"📄 Extracting LINKS and POST_DATE from HTML...")
            html_links = self.html_parser.parse_job_details(html, details_url)
            
            # Merge links from HTML (only if not already present)
            link_fields = ['application_url', 'official_website', 'organization_url', 'pdf_url']
            for field in link_fields:
                html_value = html_links.get(field)
                if html_value and not structured_data.get(field):
                    structured_data[field] = html_value
                    logger.info(f"   + Added {field} from HTML: {html_value[:50]}...")
        
        # ALWAYS extract post_date from HTML (article publish date)
        logger.info(f"📅 Extracting post_date (article date) from HTML...")
        post_date = self._extract_post_date_from_html(html)
        if post_date:
            structured_data['post_date'] = post_date
            logger.info(f"   ✓ Post date extracted: {post_date}")
        else:
            logger.warning(f"   ⚠️ Could not extract post_date from HTML")
        
        # Clean FreeJobAlert links from extracted data
        structured_data = self._clean_links(structured_data)
        
        # Merge basic listing data with extracted details
        final_data = {**job_listing, **structured_data}
        final_data['data_source'] = source
        
        # Final cleanup - ensure no FreeJobAlert links in final data
        final_data = self._clean_links(final_data)
        
        # Log final important fields
        logger.info(f"📦 Final extracted fields:")
        if final_data.get('category'):
            logger.info(f"   ✓ Category: {final_data['category']}")
        else:
            logger.warning(f"   ⚠️ Category not extracted")
        if final_data.get('location'):
            logger.info(f"   ✓ Location: {final_data['location']}")
        if final_data.get('post_date'):
            logger.info(f"   ✓ Post Date: {final_data['post_date']}")
        if final_data.get('application_url'):
            logger.info(f"   ✓ Application URL: {final_data['application_url'][:60]}...")
        if final_data.get('official_website'):
            logger.info(f"   ✓ Official Website: {final_data['official_website'][:60]}...")
        
        # STEP 3: ALWAYS generate SEO blog with Gemma 3 (concise, <1000 words)
        if self.gemma.is_available():
            logger.info(f"🤖 Generating concise SEO blog (<1000 words) with Gemma 3...")
            blog_content = self.gemma.generate_blog(final_data)
            
            if blog_content:
                final_data['seo_title'] = blog_content.get('seo_title')
                final_data['meta_description'] = blog_content.get('meta_description')
                final_data['blog_article'] = blog_content.get('article')
                final_data['highlights'] = blog_content.get('highlights')
                final_data['faqs'] = blog_content.get('faqs')
                
                article_length = len(blog_content.get('article', ''))
                word_count = len(blog_content.get('article', '').split())
                logger.info(f"✓ SEO blog generated ({article_length} chars, ~{word_count} words)")
                logger.info(f"   - SEO title: {blog_content.get('seo_title', 'N/A')[:60]}...")
                logger.info(f"   - Meta desc: {blog_content.get('meta_description', 'N/A')[:60]}...")
                logger.info(f"   - Highlights: {len(blog_content.get('highlights', []))}")
                logger.info(f"   - FAQs: {len(blog_content.get('faqs', []))}")
            else:
                logger.warning("⚠️  Blog generation failed, using template fallback")
                final_data.update(self._generate_template_blog(final_data))
        else:
            logger.info("📝 Using template-based blog (Gemma 3 not available)")
            final_data.update(self._generate_template_blog(final_data))
        
        return final_data
    
    def _generate_template_blog(self, data: Dict) -> Dict:
        """Generate simple template-based blog as fallback."""
        
        title = data.get('title', 'Job Recruitment')
        org = data.get('organization', 'Organization')
        vacancies = data.get('vacancies', 'multiple')
        last_date = data.get('last_date', 'Check notification')
        
        seo_title = f"{title[:60]}..."
        meta_description = f"{org} recruitment notification. Apply for {vacancies} posts. Last date: {last_date}."
        
        article = f"""# {title}

## Overview
{org} has announced recruitment for {vacancies} posts. Interested and eligible candidates can apply before {last_date}.

## 🎯 Key Highlights
- Total Posts: {vacancies}
- Last Date: {last_date}
- Organization: {org}

## Important Details

### Vacancy Details
Total vacancies: {vacancies}

### Important Dates
Last date to apply: {last_date}

### How to Apply
Candidates should visit the official website and follow the application procedure mentioned in the official notification.
"""
        
        highlights = [
            f"Total Posts: {vacancies}",
            f"Last Date: {last_date}",
            f"Organization: {org}",
            "Apply Mode: Check notification",
            "For complete details, check official notification"
        ]
        
        faqs = [
            {
                "question": "What is the last date to apply?",
                "answer": f"The last date to apply is {last_date}."
            },
            {
                "question": "How many posts are available?",
                "answer": f"Total {vacancies} posts are available."
            },
            {
                "question": "How to apply for this recruitment?",
                "answer": "Check the official notification for complete application procedure."
            }
        ]
        
        return {
            'seo_title': seo_title,
            'meta_description': meta_description[:160],
            'blog_article': article,
            'highlights': highlights,
            'faqs': faqs
        }
