"""Klient LLM. Domyślnie DeepSeek (API zgodne z OpenAI); można wskazać lokalny serwer
(np. Ollama / vLLM) w config.toml. Bez api_key dla DeepSeeka działa w trybie echo."""
import ipaddress
import time
from urllib.parse import urlparse

import httpx

from app.config import settings


def is_echo_mode() -> bool:
    cfg = settings.llm
    return not cfg.api_key and "deepseek" in cfg.base_url


def is_local(url: str | None = None) -> bool:
    """Czy serwer (domyślnie LLM z [llm]) działa lokalnie / w sieci urzędu – dane nie wychodzą na zewnątrz."""
    host = urlparse(settings.llm.base_url if url is None else url).hostname or ""
    if not host:
        return False
    # Nazwa bez kropki (np. „ollama” – usługa w sieci docker compose) nie jest domeną internetową,
    # więc rozwiązuje się tylko w sieci lokalnej / urzędu.
    if host == "localhost" or "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def backend_name() -> str:
    return "lokalny" if is_local() else "zewnętrzny"


def _client(timeout: float | None = None) -> httpx.AsyncClient:
    cfg = settings.llm
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    return httpx.AsyncClient(
        base_url=cfg.base_url, headers=headers, timeout=timeout or cfg.timeout
    )


async def chat(messages: list[dict], **params) -> dict:
    """Zwraca całą wiadomość asystenta."""
    if is_echo_mode():
        return {"role": "assistant", "content": f"[echo] {messages[-1]['content']}"}
    body = {"model": settings.llm.model, "messages": messages, **params}
    async with _client() as client:
        resp = await client.post("/chat/completions", json=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


async def complete(messages: list[dict], **params) -> str:
    return (await chat(messages, **params)).get("content") or ""


async def health() -> dict:
    """Sprawdza dostępność modelu przez GET /models (nie zużywa tokenów)."""
    model = settings.llm.model
    info = {"model": model, "base_url": settings.llm.base_url}
    if is_echo_mode():
        return {**info, "status": "echo", "detail": "Brak llm.api_key w config.toml – tryb echo"}
    start = time.perf_counter()
    try:
        async with _client(timeout=10) as client:
            resp = await client.get("/models")
            resp.raise_for_status()
        latency = int((time.perf_counter() - start) * 1000)
        models = [m.get("id") for m in resp.json().get("data", [])]
        if models and model not in models:
            return {**info, "status": "error", "latency_ms": latency,
                    "detail": f"Model niedostępny. Dostępne: {', '.join(models)}"}
        return {**info, "status": "ok", "latency_ms": latency}
    except httpx.HTTPStatusError as exc:
        return {**info, "status": "error", "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {**info, "status": "error", "detail": f"{type(exc).__name__}: {exc}"}
