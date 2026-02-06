# FreeJobAlert.com Job Scraper

Automated job scraper that extracts job postings from FreeJobAlert.com, stores them in Supabase, downloads PDF notices, and uploads them to Google Drive.

## Features

- 🔍 Scrapes job listings from FreeJobAlert.com (latest notifications, government jobs, etc.)
- 💾 Stores job data in Supabase PostgreSQL database
- 📄 Downloads PDF notices automatically
- ☁️ Uploads PDFs to Google Drive and stores shareable links
- 🔄 Handles pagination and multiple job categories
- ⚡ Robust error handling and retry mechanisms
- 📊 Duplicate detection to avoid re-scraping

## Prerequisites

- Python 3.8+
- Supabase account and project
- Google Cloud Platform account with Drive API enabled
- Google Drive API credentials

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Anuj472/freejobalert-scraper.git
cd freejobalert-scraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```

Edit `.env` file with your credentials:
- Supabase URL and API key
- Google Drive credentials path
- Google Drive folder ID

## Supabase Setup

Create a table in your Supabase database:

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

-- Create index for faster lookups
CREATE INDEX idx_jobs_url ON jobs(job_url);
CREATE INDEX idx_jobs_scraped_at ON jobs(scraped_at);
```

## Google Drive API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Drive API
4. Create credentials (OAuth 2.0 Client ID or Service Account)
5. Download the credentials JSON file
6. Save it as `credentials.json` in the project root
7. Create a folder in Google Drive and note its ID from the URL

## Usage

### Basic Usage

```bash
python main.py
```

### Scrape Specific Categories

```bash
# Scrape latest notifications
python main.py --category latest-notifications

# Scrape government jobs
python main.py --category government-jobs

# Scrape bank jobs
python main.py --category bank-jobs
```

### Set Maximum Pages to Scrape

```bash
python main.py --max-pages 5
```

## Project Structure

```
freejobalert-scraper/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── config.py              # Configuration management
├── main.py                # Main execution script
├── scraper.py             # Web scraping logic
├── supabase_client.py     # Supabase database operations
├── gdrive_upload.py       # Google Drive upload functionality
└── credentials.json       # Google Drive credentials (not in git)
```

## Configuration

Edit `config.py` to customize:
- Scraping intervals
- Retry attempts
- Timeout settings
- User agent strings
- Categories to scrape

## Scheduling with Cron

To run the scraper daily at 9 AM:

```bash
crontab -e
```

Add:
```
0 9 * * * cd /path/to/freejobalert-scraper && /usr/bin/python3 main.py >> scraper.log 2>&1
```

## Docker Support (Optional)

Build and run with Docker:

```bash
docker build -t freejobalert-scraper .
docker run -d --env-file .env freejobalert-scraper
```

## Error Handling

- Automatic retries for failed requests
- Logging of all errors to `scraper.log`
- Graceful handling of missing PDFs
- Network timeout protection

## Data Schema

### Jobs Table

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| title | TEXT | Job title |
| organization | TEXT | Hiring organization |
| post_date | DATE | Posting date |
| last_date | DATE | Application deadline |
| vacancies | INTEGER | Number of positions |
| qualification | TEXT | Required qualifications |
| location | TEXT | Job location |
| job_url | TEXT | Original job posting URL |
| pdf_url | TEXT | PDF notice URL |
| gdrive_link | TEXT | Google Drive shareable link |
| category | TEXT | Job category |
| scraped_at | TIMESTAMP | When scraped |
| updated_at | TIMESTAMP | Last update time |

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Legal Disclaimer

This scraper is for educational purposes. Ensure you comply with:
- FreeJobAlert.com's terms of service
- Robots.txt directives
- Rate limiting and respectful scraping practices
- Data privacy regulations

## License

MIT License - see LICENSE file for details

## Support

For issues or questions:
- Open an issue on GitHub
- Check existing issues for solutions

## Roadmap

- [ ] Add email notifications for new jobs
- [ ] Implement job filtering by keywords
- [ ] Add support for multiple job portals
- [ ] Create web dashboard for viewing scraped jobs
- [ ] Add job alert notifications via Telegram/WhatsApp

---

**Note**: Always respect website terms of service and implement appropriate delays between requests to avoid overloading servers.