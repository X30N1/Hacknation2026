"""OCR skanów – Tesseract z językiem polskim (testy pomijane, gdy nie jest zainstalowany)."""
import io
import pathlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.config import load_settings, settings
from app.sprawy import ekstrakcja
from main import app

client = TestClient(app)
# czcionka z polskimi znakami (domyślna czcionka PIL nie ma np. „ę”)
CZCIONKI = ["/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            r"C:\Windows\Fonts\arial.ttf"]
CZCIONKA = next((c for c in CZCIONKI if pathlib.Path(c).is_file()), None)


def skan(tekst: str) -> bytes:
    """PDF z samym obrazem strony (bez warstwy tekstowej) – jak ze skanera."""
    obraz = Image.new("L", (1240, 400), 255)
    ImageDraw.Draw(obraz).text((60, 150), tekst, fill=0, font=ImageFont.truetype(CZCIONKA, 56) if CZCIONKA else ImageFont.load_default(size=56))
    buf = io.BytesIO()
    obraz.save(buf, format="PDF", resolution=150)
    return buf.getvalue()


def odczyt(dane: bytes):
    return client.post("/dokumenty/odczyt", files={"plik": ("skan.pdf", dane)}).json()


@pytest.fixture(autouse=True)
def bez_pamieci():
    ekstrakcja.ocr_dostepny.cache_clear()
    yield
    ekstrakcja.ocr_dostepny.cache_clear()


@pytest.mark.skipif(not ekstrakcja.ocr_dostepny(), reason="brak tesseract z językiem polskim")
def test_tesseract_polski():
    r = odczyt(skan("Wniosek o udostępnienie informacji"))
    assert r["metoda"] == "OCR" and "Wniosek" in r["tekst"] and "informacji" in r["tekst"]
    if CZCIONKA:
        assert "udostępnienie" in r["tekst"]  # polskie znaki – język pol
    assert 0.6 <= r["ocr_pewnosc"] <= 1


def test_brak_jezyka(monkeypatch):
    monkeypatch.setattr(settings.ocr, "jezyk", "xyz")  # pakiet językowy niezainstalowany
    r = odczyt(skan("Wniosek"))
    assert (r["metoda"], r["tekst"], r["ocr_pewnosc"]) == ("OCR", "", 0.0)  # do wpisania ręcznie


def test_jezyk_z_env(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[ocr]\njezyk = "pol"\ndpi = 200\n')
    s = load_settings(p, env={"APP_OCR_JEZYK": "pol+eng"})
    assert (s.ocr.jezyk, s.ocr.dpi) == ("pol+eng", 200)
