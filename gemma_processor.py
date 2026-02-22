"""Gemma 3 Processor - Extract fields from PDF or raw text.

This processor handles:
1. PDF extraction (multimodal Gemma 3)
2. Text extraction (text-only Gemma 3)
3. Blog generation

ALL content extraction goes through LLM.
"""

import logging
import requests
import base64
import os
import tempfile
from typing import Dict, Optional
import json
import re

from config import Config

logger = logging.getLogger(__name__)

class GemmaProcessor:
    """Gemma 3 processor for PDF and text extraction."""
    
    def __init__(self):
        """Initialize Gemma processor."""
        self.ollama_url = Config.OLLAMA_URL
        self.model = Config.OLLAMA_MODEL
        self._available = self._check_availability()
    
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
    
    def process_pdf_url(self, pdf_url: str) -> Optional[Dict]:
        """Download PDF and extract ALL fields using Gemma.
        
        Args:
            pdf_url: URL of PDF to download
        
        Returns:
            Dictionary with all extracted fields or None
        """
        try:
            # Download PDF
            logger.info(f"Downloading PDF from: {pdf_url[:70]}...")
            response = requests.get(pdf_url, timeout=60)
            response.raise_for_status()
            
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
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing PDF URL: {e}")
            return None
    
    def process_pdf_file(self, pdf_path: str) -> Optional[Dict]:
        """Extract ALL fields from PDF using multimodal Gemma.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            Dictionary with all extracted fields
        """
        try:
            # Read PDF as base64
            with open(pdf_path, 'rb') as f:
                pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Prompt for Gemma to extract ALL fields
            prompt = self._get_extraction_prompt()
            
            # Call Gemma with PDF
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [pdf_base64],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 2000
                    }
                },
                timeout=120
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
            logger.error(f"Error processing PDF with Gemma: {e}")
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
  "category": "Job category (banking/defence/railway/ssc/upsc/police/teaching/psu/state-govt/central-govt)",
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
- Return ONLY valid JSON
- Use "DD-MM-YYYY" format for dates
- vacancies must be integer (filter out years like 2026)
- For category, choose most appropriate from the list
- If field not found, use null or empty string
- Do not include markdown formatting
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
                    if value and str(value).strip().lower() not in ['null', 'none', 'n/a', '']:
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

Return ONLY valid JSON.
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
