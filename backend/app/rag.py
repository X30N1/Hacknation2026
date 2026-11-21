"""RAG nad wcześniejszymi rozmowami.

Wyszukiwanie hybrydowe:
- pełnotekstowe: SQLite FTS5 (bm25), bez polskich znaków diakrytycznych, z prostym
  „stemmingiem” przez obcięcie słów do prefiksu (umowy / umów / umowa -> "umow*"),
- wektorowe (opcjonalne): embeddingi z API zgodnego z OpenAI /embeddings, cosinus.
Oba rankingi łączone przez Reciprocal Rank Fusion (RRF).
"""
import logging
import math
import re
from array import array
from dataclasses import dataclass

import httpx

from app.config import settings
from app.storage import store

log = logging.getLogger(__name__)

PREFIX_LEN = 5          # długość prefiksu słowa w zapytaniu FTS
CANDIDATES = 50         # ile kandydatów z każdej metody przed fuzją
RRF_K = 60
SNIPPET_LEN = 300       # TODO: limit – długość fragmentu zwracanego frontendowi

STOPWORDS = {
    "jest", "oraz", "albo", "jako", "przez", "przy", "który", "która", "które",
    "tego", "tych", "jaki", "jaka", "jakie", "czy", "dla", "nie", "się", "lub",
    "ale", "też", "tak", "jak", "aby", "żeby", "może", "mogę", "proszę", "było",
}


@dataclass
class Hit:
    chunk_id: int
    thread_id: int
    message_id: int
    role: str
    text: str
    score: float
    title: str = ""


# ---------- chunking ----------
def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    size = size or settings.rag.chunk_size
    overlap = settings.rag.chunk_overlap if overlap is None else overlap
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # tniemy na granicy akapitu/zdania/słowa, jeśli się da
            for sep in ("\n\n", ". ", " "):
                cut = text.rfind(sep, start + size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


# ---------- embeddingi ----------
def embeddings_enabled() -> bool:
    return bool(settings.rag.embeddings.base_url)


async def embed(texts: list[str]) -> list[list[float]] | None:
    """Zwraca embeddingi albo None (wyłączone / błąd – wtedy tylko FTS)."""
    cfg = settings.rag.embeddings
    if not cfg.base_url or not texts:
        return None
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    try:
        async with httpx.AsyncClient(
            base_url=cfg.base_url, headers=headers, timeout=cfg.timeout
        ) as client:
            resp = await client.post("/embeddings", json={"model": cfg.model, "input": texts})
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in data]
    except Exception as exc:  # noqa: BLE001
        log.warning("Embeddingi niedostępne: %s", exc)
        return None


def _to_blob(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _from_blob(blob: bytes) -> array:
    a = array("f")
    a.frombytes(blob)
    return a


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ---------- indeksowanie ----------
async def index_message(thread_id: int, message_id: int, role: str, content: str) -> int:
    # TODO: anonimizacja przed indeksowaniem (dane osobowe z jednej sprawy
    #       nie powinny trafiać do odpowiedzi w innej)
    chunks = chunk_text(content)
    if not chunks:
        return 0
    vectors = await embed(chunks)
    model = settings.rag.embeddings.model if vectors else None
    with store.lock, store.conn:
        for i, chunk in enumerate(chunks):
            cur = store.conn.execute(
                "INSERT INTO rag_chunks (thread_id, message_id, role, text, embedding, embedding_model)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, message_id, role, chunk,
                 _to_blob(vectors[i]) if vectors else None, model),
            )
            store.conn.execute(
                "INSERT INTO rag_fts (rowid, text) VALUES (?, ?)", (cur.lastrowid, chunk)
            )
    return len(chunks)


# ---------- wyszukiwanie ----------
def fts_query(query: str) -> str | None:
    words = re.findall(r"\w+", query.lower())
    terms = []
    for w in words:
        if len(w) < 3 or w in STOPWORDS or w.isdigit() and len(w) < 4:
            continue
        t = w[:PREFIX_LEN]
        if t not in terms:
            terms.append(t)
    return " OR ".join(f'"{t}"*' for t in terms) or None


def _lexical(query: str, exclude_thread: int | None) -> list[int]:
    q = fts_query(query)
    if not q:
        return []
    rows = store.conn.execute(
        "SELECT c.id FROM rag_fts JOIN rag_chunks c ON c.id = rag_fts.rowid"
        " WHERE rag_fts MATCH ? AND c.thread_id IS NOT ?"
        " ORDER BY bm25(rag_fts) LIMIT ?",
        (q, exclude_thread, CANDIDATES),
    ).fetchall()
    return [r["id"] for r in rows]


async def _vector(query: str, exclude_thread: int | None) -> list[int]:
    if not embeddings_enabled():
        return []
    vecs = await embed([query])
    if not vecs:
        return []
    qv = vecs[0]
    # TODO: przy dużej liczbie fragmentów – indeks wektorowy (sqlite-vec / pgvector)
    rows = store.conn.execute(
        "SELECT id, embedding FROM rag_chunks"
        " WHERE embedding IS NOT NULL AND embedding_model = ? AND thread_id IS NOT ?",
        (settings.rag.embeddings.model, exclude_thread),
    ).fetchall()
    scored = sorted(
        ((r["id"], _cosine(qv, _from_blob(r["embedding"]))) for r in rows),
        key=lambda x: x[1], reverse=True,
    )
    return [cid for cid, _ in scored[:CANDIDATES]]


async def search(query: str, top_k: int | None = None,
                 exclude_thread: int | None = None) -> list[Hit]:
    top_k = top_k or settings.rag.top_k
    rankings = [_lexical(query, exclude_thread), await _vector(query, exclude_thread)]

    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    best = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
    if not best:
        return []

    ids = [cid for cid, _ in best]
    rows = store.conn.execute(
        f"SELECT * FROM rag_chunks WHERE id IN ({','.join('?' * len(ids))})", ids
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    titles = store.get_titles({r["thread_id"] for r in rows})
    return [
        Hit(cid, by_id[cid]["thread_id"], by_id[cid]["message_id"], by_id[cid]["role"],
            by_id[cid]["text"], round(score, 5), titles.get(by_id[cid]["thread_id"], ""))
        for cid, score in best
    ]


def format_hits(hits: list[Hit]) -> str:
    """Wyniki w formie dla LLM."""
    if not hits:
        return "Brak pasujących fragmentów we wcześniejszych rozmowach."
    parts = []
    for h in hits:
        who = "urzędnik" if h.role == "user" else "asystent"
        parts.append(
            f"[wątek {h.thread_id} „{h.title}”, wiadomość {h.message_id}, {who}]\n{h.text}"
        )
    return "\n\n---\n\n".join(parts)
