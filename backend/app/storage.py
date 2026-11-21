from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from threading import Lock

from app.schemas import CalendarEvent, CalendarEventCreate


@dataclass
class StoredMessage:
    id: int
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime


@dataclass
class Thread:
    id: int
    title: str
    create_date: datetime
    messages: list[StoredMessage] = field(default_factory=list)


class Store:
    def __init__(self) -> None:
        self._lock = Lock()
        self._thread_ids = count(1)
        self._event_ids = count(1)
        self.threads: dict[int, Thread] = {}
        self.events: dict[int, CalendarEvent] = {}

    # --- wątki ---
    def create_thread(self, title: str) -> Thread:
        with self._lock:
            tid = next(self._thread_ids)
            thread = Thread(id=tid, title=title, create_date=datetime.now())
            self.threads[tid] = thread
            return thread

    def add_message(self, thread: Thread, role: str, content: str) -> StoredMessage:
        with self._lock:
            msg = StoredMessage(
                id=len(thread.messages) + 1,
                role=role,
                content=content,
                timestamp=datetime.now(),
            )
            thread.messages.append(msg)
            return msg

    # --- kalendarz ---
    def add_event(self, data: CalendarEventCreate) -> CalendarEvent:
        with self._lock:
            eid = next(self._event_ids)
            event = CalendarEvent(id=eid, **dict(data))
            self.events[eid] = event
            return event


store = Store()
