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
from typing import Optional

logger = logging.getLogger("gemma_processor")


# ─── JSON REPAIR ────────────────────────────────────────────────────────────────────────────────

def _repair_json(raw: str) -> Optional[dict]:
    """Progressively try to parse / repair LLM JSON output."""
    # 1. Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Pull out first {...} block (LLM sometimes wraps JSON in markdown)
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    candidate = m.group(0) if m else raw

    # 3. Strip trailing commas before } or ]
    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)

    # 4. Replace smart / curly quotes
    candidate = (
        candidate
        .replace('\u201c', '"').replace('\u201d', '"')
        .replace('\u2018', "'").replace('\u2019', "'")
    )

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 5. Try json_repair library (pip install json-repair)
    try:
        from json_repair import repair_json
        return json.loads(repair_json(candidate))
    except Exception:
        pass

    logger.error("\u274c All JSON repair strategies failed")
    return None


# ─── PDF TEXT EXTRACTION (no poppler, no images) ────────────────────────────────────────────

def extract_pdf_text(
    pdf_url: str,
    max_pages: int = 10,       # raised from 5 → cover longer notifications
    max_chars: int = 0,        # 0 = no cap, pass the full document to the LLM
) -> Optional[str]:
    """
    Download a PDF and extract its full text.

    Primary:  pdfplumber  (pure-Python, no poppler needed)
    Fallback: pymupdf / fitz

    Args:
        pdf_url   : Direct URL to the PDF file.
        max_pages : Maximum number of PDF pages to read (default 10).
        max_chars : If > 0, truncate output to this many characters.
                    Default is 0 (no truncation — full document passed to LLM).

    Returns:
        Extracted text string, or None if the PDF is image-only / unreadable.
    """
    for attempt in range(2):
        try:
            logger.info(f"Downloading PDF from: {pdf_url[:80]}...")
            resp = httpx.get(pdf_url, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            pdf_bytes = resp.content
            size_mb = len(pdf_bytes) / 1024 / 1024
            logger.info(f"\u2713 PDF downloaded: {size_mb:.2f} MB")

            # Try pdfplumber first
            text = _extract_with_pdfplumber(pdf_bytes, max_pages)

            # Fallback to pymupdf
            if not text:
                logger.info("pdfplumber returned no text \u2192 trying pymupdf...")
                text = _extract_with_pymupdf(pdf_bytes, max_pages)

            if not text or not text.strip():
                logger.warning("\u26a0\ufe0f  PDF has no extractable text (scanned / image-only PDF)")
                return None

            raw_len = len(text)

            # Only truncate if an explicit cap was requested
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
    Calls a local Ollama model (default: gemma3:12b) for:
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
  "post_name": "comma-separated post names",
  "vacancies": integer or null,
  "qualification": "required educational qualification",
  "age_limit": "e.g. 18-25 years",
  "salary": "pay scale or salary range",
  "application_fee": "fee details or Free",
  "last_date": "DD/MM/YYYY or descriptive",
  "selection_process": "Written Exam | Interview | Merit etc",
  "location": "state or All India",
  "exam_date": "DD/MM/YYYY or null",
  "official_website": null,
  "apply_url": null,
  "pdf_url": null,
  "extra_notes": "any important info not covered above"
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
        model: str = "gemma3:12b",
        base_url: str = "http://localhost:11434",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _call_ollama(
        self,
        prompt: str,
        temperature: float = 0.2,
        num_ctx: int = 32768,    # raised from 16384 → fits full PDF + prompt
        timeout: int = 180,      # default 180s; blog calls pass 360s
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
        """
        Extract structured job fields from HTML text or PDF text.

        The full content is passed to the LLM — no character truncation.
        A 32 K context window comfortably holds the longest government
        notification PDFs (~15–20 K chars) plus the extraction prompt.
        """
        prompt = self.EXTRACT_PROMPT.format(
            content_label=content_label,
            content=content,          # NO truncation — full document
        )
        raw = self._call_ollama(prompt, temperature=0.1, num_ctx=32768, timeout=180)
        if not raw:
            return None

        result = _repair_json(raw)
        if result:
            logger.info(
                f"\u2713 LLM extracted {len(result)} fields from {content_label}"
            )
        else:
            logger.error(f"Failed to parse LLM JSON: {raw[:300]}")
        return result

    def generate_blog(self, job_data: dict) -> Optional[str]:
        """
        Generate a 9000+ character SEO blog post for the job.

        Uses a 360 s timeout and 32 K context to avoid timeouts on
        long-form generation.
        """
        job_summary = json.dumps(job_data, ensure_ascii=False, indent=2)
        prompt = self.BLOG_PROMPT.format(job_data=job_summary[:3000])

        # 360 s timeout for long blog generation
        blog = self._call_ollama(
            prompt, temperature=0.7, num_ctx=32768, timeout=360
        )
        if not blog:
            return None

        logger.info(f"\u2713 Blog generated ({len(blog)} chars)")

        # Auto-expand if below threshold
        if len(blog) < 6000:
            logger.warning(
                f"\u26a0\ufe0f  Blog too short ({len(blog)} chars) — requesting expansion..."
            )
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
