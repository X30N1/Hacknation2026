"""Archiwum, baza wiedzy, ścieżka (wydziały), projekty pism i eksport pism."""
import asyncio
import io
import re
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.routers.sprawy import Dzis, _sprawa, _wczytaj_plik
from app.sprawy import archiwum, projekt, repo, wydzialy
from app.sprawy.model import (
    RODZAJE_WIEDZY, Dokument, DraftPisma, PodobnaSprawa, ProjektPisma, SugestieWydzialow, TrafienieArchiwum,
    WiedzaDokument,
)

router = APIRouter(tags=["archiwum"])

FRAZA_MAX = 500  # TODO: limit – długość frazy wyszukiwania


@router.get("/sprawy/{sid}/podobne", response_model=list[PodobnaSprawa])
async def podobne(sid: int, d: Dzis, limit: int = Query(5, ge=1, le=20)):
    """Podobne sprawy z archiwum (przedmiot + treść zanonimizowanych dokumentów), bez LLM."""
    _sprawa(sid, d)
    return archiwum.podobne(sid, d, limit)


@router.get("/sprawy/{sid}/wydzialy", response_model=SugestieWydzialow)
async def sugestie_wydzialow(sid: int, d: Dzis):
    """Propozycje jednostek UMB, do których wysłać prośbę o odpowiedź – z uzasadnieniem."""
    _sprawa(sid, d)
    return await wydzialy.zaproponuj(sid, d)


async def do_rozlaczenia(request: Request, zadanie, co: float = 0.5):
    """Wynik korutyny; gdy klient przerwie zapytanie (przycisk „Anuluj” – fetch abort), generacja
    w LLM jest przerywana (zamknięte połączenie z modelem), a nie liczy się dalej w tle."""
    task = asyncio.ensure_future(zadanie)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=co)
            if done:
                return task.result()
            if await request.is_disconnected():
                task.cancel()
                raise HTTPException(499, "Anulowano.")
    finally:
        if not task.done():
            task.cancel()


@router.post("/sprawy/{sid}/draft", response_model=ProjektPisma)
async def draft_pisma(sid: int, body: DraftPisma, d: Dzis, request: Request):
    """Projekt pisma (odpowiedź, wezwanie, zapytanie do wydziałów, przedłużenie). Niczego nie zapisuje –
    urzędnik sprawdza projekt, anonimizuje go i dopiero wtedy zapisuje (POST /sprawy/{id}/dokumenty)."""
    s = _sprawa(sid, d)
    return await do_rozlaczenia(
        request, projekt.przygotuj(s, d, body.rodzaj, body.wydzialy, body.nowy_termin))


@router.get("/archiwum/szukaj", response_model=list[TrafienieArchiwum])
async def szukaj(q: str = Query(..., min_length=2, max_length=FRAZA_MAX)):
    return archiwum.szukaj(q)


# ---------- baza wiedzy ----------
@router.get("/wiedza", response_model=list[WiedzaDokument])
async def lista_wiedzy():
    return archiwum.lista_wiedzy()


@router.post("/wiedza", response_model=Dokument, status_code=status.HTTP_201_CREATED)
async def dodaj_wiedze(plik: UploadFile = File(...), rodzaj: str = Form(...)):
    """Ustawa, zarządzenie, wzór pisma albo archiwalne pismo – materiał dla wyszukiwarki
    i projektów odpowiedzi. Bez anonimizacji – to materiały źródłowe, zapisywane w całości."""
    rodzaj = rodzaj.strip().upper()
    if rodzaj not in RODZAJE_WIEDZY:
        raise HTTPException(422, f"Nieznany rodzaj. Dozwolone: {', '.join(RODZAJE_WIEDZY)}.")
    nazwa, dane, odczyt = await _wczytaj_plik(plik)
    if not odczyt.tekst.strip():
        raise HTTPException(422, "Plik nie zawiera tekstu.")
    return repo.zapisz_dokument(nazwa, dane, rodzaj, odczyt.metoda, odczyt.tekst, odczyt.ocr_pewnosc)


@router.get("/wiedza/{did}", response_model=Dokument)
async def czytaj_wiedze(did: int):
    """Pełny tekst dokumentu z bazy wiedzy (jak w bazie)."""
    doc = archiwum.wiedza(did)
    if doc is None:
        raise HTTPException(404, "Nie znaleziono dokumentu w bazie wiedzy.")
    return doc


@router.delete("/wiedza/{did}", status_code=status.HTTP_204_NO_CONTENT)
async def usun_wiedze(did: int):
    """Np. przy aktualizacji ustawy – stara wersja znika z wyszukiwania."""
    if not archiwum.usun_wiedze(did):
        raise HTTPException(404, "Nie znaleziono dokumentu w bazie wiedzy.")


# ---------- eksport ----------
@router.get("/dokumenty/{did}/docx")
async def dokument_docx(did: int):
    """Tekst dokumentu (jak w bazie: dokumenty spraw zanonimizowane, baza wiedzy w całości) jako plik Word."""
    import docx

    doc = repo.dokument(did)
    if doc is None:
        raise HTTPException(404, "Nie znaleziono dokumentu.")
    plik = docx.Document()
    for akapit in doc.tekst.split("\n"):
        plik.add_paragraph(akapit)
    buf = io.BytesIO()
    plik.save(buf)
    nazwa = re.sub(r"\.[^.]+$", "", doc.nazwa_pliku) + ".docx"
    return StreamingResponse(
        io.BytesIO(buf.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nazwa)}"},
    )
