"""Kontrakt API spraw – zgodny z frontendem (frontend/src/api/client.js).
Daty jako 'RRRR-MM-DD' (ISO)."""
import re
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

ZNAK_RE = re.compile(r"^BKS\.IV\.1431\.(\d+)\.(\d{4})$")
ZNAK_W_TEKSCIE_RE = re.compile(r"BKS\.IV\.1431\.\d+\.\d{4}")

INICJALY_MAX = 20       # TODO: limit (frontend: maxLength 10, import xlsx: „Pracownik 1”)
WNIOSKODAWCA_MAX = 300  # TODO: limit
PRZEDMIOT_MAX = 2000    # TODO: limit (frontend proponuje 160 znaków z treści)
TEKST_MAX = 1_000_000   # TODO: limit – tekst dokumentu po OCR


class Status(StrEnum):
    NOWY = "NOWY"                      # a) brak działań
    W_WYDZIALACH = "W_WYDZIALACH"      # b) zapytania w wydziałach
    DOPRECYZOWANIE = "DOPRECYZOWANIE"
    PRZEDLUZONA = "PRZEDLUZONA"        # c) kwerenda / przedłużenie
    PROJEKT_GOTOWY = "PROJEKT_GOTOWY"  # d) odpowiedź przygotowana
    WYSLANA = "WYSLANA"                # e) odpowiedź wysłana
    BEZ_ROZPOZNANIA = "BEZ_ROZPOZNANIA"


class Pilnosc(StrEnum):
    PRZEKROCZONY = "PRZEKROCZONY"
    DZIS = "DZIS"
    JUTRO = "JUTRO"
    WKROTCE = "WKROTCE"
    BRAK = "BRAK"
    ZAMKNIETA = "ZAMKNIETA"


class TypZdarzenia(StrEnum):
    REJESTRACJA = "REJESTRACJA"
    PRZEKAZANIE = "PRZEKAZANIE"
    ODP_WYDZIALU = "ODP_WYDZIALU"
    WEZWANIE_DOPRECYZOWANIE = "WEZWANIE_DOPRECYZOWANIE"
    DOPRECYZOWANIE_OTRZYMANE = "DOPRECYZOWANIE_OTRZYMANE"
    PRZEDLUZENIE = "PRZEDLUZENIE"
    PROJEKT = "PROJEKT"
    WYSLANO = "WYSLANO"
    BEZ_ROZPOZNANIA = "BEZ_ROZPOZNANIA"


class Metoda(StrEnum):
    DOCX = "DOCX"
    PDF_TEXT = "PDF_TEXT"
    OCR = "OCR"
    RECZNA = "RECZNA"


class Zrodlo(StrEnum):
    UPLOAD = "upload"
    IMPORT = "import"


class Flaga(BaseModel):
    kod: str
    opis: str
    propozycja: str | None = None


class Zdarzenie(BaseModel):
    id: int
    typ: TypZdarzenia
    data: date
    nowy_termin: date | None = None
    payload: dict[str, Any] = {}
    inicjaly: str | None = None


class Dokument(BaseModel):
    id: int
    sprawa_id: int | None
    rodzaj: str
    nazwa_pliku: str
    wydzial: str | None = None
    metoda: Metoda
    ocr_pewnosc: float | None = None
    tekst: str


class SprawaLista(BaseModel):
    id: int
    znak: str
    nr: int
    rok: int
    zrodlo: Zrodlo
    wnioskodawca: str
    przedmiot: str
    data_wplywu: date
    termin: date | None
    termin_wstrzymany: bool
    status: Status
    pilnosc: Pilnosc
    pozostalo_dni: int | None
    przedluzenie_dni: int | None
    data_odpowiedzi: date | None
    inicjaly: str | None
    flagi: list[Flaga]


class SprawaSzczegoly(SprawaLista):
    zdarzenia: list[Zdarzenie]
    dokumenty: list[Dokument]


# ---------- wejście ----------
class _Wejscie(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SprawaUtworz(_Wejscie):
    znak: str
    data_wplywu: date
    wnioskodawca: str = Field("", max_length=WNIOSKODAWCA_MAX)
    przedmiot: str = Field("", max_length=PRZEDMIOT_MAX)
    inicjaly: str | None = Field(None, max_length=INICJALY_MAX)

    @field_validator("znak")
    @classmethod
    def _znak(cls, v: str) -> str:
        if not ZNAK_RE.match(v):
            raise ValueError("Numer sprawy musi mieć format BKS.IV.1431.<nr>.<rok>.")
        return v

    @field_validator("inicjaly")
    @classmethod
    def _puste(cls, v):
        return v or None


class ZdarzenieDodaj(_Wejscie):
    typ: TypZdarzenia
    data: date
    nowy_termin: date | None = None
    payload: dict[str, Any] = {}
    inicjaly: str | None = Field(None, max_length=INICJALY_MAX)


class DokumentPopraw(_Wejscie):
    tekst: str = Field(..., max_length=TEKST_MAX)


class Propozycja(BaseModel):
    znak: str
    data_wplywu: date
    wnioskodawca: str
    przedmiot: str


class Odczyt(BaseModel):
    """Tekst odczytany z pliku – nic nie jest zapisywane (POST /dokumenty/odczyt)."""
    nazwa_pliku: str
    metoda: Metoda
    ocr_pewnosc: float | None = None
    tekst: str


class OdczytWniosku(BaseModel):
    odczyt: Odczyt
    propozycja: Propozycja


# ---------- archiwum, baza wiedzy, wydziały, projekt odpowiedzi ----------
# Dokumenty bazy wiedzy nie należą do sprawy (sprawa_id = NULL).
RODZAJE_WIEDZY = {
    "USTAWA": "Ustawa / przepis",
    "ZARZADZENIE": "Zarządzenie / instrukcja",
    "WZOR": "Wzór pisma",
    "ARCHIWUM": "Archiwalne pismo",
}


class PodobnaSprawa(BaseModel):
    id: int
    znak: str
    przedmiot: str
    data_wplywu: date
    status: Status
    wydzialy: list[str]        # wydziały, które odpowiadały / do których przekazano sprawę
    fragment: str              # dopasowany fragment (z [ ] wokół trafionych słów)
    ma_odpowiedz: bool         # czy w sprawie jest dokument odpowiedzi do wykorzystania


class TrafienieArchiwum(BaseModel):
    sprawa_id: int | None
    znak: str | None
    dokument_id: int | None
    nazwa_pliku: str | None
    rodzaj: str                # SPRAWA albo rodzaj dokumentu
    data: date | None
    fragment: str


class WiedzaDokument(BaseModel):
    id: int
    rodzaj: str
    nazwa_pliku: str
    znaki: int
    utworzono: str


class SugestiaWydzialu(BaseModel):
    skrot: str
    nazwa: str
    uzasadnienie: str
    zrodlo: str                # ARCHIWUM | SLOWA_KLUCZOWE | LLM


class SugestieWydzialow(BaseModel):
    sugestie: list[SugestiaWydzialu]
    wszystkie: list[dict[str, str]]  # pełna lista wydziałów i biur UMB (skrot, nazwa)


class ProjektOdpowiedzi(BaseModel):
    tekst: str
    llm_uzyty: bool
    zrodla: list[str]          # z czego powstał projekt – do weryfikacji przez urzędnika
    uwagi: list[str] = []
