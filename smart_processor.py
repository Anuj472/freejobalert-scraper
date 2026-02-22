"""Smart Job Processor - CORRECTED PIPELINE.

CORRECT FLOW:
1. Scrape HTML → Extract ONLY links (job_url, pdf_url, official_website)
2. If PDF found → Download and give PDF to LLM
3. If NO PDF → Give raw HTML text to LLM
4. LLM extracts ALL other fields (title, org, qualification, dates, etc.)
5. Merge: Links from HTML + Everything else from LLM
6. Generate slug + blog

CRITICAL: HTML parser does NOT extract content fields, only links.
"""

import logging
import re
import requests
from typing import Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from gemma_processor import GemmaProcessor

logger = logging.getLogger(__name__)

class SmartJobProcessor:
    """Smart processor: Extract links from HTML, give PDF/text to LLM."""
    
    def __init__(self):
        """Initialize processor."""
        self.gemma = GemmaProcessor()
        
        if self.gemma.is_available():
            logger.info("✓ Smart processor initialized with Gemma 3")
        else:
            logger.warning("⚠️  Gemma 3 not available - scraper will only extract links!")
    
    def _is_freejobalert_link(self, url: str) -> bool:
        """Check if URL is from FreeJobAlert (should be BLOCKED)."""
        if not url:
            return False
        return 'freejobalert.com' in url.lower()
    
    def _extract_links_from_html(self, html: str, base_url: str) -> Dict:
        """Extract ONLY links from HTML.
        
        Returns:
        - job_url: Apply Online link
        - pdf_url: Official PDF notification
        - official_website: Official organization website
        
        Blocks all FreeJobAlert links.
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            links = {
                'job_url': None,
                'pdf_url': None,
                'official_website': None,
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
                
                # CRITICAL: Skip FreeJobAlert links
                if self._is_freejobalert_link(href):
                    continue
                
                # Get parent context
                parent_text = ''
                if link.parent:
                    parent_text = link.parent.get_text(strip=True).lower()
                
                # Identify link type
                
                # 1. Apply Online link
                if not links['job_url']:
                    if any(kw in text for kw in ['apply online', 'click here to apply', 'apply now', 'register', 'login']):
                        links['job_url'] = href
                        logger.info(f"✓ Apply Online: {href[:60]}...")
                        continue
                    elif 'apply' in parent_text and ('online' in parent_text or 'click' in text):
                        links['job_url'] = href
                        logger.info(f"✓ Apply Online (context): {href[:60]}...")
                        continue
                
                # 2. PDF notification
                if not links['pdf_url'] and '.pdf' in href.lower():
                    # Prefer links with notification/official keywords
                    if any(kw in text or kw in parent_text for kw in ['notification', 'official', 'advertisement', 'download pdf']):
                        links['pdf_url'] = href
                        logger.info(f"✓ PDF: {href[:60]}...")
                        continue
                    # Fallback: any PDF link
                    links['pdf_url'] = href
                    logger.info(f"✓ PDF: {href[:60]}...")
                
                # 3. Official website
                if not links['official_website']:
                    if any(kw in text or kw in parent_text for kw in ['official website', 'official site', 'visit website']):
                        links['official_website'] = href
                        logger.info(f"✓ Official Website: {href[:60]}...")
            
            # Log summary
            if not links['job_url']:
                logger.warning("⚠️  Apply Online link not found")
            if not links['pdf_url']:
                logger.info("ℹ️  No PDF link found")
            
            return links
            
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
            return {}
    
    def _get_raw_text_from_html(self, html: str) -> str:
        """Extract clean text content from HTML for LLM processing."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content
            content = soup.find('div', class_='entry-content') or soup.find('article') or soup.body
            
            if not content:
                return soup.get_text(separator='\n', strip=True)
            
            # Remove script/style tags
            for tag in content(['script', 'style', 'iframe', 'nav', 'footer', 'header']):
                tag.decompose()
            
            # Get clean text
            raw_text = content.get_text(separator='\n', strip=True)
            
            # Limit to reasonable size (Gemma context limit)
            if len(raw_text) > 10000:
                raw_text = raw_text[:10000]
            
            return raw_text
            
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return ""
    
    def process_job(self, job_listing: Dict, html: str, details_url: str) -> Dict:
        """
        CORRECT PIPELINE:
        
        1. Extract ONLY links from HTML (job_url, pdf_url, official_website)
        2. Check if PDF found:
           - YES: Download PDF → Give to LLM → Extract ALL fields
           - NO: Give raw HTML text to LLM → Extract ALL fields
        3. Merge: Links from HTML + All fields from LLM
        4. Generate blog
        
        Args:
            job_listing: Basic info from listing page (title, org from table)
            html: HTML content of detail page
            details_url: URL of detail page
        
        Returns:
            Complete job data
        """
        
        logger.info("="*60)
        logger.info("STEP 1: Extracting ONLY links from HTML...")
        
        # STEP 1: Extract ONLY links from HTML
        html_links = self._extract_links_from_html(html, details_url)
        
        # STEP 2: Check if PDF found
        pdf_url = html_links.get('pdf_url')
        
        llm_data = None
        source = None
        
        if pdf_url and self.gemma.is_available():
            logger.info("="*60)
            logger.info("🞼 SCENARIO: PDF Found")
            logger.info("STEP 2: Downloading PDF and giving to LLM...")
            logger.info(f"PDF URL: {pdf_url[:70]}...")
            
            # Give PDF to LLM - extracts ALL fields
            llm_data = self.gemma.process_pdf_url(pdf_url)
            
            if llm_data:
                source = 'pdf_gemma3'
                logger.info("✓ LLM extracted ALL fields from PDF")
                logger.info(f"   Extracted {len([v for v in llm_data.values() if v])} fields")
            else:
                logger.warning("⚠️  PDF extraction failed, falling back to HTML text...")
        
        # STEP 3: NO PDF or PDF failed → Give raw HTML text to LLM
        if not llm_data:
            if self.gemma.is_available():
                logger.info("="*60)
                logger.info("📄 SCENARIO: NO PDF or PDF failed")
                logger.info("STEP 3: Extracting raw text from HTML and giving to LLM...")
                
                raw_text = self._get_raw_text_from_html(html)
                
                if raw_text:
                    logger.info(f"Raw text length: {len(raw_text)} chars")
                    
                    # Give raw text to LLM - extracts ALL fields
                    llm_data = self.gemma.process_text(raw_text)
                    
                    if llm_data:
                        source = 'html_gemma3'
                        logger.info("✓ LLM extracted ALL fields from HTML text")
                        logger.info(f"   Extracted {len([v for v in llm_data.values() if v])} fields")
                    else:
                        logger.error("❌ LLM extraction failed!")
                        llm_data = {}
                else:
                    logger.error("❌ Could not extract text from HTML!")
                    llm_data = {}
            else:
                logger.error("❌ Gemma not available! Cannot extract fields.")
                logger.error("Only links will be available.")
                llm_data = {}
        
        # STEP 4: Merge data
        logger.info("="*60)
        logger.info("STEP 4: Merging data...")
        
        # Start with job listing data (basic table data)
        final_data = {**job_listing}
        
        # Add ALL LLM extracted fields (overwrite table data with LLM data)
        if llm_data:
            final_data.update(llm_data)
        
        # Add links from HTML (authoritative for URLs)
        final_data.update(html_links)
        
        # Set data source
        final_data['data_source'] = source or 'html_only'
        
        # CRITICAL: Ensure NO FreeJobAlert links
        for field in ['job_url', 'pdf_url', 'official_website']:
            url = final_data.get(field)
            if url and self._is_freejobalert_link(url):
                logger.warning(f"🚨 Removing FreeJobAlert link from {field}")
                final_data[field] = None
        
        # Log final summary
        logger.info("="*60)
        logger.info("📦 FINAL DATA SUMMARY:")
        logger.info(f"   Source: {final_data.get('data_source')}")
        logger.info(f"   Title: {final_data.get('title', 'N/A')[:50]}...")
        logger.info(f"   Organization: {final_data.get('organization', 'N/A')[:50]}...")
        if final_data.get('category'):
            logger.info(f"   ✓ Category: {final_data['category']}")
        if final_data.get('qualification'):
            logger.info(f"   ✓ Qualification: {final_data['qualification'][:40]}...")
        if final_data.get('location'):
            logger.info(f"   ✓ Location: {final_data['location']}")
        if final_data.get('vacancies'):
            logger.info(f"   ✓ Vacancies: {final_data['vacancies']}")
        if final_data.get('job_url'):
            logger.info(f"   ✓ Apply URL: {final_data['job_url'][:60]}...")
        if final_data.get('pdf_url'):
            logger.info(f"   ✓ PDF URL: {final_data['pdf_url'][:60]}...")
        logger.info("="*60)
        
        # STEP 5: Generate blog
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
