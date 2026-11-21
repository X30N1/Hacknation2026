import pytest

from app.auth.repo import Uzytkownik
from app.auth.sesja import zalogowany
from app.config import AnonimizacjaSettings, AuthSettings, LLMSettings, OCRSettings, PlikiSettings, settings
from app.storage import store
from main import app

TESTOWY = Uzytkownik(id=0, login="test", rola="urzednik", musi_zmienic_haslo=False, totp_aktywny=True,
                     klucze=0, zablokowany_do=None, utworzono="2026-11-21T00:00:00")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path, request):
    """Każdy test: tryb echo LLM, świeża baza SQLite.
    Niezależne od lokalnego config.toml."""
    monkeypatch.setattr(settings, "llm", LLMSettings())
    monkeypatch.setattr(settings, "anonimizacja", AnonimizacjaSettings())
    monkeypatch.setattr(settings, "auth", AuthSettings())
    # OCR nigdy nie trafia w prawdziwy serwer (adres spoza sieci lokalnej = OCR wyłączony)
    monkeypatch.setattr(settings, "ocr", OCRSettings(base_url="http://ocr.invalid"))
    monkeypatch.setattr(settings, "pliki", PlikiSettings(katalog=str(tmp_path / "pliki")))
    store.connect(tmp_path / "test.db")
    # Testy funkcji aplikacji działają jako zalogowany urzędnik; test_auth sprawdza prawdziwe logowanie.
    if not request.module.__name__.endswith("test_auth"):
        app.dependency_overrides[zalogowany] = lambda: TESTOWY
    yield
    app.dependency_overrides.pop(zalogowany, None)
    store.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"
