# ScholarAgent — Dockerfile
# Multi-stage build: frontend build + backend runtime

# ---- Stage 1: Build frontend ----
FROM node:20-alpine AS frontend-builder

WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# ---- Stage 2: Backend runtime ----
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY agent/ ./agent/
COPY api/ ./api/
COPY tests/ ./tests/
COPY memory/ ./memory/
COPY Makefile .
COPY .env.example .

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/web/dist/ ./web/dist/

# Create non-root user
RUN useradd -m -u 1000 scholar && \
    chown -R scholar:scholar /app
USER scholar

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the API server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]