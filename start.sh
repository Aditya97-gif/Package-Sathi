#!/usr/bin/env bash
# start.sh — Launch both backend and frontend in development mode
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Legal Metrology Compliance Checker — Dev Startup    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Check Python deps ────────────────────────────────────────
echo "▶ Installing Python dependencies…"
cd "$ROOT/backend"
pip install -r requirements.txt -q

# ── Download spaCy model if missing ──────────────────────────
python -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null || \
  python -m spacy download en_core_web_sm

# ── Check Ollama ──────────────────────────────────────────────
if command -v ollama &>/dev/null; then
  echo "▶ Pulling mistral:7b (if not already cached)…"
  ollama pull mistral:7b
else
  echo "⚠  Ollama not found — LLM fallback will be skipped. Install from https://ollama.com"
fi

# ── Start Backend ─────────────────────────────────────────────
echo ""
echo "▶ Starting FastAPI backend on http://localhost:8000 …"
cd "$ROOT/backend"
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# ── Start Frontend ────────────────────────────────────────────
echo "▶ Starting React frontend on http://localhost:5173 …"
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both services are running:"
echo "   Backend API  → http://localhost:8000/docs"
echo "   Frontend App → http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both services."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT INT TERM
wait
