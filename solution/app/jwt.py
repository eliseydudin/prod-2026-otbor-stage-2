import uuid
from os import environ
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlmodel import select

from app.database import SessionDep
from app.exceptions import AppError, ErrorCode
from app.models import Role, Token, UserCreateRequest, UserDB

jwt_key = environ["RANDOM_SECRET"]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
algorithm = "HS256"
password_hasher = PasswordHash.recommended()

oauth2_scheme.make_not_authenticated_error = lambda: AppError(
    status_code=401,
    message="Токен отсутствует или невалиден",
    code=ErrorCode.UNAUTHORIZED,
    headers={"WWW-Authenticate": "Bearer"},
)  # type: ignore


def get_user(session: SessionDep, id: uuid.UUID):
    return session.exec(select(UserDB).where(UserDB.id == id)).one_or_none()


def get_user_by_email(session: SessionDep, email: str):
    return session.exec(select(UserDB).where(UserDB.email == email)).one_or_none()


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
):
    credentials_exception = AppError(
        status_code=401,
        message="Токен отсутствует или невалиден",
        code=ErrorCode.UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = Token.model_validate(
            jwt.decode(token, jwt_key, algorithms=[algorithm])
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    user = get_user(session, payload.sub)

    if user is None:
        # print("no such user")
        raise credentials_exception

    return user


CurrentUser = Annotated[UserDB, Depends(get_current_user)]


async def get_current_admin_user(current_user: CurrentUser):
    if current_user.role != Role.ADMIN:
        raise AppError.make_forbidden_error()

    return current_user


CurrentAdmin = Annotated[UserDB, Depends(get_current_admin_user)]


def create_token(user: UserDB):
    token = Token.from_user(user)
    return jwt.encode(token.to_dict(), jwt_key, algorithm)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def passwords_match(hashed: str, to_check: str) -> bool:
    return password_hasher.verify(to_check, hashed)


def setup_admin_user(session: SessionDep):
    if get_user_by_email(session, environ["ADMIN_EMAIL"]) is not None:
        return

    create_request = UserCreateRequest(
        email=environ["ADMIN_EMAIL"],
        full_name=environ["ADMIN_FULLNAME"],
        password=environ["ADMIN_PASSWORD"],
        role=Role.ADMIN,
    )
    create_request.password = hash_password(create_request.password)
    user_db = UserDB.model_validate(create_request)

    try:
        session.add(user_db)
        session.commit()
        session.refresh(user_db)
    except Exception as _:
        pass
