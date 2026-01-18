from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from sqlmodel import select, col
import uuid

from app.database import SessionDep
from app.jwt import CurrentAdminUser
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
async def all_rules(_admin: CurrentAdminUser, session: SessionDep):
    return map(
        FraudRule.from_db_rule,
        session.exec(
            select(FraudRuleDB)
            .where(FraudRuleDB.enabled)
            .order_by(col(FraudRuleDB.priority))
        ),
    )


@fraud_rules_router.post("/", response_model=FraudRule)
async def create_fraud_rule(
    _admin: CurrentAdminUser, session: SessionDep, request: FraudRuleCreateRequest
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

    except Exception:
        raise HTTPException(status_code=409, detail="Database failure")


@fraud_rules_router.post("/validate", response_model=DslValidateResponse)
async def validate(_admin: CurrentAdminUser, request: DslValidateRequest):
    try:
        _ = dsl.try_jsonify_rule(request.dsl_expression)
        return DslValidateResponse(is_valid=True, errors=[])

    except dsl.ParserError as e:
        return DslValidateResponse(
            is_valid=True, errors=[DslError.from_parser_error(e)]
        )


@fraud_rules_router.get("/{id}")
async def rule_get(
    id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentAdminUser,
):
    rule = session.exec(
        select(FraudRuleDB).where(FraudRuleDB.id == id).where(FraudRuleDB.enabled)
    ).one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return FraudRule.from_db_rule(rule)


@fraud_rules_router.put("/{id}")
async def rule_put(
    id: uuid.UUID,
    request: FraudRuleUpdateRequest,
    session: SessionDep,
    _admin: CurrentAdminUser,
):
    rule = session.exec(
        select(FraudRuleDB).where(FraudRuleDB.id == id).where(FraudRuleDB.enabled)
    ).one_or_none()

    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

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
    _admin: CurrentAdminUser,
):
    rule = session.exec(
        select(FraudRuleDB).where(FraudRuleDB.id == id).where(FraudRuleDB.enabled)
    ).one_or_none()

    if rule is None or not rule.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    rule.enabled = False
    session.add(rule)
    session.commit()
    session.refresh(rule)
