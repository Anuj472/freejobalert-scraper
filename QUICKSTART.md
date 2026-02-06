# Quick Start Guide - FreeJobAlert Scraper

## Windows Installation

### Step 1: Install Dependencies

Open PowerShell or Command Prompt in the project directory and run:

```powershell
# Install all required packages
pip install -r requirements.txt
```

Or use the automated setup script:

```powershell
# Run setup script
.\setup.bat
```

### Step 2: Create Virtual Environment (Recommended)

```powershell
# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

1. Copy `.env.example` to `.env`:
   ```powershell
   copy .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-anon-key
   GOOGLE_DRIVE_FOLDER_ID=your-drive-folder-id
   ```

### Step 4: Set Up Supabase Database

1. Go to your Supabase project dashboard
2. Navigate to SQL Editor
3. Run this SQL query:

```sql
CREATE TABLE jobs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  title TEXT NOT NULL,
  organization TEXT,
  post_date DATE,
  last_date DATE,
  vacancies INTEGER,
  qualification TEXT,
  location TEXT,
  job_url TEXT UNIQUE NOT NULL,
  pdf_url TEXT,
  gdrive_link TEXT,
  category TEXT,
  scraped_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_jobs_url ON jobs(job_url);
CREATE INDEX idx_jobs_scraped_at ON jobs(scraped_at);
```

### Step 5: Set Up Google Drive API

#### Option A: Service Account (Recommended for automation)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable **Google Drive API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Drive API"
   - Click "Enable"
4. Create Service Account:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "Service Account"
   - Fill in details and create
   - Click on the service account
   - Go to "Keys" tab
   - "Add Key" > "Create new key" > "JSON"
   - Save as `credentials.json` in project root
5. Create a folder in Google Drive
6. Share the folder with the service account email (found in credentials.json)
7. Copy the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/[THIS_IS_THE_FOLDER_ID]
   ```

#### Option B: OAuth 2.0 (For personal use)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable **Google Drive API**
3. Create OAuth 2.0 Client ID:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop app"
   - Download JSON
   - Save as `credentials.json` in project root
4. First run will open browser for authorization

### Step 6: Test Connections

```powershell
python test_connection.py
```

This will verify:
- Configuration validity
- Supabase connection
- Google Drive access
- Scraper functionality

### Step 7: Run the Scraper

```powershell
# Basic usage - scrape all categories
python main.py

# Scrape specific category
python main.py --category government-jobs

# Limit pages per category (good for testing)
python main.py --max-pages 2

# Skip PDF download and upload
python main.py --no-pdf
```

## Linux/Mac Installation

### Quick Setup

```bash
# Run setup script
chmod +x setup.sh
./setup.sh

# Activate virtual environment
source venv/bin/activate

# Test connections
python test_connection.py

# Run scraper
python main.py
```

## Troubleshooting

### ModuleNotFoundError: No module named 'supabase'

**Solution:**
```powershell
pip install -r requirements.txt
```

### ImportError: No module named 'google'

**Solution:**
```powershell
pip install google-api-python-client google-auth google-auth-oauthlib
```

### SSL Certificate Error

**Solution (Windows):**
```powershell
pip install --upgrade certifi
python -m pip install --upgrade pip
```

### Google Drive Authentication Failed

**Solutions:**
1. Check `credentials.json` is in project root
2. For service account: Ensure folder is shared with service account email
3. For OAuth: Delete `token.pickle` and re-authenticate
4. Verify `GOOGLE_DRIVE_FOLDER_ID` in `.env` is correct

### Supabase Connection Error

**Solutions:**
1. Verify `SUPABASE_URL` format: `https://xxxxx.supabase.co`
2. Use the **anon/public** key, not the service_role key
3. Check Supabase project is not paused
4. Verify table `jobs` exists

### Scraping Returns Empty Results

**Possible causes:**
1. Website structure changed - may need to update selectors
2. Rate limiting - increase `SCRAPER_DELAY` in `.env`
3. User agent blocked - try different `SCRAPER_USER_AGENT`

### PDF Download Fails

**Solutions:**
1. Some jobs may not have PDF links
2. PDF URL may be indirect (requires clicking through)
3. Check network connectivity
4. Verify `pdfs/` directory exists and is writable

## Command Line Options

```powershell
# Show help
python main.py --help

# Available options:
--category <name>      # Specific category to scrape
--max-pages <number>   # Max pages per category (default: 5)
--no-pdf              # Skip PDF download and upload
```

## Scheduling (Windows)

### Using Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Name: "FreeJobAlert Scraper"
4. Trigger: Daily at 9:00 AM
5. Action: Start a program
   - Program: `C:\Python3x\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\path\to\freejobalert-scraper`
6. Save

### Using PowerShell Script

Create `run_scraper.ps1`:
```powershell
Set-Location "C:\path\to\freejobalert-scraper"
.\venv\Scripts\activate
python main.py
```

Schedule with Task Scheduler to run this script.

## Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|----------|
| SUPABASE_URL | Yes | Your Supabase project URL | https://xxx.supabase.co |
| SUPABASE_KEY | Yes | Supabase anon/public key | eyJhbGc... |
| GOOGLE_DRIVE_FOLDER_ID | Yes | Google Drive folder ID | 1a2b3c4d5e6f |
| GOOGLE_CREDENTIALS_PATH | No | Path to credentials.json | credentials.json |
| SCRAPER_USER_AGENT | No | Custom user agent | Mozilla/5.0... |
| SCRAPER_DELAY | No | Delay between requests (seconds) | 2 |
| SCRAPER_MAX_RETRIES | No | Max retry attempts | 3 |
| SCRAPER_TIMEOUT | No | Request timeout (seconds) | 30 |
| LOG_LEVEL | No | Logging level | INFO |
| LOG_FILE | No | Log file path | scraper.log |

## Data Flow

```
1. Scraper fetches job listings from FreeJobAlert.com
   ↓
2. Parses HTML and extracts job details
   ↓
3. Downloads PDF notices (if available)
   ↓
4. Uploads PDFs to Google Drive
   ↓
5. Gets shareable Drive link
   ↓
6. Stores all data in Supabase
```

## Categories Available

- `latest-notifications`
- `government-jobs`
- `bank-jobs`
- `railway-jobs`
- `teaching-jobs`
- `police-jobs`
- `engineering-jobs`

## Tips for Best Results

1. **Start small**: Use `--max-pages 1` for initial testing
2. **Check logs**: Monitor `scraper.log` for issues
3. **Verify data**: Check Supabase and Google Drive after each run
4. **Adjust delays**: Increase if you get rate limited
5. **Schedule wisely**: Run during off-peak hours for FreeJobAlert.com
6. **Monitor storage**: PDFs can accumulate - consider cleanup strategy

## Getting Help

- Check `scraper.log` for detailed error messages
- Run `python test_connection.py` to diagnose connection issues
- Review CONTRIBUTING.md for development guidelines
- Open an issue on GitHub with:
  - Error message
  - Log excerpt
  - Steps to reproduce
  - Your environment details

## Next Steps After Setup

1. ✅ Test with limited scraping: `python main.py --max-pages 1`
2. ✅ Verify data in Supabase dashboard
3. ✅ Check PDFs uploaded to Google Drive
4. ✅ Review logs for any warnings
5. ✅ Set up scheduled runs
6. ✅ Configure notifications (optional)

---

**Need more help?** See the full [README.md](README.md) or [CONTRIBUTING.md](CONTRIBUTING.md)