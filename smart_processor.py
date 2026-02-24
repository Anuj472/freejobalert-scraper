# smart_processor.py
# Pipeline: HTML scrape -> extract links from table -> upload freejobalert PDFs to Drive
#           -> PDF text OR raw HTML text -> LLM -> merge -> blog -> Supabase

import logging
import re
from typing import Optional

from gemma_processor import GemmaProcessor, extract_pdf_text

try:
    from gdrive_uploader import GoogleDriveUploader
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False
    logging.warning("GoogleDriveUploader not available - freejobalert PDFs won't be uploaded")

logger = logging.getLogger("smart_processor")
SEP = "=" * 60

# Link fields that come only from HTML parsing — LLM output never overwrites these
HTML_AUTHORITATIVE_FIELDS = {"apply_url", "pdf_url", "official_website"}


class SmartJobProcessor:
    """
    Orchestrates the full extraction pipeline for a single FreeJobAlert job page.

    Pipeline:
      STEP 1  Extract link fields from HTML table (authoritative source)
              - If PDF is hosted on freejobalert.com → upload to Google Drive
      STEP 2  If PDF found → extract PDF text; else use raw HTML text
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
        self.gdrive_uploader = GoogleDriveUploader() if GDRIVE_AVAILABLE else None

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
            job_listing:   Basic metadata from listing page
                           (title, organization, vacancies, last_date, etc.).
            html_content:  Raw HTML string of the job detail article page.
            details_url:   The article URL (stored as freejobalert_url).

        Returns:
            Merged job dict ready for Supabase insertion, or None on failure.
        """
        if job_listing is None:
            job_listing = {}

        # ── STEP 1: Extract links from HTML table ─────────────────────────────
        logger.info(SEP)
        logger.info("STEP 1: Extracting ONLY links from HTML table...")
        html_links = _extract_links_from_html(html_content)

        # Handle freejobalert-hosted PDFs → upload to Google Drive
        if html_links.get("pdf_url"):
            pdf_url = html_links["pdf_url"]
            logger.info(f"✓ PDF found: {pdf_url[:70]}...")

            if "freejobalert" in pdf_url.lower() and self.gdrive_uploader:
                logger.info("   → PDF hosted on freejobalert.com, uploading to Google Drive...")
                try:
                    job_title = job_listing.get("title", "Unknown Job")
                    drive_link = self.gdrive_uploader.upload_pdf_from_url(
                        pdf_url,
                        job_title=job_title
                    )
                    if drive_link:
                        logger.info(f"   ✓ Uploaded to Drive: {drive_link[:60]}...")
                        html_links["pdf_url"] = drive_link  # Replace with Drive link
                    else:
                        logger.warning("   ⚠️  Drive upload failed, keeping original link")
                except Exception as e:
                    logger.error(f"   ❌ Drive upload error: {e}")
                    # Keep original freejobalert link if upload fails
            else:
                logger.info("   → External PDF (not freejobalert), keeping original link")
        else:
            logger.info("ℹ️  No PDF link found")

        if html_links.get("apply_url"):
            logger.info(f"✓ Apply Online: {html_links['apply_url'][:60]}...")
        else:
            logger.warning("⚠️  Apply Online link not found")

        if html_links.get("official_website"):
            logger.info(f"✓ Official Website: {html_links['official_website'][:60]}...")

        # ── STEP 2: Prepare content for LLM ───────────────────────────────────
        logger.info(SEP)
        llm_content: Optional[str] = None
        content_label = "HTML Text"

        # Use the potentially updated pdf_url (Drive link if uploaded)
        final_pdf_url = html_links.get("pdf_url")
        if final_pdf_url:
            logger.info("🗞  SCENARIO: PDF Found")
            logger.info("STEP 2: Downloading PDF and extracting text for LLM...")
            logger.info(f"PDF URL: {final_pdf_url[:80]}...")
            pdf_text = extract_pdf_text(final_pdf_url)
            if pdf_text:
                llm_content = pdf_text
                content_label = "PDF Text"
                logger.info(f"✓ Using PDF text ({len(pdf_text)} chars)")
            else:
                logger.warning(
                    "⚠️  PDF text extraction failed, falling back to HTML text..."
                )

        if llm_content is None:
            logger.info(SEP)
            logger.info("📄 SCENARIO: NO PDF or PDF extraction failed")
            logger.info("STEP 3: Extracting raw text from HTML and giving to LLM...")
            llm_content = _extract_raw_text(html_content)
            logger.info(f"Raw text length: {len(llm_content)} chars")

        # ── STEP 3: LLM field extraction ───────────────────────────────────────
        logger.info(SEP)
        llm_fields = self.llm.extract_fields(llm_content, content_label)

        if llm_fields:
            logger.info(f"✓ LLM extracted ALL fields from {content_label}")
            logger.info(f"   Extracted {len(llm_fields)} fields")
        else:
            logger.error("❌ LLM extraction failed!")

        # ── STEP 4: Merge ──────────────────────────────────────────────────────
        logger.info(SEP)
        logger.info("STEP 4: Merging data...")

        # Seed with listing-level metadata from the scraper
        merged: dict = {
            "title":        job_listing.get("title"),
            "organization": job_listing.get("organization"),
            "vacancies":    job_listing.get("vacancies"),
            "last_date":    job_listing.get("last_date"),
            "qualification": job_listing.get("qualification"),
        }
        # Remove None seeds so LLM values fill them
        merged = {k: v for k, v in merged.items() if v is not None}

        # Carry forward freejobalert_url if provided
        if details_url:
            merged["freejobalert_url"] = details_url

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

        # ── STEP 5: SEO blog generation ────────────────────────────────────────
        logger.info(SEP)
        logger.info("🤖 Generating SEO blog...")
        blog = self.llm.generate_blog(merged)
        if blog:
            merged["blog"] = blog
            logger.info(f"✓ Blog generated ({len(blog)} chars)")
        else:
            logger.warning("⚠️  Blog generation failed")

        return merged


# Backward-compatible alias (in case anything imports SmartProcessor)
SmartProcessor = SmartJobProcessor


# ─── HELPERS ─────────────────────────────────────────────────────────────────────

def _extract_links_from_html(html: str) -> dict:
    """
    Extract apply_url, pdf_url, official_website from FreeJobAlert HTML.

    FreeJobAlert pages have an "Important Links" table at the bottom with rows:
      - "Official Notification PDF" → <a href="...">Click here</a>
      - "Apply Online" → <a href="...">Click here</a>
      - "Official Website" → <a href="...">Click here</a>

    This function scans all tables looking for these exact labels and extracts
    the corresponding href values.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = {"apply_url": None, "pdf_url": None, "official_website": None}

    # Label patterns (case-insensitive)
    pdf_labels = ["official notification pdf", "notification pdf", "download notification"]
    apply_labels = ["apply online", "online application", "registration link"]
    website_labels = ["official website", "official site", "website link"]

    # Find all tables
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            # First cell = label, second cell = value with link
            label_cell = cells[0]
            value_cell = cells[1]

            label_text = label_cell.get_text(strip=True).lower()

            # Find the <a> tag in the value cell
            link_tag = value_cell.find("a", href=True)
            if not link_tag:
                continue

            href = link_tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue

            # Match against label patterns
            if not links["pdf_url"]:
                for pattern in pdf_labels:
                    if pattern in label_text:
                        links["pdf_url"] = href
                        break

            if not links["apply_url"]:
                for pattern in apply_labels:
                    if pattern in label_text:
                        # Only accept if it points outside freejobalert domain
                        if "freejobalert" not in href.lower():
                            links["apply_url"] = href
                        break

            if not links["official_website"]:
                for pattern in website_labels:
                    if pattern in label_text:
                        links["official_website"] = href
                        break

    # Fallback: scan all <a> tags if table extraction failed
    if not any(links.values()):
        logger.debug("No links found in tables, falling back to scanning all <a> tags")
        apply_re = re.compile(r'apply[\s_-]?online|apply[\s_-]?now|register', re.I)
        pdf_re = re.compile(r'\.pdf(\?.*)?$', re.I)
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
    logger.info("📦 FINAL DATA SUMMARY:")
    logger.info(f"   Source: {data.get('data_source')}")
    logger.info(f"   Title: {str(data.get('title', ''))[:50]}...")
    logger.info(f"   Organization: {str(data.get('organization', ''))[:30]}...")
    for field in ["category", "qualification", "vacancies", "apply_url", "pdf_url"]:
        val = data.get(field)
        if val:
            logger.info(f"   ✓ {field.replace('_', ' ').title()}: {str(val)[:50]}...")
    logger.info(SEP)
