from fastapi import APIRouter, HTTPException, status
from sqlmodel import select, col

from app.database import SessionDep
from app.jwt import CurrentAdminUser
from app.models import (
    DslError,
    DslValidateRequest,
    DslValidateResponse,
    FraudRule,
    FraudRuleCreateRequest,
    FraudRuleDB,
)
from app import dsl

fraud_rules_router = APIRouter(prefix="/fraud-rules")


@fraud_rules_router.get("/", response_model=list[FraudRule])
async def all_rules(_admin: CurrentAdminUser, session: SessionDep):
    return map(
        FraudRule.from_db_rule,
        session.exec(select(FraudRuleDB).order_by(col(FraudRuleDB.priority))),
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
