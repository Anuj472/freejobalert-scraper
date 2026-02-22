"""Gemma 3 Processor - Extract fields from PDF or raw text.

FIXED: Converts PDF to images before sending to Gemma multimodal model.
This resolves the "failed to process inputs: image: unknown format" error.
"""

import logging
import requests
import base64
import os
import tempfile
from typing import Dict, Optional, List
import json
import re
import time

# PDF to image conversion
try:
    from pdf2image import convert_from_path
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logging.warning("pdf2image not installed. PDF processing will be disabled.")

from config import Config

logger = logging.getLogger(__name__)

class GemmaProcessor:
    """Gemma 3 processor for PDF and text extraction."""
    
    def __init__(self):
        """Initialize Gemma processor."""
        self.ollama_url = Config.OLLAMA_URL
        self.model = Config.OLLAMA_MODEL
        self._available = self._check_availability()
        
        if not PDF_SUPPORT:
            logger.warning("⚠️  PDF support disabled. Install: pip install pdf2image")
            logger.warning("⚠️  Also install poppler-utils (see requirements.txt)")
    
    def is_available(self) -> bool:
        """Check if Gemma is available."""
        return self._available
    
    def _check_availability(self) -> bool:
        """Check if Ollama with Gemma is available."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = [m.get('name', '') for m in data.get('models', [])]
                if any(self.model in m for m in models):
                    logger.info(f"✓ Gemma {self.model} is available")
                    return True
        except Exception as e:
            logger.debug(f"Gemma not available: {e}")
        return False
    
    def _validate_pdf(self, pdf_bytes: bytes) -> bool:
        """Validate PDF before processing.
        
        Args:
            pdf_bytes: PDF file bytes
        
        Returns:
            True if valid, False otherwise
        """
        # Check size (< 10MB recommended)
        size_mb = len(pdf_bytes) / (1024 * 1024)
        if size_mb > 10:
            logger.warning(f"⚠️  PDF too large: {size_mb:.1f}MB (max 10MB)")
            return False
        
        # Check PDF header
        if not pdf_bytes.startswith(b'%PDF'):
            logger.warning("❌ Invalid PDF format (missing %PDF header)")
            return False
        
        logger.info(f"✓ PDF validated: {size_mb:.2f} MB")
        return True
    
    def _pdf_to_images(self, pdf_path: str, max_pages: int = 3) -> List[str]:
        """Convert PDF to base64-encoded PNG images.
        
        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum pages to convert (limit tokens)
        
        Returns:
            List of base64-encoded PNG images
        """
        if not PDF_SUPPORT:
            logger.error("❌ PDF support not available (pdf2image not installed)")
            return []
        
        try:
            logger.info(f"Converting PDF to images (max {max_pages} pages)...")
            
            # Convert PDF to images (first N pages only)
            images = convert_from_path(
                pdf_path,
                first_page=1,
                last_page=max_pages,
                dpi=150,  # Lower DPI to reduce size (was 200)
                fmt='png'
            )
            
            base64_images = []
            
            for i, image in enumerate(images):
                # Save to temp PNG with compression
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    # Reduce image size if too large
                    width, height = image.size
                    max_dimension = 2048
                    if width > max_dimension or height > max_dimension:
                        ratio = min(max_dimension / width, max_dimension / height)
                        new_size = (int(width * ratio), int(height * ratio))
                        image = image.resize(new_size, resample=1)  # LANCZOS
                        logger.info(f"  Resized page {i+1}: {width}x{height} → {new_size[0]}x{new_size[1]}")
                    
                    image.save(tmp.name, 'PNG', optimize=True, quality=85)
                    tmp_path = tmp.name
                
                # Read as base64
                with open(tmp_path, 'rb') as f:
                    img_bytes = f.read()
                    size_mb = len(img_bytes) / (1024 * 1024)
                    logger.info(f"  Page {i+1}: {size_mb:.2f} MB")
                    
                    # Skip if still too large
                    if size_mb > 5:
                        logger.warning(f"  Page {i+1} too large ({size_mb:.1f}MB), skipping")
                        continue
                    
                    base64_img = base64.b64encode(img_bytes).decode('utf-8')
                    base64_images.append(base64_img)
                
                # Cleanup temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            
            if base64_images:
                logger.info(f"✓ Converted {len(base64_images)} pages to images")
            else:
                logger.error("❌ No pages converted successfully")
            
            return base64_images
            
        except Exception as e:
            logger.error(f"❌ Error converting PDF to images: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def process_pdf_url(self, pdf_url: str, max_retries: int = 2) -> Optional[Dict]:
        """Download PDF and extract ALL fields using Gemma.
        
        Args:
            pdf_url: URL of PDF to download
            max_retries: Maximum retry attempts
        
        Returns:
            Dictionary with all extracted fields or None
        """
        for attempt in range(max_retries):
            try:
                # Download PDF
                logger.info(f"Downloading PDF from: {pdf_url[:70]}...")
                response = requests.get(
                    pdf_url, 
                    timeout=60,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                response.raise_for_status()
                
                # Validate PDF
                if not self._validate_pdf(response.content):
                    logger.warning("⚠️  PDF validation failed, using fallback")
                    return None
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    tmp.write(response.content)
                    tmp_path = tmp.name
                
                # Process PDF
                result = self.process_pdf_file(tmp_path)
                
                # Cleanup
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                
                if result:
                    return result
                    
            except requests.Timeout:
                logger.warning(f"⏱️  PDF download timeout (attempt {attempt+1}/{max_retries})")
            except requests.RequestException as e:
                logger.warning(f"❌ PDF download error: {e} (attempt {attempt+1}/{max_retries})")
            except Exception as e:
                logger.error(f"Error processing PDF URL: {e} (attempt {attempt+1}/{max_retries})")
            
            # Exponential backoff
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"   Retrying in {wait_time}s...")
                time.sleep(wait_time)
        
        logger.error(f"❌ Failed to process PDF after {max_retries} attempts")
        return None
    
    def process_pdf_file(self, pdf_path: str) -> Optional[Dict]:
        """Extract ALL fields from PDF using multimodal Gemma.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            Dictionary with all extracted fields
        """
        try:
            # Convert PDF to images
            images = self._pdf_to_images(pdf_path, max_pages=3)
            
            if not images:
                logger.error("❌ Failed to convert PDF to images")
                return None
            
            # Prompt for Gemma to extract ALL fields
            prompt = self._get_extraction_prompt()
            
            # Call Gemma with images
            logger.info(f"Sending {len(images)} pages to Gemma...")
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": images,  # Now sending PNG images, not raw PDF
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 2000,
                        "num_ctx": 4096  # Context window
                    }
                },
                timeout=180  # Increased timeout for multiple images
            )
            
            if response.status_code == 200:
                result = response.json()
                text_response = result.get('response', '')
                
                # Parse JSON from response
                extracted = self._parse_llm_response(text_response)
                
                if extracted:
                    logger.info(f"✓ Extracted {len(extracted)} fields from PDF")
                else:
                    logger.warning("⚠️  No fields extracted from PDF")
                
                return extracted
            else:
                error_text = response.text[:200] if response.text else "Unknown error"
                logger.error(f"❌ Gemma API error: {response.status_code}")
                logger.debug(f"   Error details: {error_text}")
                return None
                
        except requests.Timeout:
            logger.error("❌ Gemma API timeout (PDF processing took too long)")
            return None
        except Exception as e:
            logger.error(f"❌ Error processing PDF with Gemma: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def process_text(self, raw_text: str) -> Optional[Dict]:
        """Extract ALL fields from raw text using Gemma.
        
        Args:
            raw_text: Raw HTML text content
        
        Returns:
            Dictionary with all extracted fields
        """
        try:
            # Prompt for text extraction
            prompt = self._get_extraction_prompt() + f"\n\nTEXT CONTENT:\n{raw_text}"
            
            # Call Gemma
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 2000
                    }
                },
                timeout=90
            )
            
            if response.status_code == 200:
                result = response.json()
                text_response = result.get('response', '')
                
                # Parse JSON from response
                extracted = self._parse_llm_response(text_response)
                return extracted
            else:
                logger.error(f"Gemma API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing text with Gemma: {e}")
            return None
    
    def _get_extraction_prompt(self) -> str:
        """Get prompt for field extraction."""
        return """You are a government job data extraction expert. Extract ALL relevant information from this document.

Extract the following fields (return JSON format):

{
  "title": "Full job post name/title",
  "organization": "Department/organization name",
  "qualification": "Educational qualification required",
  "category": "Job category (banking/defence/railway/ssc/upsc/police/teaching/psu/state-govt/central-govt/healthcare)",
  "vacancies": <number of posts (integer only, not year)>,
  "location": "Job location/posting place",
  "post_date": "DD-MM-YYYY",
  "last_date": "DD-MM-YYYY",
  "salary": "Salary/pay scale",
  "age_limit": "Age limit details",
  "advt_no": "Advertisement number",
  "application_fee": "Application fee details",
  "selection_process": "Selection/exam process",
  "how_to_apply": "How to apply instructions",
  "full_description": "Brief 2-3 sentence summary",
  "important_dates": {"Event": "DD-MM-YYYY"},
  "vacancy_details": {"Post Name": "Count"}
}

Rules:
- Return ONLY valid JSON (no markdown, no extra text)
- Use "DD-MM-YYYY" format for dates
- vacancies must be integer (filter out years like 2026)
- For category, choose most appropriate from the list
- If field not found, use null or empty string
- Extract information from ALL pages shown
"""
    
    def _parse_llm_response(self, text: str) -> Dict:
        """Parse LLM JSON response."""
        try:
            # Try to find JSON in response
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                # Validate and clean data
                cleaned = {}
                
                # String fields
                for field in ['title', 'organization', 'qualification', 'category', 'location',
                             'post_date', 'last_date', 'salary', 'age_limit', 'advt_no',
                             'application_fee', 'selection_process', 'how_to_apply', 'full_description']:
                    value = data.get(field)
                    if value and str(value).strip().lower() not in ['null', 'none', 'n/a', '', 'not specified']:
                        cleaned[field] = str(value).strip()
                
                # Integer field
                vacancies = data.get('vacancies')
                if vacancies:
                    try:
                        num = int(vacancies)
                        # Filter out years
                        if 1 <= num < 50000 and (num < 2020 or num > 2030):
                            cleaned['vacancies'] = num
                    except:
                        pass
                
                # Dict fields
                for field in ['important_dates', 'vacancy_details']:
                    value = data.get(field)
                    if value and isinstance(value, dict):
                        cleaned[field] = value
                
                return cleaned
            else:
                logger.warning("No JSON found in LLM response")
                logger.debug(f"Response text: {text[:300]}...")
                return {}
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON: {e}")
            logger.debug(f"Response text: {text[:200]}...")
            return {}
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return {}
    
    def generate_blog(self, job_data: Dict) -> Optional[Dict]:
        """Generate SEO blog content using Gemma.
        
        Args:
            job_data: Extracted job data
        
        Returns:
            Dictionary with blog content
        """
        try:
            # Build prompt with job data
            title = job_data.get('title', 'Job Recruitment')
            org = job_data.get('organization', 'Organization')
            vacancies = job_data.get('vacancies', 'multiple')
            last_date = job_data.get('last_date', 'Check notification')
            qualification = job_data.get('qualification', '')
            
            prompt = f"""Write an SEO-optimized blog article for this government job recruitment.

JOB DETAILS:
- Title: {title}
- Organization: {org}
- Total Posts: {vacancies}
- Last Date: {last_date}
- Qualification: {qualification}

Generate a comprehensive blog article in JSON format:

{{
  "seo_title": "SEO-friendly title (max 60 chars)",
  "meta_description": "SEO meta description (max 160 chars)",
  "article": "Full markdown blog article (500-800 words)",
  "highlights": ["Key point 1", "Key point 2", "Key point 3"],
  "faqs": [{{"question": "Q1?", "answer": "A1"}}, {{"question": "Q2?", "answer": "A2"}}]
}}

Return ONLY valid JSON (no markdown formatting).
"""
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 2000
                    }
                },
                timeout=90
            )
            
            if response.status_code == 200:
                result = response.json()
                text_response = result.get('response', '')
                
                # Parse JSON
                json_match = re.search(r'\{[\s\S]*\}', text_response)
                if json_match:
                    blog_data = json.loads(json_match.group(0))
                    return blog_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating blog: {e}")
            return None
