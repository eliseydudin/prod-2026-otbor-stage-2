import uuid
from fastapi import APIRouter, Query
from sqlmodel import select

from app.database import SessionDep
from app.exceptions import AppError
from app.jwt import CurrentAdmin, CurrentUser, get_user, hash_password
from app.models import PagedUsers, User, UserCreateRequest, UserDB, UserUpdateRequest

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("/me")
async def me(current_user: CurrentUser) -> User:
    return User.from_db_user(current_user)


def _update_user(
    user: UserDB,
    session: SessionDep,
    request: UserUpdateRequest,
    redacter_is_admin: bool,
):
    if request.model_fields_set & {"is_active", "role"} and not redacter_is_admin:
        raise AppError.make_forbidden_error()

    for field in UserUpdateRequest.model_fields:
        if field not in request.model_fields_set:
            continue

        setattr(user, field, getattr(request, field))

    try:
        session.add(user)
        session.commit()
        session.refresh(user)

        return User.from_db_user(user)
    except Exception as e:
        raise AppError.make_internal_server_error(e)


@users_router.put("/me")
async def update_me(
    current: CurrentUser, session: SessionDep, request: UserUpdateRequest
) -> User:
    return _update_user(current, session, request, current.role.is_admin())


@users_router.post("/", status_code=201)
async def admin_create_user(
    _admin: CurrentAdmin, request: UserCreateRequest, session: SessionDep
) -> User:
    try:
        request.password = hash_password(request.password)
        user_db = UserDB.model_validate(request)
        session.add(user_db)
        session.commit()
        session.refresh(user_db)

        return User.from_db_user(user_db)
    except Exception:
        raise AppError.make_email_already_exists_error()


@users_router.get("/", response_model=PagedUsers)
async def users_page(
    _admin: CurrentAdmin,
    session: SessionDep,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, gt=0),
):
    try:
        query = select(UserDB).offset(page * size).limit(size)
        result = list(map(User.from_db_user, session.exec(query).fetchall()))

        return {
            "items": result,
            "page": page,
            "size": size,
            "total": len(result),
        }

    except Exception as e:
        raise AppError.make_internal_server_error(e)


@users_router.get("/{id}")
async def user_by_id(current: CurrentUser, id: uuid.UUID, session: SessionDep) -> User:
    if current.id != id and not current.role.is_admin():
        raise AppError.make_forbidden_error()

    if user := get_user(session, id):
        return User.from_db_user(user)
    else:
        raise AppError.make_not_found_error("Пользователь не найден")


@users_router.put("/{id}")
async def change_by_id(
    current: CurrentUser,
    id: uuid.UUID,
    session: SessionDep,
    request: UserUpdateRequest,
) -> User:
    if current.id != id and not current.role.is_admin():
        raise AppError.make_forbidden_error()

    if user := get_user(session, id):
        return _update_user(user, session, request, current.role.is_admin())
    else:
        raise AppError.make_not_found_error("Пользователь не найден")


@users_router.delete("/{id}", status_code=204)
async def delete_by_id(
    _admin: CurrentAdmin, id: uuid.UUID, session: SessionDep
) -> None:
    if user := get_user(session, id):
        try:
            user.is_active = False
            session.add(user)
            session.commit()
            session.refresh(user)
        except Exception as e:
            raise AppError.make_internal_server_error(e)
    else:
        raise AppError.make_not_found_error("Пользователь не найден")
