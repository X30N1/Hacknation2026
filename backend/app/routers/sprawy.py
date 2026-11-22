"""Sprawy, zdarzenia i dokumenty – kontrakt z frontend/src/api/client.js."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app import anonimizacja
from app.auth.sesja import Administrator, Zalogowany
from app.config import settings
from app.sprawy import analiza, ekstrakcja, repo, terminy
from app.sprawy.model import (
    Dokument, DokumentPopraw, Odczyt, OdczytWniosku, SprawaEdytuj, SprawaLista, SprawaSzczegoly,
    SprawaUtworz, TypZdarzenia, Zrodlo, ZdarzenieDodaj,
)

router = APIRouter(tags=["sprawy"])

RODZAJ_MAX = 40   # TODO: limit / słownik rodzajów dokumentów
WYDZIAL_MAX = 20  # TODO: limit / słownik wydziałów


def dzis() -> date:
    """Data „dziś” do liczenia terminów (podmieniana w testach)."""
    return date.today()


Dzis = Annotated[date, Depends(dzis)]


def _404() -> HTTPException:
    return HTTPException(404, "Nie znaleziono sprawy.")


def _sprawa(sid: int, d: date) -> SprawaSzczegoly:
    s = repo.sprawa(sid, d)
    if s is None:
        raise _404()
    return s


async def _wczytaj_plik(plik: UploadFile) -> tuple[str, bytes, ekstrakcja.Odczyt]:
    nazwa = plik.filename or "plik"
    if ekstrakcja.rozszerzenie(nazwa) not in ekstrakcja.ROZSZERZENIA:
        raise HTTPException(415, "Nieobsługiwany format. Wgraj plik PDF lub Word (DOCX).")
    limit = int(settings.pliki.max_mb * 1024 * 1024)
    dane = await plik.read(limit + 1)
    if len(dane) > limit:
        raise HTTPException(413, f"Plik jest za duży (maks. {settings.pliki.max_mb:g} MB).")
    try:
        odczyt = await run_in_threadpool(ekstrakcja.odczytaj, nazwa, dane)
    except ekstrakcja.NieobslugiwanyFormat as exc:
        raise HTTPException(415, str(exc)) from exc
    return nazwa, dane, odczyt


# ---------- sprawy ----------
@router.get("/sprawy", response_model=list[SprawaLista])
async def lista(d: Dzis, rok: int | None = None, otwarte: bool = False):
    return repo.lista_spraw(d, rok=rok, otwarte=otwarte)


@router.get("/sprawy/{sid}", response_model=SprawaSzczegoly)
async def szczegoly(sid: int, d: Dzis):
    return _sprawa(sid, d)


@router.post("/sprawy", response_model=SprawaSzczegoly, status_code=status.HTTP_201_CREATED)
async def utworz(body: SprawaUtworz, d: Dzis):
    if repo.znak_istnieje(body.znak):
        raise HTTPException(409, f"Sprawa {body.znak} już istnieje.")
    if body.data_wplywu > d:
        raise HTTPException(422, "Data wpływu nie może być z przyszłości.")
    sid = repo.utworz_sprawe(body.znak, body.data_wplywu, body.wnioskodawca, body.przedmiot,
                             body.inicjaly)
    return _sprawa(sid, d)


@router.patch("/sprawy/{sid}", response_model=SprawaSzczegoly)
async def edytuj(sid: int, body: SprawaEdytuj, d: Dzis, admin: Administrator):
    """Poprawa danych wniosku (znak, data wpływu, wnioskodawca, przedmiot, inicjały) – administrator."""
    s = _sprawa(sid, d)
    pola = body.model_dump(exclude_unset=True)
    if pola.get("znak") not in (None, s.znak) and repo.znak_istnieje(pola["znak"]):
        raise HTTPException(409, f"Sprawa {pola['znak']} już istnieje.")
    if pola.get("znak") is None:
        pola.pop("znak", None)
    if (wplyw := pola.get("data_wplywu")) is not None:
        if wplyw > d:
            raise HTTPException(422, "Data wpływu nie może być z przyszłości.")
        pozniejsze = [z.data for z in s.zdarzenia if z.typ != TypZdarzenia.REJESTRACJA]
        if pozniejsze and wplyw > min(pozniejsze):
            raise HTTPException(422, f"Data wpływu nie może być późniejsza niż pierwsze zdarzenie ({min(pozniejsze)}).")
    else:
        pola.pop("data_wplywu", None)
    for k in ("wnioskodawca", "przedmiot"):
        if pola.get(k) is None:
            pola.pop(k, None)
    if "inicjaly" in pola:
        pola["inicjaly"] = pola["inicjaly"] or None
    stare = s.model_dump(mode="json")
    zmiany = {k: [stare[k], v.isoformat() if isinstance(v, date) else v]
              for k, v in pola.items() if (v.isoformat() if isinstance(v, date) else v) != stare[k]}
    if not zmiany:
        return s
    repo.edytuj_sprawe(sid, pola)
    repo.dodaj_zdarzenie(sid, TypZdarzenia.SPRAWA_ZMIANA, d, payload={"zmiany": zmiany}, inicjaly=admin.login)
    return _sprawa(sid, d)


@router.post("/sprawy/{sid}/zdarzenia", response_model=SprawaSzczegoly,
             status_code=status.HTTP_201_CREATED)
async def dodaj_zdarzenie(sid: int, body: ZdarzenieDodaj, d: Dzis, u: Zalogowany):
    s = _sprawa(sid, d)
    if body.typ in terminy.TYLKO_ADMIN and u.rola != "admin":
        raise HTTPException(403, "Zamknąć lub wznowić sprawę może tylko administrator.")
    if s.zrodlo == Zrodlo.IMPORT:
        raise HTTPException(409, "Sprawa z importu archiwalnego jest zamknięta.")
    if body.typ in terminy.AUDYT:
        raise HTTPException(422, "Ten wpis historii tworzy serwer przy edycji dokumentów i spraw.")
    if s.status not in terminy.DOZWOLONE[body.typ]:
        raise HTTPException(
            409, f"Zdarzenie {body.typ.value} jest niedostępne w statusie {s.status.value}."
        )
    if body.data < s.data_wplywu:
        raise HTTPException(422, "Data zdarzenia jest wcześniejsza niż data wpływu.")
    if body.data > d:
        raise HTTPException(422, "Data zdarzenia nie może być z przyszłości.")

    payload = dict(body.payload)
    if body.typ == TypZdarzenia.PRZEDLUZENIE:
        if body.nowy_termin is None:
            raise HTTPException(422, "Podaj nowy termin.")
        if s.termin and body.nowy_termin <= s.termin:
            raise HTTPException(422, "Nowy termin musi być późniejszy niż obecny.")
        # > 2 miesiące od wpływu jest dozwolone, ale oznaczone flagą PRZEDLUZENIE_PONAD_2_MIES
    elif body.typ == TypZdarzenia.PRZEKAZANIE:
        wydzialy = [str(w).strip() for w in payload.get("wydzialy") or [] if str(w).strip()]
        if not wydzialy:
            raise HTTPException(422, "Podaj co najmniej jeden wydział.")
        payload["wydzialy"] = wydzialy
    elif body.typ == TypZdarzenia.ZAMKNIECIE:
        powod = str(payload.get("powod") or "").strip()
        if not powod:
            raise HTTPException(422, "Podaj powód zamknięcia sprawy.")
        payload = {"powod": powod[:500]}
    if body.nowy_termin is not None and body.typ not in (TypZdarzenia.PRZEDLUZENIE,
                                                         TypZdarzenia.WEZWANIE_DOPRECYZOWANIE):
        raise HTTPException(422, "Nowy termin można podać tylko przy przedłużeniu lub wezwaniu.")

    # zamknięcie / wznowienie: w historii zawsze login administratora (nie dane z przeglądarki)
    inicjaly = u.login if body.typ in terminy.TYLKO_ADMIN else body.inicjaly or None
    repo.dodaj_zdarzenie(sid, body.typ, body.data, body.nowy_termin, payload, inicjaly)
    return _sprawa(sid, d)


# ---------- dokumenty ----------
# ---------- odczyt bez zapisu (przed anonimizacją) ----------
# Oryginał jest przetwarzany tylko w pamięci – nie trafia do bazy ani na dysk. Do systemu
# zapisuje się wersja zanonimizowana: POST /sprawy/{id}/dokumenty z plikiem .txt.
def _odczyt(nazwa: str, odczyt: ekstrakcja.Odczyt) -> Odczyt:
    return Odczyt(nazwa_pliku=nazwa, metoda=odczyt.metoda, ocr_pewnosc=odczyt.ocr_pewnosc,
                  tekst=odczyt.tekst)


@router.post("/dokumenty/odczyt", response_model=Odczyt)
async def odczytaj_dokument(plik: UploadFile = File(...)):
    """Tekst dokumentu (TXT / DOCX / PDF / OCR) bez zapisu."""
    nazwa, _, odczyt = await _wczytaj_plik(plik)
    return _odczyt(nazwa, odczyt)


@router.post("/wnioski/odczyt", response_model=OdczytWniosku)
async def odczytaj_wniosek(d: Dzis, plik: UploadFile = File(...)):
    """Tekst wniosku bez zapisu + propozycja danych sprawy (znak, wnioskodawca, przedmiot)."""
    nazwa, _, odczyt = await _wczytaj_plik(plik)
    propozycja = await analiza.zaproponuj(nazwa, odczyt.tekst, d)
    return OdczytWniosku(odczyt=_odczyt(nazwa, odczyt), propozycja=propozycja)


def sprawdz_anonimizacje(tekst: str) -> None:
    """Ostatnia linia obrony: nie zapisujemy tekstu z niezamazanym PESEL / numerem dowodu."""
    if znalezione := anonimizacja.niezamazane_identyfikatory(tekst):
        raise HTTPException(
            422, f"Dokument zawiera niezamazane dane: {', '.join(znalezione)}. "
                 "Zamaż je w kroku anonimizacji przed zapisem.")


@router.post("/sprawy/{sid}/dokumenty", response_model=Dokument,
             status_code=status.HTTP_201_CREATED)
async def dodaj_dokument(
    sid: int, d: Dzis, u: Zalogowany,
    plik: UploadFile = File(...),
    rodzaj: str = Form("INNE", max_length=RODZAJ_MAX),
    wydzial: str | None = Form(None, max_length=WYDZIAL_MAX),
):
    """Zapis dokumentu sprawy. Frontend wysyła tu wyłącznie tekst po anonimizacji (.txt)."""
    _sprawa(sid, d)
    nazwa, dane, odczyt = await _wczytaj_plik(plik)
    sprawdz_anonimizacje(odczyt.tekst)
    doc = repo.zapisz_dokument(nazwa, dane, rodzaj.strip().upper() or "INNE", odczyt.metoda,
                               odczyt.tekst, odczyt.ocr_pewnosc, sprawa_id=sid,
                               wydzial=(wydzial or "").strip().upper() or None)
    # historia: kto i kiedy dodał dokument (login z sesji)
    repo.dodaj_zdarzenie(sid, TypZdarzenia.DOKUMENT_DODANIE, d, inicjaly=u.login,
                         payload={"dokument": doc.nazwa_pliku, "rodzaj": doc.rodzaj})
    return doc


@router.patch("/dokumenty/{did}", response_model=Dokument)
async def edytuj_dokument(did: int, body: DokumentPopraw, d: Dzis, admin: Administrator):
    """Edycja tekstu / rodzaju / nazwy / wydziału dokumentu – administrator."""
    doc = repo.dokument(did)
    if doc is None:
        raise HTTPException(404, "Nie znaleziono dokumentu.")
    pola = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "tekst" in pola and doc.sprawa_id is not None:  # baza wiedzy – bez anonimizacji
        sprawdz_anonimizacje(pola["tekst"])
    if "rodzaj" in pola:
        pola["rodzaj"] = pola["rodzaj"].upper()
    if "wydzial" in pola:
        pola["wydzial"] = pola["wydzial"].upper() or None
    stare = doc.model_dump()
    pola = {k: v for k, v in pola.items() if v != stare[k]}
    if not pola:
        return doc
    repo.edytuj_dokument(did, pola)
    if doc.sprawa_id is not None:  # historia sprawy; tekst bez treści (długi, może być wrażliwy)
        zmiany = {k: ([stare[k], v] if k != "tekst" else [len(stare[k]), len(v)]) for k, v in pola.items()}
        repo.dodaj_zdarzenie(doc.sprawa_id, TypZdarzenia.DOKUMENT_ZMIANA, d, inicjaly=admin.login,
                             payload={"dokument": doc.nazwa_pliku, "zmiany": zmiany})
    return repo.dokument(did)


@router.delete("/dokumenty/{did}", status_code=status.HTTP_204_NO_CONTENT)
async def usun_dokument(did: int, d: Dzis, admin: Administrator):
    """Usunięcie dokumentu sprawy (np. wgrany omyłkowo) – administrator. Historia zdarzeń zostaje,
    a usunięcie trafia do niej z loginem administratora."""
    doc = repo.dokument(did)
    if doc is None or not repo.usun_dokument(did):
        raise HTTPException(404, "Nie znaleziono dokumentu.")
    if doc.sprawa_id is not None:
        repo.dodaj_zdarzenie(doc.sprawa_id, TypZdarzenia.DOKUMENT_USUNIECIE, d, inicjaly=admin.login,
                             payload={"dokument": doc.nazwa_pliku, "rodzaj": doc.rodzaj})

