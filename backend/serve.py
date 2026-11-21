"""Produkcja / Docker: API pod /api + zbudowany frontend (frontend/dist) z jednego serwera.

    uvicorn serve:app --host 0.0.0.0 --port 8000

W trybie deweloperskim frontend działa na Vite (proxy /api -> :8000, prefiks obcinany),
a backend startuje jako `uvicorn main:app` bez prefiksu.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.config import BACKEND_DIR
from main import app as api
from main import lifespan

DIST = Path(os.environ.get("FRONTEND_DIST", BACKEND_DIR.parent / "frontend" / "dist")).resolve()

# lifespan podmontowanej aplikacji nie jest uruchamiany przez Starlette – łączymy bazę tutaj
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", api)


@app.get("/{sciezka:path}", include_in_schema=False)
async def frontend(sciezka: str):
    """Pliki zbudowanego frontendu; pozostałe ścieżki (np. /sprawy/5) -> index.html (routing SPA)."""
    plik = (DIST / sciezka).resolve()
    if sciezka and plik.is_file() and plik.is_relative_to(DIST):
        return FileResponse(plik)
    return FileResponse(DIST / "index.html")
