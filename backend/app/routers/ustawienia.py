"""Ustawienia bezpieczeństwa – tylko administrator."""
from fastapi import APIRouter

from app.auth import polityka
from app.auth.sesja import Administrator

router = APIRouter(prefix="/ustawienia", tags=["ustawienia"])


@router.get("/bezpieczenstwo", response_model=polityka.Polityka)
def pobierz(_: Administrator):
    return polityka.pobierz()


@router.put("/bezpieczenstwo", response_model=polityka.Polityka)
def zapisz(body: polityka.Polityka, _: Administrator):
    """Zmiana działa od razu: po włączeniu 2FA konta bez drugiego składnika muszą go skonfigurować
    (przy najbliższym zapytaniu wracają do etapu KONFIGURUJ_2FA). Nowa minimalna długość dotyczy
    kolejnych zmian haseł – obecne hasła pozostają ważne."""
    return polityka.zapisz(body)
