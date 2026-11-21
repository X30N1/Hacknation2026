from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


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


def test_is_local(monkeypatch):
    from app import llm_client
    from app.config import settings

    for url, lokalny in [
        ("http://ollama:11434/v1", True),             # usługa w docker compose
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:11434/v1", True),
        ("http://192.168.1.10:11434/v1", True),
        ("https://api.deepseek.com", False),
        ("http://8.8.8.8/v1", False),
        ("", False),
    ]:
        monkeypatch.setattr(settings.llm, "base_url", url)
        assert llm_client.is_local() is lokalny, url
