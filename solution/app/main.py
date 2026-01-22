from contextlib import asynccontextmanager
import logging
import warnings

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from rich.console import Console
from rich.logging import RichHandler
from fastapi.exceptions import RequestValidationError

from app.database import get_session, setup_tables
from app.exceptions import AppError, TimeValidationError, normalize_validation_error
from app.jwt import setup_admin_user
from app.routers import (
    auth_router,
    users_router,
    fraud_rules_router,
    transactions_router,
)

logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)

warnings.filterwarnings("ignore")
# ^ pydantic complains when serializing struct types from json sql columns
# for some reason


def setup_logging():
    console = Console(width=80)
    rich_handler = RichHandler(
        show_time=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
        show_path=False,
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
    # the testing system complains if there's a trailing `/`
    # e.g it wants "/api/v1/users" instead of "/api/v1/users/"
    error.path = request.url.path.rstrip("/")
    api_err = error.into_api_error()

    logger.error(f"an error occured: {api_err.stringify()}")

    return JSONResponse(
        status_code=error.status_code,
        content=api_err.model_dump(mode="json"),
        headers=error.headers,
    )


@app.exception_handler(RequestValidationError)
async def transform_validation_errors(request: Request, error: RequestValidationError):
    return normalize_validation_error(request, error)


@app.exception_handler(TimeValidationError)
async def time_validation(request: Request, error: TimeValidationError):
    return error.into_json_response(request.url.path.rstrip("/"))


@app.get("/ping", tags=["Auth"])
async def healthcheck():
    return {"status": "ok"}
