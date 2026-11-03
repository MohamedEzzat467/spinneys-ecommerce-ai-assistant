#!/usr/bin/env bash
# ======================================================================
# Spinneys Conversational Shopping Assistant - One-Command Startup (Bash)
# ======================================================================

set -e

echo "======================================================================"
echo "   Spinneys Conversational Shopping Assistant - One-Command Startup   "
echo "======================================================================"
echo ""

# 1. Check Python virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    echo "[ERROR] Virtual environment not found at ./venv"
    echo "Please create it using: python3 -m venv venv"
    exit 1
fi

# 2. Check Data Layer
if [ ! -f "data/retrieval_meta.parquet" ]; then
    echo "[WARNING] 'data/retrieval_meta.parquet' not found! Exporting..."
    python scripts/export_retrieval_parquets.py || {
        echo "[ERROR] Failed to export parquets. Check MySQL credentials in .env"
        exit 1
    }
fi

if [ ! -d "data/vectordb" ]; then
    echo "[WARNING] Vector database folder 'data/vectordb' missing!"
    echo "You may need to run: python scripts/ingest.py"
fi

mkdir -p logs

echo "[INFO] Starting FastAPI Backend on http://localhost:8000 ..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

echo "[INFO] Starting Frontend Chat UI on http://localhost:3000 ..."
python -m http.server 3000 --directory frontend &
UI_PID=$!

trap "kill $API_PID $UI_PID 2>/dev/null; exit" INT TERM EXIT

echo ""
echo "======================================================================"
echo "   Spinneys Assistant is now running!"
echo "======================================================================"
echo "   - Frontend Chat UI      : http://localhost:3000"
echo "   - API & Swagger Docs    : http://localhost:8000/docs"
echo "   - System Health Check   : http://localhost:8000/health"
echo "======================================================================"
echo "Press [Ctrl+C] to stop all servers."
echo ""

wait
