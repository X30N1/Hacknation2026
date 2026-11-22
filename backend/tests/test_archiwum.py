from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.routers import sprawy as sprawy_router
from app.seed import DOMYSLNY_XLSX, PISMA, PODSTAWY
from app.sprawy import ekstrakcja, import_archiwum, importer
from app.sprawy.model import Metoda
from main import app

DZIS = date(2026, 11, 21)
app.dependency_overrides[sprawy_router.dzis] = lambda: DZIS
client = TestClient(app)


def sprawa(nr, przedmiot, wplyw="2026-11-10"):
    r = client.post("/sprawy", json={"znak": f"BKS.IV.1431.{nr}.2026", "data_wplywu": wplyw,
                                     "przedmiot": przedmiot, "wnioskodawca": "Jan Testowy"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def dokument(sid, tekst, rodzaj="WNIOSEK", wydzial=None):
    r = client.post(f"/sprawy/{sid}/dokumenty", data={"rodzaj": rodzaj, "wydzial": wydzial or ""},
                    files={"plik": ("d.txt", tekst.encode())})
    assert r.status_code == 201, r.text
    return r.json()


def test_podobne_sprawy_i_wydzialy_z_archiwum():
    stara = sprawa(1, "Koszty zimowego utrzymania ulic w 2025 roku", "2026-01-05")
    client.post(f"/sprawy/{stara}/zdarzenia", json={"typ": "PRZEKAZANIE", "data": "2026-01-06",
                                                    "payload": {"wydzialy": ["WGK"]}})
    dokument(stara, "Koszt odśnieżania ulic wyniósł 3 mln zł.", "ODP_WYDZIALU", "WGK")
    sprawa(2, "Liczba uczniów w szkołach podstawowych", "2026-02-01")
    nowa = sprawa(3, "Proszę o koszty odśnieżania i zimowego utrzymania ulic")

    podobne = client.get(f"/sprawy/{nowa}/podobne").json()
    assert podobne[0]["id"] == stara and podobne[0]["wydzialy"] == ["WGK"]
    assert "[" in podobne[0]["fragment"]
    assert all(p["id"] != nowa for p in podobne)

    s = client.get(f"/sprawy/{nowa}/wydzialy").json()
    assert s["sugestie"][0]["skrot"] == "WGK" and s["sugestie"][0]["zrodlo"] == "ARCHIWUM"
    assert "BKS.IV.1431.1.2026" in s["sugestie"][0]["uzasadnienie"]
    assert {"skrot": "WE", "nazwa": "Wydział Edukacji i Sportu"} in s["wszystkie"]


def test_wydzialy_ze_slow_kluczowych():
    sid = sprawa(5, "Lista szkół i liczba nauczycieli w przedszkolach")
    s = client.get(f"/sprawy/{sid}/wydzialy").json()["sugestie"]
    assert s[0]["skrot"] == "WE" and s[0]["zrodlo"] == "SLOWA_KLUCZOWE"
    assert all(x["skrot"] != "BKS" for x in s)


def test_wyszukiwarka_i_baza_wiedzy():
    sid = sprawa(1, "Dotacje dla organizacji pozarządowych")
    dokument(sid, "Wykaz dotacji udzielonych fundacjom w 2025 roku.", "ODPOWIEDZ")
    r = client.post("/wiedza", data={"rodzaj": "ustawa"},
                    files={"plik": ("udip.txt", "Art. 13. Udostępnienie informacji publicznej "
                                    "następuje bez zbędnej zwłoki, nie później niż w terminie 14 dni.".encode())})
    assert r.status_code == 201 and r.json()["sprawa_id"] is None and r.json()["rodzaj"] == "USTAWA"
    wid = r.json()["id"]
    assert client.post("/wiedza", data={"rodzaj": "nieznany"},
                       files={"plik": ("a.txt", b"abc")}).status_code == 422

    trafienia = client.get("/archiwum/szukaj", params={"q": "dotacje fundacje"}).json()
    assert {t["rodzaj"] for t in trafienia} >= {"SPRAWA", "ODPOWIEDZ"}
    assert client.get("/archiwum/szukaj", params={"q": "terminie zwłoki"}).json()[0]["dokument_id"] == wid

    assert [w["nazwa_pliku"] for w in client.get("/wiedza").json()] == ["udip.txt"]
    doc = client.get(f"/wiedza/{wid}").json()
    assert doc["tekst"].startswith("Art. 13.") and doc["rodzaj"] == "USTAWA"
    odp = client.get(f"/sprawy/{sid}").json()["dokumenty"][0]["id"]
    assert client.get(f"/wiedza/{odp}").status_code == 404  # dokument sprawy to nie baza wiedzy
    assert client.delete(f"/wiedza/{wid}").status_code == 204
    assert client.get("/wiedza").json() == []
    assert client.get(f"/wiedza/{wid}").status_code == 404
    assert client.delete(f"/wiedza/{wid}").status_code == 404
    assert client.get("/archiwum/szukaj", params={"q": "terminie zwłoki"}).json() == []


def test_drafty_pism_z_szablonu():
    sid = sprawa(11, "Wykaz dotacji dla fundacji")
    dokument(sid, "Wnoszę o wykaz dotacji udzielonych fundacjom w 2025 r.")
    draft = lambda **b: client.post(f"/sprawy/{sid}/draft", json=b)  # noqa: E731

    w = draft(rodzaj="WEZWANIE").json()
    assert w["tekst"].startswith("PROJEKT – wymaga weryfikacji urzędnika") and "Jan Testowy" in w["tekst"]
    assert "doprecyzowanie" in w["tekst"] and "7 dni" in w["tekst"] and w["llm_uzyty"] is False
    assert any("Wniosek" in z for z in w["zrodla"])

    p = draft(rodzaj="PRZEKAZANIE", wydzialy=["wgk"]).json()["tekst"]
    assert "Do:" in p and "Jan Testowy" not in p  # pismo wewnętrzne – bez danych wnioskodawcy
    assert "termin ustawowy" in p
    assert any("Nie wskazano wydziałów" in u for u in draft(rodzaj="PRZEKAZANIE").json()["uwagi"])

    k = draft(rodzaj="PRZEDLUZENIE", nowy_termin="2027-01-09").json()["tekst"]
    assert "art. 13 ust. 2" in k and "09.01.2027" in k

    assert "brak wgranych odpowiedzi" in draft(rodzaj="ODPOWIEDZ").json()["tekst"]
    assert draft(rodzaj="NIEZNANY").status_code == 422
    assert client.get(f"/sprawy/{sid}").json()["status"] == "NOWY"  # draft niczego nie zapisuje


def test_anulowanie_draftu_przerywa_generacje():
    import asyncio

    from app.routers.archiwum import do_rozlaczenia
    from fastapi import HTTPException

    class Rozlaczony:
        async def is_disconnected(self):
            return True

    przerwana = []

    async def dlugo():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            przerwana.append(True)
            raise

    async def test():
        try:
            await do_rozlaczenia(Rozlaczony(), dlugo(), co=0.01)
        except HTTPException as exc:
            return exc.status_code

    assert asyncio.run(test()) == 499 and przerwana == [True]


def test_baza_wiedzy_bez_anonimizacji():
    tekst = "Archiwalne pismo do Jana Kowalskiego, PESEL 44051401359."
    r = client.post("/wiedza", data={"rodzaj": "ARCHIWUM"}, files={"plik": ("pismo.txt", tekst.encode())})
    assert r.status_code == 201 and client.get(f"/wiedza/{r.json()['id']}").json()["tekst"] == tekst
    # dokumenty spraw nadal tylko po anonimizacji
    sid = sprawa(9, "Test")
    assert client.post(f"/sprawy/{sid}/dokumenty", data={"rodzaj": "WNIOSEK"},
                       files={"plik": ("d.txt", tekst.encode())}).status_code == 422


def test_seed_bazy_wiedzy_bez_anonimizacji(tmp_path):
    from app.sprawy import import_archiwum
    tekst = "Zarządzenie nr 535/2024 Prezydenta Miasta Bydgoszczy – Jan Kowalski, tel. 501 234 567."
    (tmp_path / "Zarządzenie test.txt").write_text(tekst)
    assert import_archiwum.importuj_wiedze(tmp_path) == (1, 0)
    assert client.get(f"/wiedza/{client.get('/wiedza').json()[0]['id']}").json()["tekst"] == tekst


def test_projekt_odpowiedzi_z_szablonu_i_docx():
    sid = sprawa(7, "Koszt organizacji Dni Bydgoszczy")
    client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": "PRZEKAZANIE", "data": "2026-11-11",
                                                  "payload": {"wydzialy": ["BKB"]}})
    dokument(sid, "Koszt organizacji wyniósł 1 200 000 zł brutto.", "ODP_WYDZIALU", "BKB")
    p = client.post(f"/sprawy/{sid}/draft", json={"rodzaj": "ODPOWIEDZ"}).json()
    assert p["llm_uzyty"] is False  # testy: tryb echo – szablon
    t = p["tekst"]
    assert t.startswith("PROJEKT – wymaga weryfikacji urzędnika")
    assert "BKS.IV.1431.7.2026" in t and "Jan Testowy" in t and "10.11.2026" in t
    assert "Biuro Kultury Bydgoskiej przekazał" in t and "1 200 000 zł" in t
    assert any("BKB" in z for z in p["zrodla"])
    assert client.get(f"/sprawy/{sid}").json()["status"] == "W_WYDZIALACH"  # projekt niczego nie zapisuje

    d = dokument(sid, t.replace("Jan Testowy", "█████"), "PROJEKT")
    r = client.get(f"/dokumenty/{d['id']}/docx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert "attachment" in r.headers["content-disposition"]

    bez = sprawa(8, "Coś")
    assert "brak wgranych odpowiedzi" in client.post(f"/sprawy/{bez}/draft", json={"rodzaj": "ODPOWIEDZ"}).json()["tekst"]


def test_seed_nie_zapisuje_nieudanego_ocr(monkeypatch, tmp_path):
    """OCR nic nie odczytał (np. brak tesseract) -> pismo pominięte i ponowione w kolejnym seedzie."""
    (tmp_path / "Wniosek - skan.pdf").write_bytes(b"%PDF")
    wyniki = iter([ekstrakcja.Odczyt("", Metoda.OCR, 0.0),
                   ekstrakcja.Odczyt("Odczytany wniosek", Metoda.OCR, None)])
    monkeypatch.setattr(ekstrakcja, "odczytaj", lambda *_: next(wyniki))
    assert import_archiwum.importuj_pisma(tmp_path) == (0, 1)
    assert import_archiwum.importuj_pisma(tmp_path) == (1, 0)


@pytest.mark.skipif(not (DOMYSLNY_XLSX.exists() and PISMA.is_dir()), reason="brak paczki UMB")
def test_import_archiwum_umb(monkeypatch):
    monkeypatch.setattr(ekstrakcja, "ocr_dostepny", lambda: False)  # szybko: skany pomijane
    importer.importuj(DOMYSLNY_XLSX)
    nowe, _ = import_archiwum.importuj_pisma(PISMA)
    assert nowe > 0
    assert import_archiwum.importuj_pisma(PISMA)[0] == 0  # idempotentny
    import_archiwum.importuj_wiedze(PODSTAWY)

    sprawy = {s["znak"]: s["id"] for s in client.get("/sprawy").json()}
    docs = client.get(f"/sprawy/{sprawy['BKS.IV.1431.15.2026']}").json()["dokumenty"]
    assert {d["rodzaj"] for d in docs} >= {"WNIOSEK"}
    assert all(d["nazwa_pliku"].endswith(".txt") for d in docs)
    assert any(w["rodzaj"] == "USTAWA" for w in client.get("/wiedza").json())
    assert client.get("/archiwum/szukaj", params={"q": "zwierząt"}).json()


def test_fts_query_stems_and_drops_stopwords():
    from app.sprawy.archiwum import fts_query

    assert fts_query("czy jest umowa?") == '"umowa"*'
    assert fts_query("oświetlenia ulicznego") == '"oświe"* OR "ulicz"*'
    assert fts_query("a i o") is None
