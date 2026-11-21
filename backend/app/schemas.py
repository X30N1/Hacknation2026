from pydantic import BaseModel, Field

from app.formats import ApiDate, ApiTimestamp


# ---------- LLM ----------
class LLMRequest(BaseModel):
    thread_id: int = Field(-1, description="ID rozmowy; -1 tworzy nowy wątek")
    prompt: str = Field(..., min_length=1, description="Prośba bazowa użytkownika")
    context: list[str] = Field(
        default_factory=list,
        description="Teksty po OCR wykonanym lokalnie u użytkownika",
    )


class LLMResponse(BaseModel):
    thread_id: int
    message_id: int
    content: str
    timestamp: ApiTimestamp


class ThreadSummary(BaseModel):
    id: int
    title: str
    create_date: ApiTimestamp


class Message(BaseModel):
    id: int
    content: str
    timestamp: ApiTimestamp


SHORT_DESC_MAX = 500  # TODO: ustalić docelowy limit


class CalendarEventBase(BaseModel):
    name: str
    add_date: ApiDate
    due_date: ApiDate
    response_date: ApiDate | None = None
    status: bool = Field(False, description="Czy odpowiedź została wysłana")
    initials: str = Field(..., max_length=5, examples=["ŁW"])
    petition_id: int
    short_desc: str = Field(..., max_length=SHORT_DESC_MAX)
    intake_date: ApiDate


class CalendarEventCreate(CalendarEventBase):
    pass


class CalendarEvent(CalendarEventBase):
    id: int
