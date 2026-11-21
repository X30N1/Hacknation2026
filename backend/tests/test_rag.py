import json

import pytest
from fastapi.testclient import TestClient

from app import llm_client, rag
from app.config import settings
from app.storage import store
from main import app

client = TestClient(app)


async def _seed():
    a = store.create_thread("Oświetlenie uliczne")
    store.add_message(a.id, "user", "Wniosek o koszty oświetlenia ulicznego w 2025 r.")
    await rag.index_message(a.id, 1, "user",
                            "Wniosek o koszty oświetlenia ulicznego w 2025 r.")
    await rag.index_message(a.id, 2, "assistant",
                            "Właściwy jest Wydział Gospodarki Komunalnej.")
    b = store.create_thread("Umowy na sprzątanie")
    await rag.index_message(b.id, 1, "user", "Proszę o kopie umów na sprzątanie budynków.")
    return a, b


def test_chunk_text():
    assert rag.chunk_text("krótki") == ["krótki"]
    assert rag.chunk_text("   ") == []
    text = " ".join(f"zdanie{i}." for i in range(500))
    chunks = rag.chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 1 and all(len(c) <= 300 for c in chunks)
    assert chunks[0].split()[-1] in chunks[1]  # zakładka


def test_fts_query_stems_and_drops_stopwords():
    assert rag.fts_query("czy jest umowa?") == '"umowa"*'
    assert rag.fts_query("oświetlenia ulicznego") == '"oświe"* OR "ulicz"*'
    assert rag.fts_query("a i o") is None


@pytest.mark.anyio
async def test_lexical_search_inflection_and_exclude():
    a, b = await _seed()
    hits = await rag.search("oświetlenie uliczne")  # inna odmiana niż w tekście
    assert hits and hits[0].thread_id == a.id and hits[0].title == "Oświetlenie uliczne"

    hits = await rag.search("umowa sprzątania")
    assert hits[0].thread_id == b.id

    assert await rag.search("oświetlenie", exclude_thread=a.id) == []


@pytest.mark.anyio
async def test_vector_search(monkeypatch):
    monkeypatch.setattr(settings.rag.embeddings, "base_url", "http://fake")

    vocab = ["latarnie", "umowy", "drogi"]

    async def fake_embed(texts):
        return [[float(w in t.lower()) + 0.01 for w in vocab] for t in texts]

    monkeypatch.setattr(rag, "embed", fake_embed)
    t = store.create_thread("Latarnie")
    await rag.index_message(t.id, 1, "user", "Ile latarnie zużywają prądu?")
    t2 = store.create_thread("Drogi")
    await rag.index_message(t2.id, 1, "user", "Remonty: drogi gminne")

    # brak wspólnego słowa w FTS dla "latarnie" vs zapytanie -> trafienie tylko z wektorów
    monkeypatch.setattr(rag, "fts_query", lambda q: None)
    hits = await rag.search("latarnie")
    assert hits[0].thread_id == t.id


@pytest.mark.anyio
async def test_embedding_failure_falls_back_to_fts(monkeypatch):
    monkeypatch.setattr(settings.rag.embeddings, "base_url", "http://127.0.0.1:9")
    a, _ = await _seed()
    assert (await rag.search("oświetlenie"))[0].thread_id == a.id


def test_tool_calling_flow(monkeypatch):
    """Model wywołuje search_conversations, dostaje wyniki i odpowiada ze źródłami."""
    old = client.post("/llm/request", json={"prompt": "Kto odpowiada za oświetlenie uliczne?"})
    old_tid = old.json()["thread_id"]  # zaindeksowane w background task

    monkeypatch.setattr(llm_client, "is_echo_mode", lambda: False)
    seen_tool_results = []

    async def fake_chat(messages, tools=None, **params):
        if tools and messages[-1]["role"] == "user" and "tytuł" not in messages[-1]["content"]:
            return {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "search_conversations",
                             "arguments": json.dumps({"query": "oświetlenie"})},
            }]}
        if messages[-1]["role"] == "tool":
            seen_tool_results.append(messages[-1]["content"])
            return {"role": "assistant", "content": f"Patrz wątek {old_tid}."}
        return {"role": "assistant", "content": "Tytuł testowy"}

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    r = client.post("/llm/request", json={"prompt": "Jak to było z latarniami?"})
    data = r.json()
    assert r.status_code == 200, r.text
    assert data["content"] == f"Patrz wątek {old_tid}."
    assert data["sources"] and data["sources"][0]["thread_id"] == old_tid
    assert data["sources"][0]["msg_owner"] in ("user", "assistant")
    assert "oświetlenie uliczne" in seen_tool_results[0]


def test_auto_mode_injects_context(monkeypatch):
    client.post("/llm/request", json={"prompt": "Kopie umów na sprzątanie budynków"})
    monkeypatch.setattr(settings.rag, "mode", "auto")
    monkeypatch.setattr(llm_client, "is_echo_mode", lambda: False)
    captured = {}

    async def fake_chat(messages, tools=None, **params):
        captured.setdefault("first", messages)
        return {"role": "assistant", "content": "ok"}

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    r = client.post("/llm/request", json={"prompt": "umowy sprzątanie"}).json()
    assert r["sources"]
    assert any("Fragmenty wcześniejszych rozmów" in m["content"]
               for m in captured["first"] if m["role"] == "system")


def test_persistence_across_reconnect(tmp_path):
    tid = client.post("/llm/request", json={"prompt": "Trwałość"}).json()["thread_id"]
    store.connect(tmp_path / "test.db")
    assert any(t["id"] == tid for t in client.get("/llm/all").json())
    new = client.post("/llm/request", json={"prompt": "Nowy"}).json()["thread_id"]
    assert new != tid
