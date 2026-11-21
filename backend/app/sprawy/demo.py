"""Sprawy demonstracyjne z datami względem dziś (jak DEMO w frontend/src/api/mock.js)."""
from datetime import date, timedelta

from app.sprawy import repo
from app.sprawy.model import TypZdarzenia as T, Zrodlo

# (nr, wnioskodawca, przedmiot, wpływ [dni od dziś], inicjały,
#  [(typ, data [dni od dziś], payload, nowy_termin [dni od dziś] | None)])
DEMO = [
    (701, "Fundacja Przejrzysta Gmina", "Wykaz dotacji dla organizacji pozarządowych w bieżącym roku.", -30, "AK",
     [(T.PRZEKAZANIE, -29, {"wydzialy": ["BAS"]}, None), (T.PROJEKT, -20, {}, None), (T.WYSLANO, -18, {}, None)]),
    (702, "Redakcja „Gazeta Testowa”", "Koszty utrzymania zieleni miejskiej w latach 2020–2026.", -20, "MN",
     [(T.PRZEKAZANIE, -19, {"wydzialy": ["WGK"]}, None), (T.PRZEDLUZENIE, -7, {"powod": "kwerenda w archiwum"}, 10)]),
    (703, "Jan Testowy", "Liczba wydanych pozwoleń na budowę w bieżącym roku.", -15, "AK",
     [(T.PRZEKAZANIE, -14, {"wydzialy": ["WAB"]}, None)]),
    (704, "Stowarzyszenie Miasto Dla Ludzi", "Umowy na zimowe utrzymanie ulic.", -14, "MN",
     [(T.PRZEKAZANIE, -13, {"wydzialy": ["WGK"]}, None)]),
    (705, "Anna Przykładowa", "Koszt organizacji Dni Bydgoszczy.", -14, "AK",
     [(T.PRZEKAZANIE, -13, {"wydzialy": ["BKB"]}, None), (T.ODP_WYDZIALU, -3, {"wydzial": "BKB"}, None),
      (T.PROJEKT, -1, {}, None)]),
    (706, "Piotr Fikcyjny", "Liczba miejsc w żłobkach miejskich.", -13, None, []),
    (707, "Redakcja Portalu Demo", "Wydatki na promocję miasta w mediach społecznościowych.", -11, "MN",
     [(T.PRZEKAZANIE, -10, {"wydzialy": ["BP"]}, None), (T.PROJEKT, -2, {}, None)]),
    (708, "Maria Wzorcowa", "Dokumentacja inwestycji przy ul. Przykładowej.", -10, "AK",
     [(T.WEZWANIE_DOPRECYZOWANIE, -8, {"dni_na_doprecyzowanie": 7}, None)]),
    (709, "Tomasz Demo", "Lista pustostanów w zasobie gminy.", -5, "MN",
     [(T.PRZEKAZANIE, -4, {"wydzialy": ["WMG"]}, None)]),
    (710, "Rada Rodziców SP nr 99", "Harmonogram remontów szkół w przyszłym roku.", -1, None, []),
]


def zaladuj(dzis: date) -> tuple[int, int]:
    d = lambda n: dzis + timedelta(days=n)  # noqa: E731
    nowe = pominiete = 0
    for nr, kto, co, wplyw, ini, zdarzenia in DEMO:
        znak = f"BKS.IV.1431.{nr}.{dzis.year}"
        if repo.znak_istnieje(znak):
            pominiete += 1
            continue
        sid = repo.utworz_sprawe(znak, d(wplyw), kto, co, ini, zrodlo=Zrodlo.DEMO)
        for typ, off, payload, termin in zdarzenia:
            repo.dodaj_zdarzenie(sid, typ, d(off), d(termin) if termin is not None else None,
                                 payload, ini)
        nowe += 1
    return nowe, pominiete
