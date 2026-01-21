import uuid

from fastapi import APIRouter
from sqlmodel import select

from app import dsl
from app.database import SessionDep, fetch_db_fraud_rules
from app.dsl.types import EvaluationRequest
from app.exceptions import AppError
from app.jwt import CurrentUser, get_user
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


def get_fraud_rule_eval(request: EvaluationRequest, session: SessionDep):
    is_fraud = False
    results: list[FraudRuleEvaluationResult] = []

    for rule in fetch_db_fraud_rules(session):
        expr = dsl.parse_rule(rule.dsl_expression)
        matched = dsl.evaluate(expr, request)
        is_fraud = is_fraud or matched

        results.append(
            FraudRuleEvaluationResult(
                rule_id=rule.id,
                rule_name=rule.name,
                priority=rule.priority,
                matched=matched,
            )
        )

    return is_fraud, results


@transactions_router.post("/", status_code=201)
async def new_transaction(
    request: TransactionCreateRequest, user: CurrentUser, session: SessionDep
) -> TransactionDecision:
    if user.id != request.user_id and not user.role.is_admin() or not user.is_active:
        raise AppError.make_forbidden_error()

    if get_user(session, request.user_id) is None:
        raise AppError.make_not_found_error(
            "Пользователь с таким ID не найден", {"userId": request.user_id}
        )

    transaction = Transaction(
        **request.model_dump(), is_fraud=False, status=TransactionStatus.APPROVED
    )

    req = EvaluationRequest(
        amount=transaction.amount,
        currency=transaction.currency,
        user_age=user.age,
        merchant_id=transaction.merchant_id,
        ip_address=None
        if transaction.ip_address is None
        else str(transaction.ip_address),
        device_id=transaction.device_id,
        user_region=user.region,
    )

    is_fraud, rule_results = get_fraud_rule_eval(req, session)

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


@transactions_router.get("/{id}")
async def get_transaction_by_id(
    id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> TransactionDecision:
    transaction = session.exec(
        select(TransactionDB).where(TransactionDB.id == id)
    ).one_or_none()

    if transaction is None:
        raise AppError.make_not_found_error("Транзакция с данным ID не найдена")

    if transaction.user_id != user.id and not user.role.is_admin():
        raise AppError.make_forbidden_error()

    req = EvaluationRequest(
        amount=transaction.amount,
        currency=transaction.currency,
        user_age=user.age,
        merchant_id=transaction.merchant_id,
        ip_address=None
        if transaction.ip_address is None
        else str(transaction.ip_address),
        device_id=transaction.device_id,
        user_region=user.region,
    )

    _, rule_results = get_fraud_rule_eval(req, session)

    return TransactionDecision(
        transaction=transaction.to_transaction(), rule_results=rule_results
    )
