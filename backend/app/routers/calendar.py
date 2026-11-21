from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.formats import DATE_FMT
from app.schemas import CalendarEvent, CalendarEventCreate
from app.storage import store

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _qdate(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        raise HTTPException(422, f"Niepoprawna data '{value}', oczekiwano DD-MM-RRRR")


class CalendarFilters:
    def __init__(
        self,
        status: bool | None = Query(None, description="Czy odpowiedź wysłana"),
        initials: str | None = Query(None, examples=["ŁW"]),
        petition_id: int | None = None,
        due_from: str | None = Query(None, description="due_date >= (DD-MM-RRRR)"),
        due_to: str | None = Query(None, description="due_date <= (DD-MM-RRRR)"),
        q: str | None = Query(None, description="Szukaj w name / short_desc"),
    ):
        self.status = status
        self.initials = initials
        self.petition_id = petition_id
        self.due_from = _qdate(due_from)
        self.due_to = _qdate(due_to)
        self.q = q.lower() if q else None

    def match(self, e: CalendarEvent) -> bool:
        if self.status is not None and e.status != self.status:
            return False
        if self.initials and e.initials != self.initials:
            return False
        if self.petition_id is not None and e.petition_id != self.petition_id:
            return False
        if self.due_from and e.due_date < self.due_from:
            return False
        if self.due_to and e.due_date > self.due_to:
            return False
        if self.q and self.q not in (e.name + " " + e.short_desc).lower():
            return False
        return True


@router.get("", response_model=list[CalendarEvent])
async def list_events(filters: Annotated[CalendarFilters, Depends()]):
    events = [e for e in store.list_events() if filters.match(e)]
    return sorted(events, key=lambda e: e.due_date)


@router.post("", response_model=CalendarEvent, status_code=status.HTTP_201_CREATED)
async def create_event(body: CalendarEventCreate):
    return store.add_event(body)
