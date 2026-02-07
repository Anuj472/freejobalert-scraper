"""Smart Job Processor with intelligent data extraction.

Priority:
1. Extract from PDF (if available) using Gemma 3 multimodal
2. Fallback to HTML parser (if no PDF or PDF fails)
3. ALWAYS generate SEO blog using Gemma 3
"""

import logging
from typing import Dict, Optional

from gemma_processor import Gemma3Processor
from robust_parser import RobustJobParser

logger = logging.getLogger(__name__)

class SmartJobProcessor:
    """Smart processor with PDF-first approach and blog generation."""
    
    def __init__(self):
        """Initialize processors."""
        self.gemma = Gemma3Processor()
        self.html_parser = RobustJobParser()
        
        logger.info("Smart Job Processor initialized")
        logger.info(f"  - Gemma 3 12B: {'Available' if self.gemma.is_available() else 'Not Available'}")
        logger.info(f"  - HTML Parser: Available")
    
    def process_job(self, job_listing: Dict, html: str, details_url: str) -> Dict:
        """
        Process job with intelligent extraction.
        
        Workflow:
        1. Try PDF extraction (most reliable)
        2. Fallback to HTML parsing
        3. ALWAYS generate SEO blog
        
        Args:
            job_listing: Basic job info from listing page
            html: HTML content of detail page
            details_url: URL of detail page
            
        Returns:
            Complete job data with blog content
        """
        
        structured_data = None
        source = None
        
        # Extract PDF URL from HTML parser first
        html_data = self.html_parser.parse_job_details(html, details_url)
        pdf_url = html_data.get('pdf_url') or html_data.get('official_notification_pdf')
        
        # PRIORITY 1: Try PDF extraction with Gemma 3
        if pdf_url and self.gemma.is_available():
            logger.info("=" * 60)
            logger.info(f"🎯 PRIORITY 1: PDF Extraction")
            logger.info(f"   PDF URL: {pdf_url[:60]}...")
            logger.info("=" * 60)
            
            structured_data = self.gemma.process_pdf_url(pdf_url)
            
            if structured_data:
                source = 'pdf_gemma3'
                logger.info("✓ Successfully extracted data from PDF using Gemma 3")
                logger.info(f"  - Extracted {len([v for v in structured_data.values() if v])} fields")
            else:
                logger.warning("⚠️  PDF extraction failed, falling back to HTML")
        
        # PRIORITY 2: Fallback to HTML parser
        if not structured_data:
            logger.info("=" * 60)
            logger.info(f"📄 PRIORITY 2: HTML Extraction")
            logger.info(f"   Reason: {'No PDF found' if not pdf_url else 'PDF extraction failed'}")
            logger.info("=" * 60)
            
            structured_data = html_data
            source = 'html_css'
            logger.info("✓ Successfully extracted data from HTML")
            logger.info(f"  - Extracted {len([v for v in structured_data.values() if v])} fields")
        
        # Merge basic listing data with extracted details
        final_data = {**job_listing, **structured_data}
        final_data['data_source'] = source
        
        # PRIORITY 3: ALWAYS generate SEO blog with Gemma 3
        logger.info("=" * 60)
        logger.info("✍️  PRIORITY 3: Blog Generation (ALWAYS)")
        logger.info("=" * 60)
        
        if self.gemma.is_available():
            logger.info("🤖 Generating SEO blog with Gemma 3...")
            blog_content = self.gemma.generate_blog(final_data)
            
            if blog_content:
                final_data['seo_title'] = blog_content.get('seo_title')
                final_data['meta_description'] = blog_content.get('meta_description')
                final_data['blog_article'] = blog_content.get('article')
                final_data['highlights'] = blog_content.get('highlights')
                final_data['faqs'] = blog_content.get('faqs')
                
                article_len = len(blog_content.get('article', ''))
                logger.info(f"✓ SEO blog generated successfully")
                logger.info(f"  - Article length: {article_len} characters")
                logger.info(f"  - Highlights: {len(blog_content.get('highlights', []))} points")
                logger.info(f"  - FAQs: {len(blog_content.get('faqs', []))} questions")
            else:
                logger.warning("⚠️  Blog generation failed, using template")
                final_data['blog_article'] = self._generate_template_blog(final_data)
                final_data['seo_title'] = final_data.get('title', '')[:70]
                final_data['meta_description'] = f"Apply for {final_data.get('title', 'job')} recruitment"[:160]
        else:
            logger.warning("⚠️  Gemma 3 not available, using template blog")
            final_data['blog_article'] = self._generate_template_blog(final_data)
            final_data['seo_title'] = final_data.get('title', '')[:70]
            final_data['meta_description'] = f"Apply for {final_data.get('title', 'job')} recruitment"[:160]
        
        logger.info("=" * 60)
        logger.info("✓ Job processing complete")
        logger.info(f"  - Data source: {source}")
        logger.info(f"  - Has blog: {'Yes' if final_data.get('blog_article') else 'No'}")
        logger.info("=" * 60)
        
        return final_data
    
    def _generate_template_blog(self, data: Dict) -> str:
        """Generate basic template blog if Gemma 3 not available."""
        
        title = data.get('title', 'Job Recruitment')
        org = data.get('organization', 'Organization')
        vacancies = data.get('vacancies', 'Multiple')
        last_date = data.get('last_date', 'Check notification')
        
        return f"""# {title}

## Overview
{org} has announced recruitment for {vacancies} posts. This is an excellent opportunity for eligible candidates.

## Key Highlights
- 🎯 Organization: {org}
- 📌 Total Posts: {vacancies}
- 📅 Last Date: {last_date}

## Important Information
For complete details including eligibility criteria, selection process, and application procedure, please refer to the official notification.

## How to Apply
Eligible candidates can apply through the official website before the last date.

## Important Links
- Official Notification: Check official website
- Apply Online: Available on official portal

Note: This is a basic summary. For detailed information, refer to the official notification.
"""
