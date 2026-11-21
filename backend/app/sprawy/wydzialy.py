"""Podpowiedź ścieżki: do których wydziałów / biur UM Bydgoszczy wysłać prośbę o odpowiedź.

Lista jednostek: BIP UM Bydgoszcz (https://bip.um.bydgoszcz.pl/artykuly/198/wydzialy,
https://bip.um.bydgoszcz.pl/artykuly/1158/biura), stan z 20.11.2026.

Trzy źródła propozycji (urzędnik zawsze wybiera sam):
1. ARCHIWUM – wydziały, które odpowiadały w podobnych sprawach (najmocniejsza przesłanka),
2. LLM – model wybiera z zamkniętej listy jednostek i uzasadnia (gdy dostępny),
3. SLOWA_KLUCZOWE – dopasowanie prefiksów słów do zakresu jednostki (działa zawsze, lokalnie).
Słowa kluczowe to heurystyka ułożona z nazw i typowego zakresu jednostek – do weryfikacji
z regulaminem organizacyjnym urzędu.
"""
import json
import logging
import re
from collections import Counter
from datetime import date

from app import llm_client
from app.sprawy import archiwum
from app.sprawy.model import SugestiaWydzialu, SugestieWydzialow

log = logging.getLogger(__name__)

MAKS_SUGESTII = 4
TEKST_DO_LLM_MAX = 4000  # TODO: limit – znaki wniosku wysyłane do LLM

# skrót: (nazwa z BIP, prefiksy słów kluczowych – małe litery)
JEDNOSTKI: dict[str, tuple[str, list[str]]] = {
    "WAB": ("Wydział Administracji Budowlanej",
            ["pozwoleni na budow", "pozwoleń na budow", "budowlan", "rozbiórk", "zabudow", "samowol"]),
    "WE": ("Wydział Edukacji i Sportu",
           ["szkoł", "szkol", "przedszkol", "uczni", "nauczyc", "oświat", "edukac", "sport", "boisk"]),
    "WF": ("Wydział Funduszy Europejskich", ["fundusz europejsk", "unijn", "dofinansowan", "środków ue"]),
    "WGO": ("Wydział Gospodarki Odpadami",
            ["odpad", "śmieci", "smieci", "recykl", "pszok", "segregac", "wywóz"]),
    "WI": ("Wydział Informatyki", ["informatyczn", "oprogramowan", "licencj", "sprzęt komputer", "serwer"]),
    "WIM": ("Wydział Inwestycji Miasta",
            ["inwestyc", "przebudow", "modernizac", "basen", "budowa ", "projekt zagospodarowan"]),
    "WK": ("Wydział Księgowości", ["księgow", "faktur", "płatnoś", "przelew"]),
    "WMG": ("Wydział Mienia i Geodezji",
            ["nieruchomoś", "grunt", "działk", "dzierżaw", "najem", "geodez", "pustostan", "zasobie gminy",
             "zasób gminy", "lokal"]),
    "WOŚ": ("Wydział Ochrony Środowiska",
            ["środowisk", "zwierz", "wycink", "hałas", "powietrz", "smog", "ekolog", "schronisk"]),
    "WOA": ("Wydział Organizacyjno-Administracyjny",
            ["zatrudnien", "etat", "kadr", "wynagrodze", "regulamin organizac", "samochod służbow"]),
    "WPL": ("Wydział Podatków i Opłat Lokalnych", ["podatk", "podatek", "opłat lokaln", "opłata targow", "ulg"]),
    "WSO": ("Wydział Spraw Obywatelskich",
            ["meldun", "ewidencj ludnoś", "liczba mieszkańc", "liczbę mieszkańc", "dowod", "zezwoleń na sprzedaż",
             "sprzedaży alkohol", "punktów sprzedaży"]),
    "WSR": ("Wydział Świadczeń Rodzinnych", ["świadczeń rodzin", "świadczenia rodzin", "zasiłk", "alimentac"]),
    "WUK": ("Wydział Uprawnień Komunikacyjnych",
            ["prawo jazdy", "prawa jazdy", "rejestracj pojazd", "rejestracji pojazd", "kierowc"]),
    "WW": ("Wydział Windykacji", ["windykac", "zaległoś", "dłużni", "egzekuc"]),
    "WZP": ("Wydział Zamówień Publicznych", ["przetarg", "zamówie", "zamówień", "wykonawc", "specyfikac"]),
    "WZB": ("Wydział Zarządzania Budżetem Miasta",
            ["budżet", "budzet", "dotacj", "wydatk", "dochod", "zadłużen", "kredyt"]),
    "WZK": ("Wydział Zarządzania Kryzysowego i Ochrony Ludności",
            ["kryzysow", "obrony cywiln", "schron", "ewakuac", "powodz", "ochrony ludnoś"]),
    "WGK": ("Wydział Zieleni i Gospodarki Komunalnej",
            ["zieleń", "zieleni", "park", "skwer", "drzew", "utrzymani", "odśnieżan", "zimow", "oczyszczan",
             "cmentarz", "fontann", "plac zabaw", "rond"]),
    "BAS": ("Biuro Aktywności Społecznej",
            ["organizacj pozarządow", "organizacji pozarządow", "stowarzysz", "fundacj", "budżet obywatel",
             "seniorów", "młodzież"]),
    "BCB": ("Biuro Cyfryzacji i Bezpieczeństwa Informacji",
            ["cyfryzac", "bezpieczeństwa informac", "ochrony danych", "cyberbezp"]),
    "BZS": ("Biuro ds. Zdrowia i Polityki Społecznej",
            ["zdrowi", "szpital", "przychodn", "pomocy społ", "niepełnospraw", "żłob", "uzależni",
             "profilaktyk"]),
    "BKS": ("Biuro Komunikacji Społecznej", ["konsultacj społ", "skarg"]),
    "BKZ": ("Biuro Konserwatora Zabytków", ["zabyt", "konserwator", "rzeźb", "pomnik", "elewac"]),
    "BKB": ("Biuro Kultury Bydgoskiej",
            ["kultur", "festiwal", "koncert", "imprez", "dni bydgoszcz", "teatr", "muze", "bibliot"]),
    "BPR": ("Biuro Prasowe", ["prasow", "rzecznik", "dziennikar"]),
    "BP": ("Biuro Promocji Miasta i Współpracy z Zagranicą",
           ["promocj", "reklam", "mediach społecznościow", "media społecznościow", "zagranic", "partnersk",
            "kampani"]),
    "BRM": ("Biuro Rady Miasta", ["rady miasta", "radn", "sesj", "interpelac"]),
    "BZIT": ("Biuro ZIT", ["zintegrowanych inwestycji terytorialn", " zit"]),
}
SKROTY = {k.upper(): k for k in JEDNOSTKI}


def wszystkie() -> list[dict[str, str]]:
    return [{"skrot": k, "nazwa": n} for k, (n, _) in JEDNOSTKI.items()]


def _norm(s: str) -> str:
    return " " + re.sub(r"\s+", " ", s.lower()) + " "


def ze_slow(tekst: str) -> list[SugestiaWydzialu]:
    t = _norm(tekst)
    wyniki = []
    for skrot, (nazwa, slowa) in JEDNOSTKI.items():
        trafione = [s.strip() for s in slowa if s in t]
        if trafione:
            wyniki.append((len(trafione), skrot, nazwa, trafione))
    wyniki.sort(key=lambda x: -x[0])
    return [SugestiaWydzialu(
        skrot=s, nazwa=n, zrodlo="SLOWA_KLUCZOWE",
        uzasadnienie="We wniosku: " + ", ".join(f"„{x}…”" for x in tr[:4]) + ".",
    ) for _, s, n, tr in wyniki]


def z_archiwum(sid: int, dzis: date) -> list[SugestiaWydzialu]:
    licznik: Counter = Counter()
    sprawy: dict[str, list[str]] = {}
    for poz, p in enumerate(archiwum.podobne(sid, dzis, limit=5)):
        for w in p.wydzialy:
            skrot = SKROTY.get(w.upper(), w.upper())
            licznik[skrot] += 5 - poz
            sprawy.setdefault(skrot, []).append(p.znak)
    out = []
    for skrot, _ in licznik.most_common():
        nazwa = JEDNOSTKI.get(skrot, (skrot, []))[0]
        znaki = sprawy[skrot]
        out.append(SugestiaWydzialu(
            skrot=skrot, nazwa=nazwa, zrodlo="ARCHIWUM",
            uzasadnienie=f"Odpowiadał w podobnych sprawach: {', '.join(znaki[:3])}.",
        ))
    return out


PROMPT = """\
Jesteś asystentem urzędnika Urzędu Miasta Bydgoszczy. Wskaż maksymalnie 3 jednostki urzędu, \
do których urzędnik powinien wysłać prośbę o przygotowanie odpowiedzi na wniosek o udostępnienie \
informacji publicznej. Wybieraj WYŁĄCZNIE z listy (skrót – nazwa):
{lista}

Uzasadnienie: jedno krótkie zdanie po polsku. Gdy nie masz pewności, zaznacz to w uzasadnieniu.
Zwróć WYŁĄCZNIE JSON: {{"wydzialy": [{{"skrot": "...", "uzasadnienie": "..."}}]}}

Wniosek:
{tekst}"""


async def z_llm(tekst: str) -> list[SugestiaWydzialu]:
    if llm_client.is_echo_mode() or not tekst.strip():
        return []
    lista = "\n".join(f"{k} – {n}" for k, (n, _) in JEDNOSTKI.items())
    try:
        odp = await llm_client.complete(
            [{"role": "user", "content": PROMPT.format(lista=lista, tekst=tekst[:TEKST_DO_LLM_MAX])}],
            temperature=0, response_format={"type": "json_object"},
        )
        m = re.search(r"\{.*\}", odp, re.S)
        dane = json.loads(m.group(0)) if m else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Sugestie wydziałów przez LLM nieudane: %s", exc)
        return []
    out = []
    for p in dane.get("wydzialy") or []:
        skrot = SKROTY.get(str(p.get("skrot", "")).strip().upper())
        if skrot:  # tylko jednostki z listy – model nie może wymyślić wydziału
            out.append(SugestiaWydzialu(skrot=skrot, nazwa=JEDNOSTKI[skrot][0], zrodlo="LLM",
                                        uzasadnienie=str(p.get("uzasadnienie") or "").strip()[:300]))
    return out


async def zaproponuj(sid: int, dzis: date) -> SugestieWydzialow:
    tekst = archiwum.tekst_sprawy(sid)
    kolejne = z_archiwum(sid, dzis) + await z_llm(tekst) + ze_slow(tekst)
    wybrane: list[SugestiaWydzialu] = []
    for s in kolejne:
        if s.skrot == "BKS":  # BKS prowadzi sprawę UDIP – nie wysyła prośby do siebie
            continue
        if all(x.skrot != s.skrot for x in wybrane):
            wybrane.append(s)
    return SugestieWydzialow(sugestie=wybrane[:MAKS_SUGESTII], wszystkie=wszystkie())
