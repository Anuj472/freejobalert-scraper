"""Smart Job Processor with intelligent data extraction.

Architecture:
1. Priority: Extract from PDF using Gemma 3 (if available)
2. Fallback: Extract from HTML using CSS parser
3. Always: Generate SEO blog using Gemma 3
"""

import logging
from typing import Dict, Optional

from gemma_processor import GemmaProcessor
from robust_parser import RobustJobParser

logger = logging.getLogger(__name__)

class SmartJobProcessor:
    """Smart processor with PDF priority and LLM blog generation."""
    
    def __init__(self):
        """Initialize processors."""
        self.gemma = GemmaProcessor()
        self.html_parser = RobustJobParser()
        
        if self.gemma.is_available():
            logger.info("✓ Smart processor initialized with Gemma 3")
        else:
            logger.warning("⚠️  Gemma 3 not available, will use HTML parser only")
    
    def process_job(self, job_listing: Dict, html: str, details_url: str) -> Dict:
        """
        Process job with smart priority:
        
        1. Try PDF extraction with Gemma 3 (best quality)
        2. Fallback to HTML parsing (reliable)
        3. ALWAYS generate SEO blog with Gemma 3
        
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
        
        # PRIORITY 1: Extract from PDF using Gemma 3
        if pdf_url and self.gemma.is_available():
            logger.info(f"🎯 Priority 1: Extracting from PDF with Gemma 3")
            logger.info(f"   PDF: {pdf_url[:60]}...")
            
            structured_data = self.gemma.process_pdf_url(pdf_url)
            
            if structured_data:
                source = 'pdf_gemma3'
                logger.info(f"✓ Successfully extracted from PDF using Gemma 3")
                logger.info(f"   Extracted {len(structured_data)} fields")
            else:
                logger.warning("⚠️  PDF extraction failed, falling back to HTML parser")
        elif pdf_url:
            logger.info(f"⚠️  PDF found but Gemma 3 not available")
        
        # PRIORITY 2: Fallback to HTML parsing
        if not structured_data:
            logger.info(f"📄 Priority 2: Extracting from HTML using CSS parser")
            structured_data = self.html_parser.parse_job_details(html, details_url)
            source = 'html_css'
            
            if structured_data:
                non_empty = len([v for v in structured_data.values() if v])
                logger.info(f"✓ Successfully extracted from HTML")
                logger.info(f"   Extracted {non_empty} non-empty fields")
        
        # Merge basic listing data with extracted details
        final_data = {**job_listing, **structured_data}
        final_data['data_source'] = source
        
        # STEP 3: ALWAYS generate SEO blog with Gemma 3
        if self.gemma.is_available():
            logger.info(f"🤖 Generating SEO blog content with Gemma 3...")
            blog_content = self.gemma.generate_blog(final_data)
            
            if blog_content:
                final_data['seo_title'] = blog_content.get('seo_title')
                final_data['meta_description'] = blog_content.get('meta_description')
                final_data['blog_article'] = blog_content.get('article')
                final_data['highlights'] = blog_content.get('highlights')
                final_data['faqs'] = blog_content.get('faqs')
                
                article_length = len(blog_content.get('article', ''))
                logger.info(f"✓ SEO blog generated ({article_length} chars)")
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

## Key Highlights
- 🎯 Total Posts: {vacancies}
- 📅 Last Date: {last_date}
- 🏢 Organization: {org}

## Important Details

### Vacancy Details
Total vacancies: {vacancies}

### Important Dates
Last date to apply: {last_date}

### How to Apply
Candidates should visit the official website and follow the application procedure mentioned in the official notification.

## Important Links
- Official Website: {data.get('official_website', 'Check notification')}
- Apply Online: {data.get('application_url', 'Check notification')}
- Official PDF: {data.get('pdf_url', 'Check notification')}
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
