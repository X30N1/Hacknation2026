"""Import archiwalnego kalendarium (xlsx) z automatycznym wykrywaniem problemów w danych.

Kolumny: Lp. | Numer sprawy | Wnioskodawca | Przedmiot | Data wpływu | Termin odpowiedzi |
Data odpowiedzi | Osoba odpowiedzialna | Pozostało dni.
Sprawy z importu są zamknięte; wartości pokazywane „jak są”, a uwagi trafiają do `flagi`.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from app.sprawy import repo, terminy
from app.sprawy.model import ZNAK_RE, Flaga, TypZdarzenia, Zrodlo

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
DATA_PL_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
FORMULA_RE = re.compile(r"^=([A-Z]+)(\d+)\s*\+\s*(\d+)$")
PODOBIENSTWO_NAZW = 0.85


def _pl(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _norm(s) -> str:
    return " ".join(str(s or "").replace("\xa0", " ").split())


def _data(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


@dataclass
class Wiersz:
    znak: str
    wnioskodawca: str
    przedmiot: str
    data_wplywu: date
    termin: date | None
    data_odpowiedzi: date | None
    inicjaly: str | None
    termin_tekst: str | None = None
    flagi: list[Flaga] = field(default_factory=list)

    @property
    def nr(self) -> int:
        return int(ZNAK_RE.match(self.znak).group(1))

    @property
    def rok(self) -> int:
        return int(ZNAK_RE.match(self.znak).group(2))


def wczytaj_xlsx(path: Path) -> list[Wiersz]:
    import openpyxl

    ws = openpyxl.load_workbook(path).active
    wiersze = []
    for nr_wiersza, row in enumerate(ws.iter_rows(values_only=True), start=1):
        znak = _norm(row[1] if len(row) > 1 else "")
        if not ZNAK_RE.match(znak):
            continue  # nagłówki, puste wiersze
        wplyw = _data(row[4])
        termin_raw = row[5]
        termin, termin_tekst = _data(termin_raw), None
        if isinstance(termin_raw, str):
            m = FORMULA_RE.match(termin_raw.strip())
            if m and m.group(1) == "E" and int(m.group(2)) == nr_wiersza and wplyw:
                termin = wplyw + timedelta(days=int(m.group(3)))  # =E<ten wiersz>+14
            else:
                termin_tekst = _norm(termin_raw)
        wiersze.append(Wiersz(
            znak=znak, wnioskodawca=_norm(row[2]), przedmiot=_norm(row[3]),
            data_wplywu=wplyw, termin=termin, data_odpowiedzi=_data(row[6]),
            inicjaly=_norm(row[7]) or None, termin_tekst=termin_tekst,
        ))
    return wiersze


def wykryj_problemy(wiersze: list[Wiersz]) -> None:
    """Dopisuje flagi do wierszy. Reguły wynikające z samego xlsx (bez treści pism)."""
    for w in wiersze:
        ustawowy = w.data_wplywu + timedelta(days=terminy.TERMIN_DNI)
        termin_do_porownan = w.termin  # przy oczywistej literówce w roku – termin ustawowy

        if w.termin_tekst:
            daty = DATA_PL_RE.findall(w.termin_tekst)
            opis = f"Termin w xlsx zapisany tekstem: „{w.termin_tekst}”."
            if daty and "doprecyz" in w.termin_tekst.lower():
                d, m, r = map(int, daty[-1])
                w.termin = date(r, m, d)
                opis += (f" Zapisano jako wezwanie do doprecyzowania z nowym terminem "
                         f"{_pl(w.termin)} (data wezwania nieznana).")
            w.flagi.append(Flaga(kod="TERMIN_TEKSTOWY", opis=opis))
        elif w.termin and w.termin.year < w.rok:
            w.flagi.append(Flaga(
                kod="ROK_TERMINU",
                opis=f"Termin {_pl(w.termin)} ma rok wcześniejszy niż rok sprawy; "
                     f"wpływ {_pl(w.data_wplywu)} + 14 dni = {_pl(ustawowy)}.",
                propozycja=f"Termin: {_pl(ustawowy)}.",
            ))
            termin_do_porownan = ustawowy
        elif w.termin and w.termin != ustawowy:
            w.flagi.append(Flaga(
                kod="TERMIN_NIEZGODNY",
                opis=f"Termin {_pl(w.termin)} różni się od ustawowego {_pl(ustawowy)} "
                     "(14 dni od wpływu), a w xlsx nie ma przedłużenia.",
            ))

        if w.data_odpowiedzi and w.data_odpowiedzi < w.data_wplywu:
            w.flagi.append(Flaga(
                kod="ODP_PRZED_WPLYWEM",
                opis=f"Data odpowiedzi ({_pl(w.data_odpowiedzi)}) jest wcześniejsza niż "
                     f"data wpływu ({_pl(w.data_wplywu)}).",
            ))
        elif w.data_odpowiedzi and termin_do_porownan and w.data_odpowiedzi > termin_do_porownan:
            w.flagi.append(Flaga(
                kod="ODP_PO_TERMINIE",
                opis=f"Odpowiedź {_pl(w.data_odpowiedzi)} po terminie {_pl(termin_do_porownan)}, "
                     "brak przedłużenia w xlsx.",
                propozycja="Sprawdzić, czy było pismo o przedłużeniu (kwerenda).",
            ))

        if w.termin and terminy.is_weekend(w.termin):
            w.flagi.append(Flaga(kod="TERMIN_W_WEEKEND",
                                 opis=f"Termin {_pl(w.termin)} przypada w weekend."))
        if EMAIL_RE.fullmatch(w.wnioskodawca):
            w.flagi.append(Flaga(kod="WNIOSKODAWCA_EMAIL",
                                 opis="Wnioskodawca zapisany jako adres e-mail (dana osobowa)."))

    # numeracja w roku powinna rosnąć razem z datą wpływu
    for w in wiersze:
        pozniejsze = [x for x in wiersze
                      if x.rok == w.rok and x.nr > w.nr and x.data_wplywu < w.data_wplywu]
        if pozniejsze:
            x = min(pozniejsze, key=lambda x: x.nr)
            w.flagi.append(Flaga(
                kod="NUMERACJA_NIEZGODNA",
                opis=f"Sprawa nr {x.nr}.{x.rok} wpłynęła {_pl(x.data_wplywu)}, więc nr {w.nr} "
                     f"nie mógł wpłynąć {_pl(w.data_wplywu)}.",
                propozycja=f"Sprawdzić datę wpływu (prawdopodobnie przed {_pl(x.data_wplywu)}).",
            ))

    # ten sam wnioskodawca zapisany inaczej
    for w in wiersze:
        podobne = []
        for x in wiersze:
            if x is w or not w.wnioskodawca or not x.wnioskodawca or w.wnioskodawca == x.wnioskodawca:
                continue
            a, b = w.wnioskodawca.lower(), x.wnioskodawca.lower()
            if a in b or b in a or SequenceMatcher(None, a, b).ratio() >= PODOBIENSTWO_NAZW:
                podobne.append(f"{x.znak.removeprefix('BKS.IV.1431.')} („{x.wnioskodawca}”)")
        if podobne:
            w.flagi.append(Flaga(
                kod="WNIOSKODAWCA_WARIANTY",
                opis=f"Ten sam wnioskodawca może być zapisany inaczej w sprawach: {', '.join(podobne)}.",
                propozycja="Sprawdzić, czy to ta sama osoba / organizacja, i ujednolicić nazwę.",
            ))


def importuj(path: Path) -> tuple[int, int]:
    """Zwraca (zaimportowane, pominięte – już istniejące)."""
    wiersze = wczytaj_xlsx(path)
    wykryj_problemy(wiersze)
    nowe = pominiete = 0
    for w in wiersze:
        if repo.znak_istnieje(w.znak):
            pominiete += 1
            continue
        sid = repo.utworz_sprawe(
            w.znak, w.data_wplywu, w.wnioskodawca, w.przedmiot, w.inicjaly,
            zrodlo=Zrodlo.IMPORT, flagi=w.flagi,
            import_termin=w.termin, import_odpowiedz=w.data_odpowiedzi,
        )
        if w.termin_tekst and "doprecyz" in w.termin_tekst.lower():
            repo.dodaj_zdarzenie(sid, TypZdarzenia.WEZWANIE_DOPRECYZOWANIE, w.data_wplywu,
                                 nowy_termin=w.termin, payload={"zrodlo": "xlsx"})
        if w.data_odpowiedzi:
            repo.dodaj_zdarzenie(sid, TypZdarzenia.WYSLANO, w.data_odpowiedzi)
        nowe += 1
    return nowe, pominiete
