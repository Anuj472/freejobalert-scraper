"""Smart Job Processor - IMPROVED with link filtering.

Architecture:
1. Priority: Extract CONTENT from PDF using Gemma 3 (no URLs)
2. Extract LINKS from HTML using CSS parser
3. Filter out FreeJobAlert links
4. Generate SEO blog using Gemma 3 (concise, <1000 words)
"""

import logging
from typing import Dict, Optional

from gemma_processor import GemmaProcessor
from robust_parser import RobustJobParser

logger = logging.getLogger(__name__)

class SmartJobProcessor:
    """Smart processor with PDF priority and link filtering."""
    
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
    
    def process_job(self, job_listing: Dict, html: str, details_url: str) -> Dict:
        """
        Process job with smart priority and link filtering.
        
        IMPROVED WORKFLOW:
        1. PDF extracts CONTENT (job details, no URLs)
        2. HTML extracts LINKS (application URLs, official website)
        3. Filter out FreeJobAlert links
        4. Generate concise blog (<1000 words)
        
        Args:
            job_listing: Basic job info from listing page
            html: HTML content of job details page
            details_url: URL of the job details page
            
        Returns:
            Complete job data with blog content
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
        
        # PRIORITY 1: Extract CONTENT from PDF using Gemma 3 (no URLs)
        if pdf_url and self.gemma.is_available():
            logger.info(f"🎯 Priority 1: Extracting CONTENT from PDF with Gemma 3")
            logger.info(f"   (URLs will be extracted from HTML separately)")
            
            structured_data = self.gemma.process_pdf_url(pdf_url)
            
            if structured_data:
                source = 'pdf_gemma3'
                logger.info(f"✓ Successfully extracted content from PDF")
                logger.info(f"   Extracted {len(structured_data)} fields")
            else:
                logger.warning("⚠️  PDF extraction failed, falling back to HTML parser")
        elif pdf_url:
            logger.info(f"⚠️  PDF found but Gemma 3 not available")
        
        # PRIORITY 2: Extract from HTML (includes links)
        if not structured_data:
            logger.info(f"📄 Priority 2: Extracting from HTML using CSS parser")
            structured_data = self.html_parser.parse_job_details(html, details_url)
            source = 'html_css'
            
            if structured_data:
                non_empty = len([v for v in structured_data.values() if v])
                logger.info(f"✓ Successfully extracted from HTML")
                logger.info(f"   Extracted {non_empty} non-empty fields")
        else:
            # PDF gave us content, HTML gives us links
            logger.info(f"📄 Extracting organization LINKS from HTML...")
            html_links = self.html_parser.parse_job_details(html, details_url)
            
            # Merge links from HTML (only if not already present)
            link_fields = ['application_url', 'official_website', 'organization_url', 'pdf_url']
            for field in link_fields:
                html_value = html_links.get(field)
                if html_value and not structured_data.get(field):
                    structured_data[field] = html_value
                    logger.info(f"   + Added {field} from HTML: {html_value[:50]}...")
        
        # Clean FreeJobAlert links from extracted data
        structured_data = self._clean_links(structured_data)
        
        # Merge basic listing data with extracted details
        final_data = {**job_listing, **structured_data}
        final_data['data_source'] = source
        
        # Final cleanup - ensure no FreeJobAlert links in final data
        final_data = self._clean_links(final_data)
        
        # Log final URLs
        if final_data.get('application_url'):
            logger.info(f"✓ Application URL: {final_data['application_url'][:60]}...")
        if final_data.get('official_website'):
            logger.info(f"✓ Official Website: {final_data['official_website'][:60]}...")
        
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
