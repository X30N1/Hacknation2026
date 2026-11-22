"""Logowanie: admin startowy, zmiana hasła, TOTP, blokada, etapy, panel administratora."""
import time

from fastapi.testclient import TestClient

from app.auth import polityka, repo, totp
from app.config import settings
from main import app

NOWE = "Bydgoszcz-2026!"


def klient() -> TestClient:
    return TestClient(app)


def kod(sekret: str, przesuniecie: int = 0) -> str:
    return totp._kod(sekret, int(time.time() // totp.KROK) + przesuniecie)


def zaloguj(c: TestClient, login="admin", haslo="admin"):
    return c.post("/auth/login", json={"login": login, "haslo": haslo})


def scisle_zasady() -> None:
    """Ustawienia bezpieczeństwa włączone przez administratora (domyślnie wyłączone)."""
    polityka.zapisz(polityka.Polityka(wymagaj_2fa=True, min_dlugosc_hasla=10))


def admin_z_totp(c: TestClient) -> str:
    """Pełne pierwsze logowanie administratora (przy włączonym 2FA); zwraca sekret TOTP."""
    scisle_zasady()
    repo.zapewnij_admina()
    assert zaloguj(c).json()["stan"] == "ZMIEN_HASLO"
    assert c.post("/auth/haslo", json={"stare": "admin", "nowe": NOWE}).json()["stan"] == "KONFIGURUJ_2FA"
    sekret = c.post("/auth/totp/nowy").json()["sekret"]
    assert c.post("/auth/totp/potwierdz", json={"kod": kod(sekret)}).json()["stan"] == "OK"
    return sekret


def test_admin_startowy_i_pierwsze_logowanie():
    scisle_zasady()
    assert repo.zapewnij_admina() is True
    assert repo.zapewnij_admina() is False  # tylko przy pustej bazie
    c = klient()
    assert c.get("/sprawy").status_code == 401
    r = zaloguj(c)
    assert r.status_code == 200 and r.json()["stan"] == "ZMIEN_HASLO" and r.json()["rola"] == "admin"
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert c.get("/sprawy").status_code == 401  # bez zmiany hasła i 2FA – brak dostępu

    assert c.post("/auth/haslo", json={"stare": "admin", "nowe": "krotkie"}).status_code == 422
    assert c.post("/auth/haslo", json={"stare": "admin", "nowe": "admin"}).status_code == 422
    assert c.post("/auth/haslo", json={"stare": "zle", "nowe": NOWE}).status_code == 422
    assert c.post("/auth/haslo", json={"stare": "admin", "nowe": NOWE}).json()["stan"] == "KONFIGURUJ_2FA"
    assert c.get("/sprawy").status_code == 401

    nowy = c.post("/auth/totp/nowy").json()
    assert nowy["uri"].startswith("otpauth://totp/") and "<svg" in nowy["qr_svg"]
    assert c.post("/auth/totp/potwierdz", json={"kod": "000000"}).status_code == 422
    assert c.post("/auth/totp/potwierdz", json={"kod": kod(nowy["sekret"])}).json()["stan"] == "OK"
    assert c.get("/sprawy").status_code == 200

    assert zaloguj(klient(), haslo="admin").status_code == 401  # stare hasło nie działa


def test_drugi_skladnik_przy_kolejnym_logowaniu():
    sekret = admin_z_totp(klient())
    c = klient()
    assert zaloguj(c, haslo=NOWE).json()["stan"] == "DRUGI_SKLADNIK"
    assert c.get("/sprawy").status_code == 401
    # na tym etapie nie da się zmienić hasła ani podmienić TOTP (samo hasło nie przejmuje konta)
    assert c.post("/auth/haslo", json={"stare": NOWE, "nowe": "Inne-haslo-123"}).status_code == 403
    assert c.post("/auth/totp/nowy").status_code == 403
    assert c.post("/auth/totp/weryfikuj", json={"kod": "123456"}).status_code == 422
    nastepny = kod(sekret, 1)  # kod bieżącego kroku zużyto przy konfiguracji
    assert c.post("/auth/totp/weryfikuj", json={"kod": nastepny}).json()["stan"] == "OK"
    assert c.get("/sprawy").status_code == 200

    c2 = klient()
    zaloguj(c2, haslo=NOWE)
    assert c2.post("/auth/totp/weryfikuj", json={"kod": nastepny}).status_code == 422  # powtórzenie kodu

    c.post("/auth/wyloguj")
    assert c.get("/sprawy").status_code == 401


def test_blokada_po_nieudanych_probach(monkeypatch):
    monkeypatch.setattr(settings.auth, "max_prob", 3)
    repo.zapewnij_admina()
    c = klient()
    assert [zaloguj(c, haslo="zle").status_code for _ in range(3)] == [401, 401, 429]
    assert zaloguj(c).status_code == 429  # nawet poprawne hasło – konto zablokowane
    assert zaloguj(c, login="nieistnieje").status_code == 401  # ten sam komunikat co złe hasło


def test_domyslnie_bez_2fa_i_min_dlugosci():
    repo.zapewnij_admina()
    c = klient()
    r = zaloguj(c).json()
    assert r["stan"] == "ZMIEN_HASLO" and r["wymagaj_2fa"] is False and r["min_dlugosc_hasla"] == 0
    assert c.post("/auth/haslo", json={"stare": "admin", "nowe": ""}).status_code == 422  # puste nigdy
    assert c.post("/auth/haslo", json={"stare": "admin", "nowe": "admin"}).status_code == 422  # startowe nigdy
    assert c.post("/auth/haslo", json={"stare": "admin", "nowe": "abc"}).json()["stan"] == "OK"
    assert c.get("/sprawy").status_code == 200
    assert c.post("/uzytkownicy", json={"login": "jan", "haslo": "x"}).status_code == 201


def test_ustawienia_bezpieczenstwa_administratora():
    repo.zapewnij_admina()
    admin = klient()
    zaloguj(admin)
    admin.post("/auth/haslo", json={"stare": "admin", "nowe": NOWE})
    assert admin.get("/ustawienia/bezpieczenstwo").json() == {"wymagaj_2fa": False, "min_dlugosc_hasla": 0}
    admin.post("/uzytkownicy", json={"login": "jan", "haslo": "tymczasowe"})
    u = klient()
    zaloguj(u, "jan", "tymczasowe")
    u.post("/auth/haslo", json={"stare": "tymczasowe", "nowe": "jan-haslo"})
    assert u.get("/sprawy").status_code == 200
    assert u.get("/ustawienia/bezpieczenstwo").status_code == 403  # tylko administrator
    assert u.put("/ustawienia/bezpieczenstwo", json={"wymagaj_2fa": False}).status_code == 403

    assert admin.put("/ustawienia/bezpieczenstwo", json={"wymagaj_2fa": True, "min_dlugosc_hasla": -1}).status_code == 422
    r = admin.put("/ustawienia/bezpieczenstwo", json={"wymagaj_2fa": True, "min_dlugosc_hasla": 12})
    assert r.json() == {"wymagaj_2fa": True, "min_dlugosc_hasla": 12}
    # od razu: konta bez drugiego składnika muszą go skonfigurować, nowe hasła wg nowej długości
    assert u.get("/sprawy").status_code == 401
    assert u.get("/auth/ja").json()["stan"] == "KONFIGURUJ_2FA"
    assert admin.get("/auth/ja").json()["stan"] == "KONFIGURUJ_2FA"
    assert u.post("/auth/haslo", json={"stare": "jan-haslo", "nowe": "za-krotkie"}).status_code == 422

    sekret = admin.post("/auth/totp/nowy").json()["sekret"]
    assert admin.post("/auth/totp/potwierdz", json={"kod": kod(sekret)}).json()["stan"] == "OK"
    assert admin.put("/ustawienia/bezpieczenstwo", json={}).json() == {"wymagaj_2fa": False, "min_dlugosc_hasla": 0}
    assert u.get("/sprawy").status_code == 200
    assert admin.delete("/auth/totp").json()["totp"] is False  # bez wymogu można usunąć ostatni składnik


def test_panel_administratora():
    admin = klient()
    admin_z_totp(admin)
    r = admin.post("/uzytkownicy", json={"login": "Anna.Nowak", "haslo": "Tymczasowe-1", "rola": "urzednik"})
    assert r.status_code == 201 and r.json()["login"] == "anna.nowak" and r.json()["musi_zmienic_haslo"]
    anna = r.json()["id"]
    assert admin.post("/uzytkownicy", json={"login": "anna.nowak", "haslo": "Tymczasowe-1"}).status_code == 409
    assert admin.post("/uzytkownicy", json={"login": "a b", "haslo": "Tymczasowe-1"}).status_code == 422
    assert admin.post("/uzytkownicy", json={"login": "jan", "haslo": "krotkie"}).status_code == 422
    assert {u["login"] for u in admin.get("/uzytkownicy").json()} == {"admin", "anna.nowak"}

    # urzędnik: pierwsze logowanie, brak dostępu do panelu
    u = klient()
    assert zaloguj(u, "anna.nowak", "Tymczasowe-1").json()["stan"] == "ZMIEN_HASLO"
    u.post("/auth/haslo", json={"stare": "Tymczasowe-1", "nowe": "Haslo-Anny-2026"})
    sekret = u.post("/auth/totp/nowy").json()["sekret"]
    u.post("/auth/totp/potwierdz", json={"kod": kod(sekret)})
    assert u.get("/sprawy").status_code == 200
    assert u.get("/uzytkownicy").status_code == 403

    # admin ustawia hasło tymczasowe: użytkownik wylogowany, przy logowaniu najpierw 2FA, potem zmiana hasła
    assert admin.post(f"/uzytkownicy/{anna}/haslo", json={"haslo": "Reset-hasla-1"}).json()["musi_zmienic_haslo"]
    assert u.get("/sprawy").status_code == 401
    u = klient()
    assert zaloguj(u, "anna.nowak", "Reset-hasla-1").json()["stan"] == "DRUGI_SKLADNIK"
    assert u.post("/auth/totp/weryfikuj", json={"kod": kod(sekret, 1)}).json()["stan"] == "ZMIEN_HASLO"

    # reset 2FA (zgubiony telefon) -> konfiguracja od nowa
    r = admin.post(f"/uzytkownicy/{anna}/reset-2fa").json()
    assert r["totp"] is False and r["klucze"] == 0

    me = next(x["id"] for x in admin.get("/uzytkownicy").json() if x["login"] == "admin")
    assert admin.delete(f"/uzytkownicy/{me}").status_code == 409  # nie siebie
    assert admin.delete(f"/uzytkownicy/{anna}").status_code == 204
    assert admin.delete(f"/uzytkownicy/{anna}").status_code == 404
    assert zaloguj(klient(), "anna.nowak", "Reset-hasla-1").status_code == 401


def test_ostatni_skladnik_i_klucz_opcje():
    c = klient()
    admin_z_totp(c)
    assert c.delete("/auth/totp").status_code == 409  # jedyny drugi składnik
    opcje = c.post("/auth/klucz/rejestracja/opcje").json()
    assert opcje["rp"]["id"] == "localhost" and opcje["challenge"] and opcje["user"]["name"] == "admin"
    assert c.post("/auth/klucz/rejestracja", json={"credential": {"id": "x"}}).status_code == 422
    assert c.get("/auth/klucze").json() == []


def test_totp_rfc6238():
    # wektor testowy RFC 6238 (SHA-1, sekret "12345678901234567890", T = 59 s -> 94287082, 6 cyfr: 287082)
    import base64
    sekret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.sprawdz(sekret, "287082", None, teraz=59) == 1
    assert totp.sprawdz(sekret, "287082", 1, teraz=59) is None  # już użyty
