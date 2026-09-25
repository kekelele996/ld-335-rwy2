from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.messages import ErrorMessages
from app.core.timezone import business_now
from app.models.batch import ExpenseBatch, ExpenseItem
from app.models.settlement import PreSettlementVoucher, SettlementRecord
from app.schemas.settlement import (
    ExpenseUploadRequest,
    ExpenseUploadResponse,
    PreSettlementItem,
    PreSettlementRequest,
    PreSettlementResponse,
    SettlementConfirmRequest,
    SettlementResponse,
)

MONEY_SCALE = Decimal("0.01")


def _new_no(prefix: str, length: int) -> str:
    return f"{prefix}{uuid4().hex[:length].upper()}"


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_SCALE)


def upload_expenses(payload: ExpenseUploadRequest, db: Session, principal: dict) -> ExpenseUploadResponse:
    item_codes = [item.item_code for item in payload.items]
    if len(item_codes) != len(set(item_codes)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ErrorMessages.DUPLICATED_ITEM)

    active_settlement = db.scalar(
        select(SettlementRecord).where(
            SettlementRecord.visit_no == payload.visit_no,
            SettlementRecord.status == "SUCCESS",
        )
    )
    if active_settlement:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorMessages.ACTIVE_SETTLEMENT_EXISTS,
        )

    open_batch = db.scalar(
        select(ExpenseBatch).where(
            ExpenseBatch.visit_no == payload.visit_no,
            ExpenseBatch.status.in_(["UPLOADED", "PRE_SETTLED"]),
        )
    )
    if open_batch:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ErrorMessages.BATCH_ALREADY_OPEN)

    total_amount = _money(sum((item.amount for item in payload.items), Decimal("0.00")))
    batch = ExpenseBatch(
        batch_no=_new_no("UP", 14),
        visit_no=payload.visit_no,
        insured_id=payload.insured_id,
        status="UPLOADED",
        total_amount=total_amount,
        item_count=len(payload.items),
    )
    batch.items = [
        ExpenseItem(
            batch_no=batch.batch_no,
            line_no=line_no,
            item_code=item.item_code,
            name=item.name,
            category=item.category,
            catalog_class=item.catalog_class,
            unit_price=item.unit_price,
            quantity=item.quantity,
            amount=item.amount,
            self_pay_ratio=item.self_pay_ratio,
        )
        for line_no, item in enumerate(payload.items, start=1)
    ]

    db.add(batch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ExpenseBatch).where(
                ExpenseBatch.visit_no == payload.visit_no,
                ExpenseBatch.status.in_(["UPLOADED", "PRE_SETTLED"]),
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorMessages.BATCH_ALREADY_OPEN,
            ) from None
        active_settlement = db.scalar(
            select(SettlementRecord).where(
                SettlementRecord.visit_no == payload.visit_no,
                SettlementRecord.status == "SUCCESS",
            )
        )
        if active_settlement:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorMessages.ACTIVE_SETTLEMENT_EXISTS,
            ) from None
        raise
    db.refresh(batch)
    return ExpenseUploadResponse(
        batch_no=batch.batch_no,
        visit_no=batch.visit_no,
        accepted_count=batch.item_count,
        total_amount=batch.total_amount,
        status=batch.status,
    )


def _calculate(items: list[ExpenseItem], region: str) -> dict[str, Decimal]:
    total = _money(sum((item.amount for item in items), Decimal("0.00")))
    eligible_total = Decimal("0.00")
    for item in items:
        if item.catalog_class == "甲类":
            eligible_rate = Decimal("1.0000") - item.self_pay_ratio
        elif item.catalog_class == "乙类":
            eligible_rate = Decimal("0.8500") * (Decimal("1.0000") - item.self_pay_ratio)
        else:
            eligible_rate = Decimal("0.0000")
        eligible_total += item.amount * eligible_rate

    deductible = Decimal("650.00") if region.endswith("市") else Decimal("450.00")
    ratio = Decimal("0.7800") if region.endswith("市") else Decimal("0.7000")
    reimbursed = _money(max(eligible_total - deductible, Decimal("0.00")) * ratio)
    account_pay = _money(min(Decimal("800.00"), max(total - reimbursed, Decimal("0.00"))))
    self_pay = _money(max(total - reimbursed - account_pay, Decimal("0.00")))
    return {
        "total_amount": total,
        "reimbursed_amount": reimbursed,
        "account_pay_amount": account_pay,
        "self_pay_amount": self_pay,
        "deductible": deductible,
        "reimbursement_ratio": ratio,
    }


def pre_settle(payload: PreSettlementRequest, db: Session, principal: dict) -> PreSettlementResponse:
    batch = db.scalar(
        select(ExpenseBatch)
        .where(ExpenseBatch.batch_no == payload.batch_no)
        .with_for_update()
    )
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ErrorMessages.BATCH_NOT_FOUND)
    if batch.status not in {"UPLOADED", "PRE_SETTLED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ErrorMessages.BATCH_NOT_OPEN)

    active_voucher = db.scalar(
        select(PreSettlementVoucher)
        .where(
            PreSettlementVoucher.batch_no == batch.batch_no,
            PreSettlementVoucher.status == "CALCULATED",
        )
        .with_for_update()
    )
    if active_voucher and active_voucher.insured_region == payload.insured_region:
        voucher = active_voucher
    else:
        if active_voucher:
            active_voucher.status = "SUPERSEDED"
        amounts = _calculate(list(batch.items), payload.insured_region)
        voucher = PreSettlementVoucher(
            voucher_no=_new_no("YS", 16),
            batch_no=batch.batch_no,
            insured_region=payload.insured_region,
            status="CALCULATED",
            **amounts,
        )
        batch.status = "PRE_SETTLED"
        db.add(voucher)

    db.commit()
    db.refresh(voucher)
    db.refresh(batch)
    return PreSettlementResponse(
        voucher_no=voucher.voucher_no,
        batch_no=voucher.batch_no,
        insured_region=voucher.insured_region,
        total_amount=voucher.total_amount,
        reimbursed_amount=voucher.reimbursed_amount,
        account_pay_amount=voucher.account_pay_amount,
        self_pay_amount=voucher.self_pay_amount,
        deductible=voucher.deductible,
        reimbursement_ratio=voucher.reimbursement_ratio,
        status=voucher.status,
        calculated_at=voucher.calculated_at,
        details=[PreSettlementItem.model_validate(item) for item in batch.items],
    )


def confirm_settlement(
    payload: SettlementConfirmRequest,
    db: Session,
    principal: dict,
) -> SettlementResponse:
    voucher = db.scalar(
        select(PreSettlementVoucher)
        .where(PreSettlementVoucher.voucher_no == payload.voucher_no)
        .with_for_update()
    )
    if not voucher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ErrorMessages.VOUCHER_NOT_FOUND)

    batch = db.scalar(
        select(ExpenseBatch)
        .where(ExpenseBatch.batch_no == voucher.batch_no)
        .with_for_update()
    )
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ErrorMessages.BATCH_NOT_FOUND)

    existing = db.scalar(
        select(SettlementRecord)
        .where(SettlementRecord.voucher_no == voucher.voucher_no)
        .with_for_update()
    )
    if existing:
        return SettlementResponse.model_validate(existing)

    if voucher.status not in {"CALCULATED", "REVERSED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ErrorMessages.VOUCHER_NOT_ACTIVE)
    if voucher.status != "CALCULATED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ErrorMessages.SETTLEMENT_REVERSED)

    if batch.status != "PRE_SETTLED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ErrorMessages.BATCH_NOT_OPEN)

    settled_at = business_now()
    record = SettlementRecord(
        settlement_no=_new_no("JS", 18),
        voucher_no=voucher.voucher_no,
        source_batch_no=batch.batch_no,
        insured_id=batch.insured_id,
        visit_no=batch.visit_no,
        total_amount=voucher.total_amount,
        reimbursed_amount=voucher.reimbursed_amount,
        account_pay_amount=voucher.account_pay_amount,
        self_pay_amount=voucher.self_pay_amount,
        status="SUCCESS",
        created_at=settled_at,
    )
    voucher.status = "SETTLED"
    voucher.used_at = settled_at
    batch.status = "SETTLED"
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(SettlementRecord).where(SettlementRecord.voucher_no == voucher.voucher_no)
        )
        if existing:
            return SettlementResponse.model_validate(existing)
        raise
    db.refresh(record)
    return SettlementResponse.model_validate(record)


def reverse_settlement(settlement_no: str, db: Session, principal: dict) -> SettlementResponse:
    record = db.scalar(
        select(SettlementRecord)
        .where(SettlementRecord.settlement_no == settlement_no)
        .with_for_update()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ErrorMessages.SETTLEMENT_NOT_FOUND)
    if record.status == "REVERSED":
        return SettlementResponse.model_validate(record)
    if record.created_at.date() != business_now().date():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorMessages.REVERSAL_WINDOW_EXPIRED,
        )

    voucher = db.scalar(
        select(PreSettlementVoucher)
        .where(PreSettlementVoucher.voucher_no == record.voucher_no)
        .with_for_update()
    )
    batch = db.scalar(
        select(ExpenseBatch)
        .where(ExpenseBatch.batch_no == record.source_batch_no)
        .with_for_update()
    )
    reversed_at = business_now()
    record.status = "REVERSED"
    record.reversed_at = reversed_at
    if voucher:
        voucher.status = "REVERSED"
        voucher.reversed_at = reversed_at
    if batch:
        batch.status = "REVERSED"
    db.commit()
    db.refresh(record)
    return SettlementResponse.model_validate(record)


def query_settlements(
    db: Session,
    principal: dict,
    settlement_no: str | None,
    insured_id: str | None,
    visit_no: str | None,
    start: date | None,
    end: date | None,
) -> list[SettlementResponse]:
    statement = select(SettlementRecord)
    if settlement_no:
        statement = statement.where(SettlementRecord.settlement_no == settlement_no)
    if insured_id:
        statement = statement.where(SettlementRecord.insured_id == insured_id)
    if visit_no:
        statement = statement.where(SettlementRecord.visit_no == visit_no)
    if start:
        statement = statement.where(SettlementRecord.created_at >= datetime.combine(start, time.min))
    if end:
        statement = statement.where(
            SettlementRecord.created_at < datetime.combine(end + timedelta(days=1), time.min)
        )
    records = db.scalars(statement.order_by(SettlementRecord.created_at.desc())).all()
    return [SettlementResponse.model_validate(record) for record in records]
