# PDF Processing Setup Guide

## Overview

This scraper uses **pdf2image** to convert PDF notifications to images before sending them to Gemma multimodal model. This fixes the "image: unknown format" error.

## Requirements

1. **Python Package**: `pdf2image`
2. **System Dependency**: Poppler (PDF rendering engine)

---

## Installation

### 1. Install Python Package

```bash
pip install pdf2image
```

This is already included in `requirements.txt`, so if you run:

```bash
pip install -r requirements.txt
```

It will be installed automatically.

---

### 2. Install Poppler (System Dependency)

Poppler is required to convert PDFs to images. Installation varies by platform:

#### **Ubuntu/Debian Linux**

```bash
sudo apt-get update
sudo apt-get install -y poppler-utils
```

#### **CentOS/RHEL/Fedora**

```bash
sudo yum install -y poppler-utils
```

#### **macOS**

Using Homebrew:

```bash
brew install poppler
```

#### **Windows**

1. Download Poppler for Windows:
   - Latest Release: https://github.com/oschwartz10612/poppler-windows/releases/
   - Download `Release-XX.XX.X-X.zip`

2. Extract to a folder (e.g., `C:\poppler`)

3. Add to PATH:
   - Open System Properties → Environment Variables
   - Edit `PATH` and add: `C:\poppler\Library\bin`

4. Verify installation:
   ```cmd
   pdfinfo -v
   ```

---

## Verification

Test if PDF support is working:

```python
from pdf2image import convert_from_path

try:
    # Try converting a test PDF
    images = convert_from_path('test.pdf', first_page=1, last_page=1)
    print(f"✓ PDF support working! Converted {len(images)} pages.")
except Exception as e:
    print(f"❌ PDF support failed: {e}")
```

---

## How It Works

### Before (❌ Broken)

```
PDF (binary) → base64 → Gemma API → ERROR: "unknown format"
```

Gemma multimodal expects **images** (PNG/JPEG), not raw PDF files.

### After (✅ Fixed)

```
PDF → pdf2image → PNG images → base64 → Gemma API → Success!
```

The scraper now:
1. Downloads the PDF notification
2. Converts first 3 pages to PNG images (150 DPI)
3. Resizes if too large (max 2048px)
4. Sends images to Gemma for data extraction

---

## Configuration

You can adjust PDF processing in `gemma_processor.py`:

```python
# Maximum pages to process (default: 3)
images = self._pdf_to_images(pdf_path, max_pages=3)

# DPI for conversion (default: 150)
images = convert_from_path(pdf_path, dpi=150)

# Maximum PDF size (default: 10MB)
if size_mb > 10:
    logger.warning("PDF too large")
```

---

## Troubleshooting

### Error: "pdf2image not installed"

**Solution:**
```bash
pip install pdf2image
```

---

### Error: "Unable to get page count. Is poppler installed?"

**Solution:**
Poppler is not installed or not in PATH.

- **Linux**: `sudo apt-get install poppler-utils`
- **macOS**: `brew install poppler`
- **Windows**: Download and add to PATH (see above)

---

### Error: "PDF too large (X MB)"

**Solution:**
The PDF exceeds the 10MB limit. The scraper will automatically fallback to HTML text extraction.

To increase the limit, edit `gemma_processor.py`:

```python
if size_mb > 15:  # Increase from 10 to 15 MB
    logger.warning("PDF too large")
```

---

### Error: "Page X too large (Y MB), skipping"

**Solution:**
A converted PNG image is too large. This is automatically handled - the scraper processes other pages and continues.

---

### PDF Processing Still Fails

If PDF conversion fails, the scraper automatically falls back to HTML text extraction:

```
⚠️  PDF extraction failed, falling back to HTML text...
```

This ensures the scraper continues working even if PDF processing fails.

---

## Performance Notes

- **First 3 pages only**: Most job notifications have details in first few pages
- **150 DPI**: Balance between quality and file size
- **Auto-resize**: Images > 2048px are automatically resized
- **Parallel processing**: Each PDF page is processed independently

---

## Complete Installation Example (Ubuntu)

```bash
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y poppler-utils

# 2. Install Python packages
pip install -r requirements.txt

# 3. Verify installation
python -c "from pdf2image import convert_from_path; print('✓ PDF support ready')"

# 4. Run scraper
python main.py
```

---

## What Gets Fixed

This update resolves:

- ✅ **500 Error**: "failed to process inputs: image: unknown format"
- ✅ **PDF Processing**: Multimodal Gemma can now read PDF notifications
- ✅ **Better Extraction**: Gemma sees actual PDF content, not just HTML summary
- ✅ **Fallback**: Automatically uses HTML if PDF fails

---

## Need Help?

If you still encounter issues:

1. Check logs for specific error messages
2. Verify poppler installation: `pdfinfo -v`
3. Test pdf2image: `python -c "import pdf2image; print(pdf2image.__version__)"`
4. Increase logging: Set `LOG_LEVEL=DEBUG` in `.env`

---

## Related Files

- `gemma_processor.py` - Main PDF processing logic
- `smart_processor.py` - Pipeline orchestration
- `requirements.txt` - Python dependencies
- `config.py` - Configuration settings
