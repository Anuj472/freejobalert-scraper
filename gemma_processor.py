"""Gemma 3 12B Multimodal Processor with AGGRESSIVE Content Validation."""

import requests
import json
import logging
import base64
import os
import re
from pathlib import Path
from io import BytesIO
from typing import Dict, List, Optional

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logging.warning("pdf2image not installed. Image PDF processing will be disabled.")

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    logging.warning("PyPDF2 not installed. Text PDF processing will be disabled.")

from PIL import Image

logger = logging.getLogger(__name__)

class GemmaProcessor:
    """Process PDFs and generate blogs using Gemma 3 with AGGRESSIVE validation."""
    
    def __init__(self):
        """Initialize Gemma 3 12B processor with optimized settings."""
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model = "gemma3:12b"
        self.temp_dir = Path('temp_pdfs')
        self.temp_dir.mkdir(exist_ok=True)
        
        if self._check_model_available():
            logger.info(f"✓ {self.model} initialized")
            logger.info(f"  - Vision: ✓")
            logger.info(f"  - Validation: SUPER ROBUST 🛡️")
            logger.info(f"  - Context: 32K tokens")
        else:
            logger.warning(f"⚠️  {self.model} not found!")
    
    def _check_model_available(self) -> bool:
        """Check if Gemma 3 model is available."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = [m['name'] for m in response.json().get('models', [])]
                return self.model in models
        except:
            pass
        return False
    
    def is_available(self) -> bool:
        """Check if processor is available."""
        return self._check_model_available()
    
    def _aggressive_freejobalert_check(self, text: str) -> bool:
        """
        AGGRESSIVE check for ANY freejobalert references.
        Returns True if freejobalert found, False if clean.
        """
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Pattern 1: Direct domain mentions
        if 'freejobalert.com' in text_lower:
            return True
        if 'freejobalert' in text_lower and '.com' in text_lower:
            return True
        
        # Pattern 2: Text mentions
        if 'freejobalert' in text_lower:
            return True
        if 'free job alert' in text_lower:
            return True
        
        # Pattern 3: URL patterns with various protocols
        fja_patterns = [
            r'https?://(?:www\.)?freejobalert',
            r'http://freejobalert',
            r'https://freejobalert',
            r'www\.freejobalert',
            r'freejobalert\.com',
            r'//freejobalert',
        ]
        
        for pattern in fja_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _remove_all_freejobalert_content(self, text: str) -> str:
        """
        AGGRESSIVELY remove ALL freejobalert references from text.
        Multiple passes to ensure complete removal.
        """
        if not text:
            return text
        
        original_text = text
        
        # Pass 1: Remove URLs with various patterns
        url_patterns = [
            r'https?://(?:www\.)?freejobalert\.com[^\s\)\]<>"\']*',
            r'http://freejobalert\.com[^\s\)\]<>"\']*',
            r'www\.freejobalert\.com[^\s\)\]<>"\']*',
            r'freejobalert\.com[^\s\)\]<>"\']*',
            r'//freejobalert\.com[^\s\)\]<>"\']*',
        ]
        
        for pattern in url_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Pass 2: Remove markdown links containing freejobalert
        text = re.sub(
            r'\[([^\]]*)\]\(https?://(?:www\.)?freejobalert[^\)]*\)',
            r'\1',
            text,
            flags=re.IGNORECASE
        )
        
        # Pass 3: Remove "Source:" lines with freejobalert
        text = re.sub(
            r'(?:Source|Apply Link|PDF Link|Official Notification|Download|Visit)[\s:]*(?:\*\*)?(?:httpswww\.)?freejobalert[^\n]*\n?',
            '',
            text,
            flags=re.IGNORECASE
        )
        
        # Pass 4: Remove entire sentences containing freejobalert
        text = re.sub(
            r'[^.!?\n]*(?:freejobalert|free job alert)[^.!?\n]*[.!?]',
            '',
            text,
            flags=re.IGNORECASE
        )
        
        # Pass 5: Remove "Visit FreeJobAlert" type instructions
        text = re.sub(
            r'(?:Visit|Check|Download from|Apply through|Go to)[\s]+(?:the[\s]+)?(?:FreeJobAlert|Free Job Alert)[^.!?\n]*[.!?]?',
            '',
            text,
            flags=re.IGNORECASE
        )
        
        # Pass 6: Remove remaining "freejobalert" text
        text = re.sub(r'freejobalert', 'official source', text, flags=re.IGNORECASE)
        text = re.sub(r'free[\s]?job[\s]?alert', 'official notification', text, flags=re.IGNORECASE)
        
        # Pass 7: Clean up formatting
        text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 newlines
        text = re.sub(r' {2,}', ' ', text)  # Max 1 space
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Clean empty lines
        text = text.strip()
        
        # Log if we cleaned anything
        if text != original_text:
            logger.info("🧹 Removed freejobalert content from generated text")
        
        return text
    
    def _validate_and_clean_json_response(self, data: Dict) -> Optional[Dict]:
        """
        SUPER ROBUST validation of JSON response from Gemma.
        
        Returns:
            - Cleaned dict if content is valid or can be cleaned
            - None if content cannot be cleaned (too much freejobalert)
        """
        if not data:
            return None
        
        cleaned_data = {}
        fja_violations = 0
        total_fields = 0
        
        for key, value in data.items():
            total_fields += 1
            
            # Skip None values
            if value is None:
                continue
            
            # Check and clean string fields
            if isinstance(value, str):
                # Check if field contains freejobalert
                has_fja = self._aggressive_freejobalert_check(value)
                
                if has_fja:
                    fja_violations += 1
                    logger.warning(f"⚠️  Field '{key}' contains freejobalert - attempting to clean")
                    
                    # Try to clean it
                    cleaned_value = self._remove_all_freejobalert_content(value)
                    
                    # Double-check if it's actually clean now
                    if self._aggressive_freejobalert_check(cleaned_value):
                        logger.error(f"❌ Field '{key}' still has freejobalert after cleaning - rejecting")
                        # Don't include this field
                        continue
                    else:
                        # Successfully cleaned
                        if cleaned_value and len(cleaned_value) > 10:  # Must have meaningful content
                            cleaned_data[key] = cleaned_value
                            logger.info(f"✅ Field '{key}' cleaned successfully")
                        else:
                            logger.warning(f"⚠️  Field '{key}' empty after cleaning - skipping")
                else:
                    # Field is clean
                    cleaned_data[key] = value
            
            # Handle dict fields (like important_dates, vacancy_details)
            elif isinstance(value, dict):
                cleaned_dict = {}
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str):
                        if not self._aggressive_freejobalert_check(sub_value):
                            cleaned_dict[sub_key] = sub_value
                        else:
                            logger.warning(f"⚠️  Subfield '{key}.{sub_key}' contains freejobalert - removed")
                    else:
                        cleaned_dict[sub_key] = sub_value
                
                if cleaned_dict:
                    cleaned_data[key] = cleaned_dict
            
            # Handle list fields (like highlights, faqs)
            elif isinstance(value, list):
                cleaned_list = []
                for item in value:
                    if isinstance(item, str):
                        if not self._aggressive_freejobalert_check(item):
                            cleaned_list.append(item)
                        else:
                            logger.warning(f"⚠️  List item in '{key}' contains freejobalert - removed")
                    elif isinstance(item, dict):
                        # Handle FAQ objects
                        cleaned_item = {}
                        for item_key, item_value in item.items():
                            if isinstance(item_value, str):
                                if not self._aggressive_freejobalert_check(item_value):
                                    cleaned_item[item_key] = item_value
                        if cleaned_item:
                            cleaned_list.append(cleaned_item)
                    else:
                        cleaned_list.append(item)
                
                if cleaned_list:
                    cleaned_data[key] = cleaned_list
            
            else:
                # Non-string fields (numbers, bools) - pass through
                cleaned_data[key] = value
        
        # Final decision: reject if too many violations
        if fja_violations > 3:
            logger.error(f"🚨 REJECTED: Too many freejobalert violations ({fja_violations} fields)")
            logger.error("   This content cannot be used - returning None")
            return None
        
        if fja_violations > 0:
            logger.warning(f"⚠️  Cleaned {fja_violations} fields with freejobalert references")
        else:
            logger.info("✅ No freejobalert references found in generated content")
        
        return cleaned_data if cleaned_data else None
    
    def process_pdf_url(self, pdf_url: str) -> Optional[Dict]:
        """
        Download and process PDF using Gemma 3 with validation.
        """
        if not self.is_available():
            logger.warning("Gemma 3 not available, skipping PDF processing")
            return None
        
        try:
            logger.info(f"📥 Downloading PDF: {pdf_url[:60]}...")
            
            response = requests.get(pdf_url, timeout=90, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            pdf_bytes = BytesIO(response.content)
            
            # Try text extraction first
            if PYPDF2_AVAILABLE:
                text_data = self._try_text_extraction(pdf_bytes)
                if text_data and len(text_data) > 500:
                    logger.info("📄 Text PDF detected, extracting with Gemma 3...")
                    return self._extract_from_text_focused(text_data)
            
            # Convert to images for vision processing
            if PDF2IMAGE_AVAILABLE:
                logger.info("🖼️  Image/Scanned PDF detected, using Gemma 3 Vision...")
                pdf_bytes.seek(0)
                
                temp_pdf = self.temp_dir / f'temp_{hash(pdf_url)}.pdf'
                with open(temp_pdf, 'wb') as f:
                    f.write(pdf_bytes.read())
                
                images = convert_from_path(temp_pdf, dpi=200, fmt='jpeg', first_page=1, last_page=3)
                logger.info(f"✓ Converted {len(images)} pages to images")
                
                result = self._extract_from_images_focused(images)
                temp_pdf.unlink()
                
                return result
            else:
                logger.warning("pdf2image not available")
                return None
                
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            return None
    
    def _try_text_extraction(self, pdf_bytes: BytesIO) -> Optional[str]:
        """Try extracting text from PDF."""
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_bytes)
            text = ""
            for page in pdf_reader.pages[:5]:
                text += page.extract_text()
            return text if len(text) > 100 else None
        except:
            return None
    
    def _extract_from_text_focused(self, text: str) -> Optional[Dict]:
        """Extract from text with focused prompts."""
        text = text[:40000]
        
        prompt = f"""You are analyzing a government job recruitment notification document.

CRITICAL RULES - READ CAREFULLY:
1. NEVER mention "freejobalert" or "freejobalert.com" ANYWHERE in your response
2. DO NOT extract or include ANY URLs, links, or web addresses
3. DO NOT extract post_date (notification publish date)
4. Only extract last_date (application deadline)
5. Return ONLY valid JSON format

DOCUMENT TEXT:
{text}

Extract the following information:

1. Job title or post name?
2. Organization/department name?
3. Category (banking/defence/railway/ssc/upsc/police/teaching/psu/state-govt/central-govt)?
4. Total vacancies (INTEGER count)?
5. Advertisement/notification number?
6. LAST DATE to apply (DD-MM-YYYY)?
7. Salary or pay scale?
8. Age limit?
9. Educational qualification?
10. Job location or posting place?
11. Application fee?
12. Selection process?
13. How to apply (steps)?
14. Important dates?
15. Post-wise vacancy breakdown?

Return ONLY this JSON:
{{
    "title": "Job title",
    "organization": "Organization name",
    "category": "category",
    "vacancies": 100,
    "advt_no": "Advt No",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale",
    "age_limit": "Age requirement",
    "qualification": "Education required",
    "location": "Job location",
    "application_fee": {{"General": "Rs. X"}},
    "selection_process": "Selection method",
    "how_to_apply": "Application steps",
    "important_dates": {{"Application End": "DD-MM-YYYY"}},
    "vacancy_details": {{"Post": "Count"}}
}}

REMEMBER: NO URLs, NO freejobalert mentions, NO post_date field!

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=None, timeout=90)
    
    def _extract_from_images_focused(self, images: List) -> Optional[Dict]:
        """Extract from images with focused questions."""
        images_base64 = []
        for img in images:
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            images_base64.append(img_base64)
        
        prompt = """You are analyzing scanned images of a government job notification document.

CRITICAL RULES - READ CAREFULLY:
1. NEVER mention "freejobalert" or "freejobalert.com" in your response
2. DO NOT extract or include ANY URLs or links
3. DO NOT extract post_date (only last_date for application deadline)
4. Return ONLY valid JSON

Answer these questions from the images:

1. Job title?
2. Organization name?
3. Category (banking/defence/railway/ssc/upsc/police/teaching/psu/state-govt/central-govt)?
4. Total vacancies (INTEGER)?
5. Notification number?
6. LAST DATE to apply (DD-MM-YYYY)?
7. Salary/pay scale?
8. Age limit?
9. Qualification required?
10. Job location?
11. Application fee?
12. Selection process?
13. How to apply?
14. Important dates?
15. Vacancy breakdown?

Return ONLY this JSON:
{
    "title": "Job title",
    "organization": "Organization",
    "category": "category",
    "vacancies": 100,
    "advt_no": "Advt No",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale",
    "age_limit": "Age",
    "qualification": "Education",
    "location": "Location",
    "application_fee": {"General": "Rs. X"},
    "selection_process": "Method",
    "how_to_apply": "Steps",
    "important_dates": {"Application End": "DD-MM-YYYY"},
    "vacancy_details": {"Post": "Count"}
}

REMEMBER: NO URLs, NO freejobalert, NO post_date!

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=images_base64, timeout=90)
    
    def generate_blog(self, job_data: Dict) -> Optional[Dict]:
        """
        Generate blog with AGGRESSIVE validation.
        """
        if not self.is_available():
            logger.warning("Gemma 3 not available, skipping blog generation")
            return None
        
        # Clean input data first
        cleaned_input = {}
        for key, value in job_data.items():
            if value and isinstance(value, str):
                cleaned_input[key] = self._remove_all_freejobalert_content(value)
            else:
                cleaned_input[key] = value
        
        prompt = f"""Create a CONCISE, SEO-optimized blog post for this job recruitment.

CRITICAL RULES - FOLLOW STRICTLY:
1. NEVER mention "freejobalert" or "freejobalert.com" anywhere
2. DO NOT include ANY URLs or web links in the blog
3. Focus on official information only
4. Use phrases like "official notification" or "official website" instead of website names

JOB DATA:
{json.dumps(cleaned_input, indent=2)}

REQUIREMENTS:
1. Word Limit: 800-900 words maximum
2. SEO Title: 60-70 characters
3. Meta Description: 150-160 characters
4. Blog Structure:
   - Brief Overview (2-3 sentences)
   - 🎯 Key Highlights (5 bullet points with emojis)
   - 📅 Important Dates (markdown table)
   - 📋 Eligibility
   - 💰 Salary & Fee
   - 📝 How to Apply (4-5 steps)
   - ❓ FAQs (5 questions)

5. Use markdown headings (##, ###)
6. Add emojis for engagement
7. Be concise and clear
8. NO URLs or links

Return ONLY valid JSON:
{{
    "seo_title": "Job Title 2026 - X Posts | Last Date",
    "meta_description": "Complete details about...",
    "article": "Full markdown blog (800-900 words)...",
    "highlights": [
        "Total Posts: X",
        "Last Date: DD-MM-YYYY",
        "Salary: Rs. X-Y",
        "Qualification: ...",
        "Apply Mode: Online/Offline"
    ],
    "faqs": [
        {{
            "question": "What is the last date?",
            "answer": "Brief answer..."
        }}
    ]
}}

CRITICAL: NO freejobalert mentions, NO URLs!

JSON OUTPUT:"""

        result = self._call_gemma(prompt, images=None, for_blog=True, timeout=180)
        
        # 🛡️ AGGRESSIVE POST-GENERATION VALIDATION
        if result:
            logger.info("🛡️ Running AGGRESSIVE post-generation validation...")
            validated_result = self._validate_and_clean_json_response(result)
            
            if not validated_result:
                logger.error("🚨 BLOG REJECTED: Contains too much freejobalert content")
                logger.error("   Returning None - blog will not be used")
                return None
            
            logger.info("✅ Blog passed validation and cleaning")
            return validated_result
        
        return None
    
    def _call_gemma(self, prompt: str, images: Optional[List[str]] = None, 
                    for_blog: bool = False, timeout: int = 90) -> Optional[Dict]:
        """Call Gemma 3 model."""
        try:
            messages = [{"role": "user", "content": prompt}]
            
            if images:
                messages[0]["images"] = images
            
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.7 if for_blog else 0.1,
                        "num_predict": 2500 if for_blog else 2048,
                        "num_ctx": 32768,
                        "num_gpu": 99,
                        "num_thread": 8,
                        "f16_kv": True,
                        "low_vram": False,
                    }
                },
                timeout=timeout
            )
            
            if response.status_code == 200:
                content = response.json()['message']['content']
                
                # Clean JSON response
                content = content.strip()
                if content.startswith('```json'):
                    content = content[7:]
                if content.startswith('```'):
                    content = content[3:]
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()
                
                data = json.loads(content)
                logger.info(f"✓ Gemma 3 extracted {len(data)} fields")
                return data
            else:
                logger.error(f"Gemma 3 API error: {response.status_code}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Gemma 3 call failed: {e}")
            return None
