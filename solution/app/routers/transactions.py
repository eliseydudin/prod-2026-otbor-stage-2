import uuid
from datetime import datetime, timedelta
from logging import getLogger
from typing import Optional

from fastapi import APIRouter, Query, Request, Response
from pydantic import ValidationError
from sqlmodel import col, select

from app import dsl
from app.database import SessionDep, fetch_db_fraud_rules
from app.dsl.types import EvaluationRequest, ParserError
from app.exceptions import (
    AppError,
    TimeValidationError,
    normalize_validation_error_to_dict,
)
from app.jwt import CurrentUser, get_user
from app.models import (
    FraudRuleEvaluationResult,
    PagedTransactions,
    Transaction,
    TransactionBatchResponse,
    TransactionBatchResultItem,
    TransactionCreateBatch,
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
        try:
            expr = dsl.parse_rule(rule.dsl_expression)
            matched = dsl.evaluate(expr, request)
        except ParserError:
            matched = False

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
        rule_results=rule_results,
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
    create_request: TransactionCreateBatch,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> TransactionBatchResponse:
    result = []
    error_occured = False

    for i, req in enumerate(create_request.items):
        try:
            req = TransactionCreateRequest.model_validate(req)
            item = create_transaction(req, user, session)
            result.append(TransactionBatchResultItem(index=i, decision=item))
        except AppError as e:
            error_occured = True
            e.path = request.url.path.rstrip("/")
            result.append(TransactionBatchResultItem(index=i, error=e.into_api_error()))
        except ValidationError as e:
            error_occured = True
            _, data = normalize_validation_error_to_dict(request, e)  # type: ignore
            result.append(TransactionBatchResultItem(index=i, error=data))

    if error_occured:
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

    return TransactionDecision(
        transaction=transaction.to_transaction(),
        rule_results=transaction.rule_results,
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
    user_id: Optional[uuid.UUID] = Query(default=None, alias="userId"),
    status: Optional[TransactionStatus] = None,
    is_fraud: Optional[bool] = Query(default=None, alias="isFraud"),
) -> PagedTransactions:
    if not from_time < to:
        raise TimeValidationError(from_time, to)

    query = (
        select(TransactionDB)
        .order_by(col(TransactionDB.created_at).desc())
        .offset(page * size)
        .where(status is None or TransactionDB.status == status)
        .where(TransactionDB.created_at > from_time, TransactionDB.created_at < to)
        .where(is_fraud is None or TransactionDB.is_fraud == is_fraud)
        .limit(size)
    )

    if user_id is not None and user.role.is_admin():
        query = query.where(TransactionDB.user_id == user_id)
    elif not user.role.is_admin():
        query = query.where(TransactionDB.user_id == user.id)

    logger.info("flags are: " + f"{user_id=} {status=} {is_fraud=} {user.role=}")
    logger.info(f"query is: {str(query)}")
    result = list(map(TransactionDB.to_transaction, session.exec(query)))

    return PagedTransactions(items=result, size=size, page=page, total=len(result))
