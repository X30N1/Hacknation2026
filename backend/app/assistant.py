import json
import logging

from app import llm_client, rag
from app.config import settings

log = logging.getLogger(__name__)

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_conversations",
        "description": (
            "Przeszukuje wcześniejsze rozmowy (inne wątki) urzędników z asystentem: "
            "poprzednie wnioski, kwerendy do wydziałów, projekty odpowiedzi. Użyj, gdy "
            "urzędnik odwołuje się do wcześniejszej sprawy albo gdy podobny wniosek mógł "
            "być już rozpatrywany (np. który wydział odpowiadał, jak sformułowano pismo)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Zapytanie: temat sprawy, słowa kluczowe, sygnatura, nazwa wydziału",
                }
            },
            "required": ["query"],
        },
    },
}


def _dedupe(hits: list[rag.Hit]) -> list[rag.Hit]:
    seen, out = set(), []
    for h in hits:
        if h.chunk_id not in seen:
            seen.add(h.chunk_id)
            out.append(h)
    return out


async def answer(messages: list[dict], exclude_thread: int | None) -> tuple[str, list[rag.Hit]]:
    """Zwraca (treść odpowiedzi, źródła z RAG). Nie modyfikuje przekazanej listy."""
    messages = list(messages)
    mode = settings.rag.mode
    if mode == "off" or llm_client.is_echo_mode():
        return await llm_client.complete(messages), []

    if mode == "auto":
        hits = await rag.search(messages[-1]["content"], exclude_thread=exclude_thread)
        if hits:
            messages.insert(-1, {
                "role": "system",
                "content": "Fragmenty wcześniejszych rozmów, które mogą być pomocne:\n\n"
                           + rag.format_hits(hits),
            })
        return await llm_client.complete(messages), hits

    # mode == "tool"
    sources: list[rag.Hit] = []
    for _ in range(settings.rag.max_tool_rounds):
        msg = await llm_client.chat(messages, tools=[SEARCH_TOOL])
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or "", _dedupe(sources)
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls})
        for call in calls:
            fn = call.get("function", {})
            if fn.get("name") != SEARCH_TOOL["function"]["name"]:
                result = f"Nieznane narzędzie: {fn.get('name')}"
            else:
                try:
                    query = json.loads(fn.get("arguments") or "{}").get("query", "")
                except json.JSONDecodeError:
                    query = ""
                hits = await rag.search(query, exclude_thread=exclude_thread) if query else []
                log.info("search_conversations(%r) -> %d", query, len(hits))
                sources.extend(hits)
                result = rag.format_hits(hits)
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": result})

    # wyczerpany limit rund – ostatnie wywołanie bez narzędzi
    return await llm_client.complete(messages), _dedupe(sources)
