# smart_processor.py
# Pipeline: HTML scrape -> extract links -> PDF text OR raw HTML text
#           -> LLM extraction -> merge (HTML links authoritative) -> blog -> Supabase

import logging
from typing import Optional

from gemma_processor import GemmaProcessor, extract_pdf_text

logger = logging.getLogger("smart_processor")
SEP = "=" * 60

# Link fields that come only from HTML parsing — LLM output never overwrites these
HTML_AUTHORITATIVE_FIELDS = {"apply_url", "pdf_url", "official_website"}


class SmartProcessor:
    """
    Orchestrates the full extraction pipeline for a single FreeJobAlert job page.

    Pipeline:
      STEP 1  Extract link fields from HTML (authoritative source)
      STEP 2  If PDF found -> extract PDF text; else use raw HTML text
      STEP 3  Send content to LLM for all non-link fields
      STEP 4  Merge: HTML links win, LLM fills everything else
      STEP 5  Generate 9000-char SEO blog
    """

    def __init__(
        self,
        model: str = "gemma3:12b",
        ollama_url: str = "http://localhost:11434",
    ):
        self.llm = GemmaProcessor(model=model, base_url=ollama_url)

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def process(
        self,
        html_content: str,
        job_listing: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Process a single job page.

        Args:
            html_content:  Raw HTML string of the FreeJobAlert article page.
            job_listing:   Optional dict with pre-scraped metadata from the
                           listing page (title, organization, vacancies, etc.).

        Returns:
            Merged job dict ready for Supabase insertion, or None on failure.
        """
        if job_listing is None:
            job_listing = {}

        # ── STEP 1: Extract links from HTML ──────────────────────────────────
        logger.info(SEP)
        logger.info("STEP 1: Extracting ONLY links from HTML...")
        html_links = _extract_links_from_html(html_content)

        if html_links.get("apply_url"):
            logger.info(f"\u2713 Apply Online (context): {html_links['apply_url'][:60]}...")
        else:
            logger.warning("\u26a0\ufe0f  Apply Online link not found")

        if html_links.get("pdf_url"):
            logger.info(f"\u2713 PDF: {html_links['pdf_url'][:60]}...")
        else:
            logger.info("\u2139\ufe0f  No PDF link found")

        if html_links.get("official_website"):
            logger.info(f"\u2713 Official Website: {html_links['official_website'][:60]}...")

        # ── STEP 2: Prepare content for LLM ──────────────────────────────────
        logger.info(SEP)
        llm_content: Optional[str] = None
        content_label = "HTML Text"

        if html_links.get("pdf_url"):
            logger.info("\U0001f9de  SCENARIO: PDF Found")
            logger.info("STEP 2: Downloading PDF and giving to LLM... ")
            logger.info(f"PDF URL: {html_links['pdf_url'][:80]}...")
            pdf_text = extract_pdf_text(html_links["pdf_url"])
            if pdf_text:
                llm_content = pdf_text
                content_label = "PDF Text"
                logger.info(f"\u2713 Using PDF text ({len(pdf_text)} chars)")
            else:
                logger.warning(
                    "\u26a0\ufe0f  PDF extraction failed, falling back to HTML text..."
                )

        if llm_content is None:
            logger.info(SEP)
            logger.info("\U0001f4c4 SCENARIO: NO PDF or PDF failed")
            logger.info("STEP 3: Extracting raw text from HTML and giving to LLM...")
            llm_content = _extract_raw_text(html_content)
            logger.info(f"Raw text length: {len(llm_content)} chars")

        # ── STEP 3: LLM field extraction ──────────────────────────────────────
        logger.info(SEP)
        llm_fields = self.llm.extract_fields(llm_content, content_label)

        if llm_fields:
            logger.info(f"\u2713 LLM extracted ALL fields from {content_label}")
            logger.info(f"   Extracted {len(llm_fields)} fields")
        else:
            logger.error("\u274c LLM extraction failed!")

        # ── STEP 4: Merge ─────────────────────────────────────────────────────
        logger.info(SEP)
        logger.info("STEP 4: Merging data...")

        # Seed with listing-level metadata (from scraper / FreeJobAlert listing)
        merged: dict = {
            "title":        job_listing.get("title"),
            "organization": job_listing.get("organization"),
            "vacancies":    job_listing.get("vacancies"),
        }
        # Remove None seeds so LLM can fill them
        merged = {k: v for k, v in merged.items() if v is not None}

        # Layer in LLM output for all non-link fields
        if llm_fields:
            for key, value in llm_fields.items():
                if key not in HTML_AUTHORITATIVE_FIELDS and value:
                    merged[key] = value

        # HTML links are always authoritative — overwrite whatever LLM said
        for field in HTML_AUTHORITATIVE_FIELDS:
            val = html_links.get(field)
            if val:
                merged[field] = val

        # Tag data source for audit
        if content_label == "PDF Text" and llm_fields:
            merged["data_source"] = "pdf_gemma3"
        elif llm_fields:
            merged["data_source"] = "html_gemma3"
        else:
            merged["data_source"] = "html_only"

        _log_summary(merged)

        # ── STEP 5: SEO blog generation ───────────────────────────────────────
        logger.info(SEP)
        logger.info("\U0001f916 Generating SEO blog...")
        blog = self.llm.generate_blog(merged)
        if blog:
            merged["blog"] = blog
            logger.info(f"\u2713 Blog generated ({len(blog)} chars)")
        else:
            logger.warning("\u26a0\ufe0f  Blog generation failed")

        return merged


# ─── HELPERS ────────────────────────────────────────────────────────────────────

def _extract_links_from_html(html: str) -> dict:
    """
    Extract apply_url, pdf_url, official_website from raw HTML.
    HTML is the single source of truth for link fields.
    """
    from bs4 import BeautifulSoup
    import re

    soup = BeautifulSoup(html, "html.parser")
    links = {"apply_url": None, "pdf_url": None, "official_website": None}

    apply_re   = re.compile(r'apply[\s_-]?online|apply[\s_-]?now|apply[\s_-]?here|register\s+now', re.I)
    pdf_re     = re.compile(r'\.pdf(\?.*)?$', re.I)
    official_re = re.compile(r'official[\s_-]?(website|site|link|notification)', re.I)

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        text = tag.get_text(strip=True)

        if not href or href.startswith("#") or href.startswith("javascript"):
            continue

        # PDF link
        if pdf_re.search(href) and not links["pdf_url"]:
            links["pdf_url"] = href

        # Apply Online link (must point outside FreeJobAlert)
        elif apply_re.search(text) and not links["apply_url"]:
            if href.startswith("http") and "freejobalert" not in href.lower():
                links["apply_url"] = href

        # Official website
        elif official_re.search(text) and not links["official_website"]:
            if href.startswith("http"):
                links["official_website"] = href

    return links


def _extract_raw_text(html: str) -> str:
    """Extract clean plain text from HTML, stripping nav/footer noise."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    lines = [
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    ]
    return "\n".join(lines)


def _log_summary(data: dict) -> None:
    logger.info(SEP)
    logger.info("\U0001f4e6 FINAL DATA SUMMARY:")
    logger.info(f"   Source: {data.get('data_source')}")
    logger.info(f"   Title: {str(data.get('title', ''))[:50]}...")
    logger.info(f"   Organization: {str(data.get('organization', ''))[:30]}...")
    for field in ["category", "qualification", "vacancies", "apply_url", "pdf_url"]:
        val = data.get(field)
        if val:
            logger.info(f"   \u2713 {field.replace('_', ' ').title()}: {str(val)[:50]}...")
    logger.info(SEP)
