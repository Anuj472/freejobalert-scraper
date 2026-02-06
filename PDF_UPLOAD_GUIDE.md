# PDF Upload Workflow Guide

This guide explains how to handle FreeJobAlert PDFs and upload them to Google Drive.

## Overview

The scraper distinguishes between two types of PDFs:

1. **External PDFs** - Hosted on government/organization websites
   - ✅ Saved directly to `pdf_url` in database
   - Example: `https://cochinshipyard.in/uploads/career/3f42ff72495098e71dc62d9c0fb409a4.pdf`

2. **FreeJobAlert PDFs** - Hosted on `img2.freejobalert.com`
   - ⚠️ **NOT saved** to `pdf_url` (stays NULL)
   - Must be uploaded to Google Drive
   - Drive link saved to `gdrive_link`
   - Example: `https://img2.freejobalert.com/news/2026/02/852381-69856e084f12021262758.pdf`

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Google Drive Setup

#### Create Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable **Google Drive API**:
   - Go to "APIs & Services" → "Enable APIs and Services"
   - Search for "Google Drive API" and enable it

4. Create Service Account:
   - Go to "IAM & Admin" → "Service Accounts"
   - Click "Create Service Account"
   - Name: `freejobalert-scraper`
   - Click "Create and Continue"
   - Grant role: "Editor" (or custom role with Drive access)
   - Click "Done"

5. Create Key:
   - Click on your service account
   - Go to "Keys" tab
   - Click "Add Key" → "Create new key"
   - Choose JSON format
   - Save the downloaded file as `credentials.json` in your project root

#### Create Google Drive Folder

1. Go to [Google Drive](https://drive.google.com/)
2. Create a new folder: `JobCurator PDFs`
3. Right-click folder → "Share"
4. Add your service account email (from `credentials.json`)
   - Email looks like: `freejobalert-scraper@project-id.iam.gserviceaccount.com`
   - Give it "Editor" permission
5. Get Folder ID:
   - Open the folder
   - Copy ID from URL: `https://drive.google.com/drive/folders/FOLDER_ID_HERE`

### 3. Configure Environment

Add to your `.env` file:

```env
# Google Drive Configuration
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
```

## Usage

### Step 1: Scrape Jobs

```bash
# Scrape jobs (without downloading PDFs)
python main.py --no-pdf --max-pages 2
```

This will:
- Extract all job details from FreeJobAlert
- Save external PDF URLs to `pdf_url`
- Leave `pdf_url` NULL for FreeJobAlert PDFs
- Log which PDFs need Drive upload

### Step 2: Check Statistics

```bash
python process_pdfs.py --stats
```

Output:
```
PDF Upload Statistics:
============================================================
Jobs needing PDF processing: 45
Jobs with external PDFs: 123
Jobs with Google Drive links: 67
Total jobs in database: 235
============================================================
```

### Step 3: Process PDFs

```bash
# Process 10 jobs (default batch size)
python process_pdfs.py

# Process 5 jobs
python process_pdfs.py --max-jobs 5

# Process 20 jobs at a time
python process_pdfs.py --batch-size 20

# Debug mode
python process_pdfs.py --log-level DEBUG
```

The script will:
1. Find jobs with `pdf_url IS NULL` and `gdrive_link IS NULL`
2. Re-fetch job details to get PDF URL
3. Check if PDF is from FreeJobAlert
4. Download PDF to temporary file
5. Upload to Google Drive
6. Update database with shareable Drive link
7. Clean up temporary files

### Step 4: Monitor Progress

Logs are saved to `pdf_processor.log`:

```bash
tail -f pdf_processor.log
```

## Testing

### Test Google Drive Upload

```bash
# Test with a specific PDF URL
python gdrive_uploader.py "https://img2.freejobalert.com/news/2026/02/852381-69856e084f12021262758.pdf"
```

Expected output:
```
✅ Upload successful!
Shareable link: https://drive.google.com/file/d/FILE_ID/view
```

## Database Schema

```sql
-- Jobs with external PDFs (saved directly)
SELECT title, pdf_url 
FROM jobs 
WHERE pdf_url IS NOT NULL;

-- Jobs needing Drive upload (FreeJobAlert PDFs)
SELECT title, job_url 
FROM jobs 
WHERE pdf_url IS NULL 
  AND gdrive_link IS NULL;

-- Jobs with Drive links (already uploaded)
SELECT title, gdrive_link 
FROM jobs 
WHERE gdrive_link IS NOT NULL;
```

## Workflow Summary

```
┌─────────────────────────────────────────────────────────┐
│                   Scrape FreeJobAlert                   │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
          ┌───────────────┐
          │ External PDF? │
          └───────┬───────┘
                  │
         ┌────────┴────────┐
         │                 │
        YES               NO
         │                 │
         ▼                 ▼
  ┌──────────────┐  ┌──────────────┐
  │ Save to      │  │ Leave NULL,  │
  │ pdf_url      │  │ needs upload │
  └──────────────┘  └──────┬───────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ Download PDF │
                    └──────┬───────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ Upload to    │
                    │ Google Drive │
                    └──────┬───────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ Save Drive   │
                    │ link to DB   │
                    └──────────────┘
```

## Automation

You can automate the entire workflow:

```bash
#!/bin/bash
# daily_job_sync.sh

echo "=== Scraping new jobs ==="
python main.py --no-pdf --max-pages 3

echo "\n=== Processing PDFs ==="
python process_pdfs.py --batch-size 20

echo "\n=== Statistics ==="
python process_pdfs.py --stats
```

Set up a cron job:
```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/freejobalert-scraper && ./daily_job_sync.sh >> logs/daily.log 2>&1
```

## Troubleshooting

### "Google credentials file not found"

- Ensure `credentials.json` is in project root
- Check `GOOGLE_CREDENTIALS_PATH` in `.env`

### "Permission denied" when uploading

- Share Drive folder with service account email
- Verify folder ID is correct
- Check service account has "Editor" role

### "Downloaded file is not a valid PDF"

- Some PDFs may be corrupted or access-restricted
- Check if PDF URL is still valid
- Try downloading manually to verify

### "API quota exceeded"

- Google Drive API has daily quotas
- Process smaller batches: `--batch-size 5`
- Wait and retry later

## Best Practices

1. **Start Small**: Test with `--max-jobs 5` first
2. **Monitor Logs**: Check `pdf_processor.log` for errors
3. **Rate Limiting**: Don't process too many jobs at once
4. **Regular Stats**: Run `--stats` to track progress
5. **Backup**: Keep Drive folder backed up
6. **Clean Up**: Periodically check for duplicate files in Drive

## File Naming Convention

Uploaded files are named:
```
{job_title}_{original_filename}.pdf
```

Example:
```
IOCL_Pipelines_Division_Recruitment_2026_852381-69856e084f12021262758.pdf
```

## API Limits

### Google Drive API
- **Queries per day**: 1 billion
- **Queries per 100 seconds per user**: 1,000
- **File uploads**: ~750 per day (for free accounts)

For production use, consider:
- Google Workspace account (higher limits)
- Batch processing over multiple days
- Caching and deduplication

## Support

For issues or questions:
1. Check logs: `pdf_processor.log`
2. Run with debug: `--log-level DEBUG`
3. Test Drive upload: `python gdrive_uploader.py <pdf_url>`
