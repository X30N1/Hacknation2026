"""Etapy logowania i zależności FastAPI chroniące API.

Kolejność etapów po poprawnym haśle:
  1. DRUGI_SKLADNIK – konto ma TOTP / klucz: trzeba go potwierdzić (przed zmianą hasła, żeby samo
     hasło – np. tymczasowe od administratora – nie wystarczyło do przejęcia konta),
  2. ZMIEN_HASLO    – pierwsze logowanie albo hasło ustawione przez administratora,
  3. KONFIGURUJ_2FA – konto bez drugiego składnika (gdy administrator włączył wymóg 2FA),
  4. OK             – pełny dostęp.
"""
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.auth import polityka, repo

COOKIE = "sesja"


class Stan(StrEnum):
    DRUGI_SKLADNIK = "DRUGI_SKLADNIK"
    ZMIEN_HASLO = "ZMIEN_HASLO"
    KONFIGURUJ_2FA = "KONFIGURUJ_2FA"
    OK = "OK"


def stan(s: repo.Sesja) -> Stan:
    u = s.uzytkownik
    if u.ma_drugi_skladnik and not s.drugi_skladnik:
        return Stan.DRUGI_SKLADNIK
    if u.musi_zmienic_haslo:
        return Stan.ZMIEN_HASLO
    if not u.ma_drugi_skladnik and polityka.pobierz().wymagaj_2fa:
        return Stan.KONFIGURUJ_2FA
    return Stan.OK


def biezaca_sesja(request: Request) -> repo.Sesja:
    """Dowolny etap logowania (po haśle)."""
    s = repo.sesja(request.cookies.get(COOKIE))
    if s is None:
        raise HTTPException(401, "Zaloguj się.")
    return s


SesjaDep = Annotated[repo.Sesja, Depends(biezaca_sesja)]


def wymagaj_etapu(*dozwolone: Stan):
    def zaleznosc(s: SesjaDep) -> repo.Sesja:
        if stan(s) not in dozwolone:
            raise HTTPException(403, "Ta operacja jest niedostępna na tym etapie logowania.")
        return s
    return zaleznosc


def zalogowany(s: SesjaDep) -> repo.Uzytkownik:
    """Pełny dostęp do aplikacji: hasło + drugi składnik (jeśli wymagany)."""
    if stan(s) != Stan.OK:
        raise HTTPException(401, "Dokończ logowanie.")
    return s.uzytkownik


Zalogowany = Annotated[repo.Uzytkownik, Depends(zalogowany)]


def administrator(u: Zalogowany) -> repo.Uzytkownik:
    if u.rola != "admin":
        raise HTTPException(403, "Tylko administrator może zarządzać użytkownikami.")
    return u


Administrator = Annotated[repo.Uzytkownik, Depends(administrator)]
