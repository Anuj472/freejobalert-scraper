"""LLM-based parser for extracting job data from HTML.

Uses Groq API (Llama models) or local Ollama as fallback.
Only parses missing fields to save cost and time.
"""

import logging
import json
import os
from typing import Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

# Try to import Groq (optional)
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq not installed. Install with: pip install groq")


class JobLLMParser:
    """Intelligent job data parser using LLMs."""
    
    # Field definitions for LLM
    FIELD_DESCRIPTIONS = {
        'title': 'Job title or post name',
        'organization': 'Organization or department name',
        'qualification': 'Educational qualification required',
        'category': 'Job category (Government, Bank, Railway, etc.)',
        'advt_no': 'Advertisement or notification number',
        'post_date': 'Post or notification date (DD-MM-YYYY format)',
        'last_date': 'Last date to apply (DD-MM-YYYY format)',
        'vacancies': 'Total number of vacancies or posts',
        'location': 'Job location or state',
        'salary': 'Salary or pay scale details',
        'age_limit': 'Age limit for applicants',
        'application_fee': 'Application fee details',
        'application_url': 'Direct link to apply online (URL with http/https)',
        'official_website': 'Official website of organization (URL with http/https)',
        'official_notification_pdf': 'Link to official PDF notification (URL with http/https)',
        'selection_process': 'Selection process or exam pattern',
        'how_to_apply': 'Steps or instructions to apply',
    }
    
    def __init__(self):
        """Initialize LLM parser with available provider."""
        self.provider = None
        self.groq_client = None
        self.ollama_url = "http://localhost:11434"
        self.ollama_model = "llama3.2:3b"  # Default model
        
        # Check for Groq API
        groq_key = os.getenv('GROQ_API_KEY')
        if groq_key and GROQ_AVAILABLE:
            try:
                self.groq_client = Groq(api_key=groq_key)
                self.groq_model = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
                self.provider = 'groq'
                logger.info(f"✓ Using Groq API with {self.groq_model} (fast & free)")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq: {e}")
        
        # Check for local Ollama
        if not self.provider:
            if self._check_ollama_available():
                self.provider = 'ollama'
                self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')
                logger.info(f"✓ Using Ollama local with {self.ollama_model} (private & free)")
            else:
                logger.warning("⚠️  No LLM provider available. Install Groq or Ollama.")
                logger.warning("   Groq: pip install groq + get key from https://console.groq.com/")
                logger.warning("   Ollama: curl -fsSL https://ollama.com/install.sh | sh")
    
    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def is_available(self) -> bool:
        """Check if any LLM provider is available."""
        return self.provider is not None
    
    def _build_extraction_prompt(self, html: str, missing_fields: List[str]) -> str:
        """Build prompt for LLM to extract missing fields."""
        
        # Build field descriptions
        field_desc = []
        for field in missing_fields:
            desc = self.FIELD_DESCRIPTIONS.get(field, field)
            field_desc.append(f"  - {field}: {desc}")
        
        field_list = "\n".join(field_desc)
        
        prompt = f"""Extract the following job details from this FreeJobAlert HTML page:

{field_list}

Rules:
1. Return ONLY valid JSON with extracted fields
2. Use null for fields not found
3. For dates, use DD-MM-YYYY format
4. For URLs, include full URL with http/https
5. Extract exact text, don't summarize
6. For "Apply Online" links, look for application/registration URLs
7. For "Official Website", look for organization homepage
8. For PDF links, look for notification/advertisement PDF URLs

HTML Content:
{html[:15000]}

Return JSON:"""
        
        return prompt
    
    def _parse_with_groq(self, html: str, missing_fields: List[str]) -> Dict:
        """Parse using Groq API."""
        try:
            prompt = self._build_extraction_prompt(html, missing_fields)
            
            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a job posting data extractor. Extract information from HTML and return ONLY valid JSON. Be precise and accurate."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error(f"Groq returned invalid JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing with Groq: {e}")
            return {}
    
    def _parse_with_ollama(self, html: str, missing_fields: List[str]) -> Dict:
        """Parse using local Ollama."""
        try:
            prompt = self._build_extraction_prompt(html, missing_fields)
            
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Extract job data from HTML. Return only valid JSON."
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
                        "num_predict": 2000
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()['message']['content']
                return json.loads(content)
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return {}
                
        except json.JSONDecodeError as e:
            logger.error(f"Ollama returned invalid JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing with Ollama: {e}")
            return {}
    
    def parse_missing_fields(self, html: str, missing_fields: List[str]) -> Dict:
        """Parse only the missing fields from HTML.
        
        Args:
            html: Raw HTML content
            missing_fields: List of field names to extract
            
        Returns:
            Dictionary with extracted field values
        """
        if not self.is_available():
            logger.warning("No LLM provider available, skipping LLM parsing")
            return {}
        
        if not missing_fields:
            logger.debug("No missing fields to parse")
            return {}
        
        logger.info(f"🤖 Using LLM ({self.provider}) to extract: {', '.join(missing_fields)}")
        
        # Parse with available provider
        if self.provider == 'groq':
            result = self._parse_with_groq(html, missing_fields)
        elif self.provider == 'ollama':
            result = self._parse_with_ollama(html, missing_fields)
        else:
            return {}
        
        # Log what was extracted
        extracted_count = len([v for v in result.values() if v])
        logger.info(f"  ✓ LLM extracted {extracted_count}/{len(missing_fields)} fields")
        
        for field, value in result.items():
            if value:
                value_preview = str(value)[:60]
                logger.debug(f"    - {field}: {value_preview}")
        
        return result
    
    def parse_full_job(self, html: str) -> Dict:
        """Parse all job fields from HTML (use when CSS parsing completely fails).
        
        Args:
            html: Raw HTML content
            
        Returns:
            Dictionary with all extracted fields
        """
        all_fields = list(self.FIELD_DESCRIPTIONS.keys())
        return self.parse_missing_fields(html, all_fields)
