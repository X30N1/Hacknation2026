import io
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.routers import sprawy as sprawy_router
from app.sprawy import ekstrakcja, importer
from app.seed import DOMYSLNY_XLSX
from main import app

DZIS = date(2026, 11, 21)
app.dependency_overrides[sprawy_router.dzis] = lambda: DZIS
client = TestClient(app)


def nowa(znak="BKS.IV.1431.100.2026", wplyw="2026-11-16", **kw):
    r = client.post("/sprawy", json={"znak": znak, "data_wplywu": wplyw, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def zdarzenie(sid, typ, data="2026-11-20", **kw):
    return client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": typ, "data": data, **kw})


def docx_bytes(*linie):
    import docx

    d = docx.Document()
    for t in linie:
        d.add_paragraph(t)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def pdf_z_tekstem(tekst: str) -> bytes:
    """Minimalny PDF z warstwą tekstową (Helvetica)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({tekst}) Tj ET".encode()
    obiekty = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(obiekty, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(obiekty) + 1)
    out += b"".join(b"%010d 00000 n \n" % x for x in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(obiekty) + 1, xref)
    return bytes(out)


# ---------- sprawy i zdarzenia ----------
def test_utworz_i_lista():
    s = nowa(wnioskodawca="Jan Testowy", przedmiot="Budżet", inicjaly="AK")
    assert s["termin"] == "2026-11-30" and s["status"] == "NOWY"
    assert s["pozostalo_dni"] == 9 and s["pilnosc"] == "BRAK"
    assert s["zdarzenia"][0]["typ"] == "REJESTRACJA" and s["dokumenty"] == []

    lista = client.get("/sprawy").json()
    assert len(lista) == 1 and "zdarzenia" not in lista[0]
    assert client.get("/sprawy?rok=2025").json() == []
    assert len(client.get("/sprawy?otwarte=1").json()) == 1


def test_bledy_w_formacie_frontendu():
    r = client.post("/sprawy", json={"znak": "zly", "data_wplywu": "2026-11-16"})
    assert r.status_code == 422
    assert r.json()["blad"] == "Niepoprawne dane. Numer sprawy musi mieć format BKS.IV.1431.<nr>.<rok>."
    nowa()
    r = client.post("/sprawy", json={"znak": "BKS.IV.1431.100.2026", "data_wplywu": "2026-11-16"})
    assert r.status_code == 409 and "już istnieje" in r.json()["blad"]
    assert client.get("/sprawy/999").json()["blad"] == "Nie znaleziono sprawy."
    assert client.get("/nie-ma").json()["blad"] == "Not Found"


def test_przeplyw_statusow():
    sid = nowa()["id"]
    assert zdarzenie(sid, "WYSLANO").status_code == 409  # nie ze statusu NOWY
    r = zdarzenie(sid, "PRZEKAZANIE", payload={"wydzialy": [" WGK ", ""]})
    assert r.status_code == 201 and r.json()["status"] == "W_WYDZIALACH"
    assert r.json()["zdarzenia"][-1]["payload"] == {"wydzialy": ["WGK"]}

    assert zdarzenie(sid, "PRZEDLUZENIE").status_code == 422  # brak nowego terminu
    s = zdarzenie(sid, "PRZEDLUZENIE", nowy_termin="2026-12-15", inicjaly="AK").json()
    assert (s["status"], s["termin"], s["przedluzenie_dni"]) == ("PRZEDLUZONA", "2026-12-15", 15)

    assert zdarzenie(sid, "PROJEKT").json()["status"] == "PROJEKT_GOTOWY"
    s = zdarzenie(sid, "WYSLANO", data="2026-11-21").json()
    assert (s["status"], s["pilnosc"], s["data_odpowiedzi"]) == ("WYSLANA", "ZAMKNIETA", "2026-11-21")
    assert zdarzenie(sid, "PROJEKT").status_code == 409


def test_walidacja_zdarzen():
    sid = nowa()["id"]
    assert zdarzenie(sid, "PRZEKAZANIE", payload={"wydzialy": []}).status_code == 422
    assert zdarzenie(sid, "PRZEKAZANIE", data="2026-11-01",
                     payload={"wydzialy": ["X"]}).status_code == 422  # przed wpływem
    assert zdarzenie(sid, "PRZEKAZANIE", data="2026-12-01",
                     payload={"wydzialy": ["X"]}).status_code == 422  # przyszłość
    assert zdarzenie(sid, "REJESTRACJA").status_code == 409
    assert zdarzenie(sid, "NIEZNANE").status_code == 422


def test_doprecyzowanie_i_bez_rozpoznania():
    sid = nowa(wplyw="2026-11-02")["id"]
    s = zdarzenie(sid, "WEZWANIE_DOPRECYZOWANIE", data="2026-11-03").json()
    assert s["termin_wstrzymany"] and s["termin"] is None
    assert any(f["kod"] == "DOPRECYZOWANIE_MINELO" for f in s["flagi"])
    assert zdarzenie(sid, "BEZ_ROZPOZNANIA").json()["status"] == "BEZ_ROZPOZNANIA"


# ---------- dokumenty ----------
def test_odczyt_wniosku_docx():
    plik = docx_bytes("Wniosek o udostępnienie informacji publicznej", "Proszę o wykaz dotacji.")
    r = client.post("/wnioski/odczyt", files={"plik": ("wniosek.docx", plik)})
    assert r.status_code == 200, r.text
    o, prop = r.json()["odczyt"], r.json()["propozycja"]
    assert o["metoda"] == "DOCX" and "wykaz dotacji" in o["tekst"]
    assert prop["znak"] == "BKS.IV.1431.1.2026" and prop["data_wplywu"] == "2026-11-21"
    assert prop["przedmiot"] == "Proszę o wykaz dotacji."  # nagłówek pominięty
    assert client.post("/wnioski/analiza", files={"plik": ("wniosek.docx", plik)}).status_code in (404, 405)
    r = client.post("/sprawy", json={"znak": "BKS.IV.1431.2.2026", "data_wplywu": "2026-11-21",
                                     "dokument_id": 1})
    assert r.status_code == 422  # przypinanie oryginału z bazy nie istnieje


def test_odczyt_znak_z_nazwy_pliku_i_txt_cp1250():
    tekst = "Proszę o informację – żółć".encode("cp1250")
    r = client.post("/wnioski/odczyt", files={"plik": ("Wniosek - BKS.IV.1431.599.2026.txt", tekst)})
    assert r.json()["propozycja"]["znak"] == "BKS.IV.1431.599.2026"
    assert r.json()["odczyt"]["tekst"] == "Proszę o informację – żółć"
    assert r.json()["odczyt"]["metoda"] == "RECZNA"


def test_pdf_warstwa_tekstowa_i_skan(monkeypatch):
    tekst = "Wniosek o udostepnienie informacji publicznej dotyczacej budzetu miasta"
    r = client.post("/dokumenty/odczyt", files={"plik": ("w.pdf", pdf_z_tekstem(tekst))}).json()
    assert r["metoda"] == "PDF_TEXT" and tekst in r["tekst"]

    monkeypatch.setattr(ekstrakcja, "ocr_dostepny", lambda: False)
    r = client.post("/dokumenty/odczyt", files={"plik": ("skan.pdf", pdf_z_tekstem(""))}).json()
    assert r["metoda"] == "OCR" and r["ocr_pewnosc"] == 0.0


def test_formaty_i_rozmiar(monkeypatch):
    from app.config import settings

    r = client.post("/dokumenty/odczyt", files={"plik": ("w.doc", b"x")})
    assert r.status_code == 415 and "PDF lub Word" in r.json()["blad"]
    assert client.post("/dokumenty/odczyt", files={"plik": ("w.docx", b"nie docx")}).status_code == 415
    monkeypatch.setattr(settings.pliki, "max_mb", 0.0001)
    assert client.post("/dokumenty/odczyt", files={"plik": ("w.txt", b"x" * 500)}).status_code == 413


@pytest.mark.usefixtures("jako_admin")
def test_serwer_odrzuca_niezamazany_pesel():
    sid = nowa()["id"]
    r = client.post(f"/sprawy/{sid}/dokumenty", data={"rodzaj": "ODPOWIEDZ"},
                    files={"plik": ("odp.txt", "Jan, PESEL 44051401359".encode())})
    assert r.status_code == 422 and "PESEL" in r.json()["blad"]
    d = client.post(f"/sprawy/{sid}/dokumenty", data={"rodzaj": "ODPOWIEDZ"},
                    files={"plik": ("odp.txt", "Jan, PESEL █████".encode())}).json()
    assert client.patch(f"/dokumenty/{d['id']}", json={"tekst": "dowód ABC123456"}).status_code == 422
    assert client.get(f"/sprawy/{sid}").json()["dokumenty"][0]["tekst"] == "Jan, PESEL █████"


def test_dokument_do_sprawy():
    sid = nowa()["id"]
    r = client.post(f"/sprawy/{sid}/dokumenty",
                    files={"plik": ("odp.docx", docx_bytes("Odpowiedź wydziału"))},
                    data={"rodzaj": "odp_wydzialu", "wydzial": "WGK"})
    assert r.status_code == 201
    assert (r.json()["rodzaj"], r.json()["wydzial"], r.json()["sprawa_id"]) == ("ODP_WYDZIALU", "WGK", sid)
    assert client.get(f"/sprawy/{sid}").json()["dokumenty"][0]["id"] == r.json()["id"]
    assert client.post("/sprawy/999/dokumenty", files={"plik": ("a.txt", b"a")}).status_code == 404


# ---------- import xlsx ----------
@pytest.mark.skipif(not DOMYSLNY_XLSX.exists(), reason="brak pliku xlsx z paczki UMB")
def test_import_xlsx_flagi():
    assert importer.importuj(DOMYSLNY_XLSX) == (10, 0)
    assert importer.importuj(DOMYSLNY_XLSX) == (0, 10)  # idempotentny

    sprawy = {s["znak"].removeprefix("BKS.IV.1431."): s for s in client.get("/sprawy").json()}
    kody = {k: {f["kod"] for f in s["flagi"]} for k, s in sprawy.items()}
    assert all(s["status"] == "WYSLANA" and s["pilnosc"] == "ZAMKNIETA" for s in sprawy.values())

    assert {"ODP_PRZED_WPLYWEM", "NUMERACJA_NIEZGODNA", "TERMIN_W_WEEKEND"} <= kody["15.2026"]
    assert kody["18.2026"] == {"ROK_TERMINU"}  # odp. 26.01 mieści się w poprawionym 29.01
    warianty = [f for f in sprawy["509.2026"]["flagi"] if f["kod"] == "WNIOSKODAWCA_WARIANTY"]
    assert len(warianty) == 1 and "307.2025" in warianty[0]["opis"] and "599.2026" in warianty[0]["opis"]
    assert "WNIOSKODAWCA_EMAIL" in kody["17.2026"]
    assert "TERMIN_TEKSTOWY" in kody["509.2026"] and sprawy["509.2026"]["termin"] == "2026-09-18"
    assert "ODP_PO_TERMINIE" in kody["543.2026"] and "ODP_PO_TERMINIE" in kody["590.2026"]
    assert sprawy["590.2026"]["termin"] == "2026-09-21"  # formuła =E11+14
    assert "WNIOSKODAWCA_WARIANTY" in kody["293.2025"] and "WNIOSKODAWCA_WARIANTY" in kody["509.2026"]
    assert kody["16.2026"] == set()

    sid = sprawy["509.2026"]["id"]
    assert [z["typ"] for z in client.get(f"/sprawy/{sid}").json()["zdarzenia"]] == \
        ["REJESTRACJA", "WEZWANIE_DOPRECYZOWANIE", "WYSLANO"]
    assert zdarzenie(sid, "PROJEKT").status_code == 409  # import zamknięty


def test_odczyt_bez_zapisu_i_zapis_zanonimizowanego():
    """Przepływ frontu: odczyt (nic nie trafia do bazy ani na dysk) → anonimizacja → zapis .txt."""
    from app.config import settings
    from app.storage import store

    def stan():
        n = store.conn.execute("SELECT COUNT(*) FROM dokumenty").fetchone()[0]
        katalog = settings.pliki.resolved()
        return n, sorted(katalog.iterdir()) if katalog.exists() else []

    przed = stan()
    plik = docx_bytes("Wniosek o udostępnienie informacji publicznej",
                      "Proszę o wykaz umów na odśnieżanie.", "Jan Kowalski, PESEL 44051401359")
    r = client.post("/wnioski/odczyt", files={"plik": ("BKS.IV.1431.301.2026.docx", plik)})
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["odczyt"]["nazwa_pliku"] == "BKS.IV.1431.301.2026.docx"
    assert o["odczyt"]["metoda"] == "DOCX" and "44051401359" in o["odczyt"]["tekst"]
    assert o["propozycja"]["znak"] == "BKS.IV.1431.301.2026"
    assert o["propozycja"]["przedmiot"] == "Proszę o wykaz umów na odśnieżanie."

    r = client.post("/dokumenty/odczyt", files={"plik": ("odp.txt", "Odpowiedź wydziału".encode())})
    assert r.json() == {"nazwa_pliku": "odp.txt", "metoda": "RECZNA", "ocr_pewnosc": None,
                        "tekst": "Odpowiedź wydziału"}
    assert client.post("/dokumenty/odczyt", files={"plik": ("x.exe", b"MZ")}).status_code == 415
    assert stan() == przed  # odczyt niczego nie zapisał

    # zapis: sprawa + wyłącznie zanonimizowany tekst
    s = nowa(znak=o["propozycja"]["znak"])
    tekst = o["odczyt"]["tekst"].replace("Jan Kowalski", "█████").replace("44051401359", "█████")
    d = client.post(f"/sprawy/{s['id']}/dokumenty", data={"rodzaj": "WNIOSEK"},
                    files={"plik": ("BKS.IV.1431.301.2026.txt", tekst.encode())}).json()
    assert d["tekst"] == tekst and "44051401359" not in d["tekst"]
    assert client.get(f"/sprawy/{s['id']}").json()["dokumenty"][0]["id"] == d["id"]


def test_dokumenty_edycja_i_usuwanie_tylko_admin(request):
    sid = nowa()["id"]
    d = client.post(f"/sprawy/{sid}/dokumenty", data={"rodzaj": "INNE"},
                    files={"plik": ("x.txt", "Treść".encode())}).json()
    assert client.patch(f"/dokumenty/{d['id']}", json={"tekst": "Nowa"}).status_code == 403
    assert client.delete(f"/dokumenty/{d['id']}").status_code == 403

    request.getfixturevalue("jako_admin")
    r = client.patch(f"/dokumenty/{d['id']}", json={"rodzaj": "odp_wydzialu", "wydzial": "wgk",
                                                    "nazwa_pliku": "Odpowiedź WGK.txt", "tekst": "Poprawiona"})
    assert r.status_code == 200
    assert {k: r.json()[k] for k in ("rodzaj", "wydzial", "nazwa_pliku", "tekst")} == {
        "rodzaj": "ODP_WYDZIALU", "wydzial": "WGK", "nazwa_pliku": "Odpowiedź WGK.txt", "tekst": "Poprawiona"}
    assert client.patch(f"/dokumenty/{d['id']}", json={"wydzial": ""}).json()["wydzial"] is None
    assert client.patch(f"/dokumenty/{d['id']}", json={"rodzaj": "ODP_WYDZIALU"}).status_code == 200  # bez zmian
    assert client.delete(f"/dokumenty/{d['id']}").status_code == 204
    sp = client.get(f"/sprawy/{sid}").json()
    assert sp["dokumenty"] == [] and sp["status"] == "NOWY"  # wpisy audytowe nie zmieniają statusu
    audyt = [z for z in sp["zdarzenia"] if z["typ"].startswith("DOKUMENT_")]
    assert [(z["typ"], z["inicjaly"]) for z in audyt] == [
        ("DOKUMENT_DODANIE", "test"),  # dodał urzędnik (login z sesji)
        ("DOKUMENT_ZMIANA", "admin"), ("DOKUMENT_ZMIANA", "admin"), ("DOKUMENT_USUNIECIE", "admin")]
    assert audyt[0]["payload"] == {"dokument": "x.txt", "rodzaj": "INNE"}
    assert audyt[1]["payload"] == {"dokument": "x.txt", "zmiany": {
        "rodzaj": ["INNE", "ODP_WYDZIALU"], "nazwa_pliku": ["x.txt", "Odpowiedź WGK.txt"],
        "wydzial": [None, "WGK"], "tekst": [5, 10]}}
    assert audyt[3]["payload"] == {"dokument": "Odpowiedź WGK.txt", "rodzaj": "ODP_WYDZIALU"}
    assert client.delete(f"/dokumenty/{d['id']}").status_code == 404
    # wpisów audytowych nie da się dodać ręcznie
    assert client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": "DOKUMENT_USUNIECIE", "data": "2026-11-20"}).status_code == 422


def test_edycja_wniosku_tylko_admin(request):
    s = nowa()
    sid = s["id"]
    assert client.patch(f"/sprawy/{sid}", json={"przedmiot": "Nowy"}).status_code == 403

    request.getfixturevalue("jako_admin")
    r = client.patch(f"/sprawy/{sid}", json={"przedmiot": "Wykaz dotacji", "wnioskodawca": "Anna Nowak",
                                             "znak": "BKS.IV.1431.777.2026", "data_wplywu": "2026-11-15",
                                             "inicjaly": ""}).json()
    assert (r["przedmiot"], r["wnioskodawca"], r["znak"], r["nr"]) == ("Wykaz dotacji", "Anna Nowak", "BKS.IV.1431.777.2026", 777)
    assert r["data_wplywu"] == "2026-11-15" and r["termin"] == "2026-11-29" and r["inicjaly"] is None
    assert r["zdarzenia"][0]["typ"] == "REJESTRACJA" and r["zdarzenia"][0]["data"] == "2026-11-15"
    zmiana = r["zdarzenia"][-1]
    assert (zmiana["typ"], zmiana["inicjaly"]) == ("SPRAWA_ZMIANA", "admin")
    assert zmiana["payload"]["zmiany"]["przedmiot"] == ["", "Wykaz dotacji"]
    assert zmiana["payload"]["zmiany"]["data_wplywu"] == ["2026-11-16", "2026-11-15"]

    inna = client.post("/sprawy", json={"znak": "BKS.IV.1431.778.2026", "data_wplywu": "2026-11-10"}).json()
    assert client.patch(f"/sprawy/{inna['id']}", json={"znak": "BKS.IV.1431.777.2026"}).status_code == 409
    assert client.patch(f"/sprawy/{sid}", json={"znak": "zly"}).status_code == 422
    client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": "PRZEKAZANIE", "data": "2026-11-17", "payload": {"wydzialy": ["WGK"]}})
    assert client.patch(f"/sprawy/{sid}", json={"data_wplywu": "2026-11-18"}).status_code == 422  # po zdarzeniu


def test_zamkniecie_i_wznowienie_tylko_admin(request):
    sid = nowa()["id"]
    client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": "PRZEKAZANIE", "data": "2026-11-17", "payload": {"wydzialy": ["WGK"]}})
    zamknij = {"typ": "ZAMKNIECIE", "data": "2026-11-18", "payload": {"powod": "Wniosek wycofany"}}
    assert client.post(f"/sprawy/{sid}/zdarzenia", json=zamknij).status_code == 403

    request.getfixturevalue("jako_admin")
    assert client.post(f"/sprawy/{sid}/zdarzenia", json={**zamknij, "payload": {}}).status_code == 422  # bez powodu
    r = client.post(f"/sprawy/{sid}/zdarzenia", json=zamknij).json()
    assert (r["status"], r["pilnosc"], r["pozostalo_dni"]) == ("ZAMKNIETA", "ZAMKNIETA", None)
    assert r["zdarzenia"][-1]["payload"] == {"powod": "Wniosek wycofany"}
    assert r["zdarzenia"][-1]["inicjaly"] == "admin"  # login z sesji, nie z przeglądarki
    assert sid not in [x["id"] for x in client.get("/sprawy", params={"otwarte": True}).json()]
    assert client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": "PRZEKAZANIE", "data": "2026-11-18",
                                                         "payload": {"wydzialy": ["WE"]}}).status_code == 409
    assert client.post(f"/sprawy/{sid}/zdarzenia", json=zamknij).status_code == 409  # już zamknięta
    r = client.post(f"/sprawy/{sid}/zdarzenia", json={"typ": "WZNOWIENIE", "data": "2026-11-19"}).json()
    assert r["status"] == "W_WYDZIALACH"  # status sprzed zamknięcia
