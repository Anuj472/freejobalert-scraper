# Quick Start Guide

## Complete Workflow in 5 Steps

### 1. Install Dependencies

```bash
git pull origin main
pip install -r requirements.txt
```

### 2. Setup Google Drive (First Time Only)

#### A. Create Service Account
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable **Google Drive API**
3. Create **Service Account** and download `credentials.json`
4. Save `credentials.json` to project root

#### B. Create Drive Folder
1. Create folder in [Google Drive](https://drive.google.com/)
2. Share with service account email (from credentials.json)
3. Copy folder ID from URL

#### C. Update .env
```env
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
```

### 3. Scrape Jobs

```bash
python main.py --no-pdf --max-pages 2
```

This extracts:
- Job details (title, organization, dates, etc.)
- Application URLs ("Apply Online: Click here")
- Official website URLs
- PDF URLs (external) OR flags for Drive upload (FreeJobAlert)

### 4. Check What Needs Upload

```bash
python process_pdfs.py --stats
```

Output:
```
Jobs needing PDF processing: 45      ← FreeJobAlert PDFs to upload
Jobs with external PDFs: 123         ← Already saved
Jobs with Google Drive links: 67     ← Already uploaded
```

### 5. Upload FreeJobAlert PDFs

```bash
# Process 10 jobs
python process_pdfs.py

# Or process specific number
python process_pdfs.py --max-jobs 5
```

The script will:
1. ✅ Download FreeJobAlert PDFs
2. ✅ Upload to Google Drive
3. ✅ Get shareable public link
4. ✅ Save link to database (`gdrive_link`)
5. ✅ Clean up temporary files

## What Gets Saved?

### External PDFs (Government Sites)
```sql
-- Saved directly to pdf_url
pdf_url: 'https://cochinshipyard.in/uploads/career/file.pdf'
gdrive_link: NULL
```

### FreeJobAlert PDFs
```sql
-- Uploaded to Drive, link saved to gdrive_link
pdf_url: NULL
gdrive_link: 'https://drive.google.com/file/d/FILE_ID/view'
```

## Database Fields Extracted

✅ **Basic Info**: title, organization, qualification, location  
✅ **Dates**: post_date, last_date  
✅ **Numbers**: vacancies, advt_no  
✅ **Links**: application_url, official_website, organization_url  
✅ **PDFs**: pdf_url (external) OR gdrive_link (uploaded)  
✅ **Details**: salary, age_limit, application_fee  
✅ **Procedures**: selection_process, how_to_apply  
✅ **JSON**: important_dates, vacancy_details  

## Example URLs Extracted

### From Job Page Like:
```
Apply Online: [Click here](https://cochinshipyard.in/career/apply/750)
Official Notification PDF: [Click here](https://cochinshipyard.in/uploads/career/file.pdf)
Official Website: [Click here](https://cochinshipyard.in/)
```

### Scraper Extracts:
```python
application_url = 'https://cochinshipyard.in/career/apply/750'
pdf_url = 'https://cochinshipyard.in/uploads/career/file.pdf'
official_website = 'https://cochinshipyard.in/'
organization_url = 'https://cochinshipyard.in/'
```

## Daily Automation

Create `daily_sync.sh`:
```bash
#!/bin/bash
cd /path/to/freejobalert-scraper

# Scrape new jobs
python main.py --no-pdf --max-pages 3

# Upload PDFs
python process_pdfs.py --batch-size 20

# Show stats
python process_pdfs.py --stats
```

Make executable:
```bash
chmod +x daily_sync.sh
```

Run via cron (daily at 2 AM):
```bash
crontab -e
# Add:
0 2 * * * /path/to/freejobalert-scraper/daily_sync.sh >> /path/to/logs/daily.log 2>&1
```

## Troubleshooting

### Test Drive Upload
```bash
python gdrive_uploader.py "https://img2.freejobalert.com/news/2026/02/test.pdf"
```

### Check Logs
```bash
tail -f pdf_processor.log
```

### Debug Mode
```bash
python process_pdfs.py --log-level DEBUG --max-jobs 1
```

## Common Issues

**"Credentials file not found"**  
→ Ensure `credentials.json` exists in project root

**"Permission denied"**  
→ Share Drive folder with service account email

**"No jobs found"**  
→ Run scraper first: `python main.py --no-pdf`

## Full Documentation

See [PDF_UPLOAD_GUIDE.md](./PDF_UPLOAD_GUIDE.md) for complete details.
