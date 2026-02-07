"""Gemma 3 12B Multimodal Processor for PDF extraction and blog generation.

Handles:
- Text PDFs (fast extraction)
- Scanned/Image PDFs (vision-based extraction)
- SEO blog generation
"""

import requests
import json
import logging
import base64
import os
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
    """Process PDFs and generate blogs using Gemma 3 12B multimodal model."""
    
    def __init__(self):
        """Initialize Gemma 3 12B processor."""
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model = "gemma3:12b"
        self.temp_dir = Path('temp_pdfs')
        self.temp_dir.mkdir(exist_ok=True)
        
        # Check if Gemma 3 is available
        if self._check_model_available():
            logger.info(f"✓ {self.model} initialized")
            logger.info(f"  - Vision: ✓")
            logger.info(f"  - Context: 128K tokens")
            logger.info(f"  - VRAM: 8.1 GB")
        else:
            logger.warning(f"⚠️  {self.model} not found!")
            logger.warning(f"   Run: ollama pull {self.model}")
    
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
    
    def process_pdf_url(self, pdf_url: str) -> Optional[Dict]:
        """
        Download and process PDF using Gemma 3.
        Handles both text and image PDFs.
        
        Args:
            pdf_url: URL of the PDF file
            
        Returns:
            Extracted job data dictionary or None
        """
        if not self.is_available():
            logger.warning("Gemma 3 not available, skipping PDF processing")
            return None
        
        try:
            logger.info(f"📥 Downloading PDF: {pdf_url[:60]}...")
            
            # Download PDF
            response = requests.get(pdf_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            pdf_bytes = BytesIO(response.content)
            
            # Try text extraction first (fast path)
            if PYPDF2_AVAILABLE:
                text_data = self._try_text_extraction(pdf_bytes)
                if text_data and len(text_data) > 500:
                    logger.info("📄 Text PDF detected, extracting with Gemma 3...")
                    return self._extract_from_text(text_data)
            
            # Convert to images for vision processing
            if PDF2IMAGE_AVAILABLE:
                logger.info("🖼️  Image/Scanned PDF detected, using Gemma 3 Vision...")
                pdf_bytes.seek(0)
                
                # Save temporarily
                temp_pdf = self.temp_dir / f'temp_{hash(pdf_url)}.pdf'
                with open(temp_pdf, 'wb') as f:
                    f.write(pdf_bytes.read())
                
                # Convert to images
                images = convert_from_path(
                    temp_pdf,
                    dpi=200,
                    fmt='jpeg',
                    first_page=1,
                    last_page=3  # Process first 3 pages
                )
                
                logger.info(f"✓ Converted {len(images)} pages to images")
                
                # Extract with vision
                result = self._extract_from_images(images)
                
                # Cleanup
                temp_pdf.unlink()
                
                return result
            else:
                logger.warning("pdf2image not available, cannot process image PDFs")
                return None
                
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            return None
    
    def _try_text_extraction(self, pdf_bytes: BytesIO) -> Optional[str]:
        """Try extracting text from PDF."""
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_bytes)
            text = ""
            for page in pdf_reader.pages[:5]:  # First 5 pages
                text += page.extract_text()
            return text if len(text) > 100 else None
        except:
            return None
    
    def _extract_from_text(self, text: str) -> Optional[Dict]:
        """Extract structured data from text PDF using Gemma 3."""
        
        prompt = f"""Extract job recruitment information from this official notification.

NOTIFICATION TEXT:
{text[:50000]}

Return ONLY valid JSON with these fields:
{{
    "title": "Complete job title",
    "organization": "Organization/Department name",
    "vacancies": 120,
    "post_date": "DD-MM-YYYY",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale with amount",
    "age_limit": "Age requirement",
    "qualification": "Educational qualification required",
    "location": "Job location with state",
    "application_fee": {{"General/OBC": "Rs. 100", "SC/ST": "Nil"}},
    "advt_no": "Advertisement/Notification number",
    "application_url": "Online application URL",
    "official_website": "Organization website URL",
    "selection_process": "Selection/exam process",
    "how_to_apply": "Application instructions",
    "important_dates": {{
        "Application Start": "DD-MM-YYYY",
        "Application End": "DD-MM-YYYY",
        "Exam Date": "DD-MM-YYYY"
    }},
    "vacancy_details": {{
        "Post Name": "Count"
    }}
}}

CRITICAL RULES:
1. vacancies MUST be INTEGER (total count, not year)
2. Dates in DD-MM-YYYY format only
3. Extract exact values from text
4. Use null for fields not found
5. Return ONLY valid JSON, no markdown

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=None)
    
    def _extract_from_images(self, images: List) -> Optional[Dict]:
        """Extract structured data from PDF images using Gemma 3 Vision."""
        
        # Convert images to base64
        images_base64 = []
        for img in images:
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            images_base64.append(img_base64)
        
        prompt = """Analyze these scanned government job notification document images and extract ALL information.

Extract:
- Job title and organization name
- Total number of vacancies (COUNT as integer, not year)
- Important dates (application start, end, exam date)
- Salary/pay scale
- Age limit
- Educational qualification required
- Job location
- Application fee by category
- Selection process
- Application instructions
- Vacancy breakdown by post
- Advertisement/notification number
- URLs if shown

Return ONLY valid JSON:
{
    "title": "Complete job title from document",
    "organization": "Organization/Department name",
    "vacancies": 120,
    "post_date": "DD-MM-YYYY",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale",
    "age_limit": "Age requirement",
    "qualification": "Educational qualification",
    "location": "Location with state",
    "application_fee": {"General": "Rs. 100", "SC/ST": "Nil"},
    "advt_no": "Advertisement number",
    "application_url": "Apply URL if shown",
    "official_website": "Organization website if shown",
    "selection_process": "Selection method",
    "how_to_apply": "Application procedure",
    "important_dates": {
        "Application Start": "DD-MM-YYYY",
        "Application End": "DD-MM-YYYY",
        "Exam Date": "DD-MM-YYYY"
    },
    "vacancy_details": {
        "Post Name": "Count"
    }
}

CRITICAL:
- vacancies = INTEGER total count (NOT year like 2026)
- Read tables carefully
- Extract dates in DD-MM-YYYY format
- null for missing fields
- Return ONLY JSON, no markdown

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=images_base64)
    
    def generate_blog(self, job_data: Dict) -> Optional[Dict]:
        """Generate SEO-optimized blog from job data using Gemma 3."""
        
        if not self.is_available():
            logger.warning("Gemma 3 not available, skipping blog generation")
            return None
        
        prompt = f"""Create a comprehensive, SEO-optimized blog post for this job recruitment.

JOB DATA:
{json.dumps(job_data, indent=2)}

Generate a professional blog post with:

1. **SEO Title** (60-70 characters, include year and vacancy count)
2. **Meta Description** (150-160 characters, compelling and informative)
3. **Full Article** (800-1000 words in markdown format) with sections:
   - Brief Overview (2-3 sentences)
   - Key Highlights (5-7 bullet points with emojis like 🎯 📅 💰 🎓)
   - Important Dates (markdown table)
   - Vacancy Details/Post-wise Breakdown (if available)
   - Eligibility Criteria (qualification, age limit)
   - Salary & Benefits
   - Application Fee
   - Selection Process
   - How to Apply (step-by-step)
   - Important Links (official website, application, PDF)
   - Frequently Asked Questions (5-7 relevant FAQs)

4. **Highlights** (Array of 5 concise one-liner highlights)
5. **FAQs** (Array of 5-7 Q&A pairs)

REQUIREMENTS:
- Write in clear, professional, helpful tone
- Use markdown headings (##, ###)
- Add relevant emojis for engagement
- Natural keyword placement for SEO
- Make it informative and user-friendly
- Include all important details
- Add actionable advice in FAQs

Return ONLY valid JSON:
{{
    "seo_title": "Job Title Year - Apply for X Posts",
    "meta_description": "Complete details about...",
    "article": "Full markdown blog post content...",
    "highlights": [
        "Total Posts: X",
        "Last Date: DD-MM-YYYY",
        "Salary: Rs. X-Y",
        "Qualification: ...",
        "Apply Mode: Online/Offline"
    ],
    "faqs": [
        {{
            "question": "What is the last date to apply?",
            "answer": "The last date..."
        }},
        ...
    ]
}}

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=None, for_blog=True)
    
    def _call_gemma(self, prompt: str, images: Optional[List[str]] = None, for_blog: bool = False) -> Optional[Dict]:
        """Call Gemma 3 12B model."""
        
        try:
            messages = [{
                "role": "user",
                "content": prompt
            }]
            
            # Add images if provided
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
                        "temperature": 0.7 if for_blog else 0,
                        "num_predict": 3000 if for_blog else 2048,
                        "num_ctx": 128000  # Use full 128K context
                    }
                },
                timeout=120
            )
            
            if response.status_code == 200:
                content = response.json()['message']['content']
                
                # Clean and parse JSON
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
            logger.debug(f"Response content: {content[:200] if 'content' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Gemma 3 call failed: {e}")
            return None
