from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.routers import calendar, llm
from app.storage import store


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.connect(settings.database.resolved())
    yield
    store.close()


app = FastAPI(
    title="Asystent urzędnika – UM Bydgoszcz",
    description="Przykładowa implementacja API wg docs/APIDOC.md",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(llm.router)
app.include_router(calendar.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
