# Asystent urzędnika UDIP – jeden obraz: frontend (zbudowany) + backend FastAPI + OCR (Tesseract, pol).
#   docker compose up --build        -> http://localhost:8000
# Działa bez internetu. Model językowy opcjonalny – lokalna Ollama, zob. docker-compose.yml.

FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-pol \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY ["Hacknation 2026 - UMB", "/app/Hacknation 2026 - UMB"]
COPY --from=frontend /src/frontend/dist /app/frontend/dist

EXPOSE 8000
# Dane startowe są idempotentne: kalendarium xlsx (10 spraw), archiwum pism i podstaw prawnych UMB.
# Seed działa w tle – serwer odpowiada od razu, a import archiwum (z OCR skanów) trwa obok.
# Do środowiska produkcyjnego należy usunąć "uv run --no-sync python -m app.seed --archiwum &"!
CMD ["sh", "-c", "uv run --no-sync python -m app.seed --archiwum & exec uv run --no-sync uvicorn serve:app --host 0.0.0.0 --port 8000"]
