import sqlite3
from pathlib import Path
from threading import RLock

SCHEMA = """
CREATE TABLE IF NOT EXISTS sprawy (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    znak             TEXT NOT NULL UNIQUE,
    nr               INTEGER NOT NULL,
    rok              INTEGER NOT NULL,
    zrodlo           TEXT NOT NULL,          -- upload | import
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
CREATE TABLE IF NOT EXISTS uzytkownicy (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    login              TEXT NOT NULL UNIQUE COLLATE NOCASE,
    haslo_hash         TEXT NOT NULL,
    rola               TEXT NOT NULL DEFAULT 'urzednik',  -- admin | urzednik
    musi_zmienic_haslo INTEGER NOT NULL DEFAULT 1,
    totp_sekret        TEXT,                    -- aktywny sekret TOTP
    totp_nowy          TEXT,                    -- sekret w trakcie konfiguracji (do potwierdzenia kodem)
    totp_ostatni_krok  INTEGER,                 -- ochrona przed ponownym użyciem kodu
    nieudane_proby     INTEGER NOT NULL DEFAULT 0,
    zablokowany_do     TEXT,
    utworzono          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS klucze (            -- klucze sprzętowe / passkeys (WebAuthn)
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    uzytkownik_id  INTEGER NOT NULL REFERENCES uzytkownicy(id) ON DELETE CASCADE,
    credential_id  BLOB NOT NULL UNIQUE,
    klucz_publiczny BLOB NOT NULL,
    licznik        INTEGER NOT NULL DEFAULT 0,
    nazwa          TEXT NOT NULL,
    utworzono      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sesje (
    token_hash     TEXT PRIMARY KEY,            -- SHA-256 tokenu z ciasteczka
    uzytkownik_id  INTEGER NOT NULL REFERENCES uzytkownicy(id) ON DELETE CASCADE,
    drugi_skladnik INTEGER NOT NULL DEFAULT 0,  -- 1 = TOTP / klucz potwierdzony w tej sesji
    wyzwanie       BLOB,                        -- WebAuthn: challenge bieżącej operacji
    utworzono      TEXT NOT NULL,
    wygasa         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ustawienia (         -- ustawienia zmieniane w aplikacji (JSON)
    klucz   TEXT PRIMARY KEY,
    wartosc TEXT NOT NULL
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

-- Archiwum: wyszukiwanie pełnotekstowe spraw (przedmiot, wnioskodawca) i dokumentów
-- (wyłącznie zanonimizowane teksty – oryginały nie trafiają do bazy). Synchronizacja triggerami.
CREATE VIRTUAL TABLE IF NOT EXISTS sprawy_fts USING fts5(
    przedmiot, content='sprawy', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS sprawy_fts_ai AFTER INSERT ON sprawy BEGIN
    INSERT INTO sprawy_fts (rowid, przedmiot) VALUES (new.id, new.przedmiot);
END;
CREATE TRIGGER IF NOT EXISTS sprawy_fts_ad AFTER DELETE ON sprawy BEGIN
    INSERT INTO sprawy_fts (sprawy_fts, rowid, przedmiot) VALUES ('delete', old.id, old.przedmiot);
END;
CREATE TRIGGER IF NOT EXISTS sprawy_fts_au AFTER UPDATE OF przedmiot ON sprawy BEGIN
    INSERT INTO sprawy_fts (sprawy_fts, rowid, przedmiot) VALUES ('delete', old.id, old.przedmiot);
    INSERT INTO sprawy_fts (rowid, przedmiot) VALUES (new.id, new.przedmiot);
END;
CREATE VIRTUAL TABLE IF NOT EXISTS dokumenty_fts USING fts5(
    tekst, content='dokumenty', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS dokumenty_fts_ai AFTER INSERT ON dokumenty BEGIN
    INSERT INTO dokumenty_fts (rowid, tekst) VALUES (new.id, new.tekst);
END;
CREATE TRIGGER IF NOT EXISTS dokumenty_fts_ad AFTER DELETE ON dokumenty BEGIN
    INSERT INTO dokumenty_fts (dokumenty_fts, rowid, tekst) VALUES ('delete', old.id, old.tekst);
END;
CREATE TRIGGER IF NOT EXISTS dokumenty_fts_au AFTER UPDATE OF tekst ON dokumenty BEGIN
    INSERT INTO dokumenty_fts (dokumenty_fts, rowid, tekst) VALUES ('delete', old.id, old.tekst);
    INSERT INTO dokumenty_fts (rowid, tekst) VALUES (new.id, new.tekst);
END;
"""


class Store:
    def __init__(self) -> None:
        self.lock = RLock()
        self._conn: sqlite3.Connection | None = None

    def connect(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.close()
        # TODO: przy większym ruchu – pula połączeń / async driver
        # timeout + WAL: seed (osobny proces przy starcie kontenera) i serwer piszą do tej samej bazy
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Proste migracje istniejących baz (do czasu wprowadzenia Alembica)."""
        (wersja,) = self._conn.execute("PRAGMA user_version").fetchone()
        if wersja < 1:
            # indeksy archiwum dla danych sprzed wprowadzenia triggerów
            self._conn.execute("INSERT INTO sprawy_fts (sprawy_fts) VALUES ('rebuild')")
            self._conn.execute("INSERT INTO dokumenty_fts (dokumenty_fts) VALUES ('rebuild')")
            self._conn.execute("PRAGMA user_version = 1")
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


store = Store()
