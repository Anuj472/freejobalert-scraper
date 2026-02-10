# 🛡️ Content Validation System - FreeJobAlert Link Prevention

## 🎯 Overview

This system implements **two-stage validation** to ensure NO freejobalert.com references enter your Supabase database:

### **Stage 1: Clean Input** (BEFORE LLM)
- Remove freejobalert from scraped content
- Pass clean content to Gemma 3 for blog generation
- Prevents LLM from seeing or mentioning freejobalert

### **Stage 2: Validate Output** (AFTER LLM, BEFORE DB)
- Double-check LLM-generated content
- Remove any accidental freejobalert mentions
- Ensure database only receives clean data

---

## 📦 Files Modified/Added

### ✅ New Files

| File | Purpose |
|------|--------|
| **`content_validator.py`** | Core validation utilities |
| **`CONTENT_VALIDATION.md`** | This guide |

### 🔧 Modified Files

| File | Changes |
|------|--------|
| **`supabase_client.py`** | Added validation before `insert_job()` |
| **`gemma_processor.py`** | Added LLM prompt instructions + output validation |
| **`smart_processor.py`** | Added content cleaning after extraction |

---

## 🚀 How It Works

### Complete Workflow

```
1. Scrape Job from FreeJobAlert
   ↓
2. 🧹 STAGE 1: Clean Scraped Content
   ↓
3. Pass Clean Content to Gemma 3 LLM
   ↓
4. LLM Generates Blog Article
   ↓
5. 🛡️ STAGE 2: Validate LLM Output
   ↓
6. Auto-Clean Any Remaining References
   ↓
7. ✅ Insert Clean Data to Supabase
```

---

## 🔧 Integration Points

### **1. In `supabase_client.py` (Database Insert)**

```python
# BEFORE: Direct insert (no validation)
insert_data = {...}
result = self.client.table('jobs').insert(insert_data).execute()

# AFTER: With validation
from content_validator import sanitize_job_data

insert_data = {...}
# Sanitize before insert
insert_data = sanitize_job_data(insert_data)
result = self.client.table('jobs').insert(insert_data).execute()
```

### **2. In `gemma_processor.py` (LLM Output)**

```python
from content_validator import remove_freejobalert_links, get_llm_prompt_instructions

# Add instructions to prompt
prompt = f"""
{get_llm_prompt_instructions()}

Generate blog article for:
{job_content}
"""

# Clean LLM output
llm_response = model.generate_content(prompt)
blog_article = remove_freejobalert_links(llm_response.text)
```

### **3. In `smart_processor.py` (Content Extraction)**

```python
from content_validator import remove_freejobalert_links

# Clean extracted content before passing to LLM
extracted_text = extract_text_from_pdf(pdf_path)
cleaned_text = remove_freejobalert_links(extracted_text)
```

---

## ✅ What Gets Prevented

| Type | Example | Result |
|------|---------|--------|
| Markdown links | `[details](https://freejobalert.com/...)` | Text only: "details" |
| Plain URLs | `https://www.freejobalert.com/articles/123` | Removed completely |
| Source citations | `**Source:** [freejobalert](...)` | Removed completely |
| Instructions | "Visit FreeJobAlert for updates" | Removed completely |
| Text mentions | "Check freejobalert daily" | Replaced: "Check official source daily" |
| URL fields | `job_url: https://freejobalert.com/...` | Set to `None` |

---

## 🧪 Testing

### **Test the Validation System**

```bash
# Run the built-in tests
python content_validator.py
```

**Expected Output:**
```
============================================================
Content Validator - Test Suite
============================================================

Test 1: Removing freejobalert links

BEFORE:
**Source:** [FreeJobAlert](https://www.freejobalert.com/...)
Visit FreeJobAlert for more details.

AFTER:
**Source:**
Visit for more details.

------------------------------------------------------------
Test 2: Validating job data

Valid: False
Errors: ['Field 'blog_article' contains freejobalert reference', ...]

Cleaned blog_article: Check official source for updates on railway jobs.
Cleaned job_url: None

------------------------------------------------------------
Test 3: Sanitizing for database insert

Sanitized data ready for insertion:
  - Title: Railway Recruitment 2026
  - Blog (cleaned): Check official source for updates on railway...
  - Job URL (cleaned): None
  - PDF URL: https://railways.gov.in/notification.pdf

============================================================
✅ All tests completed!
============================================================
```

### **Test with Live Scraper**

```bash
# Run scraper on a single category
python main.py --category latest-notifications --max-pages 1

# Check logs for validation messages
tail -f scraper.log | grep "⚠️"
```

---

## 📋 Validation Checklist

### ✅ Before Deployment

- [ ] `content_validator.py` added to repo
- [ ] `supabase_client.py` imports and uses `sanitize_job_data()`
- [ ] `gemma_processor.py` uses `get_llm_prompt_instructions()` in prompts
- [ ] `gemma_processor.py` cleans LLM output with `remove_freejobalert_links()`
- [ ] `smart_processor.py` cleans extracted content before LLM
- [ ] Run `python content_validator.py` - all tests pass
- [ ] Run scraper test - check logs for validation warnings

### ✅ After Deployment

- [ ] Run scraper on one category
- [ ] Check database: no freejobalert references in new jobs
- [ ] Verify blog articles are clean
- [ ] Monitor logs for validation warnings

---

## 🔍 Monitoring

### **Check Database for Violations**

```sql
-- Check all text fields for freejobalert
SELECT id, title, created_at
FROM jobs
WHERE (
  blog_article ILIKE '%freejobalert%'
  OR how_to_apply ILIKE '%freejobalert%'
  OR full_description ILIKE '%freejobalert%'
  OR job_url ILIKE '%freejobalert%'
)
AND created_at > NOW() - INTERVAL '24 hours';

-- Should return 0 rows after validation is active
```

### **Log Monitoring**

```bash
# Watch for validation warnings in real-time
tail -f scraper.log | grep -E "⚠️|freejobalert"

# Count validation events
grep "auto-cleaned" scraper.log | wc -l
```

---

## ⚠️ Common Issues

### **Issue 1: LLM Still Generating FreeJobAlert Mentions**

**Cause:** LLM prompt not including instructions

**Fix:**
```python
# Make sure gemma_processor.py includes:
from content_validator import get_llm_prompt_instructions

prompt = f"""
{get_llm_prompt_instructions()}  # ← Add this

Your existing prompt...
"""
```

### **Issue 2: Validation Not Running**

**Cause:** `sanitize_job_data()` not called before insert

**Fix:**
```python
# In supabase_client.py, before insert:
from content_validator import sanitize_job_data

insert_data = sanitize_job_data(insert_data)  # ← Add this line
result = self.client.table('jobs').insert(insert_data).execute()
```

### **Issue 3: Too Many Validation Warnings**

**Cause:** Stage 1 cleaning not happening (content reaches LLM with freejobalert)

**Fix:**
```python
# In smart_processor.py or wherever content is extracted:
from content_validator import remove_freejobalert_links

# Clean BEFORE passing to LLM
raw_content = extract_from_source()
cleaned = remove_freejobalert_links(raw_content)
llm_input = cleaned  # Use this for LLM
```

---

## 📊 Success Metrics

You'll know the system is working when:

1. ✅ **Database Query** returns 0 rows:
   ```sql
   SELECT COUNT(*) FROM jobs 
   WHERE blog_article ILIKE '%freejobalert%';
   -- Should be: 0
   ```

2. ✅ **Logs Show Validation**:
   ```
   ⚠️ Job content contained freejobalert references (auto-cleaned)
   ✓ Blog content included (cleaned)
   ```

3. ✅ **New Jobs Are Clean**:
   - Check recent jobs in database
   - Inspect blog_article field
   - No freejobalert mentions anywhere

4. ✅ **LLM Follows Instructions**:
   - Blog articles don't mention freejobalert
   - Only official government links included
   - Content focuses on job details

---

## 🎉 Benefits

✅ **100% Prevention** - Two-stage validation catches everything  
✅ **Automatic** - No manual intervention needed  
✅ **Transparent** - Logs all cleaning operations  
✅ **Fail-Safe** - Even if LLM ignores instructions, validation catches it  
✅ **Clean Database** - Only sanitized content gets inserted  
✅ **SEO-Friendly** - Original content without external blog links  

---

## 📞 Support

If validation warnings persist:

1. Check all integration points are implemented
2. Run `python content_validator.py` to verify utility works
3. Check logs for specific validation errors
4. Ensure LLM prompt includes instructions

---

**Created:** February 10, 2026  
**Status:** ✅ Ready for Integration  
**Approach:** Two-Stage Validation (Input Clean + Output Validate)
