"""Zarządzanie kontami – tylko administrator."""
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.auth import repo
from app.auth.sesja import Administrator
from app.routers.auth import HASLO_MAX, waliduj_haslo

router = APIRouter(prefix="/uzytkownicy", tags=["użytkownicy"])

LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
Rola = Literal["admin", "urzednik"]


class UzytkownikWidok(BaseModel):
    id: int
    login: str
    rola: str
    musi_zmienic_haslo: bool
    totp: bool
    klucze: int
    zablokowany_do: str | None
    utworzono: str


def _widok(u: repo.Uzytkownik) -> UzytkownikWidok:
    blokada = repo.zablokowany(u)
    return UzytkownikWidok(id=u.id, login=u.login, rola=u.rola, musi_zmienic_haslo=u.musi_zmienic_haslo,
                           totp=u.totp_aktywny, klucze=u.klucze,
                           zablokowany_do=blokada.isoformat() if blokada else None, utworzono=u.utworzono)


def _konto(uid: int) -> repo.Uzytkownik:
    u = repo.po_id(uid)
    if u is None:
        raise HTTPException(404, "Nie znaleziono użytkownika.")
    return u


@router.get("", response_model=list[UzytkownikWidok])
def lista(_: Administrator):
    return [_widok(u) for u in repo.lista()]


class NowyUzytkownik(BaseModel):
    login: str
    haslo: str = Field(..., max_length=HASLO_MAX)
    rola: Rola = "urzednik"

    @field_validator("login")
    @classmethod
    def _login(cls, v: str) -> str:
        v = v.strip().lower()
        if not LOGIN_RE.match(v):
            raise ValueError("Login: 3–40 znaków – małe litery, cyfry, kropka, myślnik, podkreślenie.")
        return v


@router.post("", response_model=UzytkownikWidok, status_code=status.HTTP_201_CREATED)
def dodaj(body: NowyUzytkownik, _: Administrator):
    """Hasło tymczasowe – użytkownik zmienia je przy pierwszym logowaniu."""
    if repo.po_loginie(body.login)[0]:
        raise HTTPException(409, f"Użytkownik {body.login} już istnieje.")
    waliduj_haslo(body.haslo, body.login)
    return _widok(repo.utworz(body.login, body.haslo, body.rola))


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def usun(uid: int, admin: Administrator):
    u = _konto(uid)
    if u.id == admin.id:
        raise HTTPException(409, "Nie możesz usunąć własnego konta.")
    if u.rola == "admin" and repo.liczba_adminow() <= 1:
        raise HTTPException(409, "Nie można usunąć ostatniego administratora.")
    repo.usun(u.id)


class NoweHaslo(BaseModel):
    haslo: str = Field(..., max_length=HASLO_MAX)


@router.post("/{uid}/haslo", response_model=UzytkownikWidok)
def ustaw_haslo(uid: int, body: NoweHaslo, _: Administrator):
    """Hasło tymczasowe: odblokowuje konto, wylogowuje użytkownika i wymusza zmianę przy logowaniu."""
    u = _konto(uid)
    waliduj_haslo(body.haslo, u.login)
    repo.ustaw_haslo(u.id, body.haslo, musi_zmienic=True)
    repo.zakoncz_wszystkie(u.id)
    return _widok(_konto(uid))


@router.post("/{uid}/reset-2fa", response_model=UzytkownikWidok)
def resetuj_2fa(uid: int, admin: Administrator):
    """Np. zgubiony telefon / klucz – użytkownik skonfiguruje drugi składnik od nowa przy logowaniu."""
    u = _konto(uid)
    if u.id == admin.id:
        raise HTTPException(409, "Własny drugi składnik zmienisz w ustawieniach konta.")
    repo.resetuj_drugi_skladnik(u.id)
    repo.zakoncz_wszystkie(u.id)
    return _widok(_konto(uid))
