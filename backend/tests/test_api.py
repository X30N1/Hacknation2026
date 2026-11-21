from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_llm_flow():
    r = client.post("/llm/request", json={"thread_id": -1, "prompt": "Ile wniosków?", "context": ["skan 1"]})
    assert r.status_code == 200, r.text
    data = r.json()
    tid = data["thread_id"]
    assert data["message_id"] == 2  # 1 = user, 2 = assistant

    r = client.post("/llm/request", json={"thread_id": tid, "prompt": "A dalej?"})
    assert r.json()["message_id"] == 4

    threads = client.get("/llm/all").json()
    assert any(t["id"] == tid and t["title"] == "Ile wniosków?" for t in threads)

    msgs = client.get(f"/llm/{tid}").json()
    assert len(msgs) == 2

    assert client.get("/llm/9999").status_code == 404
    assert client.post("/llm/request", json={"thread_id": 9999, "prompt": "x"}).status_code == 404


def test_calendar():
    ev = {
        "name": "BKS.IV.1431.15.2026",
        "add_date": "01-11-2026",
        "due_date": "15-11-2026",
        "response_date": None,
        "status": False,
        "initials": "ŁW",
        "petition_id": 15,
        "short_desc": "Wniosek o udostępnienie umów",
        "intake_date": "01-11-2026",
    }
    r = client.post("/calendar", json=ev)
    assert r.status_code == 201, r.text
    assert r.json()["due_date"] == "15-11-2026"

    client.post("/calendar", json={**ev, "petition_id": 16, "status": True, "due_date": "30-11-2026"})

    assert len(client.get("/calendar").json()) >= 2
    assert all(e["status"] is False for e in client.get("/calendar?status=false").json())
    assert all(e["petition_id"] == 16 for e in client.get("/calendar?due_from=20-11-2026").json())
    assert client.get("/calendar?due_from=2026-11-20").status_code == 422
    assert client.post("/calendar", json={**ev, "due_date": "2026-11-15"}).status_code == 422


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
