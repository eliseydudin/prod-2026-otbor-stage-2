from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from app.database import SessionDep
from app.jwt import CurrentAdminUser, CurrentUserDB, hash_password
from app.models import PagedUsers, User, UserCreateRequest, UserDB, UserUpdateRequest

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("/me")
async def me(current_user: CurrentUserDB) -> User:
    return User.from_db_user(current_user)


@users_router.put("/me")
async def update_me(
    current: CurrentUserDB, session: SessionDep, request: UserUpdateRequest
):
    if request.model_fields_set & {"is_active", "role"} and not current.role.is_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    for field in UserUpdateRequest.model_fields:
        if field not in request.model_fields_set:
            continue

        setattr(current, field, getattr(request, field))

    try:
        session.add(current)
        session.commit()
        session.refresh(current)

        return User.from_db_user(current)
    except Exception:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@users_router.post("/")
async def admin_create_user(
    _admin: CurrentAdminUser, request: UserCreateRequest, session: SessionDep
) -> User:
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
