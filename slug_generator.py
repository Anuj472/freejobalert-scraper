"""Generate deterministic slugs for job postings.

Slug format: <job_title>-<organization>-<random_suffix>
Example: assistant-professor-iit-delhi-abc123
"""

import re
import hashlib
import logging

logger = logging.getLogger(__name__)

def generate_slug(job_title: str, organization: str, job_id: str = None) -> str:
    """
    Generate a deterministic URL-friendly slug from job title and organization.
    
    Args:
        job_title: Job title/post name
        organization: Organization/recruitment board name
        job_id: Optional unique job identifier for hash (e.g., UUID or details_url)
    
    Returns:
        URL-safe slug string
    """
    if not job_title or not organization:
        logger.warning("Cannot generate slug: missing job_title or organization")
        return None
    
    # Clean and normalize title
    title_clean = _slugify(job_title)
    
    # Clean and normalize organization
    org_clean = _slugify(organization)
    
    # Combine title + org
    base_slug = f"{title_clean}-{org_clean}"
    
    # Add deterministic suffix based on job_id to ensure uniqueness
    if job_id:
        # Use first 6 chars of SHA256 hash for deterministic suffix
        hash_obj = hashlib.sha256(job_id.encode('utf-8'))
        suffix = hash_obj.hexdigest()[:6]
        base_slug = f"{base_slug}-{suffix}"
    
    # Truncate if too long (max 100 chars recommended for URLs)
    if len(base_slug) > 100:
        base_slug = base_slug[:100]
    
    # Remove trailing hyphens
    base_slug = base_slug.rstrip('-')
    
    return base_slug

def _slugify(text: str) -> str:
    """
    Convert text to URL-friendly slug.
    
    Steps:
    1. Convert to lowercase
    2. Remove special characters
    3. Replace spaces with hyphens
    4. Remove consecutive hyphens
    """
    # Convert to lowercase
    text = text.lower()
    
    # Remove content in parentheses (e.g., "IIT (Indian Institute of Technology)" -> "IIT")
    text = re.sub(r'\([^)]*\)', '', text)
    
    # Remove special characters except spaces and hyphens
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Replace spaces with hyphens
    text = text.replace(' ', '-')
    
    # Remove consecutive hyphens
    text = re.sub(r'-+', '-', text)
    
    # Strip leading/trailing hyphens
    text = text.strip('-')
    
    return text

def validate_slug(slug: str) -> bool:
    """
    Validate if a slug is properly formatted.
    
    Valid slug:
    - Contains only lowercase letters, numbers, and hyphens
    - No consecutive hyphens
    - No leading/trailing hyphens
    """
    if not slug:
        return False
    
    # Check format
    pattern = r'^[a-z0-9]+(-[a-z0-9]+)*$'
    return bool(re.match(pattern, slug))
