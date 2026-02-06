#!/bin/bash
# Setup script for FreeJobAlert Scraper

echo "========================================"
echo "FreeJobAlert Scraper Setup"
echo "========================================"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d" " -f2 | cut -d"." -f1,2)
echo "✓ Python version: $PYTHON_VERSION"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

if [ $? -eq 0 ]; then
    echo "✓ Virtual environment created"
else
    echo "❌ Failed to create virtual environment"
    exit 1
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p pdfs logs
echo "✓ Directories created"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env file and add your credentials:"
    echo "   - SUPABASE_URL"
    echo "   - SUPABASE_KEY"
    echo "   - GOOGLE_DRIVE_FOLDER_ID"
    echo ""
else
    echo ""
    echo "✓ .env file already exists"
fi

# Check for Google credentials
if [ ! -f credentials.json ]; then
    echo ""
    echo "⚠️  WARNING: credentials.json not found"
    echo "   Please download your Google Drive API credentials and save as credentials.json"
    echo ""
else
    echo "✓ Google credentials found"
fi

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials"
echo "2. Add credentials.json for Google Drive API"
echo "3. Run: source venv/bin/activate"
echo "4. Run: python main.py"
echo ""
echo "For more information, see README.md"
echo ""