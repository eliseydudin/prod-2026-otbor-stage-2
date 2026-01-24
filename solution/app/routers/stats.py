from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Query
from sqlmodel import select

from app.database import SessionDep
from app.exceptions import TimeValidationError
from app.jwt import CurrentAdmin
from app.models import MerchantRiskRow, StatsOverview, TransactionDB, TransactionStatus

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
    risk_merchants: defaultdict[tuple[str, str], tuple[float, int, int]] = defaultdict(
        lambda: (0.0, 0, 0)
    )

    def to_risk_merchant_row(
        key: tuple[str, str], val: tuple[float, int, int]
    ) -> MerchantRiskRow:
        return MerchantRiskRow(
            merchant_id=key[0],
            merchant_category_code=key[1],
            gmv=val[0],
            tx_count=val[1],
            decline_rate=0 if val[1] == 0 else val[2] / val[1],
        )

    for transaction in transactions:
        gmv += transaction.amount
        transaction_count += 1
        if transaction.status == TransactionStatus.APPROVED:
            approved += 1

        if (
            transaction.merchant_id is None
            or transaction.merchant_category_code is None
        ):
            continue

        key = (transaction.merchant_id, transaction.merchant_category_code)
        data = risk_merchants[key]
        risk_merchants[key] = (
            data[0] + transaction.amount,
            data[1] + 1,
            data[2] + 1 if transaction.status == TransactionStatus.DECLINED else 0,
        )

    approval_rate = 0.0 if transaction_count == 0 else gmv / transaction_count
    top_risk_merchants = list(
        map(
            lambda item: to_risk_merchant_row(item[0], item[1]),
            risk_merchants.items(),
        )
    )
    top_risk_merchants.sort(key=lambda row: row.decline_rate, reverse=True)
    top_risk_merchants = top_risk_merchants[:10]

    return StatsOverview(
        from_time=from_time,
        to=to,
        volume=transaction_count,
        gmv=gmv,
        approval_rate=approval_rate,
        decline_rate=0.0 if transaction_count == 0 else 1.0 - approval_rate,
        top_risk_merchants=top_risk_merchants,
    )
