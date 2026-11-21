"""Klient LLM. Domyślnie DeepSeek (API zgodne z OpenAI); można wskazać lokalny serwer
(np. Ollama / vLLM) w config.toml. Bez api_key dla DeepSeeka działa w trybie echo."""
import ipaddress
import time
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.prompts import SYSTEM_PROMPT, TITLE_PROMPT

TITLE_MAX = 60            # TODO: limit – długość tytułu wątku
TITLE_INPUT_MAX = 2000    # TODO: limit – ile znaków pytania/odpowiedzi idzie do tytułu


def is_echo_mode() -> bool:
    cfg = settings.llm
    return not cfg.api_key and "deepseek" in cfg.base_url


def is_local() -> bool:
    """Czy LLM działa lokalnie / w sieci urzędu (dane nie wychodzą na zewnątrz)."""
    host = urlparse(settings.llm.base_url).hostname or ""
    if host == "localhost" or host.endswith((".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def backend_name() -> str:
    if "deepseek" in settings.llm.base_url:
        return "deepseek"
    return "lokalny" if is_local() else "zewnętrzny"


def _client(timeout: float | None = None) -> httpx.AsyncClient:
    cfg = settings.llm
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    return httpx.AsyncClient(
        base_url=cfg.base_url, headers=headers, timeout=timeout or cfg.timeout
    )


def user_content(prompt: str, context: list[str] | None = None) -> str:
    """Treść wiadomości urzędnika wysyłana do LLM (prompt + dokumenty po OCR)."""
    if not context:
        return prompt
    joined = "\n\n---\n\n".join(context)
    return f"Kontekst (dokumenty po OCR):\n{joined}\n\nPolecenie:\n{prompt}"


def build_messages(history: list[dict], prompt: str, context: list[str]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_content(prompt, context)},
    ]


async def chat(messages: list[dict], tools: list[dict] | None = None, **params) -> dict:
    """Zwraca całą wiadomość asystenta (może zawierać tool_calls)."""
    if is_echo_mode():
        return {"role": "assistant", "content": f"[echo] {messages[-1]['content']}"}
    body = {"model": settings.llm.model, "messages": messages, **params}
    if tools:
        body["tools"] = tools
    async with _client() as client:
        resp = await client.post("/chat/completions", json=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


async def complete(messages: list[dict], **params) -> str:
    return (await chat(messages, **params)).get("content") or ""


def _fallback_title(prompt: str) -> str:
    title = " ".join(prompt.split())
    return title if len(title) <= TITLE_MAX else title[: TITLE_MAX - 1] + "…"


async def generate_title(prompt: str, answer: str) -> str:
    """Tytuł wątku na bazie pierwszego pytania i odpowiedzi (jak w Claude.ai).
    Przy błędzie LLM – obcięty prompt, żeby nie blokować rozmowy."""
    if is_echo_mode():
        return _fallback_title(prompt)
    try:
        title = await complete(
            [{"role": "user", "content": TITLE_PROMPT.format(
                prompt=prompt[:TITLE_INPUT_MAX], answer=answer[:TITLE_INPUT_MAX])}],
            max_tokens=30,
            temperature=0.3,
        )
    except Exception:  # noqa: BLE001
        return _fallback_title(prompt)
    title = title.strip().strip('"„”\'').rstrip(".").splitlines()[0] if title.strip() else ""
    return _fallback_title(title or prompt)


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
