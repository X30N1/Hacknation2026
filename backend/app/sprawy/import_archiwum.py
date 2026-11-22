"""Import archiwalnych pism i podstaw prawnych z paczki UMB (python -m app.seed --archiwum).

Pisma („Wniosek - BKS.IV.1431.15.2026.docx”, „Odpowiedź - …pdf”) trafiają do spraw z kalendarium
o tym samym numerze; bez pasującej sprawy – do bazy wiedzy jako ARCHIWUM. Przed zapisem tekst pism
jest automatycznie anonimizowany wzorcami i danymi wnioskodawcy (materiały testowe, bez udziału
urzędnika). Zapisywany jest wyłącznie tekst po anonimizacji (.txt) – oryginały nie trafiają do bazy.
Podstawy prawne (ustawy, zarządzenia) trafiają do bazy wiedzy w całości, bez anonimizacji – tak jak
pliki dodawane do bazy wiedzy w aplikacji. Import jest idempotentny.
"""
from pathlib import Path

from app import anonimizacja
from app.sprawy import ekstrakcja, repo
from app.sprawy.model import ZNAK_W_TEKSCIE_RE
from app.storage import store

RODZAJ_PISMA = {
    "wniosek": "WNIOSEK",
    "odpowiedź": "ODPOWIEDZ",
    "odpowiedz": "ODPOWIEDZ",
    "kwerenda": "KWERENDA",
    "doprecyzowanie": "WEZWANIE",
}
# podstawy prawne: fragment nazwy pliku -> rodzaj w bazie wiedzy
RODZAJ_WIEDZY = {
    "zarządzenie": "ZARZADZENIE",
    "ustawy": "USTAWA",
    "anonimizacji": "ZARZADZENIE",
    "instrukcja": "ZARZADZENIE",
}


def _sprawa_po_znaku(znak: str) -> int | None:
    r = store.conn.execute("SELECT id FROM sprawy WHERE znak = ?", (znak,)).fetchone()
    return r["id"] if r else None


def _istnieje(nazwa: str, sid: int | None) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM dokumenty WHERE nazwa_pliku = ? AND sprawa_id IS ?", (nazwa, sid)
    ).fetchone() is not None


def _zapisz(plik: Path, rodzaj: str, sid: int | None, anonimizuj: bool = True) -> bool:
    nazwa = plik.stem + ".txt"
    if _istnieje(nazwa, sid):
        return False
    try:
        odczyt = ekstrakcja.odczytaj(plik.name, plik.read_bytes())
    except ekstrakcja.NieobslugiwanyFormat:
        return False
    # pusty tekst (np. pismo odręczne) albo OCR niedostępny (brak tesseract / języka): nie zapisujemy –
    # następny seed spróbuje ponownie (zapisany dokument blokowałby powtórkę)
    if not odczyt.tekst.strip() or odczyt.ocr_pewnosc == 0:
        return False
    tekst = odczyt.tekst
    if anonimizuj:
        tekst = anonimizacja.zamaz_automatycznie(tekst, repo.wnioskodawca(sid) if sid else None)
    repo.zapisz_dokument(nazwa, tekst.encode("utf-8"), rodzaj, odczyt.metoda, tekst,
                         odczyt.ocr_pewnosc, sprawa_id=sid)
    return True


def importuj_pisma(katalog: Path) -> tuple[int, int]:
    nowe = pominiete = 0
    for plik in sorted(katalog.iterdir()):
        if ekstrakcja.rozszerzenie(plik.name) not in ekstrakcja.ROZSZERZENIA:
            continue
        typ = plik.name.split(" - ")[0].strip().lower()
        znak = ZNAK_W_TEKSCIE_RE.search(plik.name)
        sid = _sprawa_po_znaku(znak.group(0)) if znak else None
        rodzaj = RODZAJ_PISMA.get(typ, "INNE") if sid else "ARCHIWUM"
        if _zapisz(plik, rodzaj, sid):
            nowe += 1
        else:
            pominiete += 1
    return nowe, pominiete


def importuj_wiedze(katalog: Path) -> tuple[int, int]:
    nowe = pominiete = 0
    for plik in sorted(katalog.iterdir()):
        rodzaj = next((r for k, r in RODZAJ_WIEDZY.items() if k in plik.name.lower()), None)
        if rodzaj is None or ekstrakcja.rozszerzenie(plik.name) not in ekstrakcja.ROZSZERZENIA:
            continue
        if _zapisz(plik, rodzaj, None, anonimizuj=False):
            nowe += 1
        else:
            pominiete += 1
    return nowe, pominiete
