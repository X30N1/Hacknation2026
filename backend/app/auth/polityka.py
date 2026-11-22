"""Ustawienia bezpieczeństwa logowania – zmienia je administrator w aplikacji (tabela `ustawienia`).

Domyślnie bez wymogów: drugi składnik i minimalna długość hasła są opcjonalne, dopóki
administrator ich nie włączy.
"""
from pydantic import BaseModel, Field

from app.storage import store

KLUCZ = "bezpieczenstwo"


class Polityka(BaseModel):
    # Drugi składnik (aplikacja TOTP albo klucz FIDO2/WebAuthn) obowiązkowy dla wszystkich kont.
    wymagaj_2fa: bool = False
    # 0 = bez wymogu długości (hasło nie może być tylko puste).
    min_dlugosc_hasla: int = Field(0, ge=0, le=128)


def pobierz() -> Polityka:
    r = store.conn.execute("SELECT wartosc FROM ustawienia WHERE klucz = ?", (KLUCZ,)).fetchone()
    return Polityka.model_validate_json(r[0]) if r else Polityka()


def zapisz(p: Polityka) -> Polityka:
    with store.lock, store.conn:
        store.conn.execute(
            "INSERT INTO ustawienia (klucz, wartosc) VALUES (?, ?)"
            " ON CONFLICT (klucz) DO UPDATE SET wartosc = excluded.wartosc", (KLUCZ, p.model_dump_json()))
    return p
