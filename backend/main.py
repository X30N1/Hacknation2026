from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app import llm_client
from app.config import settings
from app.auth import repo as konta
from app.auth.sesja import zalogowany
from app.routers import anonimizacja, archiwum, auth, sprawy, uzytkownicy
from app.storage import store


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.connect(settings.database.resolved())
    if konta.zapewnij_admina():
        print("Utworzono konto administratora: admin / admin – zmień hasło przy pierwszym logowaniu.")
    yield
    store.close()


app = FastAPI(
    title="Asystent urzędnika – UM Bydgoszcz",
    description="API wg backend/docs/APIDOC.md (kontrakt spraw zgodny z frontendem)",
    version="0.2.0",
    lifespan=lifespan,
)

# Logowanie i zarządzanie kontami; cała reszta API tylko po pełnym zalogowaniu (hasło + 2FA).
app.include_router(auth.router)
app.include_router(uzytkownicy.router)
_chronione = [Depends(zalogowany)]
app.include_router(sprawy.router, dependencies=_chronione)
app.include_router(anonimizacja.router, dependencies=_chronione)
app.include_router(archiwum.router, dependencies=_chronione)


# Błędy w formacie frontendu: {"blad": "komunikat"} (+ "detail" dla zgodności z FastAPI).
@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException):
    return JSONResponse({"blad": str(exc.detail), "detail": exc.detail},
                        status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    bledy = []
    for e in exc.errors():
        msg = e.get("msg", "").removeprefix("Value error, ")
        pole = ".".join(str(x) for x in e.get("loc", [])[1:])
        bledy.append(msg if e.get("type") == "value_error" or not pole else f"{pole}: {msg}")
    return JSONResponse(
        {"blad": "Niepoprawne dane. " + "; ".join(bledy), "detail": jsonable(exc.errors())},
        status_code=422,
    )


def jsonable(errors):
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(errors, custom_encoder={Exception: str})


@app.get("/health", tags=["meta"])
async def health():
    """Stan aplikacji w formacie oczekiwanym przez frontend (nagłówek „AI: …”)."""
    llm_info = await llm_client.health()
    echo = llm_info["status"] == "echo"
    return {
        "status": "ok",
        "ok": True,
        "dzis": date.today().isoformat(),
        "llm": {
            "backend": "echo" if echo else llm_client.backend_name(),
            "model": llm_info["model"],
            "dostepny": llm_info["status"] == "ok",
            # true = dane wychodzą poza urząd (frontend pokazuje ostrzeżenie)
            "zewnetrzny": not echo and not llm_client.is_local(),
            "detail": llm_info.get("detail"),
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
