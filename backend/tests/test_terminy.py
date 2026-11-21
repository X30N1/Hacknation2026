from datetime import date

from app.sprawy.model import Pilnosc, Status, TypZdarzenia as T, Zdarzenie, Zrodlo
from app.sprawy.terminy import add_months, przelicz

WPLYW = date(2026, 11, 2)  # poniedziałek; +14 = 16.11 (pn)
_id = iter(range(1, 1000))


def z(typ, data, nowy_termin=None):
    return Zdarzenie(id=next(_id), typ=typ, data=data, nowy_termin=nowy_termin)


def kody(w):
    return {f.kod for f in w.flagi}


def test_add_months_przycina():
    assert add_months(date(2026, 8, 31), 2) == date(2026, 10, 31)
    assert add_months(date(2026, 12, 31), 2) == date(2027, 2, 28)


def test_nowy_14_dni_i_pilnosc():
    zd = [z(T.REJESTRACJA, WPLYW)]
    assert przelicz(WPLYW, zd, date(2026, 11, 5)).termin == date(2026, 11, 16)
    assert przelicz(WPLYW, zd, date(2026, 11, 5)).pilnosc == Pilnosc.BRAK
    assert przelicz(WPLYW, zd, date(2026, 11, 13)).pilnosc == Pilnosc.WKROTCE
    assert przelicz(WPLYW, zd, date(2026, 11, 15)).pilnosc == Pilnosc.JUTRO
    assert przelicz(WPLYW, zd, date(2026, 11, 16)).pilnosc == Pilnosc.DZIS
    w = przelicz(WPLYW, zd, date(2026, 11, 18))
    assert (w.pilnosc, w.pozostalo_dni, w.status) == (Pilnosc.PRZEKROCZONY, -2, Status.NOWY)


def test_przedluzenie():
    w = przelicz(WPLYW, [z(T.PRZEKAZANIE, WPLYW), z(T.PRZEDLUZENIE, date(2026, 11, 10), date(2026, 12, 1))],
                 date(2026, 11, 10))
    assert (w.status, w.termin, w.przedluzenie_dni) == (Status.PRZEDLUZONA, date(2026, 12, 1), 15)
    w = przelicz(WPLYW, [z(T.PRZEDLUZENIE, WPLYW, date(2027, 1, 15))], WPLYW)
    assert "PRZEDLUZENIE_PONAD_2_MIES" in kody(w)


def test_doprecyzowanie_wstrzymuje_i_wznawia():
    w = przelicz(WPLYW, [z(T.WEZWANIE_DOPRECYZOWANIE, date(2026, 11, 3))], date(2026, 11, 5))
    assert (w.status, w.termin, w.termin_wstrzymany, w.pilnosc) == \
        (Status.DOPRECYZOWANIE, None, True, Pilnosc.BRAK)
    assert "DOPRECYZOWANIE_MINELO" in kody(przelicz(
        WPLYW, [z(T.WEZWANIE_DOPRECYZOWANIE, date(2026, 11, 3))], date(2026, 11, 11)))
    w = przelicz(WPLYW, [z(T.WEZWANIE_DOPRECYZOWANIE, date(2026, 11, 3)),
                         z(T.DOPRECYZOWANIE_OTRZYMANE, date(2026, 11, 6))], date(2026, 11, 6))
    assert (w.status, w.termin, w.termin_wstrzymany) == (Status.W_WYDZIALACH, date(2026, 11, 20), False)


def test_wyslano_zamyka():
    w = przelicz(WPLYW, [z(T.PROJEKT, WPLYW), z(T.WYSLANO, date(2026, 11, 10))], date(2026, 12, 30))
    assert (w.status, w.pilnosc, w.data_odpowiedzi, w.pozostalo_dni) == \
        (Status.WYSLANA, Pilnosc.ZAMKNIETA, date(2026, 11, 10), None)


def test_weekend_flaga():
    sobota = date(2026, 11, 7)  # +14 = sobota 21.11
    assert "TERMIN_W_WEEKEND" in kody(przelicz(sobota, [], sobota))


def test_import_jak_jest():
    w = przelicz(WPLYW, [], date(2027, 1, 1), zrodlo=Zrodlo.IMPORT,
                 import_termin=date(2025, 1, 1), import_odpowiedz=date(2026, 11, 10))
    assert (w.status, w.pilnosc, w.termin) == (Status.WYSLANA, Pilnosc.ZAMKNIETA, date(2025, 1, 1))
