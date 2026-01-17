from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from .database import SessionDep
from .jwt import create_token, get_user_by_email, hash_password, passwords_match
from .models import LoginRequest, OAuth2Token, User, UserCreateRequest, UserDB

auth_router = APIRouter(prefix="/auth")


@auth_router.post("/register")
async def register(request: UserCreateRequest, session: SessionDep):
    try:
        request.password = hash_password(request.password)
        user_db = UserDB.model_validate(request)
        session.add(user_db)
        session.commit()
        session.refresh(user_db)

        token = create_token(user_db)
        return {"accessToken": token, "user": User.from_db_user(user_db)}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _login_inner(email: str, password: str, session: SessionDep):
    try:
        user = get_user_by_email(session, email)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="no such user"
            )

        if not passwords_match(user.password, password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="wrong password"
            )

        return (
            User.from_db_user(user),
            create_token(user),
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@auth_router.post("/login")
async def login(request: LoginRequest, session: SessionDep):
    user, token = _login_inner(request.email, request.password, session)
    return {"accessToken": token, "expiresIn": 3600, "user": user}


@auth_router.post(
    "/token",
    description="Same as /login except it takes in a `OAuth2PasswordRequestForm` instead of `LoginRequest`",
)
async def token(
    request: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
):
    _, token = _login_inner(request.username, request.password, session)
    return OAuth2Token(access_token=token, token_type="bearer")
