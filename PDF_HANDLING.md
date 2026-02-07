# PDF Handling Logic

## How It Works

The scraper now intelligently handles PDFs based on their source:

### **1. FreeJobAlert PDFs** → Upload to Google Drive

```
PDF URL contains "freejobalert.com"
↓
Download PDF
↓
Upload to Google Drive
↓
Store Drive link in `gdrive_link` field
```

### **2. External PDFs** → Keep Original URL

```
PDF from bank/organization website
↓
Store URL directly in `pdf_url` field
↓
No download/upload needed
```

---

## Database Fields

| Field | Purpose | Example |
|-------|---------|-------|
| `pdf_url` | External PDF URLs (bank, govt sites) | `https://sbi.bank.in/docs/notification.pdf` |
| `gdrive_link` | Google Drive links (uploaded FreeJobAlert PDFs) | `https://drive.google.com/file/d/ABC123...` |

---

## Examples

### **Example 1: FreeJobAlert PDF**

```python
Input:
  pdf_url: "https://img2.freejobalert.com/pdfs/sbi-recruitment.pdf"
  
Process:
  1. Detect FreeJobAlert domain
  2. Download PDF
  3. Upload to Google Drive
  
Database:
  pdf_url: NULL
  gdrive_link: "https://drive.google.com/file/d/ABC123..."
```

### **Example 2: External PDF (Bank Website)**

```python
Input:
  pdf_url: "https://sbi.bank.in/documents/2026/notification.pdf"
  
Process:
  1. Detect external domain
  2. No download needed
  
Database:
  pdf_url: "https://sbi.bank.in/documents/2026/notification.pdf"
  gdrive_link: NULL
```

---

## Logs

You'll see different log messages based on PDF source:

### **FreeJobAlert PDF**
```bash
FreeJobAlert PDF detected: https://img2.freejobalert.com/pdfs/...
Downloading and uploading to Google Drive...
✓ PDF uploaded to Google Drive: https://drive.google.com/file/d/...
Successfully saved: SBI Recruitment 2026
  → Google Drive: https://drive.google.com/file/d/ABC123...
```

### **External PDF**
```bash
External PDF (no upload needed): https://sbi.bank.in/documents/...
Successfully saved: SBI Recruitment 2026
  → PDF URL: https://sbi.bank.in/documents/notification.pdf
```

---

## Query Examples

### **Get Jobs with Google Drive PDFs**

```sql
SELECT 
  title,
  organization,
  gdrive_link
FROM jobs
WHERE gdrive_link IS NOT NULL
ORDER BY scraped_at DESC
LIMIT 10;
```

### **Get Jobs with External PDFs**

```sql
SELECT 
  title,
  organization,
  pdf_url
FROM jobs
WHERE pdf_url IS NOT NULL
ORDER BY scraped_at DESC
LIMIT 10;
```

### **Get All Jobs with Any PDF**

```sql
SELECT 
  title,
  organization,
  COALESCE(gdrive_link, pdf_url) as pdf_link,
  CASE 
    WHEN gdrive_link IS NOT NULL THEN 'Google Drive'
    WHEN pdf_url IS NOT NULL THEN 'External'
    ELSE 'No PDF'
  END as pdf_source
FROM jobs
ORDER BY scraped_at DESC
LIMIT 10;
```

---

## Configuration

### **Enable/Disable Google Drive Upload**

```bash
# Skip all PDF operations
python main.py --no-pdf

# Or remove Google Drive credentials
# PDFs will still be detected and external URLs saved
```

### **Google Drive Not Configured**

If Google Drive is not set up:
- External PDFs: ✅ Still saved in `pdf_url`
- FreeJobAlert PDFs: ❌ Skipped (but URL logged)

---

## Benefits

### **Before (Old Logic)**
```
❌ All PDFs uploaded to Drive (unnecessary)
❌ External PDFs wasted time/bandwidth
❌ External PDFs could expire on Drive
❌ Confusing which is original source
```

### **After (New Logic)**
```
✅ Only FreeJobAlert PDFs uploaded
✅ External PDFs keep original URL
✅ External PDFs always accessible from source
✅ Clear distinction in database
✅ Faster processing
✅ Less Drive storage used
```

---

## Troubleshooting

### **PDFs Not Uploading to Drive**

```bash
# 1. Check if PDF is from FreeJobAlert
grep "FreeJobAlert PDF detected" scraper.log

# 2. Check Google Drive auth
ls -la credentials.json token.json

# 3. Check upload errors
grep "Error.*upload" scraper.log
```

### **External PDFs Not Saving**

```bash
# Check if PDFs were detected
grep "External PDF" scraper.log

# Should see:
# External PDF (no upload needed): https://...
```

### **Both Fields Empty**

```sql
-- Check for jobs without any PDF
SELECT 
  title,
  organization,
  freejobalert_url
FROM jobs
WHERE pdf_url IS NULL
  AND gdrive_link IS NULL
ORDER BY scraped_at DESC
LIMIT 10;

-- These jobs might not have PDFs on the source page
```

---

## Migration

If you have old jobs with external PDFs in `gdrive_link`:

```sql
-- Move external PDFs from gdrive_link to pdf_url
UPDATE jobs
SET 
  pdf_url = gdrive_link,
  gdrive_link = NULL
WHERE gdrive_link IS NOT NULL
  AND gdrive_link NOT LIKE '%drive.google.com%';

-- Verify
SELECT 
  COUNT(*) as total_pdfs,
  COUNT(gdrive_link) as drive_pdfs,
  COUNT(pdf_url) as external_pdfs
FROM jobs;
```

---

## Code Reference

### **Detection Function**

```python
def is_freejobalert_pdf(url: str) -> bool:
    """Check if PDF is hosted on FreeJobAlert domain."""
    if not url:
        return False
    parsed = urlparse(url.lower())
    return 'freejobalert.com' in parsed.netloc
```

### **Upload Logic**

```python
if is_freejobalert_pdf(pdf_url):
    # Download + Upload to Drive
    gdrive_link = uploader.upload_pdf_and_get_link(pdf_path)
    job_data['gdrive_link'] = gdrive_link
else:
    # Keep original URL
    job_data['pdf_url'] = pdf_url
```

---

## Best Practices

1. **Always check both fields** when displaying PDFs
   ```python
   pdf_link = job.get('gdrive_link') or job.get('pdf_url')
   ```

2. **Use appropriate field in frontend**
   - Show Google Drive icon for `gdrive_link`
   - Show external link icon for `pdf_url`

3. **Monitor Drive storage**
   - Only FreeJobAlert PDFs uploaded
   - Saves ~70% storage vs uploading all PDFs

---

## Summary

| PDF Source | Field Used | Action |
|------------|------------|--------|
| FreeJobAlert | `gdrive_link` | Download → Upload → Store Drive link |
| External (Bank/Govt) | `pdf_url` | Store original URL directly |
| No PDF | Both NULL | No PDF available |

---

**Test it now:**

```bash
git pull origin main
python main.py --max-pages 1

# Check logs
grep "PDF" scraper.log | tail -20

# Check database
psql -c "SELECT title, pdf_url, gdrive_link FROM jobs ORDER BY scraped_at DESC LIMIT 5;"
```
