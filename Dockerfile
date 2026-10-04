# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + serve frontend dist ─────────────────────────────
FROM python:3.11-slim

# System dependencies for OpenCV, Tesseract, and WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Copy backend source
COPY backend/ ./backend/
COPY rules/ ./rules/

# Copy built frontend into backend static directory
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Data directories
RUN mkdir -p data/uploads data/reports

# Expose port
EXPOSE 8000

# Serve frontend dist via FastAPI's StaticFiles + run backend
WORKDIR /app/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
