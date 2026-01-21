from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from rich.console import Console
from rich.logging import RichHandler

from app.database import get_session, setup_tables
from app.auth import auth_router
from app.exceptions import AppError
from app.jwt import setup_admin_user
from app.users import users_router
from app.fraud_rules import fraud_rules_router
from app.transactions import transactions_router

# import app.dsl

logger = logging.getLogger("app")


def setup_logging():
    console = Console(width=80)
    rich_handler = RichHandler(
        show_time=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
        show_path=True,
        console=console,
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False


@asynccontextmanager
async def lifespan(_app):
    setup_logging()
    setup_tables()

    for session in get_session():
        setup_admin_user(session)

    logger.info("setup successful")
    yield


app = FastAPI(lifespan=lifespan, root_path="/api/v1")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(fraud_rules_router)
app.include_router(transactions_router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, error: AppError):
    error.path = request.url.path
    return JSONResponse(
        status_code=error.status_code,
        content=error.into_api_error().model_dump(mode="json"),
        headers=error.headers,
    )


@app.get("/ping", tags=["Auth"])
async def healthcheck():
    return {"status": "ok"}
