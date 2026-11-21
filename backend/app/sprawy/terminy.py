"""Reguły terminów i statusu sprawy (źródło prawdy; frontend/src/api/mock.js ma uproszczoną kopię).

- termin: 14 dni od wpływu (art. 13 ust. 1 UDIP),
- wezwanie do doprecyzowania: bez nowego terminu wstrzymuje bieg, z nowym – ustawia go,
- otrzymanie doprecyzowania: 14 dni od daty otrzymania,
- przedłużenie (kwerenda): nowy termin, maks. 2 miesiące od wpływu (art. 13 ust. 2 UDIP),
- 7 dni na doprecyzowanie, potem można pozostawić wniosek bez rozpoznania.
"""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.sprawy.model import Flaga, Pilnosc, Status, TypZdarzenia, Zdarzenie, Zrodlo

TERMIN_DNI = 14
DOPRECYZOWANIE_DNI = 7
PRZEDLUZENIE_MAX_MIES = 2
WKROTCE_DNI = 3


def add_months(d: date, n: int) -> date:
    """Jak frontend: przy krótszym miesiącu przycina do ostatniego dnia."""
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


@dataclass
class Wynik:
    termin: date | None
    termin_wstrzymany: bool
    status: Status
    pilnosc: Pilnosc
    pozostalo_dni: int | None
    przedluzenie_dni: int | None
    data_odpowiedzi: date | None
    flagi: list[Flaga] = field(default_factory=list)


def przelicz(
    data_wplywu: date,
    zdarzenia: list[Zdarzenie],
    dzis: date,
    zrodlo: Zrodlo = Zrodlo.UPLOAD,
    flagi: list[Flaga] | None = None,
    import_termin: date | None = None,
    import_odpowiedz: date | None = None,
) -> Wynik:
    flagi = list(flagi or [])

    if zrodlo == Zrodlo.IMPORT:
        # sprawy archiwalne: wartości z xlsx „jak są”, problemy opisują flagi z importu
        return Wynik(import_termin, False, Status.WYSLANA, Pilnosc.ZAMKNIETA,
                     None, None, import_odpowiedz, flagi)

    termin = data_wplywu + timedelta(days=TERMIN_DNI)
    status = Status.NOWY
    wstrzymany = False
    przedluzenie = None
    odp = None
    wezwanie = None

    for e in sorted(zdarzenia, key=lambda e: (e.data, e.id)):
        match e.typ:
            case TypZdarzenia.PRZEKAZANIE:
                if status == Status.NOWY:
                    status = Status.W_WYDZIALACH
            case TypZdarzenia.WEZWANIE_DOPRECYZOWANIE:
                status = Status.DOPRECYZOWANIE
                wezwanie = e.data
                if e.nowy_termin:
                    termin = e.nowy_termin
                else:
                    wstrzymany = True
            case TypZdarzenia.DOPRECYZOWANIE_OTRZYMANE:
                status = Status.W_WYDZIALACH
                wstrzymany = False
                termin = e.data + timedelta(days=TERMIN_DNI)
            case TypZdarzenia.PRZEDLUZENIE:
                if e.nowy_termin:
                    przedluzenie = (e.nowy_termin - termin).days
                    termin = e.nowy_termin
                status = Status.PRZEDLUZONA
            case TypZdarzenia.PROJEKT:
                status = Status.PROJEKT_GOTOWY
            case TypZdarzenia.WYSLANO:
                status = Status.WYSLANA
                odp = e.data
            case TypZdarzenia.BEZ_ROZPOZNANIA:
                status = Status.BEZ_ROZPOZNANIA
                odp = e.data

    zamknieta = status in (Status.WYSLANA, Status.BEZ_ROZPOZNANIA)
    pilnosc = Pilnosc.ZAMKNIETA
    pozostalo = None
    if not zamknieta and wstrzymany:
        pilnosc = Pilnosc.BRAK
    elif not zamknieta:
        pozostalo = (termin - dzis).days
        pilnosc = (
            Pilnosc.PRZEKROCZONY if pozostalo < 0
            else Pilnosc.DZIS if pozostalo == 0
            else Pilnosc.JUTRO if pozostalo == 1
            else Pilnosc.WKROTCE if pozostalo <= WKROTCE_DNI
            else Pilnosc.BRAK
        )
        if is_weekend(termin):
            flagi.append(Flaga(
                kod="TERMIN_W_WEEKEND",
                opis="Termin przypada w weekend – sprawdź zasadę liczenia (art. 57 § 4 KPA).",
            ))

    if (status == Status.DOPRECYZOWANIE and wezwanie
            and dzis > wezwanie + timedelta(days=DOPRECYZOWANIE_DNI)):
        flagi.append(Flaga(
            kod="DOPRECYZOWANIE_MINELO",
            opis=f"Minęło {DOPRECYZOWANIE_DNI} dni na doprecyzowanie.",
            propozycja="Rozważ pozostawienie wniosku bez rozpoznania.",
        ))
    if termin > add_months(data_wplywu, PRZEDLUZENIE_MAX_MIES):
        flagi.append(Flaga(
            kod="PRZEDLUZENIE_PONAD_2_MIES",
            opis="Nowy termin przekracza 2 miesiące od dnia wpływu (art. 13 ust. 2 UDIP).",
        ))

    return Wynik(
        termin=None if wstrzymany else termin,
        termin_wstrzymany=wstrzymany,
        status=status,
        pilnosc=pilnosc,
        pozostalo_dni=pozostalo,
        przedluzenie_dni=przedluzenie,
        data_odpowiedzi=odp,
        flagi=flagi,
    )


# Dozwolone zdarzenia w danym statusie (jak AKCJE w frontend/src/pages/Sprawa.jsx).
DOZWOLONE: dict[TypZdarzenia, set[Status]] = {
    TypZdarzenia.PRZEKAZANIE: {Status.NOWY, Status.W_WYDZIALACH, Status.PRZEDLUZONA},
    TypZdarzenia.ODP_WYDZIALU: {Status.W_WYDZIALACH, Status.PRZEDLUZONA},
    TypZdarzenia.WEZWANIE_DOPRECYZOWANIE: {Status.NOWY, Status.W_WYDZIALACH},
    TypZdarzenia.DOPRECYZOWANIE_OTRZYMANE: {Status.DOPRECYZOWANIE},
    TypZdarzenia.PRZEDLUZENIE: {Status.NOWY, Status.W_WYDZIALACH, Status.PRZEDLUZONA},
    TypZdarzenia.PROJEKT: {Status.W_WYDZIALACH, Status.PRZEDLUZONA},
    TypZdarzenia.WYSLANO: {Status.PROJEKT_GOTOWY},
    TypZdarzenia.BEZ_ROZPOZNANIA: {Status.DOPRECYZOWANIE},
    TypZdarzenia.REJESTRACJA: set(),  # tylko przy tworzeniu sprawy
}
