"""Dostęp do bazy dla spraw, zdarzeń i dokumentów (SQLite, app/storage.py)."""
import json
import re
from datetime import date, datetime
from pathlib import Path

from app.config import settings
from app.sprawy import terminy
from app.sprawy.model import (
    ZNAK_RE, Dokument, Flaga, Metoda, SprawaLista, SprawaSzczegoly, TypZdarzenia,
    Zdarzenie, Zrodlo,
)
from app.storage import store


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def _iso(v: date | None) -> str | None:
    return v.isoformat() if v else None


# ---------- sprawy ----------
def znak_istnieje(znak: str) -> bool:
    return store.conn.execute("SELECT 1 FROM sprawy WHERE znak = ?", (znak,)).fetchone() is not None


def nastepny_nr(rok: int) -> int:
    (n,) = store.conn.execute(
        "SELECT COALESCE(MAX(nr), 0) + 1 FROM sprawy WHERE rok = ?", (rok,)
    ).fetchone()
    return n


def utworz_sprawe(
    znak: str, data_wplywu: date, wnioskodawca: str = "", przedmiot: str = "",
    inicjaly: str | None = None, zrodlo: Zrodlo = Zrodlo.UPLOAD,
    flagi: list[Flaga] | None = None, import_termin: date | None = None,
    import_odpowiedz: date | None = None,
) -> int:
    m = ZNAK_RE.match(znak)
    nr, rok = int(m.group(1)), int(m.group(2))
    with store.lock, store.conn:
        cur = store.conn.execute(
            "INSERT INTO sprawy (znak, nr, rok, zrodlo, wnioskodawca, przedmiot, data_wplywu,"
            " inicjaly, flagi, import_termin, import_odpowiedz) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (znak, nr, rok, zrodlo.value, wnioskodawca, przedmiot, data_wplywu.isoformat(),
             inicjaly, json.dumps([f.model_dump() for f in flagi or []], ensure_ascii=False),
             _iso(import_termin), _iso(import_odpowiedz)),
        )
        sid = cur.lastrowid
        _insert_zdarzenie(sid, TypZdarzenia.REJESTRACJA, data_wplywu, None, {}, inicjaly)
    return sid


def edytuj_sprawe(sid: int, pola: dict) -> None:
    """pola ⊆ {znak, data_wplywu, wnioskodawca, przedmiot, inicjaly}. Zmiana znaku przelicza nr/rok,
    zmiana daty wpływu – datę zdarzenia REJESTRACJA (od niej liczy się termin)."""
    kolumny = {k: v for k, v in pola.items() if k in ("znak", "data_wplywu", "wnioskodawca", "przedmiot", "inicjaly")}
    if "znak" in kolumny:
        m = ZNAK_RE.match(kolumny["znak"])
        kolumny |= {"nr": int(m.group(1)), "rok": int(m.group(2))}
    if "data_wplywu" in kolumny:
        kolumny["data_wplywu"] = kolumny["data_wplywu"].isoformat()
    if not kolumny:
        return
    with store.lock, store.conn:
        store.conn.execute(f"UPDATE sprawy SET {', '.join(f'{k} = ?' for k in kolumny)} WHERE id = ?",
                           (*kolumny.values(), sid))
        if "data_wplywu" in kolumny:
            store.conn.execute("UPDATE zdarzenia SET data = ? WHERE sprawa_id = ? AND typ = 'REJESTRACJA'",
                               (kolumny["data_wplywu"], sid))


def _wiersz(sid: int):
    return store.conn.execute("SELECT * FROM sprawy WHERE id = ?", (sid,)).fetchone()


def zrodlo(sid: int) -> Zrodlo | None:
    w = _wiersz(sid)
    return Zrodlo(w["zrodlo"]) if w else None


def wnioskodawca(sid: int) -> str | None:
    w = _wiersz(sid)
    return w["wnioskodawca"] if w else None


# ---------- zdarzenia ----------
def _insert_zdarzenie(sid, typ, data, nowy_termin, payload, inicjaly) -> int:
    cur = store.conn.execute(
        "INSERT INTO zdarzenia (sprawa_id, typ, data, nowy_termin, payload, inicjaly)"
        " VALUES (?,?,?,?,?,?)",
        (sid, typ.value, data.isoformat(), _iso(nowy_termin),
         json.dumps(payload, ensure_ascii=False), inicjaly),
    )
    return cur.lastrowid


def dodaj_zdarzenie(sid: int, typ: TypZdarzenia, data: date, nowy_termin: date | None = None,
                    payload: dict | None = None, inicjaly: str | None = None) -> int:
    with store.lock, store.conn:
        return _insert_zdarzenie(sid, typ, data, nowy_termin, payload or {}, inicjaly)


def _zdarzenia(sprawa_ids: list[int] | None = None) -> dict[int, list[Zdarzenie]]:
    sql, args = "SELECT * FROM zdarzenia", ()
    if sprawa_ids is not None:
        sql += f" WHERE sprawa_id IN ({','.join('?' * len(sprawa_ids))})"
        args = tuple(sprawa_ids)
    wynik: dict[int, list[Zdarzenie]] = {}
    for r in store.conn.execute(sql + " ORDER BY data, id", args):
        wynik.setdefault(r["sprawa_id"], []).append(Zdarzenie(
            id=r["id"], typ=r["typ"], data=r["data"], nowy_termin=r["nowy_termin"],
            payload=json.loads(r["payload"] or "{}"), inicjaly=r["inicjaly"],
        ))
    return wynik


# ---------- widok sprawy ----------
def _lista(w, zdarzenia: list[Zdarzenie], dzis: date) -> SprawaLista:
    wynik = terminy.przelicz(
        data_wplywu=_d(w["data_wplywu"]), zdarzenia=zdarzenia, dzis=dzis,
        zrodlo=Zrodlo(w["zrodlo"]),
        flagi=[Flaga(**f) for f in json.loads(w["flagi"] or "[]")],
        import_termin=_d(w["import_termin"]), import_odpowiedz=_d(w["import_odpowiedz"]),
    )
    return SprawaLista(
        id=w["id"], znak=w["znak"], nr=w["nr"], rok=w["rok"], zrodlo=w["zrodlo"],
        wnioskodawca=w["wnioskodawca"], przedmiot=w["przedmiot"],
        data_wplywu=w["data_wplywu"], inicjaly=w["inicjaly"], **vars(wynik),
    )


def lista_spraw(dzis: date, rok: int | None = None, otwarte: bool = False) -> list[SprawaLista]:
    sql, args = "SELECT * FROM sprawy", ()
    if rok is not None:
        sql, args = sql + " WHERE rok = ?", (rok,)
    wiersze = store.conn.execute(sql, args).fetchall()
    zd = _zdarzenia()
    sprawy = [_lista(w, zd.get(w["id"], []), dzis) for w in wiersze]
    if otwarte:
        sprawy = [s for s in sprawy if s.pilnosc != "ZAMKNIETA"]
    return sorted(sprawy, key=lambda s: (s.data_wplywu, s.nr))


def sprawa(sid: int, dzis: date) -> SprawaSzczegoly | None:
    w = _wiersz(sid)
    if w is None:
        return None
    zd = _zdarzenia([sid]).get(sid, [])
    return SprawaSzczegoly(
        **_lista(w, zd, dzis).model_dump(), zdarzenia=zd, dokumenty=dokumenty_sprawy(sid)
    )


# ---------- dokumenty ----------
def katalog_plikow() -> Path:
    p = settings.pliki.resolved()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bezpieczna_nazwa(nazwa: str) -> str:
    nazwa = Path(nazwa).name
    return re.sub(r"[^\w.\- ]", "_", nazwa)[:150] or "plik"


def _dokument(r) -> Dokument:
    return Dokument(
        id=r["id"], sprawa_id=r["sprawa_id"], rodzaj=r["rodzaj"], nazwa_pliku=r["nazwa_pliku"],
        wydzial=r["wydzial"], metoda=r["metoda"], ocr_pewnosc=r["ocr_pewnosc"],
        tekst=r["tekst"],
    )


def zapisz_dokument(nazwa_pliku: str, dane: bytes, rodzaj: str, metoda: Metoda,
                    tekst: str, ocr_pewnosc: float | None, sprawa_id: int | None = None,
                    wydzial: str | None = None) -> Dokument:
    with store.lock, store.conn:
        cur = store.conn.execute(
            "INSERT INTO dokumenty (sprawa_id, rodzaj, nazwa_pliku, wydzial, metoda, ocr_pewnosc,"
            " tekst, sciezka, utworzono) VALUES (?,?,?,?,?,?,?,?,?)",
            (sprawa_id, rodzaj, nazwa_pliku, wydzial, metoda.value, ocr_pewnosc, tekst, "",
             datetime.now().isoformat()),
        )
        did = cur.lastrowid
        sciezka = katalog_plikow() / f"{did}_{_bezpieczna_nazwa(nazwa_pliku)}"
        sciezka.write_bytes(dane)
        store.conn.execute("UPDATE dokumenty SET sciezka = ? WHERE id = ?", (str(sciezka), did))
    return dokument(did)


def dokument(did: int) -> Dokument | None:
    r = store.conn.execute("SELECT * FROM dokumenty WHERE id = ?", (did,)).fetchone()
    return _dokument(r) if r else None


def dokumenty_sprawy(sid: int) -> list[Dokument]:
    rows = store.conn.execute(
        "SELECT * FROM dokumenty WHERE sprawa_id = ? ORDER BY id", (sid,)
    ).fetchall()
    return [_dokument(r) for r in rows]


def edytuj_dokument(did: int, pola: dict) -> None:
    """pola ⊆ {tekst, rodzaj, nazwa_pliku, wydzial}; nazwy kolumn z białej listy."""
    pola = {k: v for k, v in pola.items() if k in ("tekst", "rodzaj", "nazwa_pliku", "wydzial")}
    if not pola:
        return
    with store.lock, store.conn:
        store.conn.execute(f"UPDATE dokumenty SET {', '.join(f'{k} = ?' for k in pola)} WHERE id = ?",
                           (*pola.values(), did))


def usun_dokument(did: int) -> bool:
    r = store.conn.execute("SELECT sciezka FROM dokumenty WHERE id = ?", (did,)).fetchone()
    if r is None:
        return False
    with store.lock, store.conn:
        store.conn.execute("DELETE FROM dokumenty WHERE id = ?", (did,))
    if r["sciezka"]:
        Path(r["sciezka"]).unlink(missing_ok=True)
    return True
