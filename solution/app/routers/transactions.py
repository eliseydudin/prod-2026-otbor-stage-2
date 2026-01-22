import uuid
from datetime import datetime, timedelta
from logging import getLogger
from typing import Optional

from fastapi import APIRouter, Query, Request, Response
from pydantic import ValidationError
from sqlmodel import col, select

from app import dsl
from app.database import SessionDep, fetch_db_fraud_rules
from app.dsl.types import EvaluationRequest
from app.exceptions import AppError, TimeValidationError, normalize_validation_error
from app.jwt import CurrentUser, get_user
from app.models import (
    FraudRuleEvaluationResult,
    PagedTransactions,
    Transaction,
    TransactionBatchResponse,
    TransactionBatchResultItem,
    TransactionCreateRequest,
    TransactionDB,
    TransactionDecision,
    TransactionStatus,
    make_eval_request,
)

# from app.database import SessionDep
# from app.exceptions import AppError
# from app.jwt import CurrentUser

transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])
logger = getLogger("app.transcations")


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


def create_transaction(
    request: TransactionCreateRequest, user: CurrentUser, session: SessionDep
) -> TransactionDecision:
    if user.id != request.user_id and not user.role.is_admin() or not user.is_active:
        raise AppError.make_forbidden_error()

    req_user = get_user(session, request.user_id)
    if req_user is None:
        raise AppError.make_not_found_error(
            "Пользователь с таким ID не найден", {"userId": request.user_id}
        )

    transaction = Transaction(
        **request.model_dump(), is_fraud=False, status=TransactionStatus.APPROVED
    )

    req = make_eval_request(transaction, req_user)
    is_fraud, rule_results = get_fraud_rule_eval(req, session)

    if is_fraud:
        transaction.is_fraud = True
        transaction.status = TransactionStatus.DECLINED

    db_transaction = TransactionDB(
        **transaction.model_dump(exclude={"ip_address"}),
        ip_address=None
        if transaction.ip_address is None
        else str(transaction.ip_address),
    )
    session.add(db_transaction)
    session.commit()
    session.refresh(db_transaction)

    logger.info(
        f"created a new transaction, is_fraud={is_fraud}, ID={db_transaction.id} "
        + f"eval_request={req}"
    )

    return TransactionDecision(rule_results=rule_results, transaction=transaction)


@transactions_router.post("/", status_code=201)
async def new_transaction(
    request: TransactionCreateRequest, user: CurrentUser, session: SessionDep
) -> TransactionDecision:
    return create_transaction(request, user, session)


@transactions_router.post("/batch", status_code=201)
async def post_batch(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> TransactionBatchResponse:
    data = await request.json()
    result = []
    errors = 0
    # all = len(request.items)

    for i, req in enumerate(data["items"]):
        try:
            req = TransactionCreateRequest.model_validate(req)
            item = create_transaction(req, user, session)
            result.append(TransactionBatchResultItem(index=i, decision=item))
        except AppError as e:
            result.append(TransactionBatchResultItem(index=i, error=e.into_api_error()))
            errors += 1
        except ValidationError as e:
            result.append(
                TransactionBatchResultItem(
                    index=i,
                    error=normalize_validation_error(e),  # type: ignore
                )
            )

    if errors != 0:
        response.status_code = 207

    return TransactionBatchResponse(items=result)


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

    req = make_eval_request(transaction, user)
    _, rule_results = get_fraud_rule_eval(req, session)

    return TransactionDecision(
        transaction=transaction.to_transaction(), rule_results=rule_results
    )


@transactions_router.get("/")
async def get_transactions(
    user: CurrentUser,
    session: SessionDep,
    # query params below
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, gt=0),
    from_time: datetime = Query(
        alias="from", default_factory=lambda: datetime.now() - timedelta(days=90)
    ),
    to: datetime = Query(default_factory=datetime.now),
    user_id: Optional[uuid.UUID] = None,
    status: Optional[TransactionStatus] = None,
    is_fraud: Optional[bool] = None,
) -> PagedTransactions:
    if not from_time < to:
        raise TimeValidationError(from_time, to)

    query = (
        select(TransactionDB)
        .order_by(col(TransactionDB.created_at).desc())
        .offset(page * size)
        .limit(size)
    )
    if status is not None:
        query = query.where(TransactionDB.status == status)
    if from_time is not None and to is not None:
        query = query.where(TransactionDB.created_at > from_time).where(
            TransactionDB.created_at < to
        )
    if is_fraud is not None:
        query = query.where(TransactionDB.is_fraud == is_fraud)

    if user_id is not None and user.role.is_admin():
        query = query.where(TransactionDB.user_id == user_id)
    elif not user.role.is_admin():
        query = query.where(TransactionDB.user_id == user.id)

    result = list(map(TransactionDB.to_transaction, session.exec(query)))

    return PagedTransactions(items=result, size=size, page=page, total=len(result))
