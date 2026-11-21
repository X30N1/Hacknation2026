"""Odczyt tekstu z wgranych plików: DOCX, PDF (warstwa tekstowa), skany PDF (OCR), TXT."""
import io
import logging
import shutil
from dataclasses import dataclass
from functools import lru_cache

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


@lru_cache
def ocr_dostepny() -> bool:
    """Tesseract + pakiet językowy z config.toml (np. Arch: tesseract-data-pol)."""
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract

        return settings.ocr.jezyk in pytesseract.get_languages(config="")
    except Exception:  # noqa: BLE001
        return False


def _ocr_pdf(dane: bytes) -> Odczyt:
    if not ocr_dostepny():
        log.warning("OCR niedostępny (brak tesseract lub języka %r)", settings.ocr.jezyk)
        # pewność 0 -> frontend pokazuje baner i urzędnik wpisuje tekst ręcznie
        return Odczyt("", Metoda.OCR, 0.0)

    import pypdfium2
    import pytesseract

    pdf = pypdfium2.PdfDocument(dane)
    teksty, pewnosci = [], []
    try:
        for i in range(min(len(pdf), settings.ocr.max_stron)):
            obraz = pdf[i].render(scale=settings.ocr.dpi / 72).to_pil()
            dane_ocr = pytesseract.image_to_data(
                obraz, lang=settings.ocr.jezyk, output_type=pytesseract.Output.DICT
            )
            linie: dict[tuple, list[str]] = {}
            for j, slowo in enumerate(dane_ocr["text"]):
                conf = float(dane_ocr["conf"][j])
                if conf < 0 or not slowo.strip():
                    continue
                pewnosci.append(conf)
                klucz = (dane_ocr["block_num"][j], dane_ocr["par_num"][j], dane_ocr["line_num"][j])
                linie.setdefault(klucz, []).append(slowo)
            teksty.append("\n".join(" ".join(w) for w in linie.values()))
    finally:
        pdf.close()
    pewnosc = round(sum(pewnosci) / len(pewnosci) / 100, 2) if pewnosci else 0.0
    return Odczyt("\n\n".join(teksty).strip(), Metoda.OCR, pewnosc)
