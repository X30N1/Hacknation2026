"""Wypełnienie bazy danymi startowymi.

    uv run python -m app.seed            # import kalendarium xlsx z paczki UMB
    uv run python -m app.seed --xlsx plik.xlsx
    uv run python -m app.seed --archiwum     # + przykładowe pisma i podstawy prawne (archiwum, baza wiedzy)
"""
import argparse
from pathlib import Path

from app.config import BACKEND_DIR, settings
from app.sprawy import import_archiwum, importer
from app.storage import store

PACZKA_UMB = BACKEND_DIR.parent / "Hacknation 2026 - UMB"
DOMYSLNY_XLSX = PACZKA_UMB / "Schemat kalendarium" / "WNIOSKI O UDOSTĘPNIANIE INFORMACJI PUBLICZNEJ.xlsx"
PISMA = PACZKA_UMB / "Przykładowe wnioski i odpowiedzi"
PODSTAWY = PACZKA_UMB / "Dokumenty i podstawy prawne"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xlsx", type=Path, default=DOMYSLNY_XLSX, help="kalendarium do importu")
    p.add_argument("--bez-xlsx", action="store_true", help="pomiń import xlsx")
    p.add_argument("--archiwum", action="store_true",
                   help="zaimportuj przykładowe pisma i podstawy prawne z paczki UMB (z OCR – może potrwać)")
    a = p.parse_args()

    store.connect(settings.database.resolved())
    if not a.bez_xlsx:
        n, s = importer.importuj(a.xlsx)
        print(f"Import xlsx: {n} nowych, {s} już istniało ({a.xlsx.name})")
    if a.archiwum:
        if PISMA.is_dir():
            n, s = import_archiwum.importuj_pisma(PISMA)
            print(f"Archiwum pism: {n} nowych, {s} pominiętych (już są lub bez tekstu)")
        if PODSTAWY.is_dir():
            n, s = import_archiwum.importuj_wiedze(PODSTAWY)
            print(f"Baza wiedzy: {n} nowych, {s} pominiętych")
    store.close()


if __name__ == "__main__":
    main()
