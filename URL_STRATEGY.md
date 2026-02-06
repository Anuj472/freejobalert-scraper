# URL Handling Strategy

## Problem

Previously, `job_url` was storing FreeJobAlert article URLs like:
```
https://www.freejobalert.com/articles/iit-gandhinagar-recruitment-2026-3036714
```

But `job_url` should point to the **organization's official job page**, not FreeJobAlert.

## Solution

The scraper now uses a **priority-based URL selection** for `job_url`:

### Priority Order

1. **`application_url`** (highest priority)
   - Extracted from "Apply Online: [Click here](URL)"
   - Example: `https://cochinshipyard.in/career/apply/750`

2. **`official_website`** (medium priority)
   - Extracted from "Official Website: [Click here](URL)"
   - Example: `https://cochinshipyard.in/`

3. **FreeJobAlert URL** (fallback only)
   - Used only if no organization URL is found
   - Example: `https://www.freejobalert.com/articles/...`

## Database Fields

### Current Schema

```sql
-- Primary URL fields
job_url              TEXT NOT NULL    -- Organization's application/website URL
application_url      TEXT             -- "Apply Online" link
official_website     TEXT             -- "Official Website" link  
organization_url     TEXT             -- Organization homepage

-- PDF fields
pdf_url             TEXT              -- External PDF URL (if not FreeJobAlert)
gdrive_link         TEXT              -- Google Drive link (for FreeJobAlert PDFs)

-- Optional tracking field
freejobalert_url    TEXT UNIQUE       -- FreeJobAlert source URL for deduplication
```

### Recommended Schema (with migration)

Run `MIGRATION_ADD_FJA_URL.sql` to add:

```sql
freejobalert_url TEXT UNIQUE  -- Track FreeJobAlert source separately
```

Benefits:
- `job_url` always points to organization
- `freejobalert_url` prevents duplicate scraping
- Can track which jobs came from FreeJobAlert

## Examples

### Example 1: Full Organization URLs

**From FreeJobAlert page:**
```
Apply Online: [Click here](https://cochinshipyard.in/career/apply/750)
Official Notification PDF: [Click here](https://cochinshipyard.in/uploads/career/file.pdf)
Official Website: [Click here](https://cochinshipyard.in/)
```

**Database:**
```json
{
  "job_url": "https://cochinshipyard.in/career/apply/750",
  "application_url": "https://cochinshipyard.in/career/apply/750",
  "official_website": "https://cochinshipyard.in/",
  "organization_url": "https://cochinshipyard.in/",
  "pdf_url": "https://cochinshipyard.in/uploads/career/file.pdf",
  "freejobalert_url": "https://www.freejobalert.com/articles/xyz-123"
}
```

### Example 2: No Apply Link

**From FreeJobAlert page:**
```
Official Notification PDF: [Click here](https://iitgn.ac.in/pdf/recruitment.pdf)
Official Website: [Click here](https://iitgn.ac.in/)
```

**Database:**
```json
{
  "job_url": "https://iitgn.ac.in/",
  "application_url": null,
  "official_website": "https://iitgn.ac.in/",
  "organization_url": "https://iitgn.ac.in/",
  "pdf_url": "https://iitgn.ac.in/pdf/recruitment.pdf",
  "freejobalert_url": "https://www.freejobalert.com/articles/xyz-456"
}
```

### Example 3: FreeJobAlert PDF

**From FreeJobAlert page:**
```
Apply Online: [Click here](https://organization.gov.in/apply)
Official Notification PDF: [Click here](https://img2.freejobalert.com/news/2026/02/file.pdf)
Official Website: [Click here](https://organization.gov.in/)
```

**Database (before Drive upload):**
```json
{
  "job_url": "https://organization.gov.in/apply",
  "application_url": "https://organization.gov.in/apply",
  "official_website": "https://organization.gov.in/",
  "pdf_url": null,
  "gdrive_link": null,
  "freejobalert_url": "https://www.freejobalert.com/articles/xyz-789"
}
```

**After `process_pdfs.py`:**
```json
{
  "job_url": "https://organization.gov.in/apply",
  "application_url": "https://organization.gov.in/apply",
  "official_website": "https://organization.gov.in/",
  "pdf_url": null,
  "gdrive_link": "https://drive.google.com/file/d/FILE_ID/view",
  "freejobalert_url": "https://www.freejobalert.com/articles/xyz-789"
}
```

### Example 4: Fallback (No Organization URLs)

**From FreeJobAlert page:**
```
Official Notification PDF: [Click here](https://img2.freejobalert.com/news/2026/02/file.pdf)
(No Apply Online link, No Official Website link)
```

**Database:**
```json
{
  "job_url": "https://www.freejobalert.com/articles/xyz-999",
  "application_url": null,
  "official_website": null,
  "pdf_url": null,
  "freejobalert_url": "https://www.freejobalert.com/articles/xyz-999"
}
```

⚠️ **Warning logged**: "No organization URL found, using FreeJobAlert URL"

## Migration Steps

### 1. Add Optional Column (Recommended)

```bash
# In Supabase SQL Editor, run:
cat MIGRATION_ADD_FJA_URL.sql
```

This adds:
- `freejobalert_url TEXT UNIQUE`
- Indexes for faster lookups
- Migrates existing FreeJobAlert URLs from `job_url`

### 2. Update Existing Records (Optional)

If you want to clean up old records:

```sql
-- Find jobs with FreeJobAlert URLs in job_url
SELECT id, title, job_url, application_url
FROM jobs
WHERE job_url LIKE '%freejobalert.com%';

-- Update to use application_url if available
UPDATE jobs
SET job_url = application_url
WHERE job_url LIKE '%freejobalert.com%' 
  AND application_url IS NOT NULL;

-- Update to use official_website if no application_url
UPDATE jobs
SET job_url = official_website
WHERE job_url LIKE '%freejobalert.com%' 
  AND application_url IS NULL
  AND official_website IS NOT NULL;
```

### 3. Verify

```sql
-- Check distribution
SELECT 
    COUNT(*) FILTER (WHERE job_url LIKE '%freejobalert.com%') as fja_urls,
    COUNT(*) FILTER (WHERE job_url NOT LIKE '%freejobalert.com%') as org_urls,
    COUNT(*) as total
FROM jobs;
```

## Code Changes

### Before (supabase_client.py)

```python
# Old: Always used FreeJobAlert URL
insert_data['job_url'] = job_data.get('job_url')  # FreeJobAlert URL
```

### After (supabase_client.py)

```python
# New: Prioritize organization URLs
if application_url:
    insert_data['job_url'] = application_url
elif official_website:
    insert_data['job_url'] = official_website
else:
    insert_data['job_url'] = fja_url  # Fallback

# Track FreeJobAlert source separately
insert_data['freejobalert_url'] = fja_url
```

## Deduplication Strategy

### With `freejobalert_url` column:

```python
def job_exists(self, fja_url: str) -> bool:
    # Check by freejobalert_url (preferred)
    result = self.client.table('jobs')
        .select('id')
        .eq('freejobalert_url', fja_url)
        .execute()
    return len(result.data) > 0
```

### Without `freejobalert_url` column:

```python
def job_exists(self, fja_url: str) -> bool:
    # Fallback: check by job_url constraint
    result = self.client.table('jobs')
        .select('id')
        .eq('job_url', fja_url)
        .execute()
    return len(result.data) > 0
```

## Benefits

### ✅ For Users
- Click on `job_url` → Go directly to organization's application page
- No need to navigate through FreeJobAlert
- Better user experience

### ✅ For SEO
- Links point to authoritative sources
- Better for search engine ranking
- Proper attribution to organizations

### ✅ For Scraper
- Prevents duplicate scraping using `freejobalert_url`
- Tracks data source for auditing
- Can re-scrape from FreeJobAlert if needed

## Testing

```bash
# Pull latest code
git pull origin main

# Optional: Run migration
# (Run MIGRATION_ADD_FJA_URL.sql in Supabase SQL Editor)

# Scrape jobs
python main.py --no-pdf --max-pages 1

# Check logs for URL assignment
grep "Using.*as job_url" scraper.log

# Query database
psql $DATABASE_URL -c "SELECT title, job_url, application_url, freejobalert_url FROM jobs LIMIT 5;"
```

## Log Output

You'll see logs like:

```
INFO - Using application URL as job_url: https://cochinshipyard.in/career/apply/750
INFO - Source URL (FreeJobAlert): https://www.freejobalert.com/articles/xyz
INFO - Successfully inserted job: Cochin Shipyard Recruitment 2026
INFO -   - Apply URL: https://cochinshipyard.in/career/apply/750
```

Or fallback:

```
WARNING - No organization URL found, using FreeJobAlert URL: https://www.freejobalert.com/...
```

## FAQ

**Q: What if a job has no organization URLs?**  
A: The scraper uses FreeJobAlert URL as fallback and logs a warning.

**Q: Do I need to run the migration?**  
A: No, it's optional. The code works with or without `freejobalert_url` column.

**Q: Will old records break?**  
A: No. Existing records continue to work. Only new scrapes use the new logic.

**Q: How do I fix old records?**  
A: Run the UPDATE queries in the Migration section above.

**Q: What about the unique constraint on `job_url`?**  
A: If you add `freejobalert_url` column, deduplication uses that instead. Otherwise, `job_url` constraint still works but may have duplicates if same organization URL appears in multiple FreeJobAlert articles.
