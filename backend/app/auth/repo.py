"""Konta, sesje i klucze WebAuthn w SQLite."""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.auth import hasla
from app.config import settings
from app.storage import store

ADMIN_LOGIN = "admin"
ADMIN_HASLO_STARTOWE = "admin"


@dataclass
class Uzytkownik:
    id: int
    login: str
    rola: str
    musi_zmienic_haslo: bool
    totp_aktywny: bool
    klucze: int
    zablokowany_do: datetime | None
    utworzono: str

    @property
    def ma_drugi_skladnik(self) -> bool:
        return self.totp_aktywny or self.klucze > 0


@dataclass
class Sesja:
    token_hash: str
    uzytkownik: Uzytkownik
    drugi_skladnik: bool
    wyzwanie: bytes | None


def _teraz() -> datetime:
    return datetime.now().replace(microsecond=0)


def _uzytkownik(r) -> Uzytkownik:
    return Uzytkownik(
        id=r["id"], login=r["login"], rola=r["rola"], musi_zmienic_haslo=bool(r["musi_zmienic_haslo"]),
        totp_aktywny=bool(r["totp_sekret"]), klucze=r["klucze"],
        zablokowany_do=datetime.fromisoformat(r["zablokowany_do"]) if r["zablokowany_do"] else None,
        utworzono=r["utworzono"],
    )


_SELECT = ("SELECT u.*, (SELECT COUNT(*) FROM klucze k WHERE k.uzytkownik_id = u.id) AS klucze"
           " FROM uzytkownicy u")


# ---------- konta ----------
def zapewnij_admina() -> bool:
    """Pierwsze uruchomienie: konto admin / admin z obowiązkową zmianą hasła przy logowaniu."""
    with store.lock, store.conn:
        if store.conn.execute("SELECT 1 FROM uzytkownicy LIMIT 1").fetchone():
            return False
        store.conn.execute(
            "INSERT INTO uzytkownicy (login, haslo_hash, rola, musi_zmienic_haslo, utworzono)"
            " VALUES (?, ?, 'admin', 1, ?)",
            (ADMIN_LOGIN, hasla.zahashuj(ADMIN_HASLO_STARTOWE), _teraz().isoformat()),
        )
    return True


def po_id(uid: int) -> Uzytkownik | None:
    r = store.conn.execute(f"{_SELECT} WHERE u.id = ?", (uid,)).fetchone()
    return _uzytkownik(r) if r else None


def po_loginie(login: str):
    """(Uzytkownik, hash hasła) albo (None, None)."""
    r = store.conn.execute(f"{_SELECT} WHERE u.login = ?", (login,)).fetchone()
    return (_uzytkownik(r), r["haslo_hash"]) if r else (None, None)


def lista() -> list[Uzytkownik]:
    return [_uzytkownik(r) for r in store.conn.execute(f"{_SELECT} ORDER BY u.login")]


def utworz(login: str, haslo: str, rola: str) -> Uzytkownik:
    with store.lock, store.conn:
        cur = store.conn.execute(
            "INSERT INTO uzytkownicy (login, haslo_hash, rola, musi_zmienic_haslo, utworzono)"
            " VALUES (?, ?, ?, 1, ?)", (login, hasla.zahashuj(haslo), rola, _teraz().isoformat()))
    return po_id(cur.lastrowid)


def usun(uid: int) -> None:
    with store.lock, store.conn:
        store.conn.execute("DELETE FROM uzytkownicy WHERE id = ?", (uid,))


def liczba_adminow() -> int:
    return store.conn.execute("SELECT COUNT(*) FROM uzytkownicy WHERE rola = 'admin'").fetchone()[0]


def ustaw_haslo(uid: int, haslo: str, musi_zmienic: bool) -> None:
    with store.lock, store.conn:
        store.conn.execute(
            "UPDATE uzytkownicy SET haslo_hash = ?, musi_zmienic_haslo = ?, nieudane_proby = 0,"
            " zablokowany_do = NULL WHERE id = ?", (hasla.zahashuj(haslo), int(musi_zmienic), uid))


def haslo_hash(uid: int) -> str:
    return store.conn.execute("SELECT haslo_hash FROM uzytkownicy WHERE id = ?", (uid,)).fetchone()[0]


def nieudana_proba(uid: int) -> datetime | None:
    """Zlicza nieudane logowanie; zwraca czas końca blokady, jeśli przekroczono limit."""
    cfg = settings.auth
    with store.lock, store.conn:
        (proby,) = store.conn.execute(
            "UPDATE uzytkownicy SET nieudane_proby = nieudane_proby + 1 WHERE id = ?"
            " RETURNING nieudane_proby", (uid,)).fetchone()
        if proby < cfg.max_prob:
            return None
        do = _teraz() + timedelta(minutes=cfg.blokada_minut)
        store.conn.execute("UPDATE uzytkownicy SET zablokowany_do = ?, nieudane_proby = 0 WHERE id = ?",
                           (do.isoformat(), uid))
    return do


def udana_proba(uid: int) -> None:
    with store.lock, store.conn:
        store.conn.execute(
            "UPDATE uzytkownicy SET nieudane_proby = 0, zablokowany_do = NULL WHERE id = ?", (uid,))


def zablokowany(u: Uzytkownik) -> datetime | None:
    return u.zablokowany_do if u.zablokowany_do and u.zablokowany_do > _teraz() else None


# ---------- TOTP ----------
def totp(uid: int) -> tuple[str | None, str | None, int | None]:
    r = store.conn.execute(
        "SELECT totp_sekret, totp_nowy, totp_ostatni_krok FROM uzytkownicy WHERE id = ?", (uid,)).fetchone()
    return r["totp_sekret"], r["totp_nowy"], r["totp_ostatni_krok"]


def ustaw_totp_nowy(uid: int, sekret: str | None) -> None:
    with store.lock, store.conn:
        store.conn.execute("UPDATE uzytkownicy SET totp_nowy = ? WHERE id = ?", (sekret, uid))


def aktywuj_totp(uid: int, krok: int) -> None:
    with store.lock, store.conn:
        store.conn.execute(
            "UPDATE uzytkownicy SET totp_sekret = totp_nowy, totp_nowy = NULL, totp_ostatni_krok = ?"
            " WHERE id = ?", (krok, uid))


def zapisz_krok_totp(uid: int, krok: int) -> None:
    with store.lock, store.conn:
        store.conn.execute("UPDATE uzytkownicy SET totp_ostatni_krok = ? WHERE id = ?", (krok, uid))


def wylacz_totp(uid: int) -> None:
    with store.lock, store.conn:
        store.conn.execute(
            "UPDATE uzytkownicy SET totp_sekret = NULL, totp_nowy = NULL, totp_ostatni_krok = NULL"
            " WHERE id = ?", (uid,))


def resetuj_drugi_skladnik(uid: int) -> None:
    wylacz_totp(uid)
    with store.lock, store.conn:
        store.conn.execute("DELETE FROM klucze WHERE uzytkownik_id = ?", (uid,))


# ---------- klucze WebAuthn ----------
def klucze(uid: int) -> list[dict]:
    return [dict(r) for r in store.conn.execute(
        "SELECT id, credential_id, klucz_publiczny, licznik, nazwa, utworzono FROM klucze"
        " WHERE uzytkownik_id = ? ORDER BY id", (uid,))]


def dodaj_klucz(uid: int, credential_id: bytes, klucz_publiczny: bytes, licznik: int, nazwa: str) -> None:
    with store.lock, store.conn:
        store.conn.execute(
            "INSERT INTO klucze (uzytkownik_id, credential_id, klucz_publiczny, licznik, nazwa, utworzono)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (uid, credential_id, klucz_publiczny, licznik, nazwa, _teraz().isoformat()))


def zapisz_licznik(kid: int, licznik: int) -> None:
    with store.lock, store.conn:
        store.conn.execute("UPDATE klucze SET licznik = ? WHERE id = ?", (licznik, kid))


def usun_klucz(uid: int, kid: int) -> bool:
    with store.lock, store.conn:
        cur = store.conn.execute("DELETE FROM klucze WHERE id = ? AND uzytkownik_id = ?", (kid, uid))
    return cur.rowcount == 1


# ---------- sesje ----------
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def nowa_sesja(uid: int) -> str:
    token = secrets.token_urlsafe(32)
    teraz = _teraz()
    wygasa = teraz + timedelta(minutes=settings.auth.sesja_wstepna_minuty)
    with store.lock, store.conn:
        store.conn.execute("DELETE FROM sesje WHERE wygasa < ?", (teraz.isoformat(),))
        store.conn.execute(
            "INSERT INTO sesje (token_hash, uzytkownik_id, utworzono, wygasa) VALUES (?, ?, ?, ?)",
            (_hash(token), uid, teraz.isoformat(), wygasa.isoformat()))
    return token


def sesja(token: str | None) -> Sesja | None:
    return sesja_po_hashu(_hash(token)) if token else None


def sesja_po_hashu(token_hash: str) -> Sesja | None:
    r = store.conn.execute("SELECT * FROM sesje WHERE token_hash = ?", (token_hash,)).fetchone()
    if r is None or datetime.fromisoformat(r["wygasa"]) < _teraz():
        return None
    u = po_id(r["uzytkownik_id"])
    if u is None:
        return None
    return Sesja(r["token_hash"], u, bool(r["drugi_skladnik"]), r["wyzwanie"])


def oznacz_drugi_skladnik(s: Sesja) -> None:
    with store.lock, store.conn:
        store.conn.execute("UPDATE sesje SET drugi_skladnik = 1, wyzwanie = NULL WHERE token_hash = ?",
                           (s.token_hash,))


def pelna_sesja(s: Sesja) -> None:
    """Logowanie zakończone -> sesja na cały dzień pracy (wcześniej: kilkanaście minut)."""
    wygasa = _teraz() + timedelta(hours=settings.auth.sesja_godziny)
    with store.lock, store.conn:
        store.conn.execute("UPDATE sesje SET wygasa = ? WHERE token_hash = ?", (wygasa.isoformat(), s.token_hash))


def ustaw_wyzwanie(s: Sesja, wyzwanie: bytes | None) -> None:
    with store.lock, store.conn:
        store.conn.execute("UPDATE sesje SET wyzwanie = ? WHERE token_hash = ?", (wyzwanie, s.token_hash))


def zakoncz_sesje(token_hash: str) -> None:
    with store.lock, store.conn:
        store.conn.execute("DELETE FROM sesje WHERE token_hash = ?", (token_hash,))


def zakoncz_wszystkie(uid: int, oprocz: str | None = None) -> None:
    with store.lock, store.conn:
        store.conn.execute("DELETE FROM sesje WHERE uzytkownik_id = ? AND token_hash IS NOT ?", (uid, oprocz))
