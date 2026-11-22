"""Konfiguracja z pliku config.toml (w .gitignore). Wzór: config.example.toml.
Brak pliku = wartości domyślne (bez klucza API -> tryb echo)."""
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

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
    # GLM-OCR (https://huggingface.co/zai-org/GLM-OCR):
    #   api = "ollama" – natywne /api/generate Ollamy (zalecane przez autorów modelu; endpoint zgodny
    #                    z OpenAI w Ollamie ma ograniczenia przy obrazach), base_url bez /v1,
    #   api = "openai" – vLLM / SGLang (--served-model-name glm-ocr), base_url z /v1.
    api: Literal["ollama", "openai"] = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    model: str = "glm-ocr"
    prompt: str = "Text Recognition:"
    timeout: float = Field(600, gt=0)              # sekundy na jedną stronę (CPU: kilka minut)
    max_tokens: int = Field(4096, ge=256)          # limit tekstu z jednej strony
    # Kontekst modelu (tylko api = "ollama"): obraz strony A4 przy 200 dpi to ~4000 tokenów + tekst
    # odpowiedzi. Domyślne 4096 Ollamy ucina wynik.
    num_ctx: int = Field(16384, ge=2048)
    # Skany to ORYGINAŁY – z niezamazanymi danymi osobowymi. Domyślnie tylko serwer lokalny.
    zezwol_zewnetrzny: bool = False
    dpi: int = Field(150, ge=72, le=600)
    # Dłuższy bok obrazu strony w pikselach – czas OCR rośnie szybko z rozmiarem obrazu
    # (CPU, strona 1695×2434 px: ~4 min). Duże skany są zmniejszane do tej wartości.
    max_bok_px: int = Field(1600, ge=600, le=6000)
    # Wątki CPU dla Ollamy (tylko api = "ollama"); puste = wybór Ollamy (zwykle rdzenie wydajne).
    num_thread: int | None = Field(None, ge=1)
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
    """APP_<SEKCJA>_<KLUCZ> nadpisuje wartość z pliku, np. APP_OCR_BASE_URL=http://ollama:11434/v1
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
