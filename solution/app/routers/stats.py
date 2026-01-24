from datetime import datetime, timedelta
import uuid

from fastapi import APIRouter, Query
from sqlmodel import select

from app.database import SessionDep
from app.exceptions import TimeValidationError
from app.jwt import CurrentAdmin
from app.models import (
    FraudRuleEvaluationResult,
    MerchantRiskRow,
    RuleMatchRowStat,
    RuleMatchStats,
    StatsOverview,
    TransactionDB,
)

stats_router = APIRouter(prefix="/stats", tags=["Stats"])


@stats_router.get("/overview")
async def overview(
    _admin: CurrentAdmin,
    session: SessionDep,
    from_time: datetime = Query(
        alias="from", default_factory=lambda: datetime.now() - timedelta(days=30)
    ),
    to: datetime = Query(default_factory=datetime.now),
) -> StatsOverview:
    if to - from_time > timedelta(days=90):
        raise TimeValidationError(
            from_time,
            to,
            "difference between `from` and `to` is bigger than 90 days",
        )

    transactions = map(
        TransactionDB.to_transaction,
        session.exec(
            select(TransactionDB).where(
                TransactionDB.timestamp < to,
                TransactionDB.timestamp >= from_time,
            )
        ),
    )
    transaction_count = 0
    approved = 0
    gmv = 0.0

    merchants: dict[str, MerchantRiskRow] = {}

    for transaction in transactions:
        gmv += transaction.amount
        transaction_count += 1
        if transaction.status.is_approved():
            approved += 1

        if transaction.merchant_id is None:
            continue

        key = transaction.merchant_id
        if key not in merchants:
            merchants[key] = MerchantRiskRow(
                merchant_id=key,
                merchant_category_code=transaction.merchant_category_code,
                tx_count=0,
                gmv=0,
                decline_rate=0,
            )

        merchants[key].tx_count += 1
        merchants[key].gmv += transaction.amount
        # before we send off the data `decline_rate` stores the amount of declined
        # transactions
        merchants[key].decline_rate += 1 if transaction.status.is_declined() else 0

    approval_rate = (
        0.0 if transaction_count == 0 else round(approved / transaction_count, 2)
    )

    for key in merchants:
        if merchants[key].tx_count == 0:
            continue
        merchants[key].decline_rate = round(
            merchants[key].decline_rate / merchants[key].tx_count, 2
        )

    top_risk_merchants = list(merchants.values())
    top_risk_merchants.sort(key=lambda row: row.decline_rate, reverse=True)
    top_risk_merchants = top_risk_merchants[:10]

    return StatsOverview(
        from_time=from_time,
        to=to,
        volume=transaction_count,
        gmv=gmv,
        approval_rate=approval_rate,
        decline_rate=0.0 if transaction_count == 0 else round(1.0 - approval_rate, 2),
        top_risk_merchants=top_risk_merchants,
    )


@stats_router.get("/rules/matches")
async def rule_matches(
    _admin: CurrentAdmin,
    session: SessionDep,
    from_time: datetime = Query(
        alias="from", default_factory=lambda: datetime.now() - timedelta(days=30)
    ),
    to: datetime = Query(default_factory=datetime.now),
    top: int = Query(default=20, le=100, ge=1),
) -> RuleMatchStats:
    if to - from_time > timedelta(days=90):
        raise TimeValidationError(
            from_time,
            to,
            "difference between `from` and `to` is bigger than 90 days",
        )

    transactions = session.exec(
        select(TransactionDB).where(
            TransactionDB.timestamp < to,
            TransactionDB.timestamp >= from_time,
        )
    )

    rules: dict[uuid.UUID, RuleMatchRowStat] = {}
    declines = 0

    for transaction in transactions:
        if transaction.status.is_declined():
            declines += 1

        for rule in transaction.rule_results:
            rule = FraudRuleEvaluationResult.model_validate(rule)
            if rule.rule_id not in rules:
                rules[rule.rule_id] = RuleMatchRowStat.from_rule_eval_result(rule)

            rules[rule.rule_id].matches += 1
            rules[rule.rule_id].users_affected.add(transaction.user_id)
            if transaction.merchant_id is not None:
                rules[rule.rule_id].merchants_affected.add(transaction.merchant_id)

            if transaction.status.is_declined():
                rules[rule.rule_id].declines += 1

    rule_match_rows = map(lambda row: row.into_rule_match_row(declines), rules.values())
    rule_match_rows = list(rule_match_rows)[:top]

    return RuleMatchStats(items=rule_match_rows)
