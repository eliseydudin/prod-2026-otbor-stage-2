from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import setup_tables
from app.auth import auth_router
from app.users import users_router


@asynccontextmanager
async def lifespan(_app):
    setup_tables()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)
app.include_router(users_router)


@app.get("/ping")
async def healthcheck():
    return {"status": "ok"}
