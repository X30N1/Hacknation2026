"""Projekty pism w sprawie (drafty) – odpowiedź na wniosek, wezwanie do doprecyzowania,
zapytanie do wydziałów, zawiadomienie o przedłużeniu terminu.

Materiały: treść wniosku (i doprecyzowania), odpowiedzi wydziałów, pisma tego samego rodzaju
z najbardziej podobnych spraw z archiwum (wzór stylu) i fragmenty bazy wiedzy (ustawy, zarządzenia).
Dokumenty spraw są w bazie już zanonimizowane. Dane wnioskodawcy NIE trafiają do modelu:
model wstawia znacznik [WNIOSKODAWCA], który podmieniamy lokalnie.

Z LLM, gdy dostępny; w przeciwnym razie szablon pisma. Wynik zawsze jest PROJEKTEM do sprawdzenia
przez urzędnika (merytorycznie i pod kątem anonimizacji) – nic nie jest wysyłane ani zapisywane.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app import llm_client
from app.config import settings
from app.prompts import SYSTEM_PROMPT
from app.sprawy import archiwum, wydzialy
from app.sprawy.model import ProjektPisma, RodzajPisma, SprawaSzczegoly, TypZdarzenia
from app.sprawy.terminy import DOPRECYZOWANIE_DNI

log = logging.getLogger(__name__)

NAGLOWEK = "PROJEKT – wymaga weryfikacji urzędnika"
ZNACZNIK = "[WNIOSKODAWCA]"
PODPIS = "Z poważaniem\n[DO UZUPEŁNIENIA – podpis osoby upoważnionej]"


def _pl(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "[DO UZUPEŁNIENIA]"


def _nazwa(skrot: str | None) -> str:
    if not skrot:
        return "Wydział (nie wskazano)"
    return wydzialy.JEDNOSTKI.get(skrot, (skrot, []))[0]


@dataclass
class Parametry:
    """Dane z okna akcji (wydziały przy przekazaniu, nowy termin przy przedłużeniu)."""
    wydzialy: list[str]
    nowy_termin: date | None


@dataclass
class Materialy:
    wnioski: list
    odpowiedzi: list


def _materialy(s: SprawaSzczegoly) -> Materialy:
    tekstowe = [d for d in s.dokumenty if d.tekst.strip()]
    return Materialy(
        wnioski=[d for d in tekstowe if d.rodzaj in ("WNIOSEK", "DOPRECYZOWANIE")],
        odpowiedzi=[d for d in tekstowe if d.rodzaj == "ODP_WYDZIALU"],
    )


def _wydzialy_sprawy(s: SprawaSzczegoly, p: Parametry) -> list[str]:
    """Wydziały z okna akcji, a gdy brak – z wcześniejszych przekazań w historii sprawy."""
    if p.wydzialy:
        return p.wydzialy
    out: list[str] = []
    for z in s.zdarzenia:
        if z.typ == TypZdarzenia.PRZEKAZANIE:
            out += [w for w in z.payload.get("wydzialy") or [] if w not in out]
    return out


def _zakres(s: SprawaSzczegoly) -> str:
    return f" w zakresie: {s.przedmiot.rstrip('.')}" if s.przedmiot else ""


def _naglowek(s: SprawaSzczegoly, dzis: date, adresat: str = ZNACZNIK) -> str:
    return f"{NAGLOWEK}\n\nBydgoszcz, dnia {_pl(dzis)} r.\n{s.znak}\n\n{adresat}\n\n"


# ---------- szablony (bez LLM) ----------
def _szablon_odpowiedz(s: SprawaSzczegoly, dzis: date, m: Materialy, p: Parametry) -> str:
    tresc = "\n\n".join(
        f"{_nazwa(d.wydzial)} przekazał następujące informacje:\n{d.tekst.strip()}" for d in m.odpowiedzi
    ) or "[DO UZUPEŁNIENIA – brak wgranych odpowiedzi wydziałów]"
    return (
        _naglowek(s, dzis)
        + f"W odpowiedzi na wniosek z dnia {_pl(s.data_wplywu)} r. o udostępnienie informacji publicznej"
        f"{_zakres(s)}, na podstawie art. 10 ust. 1 ustawy z dnia 6 września 2001 r. o dostępie do informacji "
        f"publicznej, uprzejmie informuję, że:\n\n{tresc}\n\n{PODPIS}"
    )


def _szablon_wezwanie(s: SprawaSzczegoly, dzis: date, m: Materialy, p: Parametry) -> str:
    return (
        _naglowek(s, dzis)
        + f"W związku z wnioskiem z dnia {_pl(s.data_wplywu)} r. o udostępnienie informacji publicznej"
        f"{_zakres(s)} uprzejmie proszę o doprecyzowanie wniosku poprzez wskazanie:\n"
        "1. [DO UZUPEŁNIENIA – której części wniosku dotyczy niejasność i jakiej informacji potrzeba]\n\n"
        f"Wyjaśnienia prosimy przekazać w terminie {DOPRECYZOWANIE_DNI} dni od dnia otrzymania niniejszego "
        "pisma. Termin na udostępnienie informacji biegnie od dnia otrzymania doprecyzowania. "
        "Nieudzielenie wyjaśnień w wyznaczonym terminie spowoduje pozostawienie wniosku bez rozpoznania.\n\n"
        f"{PODPIS}"
    )


def termin_wewnetrzny(s: SprawaSzczegoly, dzis: date) -> date:
    """Termin dla wydziałów: tydzień, ale nie później niż 3 dni przed terminem ustawowym."""
    t = dzis + timedelta(days=7)
    if s.termin:
        t = min(t, s.termin - timedelta(days=3))
    return max(t, dzis)


def _szablon_przekazanie(s: SprawaSzczegoly, dzis: date, m: Materialy, p: Parametry) -> str:
    adresaci = "\n".join(_nazwa(w) for w in _wydzialy_sprawy(s, p)) or "[DO UZUPEŁNIENIA – wydział]"
    return (
        _naglowek(s, dzis, f"Do:\n{adresaci}")
        + f"W związku z wnioskiem z dnia {_pl(s.data_wplywu)} r. o udostępnienie informacji publicznej"
        f"{_zakres(s)} (treść wniosku w załączeniu) uprzejmie proszę o przekazanie informacji:\n"
        "1. [DO UZUPEŁNIENIA – pytania z wniosku do tego wydziału]\n\n"
        f"Proszę o odpowiedź w terminie do dnia {_pl(termin_wewnetrzny(s, dzis))} r. – termin ustawowy "
        f"na udostępnienie informacji upływa {_pl(s.termin)} r. Jeśli wydział nie posiada żądanej "
        "informacji albo nie jest ona informacją publiczną, proszę o wskazanie tego w odpowiedzi.\n\n"
        f"{PODPIS}"
    )


def _szablon_przedluzenie(s: SprawaSzczegoly, dzis: date, m: Materialy, p: Parametry) -> str:
    return (
        _naglowek(s, dzis)
        + f"W związku z wnioskiem z dnia {_pl(s.data_wplywu)} r. o udostępnienie informacji publicznej"
        f"{_zakres(s)}, na podstawie art. 13 ust. 2 ustawy z dnia 6 września 2001 r. o dostępie do informacji "
        "publicznej uprzejmie informuję, że informacja nie może zostać udostępniona w terminie 14 dni. "
        "Powodem opóźnienia jest [DO UZUPEŁNIENIA – np. konieczność zebrania informacji z kilku wydziałów "
        f"lub znaczny zakres wniosku].\n\nInformacja zostanie udostępniona w terminie do dnia "
        f"{_pl(p.nowy_termin)} r.\n\n{PODPIS}"
    )


# ---------- polecenia dla LLM ----------
WSPOLNE = """\
- Pierwsza linia: „{naglowek}”. Potem: miejscowość i data „Bydgoszcz, dnia {data} r.”, znak sprawy \
„{znak}”, adresat: {adresat}.
- Znaki █████ to dane zamazane przy anonimizacji – zostaw je bez zmian, nie zgaduj ich treści.
- Pisma z archiwum to wyłącznie wzór stylu – nie przenoś z nich faktów.
- Brakujące informacje oznacz jako [DO UZUPEŁNIENIA – …] z opisem, czego brakuje.
- Na końcu „Z poważaniem” i miejsce na podpis. Zwróć sam tekst pisma, bez Markdown i bez komentarzy."""

POLECENIA = {
    RodzajPisma.ODPOWIEDZ: """\
Przygotuj PROJEKT pisma – odpowiedzi Urzędu Miasta Bydgoszczy na wniosek o udostępnienie informacji \
publicznej z dnia {wplyw} r., wyłącznie na podstawie poniższych materiałów.
- Treść: odwołanie do wniosku, podstawa prawna, informacje z odpowiedzi wydziałów (nie zmieniaj liczb, \
dat ani nazw). Gdy odpowiedź wydziału nie obejmuje części wniosku, wstaw [DO UZUPEŁNIENIA – …].""",
    RodzajPisma.WEZWANIE: """\
Przygotuj PROJEKT wezwania do doprecyzowania wniosku o udostępnienie informacji publicznej z dnia \
{wplyw} r., na podstawie poniższych materiałów.
- Wskaż konkretnie, które części wniosku są niejasne lub zbyt ogólne, i sformułuj ponumerowane \
pytania do wnioskodawcy. Nie oceniaj, czy informacja zostanie udostępniona.
- Termin na wyjaśnienia: {dni} dni od otrzymania pisma; termin na udostępnienie biegnie od dnia \
doprecyzowania; brak wyjaśnień = pozostawienie wniosku bez rozpoznania.""",
    RodzajPisma.PRZEKAZANIE: """\
Przygotuj PROJEKT wewnętrznego pisma Biura Komunikacji Społecznej do wydziałów Urzędu Miasta \
Bydgoszczy z prośbą o informacje potrzebne do odpowiedzi na wniosek o udostępnienie informacji \
publicznej z dnia {wplyw} r.
- Adresaci: {wydzialy}. Dla każdego wydziału wypisz ponumerowane pytania z wniosku, które należą \
do jego zakresu (nie dopisuj pytań spoza wniosku).
- Termin odpowiedzi wydziału: do dnia {termin_wewn} r.; termin ustawowy upływa {termin} r.
- Pismo jest wewnętrzne – nie wpisuj danych wnioskodawcy.""",
    RodzajPisma.PRZEDLUZENIE: """\
Przygotuj PROJEKT zawiadomienia wnioskodawcy o przedłużeniu terminu udostępnienia informacji \
publicznej (art. 13 ust. 2 ustawy o dostępie do informacji publicznej) – wniosek z dnia {wplyw} r.
- Podaj powód opóźnienia wynikający z materiałów (np. zakres wniosku, liczba wydziałów: {wydzialy}) \
i nowy termin: {nowy_termin} r. (nie zmieniaj go).""",
}


@dataclass
class Pismo:
    szablon: Callable[[SprawaSzczegoly, date, Materialy, Parametry], str]
    wzor: tuple[str, ...]          # rodzaje dokumentów z podobnych spraw – wzór stylu
    wiedza: str                    # dodatkowe słowa do wyszukania podstaw prawnych
    adresat: str = ZNACZNIK
    odpowiedzi: bool = False       # czy odpowiedzi wydziałów są materiałem


PISMA = {
    RodzajPisma.ODPOWIEDZ: Pismo(_szablon_odpowiedz, ("ODPOWIEDZ", "PROJEKT"), "udostępnienie informacji",
                                 odpowiedzi=True),
    RodzajPisma.WEZWANIE: Pismo(_szablon_wezwanie, ("WEZWANIE",), "doprecyzowanie wniosku bez rozpoznania"),
    RodzajPisma.PRZEKAZANIE: Pismo(_szablon_przekazanie, ("ZAPYTANIE",), "wydział informacja termin",
                                   adresat="„Do:” i nazwy wydziałów (każda w osobnej linii)"),
    RodzajPisma.PRZEDLUZENIE: Pismo(_szablon_przedluzenie, ("KWERENDA",), "przedłużenie terminu art. 13 ust. 2",
                                    odpowiedzi=True),
}


def _blok(tytul: str, tekst: str, maks: int | None = None) -> str:
    maks = settings.llm.limity.projekt_material if maks is None else maks
    return f"### {tytul}\n{tekst.strip()[:maks]}"


async def _z_llm(rodzaj: RodzajPisma, s: SprawaSzczegoly, dzis: date, m: Materialy, p: Parametry,
                 wzory, wiedza) -> str:
    pismo = PISMA[rodzaj]
    bloki = [_blok(f"{'Doprecyzowanie' if d.rodzaj == 'DOPRECYZOWANIE' else 'Wniosek'} ({d.nazwa_pliku})", d.tekst)
             for d in m.wnioski]
    if pismo.odpowiedzi:
        bloki += [_blok(f"Odpowiedź: {_nazwa(d.wydzial)} ({d.nazwa_pliku})", d.tekst) for d in m.odpowiedzi]
    wzor_max = settings.llm.limity.projekt_wzor
    bloki += [_blok(f"Wzór stylu – pismo w sprawie {znak}", t, wzor_max) for znak, t in wzory]
    bloki += [_blok(f"Podstawa prawna ({n})", t) for n, t in wiedza]
    wydz = ", ".join(_nazwa(w) for w in _wydzialy_sprawy(s, p)) or "nie wskazano"
    polecenie = POLECENIA[rodzaj].format(
        wplyw=_pl(s.data_wplywu), dni=DOPRECYZOWANIE_DNI, wydzialy=wydz, termin=_pl(s.termin),
        termin_wewn=_pl(termin_wewnetrzny(s, dzis)), nowy_termin=_pl(p.nowy_termin),
    ) + "\n" + WSPOLNE.format(naglowek=NAGLOWEK, data=_pl(dzis), znak=s.znak,
                              adresat=pismo.adresat if pismo.adresat != ZNACZNIK
                              else f"znacznik {ZNACZNIK} (nie wpisuj danych wnioskodawcy)")
    tresc = f"{polecenie}\n\nPrzedmiot wniosku: {s.przedmiot or '—'}\n\n" + "\n\n".join(bloki)
    return await llm_client.complete(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": tresc}],
        temperature=settings.llm.temperatury.projekt,
    )


async def przygotuj(s: SprawaSzczegoly, dzis: date, rodzaj: RodzajPisma = RodzajPisma.ODPOWIEDZ,
                    adresaci: list[str] | None = None, nowy_termin: date | None = None) -> ProjektPisma:
    pismo = PISMA[rodzaj]
    p = Parametry(wydzialy=[w.strip().upper() for w in adresaci or [] if w.strip()], nowy_termin=nowy_termin)
    m = _materialy(s)
    wzory = archiwum.pisma_podobnych(s.id, dzis, pismo.wzor)
    wiedza = archiwum.fragmenty_wiedzy(f"{archiwum.tekst_sprawy(s.id)} {pismo.wiedza}")
    zrodla = [f"{'Doprecyzowanie' if d.rodzaj == 'DOPRECYZOWANIE' else 'Wniosek'}: {d.nazwa_pliku}" for d in m.wnioski]
    if pismo.odpowiedzi:
        zrodla += [f"Odpowiedź wydziału {d.wydzial or '—'}: {d.nazwa_pliku}" for d in m.odpowiedzi]
    uwagi = []
    if not m.wnioski:
        uwagi.append("Brak treści wniosku w dokumentach sprawy – projekt powstał tylko z przedmiotu sprawy.")
    if rodzaj == RodzajPisma.ODPOWIEDZ and not m.odpowiedzi:
        uwagi.append("Brak wgranych odpowiedzi wydziałów – projekt zawiera tylko szkielet pisma.")
    if rodzaj == RodzajPisma.PRZEKAZANIE and not _wydzialy_sprawy(s, p):
        uwagi.append("Nie wskazano wydziałów – uzupełnij adresatów.")

    tekst, uzyty = None, False
    if not llm_client.is_echo_mode():
        try:
            tekst = (await _z_llm(rodzaj, s, dzis, m, p, wzory, wiedza)).strip()
            uzyty = bool(tekst)
            zrodla += [f"Wzór stylu: pismo w sprawie {z}" for z, _ in wzory]
            zrodla += [f"Podstawa prawna: {n}" for n, _ in wiedza]
        except Exception as exc:  # noqa: BLE001
            log.warning("Projekt pisma (%s) przez LLM nieudany: %s", rodzaj.value, exc)
            uwagi.append("Model językowy niedostępny – projekt z szablonu.")
    else:
        uwagi.append("Model językowy wyłączony – projekt z szablonu.")
    if not tekst:
        tekst = pismo.szablon(s, dzis, m, p)
    if not tekst.startswith(NAGLOWEK):
        tekst = f"{NAGLOWEK}\n\n{tekst}"
    tekst = tekst.replace(ZNACZNIK, s.wnioskodawca or "[DO UZUPEŁNIENIA – adresat]")
    return ProjektPisma(tekst=tekst, llm_uzyty=uzyty, zrodla=zrodla, uwagi=uwagi)
