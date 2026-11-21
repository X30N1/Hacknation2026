"""Wypełnienie bazy danymi startowymi.

    uv run python -m app.seed            # import kalendarium xlsx z paczki UMB
    uv run python -m app.seed --demo     # + 10 spraw demo z datami względem dziś
    uv run python -m app.seed --xlsx plik.xlsx
"""
import argparse
from datetime import date
from pathlib import Path

from app.config import BACKEND_DIR, settings
from app.sprawy import demo, importer
from app.storage import store

DOMYSLNY_XLSX = (BACKEND_DIR.parent / "Hacknation 2026 - UMB" / "Schemat kalendarium"
                 / "WNIOSKI O UDOSTĘPNIANIE INFORMACJI PUBLICZNEJ.xlsx")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xlsx", type=Path, default=DOMYSLNY_XLSX, help="kalendarium do importu")
    p.add_argument("--bez-xlsx", action="store_true", help="pomiń import xlsx")
    p.add_argument("--demo", action="store_true", help="dodaj sprawy demonstracyjne")
    a = p.parse_args()

    store.connect(settings.database.resolved())
    if not a.bez_xlsx:
        n, s = importer.importuj(a.xlsx)
        print(f"Import xlsx: {n} nowych, {s} już istniało ({a.xlsx.name})")
    if a.demo:
        n, s = demo.zaladuj(date.today())
        print(f"Demo: {n} nowych, {s} już istniało")
    store.close()


if __name__ == "__main__":
    main()
