"""Gemma 3 12B Multimodal Processor - IMPROVED VERSION with 8-bit quantization."""

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
    """Process PDFs and generate blogs using Gemma 3 with 8-bit quantization."""
    
    def __init__(self):
        """Initialize Gemma 3 12B processor with optimized settings."""
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model = "gemma3:12b"
        self.temp_dir = Path('temp_pdfs')
        self.temp_dir.mkdir(exist_ok=True)
        
        if self._check_model_available():
            logger.info(f"✓ {self.model} initialized")
            logger.info(f"  - Vision: ✓")
            logger.info(f"  - Quantization: 8-bit (faster inference)")
            logger.info(f"  - Context: 32K tokens")
            logger.info(f"  - VRAM: ~4-5 GB (optimized)")
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
        IMPROVED: Focused prompts, no URL extraction.
        """
        if not self.is_available():
            logger.warning("Gemma 3 not available, skipping PDF processing")
            return None
        
        try:
            logger.info(f"📥 Downloading PDF: {pdf_url[:60]}...")
            
            # Download PDF with INCREASED timeout (90 seconds for slow servers)
            response = requests.get(pdf_url, timeout=90, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            pdf_bytes = BytesIO(response.content)
            
            # Try text extraction first (fast path)
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
                
                images = convert_from_path(
                    temp_pdf,
                    dpi=200,
                    fmt='jpeg',
                    first_page=1,
                    last_page=3
                )
                
                logger.info(f"✓ Converted {len(images)} pages to images")
                
                result = self._extract_from_images_focused(images)
                temp_pdf.unlink()
                
                return result
            else:
                logger.warning("pdf2image not available, cannot process image PDFs")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"PDF download timeout after 90 seconds: {pdf_url[:60]}")
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
        """
        IMPROVED: Extract with focused, specific questions.
        NO URL extraction - HTML parser will handle that.
        DO NOT extract post_date - HTML parser will handle that.
        """
        
        # Truncate text to fit context (32K tokens)
        text = text[:40000]  # Reduced from 50K
        
        prompt = f"""You are analyzing a government job recruitment notification document.

DOCUMENT TEXT:
{text}

Answer these SPECIFIC questions by carefully reading the document. Return ONLY valid JSON.

CRITICAL RULES:
1. DO NOT extract or include ANY URLs, links, or web addresses
2. DO NOT extract post_date (notification publish date) - only extract last_date (application deadline)
3. Vacancies MUST be INTEGER count (e.g., 100, 50, 25) NOT year (2026)
4. Dates in DD-MM-YYYY format only
5. Use null for fields not found in document
6. Be precise and extract EXACT values from document

Questions to answer:

1. What is the EXACT job title or post name?
   Example: "Assistant Engineer", "Staff Nurse", "Clerk Grade II"

2. What is the EXACT organization/department/commission name?
   Example: "Indian Railways", "State Bank of India", "UPSC"

3. **IMPORTANT: What CATEGORY does this job belong to?**
   Based on the organization type, choose the MOST APPROPRIATE category:
   
   - "banking" - If organization is: SBI, IBPS, RBI, Bank of India, Canara Bank, PNB, any bank
   - "defence" - If organization is: Indian Army, Navy, Air Force, DRDO, OTA, NDA, Coast Guard
   - "railway" - If organization is: Indian Railways, RRB, Railway Recruitment Board, IRCTC
   - "ssc" - If organization is: Staff Selection Commission, SSC
   - "upsc" - If organization is: Union Public Service Commission, UPSC
   - "police" - If organization is: Police Department, State Police, Central Police
   - "teaching" - If organization is: University, School, Education Department, UGC, NCERT
   - "psu" - If organization is: NTPC, ONGC, SAIL, BHEL, Coal India, any PSU
   - "state-govt" - If organization is: State Government Department (not railway/police)
   - "central-govt" - If organization is: Central Government Department (not SSC/UPSC/Railway)
   - "admit-card" - If document is about admit card
   - "result" - If document is about result/answer key
   - "answer-key" - If document is about answer key
   
   Examples:
   - "Union Public Service Commission" → category: "upsc"
   - "State Bank of India" → category: "banking"
   - "Indian Railways" → category: "railway"
   - "Indian Army" → category: "defence"
   - "Staff Selection Commission" → category: "ssc"

4. How many TOTAL vacancies are there? (INTEGER count, NOT year)
   Look for: "Total Posts", "Total Vacancies", numbers in tables
   Example: 150 (not 2026)

5. What is the advertisement/notification number?
   Example: "Advt. No. 01/2026", "Notification No. 12345"

6. What is the LAST DATE to apply? (Application deadline, NOT notification date)
   Look for: "Last Date", "Closing Date", "Apply By"
   Format: DD-MM-YYYY
   Example: "15-02-2026"

7. What is the salary or pay scale mentioned?
   Example: "Rs. 25,000 - 50,000", "Level 7, Rs. 44,900"

8. What is the age limit for applicants?
   Example: "21-30 years", "18-35 years as on 01-01-2026"

9. What educational qualification is required?
   Example: "Bachelor's Degree in Engineering", "10th Pass", "Graduate"

10. **IMPORTANT: What is the job location or posting place?**
    Look carefully for: "Place of Posting", "Location", "Work Location", "Job Station"
    - Check if it mentions specific cities: Delhi, Mumbai, Bangalore, etc.
    - Check if it mentions states: Maharashtra, Karnataka, UP, etc.
    - Check if it mentions regions: North India, South India, All India
    - Look in vacancy tables for location columns
    Example: "New Delhi", "Mumbai, Maharashtra", "All India", "Various locations across India"

11. What is the application fee for different categories?
     Example: {{"General/OBC": "Rs. 500", "SC/ST/PH": "Rs. 250", "Women": "Rs. 250"}}

12. What is the selection process or exam pattern?
     Example: "Written Exam + Interview", "CBT + Physical Test"

13. How should candidates apply? (Step-by-step instructions from document)
     Example: "Apply online through official website"

14. Important dates mentioned?
     - Application start date? (DD-MM-YYYY)
     - Application end date / Last date? (DD-MM-YYYY)
     - Exam date if mentioned? (DD-MM-YYYY)

15. Is there a post-wise vacancy breakdown in tables?
     Example: {{"Engineer": "50", "Assistant": "100"}}

Return ONLY this JSON structure:
{{
    "title": "Exact job title from document",
    "organization": "Exact organization name",
    "category": "banking/defence/railway/ssc/upsc/police/teaching/psu/state-govt/central-govt",
    "vacancies": 120,
    "advt_no": "Advertisement number",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale details",
    "age_limit": "Age requirement",
    "qualification": "Educational qualification",
    "location": "Job location with city/state",
    "application_fee": {{"General": "Rs. X", "SC/ST": "Nil"}},
    "selection_process": "Exam/selection method",
    "how_to_apply": "Application instructions",
    "important_dates": {{
        "Application Start": "DD-MM-YYYY or null",
        "Application End": "DD-MM-YYYY",
        "Exam Date": "DD-MM-YYYY or null"
    }},
    "vacancy_details": {{
        "Post Name 1": "Count",
        "Post Name 2": "Count"
    }}
}}

REMEMBER:
- NO URLs or links
- NO post_date field
- Category = Based on organization type (banking/defence/railway/ssc/upsc/etc.)
- Vacancies = INTEGER count
- Location = MUST extract carefully
- last_date = Application deadline only
- Dates = DD-MM-YYYY
- null if not found

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=None, timeout=90)  # Reduced from 120s
    
    def _extract_from_images_focused(self, images: List) -> Optional[Dict]:
        """
        IMPROVED: Extract from images with focused questions.
        NO URL extraction.
        NO post_date extraction.
        """
        
        # Convert images to base64
        images_base64 = []
        for img in images:
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            images_base64.append(img_base64)
        
        prompt = """You are analyzing scanned images of a government job notification document.

Answer these SPECIFIC questions by carefully reading all images. Return ONLY valid JSON.

CRITICAL RULES:
1. DO NOT extract or include ANY URLs, links, or web addresses
2. DO NOT extract post_date (notification date) - only last_date (application deadline)
3. Read tables carefully - vacancies = INTEGER count (e.g., 50, 100) NOT year (2026)
4. Dates in DD-MM-YYYY format
5. Use null for fields you cannot find
6. Extract EXACT text you see

Questions:

1. What is the EXACT job title/post name shown?

2. What is the EXACT organization/department name?

3. **CRITICAL: What CATEGORY does this job belong to?**
   Look at the organization name/logo and determine the category:
   
   - "banking" - Banks: SBI, IBPS, RBI, PNB, Bank of India, etc.
   - "defence" - Armed Forces: Army, Navy, Air Force, DRDO, NDA, etc.
   - "railway" - Indian Railways, RRB, Railway Recruitment Board
   - "ssc" - Staff Selection Commission
   - "upsc" - Union Public Service Commission
   - "police" - Police Department, State/Central Police
   - "teaching" - Universities, Schools, Education Dept
   - "psu" - PSUs: NTPC, ONGC, SAIL, BHEL, etc.
   - "state-govt" - State Government Departments
   - "central-govt" - Central Government Departments
   - "admit-card" - If this is an admit card document
   - "result" - If this is a result document
   
   Choose the MOST APPROPRIATE category based on what you see.

4. How many TOTAL vacancies? (Look in tables, INTEGER count only, NOT year)

5. What is the notification/advertisement number?

6. What is the LAST DATE to apply? (Application deadline, NOT notification date)
   Format: DD-MM-YYYY

7. Salary or pay scale?

8. Age limit for applicants?

9. Educational qualification required?

10. **CRITICAL: What is the job LOCATION?**
    Look for: Place of Posting, Location, Work Station
    Extract city/state/region mentioned

11. Application fee by category?

12. Selection process or exam pattern?

13. How to apply? (Steps visible)

14. Important dates:
     - Application start? (DD-MM-YYYY)
     - Last date? (DD-MM-YYYY)
     - Exam date? (DD-MM-YYYY)

15. Post-wise vacancy breakdown?

Return ONLY this JSON:
{
    "title": "Exact job title",
    "organization": "Exact organization name",
    "category": "banking/defence/railway/ssc/upsc/police/teaching/psu/state-govt/central-govt",
    "vacancies": 100,
    "advt_no": "Notification number",
    "last_date": "DD-MM-YYYY",
    "salary": "Pay scale",
    "age_limit": "Age requirement",
    "qualification": "Education required",
    "location": "Job location/posting place",
    "application_fee": {"General": "Rs. X", "SC/ST": "Nil"},
    "selection_process": "Selection method",
    "how_to_apply": "Application steps",
    "important_dates": {
        "Application Start": "DD-MM-YYYY or null",
        "Application End": "DD-MM-YYYY",
        "Exam Date": "DD-MM-YYYY or null"
    },
    "vacancy_details": {
        "Post 1": "Count",
        "Post 2": "Count"
    }
}

REMEMBER:
- NO URLs
- NO post_date
- Category = Based on organization (banking/defence/railway/etc.)
- Vacancies = INTEGER count
- Location = MUST extract
- last_date = Application deadline
- Dates = DD-MM-YYYY
- null if not visible

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=images_base64, timeout=90)  # Reduced from 120s
    
    def generate_blog(self, job_data: Dict) -> Optional[Dict]:
        """
        IMPROVED: Generate concise SEO blog UNDER 1000 words.
        """
        
        if not self.is_available():
            logger.warning("Gemma 3 not available, skipping blog generation")
            return None
        
        # Prepare clean data (remove None values)
        clean_data = {k: v for k, v in job_data.items() if v is not None}
        
        prompt = f"""Create a CONCISE, SEO-optimized blog post for this job recruitment.

JOB DATA:
{json.dumps(clean_data, indent=2)}

REQUIREMENTS:
1. WORD LIMIT: Maximum 800-900 words (be concise!)
2. SEO Title: 60-70 characters
3. Meta Description: 150-160 characters
4. Blog Structure:
   - Brief Overview (2-3 sentences)
   - 🎯 Key Highlights (5 bullet points with emojis)
   - 📅 Important Dates (markdown table)
   - 📋 Eligibility (qualification, age limit)
   - 💰 Salary & Fee Details
   - 📝 How to Apply (4-5 steps)
   - ❓ FAQs (5 questions)

5. IMPORTANT:
   - Use markdown headings (##, ###)
   - Add emojis for engagement
   - Keep language simple and clear
   - Focus on KEY information only
   - NO fluff or repetition
   - Be helpful and direct

6. Provide 5 one-liner highlights and 5 FAQs

Return ONLY valid JSON:
{{
    "seo_title": "Job Title 2026 - X Posts | Last Date",
    "meta_description": "Complete details about...",
    "article": "Full markdown blog (800-900 words MAX)...",
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
        }},
        {{
            "question": "How many posts?",
            "answer": "Brief answer..."
        }},
        {{
            "question": "What is the qualification?",
            "answer": "Brief answer..."
        }},
        {{
            "question": "What is the salary?",
            "answer": "Brief answer..."
        }},
        {{
            "question": "How to apply?",
            "answer": "Brief answer..."
        }}
    ]
}}

CRITICAL:
- Blog article MUST be under 1000 words
- Be concise and to-the-point
- Focus on IMPORTANT details only
- Use tables for dates/fees

JSON OUTPUT:"""

        return self._call_gemma(prompt, images=None, for_blog=True, timeout=180)  # Reduced from 300s
    
    def _call_gemma(self, prompt: str, images: Optional[List[str]] = None, 
                    for_blog: bool = False, timeout: int = 90) -> Optional[Dict]:
        """Call Gemma 3 12B model with 8-bit quantization optimizations."""
        
        try:
            messages = [{
                "role": "user",
                "content": prompt
            }]
            
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
                        "temperature": 0.7 if for_blog else 0.1,  # Lower temp for extraction
                        "num_predict": 2500 if for_blog else 2048,  # Token limit
                        "num_ctx": 32768,  # Reduced from 128K for speed (32K is enough)
                        "num_gpu": 99,  # Force GPU usage
                        "num_thread": 8,  # CPU threads for CPU layers
                        "f16_kv": True,  # Use FP16 for key/value cache (faster)
                        "low_vram": False,  # We want speed, not VRAM savings
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
            logger.debug(f"Response: {content[:200] if 'content' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Gemma 3 call failed: {e}")
            return None
