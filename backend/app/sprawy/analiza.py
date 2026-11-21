"""Propozycja danych sprawy z treści wniosku (formularz „Zarejestruj wniosek”).
Z LLM, gdy dostępny; w przeciwnym razie prosta heurystyka. Urzędnik zawsze zatwierdza."""
import json
import logging
import re
from datetime import date

from app import llm_client
from app.sprawy import repo
from app.sprawy.model import ZNAK_W_TEKSCIE_RE, Propozycja

log = logging.getLogger(__name__)

PRZEDMIOT_PROPOZYCJA_MAX = 160  # TODO: limit – jak w frontend/src/api/mock.js
TEKST_DO_LLM_MAX = 6000         # TODO: limit – znaki wniosku wysyłane do LLM

PROMPT = """\
Z poniższego wniosku o udostępnienie informacji publicznej wyodrębnij:
- "wnioskodawca": imię i nazwisko lub nazwa wnioskodawcy (pusty napis, jeśli brak),
- "przedmiot": krótki opis, czego dotyczy wniosek (jedno zdanie, maks. 160 znaków).
Zwróć WYŁĄCZNIE obiekt JSON z tymi dwoma polami.

Wniosek:
{tekst}"""


# nagłówki i formułki, które nie mówią, czego dotyczy wniosek
POMIJANE = re.compile(
    r"^(wniosek( o udost\w+ informacji publicznej)?|szanown\w+.*|dzień dobry.*|witam.*|"
    r"biuro .*|wydzia[łl] .*|"
    r"(do\s+)?urz[ąa]d miasta.*|prezydent miasta.*|.*\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}.*|"
    r"dzia[łl]aj[ąa]c (we w[łl]asnym imieniu|na podstawie).*|w imieniu.{0,60})[\s,.:]*$",
    re.I,
)


def _pierwsza_linia(tekst: str) -> str:
    linie = [" ".join(x.split()) for x in tekst.splitlines()]
    linie = [x for x in linie if len(x) > 3]
    for linia in linie:
        if not POMIJANE.match(linia):
            return linia[:PRZEDMIOT_PROPOZYCJA_MAX]
    return (linie[0] if linie else "")[:PRZEDMIOT_PROPOZYCJA_MAX]


async def _z_llm(tekst: str) -> dict:
    if llm_client.is_echo_mode() or not tekst.strip():
        return {}
    try:
        odp = await llm_client.complete(
            [{"role": "user", "content": PROMPT.format(tekst=tekst[:TEKST_DO_LLM_MAX])}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        m = re.search(r"\{.*\}", odp, re.S)
        dane = json.loads(m.group(0)) if m else {}
        return {k: str(dane.get(k) or "").strip() for k in ("wnioskodawca", "przedmiot")}
    except Exception as exc:  # noqa: BLE001
        log.warning("Analiza wniosku przez LLM nieudana: %s", exc)
        return {}


async def zaproponuj(nazwa_pliku: str, tekst: str, dzis: date) -> Propozycja:
    znalezione = ZNAK_W_TEKSCIE_RE.search(nazwa_pliku) or ZNAK_W_TEKSCIE_RE.search(tekst)
    znak = znalezione.group(0) if znalezione else \
        f"BKS.IV.1431.{repo.nastepny_nr(dzis.year)}.{dzis.year}"
    llm = await _z_llm(tekst)
    return Propozycja(
        znak=znak,
        data_wplywu=dzis,
        wnioskodawca=llm.get("wnioskodawca", ""),
        przedmiot=(llm.get("przedmiot") or _pierwsza_linia(tekst))[:PRZEDMIOT_PROPOZYCJA_MAX],
    )
