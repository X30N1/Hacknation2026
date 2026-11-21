from fastapi.testclient import TestClient

from app import llm_client
from main import app

client = TestClient(app)

TEKST = """Wnioskodawca: Jan Kowalski
ul. Gdańska 12/4, 85-005 Bydgoszcz
PESEL 44051401359, tel. 501 234 567, jan.k@example.com
Proszę o informację. Pan Kowalskiego syn choruje na astmę.
Z poważaniem, Jan Kowalski"""


def frag(r, kategoria):
    return [f["tekst"] for f in r["fragmenty"] if f["kategoria"] == kategoria]


def test_wzorce_bez_llm():
    r = client.post("/anonimizacja", json={"tekst": TEKST}).json()
    assert r["llm_uzyty"] is False and r["uwagi"]  # echo -> tylko wzorce, z ostrzeżeniem
    assert frag(r, "PESEL") == ["44051401359"]
    assert frag(r, "TELEFON") == ["501 234 567"]
    assert frag(r, "EMAIL") == ["jan.k@example.com"]
    assert "ul. Gdańska 12/4" in frag(r, "ADRES") and "85-005 Bydgoszcz" in frag(r, "ADRES")
    assert frag(r, "IMIE_NAZWISKO") == ["Jan Kowalski"]
    for f in r["fragmenty"]:
        assert TEKST[f["start"]:f["end"]] == f["tekst"] and f["zrodlo"] == "WZORZEC"
    # błędna suma kontrolna PESEL -> brak propozycji
    assert not frag(client.post("/anonimizacja", json={"tekst": "44051401358"}).json(), "PESEL")


def test_wnioskodawca_i_odmiana():
    r = client.post("/anonimizacja", json={"tekst": TEKST, "wnioskodawca": "Jan Kowalski"}).json()
    nazw = [f for f in r["fragmenty"] if f["kategoria"] == "IMIE_NAZWISKO"]
    assert [f["tekst"] for f in nazw] == ["Jan Kowalski", "Kowalskiego", "Jan Kowalski"]
    assert {f["zrodlo"] for f in nazw[1:]} == {"SPRAWA"}
    # osoby prawnej nie anonimizujemy
    r = client.post("/anonimizacja", json={"tekst": "Fundacja Jawności pyta",
                                           "wnioskodawca": "Fundacja Jawności"}).json()
    assert r["fragmenty"] == []


def test_llm(monkeypatch):
    monkeypatch.setattr(llm_client, "is_echo_mode", lambda: False)

    async def fake_complete(messages, **params):
        assert params["response_format"] == {"type": "json_object"}
        return ('{"dane": [{"tekst": "choruje na astmę", "kategoria": "DANE_WRAZLIWE",'
                ' "powod": "stan zdrowia"}, {"tekst": "nie ma w tekście", "kategoria": "INNE"},'
                ' {"tekst": "PESEL 44051401359", "kategoria": "BZDURA"}]}')

    monkeypatch.setattr(llm_client, "complete", fake_complete)
    r = client.post("/anonimizacja", json={"tekst": TEKST}).json()
    assert r["llm_uzyty"] is True and r["uwagi"] == []
    zdrowie = next(f for f in r["fragmenty"] if f["kategoria"] == "DANE_WRAZLIWE")
    assert (zdrowie["tekst"], zdrowie["zrodlo"], zdrowie["powod"]) == \
        ("choruje na astmę", "LLM", "stan zdrowia")
    assert not any(f["tekst"] == "nie ma w tekście" for f in r["fragmenty"])
    # dłuższy zakres z LLM wygrywa z nakładającym się wzorcem, nieznana kategoria -> INNE
    assert ("PESEL 44051401359", "INNE") in [(f["tekst"], f["kategoria"]) for f in r["fragmenty"]]
    # zakresy rosnące i bez nakładania
    zakresy = [(f["start"], f["end"]) for f in r["fragmenty"]]
    assert all(a[1] <= b[0] for a, b in zip(zakresy, zakresy[1:]))


def test_llm_blad(monkeypatch):
    monkeypatch.setattr(llm_client, "is_echo_mode", lambda: False)

    async def broken(messages, **params):
        raise RuntimeError("down")

    monkeypatch.setattr(llm_client, "complete", broken)
    r = client.post("/anonimizacja", json={"tekst": TEKST}).json()
    assert r["llm_uzyty"] is True and r["uwagi"] and frag(r, "PESEL")
