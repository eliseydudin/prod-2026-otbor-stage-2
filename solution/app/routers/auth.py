from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.database import SessionDep
from app.exceptions import AppError, ErrorCode
from app.jwt import create_token, get_user_by_email, hash_password, passwords_match
from app.models import (
    LoginRequest,
    OAuth2Token,
    RegisterRequest,
    User,
    UserDB,
)

auth_router = APIRouter(prefix="/auth", tags=["Auth"])
logger = getLogger("app.auth")


@auth_router.post("/register", status_code=201)
async def register(request: RegisterRequest, session: SessionDep):
    try:
        request.password = hash_password(request.password)
        user_db = UserDB.model_validate(request)
        session.add(user_db)
        session.commit()
        session.refresh(user_db)

        token = create_token(user_db)
        logger.info(f"a new user has registered, {user_db.email=}, {user_db.id=}")
        return {"accessToken": token, "user": User.from_db_user(user_db)}

    except Exception:
        raise AppError(
            status_code=409,
            code=ErrorCode.EMAIL_ALREADY_EXISTS,
            message="Пользователь с таким email уже существует",
            details={"field": "email", "value": request.email},
        )


def _login_inner(email: str, password: str, session: SessionDep):
    user = get_user_by_email(session, email)
    bad_creds = AppError(
        status_code=401,
        code=ErrorCode.UNAUTHORIZED,
        message="Токен отсутствует или невалиден",
    )

    if user is None:
        raise bad_creds

    if not user.is_active:
        raise AppError(
            status_code=423,
            code=ErrorCode.USER_INACTIVE,
            message="Пользователь деактивирован",
        )

    if not passwords_match(user.password, password):
        raise bad_creds

    return (
        User.from_db_user(user),
        create_token(user),
    )


@auth_router.post("/login")
async def login(request: LoginRequest, session: SessionDep):
    user, token = _login_inner(request.email, request.password, session)
    return {"accessToken": token, "expiresIn": 3600, "user": user}


@auth_router.post("/token", include_in_schema=False)
async def token(
    request: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> OAuth2Token:
    _, token = _login_inner(request.username, request.password, session)
    return OAuth2Token(access_token=token, token_type="bearer")
