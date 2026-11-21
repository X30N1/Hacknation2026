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
