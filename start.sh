#!/bin/bash
set -e

NASTRAN_DIR="data/NASTRAN-95"

mkdir -p data/chromadb data/indices

# Check if collection already has data
COUNT=$(python3 -c "
import chromadb
try:
    c = chromadb.PersistentClient(path='data/chromadb')
    col = c.get_collection('nastran95')
    print(col.count())
except Exception:
    print(0)
" 2>/dev/null || echo 0)

if [ "${COUNT:-0}" -gt "0" ]; then
    echo "INFO: ChromaDB has ${COUNT} chunks, skipping ingest."
else
    echo "INFO: No data found. Running first-time ingest..."

    if [ ! -d "${NASTRAN_DIR}" ]; then
        echo "INFO: Cloning NASTRAN-95 from GitHub..."
        git clone --depth=1 https://github.com/nasa/NASTRAN-95.git "${NASTRAN_DIR}"
    fi

    echo "INFO: Running ingestion pipeline (this takes ~10 min on first boot)..."
    legacylens ingest "${NASTRAN_DIR}"
    echo "INFO: Ingest complete."
fi

echo "INFO: Starting LegacyLens API server on port ${PORT:-8000}..."
exec uvicorn legacylens.api:app --host 0.0.0.0 --port "${PORT:-8000}"
