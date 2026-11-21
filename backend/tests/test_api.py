from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_llm_flow():
    r = client.post("/llm/request", json={"thread_id": -1, "prompt": "Ile wniosków?", "context": ["skan 1"]})
    assert r.status_code == 200, r.text
    data = r.json()
    tid = data["thread_id"]
    assert (data["message_id"], data["msg_owner"]) == (2, "assistant")  # 1 = pytanie urzędnika

    r = client.post("/llm/request", json={"thread_id": tid, "prompt": "A dalej?"})
    assert (r.json()["message_id"], r.json()["msg_owner"]) == (4, "assistant")

    threads = client.get("/llm/all").json()
    assert any(t["id"] == tid and t["title"] == "Ile wniosków?" for t in threads)

    msgs = client.get(f"/llm/{tid}").json()
    assert [(m["message_id"], m["msg_owner"]) for m in msgs] == \
        [(1, "user"), (2, "assistant"), (3, "user"), (4, "assistant")]
    # urzędnik widzi swój prompt – bez doklejonego tekstu OCR
    assert msgs[0]["content"] == "Ile wniosków?" and msgs[2]["content"] == "A dalej?"
    assert msgs[1]["content"].startswith("[echo] Kontekst (dokumenty po OCR):\nskan 1")

    assert client.get("/llm/9999").status_code == 404
    assert client.post("/llm/request", json={"thread_id": 9999, "prompt": "x"}).status_code == 404


def test_llm_health_echo():
    r = client.get("/llm/health")
    assert r.status_code == 200
    assert r.json()["status"] == "echo"


def test_llm_health_error(monkeypatch):
    from app import llm_client

    async def broken():
        return {"status": "error", "model": "x", "base_url": "y", "detail": "down"}

    monkeypatch.setattr(llm_client, "health", broken)
    assert client.get("/llm/health").status_code == 503


def test_title_from_llm(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(llm_client, "is_echo_mode", lambda: False)

    async def fake_chat(messages, tools=None, **params):
        if "tytuł" in messages[-1]["content"]:
            return {"role": "assistant", "content": '"Wydatki na oświetlenie uliczne."'}
        return {"role": "assistant", "content": "Właściwy będzie Wydział Gospodarki Komunalnej."}

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    tid = client.post("/llm/request", json={"prompt": "Ile miasto wydało na latarnie?"}).json()["thread_id"]
    title = next(t["title"] for t in client.get("/llm/all").json() if t["id"] == tid)
    assert title == "Wydatki na oświetlenie uliczne"


def test_health_frontend_shape(monkeypatch):
    from app.config import settings

    llm = client.get("/health").json()["llm"]
    assert llm == {"backend": "echo", "model": "deepseek-chat", "dostepny": False,
                   "zewnetrzny": False, "detail": llm["detail"]}

    from app import llm_client

    async def ok():
        return {"status": "ok", "model": "deepseek-chat", "base_url": "x"}

    monkeypatch.setattr(settings.llm, "api_key", "sk-test")
    monkeypatch.setattr(llm_client, "health", ok)
    assert client.get("/health").json()["llm"]["dostepny"] is True
    assert client.get("/health").json()["llm"]["zewnetrzny"] is True

    monkeypatch.setattr(settings.llm, "base_url", "http://192.168.1.10:11434/v1")
    assert client.get("/health").json()["llm"]["zewnetrzny"] is False


def test_kontekst_ocr_trafia_do_historii_llm(monkeypatch):
    """Kontekst zapisany osobno nadal jest wysyłany do LLM w kolejnych pytaniach wątku."""
    from app import llm_client

    tid = client.post("/llm/request", json={"prompt": "Streść", "context": ["TREŚĆ WNIOSKU"]}).json()["thread_id"]
    monkeypatch.setattr(llm_client, "is_echo_mode", lambda: False)
    seen = {}

    async def fake_chat(messages, tools=None, **params):
        seen["messages"] = messages
        return {"role": "assistant", "content": "ok"}

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    client.post("/llm/request", json={"thread_id": tid, "prompt": "A kto pyta?"})
    hist = [m for m in seen["messages"] if m["role"] != "system"]
    assert [m["role"] for m in hist] == ["user", "assistant", "user"]
    assert "TREŚĆ WNIOSKU" in hist[0]["content"] and hist[0]["content"].endswith("Streść")
    assert hist[2]["content"] == "A kto pyta?"


def test_migracja_starej_bazy(tmp_path):
    """Baza sprzed kolumny messages.context otwiera się i działa."""
    import sqlite3

    from app.storage import store

    db = tmp_path / "stara.db"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE threads (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                              create_date TEXT NOT NULL);
        CREATE TABLE messages (thread_id INTEGER NOT NULL, id INTEGER NOT NULL, role TEXT NOT NULL,
                               content TEXT NOT NULL, timestamp TEXT NOT NULL, PRIMARY KEY (thread_id, id));
        INSERT INTO threads VALUES (1, 'Stary', '2026-11-20T10:00:00');
        INSERT INTO messages VALUES (1, 1, 'user', 'pytanie', '2026-11-20T10:00:00');
    """)
    c.commit()
    c.close()
    store.connect(db)
    assert store.get_messages(1)[0].context == []
    assert client.get("/llm/1").json()[0]["msg_owner"] == "user"
