"""Propozycje danych do anonimizacji (frontend: AnonimizacjaPodglad.jsx)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import anonimizacja
from app.anonimizacja import Propozycje
from app.sprawy import repo
from app.sprawy.model import TEKST_MAX, WNIOSKODAWCA_MAX

router = APIRouter(tags=["anonimizacja"])


class AnonimizacjaZapytanie(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tekst: str = Field(..., max_length=TEKST_MAX)
    wnioskodawca: str | None = Field(None, max_length=WNIOSKODAWCA_MAX)
    llm: bool = True


@router.post("/anonimizacja", response_model=Propozycje)
async def propozycje_tekstu(body: AnonimizacjaZapytanie):
    """Dowolny tekst – np. kontekst OCR przed wysłaniem do asystenta albo projekt pisma."""
    return await anonimizacja.zaproponuj(body.tekst, body.wnioskodawca, body.llm)


@router.get("/dokumenty/{did}/anonimizacja", response_model=Propozycje)
async def propozycje_dokumentu(did: int, llm: bool = True):
    """Dokument z bazy; wnioskodawca sprawy jest dodatkowo wyszukiwany w treści."""
    doc = repo.dokument(did)
    if doc is None:
        raise HTTPException(404, "Nie znaleziono dokumentu.")
    wnioskodawca = repo.wnioskodawca(doc.sprawa_id) if doc.sprawa_id else None
    return await anonimizacja.zaproponuj(doc.tekst, wnioskodawca, llm)
