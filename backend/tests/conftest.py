import pytest

from app.config import AnonimizacjaSettings, LLMSettings, OCRSettings, PlikiSettings, settings
from app.storage import store


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Każdy test: tryb echo LLM, świeża baza SQLite.
    Niezależne od lokalnego config.toml."""
    monkeypatch.setattr(settings, "llm", LLMSettings())
    monkeypatch.setattr(settings, "anonimizacja", AnonimizacjaSettings())
    # OCR nigdy nie trafia w prawdziwy serwer (adres spoza sieci lokalnej = OCR wyłączony)
    monkeypatch.setattr(settings, "ocr", OCRSettings(base_url="http://ocr.invalid"))
    monkeypatch.setattr(settings, "pliki", PlikiSettings(katalog=str(tmp_path / "pliki")))
    store.connect(tmp_path / "test.db")
    yield
    store.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"
