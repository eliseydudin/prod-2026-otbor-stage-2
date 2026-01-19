from fastapi import APIRouter, HTTPException, status

from app.database import SessionDep
from app.jwt import CurrentUserDB
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
    user: CurrentUserDB, session: SessionDep, request: TransactionCreateRequest
):
    if request.user_id != user.id and not user.role.is_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

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
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
