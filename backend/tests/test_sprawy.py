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


def test_edycja():
    s = nowa()
    r = client.patch(f"/sprawy/{s['id']}", json={"wnioskodawca": "Ewa", "data_wplywu": "2026-11-17"})
    assert r.json()["wnioskodawca"] == "Ewa" and r.json()["termin"] == "2026-12-01"
    assert r.json()["zdarzenia"][0]["data"] == "2026-11-17"
    assert client.patch(f"/sprawy/{s['id']}", json={"znak": "x"}).status_code == 422


# ---------- dokumenty ----------
def test_analiza_docx_i_rejestracja():
    plik = docx_bytes("Wniosek o udostępnienie informacji publicznej", "Proszę o wykaz dotacji.")
    r = client.post("/wnioski/analiza", files={"plik": ("wniosek.docx", plik)})
    assert r.status_code == 200, r.text
    wynik = r.json()
    doc, prop = wynik["dokument"], wynik["propozycja"]
    assert doc["metoda"] == "DOCX" and "wykaz dotacji" in doc["tekst"] and doc["sprawa_id"] is None
    assert prop["znak"] == "BKS.IV.1431.1.2026" and prop["data_wplywu"] == "2026-11-21"
    assert prop["przedmiot"] == "Proszę o wykaz dotacji."  # nagłówek pominięty

    assert client.patch(f"/dokumenty/{doc['id']}", json={"tekst": "poprawiony"}).json()["tekst"] == "poprawiony"
    s = nowa(znak=prop["znak"], wplyw=prop["data_wplywu"], dokument_id=doc["id"])
    assert s["dokumenty"][0]["id"] == doc["id"] and s["dokumenty"][0]["tekst"] == "poprawiony"
    # ponowne użycie dokumentu
    r = client.post("/sprawy", json={"znak": "BKS.IV.1431.2.2026", "data_wplywu": "2026-11-21",
                                     "dokument_id": doc["id"]})
    assert r.status_code == 409

    pobrany = client.get(doc["url_podgladu"])
    assert pobrany.status_code == 200 and pobrany.content == plik


def test_analiza_znak_z_nazwy_pliku_i_txt_cp1250():
    tekst = "Proszę o informację – żółć".encode("cp1250")
    r = client.post("/wnioski/analiza", files={"plik": ("Wniosek - BKS.IV.1431.599.2026.txt", tekst)})
    assert r.json()["propozycja"]["znak"] == "BKS.IV.1431.599.2026"
    assert r.json()["dokument"]["tekst"] == "Proszę o informację – żółć"
    assert r.json()["dokument"]["metoda"] == "RECZNA"


def test_pdf_warstwa_tekstowa_i_skan(monkeypatch):
    tekst = "Wniosek o udostepnienie informacji publicznej dotyczacej budzetu miasta"
    r = client.post("/wnioski/analiza", files={"plik": ("w.pdf", pdf_z_tekstem(tekst))}).json()
    assert r["dokument"]["metoda"] == "PDF_TEXT" and tekst in r["dokument"]["tekst"]

    monkeypatch.setattr(ekstrakcja, "ocr_dostepny", lambda: False)
    r = client.post("/wnioski/analiza", files={"plik": ("skan.pdf", pdf_z_tekstem(""))}).json()
    assert r["dokument"]["metoda"] == "OCR" and r["dokument"]["ocr_pewnosc"] == 0.0


def test_formaty_i_rozmiar(monkeypatch):
    from app.config import settings

    r = client.post("/wnioski/analiza", files={"plik": ("w.doc", b"x")})
    assert r.status_code == 415 and "PDF lub Word" in r.json()["blad"]
    assert client.post("/wnioski/analiza", files={"plik": ("w.docx", b"nie docx")}).status_code == 415
    monkeypatch.setattr(settings.pliki, "max_mb", 0.0001)
    assert client.post("/wnioski/analiza", files={"plik": ("w.txt", b"x" * 500)}).status_code == 413


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


def test_demo_seed():
    from app.sprawy import demo

    assert demo.zaladuj(DZIS) == (10, 0)
    st = {s["znak"].split(".")[3]: s for s in client.get("/sprawy").json()}
    assert st["701"]["status"] == "WYSLANA"
    assert st["702"]["status"] == "PRZEDLUZONA" and st["702"]["pozostalo_dni"] == 10
    assert st["704"]["pilnosc"] == "DZIS"
    assert st["708"]["termin_wstrzymany"] is True
