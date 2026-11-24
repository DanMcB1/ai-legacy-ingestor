#!/usr/bin/env bash
# Start the Unstructured Legacy Ingestor locally. No API key required.
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v tesseract >/dev/null 2>&1; then
  echo "Tesseract OCR is not installed. On Debian/Ubuntu: sudo apt-get install -y tesseract-ocr tesseract-ocr-eng" >&2
  echo "The app can still ingest mainframe, CSV, Excel, and text samples without it." >&2
fi
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/streamlit run app.py --server.headless true
