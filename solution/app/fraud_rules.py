from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from sqlmodel import select, col
import uuid

from app.database import SessionDep
from app.exceptions import AppError
from app.jwt import CurrentAdmin
from app.models import (
    DslError,
    DslValidateRequest,
    DslValidateResponse,
    FraudRule,
    FraudRuleCreateRequest,
    FraudRuleDB,
    FraudRuleUpdateRequest,
)
from app import dsl

fraud_rules_router = APIRouter(prefix="/fraud-rules", tags=["FraudRules"])


@fraud_rules_router.get("/", response_model=list[FraudRule])
async def all_rules(_admin: CurrentAdmin, session: SessionDep):
    return map(
        FraudRule.from_db_rule,
        session.exec(
            select(FraudRuleDB)
            .where(FraudRuleDB.enabled)
            .order_by(col(FraudRuleDB.priority))
        ),
    )


@fraud_rules_router.post("/", response_model=FraudRule, status_code=201)
async def create_fraud_rule(
    _admin: CurrentAdmin, session: SessionDep, request: FraudRuleCreateRequest
):
    try:
        dsl_expression_json = dsl.try_jsonify_rule(request.dsl_expression)
    except dsl.ParserError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Bad DSL"
        )

    db_fraud_rule = FraudRuleDB(
        **request.model_dump(), dsl_expression_json=dsl_expression_json
    )

    try:
        session.add(db_fraud_rule)
        session.commit()
        session.refresh(db_fraud_rule)

        return FraudRule.from_db_rule(db_fraud_rule)

    except Exception as e:
        raise AppError.make_internal_server_error(e)


@fraud_rules_router.post("/validate", response_model=DslValidateResponse)
async def validate(_admin: CurrentAdmin, request: DslValidateRequest):
    result = dsl.try_normalize(request.dsl_expression)

    if isinstance(result, str):
        return DslValidateResponse(
            is_valid=True, errors=[], normalized_expression=result
        )
    else:
        return DslValidateResponse(
            is_valid=False,
            errors=list(map(DslError.from_parser_error, result)),
        )


@fraud_rules_router.get("/{id}")
async def rule_get(
    id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentAdmin,
):
    rule = session.exec(
        select(FraudRuleDB).where(FraudRuleDB.id == id).where(FraudRuleDB.enabled)
    ).one_or_none()
    if rule is None:
        raise AppError.make_not_found_error("Правило не найдено")

    return FraudRule.from_db_rule(rule)


@fraud_rules_router.put("/{id}")
async def rule_put(
    id: uuid.UUID,
    request: FraudRuleUpdateRequest,
    session: SessionDep,
    _admin: CurrentAdmin,
):
    rule = session.exec(
        select(FraudRuleDB).where(FraudRuleDB.id == id).where(FraudRuleDB.enabled)
    ).one_or_none()

    if rule is None:
        raise AppError.make_not_found_error("Правило не найдено")

    rule.updated_at = datetime.now()
    rule.name = request.name

    try:
        dsl_expression_json = dsl.try_jsonify_rule(request.dsl_expression)
    except dsl.ParserError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Bad DSL"
        )

    rule.dsl_expression = request.dsl_expression
    rule.dsl_expression_json = dsl_expression_json
    rule.enabled = request.enabled
    rule.priority = request.priority

    if "description" in request.__pydantic_fields_set__:
        rule.description = request.description

    session.add(rule)
    session.commit()
    session.refresh(rule)

    return FraudRule.from_db_rule(rule)


@fraud_rules_router.delete("/{id}", status_code=204)
async def rule_delete(
    id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentAdmin,
):
    rule = session.exec(
        select(FraudRuleDB).where(FraudRuleDB.id == id).where(FraudRuleDB.enabled)
    ).one_or_none()

    if rule is None or not rule.enabled:
        raise AppError.make_not_found_error("Правило не найдено")

    rule.enabled = False
    session.add(rule)
    session.commit()
    session.refresh(rule)
