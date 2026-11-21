"""Logowanie: hasło, zmiana hasła, drugi składnik (TOTP / klucz WebAuthn), wylogowanie."""
import json
from typing import Annotated, Any

import webauthn
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from webauthn.helpers import structs

from app.auth import hasla, repo, totp
from app.auth.sesja import COOKIE, SesjaDep, Stan, stan, wymagaj_etapu
from app.config import settings

router = APIRouter(prefix="/auth", tags=["logowanie"])

WYDAWCA_TOTP = "UM Bydgoszcz – Asystent"
LOGIN_MAX, HASLO_MAX = 64, 256


class Ja(BaseModel):
    login: str
    rola: str
    stan: Stan
    totp: bool
    klucze: int
    wymagaj_2fa: bool
    min_dlugosc_hasla: int


def ja(s: repo.Sesja) -> Ja:
    u = s.uzytkownik
    return Ja(login=u.login, rola=u.rola, stan=stan(s), totp=u.totp_aktywny, klucze=u.klucze,
              wymagaj_2fa=settings.auth.wymagaj_2fa, min_dlugosc_hasla=settings.auth.min_dlugosc_hasla)


def _odswiez(s: repo.Sesja) -> repo.Sesja:
    return repo.sesja_po_hashu(s.token_hash)


def _po_etapie(s: repo.Sesja, drugi_skladnik: bool = False) -> Ja:
    """Po zakończonym kroku: pełna sesja, gdy logowanie się skończyło."""
    if drugi_skladnik:
        repo.oznacz_drugi_skladnik(s)
    s = _odswiez(s)
    if stan(s) == Stan.OK:
        repo.pelna_sesja(s)
    return ja(s)


def _ciasteczko(response: Response, token: str) -> None:
    cfg = settings.auth
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=cfg.cookie_secure,
                        max_age=int(cfg.sesja_godziny * 3600), path="/")


def waliduj_haslo(haslo: str, login: str) -> None:
    n = settings.auth.min_dlugosc_hasla
    if len(haslo) < n:
        raise HTTPException(422, f"Hasło musi mieć co najmniej {n} znaków.")
    if haslo.lower() == login.lower() or haslo == repo.ADMIN_HASLO_STARTOWE:
        raise HTTPException(422, "Hasło nie może być takie jak login ani hasło startowe.")


def _blokada(do) -> HTTPException:
    return HTTPException(429, f"Konto zablokowane po nieudanych próbach do {do:%H:%M}. "
                              "Spróbuj później albo poproś administratora o odblokowanie.")


# ---------- hasło ----------
class Logowanie(BaseModel):
    login: str = Field(..., min_length=1, max_length=LOGIN_MAX)
    haslo: str = Field(..., min_length=1, max_length=HASLO_MAX)


@router.post("/login", response_model=Ja)
def zaloguj(body: Logowanie, response: Response):
    u, zapis = repo.po_loginie(body.login.strip())
    if u is None:
        hasla.sprawdz(body.haslo, hasla.PUSTY)  # ten sam czas odpowiedzi co dla istniejącego konta
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
    if do := repo.zablokowany(u):
        raise _blokada(do)
    if not hasla.sprawdz(body.haslo, zapis):
        if do := repo.nieudana_proba(u.id):
            raise _blokada(do)
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
    repo.udana_proba(u.id)
    token = repo.nowa_sesja(u.id)
    _ciasteczko(response, token)
    return _po_etapie(repo.sesja(token))


@router.get("/ja", response_model=Ja)
def kim_jestem(s: SesjaDep):
    return ja(s)


@router.post("/wyloguj", status_code=204)
def wyloguj(s: SesjaDep, response: Response):
    repo.zakoncz_sesje(s.token_hash)
    response.delete_cookie(COOKIE, path="/")


class ZmianaHasla(BaseModel):
    stare: str = Field(..., max_length=HASLO_MAX)
    nowe: str = Field(..., max_length=HASLO_MAX)


@router.post("/haslo", response_model=Ja)
def zmien_haslo(
    body: ZmianaHasla,
    s: Annotated[repo.Sesja, Depends(wymagaj_etapu(Stan.ZMIEN_HASLO, Stan.KONFIGURUJ_2FA, Stan.OK))],
):
    u = s.uzytkownik
    if not hasla.sprawdz(body.stare, repo.haslo_hash(u.id)):
        raise HTTPException(422, "Obecne hasło jest nieprawidłowe.")
    if body.nowe == body.stare:
        raise HTTPException(422, "Nowe hasło musi być inne niż obecne.")
    waliduj_haslo(body.nowe, u.login)
    repo.ustaw_haslo(u.id, body.nowe, musi_zmienic=False)
    repo.zakoncz_wszystkie(u.id, oprocz=s.token_hash)  # wylogowanie z innych urządzeń
    return _po_etapie(s)


# ---------- TOTP ----------
KonfiguracjaDep = Annotated[repo.Sesja, Depends(wymagaj_etapu(Stan.KONFIGURUJ_2FA, Stan.OK))]
DrugiSkladnikDep = Annotated[repo.Sesja, Depends(wymagaj_etapu(Stan.DRUGI_SKLADNIK))]


class NowyTotp(BaseModel):
    sekret: str
    uri: str
    qr_svg: str


class Kod(BaseModel):
    kod: str = Field(..., max_length=16)


@router.post("/totp/nowy", response_model=NowyTotp)
def totp_nowy(s: KonfiguracjaDep):
    """Nowy sekret do zeskanowania; zaczyna działać dopiero po potwierdzeniu kodem."""
    sekret = totp.nowy_sekret()
    repo.ustaw_totp_nowy(s.uzytkownik.id, sekret)
    adres = totp.uri(sekret, s.uzytkownik.login, WYDAWCA_TOTP)
    return NowyTotp(sekret=sekret, uri=adres, qr_svg=totp.qr_svg(adres))


@router.post("/totp/potwierdz", response_model=Ja)
def totp_potwierdz(body: Kod, s: KonfiguracjaDep):
    _, nowy, _ = repo.totp(s.uzytkownik.id)
    if not nowy:
        raise HTTPException(409, "Najpierw wygeneruj kod QR.")
    krok = totp.sprawdz(nowy, body.kod, None)
    if krok is None:
        raise HTTPException(422, "Nieprawidłowy kod. Sprawdź, czy zegar w telefonie jest ustawiony automatycznie.")
    repo.aktywuj_totp(s.uzytkownik.id, krok)
    return _po_etapie(s, drugi_skladnik=True)


@router.post("/totp/weryfikuj", response_model=Ja)
def totp_weryfikuj(body: Kod, s: DrugiSkladnikDep):
    u = s.uzytkownik
    sekret, _, ostatni = repo.totp(u.id)
    if not sekret:
        raise HTTPException(409, "To konto nie ma aplikacji uwierzytelniającej – użyj klucza.")
    if do := repo.zablokowany(u):
        raise _blokada(do)
    krok = totp.sprawdz(sekret, body.kod, ostatni)
    if krok is None:
        if do := repo.nieudana_proba(u.id):
            repo.zakoncz_sesje(s.token_hash)
            raise _blokada(do)
        raise HTTPException(422, "Nieprawidłowy kod.")
    repo.zapisz_krok_totp(u.id, krok)
    repo.udana_proba(u.id)
    return _po_etapie(s, drugi_skladnik=True)


def _zostaje_drugi_skladnik(u: repo.Uzytkownik, bez_totp=False, bez_klucza=False) -> None:
    totp_zostaje = u.totp_aktywny and not bez_totp
    klucze_zostaja = u.klucze - (1 if bez_klucza else 0) > 0
    if settings.auth.wymagaj_2fa and not (totp_zostaje or klucze_zostaja):
        raise HTTPException(409, "To jedyny drugi składnik logowania – najpierw dodaj inny.")


@router.delete("/totp", response_model=Ja)
def totp_wylacz(s: Annotated[repo.Sesja, Depends(wymagaj_etapu(Stan.OK))]):
    _zostaje_drugi_skladnik(s.uzytkownik, bez_totp=True)
    repo.wylacz_totp(s.uzytkownik.id)
    return ja(_odswiez(s))


# ---------- klucze sprzętowe (WebAuthn / FIDO2) ----------
def _opcje(opcje) -> dict[str, Any]:
    return json.loads(webauthn.options_to_json(opcje))


def _deskryptory(uid: int) -> list[structs.PublicKeyCredentialDescriptor]:
    return [structs.PublicKeyCredentialDescriptor(id=k["credential_id"]) for k in repo.klucze(uid)]


@router.post("/klucz/rejestracja/opcje")
def klucz_rejestracja_opcje(s: KonfiguracjaDep):
    u = s.uzytkownik
    cfg = settings.auth
    opcje = webauthn.generate_registration_options(
        rp_id=cfg.rp_id, rp_name=cfg.rp_nazwa, user_id=str(u.id).encode(), user_name=u.login,
        exclude_credentials=_deskryptory(u.id),
        authenticator_selection=structs.AuthenticatorSelectionCriteria(
            resident_key=structs.ResidentKeyRequirement.DISCOURAGED,
            user_verification=structs.UserVerificationRequirement.PREFERRED),
    )
    repo.ustaw_wyzwanie(s, opcje.challenge)
    return _opcje(opcje)


class Rejestracja(BaseModel):
    credential: dict[str, Any]
    nazwa: str = Field("Klucz sprzętowy", max_length=60)


@router.post("/klucz/rejestracja", response_model=Ja)
def klucz_rejestracja(body: Rejestracja, s: KonfiguracjaDep):
    if not s.wyzwanie:
        raise HTTPException(409, "Rozpocznij rejestrację klucza od nowa.")
    try:
        wynik = webauthn.verify_registration_response(
            credential=body.credential, expected_challenge=s.wyzwanie,
            expected_rp_id=settings.auth.rp_id, expected_origin=settings.auth.origins)
    except Exception as exc:  # noqa: BLE001 – biblioteka zgłasza różne wyjątki weryfikacji
        raise HTTPException(422, f"Nie udało się zarejestrować klucza: {exc}") from exc
    finally:
        repo.ustaw_wyzwanie(s, None)
    repo.dodaj_klucz(s.uzytkownik.id, wynik.credential_id, wynik.credential_public_key,
                     wynik.sign_count, body.nazwa.strip() or "Klucz sprzętowy")
    return _po_etapie(s, drugi_skladnik=True)


@router.post("/klucz/logowanie/opcje")
def klucz_logowanie_opcje(s: DrugiSkladnikDep):
    if not s.uzytkownik.klucze:
        raise HTTPException(409, "To konto nie ma klucza – użyj aplikacji uwierzytelniającej.")
    opcje = webauthn.generate_authentication_options(
        rp_id=settings.auth.rp_id, allow_credentials=_deskryptory(s.uzytkownik.id),
        user_verification=structs.UserVerificationRequirement.PREFERRED)
    repo.ustaw_wyzwanie(s, opcje.challenge)
    return _opcje(opcje)


class Asercja(BaseModel):
    credential: dict[str, Any]


@router.post("/klucz/logowanie", response_model=Ja)
def klucz_logowanie(body: Asercja, s: DrugiSkladnikDep):
    u = s.uzytkownik
    if not s.wyzwanie:
        raise HTTPException(409, "Rozpocznij logowanie kluczem od nowa.")
    try:
        cid = webauthn.base64url_to_bytes(str(body.credential.get("rawId") or body.credential.get("id")))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, "Niepoprawna odpowiedź klucza.") from exc
    klucz = next((k for k in repo.klucze(u.id) if k["credential_id"] == cid), None)
    if klucz is None:
        raise HTTPException(422, "Ten klucz nie jest przypisany do konta.")
    try:
        wynik = webauthn.verify_authentication_response(
            credential=body.credential, expected_challenge=s.wyzwanie,
            expected_rp_id=settings.auth.rp_id, expected_origin=settings.auth.origins,
            credential_public_key=klucz["klucz_publiczny"], credential_current_sign_count=klucz["licznik"])
    except Exception as exc:  # noqa: BLE001
        repo.ustaw_wyzwanie(s, None)
        raise HTTPException(422, f"Weryfikacja klucza nieudana: {exc}") from exc
    repo.zapisz_licznik(klucz["id"], wynik.new_sign_count)
    repo.udana_proba(u.id)
    return _po_etapie(s, drugi_skladnik=True)


class Klucz(BaseModel):
    id: int
    nazwa: str
    utworzono: str


@router.get("/klucze", response_model=list[Klucz])
def lista_kluczy(s: Annotated[repo.Sesja, Depends(wymagaj_etapu(Stan.OK))]):
    return [Klucz(id=k["id"], nazwa=k["nazwa"], utworzono=k["utworzono"]) for k in repo.klucze(s.uzytkownik.id)]


@router.delete("/klucze/{kid}", response_model=Ja)
def usun_klucz(kid: int, s: Annotated[repo.Sesja, Depends(wymagaj_etapu(Stan.OK))]):
    _zostaje_drugi_skladnik(s.uzytkownik, bez_klucza=True)
    if not repo.usun_klucz(s.uzytkownik.id, kid):
        raise HTTPException(404, "Nie znaleziono klucza.")
    return ja(_odswiez(s))
