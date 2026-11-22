"""Konfiguracja z pliku config.toml (w .gitignore). Wzór: config.example.toml.
Brak pliku = wartości domyślne (bez klucza API -> tryb echo)."""
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BACKEND_DIR / "config.toml"


class LLMLimity(BaseModel):
    # Ile tekstu (w znakach) trafia do modelu w poszczególnych zadaniach.
    przedmiot_max: int = Field(160, ge=20)            # propozycja „przedmiotu” w formularzu wniosku
    wniosek_analiza: int = Field(6000, ge=500)        # wniosek → wnioskodawca i przedmiot
    wniosek_wydzialy: int = Field(4000, ge=500)       # wniosek → sugerowane wydziały
    anonimizacja_fragment: int = Field(6000, ge=500)  # tekst w jednym zapytaniu anonimizacji
    anonimizacja_fragmenty: int = Field(10, ge=1)     # maks. zapytań na dokument (dalej tylko wzorce)
    projekt_material: int = Field(6000, ge=500)       # jeden materiał w projekcie odpowiedzi
    projekt_wzor: int = Field(2500, ge=0)             # odpowiedź archiwalna jako wzór stylu
    uzasadnienie_max: int = Field(300, ge=20)         # uzasadnienie sugerowanego wydziału


class LLMTemperatury(BaseModel):
    # 0 = odpowiedzi powtarzalne (ekstrakcja, JSON); wyżej = swobodniejszy styl tekstu.
    analiza: float = Field(0, ge=0, le=2)        # wnioskodawca i przedmiot z wniosku
    wydzialy: float = Field(0, ge=0, le=2)       # sugerowane wydziały
    anonimizacja: float = Field(0, ge=0, le=2)   # dane do zamazania
    projekt: float = Field(0.2, ge=0, le=2)      # projekt odpowiedzi


class LLMSettings(BaseModel):
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    timeout: float = Field(120, gt=0)
    limity: LLMLimity = LLMLimity()
    temperatury: LLMTemperatury = LLMTemperatury()


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
    # Tesseract + pakiet językowy (Arch: tesseract-data-pol, Debian/Ubuntu: tesseract-ocr-pol).
    # Działa lokalnie, bez modelu – skany (oryginały z danymi osobowymi) nie opuszczają serwera.
    jezyk: str = "pol"
    dpi: int = Field(300, ge=72, le=600)
    max_stron: int = Field(20, ge=1)            # TODO: limit
    # PDF z mniejszą liczbą znaków w warstwie tekstowej traktujemy jako skan
    min_znakow_warstwy: int = Field(50, ge=0)


class AnonimizacjaSettings(BaseModel):
    # LLM uzupełnia wzorce o imiona i nazwiska bez kontekstu oraz dane wrażliwe.
    # Tekst dokumentu trafia do modelu z [llm] – na produkcji model lokalny.
    llm: bool = True


class AuthSettings(BaseModel):
    # Wymóg drugiego składnika i minimalna długość hasła: ustawienia administratora w aplikacji
    # (app/auth/polityka.py), nie w tym pliku.
    sesja_godziny: float = Field(10, gt=0)          # sesja po pełnym zalogowaniu
    sesja_wstepna_minuty: float = Field(15, gt=0)   # na zmianę hasła / drugi składnik po haśle
    max_prob: int = Field(5, ge=1)                  # nieudane logowania przed blokadą konta
    blokada_minut: float = Field(15, gt=0)
    # Ciasteczko tylko przez HTTPS – włącz za reverse proxy z TLS.
    cookie_secure: bool = False
    # WebAuthn: rp_id = domena, pod którą użytkownicy otwierają aplikację (bez portu i schematu);
    # origins = pełne adresy (schemat + host + port). Klucze działają tylko na HTTPS lub localhost.
    rp_id: str = "localhost"
    rp_nazwa: str = "Asystent urzędnika – UM Bydgoszcz"
    origins: list[str] = ["http://localhost:8000", "http://localhost:5173"]


class Settings(BaseModel):
    llm: LLMSettings = LLMSettings()
    database: DatabaseSettings = DatabaseSettings()
    pliki: PlikiSettings = PlikiSettings()
    ocr: OCRSettings = OCRSettings()
    anonimizacja: AnonimizacjaSettings = AnonimizacjaSettings()
    auth: AuthSettings = AuthSettings()


ENV_PREFIX = "APP_"


def _z_env(dane: dict, env: Mapping[str, str]) -> dict:
    """APP_<SEKCJA>_<KLUCZ> nadpisuje wartość z pliku, np. APP_LLM_BASE_URL=http://ollama:11434/v1
    (docker-compose.yml) – ten sam config.toml działa w Dockerze i przy pracy lokalnej."""
    for sekcja, model in Settings.model_fields.items():
        for klucz in model.annotation.model_fields:
            wartosc = env.get(f"{ENV_PREFIX}{sekcja}_{klucz}".upper())
            if wartosc is not None:
                dane.setdefault(sekcja, {})[klucz] = wartosc
    return dane


def load_settings(path: Path = CONFIG_PATH, env: Mapping[str, str] | None = None) -> Settings:
    dane = {}
    if path.is_file():  # brak pliku (albo katalog utworzony przez montowanie w Dockerze) = domyślne
        with path.open("rb") as f:
            dane = tomllib.load(f)
    return Settings.model_validate(_z_env(dane, os.environ if env is None else env))


settings = load_settings()
