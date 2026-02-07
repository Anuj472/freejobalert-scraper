# FreeJobAlert Scraper

> Smart job scraper with PDF-first extraction using Gemma 3 12B multimodal + HTML fallback

## 🚀 Features

- **PDF-First Extraction**: Uses Gemma 3 12B multimodal to extract data from PDF notifications
- **HTML Fallback**: CSS parser extracts from HTML when no PDF available
- **Smart Category Detection**: Gemma determines job category (banking, railway, defence, etc.)
- **SEO Blog Generation**: Generates optimized blog content (<1000 words)
- **Google Drive Upload**: Uploads FreeJobAlert PDFs to Google Drive
- **Link Filtering**: Removes FreeJobAlert links, keeps only official organization links

## 📋 Schema Field Extraction

### **LLM Output** (Gemma 3 from PDF or HTML text):

```python
# Gemma extracts these fields by analyzing PDF/text content:
LLM_FIELDS = [
    'title',              # Job title/post name
    'organization',       # Organization/department name
    'vacancies',          # Total vacancy count (INTEGER, not year)
    'qualification',      # Educational qualification
    'location',           # Job location/posting place
    'category',           # Job category (banking/railway/defence/ssc/upsc/etc.)
    'advt_no',           # Advertisement/notification number
    'full_description',  # Complete job description
    'salary',            # Pay scale/salary range
    'age_limit',         # Age requirement
    'application_fee',   # Fee structure
    'selection_process', # Exam/selection method
    'how_to_apply',      # Application instructions
    'important_dates',   # Dates (JSON: {"Application Start": "...", "Last Date": "..."})
    'vacancy_details',   # Post-wise breakdown (JSON: {"Manager": "10", "Clerk": "20"})
]
```

### **HTML Parse** (CSS selectors from HTML):

```python
# HTML parser extracts these using CSS selectors:
HTML_FIELDS = [
    'post_date',         # Article publish date (from HTML metadata)
    'last_date',         # Application deadline (from HTML tables)
    'job_url',           # Job details page URL
    'pdf_url',           # PDF notification URL
    'gdrive_link',       # Google Drive uploaded PDF link
    'official_website',  # Organization official website
    'organization_url',  # Organization URL
    'application_url',   # Online application URL
]
```

### **CRITICAL RULE**: ❌ NO FreeJobAlert Links

```python
# All extracted links are filtered:
if 'freejobalert.com' in url:
    url = None  # Remove FreeJobAlert links

# Links can be NULL but NEVER contain freejobalert.com
```

## 🎯 Category Detection

Gemma 3 determines category based on organization:

```python
CATEGORIES = {
    'banking': ['SBI', 'IBPS', 'RBI', 'Bank of India', 'PNB', 'Canara Bank'],
    'railway': ['Indian Railways', 'RRB', 'Railway Recruitment Board'],
    'defence': ['Indian Army', 'Navy', 'Air Force', 'DRDO', 'NDA', 'Coast Guard'],
    'ssc': ['Staff Selection Commission', 'SSC'],
    'upsc': ['Union Public Service Commission', 'UPSC'],
    'police': ['Police Department', 'State Police', 'Central Police'],
    'teaching': ['University', 'School', 'Education Department', 'UGC', 'NCERT'],
    'psu': ['NTPC', 'ONGC', 'SAIL', 'BHEL', 'Coal India'],
    'state-govt': ['State Government Department'],
    'central-govt': ['Central Government Department'],
}
```

## 📊 Extraction Flow

### **Scenario 1: PDF Available**

```
1. Download PDF from URL
2. Gemma 3 extracts LLM fields from PDF:
   - title, organization, vacancies, category, location, etc.
   - NO URLs (Gemma doesn't extract links)
   - NO post_date (comes from HTML)
3. HTML parser extracts:
   - post_date, last_date (from HTML tables)
   - pdf_url, application_url, official_website
4. Filter FreeJobAlert links
5. Merge data + generate blog
6. Save to Supabase
```

### **Scenario 2: NO PDF Available**

```
1. HTML parser extracts basic info
2. Gemma 3 analyzes HTML text content:
   - Reads organization name: "Punjab and Sind Bank"
   - Determines category: "banking"
   - Extracts qualification, location, etc.
3. HTML parser extracts:
   - post_date, last_date, URLs
4. Filter FreeJobAlert links
5. Merge data + generate blog
6. Save to Supabase
```

## 🛠️ Installation

```bash
# Clone repository
git clone https://github.com/Anuj472/freejobalert-scraper.git
cd freejobalert-scraper

# Install dependencies
pip install -r requirements.txt

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Gemma 3 12B model
ollama pull gemma3:12b

# Setup environment variables
cp .env.example .env
# Edit .env with your:
# - Supabase URL and KEY
# - Google Drive credentials (optional)
```

## 🚀 Usage

```bash
# Scrape latest notifications (default: 2 pages)
python main.py --category latest-notifications

# Scrape specific category with more pages
python main.py --category latest-notifications --max-pages 5

# Skip PDF processing (HTML only)
python main.py --category latest-notifications --no-pdf
```

## 📁 Project Structure

```
freejobalert-scraper/
├── main.py                 # Main execution script
├── config.py               # Configuration settings
├── scraper.py              # Web scraper (listing pages)
├── smart_processor.py      # Smart extraction orchestrator
├── gemma_processor.py      # Gemma 3 12B PDF/text processor
├── robust_parser.py        # HTML CSS parser
├── supabase_client.py      # Supabase database client
├── gdrive_upload.py        # Google Drive uploader
└── requirements.txt        # Python dependencies
```

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
  organization_url text,
  application_url text,
  
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

## 🔧 Configuration

### Environment Variables (.env)

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Ollama (optional, defaults to localhost)
OLLAMA_URL=http://localhost:11434

# Google Drive (optional)
GOOGLE_DRIVE_CREDENTIALS_FILE=path/to/credentials.json
GOOGLE_DRIVE_FOLDER_ID=your-folder-id
```

## 📈 Performance

- **PDF Extraction**: ~15-30 seconds per job (with Gemma 3)
- **HTML Extraction**: ~5-10 seconds per job
- **Blog Generation**: ~20-40 seconds per job
- **Total**: ~40-80 seconds per job (with PDF + blog)

## 🤖 Gemma 3 12B Requirements

- **RAM**: 16 GB minimum
- **VRAM**: 8.1 GB (for GPU acceleration)
- **Context**: 128K tokens
- **Features**: Vision + Text

## 📝 Example Output

```json
{
  "title": "Deputy Manager Recruitment 2026",
  "organization": "Export-Import Bank of India",
  "category": "banking",
  "vacancies": 20,
  "location": "Mumbai, Maharashtra",
  "qualification": "Post Graduate Degree in relevant field",
  "last_date": "15-02-2026",
  "salary": "Rs. 60,000 - 1,80,000",
  "application_url": "https://www.eximbankindia.in/careers",
  "pdf_url": null,
  "gdrive_link": "https://drive.google.com/file/d/...",
  "data_source": "pdf_gemma3",
  "blog_article": "# Deputy Manager Recruitment..."
}
```

## 🐛 Troubleshooting

### Gemma 3 not available
```bash
# Check Ollama is running
ollama list

# Pull model if missing
ollama pull gemma3:12b

# Test model
ollama run gemma3:12b "Hello"
```

### PDF processing fails
```bash
# Install poppler for pdf2image
sudo apt-get install poppler-utils  # Ubuntu/Debian
brew install poppler  # macOS
```

### Supabase connection error
```bash
# Check .env file
cat .env

# Verify credentials in Supabase dashboard
```

## 📄 License

MIT License

## 👤 Author

**Anuj Kumar Mishra**
- GitHub: [@Anuj472](https://github.com/Anuj472)

## 🙏 Acknowledgments

- Gemma 3 12B by Google
- Ollama for local LLM inference
- Supabase for database
- FreeJobAlert.com for job listings
