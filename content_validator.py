#!/usr/bin/env python3
"""
Content Validator - Prevents FreeJobAlert Links in Database

Two-Stage Approach:
1. Clean scraped content BEFORE passing to LLM
2. Validate LLM output BEFORE database insertion

Usage:
    from content_validator import sanitize_job_data, remove_freejobalert_links
    
    # Stage 1: Clean scraped content
    cleaned = remove_freejobalert_links(raw_content)
    
    # Stage 2: Validate before insert
    safe_data = sanitize_job_data(job_data)
    supabase.insert_job(safe_data)
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

def remove_freejobalert_links(text: Optional[str]) -> str:
    """
    Remove all freejobalert.com references from text content.
    
    Args:
        text: Text content to clean
        
    Returns:
        Cleaned text without freejobalert references
    """
    if not text:
        return ''
    
    cleaned = text
    
    # Pattern 1: Remove markdown links [text](https://freejobalert.com/...)
    cleaned = re.sub(
        r'\[([^\]]+)\]\(https?://(?:www\.)?freejobalert\.com[^)]*\)',
        r'\1',
        cleaned,
        flags=re.IGNORECASE
    )
    
    # Pattern 2: Remove plain URLs
    cleaned = re.sub(
        r'https?://(?:www\.)?freejobalert\.com\S*',
        '',
        cleaned,
        flags=re.IGNORECASE
    )
    
    # Pattern 3: Remove "Source:" lines
    cleaned = re.sub(
        r'\*\*Source:\*\*\s*\[?freejobalert\]?[^\n]*\n?',
        '',
        cleaned,
        flags=re.IGNORECASE
    )
    
    # Pattern 4: Remove "Visit/Download/Check FreeJobAlert" sentences
    cleaned = re.sub(
        r'(?:Visit|Download|Check)\s+(?:the\s+)?FreeJobAlert[^.]*\.',
        '',
        cleaned,
        flags=re.IGNORECASE
    )
    
    # Pattern 5: Remove numbered list items with freejobalert
    cleaned = re.sub(
        r'^\s*\d+\.\s*\*\*.*?FreeJobAlert.*?$',
        '',
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE
    )
    
    # Pattern 6: Replace remaining "freejobalert" text mentions
    cleaned = re.sub(r'freejobalert\.com', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'freejobalert', 'official source', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Max 2 newlines
    cleaned = re.sub(r' {2,}', ' ', cleaned)  # Max 1 space
    cleaned = cleaned.strip()
    
    return cleaned


def validate_job_content(content: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validate that job content doesn't contain freejobalert references.
    
    Args:
        content: Job data dictionary
        
    Returns:
        Tuple of (is_valid, errors, cleaned_content)
    """
    errors = []
    cleaned_content = content.copy()
    
    # Fields to check for freejobalert references
    text_fields = [
        'blog_article',
        'how_to_apply',
        'full_description',
        'selection_process',
        'seo_title',
        'meta_description'
    ]
    
    for field in text_fields:
        if field in content and content[field]:
            field_value = str(content[field]).lower()
            
            # Check for freejobalert in the content
            if 'freejobalert' in field_value:
                errors.append(f"Field '{field}' contains freejobalert reference")
            
            # Auto-clean the field
            cleaned_content[field] = remove_freejobalert_links(content[field])
    
    # Special handling for URL fields - set to None if freejobalert
    url_fields = ['job_url', 'pdf_url', 'official_website']
    for field in url_fields:
        if content.get(field) and 'freejobalert' in str(content[field]).lower():
            errors.append(f"Field '{field}' contains freejobalert URL")
            cleaned_content[field] = None
            logger.warning(f"⚠️ Removed freejobalert URL from {field}")
    
    is_valid = len(errors) == 0
    
    return is_valid, errors, cleaned_content


def sanitize_job_data(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize job data before database insertion.
    This ensures NO freejobalert content gets through.
    
    Args:
        job_data: Raw job data
        
    Returns:
        Sanitized job data safe for database insertion
    """
    is_valid, errors, cleaned_content = validate_job_content(job_data)
    
    if not is_valid:
        logger.warning(f"⚠️ Job content contained freejobalert references (auto-cleaned): {len(errors)} issues")
        for error in errors:
            logger.debug(f"   - {error}")
    
    return cleaned_content


def get_llm_prompt_instructions() -> str:
    """
    Get LLM prompt instructions that prevent freejobalert mentions.
    
    Returns:
        Prompt instructions string to append to LLM prompts
    """
    return """
CRITICAL CONTENT GUIDELINES:
1. NEVER mention "freejobalert" or "freejobalert.com" in any content
2. DO NOT include external job portal or blog website links
3. ONLY include official government/organization website links
4. Focus on creating original, helpful content for job seekers
5. Use phrases like "official notification" or "official source" instead of website names
6. All URLs must be from official government domains (.gov.in, .nic.in, railways.gov.in, etc.)
"""


def validate_highlights(highlights: List[str]) -> List[str]:
    """
    Clean freejobalert references from highlights array.
    
    Args:
        highlights: List of highlight strings
        
    Returns:
        Cleaned highlights list
    """
    if not highlights:
        return []
    
    cleaned = []
    for highlight in highlights:
        if highlight and 'freejobalert' not in highlight.lower():
            cleaned.append(remove_freejobalert_links(highlight))
        else:
            logger.debug(f"Removed highlight with freejobalert reference")
    
    return cleaned


def validate_faqs(faqs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Clean freejobalert references from FAQs array.
    
    Args:
        faqs: List of FAQ dictionaries with 'question' and 'answer' keys
        
    Returns:
        Cleaned FAQs list
    """
    if not faqs:
        return []
    
    cleaned = []
    for faq in faqs:
        if isinstance(faq, dict):
            cleaned_faq = {
                'question': remove_freejobalert_links(faq.get('question', '')),
                'answer': remove_freejobalert_links(faq.get('answer', ''))
            }
            # Only add if both question and answer are non-empty after cleaning
            if cleaned_faq['question'] and cleaned_faq['answer']:
                # Check if cleaned content still contains freejobalert
                if 'freejobalert' not in (cleaned_faq['question'] + cleaned_faq['answer']).lower():
                    cleaned.append(cleaned_faq)
                else:
                    logger.debug(f"Removed FAQ with freejobalert reference")
    
    return cleaned


# ===== Test/Example Usage =====
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Content Validator - Test Suite")
    print("="*60 + "\n")
    
    # Test 1: Remove links from text
    print("Test 1: Removing freejobalert links\n")
    
    test_text = """
    **Source:** [FreeJobAlert](https://www.freejobalert.com/articles/123)
    
    Visit FreeJobAlert for more details.
    
    Download from: https://www.freejobalert.com/pdf/notification.pdf
    
    Check freejobalert.com daily for updates.
    """
    
    print("BEFORE:")
    print(test_text)
    print("\nAFTER:")
    print(remove_freejobalert_links(test_text))
    
    # Test 2: Validate job data
    print("\n" + "-"*60)
    print("Test 2: Validating job data\n")
    
    test_job = {
        'title': 'Railway Recruitment 2026',
        'blog_article': 'Check freejobalert for updates on railway jobs.',
        'job_url': 'https://www.freejobalert.com/article/123',
        'pdf_url': 'https://railways.gov.in/notification.pdf',
        'how_to_apply': 'Visit the official website'
    }
    
    is_valid, errors, cleaned = validate_job_content(test_job)
    
    print(f"Valid: {is_valid}")
    print(f"Errors: {errors}")
    print(f"\nCleaned blog_article: {cleaned['blog_article'][:60]}...")
    print(f"Cleaned job_url: {cleaned['job_url']}")
    print(f"PDF URL (unchanged): {cleaned['pdf_url']}")
    
    # Test 3: Sanitize for database
    print("\n" + "-"*60)
    print("Test 3: Sanitizing for database insert\n")
    
    sanitized = sanitize_job_data(test_job)
    print("Sanitized data ready for insertion:")
    print(f"  - Title: {sanitized['title']}")
    print(f"  - Blog (cleaned): {sanitized['blog_article'][:50]}...")
    print(f"  - Job URL (cleaned): {sanitized['job_url']}")
    print(f"  - PDF URL: {sanitized['pdf_url']}")
    
    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60 + "\n")
