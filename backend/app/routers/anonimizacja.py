"""Propozycje danych do anonimizacji (frontend: AnonimizacjaPodglad.jsx)."""
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app import anonimizacja
from app.anonimizacja import Propozycje
from app.sprawy.model import TEKST_MAX, WNIOSKODAWCA_MAX

router = APIRouter(tags=["anonimizacja"])


class AnonimizacjaZapytanie(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tekst: str = Field(..., max_length=TEKST_MAX)
    wnioskodawca: str | None = Field(None, max_length=WNIOSKODAWCA_MAX)
    llm: bool = True


@router.post("/anonimizacja", response_model=Propozycje)
async def propozycje_tekstu(body: AnonimizacjaZapytanie):
    """Dowolny tekst – np. treść wniosku przed zapisem albo projekt pisma."""
    return await anonimizacja.zaproponuj(body.tekst, body.wnioskodawca, body.llm)

