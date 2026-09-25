from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settlement import SettlementRecord


def daily_summary(day: date, db: Session, principal: dict) -> dict:
    start_at = datetime.combine(day, time.min)
    end_at = datetime.combine(day, time.max)
    filters = [
        SettlementRecord.created_at >= start_at,
        SettlementRecord.created_at <= end_at,
    ]

    records = db.scalars(select(SettlementRecord).where(*filters)).all()
    active_records = [record for record in records if record.status != "REVERSED"]
    success_records = [record for record in records if record.status == "SUCCESS"]

    def sum_field(field_name: str, rows: list[SettlementRecord]) -> Decimal:
        return sum((getattr(row, field_name) for row in rows), Decimal("0.00"))

    failed_count = sum(1 for record in records if record.status not in {"SUCCESS", "REVERSED"})
    return {
        "day": day.isoformat(),
        "total_count": len(records),
        "active_count": len(active_records),
        "success_count": len(success_records),
        "reversed_count": len(records) - len(active_records),
        "failed_count": failed_count,
        "total_amount": str(sum_field("total_amount", active_records)),
        "reimbursed_amount": str(sum_field("reimbursed_amount", active_records)),
        "account_pay_amount": str(sum_field("account_pay_amount", active_records)),
        "self_pay_amount": str(sum_field("self_pay_amount", active_records)),
        "reversed_amount": str(sum_field("total_amount", records) - sum_field("total_amount", active_records)),
        "manual_review_count": failed_count,
    }
