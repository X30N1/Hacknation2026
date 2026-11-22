"""TOTP (RFC 6238): 6 cyfr, krok 30 s, HMAC-SHA1 – zgodne z Google Authenticator, Aegis,
Microsoft Authenticator, FreeOTP i menedżerami haseł."""
import base64
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

import segno

KROK = 30
CYFRY = 6
OKNO = 1  # akceptujemy kod z poprzedniego / następnego kroku (rozjazd zegarów)


def nowy_sekret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _kod(sekret: str, krok: int) -> str:
    klucz = base64.b32decode(sekret + "=" * (-len(sekret) % 8))
    h = hmac.digest(klucz, struct.pack(">Q", krok), "sha1")
    o = h[-1] & 0x0F
    liczba = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10**CYFRY
    return str(liczba).zfill(CYFRY)


def sprawdz(sekret: str, kod: str, ostatni_krok: int | None, teraz: float | None = None) -> int | None:
    """Numer kroku, jeśli kod jest poprawny i nie był jeszcze użyty (ochrona przed powtórzeniem);
    inaczej None."""
    kod = "".join(kod.split())
    if not (kod.isdigit() and len(kod) == CYFRY):
        return None
    biezacy = int((time.time() if teraz is None else teraz) // KROK)
    for krok in range(biezacy - OKNO, biezacy + OKNO + 1):
        if ostatni_krok is not None and krok <= ostatni_krok:
            continue
        if hmac.compare_digest(_kod(sekret, krok), kod):
            return krok
    return None


def uri(sekret: str, login: str, wydawca: str) -> str:
    etykieta = quote(f"{wydawca}:{login}")
    return f"otpauth://totp/{etykieta}?" + urlencode(
        {"secret": sekret, "issuer": wydawca, "digits": CYFRY, "period": KROK})


def qr_svg(tresc: str) -> str:
    return segno.make(tresc, error="m").svg_inline(scale=5, border=2)
