"""OCR skanów przez GLM-OCR – serwer udawany przez httpx.MockTransport (bez sieci)."""
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import OCRSettings, load_settings, settings
from app.sprawy import ekstrakcja
from main import app
from tests.test_sprawy import pdf_z_tekstem

client = TestClient(app)
SKAN = pdf_z_tekstem("")  # PDF bez warstwy tekstowej -> OCR


def serwer(monkeypatch, odpowiedz, modele=("glm-ocr:latest",)):
    """Udawany serwer OCR; zwraca listę zapytań (ścieżka, body)."""
    zapytania = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        zapytania.append((req.url.path, body))
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in modele]})
        if req.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": m} for m in modele]})
        if isinstance(odpowiedz, Exception):
            raise odpowiedz
        if req.url.path == "/api/generate":
            return httpx.Response(200, json={"response": odpowiedz})
        return httpx.Response(200, json={"choices": [{"message": {"content": odpowiedz}}]})

    def klient(timeout=None):
        return httpx.Client(base_url=settings.ocr.base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(ekstrakcja, "_klient", klient)
    return zapytania


def odczyt():
    return client.post("/dokumenty/odczyt", files={"plik": ("skan.pdf", SKAN)}).json()


def test_ollama_generate(monkeypatch):
    monkeypatch.setattr(settings, "ocr", OCRSettings())
    zapytania = serwer(monkeypatch, "```markdown\nWniosek o udostępnienie informacji\n```")
    r = odczyt()
    assert r["metoda"] == "OCR" and r["tekst"] == "Wniosek o udostępnienie informacji"
    assert r["ocr_pewnosc"] is None  # wszystkie strony odczytane, model nie podaje pewności
    sciezka, body = zapytania[-1]
    assert sciezka == "/api/generate" and body["model"] == "glm-ocr"
    assert body["prompt"] == "Text Recognition:" and body["stream"] is False
    assert base64.b64decode(body["images"][0]).startswith(b"\x89PNG")


def test_openai_vllm(monkeypatch):
    monkeypatch.setattr(settings, "ocr", OCRSettings(api="openai", base_url="http://localhost:8080/v1"))
    zapytania = serwer(monkeypatch, "Treść skanu", modele=("glm-ocr",))
    assert odczyt()["tekst"] == "Treść skanu"
    sciezka, body = zapytania[-1]
    assert sciezka == "/v1/chat/completions"
    obraz, tekst = body["messages"][0]["content"]
    assert obraz["image_url"]["url"].startswith("data:image/png;base64,")
    assert tekst == {"type": "text", "text": "Text Recognition:"}


def test_brak_modelu_i_blad_strony(monkeypatch):
    monkeypatch.setattr(settings, "ocr", OCRSettings())
    serwer(monkeypatch, "x", modele=("qwen2.5:7b",))  # glm-ocr niepobrany
    r = odczyt()
    assert (r["tekst"], r["ocr_pewnosc"]) == ("", 0.0)

    serwer(monkeypatch, httpx.ReadTimeout("za długo"))
    r = odczyt()
    assert r["ocr_pewnosc"] == 0.0 and "nie odczytano" in r["tekst"]


def test_serwer_zewnetrzny_zablokowany(monkeypatch):
    """Skany to oryginały z danymi osobowymi – bez zgody nie wysyłamy ich poza sieć lokalną."""
    monkeypatch.setattr(settings, "ocr", OCRSettings(api="openai", base_url="https://ocr.example.com/v1"))
    zapytania = serwer(monkeypatch, "x")
    assert ekstrakcja.ocr_dostepny() is False and zapytania == []

    monkeypatch.setattr(settings.ocr, "zezwol_zewnetrzny", True)
    assert ekstrakcja.ocr_dostepny() is True


@pytest.mark.parametrize("env, oczekiwany", [
    ({}, "http://localhost:11434"),
    ({"APP_OCR_BASE_URL": "http://ollama:11434"}, "http://ollama:11434"),
])
def test_adres_z_env(tmp_path, env, oczekiwany):
    p = tmp_path / "config.toml"
    p.write_text('[ocr]\nmodel = "glm-ocr:q8_0"\n')
    s = load_settings(p, env=env)
    assert (s.ocr.base_url, s.ocr.model) == (oczekiwany, "glm-ocr:q8_0")
