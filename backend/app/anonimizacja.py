"""Propozycje danych do anonimizacji – co urzędnik powinien zamazać przed wysłaniem dokumentu.

Tylko PROPOZYCJE: o zamazaniu decyduje urzędnik (frontend: AnonimizacjaPodglad.jsx).
Trzy źródła, łączone w jedną listę zakresów bez nakładania:
  WZORZEC – wyrażenia regularne (PESEL, NIP, e-mail, konto…) – port frontend/src/lib/anonimizacja.js,
  SPRAWA  – wnioskodawca zapisany w sprawie, wyszukany w treści (także odmiana nazwiska),
  LLM     – imiona i nazwiska bez kontekstu, dane wrażliwe, sytuacja osobista (model lokalny).

Zakresy `start`/`end` to indeksy znaków (code points) w `tekst`. Dla polskiego tekstu są równe
indeksom JS (UTF-16); różnią się dopiero przy znakach spoza BMP (np. emoji).
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app import llm_client
from app.config import settings
from app.prompts import ANONYMIZED_DATA

log = logging.getLogger(__name__)

KATEGORIE = {
    "IMIE_NAZWISKO": "Imię i nazwisko",
    "PESEL": "PESEL",
    "NIP": "NIP",
    "DOWOD": "Dokument tożsamości",
    "DATA_URODZENIA": "Data urodzenia",
    "ADRES": "Adres",
    "TELEFON": "Telefon",
    "EMAIL": "E-mail",
    "KONTO": "Rachunek bankowy",
    "POJAZD": "Numer rejestracyjny pojazdu",
    "KSIEGA_WIECZYSTA": "Księga wieczysta",
    "DANE_WRAZLIWE": "Dane wrażliwe (zdrowie, poglądy, karalność…)",
    "SYTUACJA_OSOBISTA": "Sytuacja rodzinna / majątkowa",
    "TAJEMNICA": "Tajemnica ustawowo chroniona",
    "INNE": "Inne dane osobowe",
}
Kategoria = Literal[tuple(KATEGORIE)]  # type: ignore[valid-type]
Zrodlo = Literal["WZORZEC", "SPRAWA", "LLM"]

LLM_FRAGMENT_MAX = 6000  # TODO: limit – znaki tekstu w jednym zapytaniu do LLM
LLM_FRAGMENTY_MAX = 10   # TODO: limit – maks. zapytań do LLM na dokument (dalej tylko wzorce)


class Fragment(BaseModel):
    start: int
    end: int
    kategoria: Kategoria
    etykieta: str
    tekst: str
    zrodlo: Zrodlo
    powod: str | None = None


class Propozycje(BaseModel):
    fragmenty: list[Fragment]
    llm_uzyty: bool
    uwagi: list[str] = []


# ---------- wzorce ----------
DUZA = "A-ZĄĆĘŁŃÓŚŹŻ"
MALA = "a-ząćęłńóśźż"


def _pesel_ok(s: str) -> bool:
    if not re.fullmatch(r"\d{11}", s):
        return False
    w = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    return (10 - sum(k * int(c) for k, c in zip(w, s)) % 10) % 10 == int(s[10])


def _nip_ok(s: str) -> bool:
    c = re.sub(r"\D", "", s)
    if len(c) != 10:
        return False
    suma = sum(k * int(x) for k, x in zip([6, 5, 7, 2, 3, 4, 5, 6, 7], c)) % 11
    return suma != 10 and suma == int(c[9])


# (kategoria, wzorzec, grupa z zakresem, walidator) – kolejność jak we froncie
WZORCE: list[tuple[str, re.Pattern, int, object]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), 0, None),
    ("KONTO", re.compile(r"(?<!\d)(?:PL ?)?\d{2}(?: ?\d{4}){6}(?!\d)"), 0, None),
    ("PESEL", re.compile(r"(?<!\d)\d{11}(?!\d)"), 0, _pesel_ok),
    ("NIP", re.compile(r"(?<!\d)\d{3}[- ]?\d{3}[- ]?\d{2}[- ]?\d{2}(?!\d)"), 0, _nip_ok),
    ("DOWOD", re.compile(r"(?<![A-Z\d])[A-Z]{3} ?\d{6}(?!\d)"), 0, None),
    ("KSIEGA_WIECZYSTA", re.compile(r"\b[A-Z]{2}\d[A-Z]/\d{8}/\d\b"), 0, None),
    ("DATA_URODZENIA", re.compile(
        r"ur(?:\.|odzon\w*)\s*(?:dnia\s*)?(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})", re.I), 1, None),
    ("POJAZD", re.compile(
        r"rejestracyjn\w*\s*(?:nr|numer)?\s*:?\s*([A-Z]{1,3} ?\d[0-9A-Z]{3,5})\b", re.I), 1, None),
    ("TELEFON", re.compile(r"(?<!\d)(?:\+48[ -]?)?\d{3}[ -]?\d{3}[ -]?\d{3}(?!\d)"), 0, None),
    ("ADRES", re.compile(
        rf"\b(?:ul\.|ulica|al\.|aleja|os\.|osiedle|pl\.|plac)\s+[{DUZA}\d][\w.\- ]{{1,40}}?"
        r"\s\d+[A-Za-z]?(?:\s?/\s?\d+[A-Za-z]?)?"), 0, None),
    ("ADRES", re.compile(rf"\b\d{{2}}-\d{{3}}\s+[{DUZA}][{MALA}]+(?:[ -][{DUZA}][{MALA}]+)?"), 0, None),
    ("IMIE_NAZWISKO", re.compile(
        rf"\b(?:Pan|Pani|Państwo|Panem|Panią|[Ii]mi[ęe] i nazwisko|[Ww]nioskodawc\w+)\b[:\s]+"
        rf"((?:[{DUZA}][{MALA}]+(?:-[{DUZA}][{MALA}]+)?[ ]?){{2,3}})"), 1, None),
]


@dataclass
class _Traf:
    start: int
    end: int
    kategoria: str
    zrodlo: str
    powod: str | None = None


def _wzorce(tekst: str) -> list[_Traf]:
    out = []
    for kategoria, wzor, grupa, ok in WZORCE:
        for m in wzor.finditer(tekst):
            fr = (m.group(grupa) or "").rstrip()
            if not fr or (ok and not ok(fr)):
                continue
            start = m.start(grupa)
            out.append(_Traf(start, start + len(fr), kategoria, "WZORZEC"))
    return out


# ---------- wnioskodawca ze sprawy ----------
# osoby prawne nie podlegają anonimizacji
# (\b po kropce nigdy nie pasuje na końcu nazwy – „Budowlanka S.A.” – stąd skróty osobno)
OSOBA_PRAWNA = re.compile(
    r"\b(?:sp\.|s\.\s?a\.|sp\.\s?j\.|sp\.\s?k\.)|\b(?:spółk\w*|fundacj\w*|stowarzysz\w*|redakcj\w*|gazet\w*|"
    r"portal\w*|związ\w*|instytut\w*|kancelari\w*|partia|urząd|gmina|ośrodek|centrum|rada|szkoła|"
    r"zarząd|towarzystw\w*)\b", re.I)


def _wnioskodawca(tekst: str, wnioskodawca: str | None) -> list[_Traf]:
    w = " ".join((wnioskodawca or "").split())
    if not w:
        return []
    powod = "wnioskodawca w sprawie"
    if "@" in w:
        return [_Traf(m.start(), m.end(), "EMAIL", "SPRAWA", powod)
                for m in re.finditer(re.escape(w), tekst, re.I)]
    if OSOBA_PRAWNA.search(w):
        return []
    out = [_Traf(m.start(), m.end(), "IMIE_NAZWISKO", "SPRAWA", powod)
           for m in re.finditer(re.escape(w), tekst, re.I)]
    # samo nazwisko, także w odmianie (Kowalski -> Kowalskiego, Kowalska -> Kowalskiej)
    nazwisko = w.split()[-1]
    if len(w.split()) >= 2 and len(nazwisko) >= 3:
        rdzen = nazwisko[:-1] if len(nazwisko) >= 5 else nazwisko
        for m in re.finditer(rf"\b{re.escape(rdzen)}\w{{0,4}}\b", tekst):
            out.append(_Traf(m.start(), m.end(), "IMIE_NAZWISKO", "SPRAWA", powod))
    return out


# ---------- LLM ----------
PROMPT = f"""\
Jesteś asystentem anonimizacji dokumentów urzędowych (dostęp do informacji publicznej).
Wskaż w poniższym tekście fragmenty, które urzędnik powinien zamazać przed udostępnieniem.
Dane podlegające anonimizacji:
{ANONYMIZED_DATA}

NIE wskazuj: nazw urzędów, wydziałów, firm i instytucji, osób pełniących funkcje publiczne
(prezydent, radni, urzędnicy podpisujący pisma służbowo), przepisów, kwot z budżetu miasta.

Zwróć WYŁĄCZNIE obiekt JSON:
{{"dane": [{{"tekst": "<fragment skopiowany z tekstu dosłownie>", "kategoria": "<kategoria>",
  "powod": "<krótko, dlaczego>"}}]}}
Dozwolone kategorie: {", ".join(KATEGORIE)}.
Gdy nic nie ma – {{"dane": []}}.

Tekst:
<<<
{{tekst}}
>>>"""


def _czesci(tekst: str) -> list[tuple[int, str]]:
    """Podział na fragmenty dla LLM – na granicy akapitu / wiersza, z przesunięciem."""
    out, poz = [], 0
    while poz < len(tekst) and len(out) < LLM_FRAGMENTY_MAX:
        koniec = min(poz + LLM_FRAGMENT_MAX, len(tekst))
        if koniec < len(tekst):
            ciecie = max(tekst.rfind("\n\n", poz, koniec), tekst.rfind("\n", poz, koniec))
            if ciecie > poz + LLM_FRAGMENT_MAX // 2:
                koniec = ciecie
        out.append((poz, tekst[poz:koniec]))
        poz = koniec
    return out


async def _llm_czesc(przesuniecie: int, czesc: str) -> list[_Traf]:
    odp = await llm_client.complete(
        [{"role": "user", "content": PROMPT.replace("{tekst}", czesc)}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    m = re.search(r"\{.*\}", odp, re.S)
    dane = json.loads(m.group(0)).get("dane", []) if m else []
    out = []
    for d in dane if isinstance(dane, list) else []:
        if not isinstance(d, dict):
            continue
        fr = str(d.get("tekst") or "").strip()
        kategoria = str(d.get("kategoria") or "INNE").upper()
        if kategoria not in KATEGORIE:
            kategoria = "INNE"
        if len(fr) < 2:
            continue
        powod = str(d.get("powod") or "").strip() or None
        # LLM podaje cytat, nie indeksy – zaznaczamy każde wystąpienie
        for w in re.finditer(re.escape(fr), czesc):
            out.append(_Traf(przesuniecie + w.start(), przesuniecie + w.end(), kategoria, "LLM", powod))
    return out


async def _llm(tekst: str) -> tuple[list[_Traf], list[str]]:
    czesci = _czesci(tekst)
    uwagi = []
    if sum(len(c) for _, c in czesci) < len(tekst):
        uwagi.append(f"Dokument jest długi – model sprawdził pierwsze "
                     f"{LLM_FRAGMENT_MAX * LLM_FRAGMENTY_MAX} znaków, dalej tylko wzorce.")
    wyniki = await asyncio.gather(*(_llm_czesc(p, c) for p, c in czesci), return_exceptions=True)
    out = []
    for w in wyniki:
        if isinstance(w, BaseException):
            log.warning("Anonimizacja przez LLM nieudana: %s", w)
            uwagi.append("Część tekstu nie została sprawdzona przez model – sprawdź ją ręcznie.")
        else:
            out.extend(w)
    return out, list(dict.fromkeys(uwagi))


def llm_wlaczony() -> bool:
    return settings.anonimizacja.llm and not llm_client.is_echo_mode()


# ---------- całość ----------
PRIORYTET = {"WZORZEC": 0, "SPRAWA": 1, "LLM": 2}  # przy równych zakresach wygrywa pewniejsze


def _scal(tekst: str, trafienia: list[_Traf]) -> list[Fragment]:
    trafienia.sort(key=lambda t: (t.start, -(t.end - t.start), PRIORYTET[t.zrodlo]))
    wynik: list[Fragment] = []
    for t in trafienia:
        if t.end <= t.start or (wynik and t.start < wynik[-1].end):
            continue
        wynik.append(Fragment(start=t.start, end=t.end, kategoria=t.kategoria,
                              etykieta=KATEGORIE[t.kategoria], tekst=tekst[t.start:t.end],
                              zrodlo=t.zrodlo, powod=t.powod))
    return wynik


ZASLONA = "█████"  # jak frontend/src/lib/anonimizacja.js – stała długość nie zdradza zamazanego tekstu
# Identyfikatory, których nie da się uzasadnić w dokumencie udostępnianym publicznie – serwer odrzuca
# zapis tekstu, w którym zostały niezamazane (ostatnia linia obrony, gdy anonimizacja we froncie zawiedzie).
BLOKUJACE = ("PESEL", "DOWOD")


def niezamazane_identyfikatory(tekst: str) -> list[str]:
    return sorted({KATEGORIE[t.kategoria] for t in _wzorce(tekst) if t.kategoria in BLOKUJACE})


def zamaz_automatycznie(tekst: str, wnioskodawca: str | None = None) -> str:
    """Zamazuje wszystko, co wykryją wzorce i wnioskodawca sprawy – bez LLM i bez decyzji urzędnika.
    Tylko dla importu archiwum (materiały testowe UMB); w aplikacji decyduje urzędnik."""
    out, poz = [], 0
    for f in _scal(tekst, _wzorce(tekst) + _wnioskodawca(tekst, wnioskodawca)):
        out += [tekst[poz:f.start], ZASLONA]
        poz = f.end
    return "".join(out) + tekst[poz:]


async def zaproponuj(tekst: str, wnioskodawca: str | None = None, llm: bool = True) -> Propozycje:
    trafienia = _wzorce(tekst) + _wnioskodawca(tekst, wnioskodawca)
    uwagi: list[str] = []
    uzyty = llm and llm_wlaczony() and bool(tekst.strip())
    if uzyty:
        z_llm, uwagi = await _llm(tekst)
        trafienia += z_llm
    elif llm and tekst.strip():
        uwagi.append("Model językowy niedostępny – propozycje tylko z wzorców. Imiona, nazwiska "
                     "i dane wrażliwe zaznacz ręcznie.")
    return Propozycje(fragmenty=_scal(tekst, trafienia), llm_uzyty=uzyty, uwagi=uwagi)
