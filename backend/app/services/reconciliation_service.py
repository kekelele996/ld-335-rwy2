from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settlement import SettlementRecord


def daily_summary(day: date, db: Session, principal: dict) -> dict:
    start_at = datetime.combine(day, time.min)
    end_at = datetime.combine(day, time.max)
    records = db.scalars(
        select(SettlementRecord).where(
            SettlementRecord.created_at >= start_at,
            SettlementRecord.created_at <= end_at,
        )
    ).all()

    success_records = [r for r in records if r.status == "SUCCESS"]
    reversed_records = [r for r in records if r.status == "REVERSED"]
    failed_records = [r for r in records if r.status not in {"SUCCESS", "REVERSED"}]

    gross_amount = sum((r.total_amount for r in records), Decimal("0.00"))
    # 已冲正金额不计入日终汇总，净额 = 成功未冲正金额
    net_amount = sum((r.total_amount for r in success_records), Decimal("0.00"))
    reversed_amount = sum((r.total_amount for r in reversed_records), Decimal("0.00"))

    return {
        "day": day.isoformat(),
        "total_count": len(records),
        "success_count": len(success_records),
        "reversed_count": len(reversed_records),
        "failed_count": len(failed_records),
        "gross_amount": str(gross_amount),
        "reversed_amount": str(reversed_amount),
        "total_amount": str(net_amount),
        "manual_review_count": len(failed_records),
    }
