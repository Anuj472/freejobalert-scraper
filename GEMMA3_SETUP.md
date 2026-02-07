# Gemma 3 12B Setup Guide

## Overview

Gemma 3 12B is a multimodal LLM that can:
- ✅ Extract data from **text PDFs**
- ✅ Extract data from **scanned/image PDFs** (Vision)
- ✅ Generate **SEO-optimized blog posts**
- ✅ Process **128K tokens** (full PDFs in one go)
- ✅ Works **100% offline and free**

---

## System Requirements

### Hardware
```
Minimum:
- GPU: 8GB VRAM (NVIDIA recommended)
- RAM: 16GB
- Storage: 10GB free space

Recommended:
- GPU: 12GB+ VRAM
- RAM: 32GB
- Storage: 20GB free space
```

### Software
```
- Linux/macOS/Windows
- NVIDIA GPU drivers (for CUDA)
- Python 3.9+
- Poppler (for pdf2image)
```

---

## Installation Steps

### Step 1: Install Ollama

#### On Linux/macOS:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### On Windows:
1. Download from: https://ollama.com/download
2. Run the installer
3. Restart terminal

### Step 2: Install Poppler (for PDF image processing)

#### Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y poppler-utils
```

#### macOS:
```bash
brew install poppler
```

#### Windows:
1. Download from: https://github.com/oschwartz10612/poppler-windows/releases
2. Extract to `C:\Program Files\poppler`
3. Add to PATH: `C:\Program Files\poppler\Library\bin`

### Step 3: Install Python Dependencies

```bash
cd freejobalert-scraper
pip install -r requirements.txt
```

### Step 4: Pull Gemma 3 12B Model

```bash
# Pull the model (8.1 GB download)
ollama pull gemma3:12b

# Verify installation
ollama list
```

You should see:
```
NAME            ID              SIZE     MODIFIED
gemma3:12b      a1b2c3d4e5f6    8.1 GB   X minutes ago
```

### Step 5: Start Ollama Server

```bash
# Start in background
ollama serve &

# Or start in foreground (for debugging)
ollama serve
```

### Step 6: Test Gemma 3

```bash
# Test text generation
curl http://localhost:11434/api/chat -d '{
  "model": "gemma3:12b",
  "messages": [{"role": "user", "content": "Hello"}]
}'
```

If working, you'll get a JSON response.

---

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Ollama Configuration
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:12b

# Optional: Use Gemma 3 for all tasks
USE_GEMMA_FOR_PDF=true
USE_GEMMA_FOR_BLOG=true
```

---

## Usage

### Basic Usage

```python
from smart_processor import SmartJobProcessor

# Initialize
processor = SmartJobProcessor()

# Process job (will use Gemma 3 automatically)
job_data = processor.process_job(
    job_listing=job_info,
    html=page_html,
    details_url=url
)

# Result includes:
print(job_data['title'])          # Extracted data
print(job_data['blog_article'])   # SEO blog
print(job_data['seo_title'])      # SEO title
print(job_data['data_source'])    # 'pdf_gemma3' or 'html_css'
```

### Direct PDF Processing

```python
from gemma_processor import GemmaProcessor

gemma = GemmaProcessor()

# Extract from PDF (text or image)
data = gemma.process_pdf_url('https://example.com/notification.pdf')

print(data['vacancies'])    # 120
print(data['last_date'])    # '28-02-2026'
```

### Blog Generation Only

```python
from gemma_processor import GemmaProcessor

gemma = GemmaProcessor()

# Generate SEO blog from data
blog = gemma.generate_blog(job_data)

print(blog['seo_title'])          # SEO-optimized title
print(blog['article'])            # Full blog post
print(len(blog['faqs']))          # Number of FAQs
```

---

## Performance

### Processing Times (per job)

| Task | Time | Details |
|------|------|--------|
| Text PDF extraction | 5-8s | Fast path |
| Image PDF extraction | 10-15s | Vision processing |
| Blog generation | 15-20s | 800-1000 words |
| **Total per job** | **~30s** | PDF + Blog |

### Throughput

```
1 job = ~30 seconds
100 jobs = ~50 minutes
1000 jobs = ~8 hours
```

---

## Troubleshooting

### Issue: "Model not found"

**Solution:**
```bash
# Check if model exists
ollama list

# If not listed, pull again
ollama pull gemma3:12b
```

### Issue: "Connection refused"

**Solution:**
```bash
# Check if Ollama is running
ps aux | grep ollama

# Start Ollama
ollama serve
```

### Issue: "Out of memory"

**Solution:**
```bash
# Check GPU memory
nvidia-smi

# If < 8GB VRAM, consider:
# 1. Close other GPU applications
# 2. Use smaller model (not recommended)
# 3. Process in smaller batches
```

### Issue: "pdf2image error"

**Solution:**
```bash
# Install poppler
# Ubuntu/Debian:
sudo apt-get install poppler-utils

# macOS:
brew install poppler

# Windows: Add poppler to PATH
```

### Issue: "Slow processing"

**Solutions:**
1. Ensure GPU is being used:
   ```bash
   nvidia-smi
   # Should show ollama process using GPU
   ```

2. Check GPU utilization:
   ```bash
   watch -n 1 nvidia-smi
   # GPU-Util should be high during processing
   ```

3. Reduce context window if needed:
   ```python
   # In gemma_processor.py, modify num_ctx
   "num_ctx": 64000  # Instead of 128000
   ```

---

## Comparison with Other Models

| Model | VRAM | Vision | Context | Quality |
|-------|------|--------|---------|--------|
| **Gemma 3 12B** | 8.1GB | ✅ | 128K | ⭐⭐⭐⭐ |
| Gemma 3 27B | 17GB | ✅ | 128K | ⭐⭐⭐⭐⭐ |
| Llama 3.2 Vision 11B | 12GB | ✅ | 8K | ⭐⭐⭐⭐ |
| Llama 3.1 8B | 8GB | ❌ | 8K | ⭐⭐⭐ |

**Winner:** Gemma 3 12B for your use case! ✅

---

## Advantages

✅ **Single Model** - Both vision and text in one model  
✅ **128K Context** - Process entire 40-page PDFs  
✅ **Free** - No API costs, 100% local  
✅ **Private** - All data stays on your machine  
✅ **Offline** - Works without internet  
✅ **Fast** - Optimized for efficiency  
✅ **Quality** - Excellent extraction and blog generation  

---

## Cost Analysis

### Using Gemma 3 (Local)
```
Initial Setup:
- Download: Free (8.1 GB)
- Hardware: GPU with 8GB VRAM (you already have)

Running Costs:
- API costs: $0
- Electricity: ~$0.10 per 1000 jobs (GPU power)

Total for 1000 jobs: $0.10
```

### Using GPT-4 Vision (Cloud)
```
For 1000 jobs with 2-page PDFs:
- PDF processing: $0.01 × 2000 pages = $20
- Blog generation: $0.03 × 1000 = $30

Total: $50 per 1000 jobs
```

**Savings with Gemma 3: $50 per 1000 jobs!** 💰

---

## Next Steps

1. **Test with sample PDF:**
   ```bash
   python test_gemma.py
   ```

2. **Run scraper:**
   ```bash
   python main.py --category latest-notifications --max-pages 1
   ```

3. **Check database:**
   - Verify `blog_article` column is populated
   - Check `data_source` field (should be 'pdf_gemma3')

4. **Monitor performance:**
   ```bash
   watch -n 1 nvidia-smi  # Monitor GPU usage
   tail -f scraper.log    # Monitor logs
   ```

---

## Support

For issues:
1. Check logs: `scraper.log`
2. Test Ollama: `ollama list`
3. GPU check: `nvidia-smi`
4. Open issue on GitHub

---

## References

- Ollama: https://ollama.com
- Gemma 3 Model: https://ollama.com/library/gemma3
- Poppler: https://poppler.freedesktop.org/
