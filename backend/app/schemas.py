from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.formats import ApiTimestamp

PROMPT_MAX = 20_000         # TODO: limit – znaki w prompt
CONTEXT_ITEMS_MAX = 50      # TODO: limit – liczba dokumentów w context
CONTEXT_ITEM_MAX = 200_000  # TODO: limit – znaki w jednym dokumencie po OCR


class LLMRequest(BaseModel):
    thread_id: int = Field(-1, description="ID rozmowy; -1 tworzy nowy wątek")
    prompt: str = Field(
        ..., min_length=1, max_length=PROMPT_MAX, description="Prośba bazowa użytkownika"
    )
    context: list[Annotated[str, Field(max_length=CONTEXT_ITEM_MAX)]] = Field(
        default_factory=list,
        max_length=CONTEXT_ITEMS_MAX,
        description="Teksty po OCR wykonanym lokalnie u użytkownika",
    )


class LLMHealth(BaseModel):
    status: Literal["ok", "echo", "error"]
    model: str
    base_url: str
    latency_ms: int | None = None
    detail: str | None = None


class Source(BaseModel):
    """Fragment wcześniejszej rozmowy użyty przez RAG."""

    thread_id: int
    message_id: int
    title: str
    snippet: str
    score: float


class LLMResponse(BaseModel):
    thread_id: int
    message_id: int
    content: str
    timestamp: ApiTimestamp
    sources: list[Source] = Field(
        default_factory=list, description="Fragmenty wcześniejszych rozmów użyte w odpowiedzi"
    )


class ThreadSummary(BaseModel):
    id: int
    title: str
    create_date: ApiTimestamp


class Message(BaseModel):
    id: int
    content: str
    timestamp: ApiTimestamp
