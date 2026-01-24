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
    MerchantRiskStats,
    RuleMatchRowStat,
    RuleMatchStats,
    StatsOverview,
    Transaction,
    TransactionDB,
    TransactionsAnalysisResult,
)

stats_router = APIRouter(prefix="/stats", tags=["Stats"])


def get_transactions_analysis(
    transactions: list[Transaction],
) -> TransactionsAnalysisResult:
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
            merchants[key] = MerchantRiskRow.from_merchant_data(
                key,
                transaction.merchant_category_code,
            )

        merchants[key].tx_count += 1
        merchants[key].gmv += transaction.amount
        # before we send off the data `decline_rate` stores the amount of declined
        # transactions
        merchants[key].decline_rate += 1 if transaction.status.is_declined() else 0

    for key in merchants:
        if merchants[key].tx_count == 0:
            continue
        merchants[key].decline_rate = round(
            merchants[key].decline_rate / merchants[key].tx_count, 2
        )

    top_risk_merchants = list(merchants.values())
    top_risk_merchants.sort(key=lambda row: row.decline_rate, reverse=True)

    return TransactionsAnalysisResult(
        transaction_count=transaction_count,
        approved=approved,
        gmv=gmv,
        merchants=top_risk_merchants,
    )


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

    analysis = get_transactions_analysis(list(transactions))

    approval_rate = (
        0.0
        if analysis.transaction_count == 0
        else round(analysis.approved / analysis.transaction_count, 2)
    )

    return StatsOverview(
        from_time=from_time,
        to=to,
        volume=analysis.transaction_count,
        gmv=analysis.gmv,
        approval_rate=approval_rate,
        decline_rate=(
            0.0 if analysis.transaction_count == 0 else round(1.0 - approval_rate, 2)
        ),
        top_risk_merchants=analysis.merchants[:10],
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

            if not rule.matched:
                continue

            rules[rule.rule_id].matches += 1
            rules[rule.rule_id].users_affected.add(transaction.user_id)

            if transaction.merchant_id is not None:
                rules[rule.rule_id].merchants_affected.add(transaction.merchant_id)

            if transaction.status.is_declined():
                rules[rule.rule_id].declines += 1

    rule_match_rows = map(lambda row: row.into_rule_match_row(declines), rules.values())
    rule_match_rows = list(rule_match_rows)[:top]

    return RuleMatchStats(items=rule_match_rows)


@stats_router.get("/merchants/risk")
async def merchants_risk(
    _admin: CurrentAdmin,
    session: SessionDep,
    from_time: datetime = Query(
        alias="from", default_factory=lambda: datetime.now() - timedelta(days=30)
    ),
    to: datetime = Query(default_factory=datetime.now),
    top: int = Query(default=20, le=200, ge=1),
) -> MerchantRiskStats:
    transactions = map(
        TransactionDB.to_transaction,
        session.exec(
            select(TransactionDB).where(
                TransactionDB.timestamp < to,
                TransactionDB.timestamp >= from_time,
            )
        ),
    )
    analysis = get_transactions_analysis(list(transactions))
    return MerchantRiskStats(items=analysis.merchants[:top])
