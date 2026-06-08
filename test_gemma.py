#!/usr/bin/env python3
"""Test script for Gemma 4 processor.

Tests:
1. Ollama connection
2. Gemma 4 model availability
3. Text extraction
4. Blog generation
"""

import sys
import logging
from gemma_processor import GemmaProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_ollama_connection():
    """Test if Ollama is running."""
    logger.info("=" * 60)
    logger.info("TEST 1: Ollama Connection")
    logger.info("=" * 60)
    
    import requests
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=5)
        if response.status_code == 200:
            logger.info("✓ Ollama is running")
            models = response.json().get('models', [])
            logger.info(f"  Available models: {len(models)}")
            for model in models:
                logger.info(f"    - {model['name']}")
            return True
        else:
            logger.error("✗ Ollama returned error")
            return False
    except Exception as e:
        logger.error(f"✗ Cannot connect to Ollama: {e}")
        logger.error("  Make sure Ollama is running: ollama serve")
        return False

def test_gemma_availability():
    """Test if Gemma 4 model is available."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Gemma 4 Model Availability")
    logger.info("=" * 60)
    
    gemma = GemmaProcessor()
    if gemma.is_available():
        logger.info("✓ Gemma 4 12B is available")
        return True
    else:
        logger.error("✗ Gemma 4 12B not found")
        logger.error("  Run: ollama pull gemma4:12b")
        return False

def test_text_extraction():
    """Test extraction from text."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Text Extraction")
    logger.info("=" * 60)
    
    gemma = GemmaProcessor()
    if not gemma.is_available():
        logger.warning("⚠️  Skipping (Gemma not available)")
        return False
    
    # Sample job notification text
    sample_text = """UPSC CIVIL SERVICES EXAMINATION 2026
    
    Union Public Service Commission
    
    NOTIFICATION
    
    UPSC invites applications for Civil Services Examination (CSE) 2026.
    
    Total Vacancies: 933 posts
    
    Important Dates:
    - Online Application Start: 15-01-2026
    - Last Date to Apply: 15-02-2026
    - Preliminary Exam: 25-05-2026
    
    Age Limit: 21-32 years as on 01-08-2026
    
    Qualification: Bachelor's Degree from recognized university
    
    Application Fee:
    - General/OBC: Rs. 100
    - Women/SC/ST/PwD: Nil
    
    Salary: Rs. 56,100 - 2,50,000 per month
    
    Selection Process: Preliminary Exam + Mains + Interview
    """
    
    try:
        logger.info("📝 Testing text extraction...")
        data = gemma.extract_fields(sample_text, "Text")
        
        if data:
            logger.info("✓ Text extraction successful")
            logger.info(f"  - Title: {data.get('title', 'N/A')}")
            logger.info(f"  - Organization: {data.get('organization', 'N/A')}")
            logger.info(f"  - Vacancies: {data.get('vacancies', 'N/A')}")
            logger.info(f"  - Last Date: {data.get('last_date', 'N/A')}")
            logger.info(f"  - Extracted fields: {len([k for k, v in data.items() if v])}")
            return True
        else:
            logger.error("✗ Text extraction failed")
            return False
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return False

def test_blog_generation():
    """Test blog generation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Blog Generation")
    logger.info("=" * 60)
    
    gemma = GemmaProcessor()
    if not gemma.is_available():
        logger.warning("⚠️  Skipping (Gemma not available)")
        return False
    
    # Sample job data
    sample_data = {
        'title': 'UPSC Civil Services Examination 2026',
        'organization': 'Union Public Service Commission',
        'vacancies': 933,
        'last_date': '15-02-2026',
        'salary': 'Rs. 56,100 - 2,50,000 per month',
        'age_limit': '21-32 years',
        'qualification': "Bachelor's Degree",
        'location': 'All India',
        'application_fee': 'General: Rs. 100, SC/ST: Nil'
    }
    
    try:
        logger.info("📝 Testing blog generation...")
        blog = gemma.generate_blog(sample_data)
        
        if blog:
            logger.info("✓ Blog generation successful")
            logger.info(f"  - Blog article length: {len(blog)} chars")
            return True
        else:
            logger.error("✗ Blog generation failed")
            return False
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return False

def main():
    """Run all tests."""
    logger.info("\n" + "#" * 60)
    logger.info("# GEMMA 4 PROCESSOR TEST SUITE")
    logger.info("#" * 60 + "\n")
    
    results = {
        'Ollama Connection': test_ollama_connection(),
        'Gemma 4 Availability': test_gemma_availability(),
        'Text Extraction': test_text_extraction(),
        'Blog Generation': test_blog_generation()
    }
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status} - {test}")
    
    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    if passed == total:
        logger.info("\n✅ All tests passed! Gemma 4 is ready to use.")
        return 0
    elif passed >= 2:  # Ollama + Gemma availability
        logger.warning("\n⚠️  Some tests failed, but basic functionality works.")
        return 0
    else:
        logger.error("\n❌ Critical tests failed. Please fix issues above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
