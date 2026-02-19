# FreeJobAlert Scraper

> Smart job scraper with PDF-first extraction using Gemma 3 12B multimodal + HTML fallback

---

## Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Installation](#️-installation)
- [Gemma 3 12B Setup](#-gemma-3-12b-setup)
- [Usage](#-usage)
- [Schema & Field Extraction](#-schema--field-extraction)
- [Extraction Flow](#-extraction-flow)
- [Project Structure](#-project-structure)
- [Database Schema](#️-database-schema)
- [PDF Handling](#-pdf-handling)
- [Google Drive Upload](#-google-drive-upload)
- [Content Validation System](#️-content-validation-system)
- [Aggressive Post-Generation Validation](#-aggressive-post-generation-validation)
- [URL Handling Strategy](#-url-handling-strategy)
- [Robust CSS-Only Parser](#-robust-css-only-parser)
- [Bug Fixes & Improvements](#-bug-fixes--improvements)
- [Configuration](#-configuration)
- [Performance](#-performance)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#contributing)
- [License](#-license)

---

## 🚀 Features

- **PDF-First Extraction**: Uses Gemma 3 12B multimodal to extract data from PDF notifications
- **HTML Fallback**: CSS parser extracts from HTML when no PDF available
- **Smart Category Detection**: Gemma determines job category (banking, railway, defence, etc.)
- **SEO Blog Generation**: Generates optimized blog content (<1000 words) with title, meta description, highlights, FAQs
- **Google Drive Upload**: Uploads FreeJobAlert PDFs to Google Drive
- **Link Filtering**: Removes FreeJobAlert links, keeps only official organization links
- **Two-Stage Content Validation**: Prevents freejobalert.com references from entering the database
- **Robust CSS Parser**: Pure CSS selectors + regex for fast, reliable extraction without LLM

---

## ⚡ Quick Start

### 1. Install Dependencies

```bash
git clone https://github.com/Anuj472/freejobalert-scraper.git
cd freejobalert-scraper
pip install -r requirements.txt
```

### 2. Setup Gemma 3 (Optional but Recommended)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:12b
ollama serve
```

### 3. Setup Google Drive (First Time Only)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Enable **Google Drive API**
2. Create **Service Account** → download `credentials.json` → save to project root
3. Create folder in [Google Drive](https://drive.google.com/) → share with service account email
4. Add to `.env`:
   ```env
   GOOGLE_CREDENTIALS_PATH=credentials.json
   GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
   ```

### 4. Setup Environment

```bash
cp .env.example .env
# Edit .env with your Supabase URL/KEY and optional configs
```

### 5. Run Scraper

```bash
python main.py --category latest-notifications --max-pages 2
```

### 6. Process FreeJobAlert PDFs (Upload to Drive)

```bash
python process_pdfs.py --stats       # Check what needs upload
python process_pdfs.py --max-jobs 10 # Upload PDFs
```

---

## 🛠️ Installation

### Prerequisites

- Python 3.9+
- Poppler (for PDF image processing)

### Install Poppler

```bash
# Ubuntu/Debian
sudo apt-get install -y poppler-utils

# macOS
brew install poppler

# Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases
# Add to PATH: C:\Program Files\poppler\Library\bin
```

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Run Database Migration

```bash
# Using psql
psql -f migrations/add_blog_columns.sql

# Or in Supabase SQL Editor:
# Copy and run migrations/add_blog_columns.sql
```

---

## 🤖 Gemma 3 12B Setup

### Overview

Gemma 3 12B is a multimodal LLM that extracts data from text/image PDFs, generates SEO blogs, processes 128K tokens, and works 100% offline and free.

### System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| GPU VRAM | 8 GB | 12+ GB |
| RAM | 16 GB | 32 GB |
| Storage | 10 GB | 20 GB |

### Installation

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh    # Linux/macOS
# Windows: Download from https://ollama.com/download

# 2. Pull Gemma 3 12B (8.1 GB download)
ollama pull gemma3:12b

# 3. Start server
ollama serve &

# 4. Verify
ollama list
curl http://localhost:11434/api/chat -d '{
  "model": "gemma3:12b",
  "messages": [{"role": "user", "content": "Hello"}]
}'

# 5. Test integration
python test_gemma.py
```

### Intelligent Fallback

```
Gemma 3 Available?
├─ YES → Use Gemma for PDF + Blog (best quality)
└─ NO  → Use HTML parser + Template blog (reliable fallback)
```

### Model Comparison

| Model | VRAM | Vision | Context | Quality |
|-------|------|--------|---------|---------|
| **Gemma 3 12B** | 8.1GB | ✅ | 128K | ⭐⭐⭐⭐ |
| Gemma 3 27B | 17GB | ✅ | 128K | ⭐⭐⭐⭐⭐ |
| Llama 3.2 Vision 11B | 12GB | ✅ | 8K | ⭐⭐⭐⭐ |

### Cost: $0 (Free & Local)

For 1000 jobs with Gemma 3: **$0** vs GPT-4 Vision: **$50**

---

## 🚀 Usage

```bash
# Scrape latest notifications (default: 2 pages)
python main.py --category latest-notifications

# Scrape with more pages
python main.py --category latest-notifications --max-pages 5

# Skip PDF processing (HTML only)
python main.py --category latest-notifications --no-pdf

# Process single job programmatically
```

```python
from smart_processor import SmartJobProcessor

processor = SmartJobProcessor()
job_data = processor.process_job(
    job_listing=job_info,
    html=page_html,
    details_url=url
)

print(job_data['title'])
print(job_data['blog_article'])
print(job_data['data_source'])  # 'pdf_gemma3' or 'html_css'
```

### Daily Automation

```bash
#!/bin/bash
# daily_job_sync.sh
python main.py --no-pdf --max-pages 3
python process_pdfs.py --batch-size 20
python process_pdfs.py --stats
```

```bash
# Cron: run daily at 2 AM
0 2 * * * cd /path/to/freejobalert-scraper && ./daily_job_sync.sh >> logs/daily.log 2>&1
```

---

## 📋 Schema & Field Extraction

### LLM Output (Gemma 3 from PDF or HTML text)

```python
LLM_FIELDS = [
    'title',              # Job title/post name
    'organization',       # Organization/department name
    'vacancies',          # Total vacancy count (INTEGER, not year)
    'qualification',      # Educational qualification
    'location',           # Job location/posting place
    'category',           # Job category (banking/railway/defence/ssc/upsc/etc.)
    'advt_no',            # Advertisement/notification number
    'full_description',   # Complete job description
    'salary',             # Pay scale/salary range
    'age_limit',          # Age requirement
    'application_fee',    # Fee structure
    'selection_process',  # Exam/selection method
    'how_to_apply',       # Application instructions
    'important_dates',    # Dates (JSON: {"Application Start": "...", "Last Date": "..."})
    'vacancy_details',    # Post-wise breakdown (JSON: {"Manager": "10", "Clerk": "20"})
]
```

### HTML Parse (CSS selectors from HTML)

```python
HTML_FIELDS = [
    'post_date',         # Article publish date (from HTML metadata)
    'last_date',         # Application deadline (from HTML tables)
    'job_url',           # Job details page URL
    'pdf_url',           # PDF notification URL
    'gdrive_link',       # Google Drive uploaded PDF link
    'official_website',  # Organization official website
]
```

### CRITICAL RULE: ❌ NO FreeJobAlert Links

All extracted links are filtered — links containing `freejobalert.com` are removed. Links can be NULL but NEVER contain freejobalert.com.

---

## 📊 Extraction Flow

### Scenario 1: PDF Available

```
1. Download PDF from URL
2. Gemma 3 extracts LLM fields from PDF (title, organization, vacancies, etc.)
3. HTML parser extracts (post_date, last_date, URLs)
4. Filter FreeJobAlert links
5. Merge data + generate blog
6. Save to Supabase
```

### Scenario 2: No PDF Available

```
1. HTML parser extracts basic info
2. Gemma 3 analyzes HTML text content (determines category, extracts fields)
3. HTML parser extracts (post_date, last_date, URLs)
4. Filter FreeJobAlert links
5. Merge data + generate blog
6. Save to Supabase
```

---

## 📁 Project Structure

```
freejobalert-scraper/
├── main.py                 # Main execution script
├── config.py               # Configuration settings
├── scraper.py              # Web scraper (listing pages)
├── smart_processor.py      # Smart extraction orchestrator
├── gemma_processor.py      # Gemma 3 12B PDF/text processor
├── robust_parser.py        # HTML CSS parser
├── content_validator.py    # Content validation utilities
├── supabase_client.py      # Supabase database client
├── gdrive_uploader.py      # Google Drive uploader
├── process_pdfs.py         # Batch PDF processor
├── test_gemma.py           # Gemma 3 test suite
└── requirements.txt        # Python dependencies
```

---

## 🗄️ Database Schema

See `schema.sql` for complete Supabase table structure.

```sql
create table public.jobs (
  id uuid primary key default gen_random_uuid(),

  -- LLM extracted fields
  title text not null,
  organization text,
  vacancies integer,
  qualification text,
  location text,
  category text,
  advt_no text,
  full_description text,
  salary text,
  age_limit text,
  application_fee text,
  selection_process text,
  how_to_apply text,
  important_dates jsonb,
  vacancy_details jsonb,

  -- HTML parsed fields
  post_date date,
  last_date date,
  job_url text not null unique,
  pdf_url text,
  gdrive_link text,
  official_website text,

  -- Auto-generated fields
  scraped_at timestamp default now(),
  updated_at timestamp default now(),

  -- SEO fields (generated by Gemma)
  seo_title text,
  meta_description text,
  blog_article text,
  highlights jsonb,
  faqs jsonb,

  -- Metadata
  freejobalert_url text unique,
  data_source text check (data_source in ('pdf_gemma3', 'html_css'))
);
```

### Database Constraints (FreeJobAlert Prevention)

```sql
ALTER TABLE jobs ADD CONSTRAINT check_no_fja_pdf_url
CHECK (pdf_url IS NULL OR pdf_url NOT ILIKE '%freejobalert.com%');

ALTER TABLE jobs ADD CONSTRAINT check_no_fja_official_website
CHECK (official_website IS NULL OR official_website NOT ILIKE '%freejobalert.com%');

ALTER TABLE jobs ADD CONSTRAINT check_no_fja_job_url
CHECK (job_url IS NULL OR job_url NOT ILIKE '%freejobalert.com%');
```

---

## 📄 PDF Handling

The scraper distinguishes between two types of PDFs:

| PDF Source | Field | Action |
|------------|-------|--------|
| **FreeJobAlert** (`img2.freejobalert.com`) | `gdrive_link` | Download → Upload to Google Drive → Store Drive link |
| **External** (bank/govt sites) | `pdf_url` | Store original URL directly |
| **No PDF** | Both NULL | No PDF available |

### Query PDFs

```sql
-- Get all jobs with any PDF
SELECT title, organization,
  COALESCE(gdrive_link, pdf_url) as pdf_link,
  CASE
    WHEN gdrive_link IS NOT NULL THEN 'Google Drive'
    WHEN pdf_url IS NOT NULL THEN 'External'
    ELSE 'No PDF'
  END as pdf_source
FROM jobs ORDER BY scraped_at DESC LIMIT 10;
```

---

## ☁️ Google Drive Upload

### Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Enable **Google Drive API**
2. Create Service Account → download `credentials.json`
3. Create folder in Google Drive → share with service account email (Editor permission)
4. Add to `.env`:
   ```env
   GOOGLE_CREDENTIALS_PATH=credentials.json
   GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
   ```

### Usage

```bash
# Check stats
python process_pdfs.py --stats

# Process PDFs (download + upload to Drive)
python process_pdfs.py --max-jobs 10

# Test a single PDF upload
python gdrive_uploader.py "https://img2.freejobalert.com/news/2026/02/test.pdf"
```

### File Naming

Uploaded files: `{job_title}_{original_filename}.pdf`

---

## 🛡️ Content Validation System

Two-stage validation prevents freejobalert.com references from entering the database.

### Stage 1: Clean Input (Before LLM)
- Remove freejobalert from scraped content
- Pass clean content to Gemma 3 for blog generation

### Stage 2: Validate Output (Before Database)
- Double-check LLM-generated content
- Auto-remove any accidental mentions
- Guarantee database only receives clean data

### Integration

```python
# In supabase_client.py (add before database insert):
from content_validator import sanitize_job_data
insert_data = sanitize_job_data(insert_data)

# In gemma_processor.py (add to blog prompt):
from content_validator import get_llm_prompt_instructions
prompt = f"""{get_llm_prompt_instructions()}
Your existing prompt...
"""
```

### What Gets Prevented

| Content Type | Example | Result |
|--------------|---------|--------|
| Markdown links | `[details](https://freejobalert.com/...)` | Text only |
| Plain URLs | `https://www.freejobalert.com/articles/123` | Removed |
| Source citations | `**Source:** [freejobalert](...)` | Removed |
| Text mentions | "Check freejobalert daily" | "Check official source daily" |
| URL fields | `job_url: https://freejobalert.com/...` | Set to `None` |

### Test Validation

```bash
python content_validator.py
```

---

## 🚨 Aggressive Post-Generation Validation

In addition to the two-stage system, `gemma_processor.py` includes aggressive post-generation validation:

### Validation Levels

1. **Field Cleaning** (1-3 violations): Auto-clean fields, remove freejobalert content
2. **Field Removal**: Remove entire field if cleaning fails
3. **Complete Rejection** (>3 violations): Reject entire blog, return `None`

### Functions

- `_aggressive_freejobalert_check(text)` — Detects ANY freejobalert reference
- `_remove_all_freejobalert_content(text)` — Multi-pass removal (URLs, markdown, sentences, text mentions)
- `_validate_and_clean_json_response(data)` — Field-by-field validation with rejection threshold

---

## 🔗 URL Handling Strategy

### Priority-Based `job_url` Selection

1. **`application_url`** (highest) — "Apply Online" link
2. **`official_website`** (medium) — Organization website
3. **FreeJobAlert URL** (fallback) — Only if no organization URL found

### Database Fields

| Field | Purpose | FreeJobAlert? |
|-------|---------|---------------|
| `job_url` | "Apply Online" link | ❌ Blocked |
| `freejobalert_url` | Source page tracking | ✅ Allowed |
| `pdf_url` | Official PDF notification | ❌ Blocked |
| `official_website` | Organization website | ❌ Blocked |
| `gdrive_link` | Uploaded FreeJobAlert PDFs | ✅ `drive.google.com` |

---

## 🔧 Robust CSS-Only Parser

### No LLM Required

The `robust_parser.py` uses pure CSS selectors + regex for fast, reliable extraction.

| Feature | LLM Parser | Robust CSS Parser |
|---------|------------|-------------------|
| **Speed** | 30-60s/job | 2-3s/job ⚡ |
| **Accuracy** | 85% | 90%+ |
| **Dependencies** | Ollama | None |
| **Reliability** | Timeouts | Always works |

### Vacancies Extraction (4 Methods)

1. **Title extraction**: "SBI Recruitment 2026 - Apply for 40 Posts" → 40
2. **Content search**: "Total Posts: 150" → 150
3. **Pattern matching**: "Apply for 80 Vacancies" → 80
4. **Table parsing**: Sum of vacancy columns

Automatically filters out years (2024-2030) and validates range (1-50000).

---

## 🐛 Bug Fixes & Improvements

### Fixed: Vacancies Showing "2026" Instead of Count

**Problem**: The `vacancies` field extracted year instead of job count.

**Solution**:
- Better prompt with explicit examples and anti-patterns
- Post-processing filters out years (2024-2030 range)
- Result: 20% → **90%+** accuracy for vacancies

### Fixed: FreeJobAlert Links in Database

**Problem**: FreeJobAlert links appeared in `blog_article`, `how_to_apply`, and URL fields.

**Solution**: Multi-layer defense:
1. **Extraction-level filtering** in `robust_parser.py` and `smart_processor.py`
2. **Database-level constraints** (CHECK constraints reject FreeJobAlert URLs)
3. **Data cleanup** migrations for existing records

### Fixed: `job_url` Pointed to FreeJobAlert

**Problem**: `job_url` was set to FreeJobAlert detail page.

**Solution**: Now extracts "Apply Online" link; `freejobalert_url` stores source for tracking.

### Improved Architecture

- Old: CSS extracts some fields → LLM fills missing → merge (error-prone)
- New: Feed ALL raw data to LLM once → complete structured JSON (better context)

---

## 🔧 Configuration

### Environment Variables (.env)

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Ollama (optional, defaults to localhost)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:12b

# Feature Toggles
USE_GEMMA_FOR_PDF=true
USE_GEMMA_FOR_BLOG=true

# Google Drive (optional)
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_DRIVE_FOLDER_ID=your-folder-id

# Performance
GEMMA_TIMEOUT=120
GEMMA_CONTEXT_SIZE=128000
```

---

## 📈 Performance

### Processing Times (per job)

| Task | Time |
|------|------|
| Text PDF extraction | 5-8s |
| Image PDF extraction | 10-15s |
| Blog generation | 15-20s |
| HTML-only extraction | 2-3s |
| **Total (PDF + Blog)** | **~30s** |

### Throughput

```
1 job     = ~30 seconds
100 jobs  = ~50 minutes
1000 jobs = ~8 hours
```

### Resource Usage (with Gemma 3)

- CPU: Light
- RAM: ~2 GB
- GPU: 8 GB VRAM

---

## 🐞 Troubleshooting

### Gemma 3 Not Available

```bash
ollama list                    # Check if model exists
ollama pull gemma3:12b         # Pull if missing
ollama run gemma3:12b "Hello"  # Test model
```

### Connection Refused

```bash
ps aux | grep ollama     # Check if running
ollama serve             # Start Ollama
```

### Out of Memory

```bash
nvidia-smi               # Check GPU memory
# Close other GPU apps, or reduce context size in gemma_processor.py
```

### PDF Processing Fails

```bash
sudo apt-get install poppler-utils   # Ubuntu/Debian
brew install poppler                 # macOS
```

### Google Drive Issues

- **Credentials not found**: Ensure `credentials.json` in project root
- **Permission denied**: Share Drive folder with service account email
- **API quota exceeded**: Process smaller batches with `--batch-size 5`

### Supabase Connection Error

```bash
cat .env   # Verify credentials
```

### Validation Not Running

```bash
grep "🛡️" scraper.log    # Check for validation messages
grep -n "from content_validator" *.py  # Verify imports
```

---

## Contributing

### Reporting Bugs

Create an issue with: clear description, steps to reproduce, expected vs actual behavior, environment, and logs.

### Code Contributions

1. Fork and clone the repo
2. Create a branch: `git checkout -b feature/your-feature-name`
3. Setup: `chmod +x setup.sh && ./setup.sh && source venv/bin/activate`
4. Follow PEP 8, add comments, update docs
5. Test: `python test_connection.py && python main.py --max-pages 1`
6. Commit with conventional messages (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
7. Push and create a Pull Request

### Priority Areas

- **High**: Improved HTML parsing, better date extraction, rate limiting, retry logic
- **Medium**: Email/Telegram notifications, keyword filtering, web dashboard, job deduplication
- **Nice to Have**: Mobile app integration, analytics, job recommendation engine

---

## 📄 License

MIT License

## 👤 Author

**Anuj Kumar Mishra** — GitHub: [@Anuj472](https://github.com/Anuj472)

## 🙏 Acknowledgments

- Gemma 3 12B by Google DeepMind
- Ollama for local LLM inference
- Supabase for database
- FreeJobAlert.com for job listings
