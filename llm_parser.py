"""LLM-based parser for extracting job data from HTML.

Improved architecture: Feed raw HTML → LLM extracts everything → Structured JSON
Fixed: Vacancies extraction (was getting year 2026 instead of count)
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
            'desc': 'Only the job title/post name',
            'example': 'Junior Engineer Recruitment'
        },
        'organization': {
            'type': 'text',
            'desc': 'Organization/department name where job is published',
            'example': 'Railway Recruitment Board'
        },
        'post_date': {
            'type': 'date',
            'desc': 'Date when post was announced (DD-MM-YYYY format)',
            'example': '15-01-2026'
        },
        'last_date': {
            'type': 'date',
            'desc': 'Last date for applying (DD-MM-YYYY format)',
            'example': '28-02-2026'
        },
        'vacancies': {
            'type': 'integer',
            'desc': 'IMPORTANT: Total NUMBER of job openings/positions. DO NOT extract year. Look for: "Total Posts: 150", "Vacancies: 80", "20 Posts". Return ONLY the count as integer.',
            'example': 150,
            'wrong_examples': ['2026', '2025-26', 'Various']  # What NOT to extract
        },
        'qualification': {
            'type': 'text',
            'desc': 'Educational qualification required',
            'example': 'Bachelor Degree in Engineering'
        },
        'location': {
            'type': 'text',
            'desc': 'Job location with city AND state (e.g., "Mumbai, Maharashtra"). If only city given, add state.',
            'example': 'New Delhi, Delhi'
        },
        'job_url': {
            'type': 'url',
            'desc': 'Organization website URL where job is posted (NOT FreeJobAlert URL)',
            'example': 'https://rrb.gov.in/recruitment/2026'
        },
        'application_url': {
            'type': 'url',
            'desc': 'Direct URL to apply online on organization website',
            'example': 'https://rrb.gov.in/apply'
        },
        'official_website': {
            'type': 'url',
            'desc': 'Organization homepage URL',
            'example': 'https://rrb.gov.in'
        },
        'pdf_url': {
            'type': 'url',
            'desc': 'Official PDF notification link',
            'example': 'https://rrb.gov.in/files/advt_2026.pdf'
        },
        'category': {
            'type': 'text',
            'desc': 'Job category. Choose ONE from: UPSC, Railway, SSC, Banking, Apprenticeship, Internship, Teaching, Police, Defence, Medical, Engineering, Private, Others',
            'example': 'Railway'
        },
        'advt_no': {
            'type': 'text',
            'desc': 'Advertisement number (starts with Advt/HRM/No/Notification)',
            'example': 'Advt. No. 02/2026'
        },
        'salary': {
            'type': 'text',
            'desc': 'Salary/pay scale with numbers and range',
            'example': 'Rs. 56,100 - 1,77,500 per month'
        },
        'age_limit': {
            'type': 'text',
            'desc': 'Age limit for applicants',
            'example': '21-32 years as on 01-01-2026'
        },
        'application_fee': {
            'type': 'json',
            'desc': 'Application fee as JSON with category breakdown. Format: {"Category": "Amount"}',
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
            'desc': 'Important dates as JSON. Format: {"Event": "Date"}',
            'example': {"Application Start": "15-01-2026", "Application End": "28-02-2026", "Exam Date": "15-04-2026"}
        },
        'vacancy_details': {
            'type': 'json',
            'desc': 'Vacancy breakdown as JSON. Format: {"Post Name": "Count"} or {"Post Name": {"Count": 50, "Category": "UR-30, OBC-15, SC-5"}}',
            'example': {"Junior Engineer Civil": "50", "Junior Engineer Electrical": "30"}
        }
    }
    
    def __init__(self):
        """Initialize LLM parser for local Ollama."""
        self.provider = None
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.2:1b')
        
        if self._check_ollama_available():
            self.provider = 'ollama'
            logger.info(f"✓ Using Ollama local with {self.ollama_model} (private & free)")
        else:
            logger.warning("⚠️  Ollama not available")
            logger.warning(f"   Run: ollama pull {self.ollama_model} && ollama serve")
    
    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def is_available(self) -> bool:
        """Check if LLM provider is available."""
        return self.provider is not None
    
    def _build_full_extraction_prompt(self, html: str) -> str:
        """Build comprehensive prompt for extracting ALL fields at once.
        
        This is the better architecture: Feed raw HTML → Get structured JSON
        """
        
        prompt = f"""You are a job posting data extractor. Extract ALL information from this HTML and return ONLY valid JSON.

DATABASE SCHEMA - Extract these fields:

1. title (text): Job title only. Example: "Junior Engineer Recruitment"

2. organization (text): Hiring organization name. Example: "Railway Recruitment Board"

3. post_date (date): Post announcement date in DD-MM-YYYY format. Example: "15-01-2026"

4. last_date (date): Application deadline in DD-MM-YYYY format. Example: "28-02-2026"

5. vacancies (integer): ⚠️ CRITICAL - Extract TOTAL NUMBER of job positions.
   - Look for: "Total Posts: 150" or "Vacancies: 80" or "20 Posts"
   - Return ONLY the number as integer: 150 or 80 or 20
   - DO NOT extract year (2026) or session (2025-26)
   - If text says "20 Posts" return: 20
   - If text says "Total: 150 vacancies" return: 150
   - Example correct: 150
   - Example WRONG: 2026, "150 posts", "Various"

6. qualification (text): Education required. Example: "Bachelor Degree"

7. location (text): Job location with city and state. Example: "Mumbai, Maharashtra"

8. job_url (url): Organization website URL (not FreeJobAlert). Example: "https://rrb.gov.in"

9. application_url (url): Apply online URL. Example: "https://rrb.gov.in/apply"

10. official_website (url): Organization homepage. Example: "https://rrb.gov.in"

11. pdf_url (url): Notification PDF URL. Example: "https://rrb.gov.in/advt.pdf"

12. category (text): Choose ONE: UPSC, Railway, SSC, Banking, Teaching, Police, Defence, Medical, Engineering, Private, Others

13. advt_no (text): Advertisement number. Example: "Advt. No. 02/2026"

14. salary (text): Pay scale. Example: "Rs. 56,100 - 1,77,500"

15. age_limit (text): Age requirement. Example: "21-32 years"

16. application_fee (JSON object): Fee by category.
    Example: {{"General/OBC": "Rs. 100", "SC/ST/Women": "Nil"}}

17. selection_process (text): Exam/selection method. Example: "Written Exam + Interview"

18. how_to_apply (text): Application steps. Example: "Apply online"

19. important_dates (JSON object): Key dates.
    Example: {{"Application Start": "15-01-2026", "Application End": "28-02-2026", "Exam Date": "15-04-2026"}}

20. vacancy_details (JSON object): Post-wise breakdown.
    Example: {{"Junior Engineer Civil": "50", "Junior Engineer Electrical": "30"}}

RULES:
- Return ONLY valid JSON (no markdown, no explanation)
- Use null for fields not found
- For vacancies: MUST be integer (not string, not year)
- For dates: DD-MM-YYYY format
- For JSON fields: Use proper JSON objects
- Extract exact data from HTML

HTML CONTENT:
{html[:15000]}

Return JSON with ALL 20 fields:"""
        
        return prompt
    
    def _build_extraction_prompt(self, html: str, field_names: List[str]) -> str:
        """Build prompt for extracting specific fields (backward compatibility)."""
        
        schema_parts = []
        for i, field in enumerate(field_names, 1):
            if field in self.SCHEMA_DEFINITION:
                field_info = self.SCHEMA_DEFINITION[field]
                schema_parts.append(f"\n{i}. {field} ({field_info['type']}):")
                schema_parts.append(f"   {field_info['desc']}")
                
                if 'example' in field_info:
                    if isinstance(field_info['example'], (dict, list)):
                        schema_parts.append(f"   Example: {json.dumps(field_info['example'])}")
                    else:
                        schema_parts.append(f"   Example: {field_info['example']}")
                
                # Add wrong examples for critical fields
                if 'wrong_examples' in field_info:
                    schema_parts.append(f"   WRONG: {', '.join(map(str, field_info['wrong_examples']))}")
        
        schema_text = "\n".join(schema_parts)
        
        prompt = f"""Extract job information from HTML and return ONLY valid JSON.

FIELDS TO EXTRACT:
{schema_text}

CRITICAL RULES:
1. Return ONLY valid JSON object (no markdown, no text)
2. Use null for fields not found
3. For vacancies: Extract NUMBER of positions (not year!)
   - "20 Posts" → 20
   - "Total: 150" → 150
   - NOT 2026 or 2025-26
4. For dates: DD-MM-YYYY format
5. For JSON fields: Use proper JSON objects
6. Extract exact data from HTML

HTML:
{html[:12000]}

JSON OUTPUT:"""
        
        return prompt
    
    def _clean_json_response(self, content: str) -> str:
        """Clean LLM response to extract valid JSON."""
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end > start:
            content = content[start:end]
        
        return content.strip()
    
    def _fix_vacancies(self, result: Dict) -> Dict:
        """Fix vacancies field - ensure it's a number, not year."""
        if 'vacancies' in result:
            val = result['vacancies']
            
            # If it's already a valid number < 10000, keep it
            if isinstance(val, int) and 1 <= val < 10000:
                return result
            
            # If it's a string, try to extract number
            if isinstance(val, str):
                # Remove common non-number text
                val = val.lower().replace('posts', '').replace('vacancies', '').replace('total', '').strip()
                
                # Find all numbers
                numbers = re.findall(r'\d+', val)
                
                if numbers:
                    # Filter out years (2024-2030)
                    valid_numbers = [int(n) for n in numbers if int(n) < 2024 or int(n) > 2030]
                    
                    if valid_numbers:
                        # Take the first valid number
                        result['vacancies'] = valid_numbers[0]
                        logger.debug(f"  ✓ Fixed vacancies: {val} → {valid_numbers[0]}")
                    else:
                        # All numbers are years, set to null
                        logger.warning(f"  ⚠️  Vacancies contains only year: {val} → null")
                        result['vacancies'] = None
                else:
                    result['vacancies'] = None
        
        return result
    
    def _parse_with_ollama(self, html: str, field_names: List[str] = None) -> Dict:
        """Parse using local Ollama.
        
        If field_names is None, extracts ALL fields (better architecture).
        """
        try:
            # Use full extraction if no specific fields requested
            if field_names is None or len(field_names) >= 15:
                prompt = self._build_full_extraction_prompt(html)
            else:
                prompt = self._build_extraction_prompt(html, field_names)
            
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise job data extractor. Extract information from HTML and return ONLY valid JSON. For vacancies field, extract the NUMBER of job positions (not year). No explanations, just JSON."
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
                timeout=60
            )
            
            if response.status_code == 200:
                content = response.json()['message']['content']
                content = self._clean_json_response(content)
                result = json.loads(content)
                
                # Fix vacancies field
                result = self._fix_vacancies(result)
                
                # Ensure JSON fields are proper JSON
                for json_field in ['application_fee', 'important_dates', 'vacancy_details']:
                    if json_field in result and isinstance(result[json_field], str):
                        try:
                            result[json_field] = json.loads(result[json_field])
                        except:
                            pass
                
                return result
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return {}
                
        except json.JSONDecodeError as e:
            logger.error(f"Ollama returned invalid JSON: {e}")
            logger.debug(f"Response: {content[:200]}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing with Ollama: {e}")
            return {}
    
    def parse_missing_fields(self, html: str, field_names: List[str]) -> Dict:
        """Parse specific fields from HTML."""
        if not self.is_available():
            logger.warning("No LLM provider available")
            return {}
        
        if not field_names:
            return {}
        
        logger.info(f"🤖 Using LLM (Ollama {self.ollama_model}) to extract {len(field_names)} fields")
        
        result = self._parse_with_ollama(html, field_names)
        
        extracted_count = len([v for v in result.values() if v is not None and v != ''])
        logger.info(f"  ✓ LLM extracted {extracted_count}/{len(field_names)} fields")
        
        for field, value in result.items():
            if value:
                if isinstance(value, (dict, list)):
                    logger.debug(f"    - {field}: {json.dumps(value)[:60]}")
                else:
                    logger.debug(f"    - {field}: {str(value)[:60]}")
        
        return result
    
    def parse_full_job(self, html: str) -> Dict:
        """Parse ALL job fields from HTML at once (recommended architecture).
        
        This is better than parsing field by field.
        """
        if not self.is_available():
            return {}
        
        logger.info(f"🤖 Using LLM (Ollama {self.ollama_model}) to extract ALL fields")
        
        all_fields = list(self.SCHEMA_DEFINITION.keys())
        result = self._parse_with_ollama(html, None)  # None = extract all
        
        extracted_count = len([v for v in result.values() if v is not None and v != ''])
        logger.info(f"  ✓ LLM extracted {extracted_count}/{len(all_fields)} fields")
        
        return result
