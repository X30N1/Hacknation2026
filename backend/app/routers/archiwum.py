"""Archiwum, baza wiedzy, ścieżka (wydziały), projekt odpowiedzi i eksport pism."""
import io
import re
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.routers.sprawy import Dzis, _sprawa, _wczytaj_plik, sprawdz_anonimizacje
from app.sprawy import archiwum, projekt, repo, wydzialy
from app.sprawy.model import (
    RODZAJE_WIEDZY, Dokument, PodobnaSprawa, ProjektOdpowiedzi, SugestieWydzialow, TrafienieArchiwum,
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


@router.post("/sprawy/{sid}/projekt", response_model=ProjektOdpowiedzi)
async def projekt_odpowiedzi(sid: int, d: Dzis):
    """Projekt pisma z odpowiedzi wydziałów. Niczego nie zapisuje – urzędnik sprawdza projekt,
    anonimizuje go i dopiero wtedy zapisuje (POST /sprawy/{id}/dokumenty, rodzaj PROJEKT)."""
    return await projekt.przygotuj(_sprawa(sid, d), d)


@router.get("/archiwum/szukaj", response_model=list[TrafienieArchiwum])
async def szukaj(q: str = Query(..., min_length=2, max_length=FRAZA_MAX)):
    return archiwum.szukaj(q)


# ---------- baza wiedzy ----------
@router.get("/wiedza", response_model=list[WiedzaDokument])
async def lista_wiedzy():
    return archiwum.lista_wiedzy()


@router.get("/wiedza/rodzaje")
async def rodzaje_wiedzy() -> dict[str, str]:
    return RODZAJE_WIEDZY


@router.post("/wiedza", response_model=Dokument, status_code=status.HTTP_201_CREATED)
async def dodaj_wiedze(plik: UploadFile = File(...), rodzaj: str = Form(...)):
    """Ustawa, zarządzenie, wzór pisma albo archiwalne pismo – materiał dla wyszukiwarki
    i projektów odpowiedzi. Frontend wysyła tekst po anonimizacji."""
    rodzaj = rodzaj.strip().upper()
    if rodzaj not in RODZAJE_WIEDZY:
        raise HTTPException(422, f"Nieznany rodzaj. Dozwolone: {', '.join(RODZAJE_WIEDZY)}.")
    nazwa, dane, odczyt = await _wczytaj_plik(plik)
    if not odczyt.tekst.strip():
        raise HTTPException(422, "Plik nie zawiera tekstu.")
    sprawdz_anonimizacje(odczyt.tekst)
    return repo.zapisz_dokument(nazwa, dane, rodzaj, odczyt.metoda, odczyt.tekst, odczyt.ocr_pewnosc)


@router.delete("/wiedza/{did}", status_code=status.HTTP_204_NO_CONTENT)
async def usun_wiedze(did: int):
    """Np. przy aktualizacji ustawy – stara wersja znika z wyszukiwania."""
    if not archiwum.usun_wiedze(did):
        raise HTTPException(404, "Nie znaleziono dokumentu w bazie wiedzy.")


# ---------- eksport ----------
@router.get("/dokumenty/{did}/docx")
async def dokument_docx(did: int):
    """Tekst dokumentu (zanonimizowany, jak w bazie) jako plik Word."""
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
