"""Magazyn danych w SQLite (wątki, wiadomości, sprawy, indeks RAG).
Schemat tymczasowy – docelowy do opisania w docs/DBDOC.md."""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    create_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    id        INTEGER NOT NULL,
    role      TEXT NOT NULL,             -- msg_owner: user | assistant
    content   TEXT NOT NULL,             -- dla user: sam prompt (bez kontekstu OCR)
    timestamp TEXT NOT NULL,
    context   TEXT NOT NULL DEFAULT '[]', -- JSON: dokumenty po OCR dołączone do pytania
    PRIMARY KEY (thread_id, id)
);
CREATE TABLE IF NOT EXISTS sprawy (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    znak             TEXT NOT NULL UNIQUE,
    nr               INTEGER NOT NULL,
    rok              INTEGER NOT NULL,
    zrodlo           TEXT NOT NULL,          -- upload | import | demo
    wnioskodawca     TEXT NOT NULL DEFAULT '',
    przedmiot        TEXT NOT NULL DEFAULT '',
    data_wplywu      TEXT NOT NULL,
    inicjaly         TEXT,
    flagi            TEXT NOT NULL DEFAULT '[]',  -- JSON: uwagi z importu
    import_termin    TEXT,                   -- tylko zrodlo=import: wartości z xlsx „jak są”
    import_odpowiedz TEXT
);
CREATE TABLE IF NOT EXISTS zdarzenia (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sprawa_id   INTEGER NOT NULL REFERENCES sprawy(id) ON DELETE CASCADE,
    typ         TEXT NOT NULL,
    data        TEXT NOT NULL,
    nowy_termin TEXT,
    payload     TEXT NOT NULL DEFAULT '{}',  -- JSON
    inicjaly    TEXT
);
CREATE TABLE IF NOT EXISTS dokumenty (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sprawa_id   INTEGER REFERENCES sprawy(id) ON DELETE SET NULL,  -- NULL do zatwierdzenia sprawy
    rodzaj      TEXT NOT NULL,
    nazwa_pliku TEXT NOT NULL,
    wydzial     TEXT,
    metoda      TEXT NOT NULL,
    ocr_pewnosc REAL,
    tekst       TEXT NOT NULL,
    sciezka     TEXT NOT NULL,
    utworzono   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rag_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id       INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    message_id      INTEGER NOT NULL,
    role            TEXT NOT NULL,
    text            TEXT NOT NULL,
    embedding       BLOB,
    embedding_model TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5(
    text, content='rag_chunks', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
"""


@dataclass
class StoredMessage:
    id: int    # numer kolejny w wątku: 1, 2, 3, … (obie strony rozmowy)
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime
    context: list[str] = field(default_factory=list)


@dataclass
class Thread:
    id: int
    title: str
    create_date: datetime


class Store:
    def __init__(self) -> None:
        self.lock = RLock()
        self._conn: sqlite3.Connection | None = None

    # --- połączenie ---
    def connect(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.close()
        # TODO: przy większym ruchu – pula połączeń / async driver
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Proste migracje istniejących baz (do czasu wprowadzenia Alembica)."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(messages)")}
        if "context" not in cols:
            self._conn.execute("ALTER TABLE messages ADD COLUMN context TEXT NOT NULL DEFAULT '[]'")
            self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Baza danych niepodłączona (store.connect)")
        return self._conn

    # --- wątki ---
    @staticmethod
    def _thread(row) -> Thread:
        return Thread(row["id"], row["title"], datetime.fromisoformat(row["create_date"]))

    def create_thread(self, title: str) -> Thread:
        now = datetime.now()
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO threads (title, create_date) VALUES (?, ?)",
                (title, now.isoformat()),
            )
        return Thread(cur.lastrowid, title, now)

    def get_thread(self, thread_id: int) -> Thread | None:
        row = self.conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        return self._thread(row) if row else None

    def list_threads(self) -> list[Thread]:
        rows = self.conn.execute("SELECT * FROM threads ORDER BY id").fetchall()
        return [self._thread(r) for r in rows]

    def get_titles(self, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        rows = self.conn.execute(f"SELECT id, title FROM threads WHERE id IN ({q})", tuple(ids))
        return {r["id"]: r["title"] for r in rows}

    # --- wiadomości ---
    def get_messages(self, thread_id: int) -> list[StoredMessage]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY id", (thread_id,)
        ).fetchall()
        return [
            StoredMessage(r["id"], r["role"], r["content"], datetime.fromisoformat(r["timestamp"]),
                          json.loads(r["context"] or "[]"))
            for r in rows
        ]

    def add_message(self, thread_id: int, role: str, content: str,
                    context: list[str] | None = None) -> StoredMessage:
        now = datetime.now()
        with self.lock, self.conn:
            (next_id,) = self.conn.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            self.conn.execute(
                "INSERT INTO messages (thread_id, id, role, content, timestamp, context)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, next_id, role, content, now.isoformat(),
                 json.dumps(context or [], ensure_ascii=False)),
            )
        return StoredMessage(next_id, role, content, now, list(context or []))


store = Store()
