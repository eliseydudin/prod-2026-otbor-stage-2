from fastapi import APIRouter

from app.jwt import CurrentUserDB
from app.models import User

users_router = APIRouter(prefix="/users")


@users_router.get("/me")
async def me(current_user: CurrentUserDB):
    return User.from_db_user(current_user)
