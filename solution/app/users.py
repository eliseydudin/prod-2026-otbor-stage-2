from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from app.database import SessionDep
from app.jwt import CurrentAdminUser, CurrentUserDB, hash_password
from app.models import PagedUsers, User, UserCreateRequest, UserDB

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("/me")
async def me(current_user: CurrentUserDB):
    return User.from_db_user(current_user)


@users_router.post("/")
async def admin_create_user(
    _admin: CurrentAdminUser, request: UserCreateRequest, session: SessionDep
):
    try:
        request.password = hash_password(request.password)
        user_db = UserDB.model_validate(request)
        session.add(user_db)
        session.commit()
        session.refresh(user_db)

        return User.from_db_user(user_db)
    except Exception:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@users_router.get("/", response_model=PagedUsers)
async def users_page(
    _admin: CurrentAdminUser,
    session: SessionDep,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, gt=0),
):
    try:
        query = select(UserDB).offset(page * size).limit(size)
        result = map(User.from_db_user, session.exec(query).fetchall())

        return {
            "items": result,
            "page": page,
            "size": size,
            "total": 0,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
