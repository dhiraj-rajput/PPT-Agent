#!/usr/bin/env bash
# setup_codespace.sh
# ------------------
# GitHub Codespace / Linux setup script for PPT-Agent.
# Run once after cloning the repo: bash scripts/setup_codespace.sh

set -e

echo "======================================="
echo "PPT-Agent Codespace Setup"
echo "======================================="

# 1. System dependencies
echo "[1/6] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    libreoffice \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0

# 2. Python dependencies
echo "[2/6] Installing Python dependencies..."
pip install -q -r requirements.txt

# 3. Docling + PaddleOCR (CPU-only)
echo "[3/6] Installing OCR libraries (CPU-only)..."
pip install -q docling
pip install -q paddlepaddle paddleocr

# 4. Install and start Ollama
echo "[4/6] Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.ai/install.sh | sh
fi

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!
echo "Ollama started (PID: $OLLAMA_PID)"
sleep 5  # Wait for Ollama to initialize

# 5. Pull Gemma 4 E4B model
echo "[5/6] Pulling gemma4:e4b model (this may take a few minutes)..."
ollama pull gemma4:e4b

# 6. Health checks
echo "[6/6] Running health checks..."

# Check LibreOffice
if command -v soffice &> /dev/null; then
    echo "  ✓ LibreOffice installed"
else
    echo "  ✗ LibreOffice NOT found - PDF conversion may fail"
fi

# Check Tesseract
if command -v tesseract &> /dev/null; then
    echo "  ✓ Tesseract OCR installed ($(tesseract --version 2>&1 | head -1))"
else
    echo "  ✗ Tesseract NOT found"
fi

# Check Ollama
if ollama list 2>/dev/null | grep -q "gemma4:e4b"; then
    echo "  ✓ gemma4:e4b model ready"
else
    echo "  ✗ gemma4:e4b not found - run: ollama pull gemma4:e4b"
fi

# Check Docling
python3 -c "import docling; print('  ✓ Docling available')" 2>/dev/null || echo "  ✗ Docling NOT installed"

echo ""
echo "Setup complete! Start the server with:"
echo "  python server.py"
echo ""
echo "Note: Ollama is running in background (PID: $OLLAMA_PID)"
echo "To stop it: kill $OLLAMA_PID"
