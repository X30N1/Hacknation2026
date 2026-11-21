from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.routers import sprawy as sprawy_router
from app.seed import DOMYSLNY_XLSX, PISMA, PODSTAWY
from app.sprawy import ekstrakcja, import_archiwum, importer
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
    assert client.delete(f"/wiedza/{wid}").status_code == 204
    assert client.get("/wiedza").json() == []
    assert client.delete(f"/wiedza/{wid}").status_code == 404
    assert client.get("/archiwum/szukaj", params={"q": "terminie zwłoki"}).json() == []


def test_projekt_odpowiedzi_z_szablonu_i_docx():
    sid = sprawa(7, "Koszt organizacji Dni Bydgoszczy")
    client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": "PRZEKAZANIE", "data": "2026-11-11",
                                                  "payload": {"wydzialy": ["BKB"]}})
    dokument(sid, "Koszt organizacji wyniósł 1 200 000 zł brutto.", "ODP_WYDZIALU", "BKB")
    p = client.post(f"/sprawy/{sid}/projekt").json()
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
    assert "brak wgranych odpowiedzi" in client.post(f"/sprawy/{bez}/projekt").json()["tekst"]


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
