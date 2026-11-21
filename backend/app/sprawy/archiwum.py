"""Archiwum: podobne sprawy, wyszukiwarka i baza wiedzy (ustawy, zarządzenia, archiwalne pisma).

Wyszukiwanie pełnotekstowe SQLite FTS5 (tabele sprawy_fts, dokumenty_fts – app/storage.py)
z prostym „stemmingiem” przez prefiksy słów (app/rag.fts_query). Dwa rankingi – po przedmiocie
sprawy i po treści dokumentów – łączone przez Reciprocal Rank Fusion. Działa lokalnie, bez modelu
językowego. Przeszukiwane są wyłącznie zanonimizowane teksty (oryginały nie trafiają do bazy).
"""
import json
import math
import re
import unicodedata
from datetime import date
from pathlib import Path

from app.rag import fts_query
from app.sprawy import repo
from app.sprawy.model import (
    RODZAJE_WIEDZY, PodobnaSprawa, TrafienieArchiwum, WiedzaDokument,
)
from app.storage import store

RRF_K = 60
KANDYDACI = 100          # ile trafień z każdej tabeli przed fuzją
ZAPYTANIE_ZNAKI = 3000   # TODO: limit – ile znaków wniosku buduje zapytanie o podobne sprawy
ZAPYTANIE_SLOWA = 40     # TODO: limit – maks. słów w zapytaniu FTS
PROG_POKRYCIA = 0.5      # TODO: do strojenia na większym archiwum – min. część wagi słów przedmiotu


# Słowa obecne w prawie każdym piśmie UDIP – nie mówią, czego dotyczy sprawa (prefiksy jak w fts_query).
FORMULKI = {
    "wnios", "udost", "infor", "publi", "dostę", "trybi", "ustaw", "wrześ", "proszę", "prosz", "uprze",
    "szano", "państ", "panst", "witam", "dzień", "dobry", "pozdr", "poważ", "powaz", "dział", "dzial",
    "zwrac", "zwraca", "odpow", "bydgo", "miast", "urzęd", "urzad", "biuro", "komun", "społe", "spole",
    "prezy", "przes", "otrzy", "udzie", "niniej", "nini", "uzasa", "wskaz", "zakre", "dotyc", "pisma",
    "pismo", "adres", "email", "mail", "ulica", "dnia", "roku", "kopia", "załąc", "zalac", "podst",
    "gminy", "gmina", "gmin", "bieżą", "bieza", "aktua", "lista", "wykaz", "zesta",
}


def _zapytanie(tekst: str) -> str | None:
    q = fts_query(tekst)
    if not q:
        return None
    terminy = [t for t in q.split(" OR ") if t.strip('"*') not in FORMULKI]
    return " OR ".join(terminy[:ZAPYTANIE_SLOWA]) or None


def _bez_ogonkow(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().replace("ł", "l"))
    return "".join(c for c in s if not unicodedata.combining(c))


def _terminy(q: str | None) -> list[str]:
    return [_bez_ogonkow(t.strip('"*')) for t in q.split(" OR ")] if q else []


def _slowa_sprawy(sid: int) -> set[str]:
    teksty = [_przedmiot(sid)] + [r["tekst"] for r in store.conn.execute(
        "SELECT tekst FROM dokumenty WHERE sprawa_id = ?", (sid,))]
    return set(re.findall(r"\w+", _bez_ogonkow(" ".join(teksty))))


def _idf(termin: str) -> float:
    """Waga słowa: ln(N / liczba spraw, w których występuje) – w przedmiocie lub dokumentach."""
    (n,) = store.conn.execute("SELECT COUNT(*) FROM sprawy").fetchone()
    q = f'"{termin}"*'
    (df,) = store.conn.execute(
        "SELECT COUNT(*) FROM (SELECT rowid FROM sprawy_fts WHERE sprawy_fts MATCH ?"
        " UNION SELECT d.sprawa_id FROM dokumenty_fts JOIN dokumenty d ON d.id = dokumenty_fts.rowid"
        " WHERE dokumenty_fts MATCH ? AND d.sprawa_id IS NOT NULL)", (q, q),
    ).fetchone()
    return math.log((n + 1) / (df + 1)) + 0.1


def _rrf(*rankingi: list[int]) -> list[int]:
    wynik: dict[int, float] = {}
    for ranking in rankingi:
        for poz, k in enumerate(ranking):
            wynik[k] = wynik.get(k, 0.0) + 1.0 / (RRF_K + poz + 1)
    return [k for k, _ in sorted(wynik.items(), key=lambda x: x[1], reverse=True)]


def wydzialy_spraw(ids: list[int]) -> dict[int, list[str]]:
    """Wydziały, do których sprawę przekazano lub które odpowiedziały (zdarzenia + dokumenty)."""
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    out: dict[int, list[str]] = {i: [] for i in ids}

    def dodaj(sid, w):
        w = (w or "").strip().upper()
        if w and w not in out[sid]:
            out[sid].append(w)

    for r in store.conn.execute(
        f"SELECT sprawa_id, payload FROM zdarzenia WHERE sprawa_id IN ({q})"
        " AND typ IN ('PRZEKAZANIE', 'ODP_WYDZIALU') ORDER BY data, id", ids,
    ):
        p = json.loads(r["payload"] or "{}")
        for w in p.get("wydzialy") or []:
            dodaj(r["sprawa_id"], w)
        dodaj(r["sprawa_id"], p.get("wydzial"))
    for r in store.conn.execute(
        f"SELECT sprawa_id, wydzial FROM dokumenty WHERE sprawa_id IN ({q}) AND wydzial IS NOT NULL", ids,
    ):
        dodaj(r["sprawa_id"], r["wydzial"])
    return out


def _przedmiot(sid: int) -> str:
    w = store.conn.execute("SELECT przedmiot FROM sprawy WHERE id = ?", (sid,)).fetchone()
    return w["przedmiot"] if w else ""


def tekst_sprawy(sid: int) -> str:
    """Przedmiot sprawy + początek wniosku – podstawa zapytania o podobne sprawy."""
    wnioski = store.conn.execute(
        "SELECT tekst FROM dokumenty WHERE sprawa_id = ? AND rodzaj = 'WNIOSEK' ORDER BY id", (sid,)
    ).fetchall()
    tekst = " ".join([_przedmiot(sid)] + [r["tekst"] for r in wnioski])
    return tekst.replace("█", " ")[:ZAPYTANIE_ZNAKI]


def _sprawy_fts(q: str, sid: int) -> list[tuple[int, str]]:
    return [(r["id"], r["frag"]) for r in store.conn.execute(
        "SELECT rowid AS id, snippet(sprawy_fts, 0, '[', ']', '…', 14) AS frag FROM sprawy_fts"
        " WHERE sprawy_fts MATCH ? AND rowid != ? ORDER BY bm25(sprawy_fts) LIMIT ?",
        (q, sid, KANDYDACI))]


def _dokumenty_fts(q: str, sid: int) -> list[tuple[int, str]]:
    """Najlepsze trafienie na sprawę (pierwsze w kolejności bm25)."""
    out: dict[int, str] = {}
    for r in store.conn.execute(
        "SELECT d.sprawa_id AS id, snippet(dokumenty_fts, 0, '[', ']', '…', 18) AS frag"
        " FROM dokumenty_fts JOIN dokumenty d ON d.id = dokumenty_fts.rowid"
        " WHERE dokumenty_fts MATCH ? AND d.sprawa_id IS NOT NULL AND d.sprawa_id != ?"
        " ORDER BY bm25(dokumenty_fts) LIMIT ?",
        (q, sid, KANDYDACI),
    ):
        out.setdefault(r["id"], r["frag"])
    return list(out.items())


def podobne(sid: int, dzis: date, limit: int = 5) -> list[PodobnaSprawa]:
    # Przedmiot (krótki opis nadany przez urzędnika) jest najczystszym sygnałem – ma dwa rankingi;
    # pełna treść wniosku dochodzi jako trzeci (dużo słów, więcej szumu).
    q_przedmiot = _zapytanie(_przedmiot(sid))
    q_pelny = _zapytanie(tekst_sprawy(sid))
    if not (q_przedmiot or q_pelny):
        return []
    fragmenty: dict[int, str] = {}

    def ranking(q, szukaj_w) -> list[int]:
        if not q:
            return []
        trafienia = szukaj_w(q, sid)
        for i, frag in trafienia:
            fragmenty.setdefault(i, frag)
        return [i for i, _ in trafienia]

    kolejnosc = _rrf(ranking(q_przedmiot, _sprawy_fts), ranking(q_przedmiot, _dokumenty_fts),
                     ranking(q_pelny, _dokumenty_fts))
    # Próg trafności: zapytanie OR trafia w niemal każdy długi dokument, więc kandydatów z FTS
    # oceniamy pokryciem: jaka część wagi słów przedmiotu (IDF – rzadkie słowa ważą więcej) występuje
    # w przedmiocie lub dokumentach kandydata. Pojedyncze ogólne słowo („liczba”, „koszt”) nie wystarcza.
    idf_cache: dict[str, float] = {}

    def pokryj(q: str | None, slowa: set[str]) -> float:
        wagi = {t: idf_cache.setdefault(t, _idf(t)) for t in _terminy(q)[:ZAPYTANIE_SLOWA]}
        suma = sum(wagi.values())
        return sum(w for t, w in wagi.items() if any(s.startswith(t) for s in slowa)) / suma if suma else 0.0

    moje_slowa = _slowa_sprawy(sid)
    pokrycie = {}
    for i in kolejnosc:
        # w obie strony: krótki przedmiot („Kompleks Astoria”) i długi („Dokumentacja basenu Astorii…”)
        pokrycie[i] = max(pokryj(q_przedmiot or q_pelny, _slowa_sprawy(i)),
                          pokryj(_zapytanie(_przedmiot(i)), moje_slowa))
    ids = sorted((i for i in kolejnosc if pokrycie[i] >= PROG_POKRYCIA),
                 key=lambda i: -pokrycie[i])[:limit]
    wydzialy = wydzialy_spraw(ids)
    z_odpowiedzia = {
        r["sprawa_id"] for r in store.conn.execute(
            f"SELECT DISTINCT sprawa_id FROM dokumenty WHERE rodzaj IN ('ODPOWIEDZ', 'PROJEKT')"
            f" AND sprawa_id IN ({','.join('?' * len(ids))})", ids,
        )
    } if ids else set()
    wynik = []
    for i in ids:
        s = repo.sprawa(i, dzis)
        if s is None:
            continue
        wynik.append(PodobnaSprawa(
            id=s.id, znak=s.znak, przedmiot=s.przedmiot, data_wplywu=s.data_wplywu, status=s.status,
            wydzialy=wydzialy.get(i, []), fragment=fragmenty.get(i, ""), ma_odpowiedz=i in z_odpowiedzia,
        ))
    return wynik


def odpowiedzi_podobnych(sid: int, dzis: date, limit: int = 2) -> list[tuple[str, str]]:
    """(znak, tekst) odpowiedzi z najbardziej podobnych spraw – wzór stylu dla projektu pisma."""
    out = []
    for p in podobne(sid, dzis, limit=6):
        r = store.conn.execute(
            "SELECT tekst FROM dokumenty WHERE sprawa_id = ? AND rodzaj IN ('ODPOWIEDZ', 'PROJEKT')"
            " ORDER BY id DESC LIMIT 1", (p.id,),
        ).fetchone()
        if r and r["tekst"].strip():
            out.append((p.znak, r["tekst"]))
        if len(out) >= limit:
            break
    return out


def szukaj(fraza: str, limit: int = 30) -> list[TrafienieArchiwum]:
    q = _zapytanie(fraza)
    if not q:
        return []
    sprawy = store.conn.execute(
        "SELECT s.id, s.znak, s.data_wplywu, snippet(sprawy_fts, 0, '[', ']', '…', 14) AS frag"
        " FROM sprawy_fts JOIN sprawy s ON s.id = sprawy_fts.rowid"
        " WHERE sprawy_fts MATCH ? ORDER BY bm25(sprawy_fts) LIMIT ?", (q, KANDYDACI),
    ).fetchall()
    dokumenty = store.conn.execute(
        "SELECT d.id, d.sprawa_id, d.nazwa_pliku, d.rodzaj, s.znak, s.data_wplywu,"
        " snippet(dokumenty_fts, 0, '[', ']', '…', 18) AS frag"
        " FROM dokumenty_fts JOIN dokumenty d ON d.id = dokumenty_fts.rowid"
        " LEFT JOIN sprawy s ON s.id = d.sprawa_id"
        " WHERE dokumenty_fts MATCH ? AND (d.sprawa_id IS NOT NULL OR d.rodzaj IN ({}))"
        " ORDER BY bm25(dokumenty_fts) LIMIT ?".format(",".join("?" * len(RODZAJE_WIEDZY))),
        (q, *RODZAJE_WIEDZY, KANDYDACI),
    ).fetchall()
    trafienia = {("s", r["id"]): TrafienieArchiwum(
        sprawa_id=r["id"], znak=r["znak"], dokument_id=None, nazwa_pliku=None, rodzaj="SPRAWA",
        data=r["data_wplywu"], fragment=r["frag"]) for r in sprawy}
    trafienia |= {("d", r["id"]): TrafienieArchiwum(
        sprawa_id=r["sprawa_id"], znak=r["znak"], dokument_id=r["id"], nazwa_pliku=r["nazwa_pliku"],
        rodzaj=r["rodzaj"], data=r["data_wplywu"], fragment=r["frag"]) for r in dokumenty}
    kolejnosc = _rrf([("s", r["id"]) for r in sprawy], [("d", r["id"]) for r in dokumenty])
    return [trafienia[k] for k in kolejnosc[:limit]]


def fragmenty_wiedzy(tekst: str, limit: int = 3, znaki: int = 1500) -> list[tuple[str, str]]:
    """(nazwa pliku, fragment) z bazy wiedzy pasujące do tekstu – podstawy prawne do projektu."""
    q = _zapytanie(tekst)
    if not q:
        return []
    rows = store.conn.execute(
        "SELECT d.nazwa_pliku, snippet(dokumenty_fts, 0, '', '', '…', 64) AS frag"
        " FROM dokumenty_fts JOIN dokumenty d ON d.id = dokumenty_fts.rowid"
        " WHERE dokumenty_fts MATCH ? AND d.sprawa_id IS NULL AND d.rodzaj IN ('USTAWA', 'ZARZADZENIE')"
        " ORDER BY bm25(dokumenty_fts) LIMIT ?", (q, limit),
    ).fetchall()
    return [(r["nazwa_pliku"], r["frag"][:znaki]) for r in rows]


# ---------- baza wiedzy ----------
def lista_wiedzy() -> list[WiedzaDokument]:
    rows = store.conn.execute(
        "SELECT id, rodzaj, nazwa_pliku, length(tekst) AS znaki, utworzono FROM dokumenty"
        " WHERE sprawa_id IS NULL AND rodzaj IN ({}) ORDER BY rodzaj, nazwa_pliku".format(
            ",".join("?" * len(RODZAJE_WIEDZY))), tuple(RODZAJE_WIEDZY),
    ).fetchall()
    return [WiedzaDokument(**dict(r)) for r in rows]


def usun_wiedze(did: int) -> bool:
    r = store.conn.execute(
        "SELECT sciezka FROM dokumenty WHERE id = ? AND sprawa_id IS NULL AND rodzaj IN ({})".format(
            ",".join("?" * len(RODZAJE_WIEDZY))), (did, *RODZAJE_WIEDZY),
    ).fetchone()
    if r is None:
        return False
    with store.lock, store.conn:
        store.conn.execute("DELETE FROM dokumenty WHERE id = ?", (did,))
    if r["sciezka"]:
        Path(r["sciezka"]).unlink(missing_ok=True)
    return True
