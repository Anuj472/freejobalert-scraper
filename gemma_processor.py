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
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
import PyPDF2
from pdf2image import convert_from_bytes

logger = logging.getLogger(__name__)

class Gemma3Processor:
    """Process PDFs and generate blogs using Gemma 3 12B multimodal model."""
    
    def __init__(self):
        """Initialize Gemma 3 processor."""
        self.ollama_url = "http://localhost:11434"
        self.model = "gemma3:12b"
        self.available = self._check_availability()
        
        if self.available:
            logger.info(f"✓ {self.model} initialized")
            logger.info(f"  - Vision: ✓ (for scanned PDFs)")
            logger.info(f"  - Text: ✓ (for text PDFs)")
            logger.info(f"  - Context: 128K tokens")
            logger.info(f"  - VRAM: ~8GB")
    
    def _check_availability(self) -> bool:
        """Check if Gemma 3 model is available."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = [m['name'] for m in response.json().get('models', [])]
                if self.model in models:
                    return True
                else:
                    logger.warning(f"⚠️  {self.model} not found")
                    logger.warning(f"   Install with: ollama pull {self.model}")
                    return False
        except Exception as e:
            logger.warning(f"⚠️  Ollama not available: {e}")
            logger.warning(f"   Install: curl -fsSL https://ollama.com/install.sh | sh")
            return False
    
    def is_available(self) -> bool:
        """Check if processor is ready to use."""
        return self.available
    
    def process_pdf_url(self, pdf_url: str) -> Optional[Dict]:
        """
        Download and process PDF (text or image) using Gemma 3.
        
        Args:
            pdf_url: URL of PDF to process
            
        Returns:
            Dictionary with extracted job data
        """
        if not self.available:
            return None
        
        try:
            # Download PDF
            logger.info(f"📥 Downloading PDF: {pdf_url[:60]}...")
            response = requests.get(pdf_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            pdf_bytes = response.content
            
            # Try text extraction first (fast path)
            logger.info("🔍 Checking if PDF is text-based...")
            text = self._extract_text_from_pdf(pdf_bytes)
            
            if text and len(text) > 500:
                # Text PDF - use Gemma 3 with text
                logger.info(f"📄 Text PDF detected ({len(text)} chars), processing with Gemma 3...")
                return self._extract_from_text(text)
            else:
                # Scanned/Image PDF - use Gemma 3 vision
                logger.info("🖼️  Image/Scanned PDF detected, using Gemma 3 Vision...")
                return self._extract_from_images(pdf_bytes)
        
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            return None
    
    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from PDF if it's text-based."""
        try:
            pdf_file = BytesIO(pdf_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages[:10]:  # First 10 pages
                text += page.extract_text() or ""
            
            return text if len(text) > 100 else None
        except:
            return None
    
    def _extract_from_text(self, text: str) -> Optional[Dict]:
        """Extract structured data from text PDF using Gemma 3."""
        
        prompt = f"""Extract job recruitment information from this official notification document.

DOCUMENT TEXT:
{text[:50000]}

Extract and return ONLY valid JSON with these fields:
{{
    "title": "Full job title",
    "organization": "Organization/Department name",
    "vacancies": 120,
    "post_date": "DD-MM-YYYY",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale details",
    "age_limit": "Age requirement",
    "qualification": "Educational qualification required",
    "location": "Job location with state",
    "application_fee": {{"General/OBC": "Rs. 100", "SC/ST/Women": "Nil"}},
    "advt_no": "Advertisement/Notification number",
    "application_url": "Online application URL",
    "official_website": "Organization website URL",
    "selection_process": "Selection/examination method",
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
2. Dates in DD-MM-YYYY format
3. Extract exact values from document
4. Use null for fields not found
5. Return ONLY valid JSON

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=None)
    
    def _extract_from_images(self, pdf_bytes: bytes) -> Optional[Dict]:
        """Extract from scanned/image PDF using Gemma 3 Vision."""
        
        try:
            # Convert PDF to images (first 3 pages usually have all info)
            logger.info("📸 Converting PDF pages to images...")
            images = convert_from_bytes(
                pdf_bytes,
                dpi=200,
                fmt='jpeg',
                first_page=1,
                last_page=3  # First 3 pages
            )
            
            logger.info(f"✓ Converted {len(images)} pages to images")
            
            # Convert images to base64
            images_base64 = []
            for img in images:
                buffered = BytesIO()
                img.save(buffered, format="JPEG", quality=85)
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                images_base64.append(img_base64)
            
            prompt = """Extract ALL job recruitment information from these scanned document images.

Read the document carefully and extract complete details including tables, dates, and vacancy breakdown.

Return ONLY valid JSON:
{
    "title": "Full job title from document",
    "organization": "Organization/Department name",
    "vacancies": 120,
    "post_date": "DD-MM-YYYY",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale",
    "age_limit": "Age requirement",
    "qualification": "Educational qualification",
    "location": "Job location",
    "application_fee": {"General": "Rs. 100", "SC/ST": "Nil"},
    "advt_no": "Advertisement number",
    "application_url": "Apply URL",
    "official_website": "Organization website",
    "selection_process": "Selection method",
    "how_to_apply": "Application instructions",
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
- vacancies is INTEGER (total count, NOT year like 2026)
- Read tables carefully for vacancy details
- Extract exact dates from document
- Return ONLY valid JSON

JSON OUTPUT:"""

            return self._call_gemma(prompt, images=images_base64)
        
        except Exception as e:
            logger.error(f"Error extracting from images: {e}")
            return None
    
    def generate_blog(self, job_data: Dict) -> Optional[Dict]:
        """
        Generate SEO-optimized blog using Gemma 3.
        
        Args:
            job_data: Structured job data
            
        Returns:
            Dictionary with blog content
        """
        if not self.available:
            return None
        
        prompt = f"""You are an expert SEO content writer for a job portal. Create a comprehensive, engaging blog post about this job opportunity.

JOB DATA:
{json.dumps(job_data, indent=2)}

Generate a complete blog post with:

1. **SEO Title** (60-70 characters, include year and vacancy count)
2. **Meta Description** (150-160 characters, compelling call-to-action)
3. **Full Article** (800-1000 words) in Markdown format with:
   - Brief Overview (2-3 sentences)
   - Key Highlights (5-7 bullet points with emojis: 🎯 📅 💰 🎓 📍)
   - Important Dates (table format)
   - Vacancy Details (table if available)
   - Eligibility Criteria (age, qualification)
   - Salary & Benefits
   - Application Fee (table by category)
   - Selection Process
   - How to Apply (step-by-step)
   - Important Links (with clear labels)
   - Frequently Asked Questions (5-7 FAQs)

4. **Highlights Array** (5 one-liner key points)
5. **FAQs Array** (question-answer pairs)

Return JSON:
{{
    "seo_title": "Job Title Year - Apply Online for X Posts",
    "meta_description": "Compelling 150-char description...",
    "article": "# Full Blog Title\\n\\n## Overview\\n...full markdown content...",
    "highlights": [
        "📌 Total Posts: X",
        "📅 Last Date: DD Month YYYY",
        "💰 Salary: Rs. X - Y",
        "🎓 Qualification: ...",
        "📍 Location: ..."
    ],
    "faqs": [
        {{"question": "What is the last date to apply?", "answer": "..."}},
        {{"question": "What is the application fee?", "answer": "..."}},
        {{"question": "What is the selection process?", "answer": "..."}},
        {{"question": "What is the age limit?", "answer": "..."}},
        {{"question": "How to apply online?", "answer": "..."}}
    ]
}}

REQUIREMENTS:
- Use markdown headings (##, ###)
- Add relevant emojis for engagement
- Include tables where appropriate
- Natural keyword placement
- Clear, helpful tone
- SEO optimized for Google

Return ONLY valid JSON:"""

        return self._call_gemma(prompt, images=None, for_blog=True)
    
    def _call_gemma(self, prompt: str, images: Optional[List[str]] = None, for_blog: bool = False) -> Optional[Dict]:
        """Call Gemma 3 model (with or without images)."""
        
        try:
            messages = [{
                "role": "user",
                "content": prompt
            }]
            
            # Add images if provided (for vision tasks)
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
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()
                
                data = json.loads(content)
                
                task_type = "blog" if for_blog else ("vision extraction" if images else "text extraction")
                logger.info(f"✓ Gemma 3 {task_type} successful")
                
                return data
            else:
                logger.error(f"Gemma 3 API error: {response.status_code}")
                return None
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemma 3 JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"Gemma 3 call failed: {e}")
            return None
