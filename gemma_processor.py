# gemma_processor.py
# PDF extraction: pdfplumber + pymupdf (NO poppler binary required)
# JSON repair: 5 progressive strategies for malformed LLM output
# Blog: 9000+ character SEO content with 11 mandatory sections

import io
import re
import json
import time
import httpx
import logging
import requests
from typing import Optional

logger = logging.getLogger("gemma_processor")

# Browser-like headers (used as HTTP-level fallback)
_PDF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


# ─── JSON REPAIR ────────────────────────────────────────────────────────────────────────────────

def _repair_json(raw: str) -> Optional[dict]:
    """Progressively try to parse / repair LLM JSON output."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    m = re.search(r'\{.*\}', raw, re.DOTALL)
    candidate = m.group(0) if m else raw
    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
    candidate = (
        candidate
        .replace('\u201c', '"').replace('\u201d', '"')
        .replace('\u2018', "'").replace('\u2019', "'")
    )

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    try:
        from json_repair import repair_json
        return json.loads(repair_json(candidate))
    except Exception:
        pass

    logger.error("\u274c All JSON repair strategies failed")
    return None


# ─── PDF DOWNLOAD HELPERS ───────────────────────────────────────────────────────────────────

def _download_with_curl_cffi(
    url: str,
    headers: dict,
    timeout: int = 60,
) -> Optional[bytes]:
    """
    Download using curl_cffi which impersonates Chrome TLS fingerprint.

    Many Indian government servers (indianrailways.gov.in, etc.) use TLS
    fingerprinting (JA3) to block non-browser clients at the TCP level
    (ECONNREFUSED / ECONNRESET). curl_cffi sends an identical TLS handshake
    to Chrome so the server accepts the connection.

    Returns raw bytes, or None if unavailable / failed.
    """
    try:
        from curl_cffi import requests as curl_requests
        resp = curl_requests.get(
            url,
            headers=headers,
            timeout=timeout,
            impersonate="chrome122",   # sends real Chrome 122 TLS fingerprint
            allow_redirects=True,
            verify=False,
        )
        resp.raise_for_status()
        logger.info("   (downloaded via curl_cffi / Chrome TLS fingerprint)")
        return resp.content
    except ImportError:
        logger.debug("curl_cffi not installed, will fall back to requests")
        return None
    except Exception as exc:
        logger.warning(f"curl_cffi download failed: {exc}")
        return None


def _download_with_requests(
    url: str,
    headers: dict,
    timeout: int = 60,
) -> Optional[bytes]:
    """Standard requests download (HTTP/1.1). Works for most servers."""
    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            verify=False,
        )
        resp.raise_for_status()
        logger.info("   (downloaded via requests / HTTP 1.1)")
        return resp.content
    except Exception as exc:
        raise exc  # let caller log & retry


# ─── PDF TEXT EXTRACTION ───────────────────────────────────────────────────────────────────

def extract_pdf_text(
    pdf_url: str,
    max_pages: int = 10,
    max_chars: int = 0,
    referer: Optional[str] = None,
) -> Optional[str]:
    """
    Download a PDF and extract its full text.

    Download strategy (in order):
      1. curl_cffi with Chrome TLS impersonation  ← fixes ECONNREFUSED on
                                                     TLS-fingerprinting servers
      2. requests with browser UA headers          ← handles HTTP-level blocks

    Text extraction strategy:
      1. pdfplumber  (pure-Python, no poppler)
      2. pymupdf / fitz  (fallback)

    Args:
        pdf_url   : Direct URL to the PDF.
        max_pages : Max PDF pages to read (default 10).
        max_chars : If > 0, truncate to this many chars.
                    Default 0 = no cap, full document to LLM.
        referer   : HTTP Referer header (pass the FreeJobAlert article URL).
    """
    headers = dict(_PDF_HEADERS)
    headers["Referer"] = referer or "https://www.freejobalert.com/"

    for attempt in range(2):
        try:
            logger.info(f"Downloading PDF from: {pdf_url[:80]}...")

            # Strategy 1: curl_cffi (Chrome TLS fingerprint)
            pdf_bytes = _download_with_curl_cffi(pdf_url, headers)

            # Strategy 2: requests fallback
            if pdf_bytes is None:
                pdf_bytes = _download_with_requests(pdf_url, headers)

            size_mb = len(pdf_bytes) / 1024 / 1024
            logger.info(f"\u2713 PDF downloaded: {size_mb:.2f} MB")

            # Extract text
            text = _extract_with_pdfplumber(pdf_bytes, max_pages)
            if not text:
                logger.info("pdfplumber returned no text \u2192 trying pymupdf...")
                text = _extract_with_pymupdf(pdf_bytes, max_pages)

            if not text or not text.strip():
                logger.warning(
                    "\u26a0\ufe0f  PDF has no extractable text (scanned / image-only PDF)"
                )
                return None

            raw_len = len(text)
            if max_chars and max_chars > 0:
                trimmed = text[:max_chars]
                logger.info(
                    f"\u2713 PDF text extracted: {len(trimmed)} chars "
                    f"(total raw: {raw_len} chars, capped at {max_chars})"
                )
            else:
                trimmed = text
                logger.info(
                    f"\u2713 PDF text extracted: {raw_len} chars (full document, no cap)"
                )

            return trimmed

        except Exception as exc:
            logger.error(f"\u274c PDF attempt {attempt + 1} failed: {exc}")
            if attempt == 0:
                logger.info("   Retrying in 1s...")
                time.sleep(1)

    logger.error("\u274c Failed to extract PDF text after 2 attempts")
    return None


def _extract_with_pdfplumber(pdf_bytes: bytes, max_pages: int) -> Optional[str]:
    try:
        import pdfplumber
        chunks: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text()
                if page_text:
                    chunks.append(page_text)
        return "\n\n".join(chunks) if chunks else None
    except Exception as exc:
        logger.warning(f"pdfplumber failed: {exc}")
        return None


def _extract_with_pymupdf(pdf_bytes: bytes, max_pages: int) -> Optional[str]:
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_to_read = min(max_pages, doc.page_count)
        chunks = [doc[i].get_text() for i in range(pages_to_read)]
        combined = "\n\n".join(c for c in chunks if c)
        return combined if combined.strip() else None
    except Exception as exc:
        logger.warning(f"pymupdf failed: {exc}")
        return None


# ─── GEMMA PROCESSOR ──────────────────────────────────────────────────────────────────────────────

class GemmaProcessor:
    """
    Calls a local Ollama model (default: gemma4:12b) for:
      1. Structured field extraction from HTML text or PDF text
      2. SEO blog generation (9000+ characters)
    """

    EXTRACT_PROMPT = """You are a government job data extraction assistant.
Extract ALL fields from the content below and return ONLY valid JSON (no markdown, no extra text).

{content_label}:
\"\"\"
{content}
\"\"\"

Return JSON exactly in this schema (use null for missing fields):
{{
  "title": "full official job title",
  "organization": "full organization name",
  "category": "one of: Central Govt | State Govt | PSU | Bank | Railway | Defence | Teaching | Healthcare | Other",
  "advt_no": "advertisement/notification number e.g. Advt. No. 01/2025",
  "post_name": "comma-separated post names",
  "vacancies": integer or null,
  "qualification": "required educational qualification in detail",
  "age_limit": "e.g. 18-25 years, with relaxation info",
  "salary": "pay scale or salary range",
  "application_fee": "fee details by category e.g. General: 500, SC/ST: 250, or Free",
  "last_date": "DD/MM/YYYY",
  "selection_process": "comma-separated stages e.g. Written Exam, Interview, Document Verification",
  "how_to_apply": "brief step-by-step how to apply description",
  "location": "state or All India",
  "full_description": "2-3 sentence plain-text summary of what this job notification is about",
  "important_dates": {{
    "notification_date": "DD/MM/YYYY or null",
    "application_start_date": "DD/MM/YYYY or null",
    "last_date": "DD/MM/YYYY or null",
    "exam_date": "DD/MM/YYYY or null",
    "admit_card_date": "DD/MM/YYYY or null",
    "result_date": "DD/MM/YYYY or null"
  }},
  "vacancy_details": {{
    "Post Name 1": integer_vacancies,
    "Post Name 2": integer_vacancies
  }},
  "highlights": [
    "Total Vacancies: X",
    "Application Fee: Y",
    "Last Date: DD/MM/YYYY",
    "Salary: Z",
    "Qualification: Q"
  ],
  "seo_title": "60-character SEO-optimized title for the job post",
  "meta_description": "150-character meta description summarising the recruitment for search engines"
}}"""

    BLOG_PROMPT = """You are an SEO content writer for an Indian government job portal.
Write a comprehensive blog post for the job notification below.

STRICT REQUIREMENTS:
- Total length: MINIMUM 9000 characters (aim for 9000-10000)
- Format: HTML with proper h2/h3 tags, tables, and lists
- Language: Clear, helpful English for job aspirants in India
- MUST include ALL these sections in order:
  1. <h2>Introduction</h2> (200+ words explaining the recruitment)
  2. <h2>Highlights / Quick Overview</h2> (HTML table: Post, Vacancies, Salary, Last Date, etc.)
  3. <h2>Post-wise Vacancy Details</h2> (table if multiple posts)
  4. <h2>Eligibility Criteria</h2> (Education, Age, Nationality sub-sections)
  5. <h2>Important Dates</h2> (table: Notification Date, Start Date, Last Date, Exam Date)
  6. <h2>Application Fee</h2> (table: category-wise fee)
  7. <h2>Selection Process</h2> (detailed stages)
  8. <h2>Salary / Pay Scale</h2> (post-wise if applicable)
  9. <h2>How to Apply Step by Step</h2> (numbered list, minimum 8 steps)
  10. <h2>Frequently Asked Questions (FAQs)</h2> (minimum 10 Q&A pairs)
  11. <h2>Conclusion</h2>

Job Details:
{job_data}

Write the full blog post now. It MUST be at least 9000 characters:"""

    def __init__(
        self,
        model: str = "gemma4:12b",
        base_url: str = "http://localhost:11434",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Check if the configured model is available in Ollama."""
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                return any(self.model in m or m in self.model for m in models)
            return False
        except Exception:
            return False

    def _call_ollama(
        self,
        prompt: str,
        temperature: float = 0.2,
        num_ctx: int = 32768,
        timeout: int = 180,
    ) -> Optional[str]:
        """Send a prompt to Ollama and return the response text."""
        try:
            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_ctx": num_ctx,
                    },
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as exc:
            logger.error(f"\u274c Ollama call failed: {exc}")
            return None

    def extract_fields(
        self,
        content: str,
        content_label: str = "HTML Text",
    ) -> Optional[dict]:
        """Extract structured job fields. Full content passed — no truncation."""
        prompt = self.EXTRACT_PROMPT.format(
            content_label=content_label,
            content=content,
        )
        raw = self._call_ollama(prompt, temperature=0.1, num_ctx=32768, timeout=180)
        if not raw:
            return None

        result = _repair_json(raw)
        if result:
            logger.info(f"\u2713 LLM extracted {len(result)} fields from {content_label}")
        else:
            logger.error(f"Failed to parse LLM JSON: {raw[:300]}")
        return result

    def generate_blog(self, job_data: dict) -> Optional[str]:
        """Generate a 9000+ character SEO blog post. Uses 360 s timeout."""
        job_summary = json.dumps(job_data, ensure_ascii=False, indent=2)
        prompt = self.BLOG_PROMPT.format(job_data=job_summary[:3000])

        blog = self._call_ollama(
            prompt, temperature=0.7, num_ctx=32768, timeout=360
        )
        if not blog:
            return None

        logger.info(f"\u2713 Blog generated ({len(blog)} chars)")

        if len(blog) < 6000:
            logger.warning(f"\u26a0\ufe0f  Blog too short ({len(blog)} chars) — requesting expansion...")
            expand_prompt = (
                f"The blog below is too short ({len(blog)} chars). "
                f"Expand it to at least 9000 characters by:\n"
                f"- Adding more detail to each section\n"
                f"- Adding more FAQ pairs (aim for 12-15)\n"
                f"- Expanding the How to Apply section with more sub-steps\n"
                f"- Adding a Tips for Applicants section\n\n"
                f"Current blog:\n{blog}\n\n"
                f"Expanded blog (must be 9000+ characters):"
            )
            expanded = self._call_ollama(
                expand_prompt, temperature=0.6, num_ctx=32768, timeout=360
            )
            if expanded and len(expanded) > len(blog):
                logger.info(f"\u2713 Blog expanded to {len(expanded)} chars")
                return expanded

        return blog
