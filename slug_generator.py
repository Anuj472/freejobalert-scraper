"""Generate URL-friendly slugs for job postings.

CRITICAL: The algorithm here MUST stay in sync with createSlug() in
          freegovtjobinfo2 / components/JobCard.tsx.

Frontend reference (JobCard.tsx):

    const createSlug = (title: string, organization: string): string => {
      const combined = `${title} ${organization}`
        .toLowerCase()
        .replace(/[^a-z0-9\\s-]/g, '')   // remove special chars
        .replace(/\\s+/g, '-')            // spaces  → hyphens
        .replace(/-+/g, '-')             // multiple hyphens → single
        .trim()
        .substring(0, 150);              // 150-char max
      return combined;
    };

    // usage: job.slug || createSlug(job.title, job.organization)

Why this matters
----------------
The frontend uses `job.slug` from the DB first.  When that is NULL (e.g.
legacy records), it falls back to createSlug() and then does:

    supabase.from('jobs').select('*').eq('slug', slug).single()

If the DB slug was generated with a different algorithm (e.g. a hash suffix)
the fallback URL will never resolve — the page returns 404.

Uniqueness strategy
-------------------
Instead of a deterministic hash suffix (which the frontend can’t reproduce),
uniqueness is handled by the caller (supabase_client._ensure_unique_slug):
  • Base slug is tried first   →  matches createSlug() exactly
  • If already taken           →  append -2, -3, …
This keeps the primary slug identical to what the frontend generates.
"""

import re
import logging

logger = logging.getLogger(__name__)


def generate_slug(job_title: str, organization: str, job_id: str = None) -> str:
    """
    Generate a URL slug that exactly matches the frontend’s createSlug().

    Args:
        job_title    : Job title string.
        organization : Organization name string.
        job_id       : Accepted for backward-compatibility but ignored.
                       Uniqueness is handled by supabase_client._ensure_unique_slug().

    Returns:
        Slug string (max 150 chars), or None if inputs are missing.
    """
    if not job_title or not organization:
        logger.warning("Cannot generate slug: missing job_title or organization")
        return None

    # Step 1: combine exactly as frontend does
    combined = f"{job_title} {organization}"

    # Step 2: lowercase
    combined = combined.lower()

    # Step 3: remove everything except a-z, 0-9, spaces, hyphens
    #         (mirrors JS: .replace(/[^a-z0-9\s-]/g, ''))
    combined = re.sub(r'[^a-z0-9\s-]', '', combined)

    # Step 4: one or more whitespace chars → single hyphen
    #         (mirrors JS: .replace(/\s+/g, '-'))
    combined = re.sub(r'\s+', '-', combined)

    # Step 5: collapse multiple consecutive hyphens
    #         (mirrors JS: .replace(/-+/g, '-'))
    combined = re.sub(r'-+', '-', combined)

    # Step 6: trim leading / trailing hyphens
    #         (mirrors JS: .trim()  — JS trim only removes whitespace, but
    #          after step 3-4 leading/trailing chars can only be hyphens)
    combined = combined.strip('-')

    # Step 7: max 150 chars  (mirrors JS: .substring(0, 150))
    combined = combined[:150]

    return combined if combined else None


def validate_slug(slug: str) -> bool:
    """
    Validate that a slug is properly formatted.

    Valid slug: lowercase letters, digits, and hyphens only;
    no leading/trailing hyphens; no consecutive hyphens.
    """
    if not slug:
        return False
    return bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', slug))
