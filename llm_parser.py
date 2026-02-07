"""LLM-based parser for extracting job data from HTML.

Configured for local Ollama (Llama 3.2 1B) with optimized prompts
for structured JSON output matching database schema.
"""

import logging
import json
import os
import re
from typing import Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class JobLLMParser:
    """Intelligent job data parser using local Ollama LLM."""
    
    # Complete database schema with detailed instructions
    SCHEMA_DEFINITION = {
        'title': {
            'type': 'text',
            'desc': 'Only the job title/post name (e.g., "Junior Engineer Recruitment 2026")',
            'example': 'UPSC Combined Medical Services Examination 2026'
        },
        'organization': {
            'type': 'text',
            'desc': 'Organization/department name where job is published',
            'example': 'Union Public Service Commission'
        },
        'post_date': {
            'type': 'date',
            'desc': 'Date when post was announced (DD-MM-YYYY)',
            'example': '15-01-2026'
        },
        'last_date': {
            'type': 'date',
            'desc': 'Last date for applying (DD-MM-YYYY)',
            'example': '28-02-2026'
        },
        'vacancies': {
            'type': 'integer',
            'desc': 'Total number of vacancies (extract number only)',
            'example': 150
        },
        'qualification': {
            'type': 'text',
            'desc': 'Educational qualification required',
            'example': 'Bachelor Degree in Engineering'
        },
        'location': {
            'type': 'text',
            'desc': 'Job location - include both city and state (e.g., "Mumbai, Maharashtra")',
            'example': 'New Delhi, Delhi'
        },
        'job_url': {
            'type': 'url',
            'desc': 'Organization website URL where job is posted (NOT FreeJobAlert URL)',
            'example': 'https://upsc.gov.in/recruitment/2026'
        },
        'application_url': {
            'type': 'url',
            'desc': 'Direct URL to apply online on organization website',
            'example': 'https://upsconline.nic.in/ora/VacancyNoticePub.php'
        },
        'official_website': {
            'type': 'url',
            'desc': 'Organization homepage URL',
            'example': 'https://upsc.gov.in'
        },
        'pdf_url': {
            'type': 'url',
            'desc': 'Official PDF notification link',
            'example': 'https://upsc.gov.in/sites/default/files/Advt_02_2026.pdf'
        },
        'category': {
            'type': 'text',
            'desc': 'Job category (UPSC/Railway/SSC/Banking/Apprenticeship/Internship/Teaching/Police/Defence/Medical/Engineering/Private)',
            'example': 'UPSC'
        },
        'advt_no': {
            'type': 'text',
            'desc': 'Advertisement number (starts with Advt/HRM/No/etc)',
            'example': 'Advt. No. 02/2026'
        },
        'salary': {
            'type': 'text',
            'desc': 'Salary/pay scale (numbers only with range)',
            'example': 'Rs. 56,100 - 1,77,500'
        },
        'age_limit': {
            'type': 'text',
            'desc': 'Age limit for applicants',
            'example': '21-32 years (as on 01-01-2026)'
        },
        'application_fee': {
            'type': 'json',
            'desc': 'Application fee in JSON format with category-wise breakdown',
            'example': {"General/OBC": "Rs. 100", "SC/ST/Women": "Nil", "PwD": "Nil"}
        },
        'selection_process': {
            'type': 'text',
            'desc': 'Selection/exam process details',
            'example': 'Written Exam + Interview'
        },
        'how_to_apply': {
            'type': 'text',
            'desc': 'Application instructions',
            'example': 'Apply online through official website'
        },
        'important_dates': {
            'type': 'json',
            'desc': 'Important dates in JSON format (keys: event name, values: date)',
            'example': {"Application Start": "15-01-2026", "Application End": "28-02-2026", "Admit Card": "March 2026", "Exam Date": "15-04-2026"}
        },
        'vacancy_details': {
            'type': 'json',
            'desc': 'Vacancy breakdown in JSON format (post name as key, number as value or details)',
            'example': {"Junior Engineer (Civil)": "50 posts", "Junior Engineer (Electrical)": "30 posts", "Junior Engineer (Mechanical)": "20 posts"}
        }
    }
    
    def __init__(self):
        """Initialize LLM parser for local Ollama."""
        self.provider = None
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.2:1b')  # Small & fast model
        
        # Check for local Ollama (PRIMARY)
        if self._check_ollama_available():
            self.provider = 'ollama'
            logger.info(f"✓ Using Ollama local with {self.ollama_model} (private & free)")
            logger.info(f"  Model info: Small parameter model optimized for speed")
        else:
            logger.warning("⚠️  Ollama not available. Please install and run:")
            logger.warning("   1. Install: curl -fsSL https://ollama.com/install.sh | sh")
            logger.warning(f"   2. Pull model: ollama pull {self.ollama_model}")
            logger.warning("   3. Start server: ollama serve")
    
    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            if response.status_code == 200:
                # Check if our model is available
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                if self.ollama_model in model_names or any(self.ollama_model.split(':')[0] in m for m in model_names):
                    return True
                else:
                    logger.warning(f"⚠️  Ollama running but model {self.ollama_model} not found")
                    logger.warning(f"   Available models: {', '.join(model_names[:3])}")
                    logger.warning(f"   Run: ollama pull {self.ollama_model}")
                    return False
            return False
        except Exception as e:
            logger.debug(f"Ollama check failed: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if LLM provider is available."""
        return self.provider is not None
    
    def _build_extraction_prompt(self, html: str, field_names: List[str]) -> str:
        """Build optimized prompt for field extraction with JSON schema."""
        
        # Build schema for requested fields
        schema_parts = []
        for field in field_names:
            if field in self.SCHEMA_DEFINITION:
                field_info = self.SCHEMA_DEFINITION[field]
                schema_parts.append(f"\n  \"{field}\": {{")
                schema_parts.append(f"    Type: {field_info['type']}")
                schema_parts.append(f"    Description: {field_info['desc']}")
                if 'example' in field_info:
                    example_str = json.dumps(field_info['example']) if isinstance(field_info['example'], (dict, list)) else f"\"{field_info['example']}\""
                    schema_parts.append(f"    Example: {example_str}")
                schema_parts.append("  }")
        
        schema_text = "\n".join(schema_parts)
        
        # Optimized prompt for small models
        prompt = f"""Extract job details from HTML and return ONLY valid JSON.

REQUIRED FIELDS:
{schema_text}

IMPORTANT RULES:
1. Return ONLY valid JSON object (no markdown, no explanation)
2. Use null for fields not found in HTML
3. For dates: DD-MM-YYYY format
4. For URLs: Full URL with http/https (prefer organization URLs, not FreeJobAlert)
5. For JSON fields (application_fee, important_dates, vacancy_details): Use proper JSON objects
6. For location: Include city AND state (e.g., "Mumbai, Maharashtra")
7. For category: Choose from [UPSC, Railway, SSC, Banking, Apprenticeship, Internship, Teaching, Police, Defence, Medical, Engineering, Private]
8. For vacancies: Extract number only (e.g., 150, not "150 posts")
9. For salary: Keep numbers with range (e.g., "56,100 - 1,77,500")
10. Extract exact data from HTML, don't make up information

HTML CONTENT:
{html[:12000]}

JSON OUTPUT:"""
        
        return prompt
    
    def _clean_json_response(self, content: str) -> str:
        """Clean LLM response to extract valid JSON."""
        # Remove markdown code blocks
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        
        # Find JSON object
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end > start:
            content = content[start:end]
        
        return content.strip()
    
    def _parse_with_ollama(self, html: str, field_names: List[str]) -> Dict:
        """Parse using local Ollama with optimized settings."""
        try:
            prompt = self._build_extraction_prompt(html, field_names)
            
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise data extractor. Extract job information from HTML and return ONLY valid JSON. No explanations, no markdown, just pure JSON object."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0,
                        "top_p": 0.9,
                        "num_predict": 2048,
                        "stop": ["\n\n\n"]
                    }
                },
                timeout=60  # Increased timeout for local processing
            )
            
            if response.status_code == 200:
                content = response.json()['message']['content']
                
                # Clean response
                content = self._clean_json_response(content)
                
                # Parse JSON
                result = json.loads(content)
                
                # Post-process: ensure proper types
                if 'vacancies' in result and result['vacancies']:
                    # Extract number from vacancies
                    if isinstance(result['vacancies'], str):
                        numbers = re.findall(r'\d+', result['vacancies'])
                        if numbers:
                            result['vacancies'] = int(numbers[0])
                
                # Ensure JSON fields are proper JSON
                for json_field in ['application_fee', 'important_dates', 'vacancy_details']:
                    if json_field in result and isinstance(result[json_field], str):
                        try:
                            result[json_field] = json.loads(result[json_field])
                        except:
                            pass
                
                return result
            else:
                logger.error(f"Ollama error: {response.status_code} - {response.text}")
                return {}
                
        except json.JSONDecodeError as e:
            logger.error(f"Ollama returned invalid JSON: {e}")
            logger.debug(f"Response content: {content[:200]}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing with Ollama: {e}")
            return {}
    
    def parse_missing_fields(self, html: str, field_names: List[str]) -> Dict:
        """Parse fields from HTML using local Ollama.
        
        Args:
            html: Raw HTML content
            field_names: List of field names to extract
            
        Returns:
            Dictionary with extracted field values
        """
        if not self.is_available():
            logger.warning("No LLM provider available, skipping LLM parsing")
            return {}
        
        if not field_names:
            logger.debug("No fields to parse")
            return {}
        
        logger.info(f"🤖 Using LLM (Ollama {self.ollama_model}) to extract {len(field_names)} fields")
        
        result = self._parse_with_ollama(html, field_names)
        
        # Log what was extracted
        extracted_count = len([v for v in result.values() if v])
        logger.info(f"  ✓ LLM extracted {extracted_count}/{len(field_names)} fields")
        
        for field, value in result.items():
            if value:
                if isinstance(value, (dict, list)):
                    logger.debug(f"    - {field}: {json.dumps(value)[:60]}")
                else:
                    value_preview = str(value)[:60]
                    logger.debug(f"    - {field}: {value_preview}")
        
        return result
    
    def parse_full_job(self, html: str) -> Dict:
        """Parse all job fields from HTML.
        
        Args:
            html: Raw HTML content
            
        Returns:
            Dictionary with all extracted fields
        """
        all_fields = list(self.SCHEMA_DEFINITION.keys())
        return self.parse_missing_fields(html, all_fields)
