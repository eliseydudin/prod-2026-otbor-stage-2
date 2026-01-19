from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import get_session, setup_tables
from app.auth import auth_router
from app.jwt import setup_admin_user
from app.users import users_router
from app.fraud_rules import fraud_rules_router
from app.transactions import transactions_router
# import app.dsl


@asynccontextmanager
async def lifespan(_app):
    setup_tables()
    for session in get_session():
        print("setting up the admin!")
        setup_admin_user(session)
    yield


app = FastAPI(lifespan=lifespan, root_path="/api/v1")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(fraud_rules_router)
app.include_router(transactions_router)


@app.get("/ping", tags=["Auth"])
async def healthcheck():
    return {"status": "ok"}
