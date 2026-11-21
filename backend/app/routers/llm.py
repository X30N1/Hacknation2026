from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from app import assistant, llm_client, rag
from app.schemas import LLMHealth, LLMRequest, LLMResponse, Message, Source, ThreadSummary
from app.storage import store

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get(
    "/health",
    response_model=LLMHealth,
    responses={503: {"model": LLMHealth, "description": "Model niedostępny"}},
)
async def llm_health(response: Response):
    result = await llm_client.health()
    if result["status"] == "error":
        response.status_code = 503
    return result


@router.post("/request", response_model=LLMResponse)
async def llm_request(body: LLMRequest, background: BackgroundTasks):
    new_thread = body.thread_id == -1
    if new_thread:
        thread, history = None, []
    else:
        thread = store.get_thread(body.thread_id)
        if thread is None:
            raise HTTPException(404, "Wątek nie istnieje")
        history = [
            {"role": m.role,
             "content": llm_client.user_content(m.content, m.context) if m.role == "user" else m.content}
            for m in store.get_messages(thread.id)
        ]

    messages = llm_client.build_messages(history, body.prompt, body.context)

    try:
        content, hits = await assistant.answer(
            messages, exclude_thread=thread.id if thread else None
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Błąd LLM: {exc}") from exc

    # Nowy wątek tworzymy dopiero po udanej odpowiedzi – tytuł z pytania i odpowiedzi.
    if thread is None:
        thread = store.create_thread(await llm_client.generate_title(body.prompt, content))

    # Prompt i kontekst OCR zapisywane osobno – w historii wątku urzędnik widzi swój prompt.
    question = store.add_message(thread.id, "user", body.prompt, body.context)
    reply = store.add_message(thread.id, "assistant", content)

    # Indeksowanie po wysłaniu odpowiedzi (embeddingi mogą chwilę trwać).
    background.add_task(rag.index_message, thread.id, question.id, "user",
                        llm_client.user_content(body.prompt, body.context))
    background.add_task(rag.index_message, thread.id, reply.id, "assistant", reply.content)

    return LLMResponse(
        thread_id=thread.id,
        message_id=reply.id,
        msg_owner="assistant",
        content=reply.content,
        timestamp=reply.timestamp,
        sources=[
            Source(thread_id=h.thread_id, message_id=h.message_id, msg_owner=h.role, title=h.title,
                   snippet=h.text[: rag.SNIPPET_LEN], score=h.score)
            for h in hits
        ],
    )


@router.get("/all", response_model=list[ThreadSummary])
async def llm_all():
    return [
        ThreadSummary(id=t.id, title=t.title, create_date=t.create_date)
        for t in store.list_threads()
    ]


@router.get("/{thread_id}", response_model=list[Message])
async def llm_thread(thread_id: int):
    if store.get_thread(thread_id) is None:
        raise HTTPException(404, "Wątek nie istnieje")
    return [
        Message(message_id=m.id, msg_owner=m.role, content=m.content, timestamp=m.timestamp)
        for m in store.get_messages(thread_id)
    ]
