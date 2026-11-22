"""Hasła: scrypt z biblioteki standardowej (memory-hard, bez dodatkowych zależności).

Format zapisu: scrypt$<n>$<r>$<p>$<sól base64>$<skrót base64>
"""
import base64
import hashlib
import hmac
import os

N, R, P, DLUGOSC = 2**15, 8, 1, 32
_MAXMEM = 64 * 1024 * 1024


def _skrot(haslo: str, sol: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(haslo.encode(), salt=sol, n=n, r=r, p=p, dklen=DLUGOSC, maxmem=_MAXMEM)


def zahashuj(haslo: str) -> str:
    sol = os.urandom(16)
    s = base64.b64encode
    return f"scrypt${N}${R}${P}${s(sol).decode()}${s(_skrot(haslo, sol, N, R, P)).decode()}"


def sprawdz(haslo: str, zapis: str) -> bool:
    try:
        alg, n, r, p, sol, skrot = zapis.split("$")
        if alg != "scrypt":
            return False
        wynik = _skrot(haslo, base64.b64decode(sol), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(wynik, base64.b64decode(skrot))


# Do wyrównania czasu odpowiedzi, gdy login nie istnieje (nie zdradzamy, które konta są w systemie).
PUSTY = zahashuj(os.urandom(16).hex())
