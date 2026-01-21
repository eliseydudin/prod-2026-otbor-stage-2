from fastapi import APIRouter

from app.database import SessionDep
from app.exceptions import AppError
from app.jwt import CurrentUser
from app.models import (
    Transaction,
    TransactionCreateRequest,
    TransactionDB,
    TransactionStatus,
    # TransactionDecision,
)

transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])


@transactions_router.post("/")
async def new_transaction(
    user: CurrentUser, session: SessionDep, request: TransactionCreateRequest
):
    if request.user_id != user.id and not user.role.is_admin():
        raise AppError.make_forbidden_error()

    db_transaction = TransactionDB.model_validate(
        request,
        update={"status": TransactionStatus.APPROVED, "is_fraud": False},
    )
    try:
        session.add(db_transaction)
        session.commit()
        session.refresh(db_transaction)

        return {
            "transaction": Transaction.model_validate(db_transaction),
            "rule_results": [],
        }

    except Exception:
        raise AppError.make_email_already_exists_error()
