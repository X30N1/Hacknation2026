"""Konfiguracja z pliku config.toml (w .gitignore). Wzór: config.example.toml.
Brak pliku = wartości domyślne (bez klucza API -> tryb echo)."""
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BACKEND_DIR / "config.toml"


class LLMSettings(BaseModel):
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    timeout: float = Field(120, gt=0)


class DatabaseSettings(BaseModel):
    # względna ścieżka liczona od katalogu backend/
    path: str = "data/app.db"

    def resolved(self) -> Path:
        return _resolve(self.path)


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BACKEND_DIR / p


class PlikiSettings(BaseModel):
    # wgrane dokumenty; ścieżka względna liczona od katalogu backend/
    katalog: str = "data/pliki"
    max_mb: float = Field(20, gt=0)  # TODO: limit – rozmiar wgrywanego pliku

    def resolved(self) -> Path:
        return _resolve(self.katalog)


class OCRSettings(BaseModel):
    # Tesseract + pakiet językowy (Arch: tesseract-data-pol, Debian: tesseract-ocr-pol)
    jezyk: str = "pol"
    dpi: int = Field(300, ge=72, le=600)
    max_stron: int = Field(20, ge=1)            # TODO: limit
    # PDF z mniejszą liczbą znaków w warstwie tekstowej traktujemy jako skan
    min_znakow_warstwy: int = Field(50, ge=0)


class EmbeddingsSettings(BaseModel):
    # API zgodne z OpenAI /embeddings (np. Ollama: http://localhost:11434/v1).
    # Puste base_url = brak wyszukiwania wektorowego, tylko pełnotekstowe (FTS5).
    base_url: str = ""
    api_key: str = ""
    model: str = "nomic-embed-text"
    timeout: float = Field(30, gt=0)


class RAGSettings(BaseModel):
    # tool = model sam wywołuje wyszukiwanie (function calling)
    # auto = wyniki doklejane do każdego zapytania (dla modeli bez function calling)
    # off  = brak RAG
    mode: Literal["tool", "auto", "off"] = "tool"
    top_k: int = Field(5, ge=1, le=50)            # TODO: limit
    chunk_size: int = Field(1200, ge=200)         # TODO: limit (znaki)
    chunk_overlap: int = Field(200, ge=0)         # TODO: limit (znaki)
    max_tool_rounds: int = Field(3, ge=1, le=10)  # TODO: limit
    embeddings: EmbeddingsSettings = EmbeddingsSettings()


class Settings(BaseModel):
    llm: LLMSettings = LLMSettings()
    database: DatabaseSettings = DatabaseSettings()
    pliki: PlikiSettings = PlikiSettings()
    ocr: OCRSettings = OCRSettings()
    rag: RAGSettings = RAGSettings()


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    if not path.exists():
        return Settings()
    with path.open("rb") as f:
        return Settings.model_validate(tomllib.load(f))


settings = load_settings()
