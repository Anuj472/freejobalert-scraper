# smart_processor.py
# Pipeline: HTML scrape -> extract links from table -> MUST upload freejobalert PDFs to Drive
#           -> PDF text OR raw HTML text -> LLM -> merge -> blog -> Supabase

import logging
import re
from typing import Optional

from gemma_processor import GemmaProcessor, extract_pdf_text
from gdrive_uploader import GoogleDriveUploader

logger = logging.getLogger("smart_processor")
SEP = "=" * 60

# Link fields that come only from HTML parsing — LLM output never overwrites these
HTML_AUTHORITATIVE_FIELDS = {"apply_url", "pdf_url", "official_website"}


class SmartJobProcessor:
    """
    Orchestrates the full extraction pipeline for a single FreeJobAlert job page.

    Pipeline:
      STEP 1  Extract link fields from HTML table (authoritative source)
              - If PDF is hosted on freejobalert.com → MUST upload to Google Drive
      STEP 2  If PDF found → extract PDF text (with page Referer header);
              else use raw HTML text
      STEP 3  Send content to LLM for all non-link fields
      STEP 4  Merge: HTML links win, LLM fills everything else
      STEP 5  Generate 9000-char SEO blog

    Note: Google Drive upload is MANDATORY for freejobalert-hosted PDFs.
          Jobs with freejobalert PDFs will be skipped if Drive unavailable.
    """

    def __init__(
        self,
        model: str = "gemma3:12b",
        ollama_url: str = "http://localhost:11434",
    ):
        self.llm = GemmaProcessor(model=model, base_url=ollama_url)

        # Initialize Google Drive uploader (REQUIRED)
        self.gdrive_uploader = GoogleDriveUploader()
        logger.info("\u2713 SmartJobProcessor initialized with Google Drive support")

    # -------------------------------------------------------------------------
    # Public entry point  (matches scraper.py call signature)
    # -------------------------------------------------------------------------

    def process_job(
        self,
        job_listing: dict,
        html_content: str,
        details_url: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Process a single FreeJobAlert job page.

        Args:
            job_listing:   Basic metadata from listing page.
            html_content:  Raw HTML string of the job detail article page.
            details_url:   The article URL (stored as freejobalert_url).
                           Also used as the HTTP Referer when downloading PDFs
                           so government servers accept the request.

        Returns:
            Merged job dict ready for Supabase insertion, or None on failure.
        """
        if job_listing is None:
            job_listing = {}

        # ── STEP 1: Extract links from HTML table ─────────────────────────────────
        logger.info(SEP)
        logger.info("STEP 1: Extracting ONLY links from HTML table...")
        html_links = _extract_links_from_html(html_content)

        # Handle freejobalert-hosted PDFs → MUST upload to Google Drive
        if html_links.get("pdf_url"):
            pdf_url = html_links["pdf_url"]
            logger.info(f"\u2713 PDF found: {pdf_url[:70]}...")

            if "freejobalert" in pdf_url.lower():
                logger.info("   \u2192 PDF hosted on freejobalert.com (MUST upload to Google Drive)")
                try:
                    job_title = job_listing.get("title", "Unknown Job")
                    drive_link = self.gdrive_uploader.upload_pdf_from_url(
                        pdf_url, job_title=job_title
                    )
                    if drive_link:
                        logger.info(f"   \u2713 Uploaded to Drive: {drive_link[:60]}...")
                        html_links["pdf_url"] = drive_link
                    else:
                        logger.error("   \u274c CRITICAL: Drive upload failed for freejobalert PDF")
                        logger.error("   \u2192 Skipping this job (freejobalert PDFs MUST be on Drive)")
                        return None
                except Exception as e:
                    logger.error(f"   \u274c CRITICAL: Drive upload error: {e}")
                    logger.error("   \u2192 Skipping this job (freejobalert PDFs MUST be on Drive)")
                    return None
            else:
                logger.info("   \u2192 External PDF (not freejobalert), keeping original link")
        else:
            logger.info("\u2139\ufe0f  No PDF link found")

        if html_links.get("apply_url"):
            logger.info(f"\u2713 Apply Online: {html_links['apply_url'][:60]}...")
        else:
            logger.warning("\u26a0\ufe0f  Apply Online link not found")

        if html_links.get("official_website"):
            logger.info(f"\u2713 Official Website: {html_links['official_website'][:60]}...")

        # ── STEP 2: Prepare content for LLM ───────────────────────────────────────
        logger.info(SEP)
        llm_content: Optional[str] = None
        content_label = "HTML Text"

        final_pdf_url = html_links.get("pdf_url")
        if final_pdf_url:
            logger.info("\U0001f5de  SCENARIO: PDF Found")
            logger.info("STEP 2: Downloading PDF and extracting text for LLM...")
            logger.info(f"PDF URL: {final_pdf_url[:80]}...")

            # Pass the FreeJobAlert article URL as HTTP Referer.
            # Many Indian government servers check Referer and refuse connections
            # (ECONNREFUSED) if the request looks like a direct / bot download.
            pdf_text = extract_pdf_text(
                final_pdf_url,
                referer=details_url or "https://www.freejobalert.com/",
            )

            if pdf_text:
                llm_content = pdf_text
                content_label = "PDF Text"
                logger.info(f"\u2713 Using PDF text ({len(pdf_text)} chars)")
            else:
                logger.warning(
                    "\u26a0\ufe0f  PDF text extraction failed, falling back to HTML text..."
                )

        if llm_content is None:
            logger.info(SEP)
            logger.info("\U0001f4c4 SCENARIO: NO PDF or PDF extraction failed")
            logger.info("STEP 3: Extracting raw text from HTML and giving to LLM...")
            llm_content = _extract_raw_text(html_content)
            logger.info(f"Raw text length: {len(llm_content)} chars")

        # ── STEP 3: LLM field extraction ────────────────────────────────────────
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

        merged: dict = {
            "title":         job_listing.get("title"),
            "organization":  job_listing.get("organization"),
            "vacancies":     job_listing.get("vacancies"),
            "last_date":     job_listing.get("last_date"),
            "qualification": job_listing.get("qualification"),
        }
        merged = {k: v for k, v in merged.items() if v is not None}

        if details_url:
            merged["freejobalert_url"] = details_url

        if llm_fields:
            for key, value in llm_fields.items():
                if key not in HTML_AUTHORITATIVE_FIELDS and value:
                    merged[key] = value

        for field in HTML_AUTHORITATIVE_FIELDS:
            val = html_links.get(field)
            if val:
                merged[field] = val

        if content_label == "PDF Text" and llm_fields:
            merged["data_source"] = "pdf_gemma3"
        elif llm_fields:
            merged["data_source"] = "html_gemma3"
        else:
            merged["data_source"] = "html_only"

        _log_summary(merged)

        # ── STEP 5: SEO blog generation ─────────────────────────────────────────
        logger.info(SEP)
        logger.info("\U0001f916 Generating SEO blog...")
        blog = self.llm.generate_blog(merged)
        if blog:
            merged["blog"] = blog
            logger.info(f"\u2713 Blog generated ({len(blog)} chars)")
        else:
            logger.warning("\u26a0\ufe0f  Blog generation failed")

        return merged


# Backward-compatible alias
SmartProcessor = SmartJobProcessor


# ─── HELPERS ───────────────────────────────────────────────────────────────────────────────────

def _extract_links_from_html(html: str) -> dict:
    """
    Extract apply_url, pdf_url, official_website from FreeJobAlert HTML.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = {"apply_url": None, "pdf_url": None, "official_website": None}

    pdf_labels     = ["official notification pdf", "notification pdf", "download notification"]
    apply_labels   = ["apply online", "online application", "registration link"]
    website_labels = ["official website", "official site", "website link"]

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label_text = cells[0].get_text(strip=True).lower()
            link_tag   = cells[1].find("a", href=True)
            if not link_tag:
                continue

            href = link_tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue

            if not links["pdf_url"]:
                for pattern in pdf_labels:
                    if pattern in label_text:
                        links["pdf_url"] = href
                        break

            if not links["apply_url"]:
                for pattern in apply_labels:
                    if pattern in label_text:
                        if "freejobalert" not in href.lower():
                            links["apply_url"] = href
                        break

            if not links["official_website"]:
                for pattern in website_labels:
                    if pattern in label_text:
                        links["official_website"] = href
                        break

    # Fallback: scan all <a> tags
    if not any(links.values()):
        logger.debug("No links found in tables, scanning all <a> tags")
        apply_re   = re.compile(r'apply[\s_-]?online|apply[\s_-]?now|register', re.I)
        pdf_re     = re.compile(r'\.pdf(\?.*)?$', re.I)
        official_re = re.compile(r'official[\s_-]?(website|site)', re.I)

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            text = tag.get_text(strip=True)
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue

            if pdf_re.search(href) and not links["pdf_url"]:
                links["pdf_url"] = href
            elif apply_re.search(text) and not links["apply_url"]:
                if href.startswith("http") and "freejobalert" not in href.lower():
                    links["apply_url"] = href
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
