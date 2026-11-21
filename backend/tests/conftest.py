import pytest

from app.config import LLMSettings, PlikiSettings, RAGSettings, settings
from app.storage import store


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Każdy test: tryb echo LLM, RAG bez embeddingów, świeża baza SQLite.
    Niezależne od lokalnego config.toml."""
    monkeypatch.setattr(settings, "llm", LLMSettings())
    monkeypatch.setattr(settings, "rag", RAGSettings())
    monkeypatch.setattr(settings, "pliki", PlikiSettings(katalog=str(tmp_path / "pliki")))
    store.connect(tmp_path / "test.db")
    yield
    store.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"
