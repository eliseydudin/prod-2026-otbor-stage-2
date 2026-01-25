from datetime import UTC, datetime, timedelta
from typing import Optional
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlmodel import col, select

from app.database import SessionDep
from app.exceptions import AppError, TimeValidationError
from app.jwt import CurrentAdmin, CurrentUser
from app.models import (
    FraudRuleEvaluationResult,
    MerchantRiskRow,
    MerchantRiskStats,
    RuleMatchRowStat,
    RuleMatchStats,
    StatsOverview,
    TimeseriesGrouping,
    TimeseriesPointStore,
    TimeseriesPoint,
    TimeseriesResponse,
    Transaction,
    TransactionChannel,
    TransactionDB,
    TransactionLocation,
    TransactionsAnalysisResult,
    UserStats,
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
        alias="from",
        default_factory=lambda: datetime.now(UTC) - timedelta(days=30),
    ),
    to: datetime = Query(default_factory=lambda: datetime.now(UTC)),
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
        alias="from",
        default_factory=lambda: datetime.now(UTC) - timedelta(days=30),
    ),
    to: datetime = Query(default_factory=lambda: datetime.now(UTC)),
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
        alias="from",
        default_factory=lambda: datetime.now(UTC) - timedelta(days=30),
    ),
    to: datetime = Query(default_factory=lambda: datetime.now(UTC)),
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


def get_decline_rate_for(session: SessionDep, id: uuid.UUID):
    now = datetime.now()
    now_minus_24h = now - timedelta(days=30)

    transactions = session.exec(
        select(TransactionDB)
        .where(
            TransactionDB.timestamp < now,
            TransactionDB.timestamp >= now_minus_24h,
            TransactionDB.user_id == id,
        )
        .order_by(col(TransactionDB.timestamp).desc())
    )

    all = 0
    declined = 0

    for transaction in transactions:
        all += 1
        if transaction.status.is_declined():
            declined += 1

    return 0.0 if all == 0 else round(declined / all, 2)


def get_last_seen_at(session: SessionDep, id: uuid.UUID):
    for trans in session.exec(
        select(TransactionDB)
        .where(TransactionDB.user_id == id)
        .order_by(col(TransactionDB.timestamp).desc())
    ):
        return trans.timestamp.replace(tzinfo=UTC)

    return None


@stats_router.get("/users/{id}/risk-profile")
async def user_risk_profile(
    user: CurrentUser,
    id: uuid.UUID,
    session: SessionDep,
) -> UserStats:
    if user.id != id and user.role.is_user():
        raise AppError.make_forbidden_error()

    now = datetime.now()
    now_minus_24h = now - timedelta(hours=24)

    transactions = list(
        session.exec(
            select(TransactionDB)
            .where(
                TransactionDB.timestamp < now,
                TransactionDB.timestamp >= now_minus_24h,
                TransactionDB.user_id == id,
            )
            .order_by(col(TransactionDB.timestamp).desc())
        )
    )

    decline_rate = get_decline_rate_for(session, id)
    last_seen_at = get_last_seen_at(session, id)

    if len(transactions) == 0:
        return UserStats(
            user_id=id,
            gmv_24h=0,
            distinct_devices_24h=0,
            distinct_cities_24h=0,
            decline_rate_30d=decline_rate,
            tx_count_24h=0,
            distinct_ips_24h=0,
            last_seen_at=last_seen_at,
        )

    devices: set[str] = set()
    cities: set[str] = set()
    ips: set[str] = set()
    gmv = 0.0

    for transaction in transactions:
        if transaction.device_id is not None:
            devices.add(transaction.device_id)

        if transaction.location is not None:
            loc = TransactionLocation.model_validate(transaction.location)
            if loc.city is not None:
                cities.add(loc.city)

        if transaction.ip_address is not None:
            ips.add(transaction.ip_address)

        gmv += transaction.amount

    return UserStats(
        user_id=id,
        gmv_24h=gmv,
        distinct_devices_24h=len(devices),
        distinct_cities_24h=len(cities),
        distinct_ips_24h=len(ips),
        decline_rate_30d=decline_rate,
        last_seen_at=last_seen_at,
        tx_count_24h=len(transactions),
    )


@stats_router.get("/transactions/timeseries")
async def transactions_timeseries(
    _admin: CurrentAdmin,
    session: SessionDep,
    from_time: datetime = Query(
        alias="from",
        default_factory=lambda: datetime.now(UTC) - timedelta(days=6, hours=23),
    ),
    to: datetime = Query(default_factory=lambda: datetime.now(UTC)),
    tz: str = Query(default="UTC", alias="timezone"),
    channel: Optional[TransactionChannel] = None,
    group_by: TimeseriesGrouping = Query(
        default=TimeseriesGrouping.DAY, alias="groupBy"
    ),
) -> TimeseriesResponse:
    timezone = ZoneInfo(tz)

    if group_by == TimeseriesGrouping.HOUR:
        max_days = 7
    elif group_by == TimeseriesGrouping.DAY:
        max_days = 90
    else:
        max_days = 365

    diff = group_by.as_timedelta()

    if to - from_time > timedelta(days=max_days):
        raise TimeValidationError(
            from_time,
            to,
            f"difference between `from` and `to` is bigger than {max_days} days",
        )

    transactions = session.exec(
        select(TransactionDB)
        .where(
            TransactionDB.timestamp < to,
            TransactionDB.timestamp >= from_time,
            channel is None or TransactionDB.channel == channel,
        )
        .order_by(col(TransactionDB.timestamp).asc())
    )

    points: list[TimeseriesPoint] = []
    current_store = TimeseriesPointStore(bucket_start=from_time)

    for transaction in transactions:
        print(transaction.timestamp)
        print(current_store.bucket_start)
        while (
            transaction.timestamp.replace(tzinfo=UTC)
            > current_store.bucket_start + diff
        ):
            points.append(current_store.into_timeseries_point(timezone))
            current_store = TimeseriesPointStore(
                bucket_start=current_store.bucket_start + diff
            )

        current_store.tx_count += 1
        current_store.gmv += transaction.amount
        if transaction.status.is_approved():
            current_store.approved += 1

    points.append(current_store.into_timeseries_point())

    return TimeseriesResponse(points=points)
