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
        model: str = "gemma4:12b",
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
                logger.info("   → PDF hosted on freejobalert.com — downloading and uploading to Google Drive...")
                try:
                    job_title = job_listing.get("title", "Unknown Job")
                    drive_link = self.gdrive_uploader.upload_pdf_from_url(
                        pdf_url, job_title=job_title
                    )
                    if drive_link:
                        logger.info(f"   ✓ Uploaded to Drive: {drive_link[:60]}...")
                        html_links["pdf_url"] = drive_link
                    else:
                        logger.warning("   ⚠️  Drive upload failed — job will be saved without pdf_url")
                        html_links["pdf_url"] = None
                except Exception as e:
                    logger.warning(f"   ⚠️  Drive upload error: {e} — job will be saved without pdf_url")
                    html_links["pdf_url"] = None
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

        # ── STEP 3: Sanitize content before LLM (strip all freejobalert refs) ─
        logger.info(SEP)
        original_len = len(llm_content)
        llm_content = _sanitize_for_llm(llm_content)
        stripped = original_len - len(llm_content)
        if stripped > 0:
            logger.info(f"✓ Sanitized content: removed {stripped} chars of freejobalert references")

        # ── STEP 4 (old 3): LLM field extraction ────────────────────────────────
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
            merged["data_source"] = "pdf_gemma4"
        elif llm_fields:
            merged["data_source"] = "html_gemma4"
        else:
            merged["data_source"] = "html_only"

        _log_summary(merged)

        # ── STEP 5: SEO blog generation ─────────────────────────────────────────
        logger.info(SEP)
        logger.info("🤖 Generating SEO blog...")
        # Sanitize merged data before passing to blog generator
        sanitized_for_blog = {k: _sanitize_for_llm(str(v)) if isinstance(v, str) else v
                              for k, v in merged.items()}
        blog = self.llm.generate_blog(sanitized_for_blog)
        if blog:
            merged["blog_article"] = blog
            logger.info(f"✓ Blog generated ({len(blog)} chars)")

            # ── Parse FAQs from blog HTML if LLM didn't return them ───────────
            if not merged.get("faqs"):
                merged["faqs"] = _extract_faqs_from_blog(blog)
                if merged["faqs"]:
                    logger.info(f"✓ Extracted {len(merged['faqs'])} FAQs from blog")

            # ── Parse highlights from blog HTML if LLM didn't return them ─────
            if not merged.get("highlights"):
                merged["highlights"] = _extract_highlights_from_blog(blog)
                if merged["highlights"]:
                    logger.info(f"✓ Extracted {len(merged['highlights'])} highlights from blog")
        else:
            logger.warning("⚠️  Blog generation failed")

        # ── STEP 6: Verify — purge any freejobalert leakage from all fields ───
        fja_count = _verify_no_fja(merged)
        if fja_count:
            logger.info(f"✓ Post-LLM verification: removed freejobalert from {fja_count} field(s)")
        else:
            logger.info("✓ Post-LLM verification passed — no freejobalert references found")

        # ── Auto-generate seo_title / meta_description if still missing ───────
        if not merged.get("seo_title") and merged.get("title") and merged.get("organization"):
            merged["seo_title"] = f"{merged['title'][:45]} – {merged['organization'][:14]}"[:60]
        if not merged.get("meta_description") and merged.get("title") and merged.get("organization"):
            merged["meta_description"] = (
                f"Apply for {merged['title']} at {merged['organization']}. "
                f"Check eligibility, vacancies, and last date."
            )[:150]

        return merged


# Backward-compatible alias
SmartProcessor = SmartJobProcessor


# ─── HELPERS ───────────────────────────────────────────────────────────────────────────────────

def _extract_links_from_html(html: str) -> dict:
    """
    Extract apply_url, pdf_url, official_website from FreeJobAlert HTML.

    Apply links on freejobalert.com are often wrapped in a freejobalert
    redirect/tracking URL (e.g. /go/org-name). We follow that redirect once
    to get the real destination URL.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = {"apply_url": None, "pdf_url": None, "official_website": None}

    pdf_labels = [
        "official notification pdf", "notification pdf",
        "download notification", "download pdf", "official advt",
    ]
    apply_labels = [
        "apply online", "online application", "registration link",
        "apply now", "click here to apply", "online apply",
        "apply",  # catch-all — matched last so it doesn't overlap
    ]
    website_labels = ["official website", "official site", "website link"]

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label_text = cells[0].get_text(strip=True).lower()

            # Collect ALL links in the value cell, not just the first one
            all_links = cells[1].find_all("a", href=True)
            if not all_links:
                continue

            for link_tag in all_links:
                href = link_tag["href"].strip()
                if not href or href.startswith("#") or href.startswith("javascript"):
                    continue

                # PDF link
                if not links["pdf_url"]:
                    for pattern in pdf_labels:
                        if pattern in label_text:
                            links["pdf_url"] = href
                            break

                # Apply Online link
                if not links["apply_url"]:
                    for pattern in apply_labels:
                        if pattern in label_text:
                            apply_href = _resolve_apply_url(href)
                            if apply_href:
                                links["apply_url"] = apply_href
                                logger.info(f"✓ Apply link resolved: {apply_href[:60]}...")
                            break

                # Official website
                if not links["official_website"]:
                    for pattern in website_labels:
                        if pattern in label_text:
                            links["official_website"] = href
                            break

    # ── Structure 2: <ul><li><strong>Label</strong>: <a href="...">...</a></li></ul> ──
    # FreeJobAlert also uses this structure (e.g. "MRVC Important Links" section)
    if not links["apply_url"] or not links["pdf_url"] or not links["official_website"]:
        for li in soup.find_all("li"):
            strong = li.find("strong")
            if not strong:
                continue

            label_text = strong.get_text(strip=True).lower().rstrip(":").strip()
            link_tag = li.find("a", href=True)
            if not link_tag:
                continue

            href = link_tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue

            if not links["pdf_url"]:
                for pattern in pdf_labels:
                    if pattern in label_text:
                        links["pdf_url"] = href
                        logger.info(f"✓ PDF found (li/strong): {href[:70]}...")
                        break

            if not links["apply_url"]:
                for pattern in apply_labels:
                    if pattern in label_text:
                        resolved = _resolve_apply_url(href)
                        if resolved:
                            links["apply_url"] = resolved
                            logger.info(f"✓ Apply Online (li/strong): {resolved[:70]}...")
                        break

            if not links["official_website"]:
                for pattern in website_labels:
                    if pattern in label_text:
                        links["official_website"] = href
                        logger.info(f"✓ Official website (li/strong): {href[:70]}...")
                        break

    # ── Fallback: scan ALL <a> tags for any links still missing ──────────────
    if not links["apply_url"] or not links["pdf_url"] or not links["official_website"]:
        logger.debug("Scanning all <a> tags for missing links...")
        apply_re    = re.compile(r'apply[\s_-]?(online|now)|register\s*(now|here)?|click\s*here', re.I)
        pdf_re      = re.compile(r'\.pdf(\?.*)?$', re.I)
        official_re = re.compile(r'official[\s_-]?(website|site)', re.I)

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            text = tag.get_text(strip=True)
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue

            if pdf_re.search(href) and not links["pdf_url"]:
                links["pdf_url"] = href
            elif apply_re.search(text) and not links["apply_url"]:
                resolved = _resolve_apply_url(href)
                if resolved:
                    links["apply_url"] = resolved
            elif official_re.search(text) and not links["official_website"]:
                if href.startswith("http"):
                    links["official_website"] = href

    return links


def _resolve_apply_url(href: str) -> Optional[str]:
    """
    Validate an apply or official website URL.

    Apply Online and Official Website links on FreeJobAlert pages are ALWAYS
    direct external URLs — they are never freejobalert.com intermediate
    redirects. So we simply accept external links and reject any
    freejobalert.com URL (which is a page link, not an apply/official link).
    """
    if not href or not href.startswith("http"):
        return None

    # Not a freejobalert link at all — always a valid external link
    if "freejobalert" not in href.lower():
        return href

    # Any freejobalert.com URL == not a real apply/official link
    return None


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


def _extract_faqs_from_blog(blog_html: str) -> list:
    """
    Parse FAQ Q&A pairs from the generated blog HTML.

    Looks for the <h2>Frequently Asked Questions</h2> section and extracts
    all <strong>Q:</strong> / <p>A:</p> or <dt>/<dd> patterns beneath it.
    Returns a list of {"q": "...", "a": "..."} dicts.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(blog_html, "html.parser")
        faqs = []

        # Locate the FAQ heading
        faq_heading = None
        for tag in soup.find_all(["h2", "h3"]):
            if "frequently asked" in tag.get_text(strip=True).lower() or "faq" in tag.get_text(strip=True).lower():
                faq_heading = tag
                break

        if not faq_heading:
            return faqs

        # Walk siblings after the FAQ heading
        current_q = None
        for sibling in faq_heading.find_next_siblings():
            text = sibling.get_text(strip=True)
            tag_name = sibling.name

            # Stop at next major heading
            if tag_name in ["h2"] and faq_heading != sibling:
                break

            # Pattern 1: <strong>Q: ...</strong> followed by answer text
            if tag_name in ["p", "div"]:
                strong = sibling.find("strong")
                if strong:
                    strong_text = strong.get_text(strip=True)
                    if strong_text.lower().startswith("q:") or strong_text.endswith("?"):
                        current_q = strong_text.lstrip("Qq: ").strip()
                        # Answer may be in the same tag after the strong
                        answer_text = text.replace(strong_text, "").strip(" :-")
                        if answer_text:
                            faqs.append({"q": current_q, "a": answer_text})
                            current_q = None
                        continue

                if current_q and text:
                    faqs.append({"q": current_q, "a": text})
                    current_q = None

            # Pattern 2: <dt> question / <dd> answer
            elif tag_name == "dt":
                current_q = text
            elif tag_name == "dd" and current_q:
                faqs.append({"q": current_q, "a": text})
                current_q = None

        return faqs[:15]  # cap at 15 FAQs

    except Exception as exc:
        logger.warning(f"FAQ extraction from blog failed: {exc}")
        return []


def _extract_highlights_from_blog(blog_html: str) -> list:
    """
    Parse highlight bullet points from the generated blog HTML.

    Looks for the <h2>Highlights</h2> / <h2>Quick Overview</h2> section
    and extracts all <li> or <td> text pairs as 'Key: Value' strings.
    Returns a list of strings.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(blog_html, "html.parser")
        highlights = []

        # Locate the highlights heading
        hl_heading = None
        for tag in soup.find_all(["h2", "h3"]):
            txt = tag.get_text(strip=True).lower()
            if "highlight" in txt or "quick overview" in txt or "overview" in txt:
                hl_heading = tag
                break

        if not hl_heading:
            return highlights

        # Walk siblings after the heading
        for sibling in hl_heading.find_next_siblings():
            tag_name = sibling.name

            # Stop at next major heading
            if tag_name == "h2":
                break

            # Bullet list
            if tag_name in ["ul", "ol"]:
                for li in sibling.find_all("li"):
                    text = li.get_text(strip=True)
                    if text:
                        highlights.append(text)

            # Table rows (key: value pairs)
            elif tag_name == "table":
                for row in sibling.find_all("tr"):
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True)
                        val = cells[1].get_text(strip=True)
                        if key and val:
                            highlights.append(f"{key}: {val}")

        return highlights[:10]  # cap at 10 highlights

    except Exception as exc:
        logger.warning(f"Highlights extraction from blog failed: {exc}")
        return []


# ─── FreeJobAlert Sanitization ─────────────────────────────────────────────


# Compiled once for performance
_FJA_URL_RE = re.compile(
    r'https?://(?:www\.)?(?:img\d*\.)?freejobalert\.com[^\s\'"<>]*',
    re.IGNORECASE,
)
_FJA_BRAND_RE = re.compile(
    r'\bfreejobalert(?:\.com)?\b',
    re.IGNORECASE,
)
_FJA_ATTR_RE = re.compile(
    r'\b(?:source|via|by|from|courtesy of)\s*:?\s*freejobalert(?:\.com)?\b[^.]*\.',
    re.IGNORECASE,
)


def _sanitize_for_llm(text: str) -> str:
    """
    Remove all FreeJobAlert references from text before it goes to the LLM.

    Strips:
    - Full freejobalert.com URLs (including image/cdn subdomains)
    - Standalone 'freejobalert' / 'freejobalert.com' brand mentions
    - Attribution phrases like 'Source: FreeJobAlert', 'via FreeJobAlert.com'

    Collapses any resulting double-spaces / blank lines.
    """
    if not text:
        return text

    # 1. Remove full URLs first (most specific)
    text = _FJA_URL_RE.sub("", text)

    # 2. Remove attribution phrases like "Source: FreeJobAlert."
    text = _FJA_ATTR_RE.sub("", text)

    # 3. Remove bare brand name mentions
    text = _FJA_BRAND_RE.sub("", text)

    # 4. Clean up double spaces and blank lines left behind
    text = re.sub(r'[ \t]{2,}', ' ', text)           # collapse spaces
    text = re.sub(r'\n{3,}', '\n\n', text)            # collapse blank lines
    text = re.sub(r'^\s+|\s+$', '', text, flags=re.MULTILINE)  # strip lines

    return text.strip()


def _sanitize_value(value) -> object:
    """Recursively sanitize a value (str, list, dict) for FJA references."""
    if isinstance(value, str):
        return _sanitize_for_llm(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    return value  # int, bool, None — leave as-is


# Fields that should NEVER be sanitized (they contain freejobalert URLs intentionally)
_FJA_PRESERVE_FIELDS = {"freejobalert_url", "pdf_url"}


def _verify_no_fja(data: dict) -> int:
    """
    Scan all fields in the merged data dict after LLM output.
    Sanitize any freejobalert references that slipped through.

    Skips 'freejobalert_url' and 'pdf_url' which intentionally hold FJA links.

    Returns the count of fields that were modified.
    """
    modified = 0
    for key, value in list(data.items()):
        if key in _FJA_PRESERVE_FIELDS:
            continue

        cleaned = _sanitize_value(value)
        if cleaned != value:
            data[key] = cleaned
            modified += 1
            logger.debug(f"   Removed FJA reference from field: '{key}'")

    return modified
