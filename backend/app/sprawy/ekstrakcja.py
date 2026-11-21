"""Odczyt tekstu z wgranych plików: DOCX, PDF (warstwa tekstowa), skany PDF (OCR – GLM-OCR), TXT."""
import base64
import io
import logging
from dataclasses import dataclass

import httpx

from app import llm_client
from app.config import settings
from app.sprawy.model import Metoda

log = logging.getLogger(__name__)

ROZSZERZENIA = {"pdf", "docx", "txt"}


class NieobslugiwanyFormat(ValueError):
    pass


@dataclass
class Odczyt:
    tekst: str
    metoda: Metoda
    ocr_pewnosc: float | None = None


def rozszerzenie(nazwa: str) -> str:
    return nazwa.rsplit(".", 1)[-1].lower() if "." in nazwa else ""


def odczytaj(nazwa: str, dane: bytes) -> Odczyt:
    ext = rozszerzenie(nazwa)
    if ext not in ROZSZERZENIA:
        raise NieobslugiwanyFormat("Nieobsługiwany format. Wgraj plik PDF lub Word (DOCX).")
    if ext == "txt":
        return Odczyt(_txt(dane), Metoda.RECZNA)
    if ext == "docx":
        return Odczyt(_docx(dane), Metoda.DOCX)
    return _pdf(dane)


def _txt(dane: bytes) -> str:
    for enc in ("utf-8-sig", "cp1250"):
        try:
            return dane.decode(enc)
        except UnicodeDecodeError:
            continue
    return dane.decode("utf-8", errors="replace")


def _docx(dane: bytes) -> str:
    import docx

    try:
        d = docx.Document(io.BytesIO(dane))
    except Exception as exc:  # noqa: BLE001
        raise NieobslugiwanyFormat("Nie udało się odczytać pliku Word (DOCX).") from exc
    czesci = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            czesci.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(czesci).strip()


def _pdf(dane: bytes) -> Odczyt:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(dane))
        tekst = "\n\n".join((p.extract_text() or "").strip() for p in reader.pages).strip()
    except Exception as exc:  # noqa: BLE001
        raise NieobslugiwanyFormat("Nie udało się odczytać pliku PDF.") from exc
    if len("".join(tekst.split())) >= settings.ocr.min_znakow_warstwy:
        return Odczyt(tekst, Metoda.PDF_TEXT)
    return _ocr_pdf(dane)


def ocr_dostepny() -> bool:
    """Serwer GLM-OCR odpowiada i ma model z [ocr] (Ollama: `ollama pull glm-ocr`)."""
    cfg = settings.ocr
    if not cfg.zezwol_zewnetrzny and not llm_client.is_local(cfg.base_url):
        log.warning("OCR wyłączony: %s nie jest serwerem lokalnym, a skany zawierają niezamazane "
                    "dane osobowe (ustaw [ocr] zezwol_zewnetrzny = true, jeśli to zamierzone)", cfg.base_url)
        return False
    try:
        with _klient(timeout=5) as k:
            if cfg.api == "ollama":
                resp = k.get("/api/tags")
                resp.raise_for_status()
                modele = {m.get("name") for m in resp.json().get("models") or []}
            else:
                resp = k.get("/models")
                resp.raise_for_status()
                modele = {m.get("id") for m in resp.json().get("data") or []}
    except Exception as exc:  # noqa: BLE001
        log.warning("Serwer OCR niedostępny (%s): %s", cfg.base_url, exc)
        return False
    # Ollama zwraca nazwy z tagiem („glm-ocr:latest”)
    return not modele or cfg.model in modele or f"{cfg.model}:latest" in modele


def _klient(timeout: float | None = None) -> httpx.Client:
    cfg = settings.ocr
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    return httpx.Client(base_url=cfg.base_url, headers=headers, timeout=timeout or cfg.timeout)


def _bez_ogrodzenia(tekst: str) -> str:
    """Model bywa, że opakowuje wynik w blok ```markdown … ``` – zostawiamy sam tekst."""
    t = tekst.strip()
    if t.startswith("```") and t.endswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()


def rozpoznaj_strone(png: bytes) -> str:
    """Jedna strona (PNG) -> tekst przez GLM-OCR."""
    cfg = settings.ocr
    obraz = base64.b64encode(png).decode()
    with _klient() as k:
        if cfg.api == "ollama":
            resp = k.post("/api/generate", json={
                "model": cfg.model, "prompt": cfg.prompt, "images": [obraz], "stream": False,
                "options": {"temperature": 0, "num_predict": cfg.max_tokens, "num_ctx": cfg.num_ctx,
                            **({"num_thread": cfg.num_thread} if cfg.num_thread else {})},
            })
            resp.raise_for_status()
            tekst = resp.json().get("response") or ""
        else:
            resp = k.post("/chat/completions", json={
                "model": cfg.model,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + obraz}},
                    {"type": "text", "text": cfg.prompt},
                ]}],
                "temperature": 0,
                "max_tokens": cfg.max_tokens,
            })
            resp.raise_for_status()
            tekst = resp.json()["choices"][0]["message"].get("content") or ""
    return _bez_ogrodzenia(tekst)


def _ocr_pdf(dane: bytes) -> Odczyt:
    if not ocr_dostepny():
        # pewność 0 -> frontend pokazuje baner i urzędnik wpisuje tekst ręcznie
        return Odczyt("", Metoda.OCR, 0.0)

    import pypdfium2

    pdf = pypdfium2.PdfDocument(dane)
    teksty, odczytane = [], 0
    try:
        strony = min(len(pdf), settings.ocr.max_stron)
        for i in range(strony):
            buf = io.BytesIO()
            strona = pdf[i]
            bok = max(strona.get_size())  # w punktach (1/72 cala)
            skala = min(settings.ocr.dpi / 72, settings.ocr.max_bok_px / bok)
            strona.render(scale=skala).to_pil().save(buf, format="PNG")
            try:
                teksty.append(rozpoznaj_strone(buf.getvalue()))
                odczytane += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("OCR strony %d nieudany: %s", i + 1, exc)
                teksty.append(f"[strona {i + 1} – nie odczytano, uzupełnij ręcznie]")
    finally:
        pdf.close()
    # GLM-OCR nie podaje pewności rozpoznania. None = wszystkie strony odczytane;
    # część nieudana -> odsetek odczytanych stron (frontend pokaże ostrzeżenie poniżej 60%).
    if not strony:
        pewnosc = 0.0
    else:
        pewnosc = None if odczytane == strony else round(odczytane / strony, 2)
    return Odczyt("\n\n".join(t for t in teksty if t).strip(), Metoda.OCR, pewnosc)
