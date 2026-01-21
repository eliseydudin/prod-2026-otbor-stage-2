from fastapi import APIRouter

from app import dsl
from app.database import SessionDep, fetch_db_fraud_rules
from app.exceptions import AppError
from app.jwt import CurrentUser
from app.models import (
    FraudRuleEvaluationResult,
    Transaction,
    TransactionCreateRequest,
    TransactionDB,
    TransactionDecision,
    TransactionStatus,
)

# from app.database import SessionDep
# from app.exceptions import AppError
# from app.jwt import CurrentUser

transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])


@transactions_router.post("/")
async def new_transaction(
    request: TransactionCreateRequest, user: CurrentUser, session: SessionDep
) -> TransactionDecision:
    if user.id != request.user_id and not user.role.is_admin() or not user.is_active:
        raise AppError.make_forbidden_error()

    transaction = Transaction(
        **request.model_dump(), is_fraud=False, status=TransactionStatus.APPROVED
    )
    rule_results: list[FraudRuleEvaluationResult] = []
    is_fraud = False

    for rule in fetch_db_fraud_rules(session):
        expr = dsl.parse_rule(rule.dsl_expression)
        matched = dsl.evaluate(expr, transaction)
        is_fraud = is_fraud or matched

        rule_results.append(
            FraudRuleEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.name,
                priority=rule.priority,
                matched=matched,
            )
        )

    if is_fraud:
        transaction.is_fraud = True
        transaction.status = TransactionStatus.DECLINED
    else:
        db_transaction = TransactionDB(
            **transaction.model_dump(exclude={"ip_address"}),
            ip_address=None
            if transaction.ip_address is None
            else str(transaction.ip_address),
        )
        session.add(db_transaction)
        session.commit()
        session.refresh(db_transaction)

    return TransactionDecision(rule_results=rule_results, transaction=transaction)
