"""Projekt odpowiedzi na wniosek – z odpowiedzi wydziałów wgranych przez urzędnika.

Materiały: treść wniosku, odpowiedzi wydziałów (dokumenty ODP_WYDZIALU), odpowiedzi z najbardziej
podobnych spraw z archiwum (wzór stylu) i fragmenty bazy wiedzy (ustawy, zarządzenia).
Wszystkie te teksty są w bazie już zanonimizowane. Dane wnioskodawcy NIE trafiają do modelu:
model wstawia znacznik [WNIOSKODAWCA], który podmieniamy lokalnie.

Z LLM, gdy dostępny; w przeciwnym razie szablon pisma. Wynik zawsze jest PROJEKTEM do sprawdzenia
przez urzędnika (merytorycznie i pod kątem anonimizacji) – nic nie jest wysyłane ani zapisywane.
"""
import logging
from datetime import date

from app import llm_client
from app.config import settings
from app.prompts import SYSTEM_PROMPT
from app.sprawy import archiwum, wydzialy
from app.sprawy.model import ProjektOdpowiedzi, SprawaSzczegoly

log = logging.getLogger(__name__)

NAGLOWEK = "PROJEKT – wymaga weryfikacji urzędnika"
ZNACZNIK = "[WNIOSKODAWCA]"


def _pl(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "[DO UZUPEŁNIENIA]"


def _nazwa(skrot: str | None) -> str:
    if not skrot:
        return "Wydział (nie wskazano)"
    return wydzialy.JEDNOSTKI.get(skrot, (skrot, []))[0]


def _materialy(s: SprawaSzczegoly):
    wnioski = [d for d in s.dokumenty if d.rodzaj == "WNIOSEK" and d.tekst.strip()]
    odpowiedzi = [d for d in s.dokumenty if d.rodzaj == "ODP_WYDZIALU" and d.tekst.strip()]
    return wnioski, odpowiedzi


def szablon(s: SprawaSzczegoly, dzis: date) -> str:
    _, odpowiedzi = _materialy(s)
    zakres = f" w zakresie: {s.przedmiot.rstrip('.')}" if s.przedmiot else ""
    tresc = "\n\n".join(
        f"{_nazwa(d.wydzial)} przekazał następujące informacje:\n{d.tekst.strip()}" for d in odpowiedzi
    ) or "[DO UZUPEŁNIENIA – brak wgranych odpowiedzi wydziałów]"
    return (
        f"{NAGLOWEK}\n\n"
        f"Bydgoszcz, dnia {_pl(dzis)} r.\n{s.znak}\n\n{ZNACZNIK}\n\n"
        f"W odpowiedzi na wniosek z dnia {_pl(s.data_wplywu)} r. o udostępnienie informacji publicznej"
        f"{zakres}, na podstawie art. 10 ust. 1 ustawy z dnia 6 września 2001 r. o dostępie do informacji "
        f"publicznej, uprzejmie informuję, że:\n\n{tresc}\n\n"
        "Z poważaniem\n[DO UZUPEŁNIENIA – podpis osoby upoważnionej]"
    )


POLECENIE = """\
Przygotuj PROJEKT pisma – odpowiedzi Urzędu Miasta Bydgoszczy na wniosek o udostępnienie informacji \
publicznej, wyłącznie na podstawie poniższych materiałów.
- Pierwsza linia: „{naglowek}”. Potem: miejscowość i data „Bydgoszcz, dnia {data} r.”, znak sprawy \
„{znak}”, adresat jako znacznik {znacznik} (nie wpisuj danych wnioskodawcy).
- Treść: odwołanie do wniosku z dnia {wplyw} r., podstawa prawna, informacje z odpowiedzi wydziałów \
(nie zmieniaj liczb, dat ani nazw), na końcu „Z poważaniem” i miejsce na podpis.
- Gdy odpowiedź wydziału nie obejmuje części wniosku, wstaw [DO UZUPEŁNIENIA – …] z opisem braku.
- Znaki █████ to dane zamazane przy anonimizacji – zostaw je bez zmian, nie zgaduj ich treści.
- Odpowiedzi z archiwum to wyłącznie wzór stylu – nie przenoś z nich faktów.
- Zwróć sam tekst pisma, bez Markdown i bez komentarzy."""


def _blok(tytul: str, tekst: str, maks: int | None = None) -> str:
    maks = settings.llm.limity.projekt_material if maks is None else maks
    return f"### {tytul}\n{tekst.strip()[:maks]}"


async def _z_llm(s: SprawaSzczegoly, dzis: date, wnioski, odpowiedzi, wzory, wiedza) -> str:
    bloki = [_blok(f"Wniosek ({d.nazwa_pliku})", d.tekst) for d in wnioski]
    bloki += [_blok(f"Odpowiedź: {_nazwa(d.wydzial)} ({d.nazwa_pliku})", d.tekst) for d in odpowiedzi]
    wzor_max = settings.llm.limity.projekt_wzor
    bloki += [_blok(f"Wzór stylu – odpowiedź w sprawie {znak}", t, wzor_max) for znak, t in wzory]
    bloki += [_blok(f"Podstawa prawna ({n})", t) for n, t in wiedza]
    polecenie = POLECENIE.format(naglowek=NAGLOWEK, data=_pl(dzis), znak=s.znak, znacznik=ZNACZNIK,
                                 wplyw=_pl(s.data_wplywu))
    tresc = f"{polecenie}\n\nPrzedmiot wniosku: {s.przedmiot or '—'}\n\n" + "\n\n".join(bloki)
    return await llm_client.complete(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": tresc}],
        temperature=settings.llm.temperatury.projekt,
    )


async def przygotuj(s: SprawaSzczegoly, dzis: date) -> ProjektOdpowiedzi:
    wnioski, odpowiedzi = _materialy(s)
    wzory = archiwum.odpowiedzi_podobnych(s.id, dzis)
    wiedza = archiwum.fragmenty_wiedzy(archiwum.tekst_sprawy(s.id))
    zrodla = [f"Wniosek: {d.nazwa_pliku}" for d in wnioski]
    zrodla += [f"Odpowiedź wydziału {d.wydzial or '—'}: {d.nazwa_pliku}" for d in odpowiedzi]
    uwagi = []
    if not odpowiedzi:
        uwagi.append("Brak wgranych odpowiedzi wydziałów – projekt zawiera tylko szkielet pisma.")

    tekst, uzyty = None, False
    if not llm_client.is_echo_mode():
        try:
            tekst = (await _z_llm(s, dzis, wnioski, odpowiedzi, wzory, wiedza)).strip()
            uzyty = bool(tekst)
            zrodla += [f"Wzór stylu: odpowiedź w sprawie {z}" for z, _ in wzory]
            zrodla += [f"Podstawa prawna: {n}" for n, _ in wiedza]
        except Exception as exc:  # noqa: BLE001
            log.warning("Projekt odpowiedzi przez LLM nieudany: %s", exc)
            uwagi.append("Model językowy niedostępny – projekt z szablonu.")
    else:
        uwagi.append("Model językowy wyłączony – projekt z szablonu.")
    if not tekst:
        tekst = szablon(s, dzis)
    if not tekst.startswith(NAGLOWEK):
        tekst = f"{NAGLOWEK}\n\n{tekst}"
    tekst = tekst.replace(ZNACZNIK, s.wnioskodawca or "[DO UZUPEŁNIENIA – adresat]")
    return ProjektOdpowiedzi(tekst=tekst, llm_uzyty=uzyty, zrodla=zrodla, uwagi=uwagi)
