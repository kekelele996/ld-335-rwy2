from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.messages import ErrorMessages
from app.core.timezone import business_now
from app.models.settlement import (
    ExpenseBatch,
    ExpenseItem,
    PresettlementVoucher,
    SettlementRecord,
)
from app.schemas.settlement import (
    ExpenseUploadRequest,
    ExpenseUploadResponse,
    PreSettlementRequest,
    PreSettlementResponse,
    PresettlementDetail,
    SettlementConfirmRequest,
    SettlementResponse,
)

CENT = Decimal("0.01")
REIMBURSEMENT_RATIO = Decimal("0.78")
ACCOUNT_PAY_CAP = Decimal("800.00")


def _gen_no(prefix: str, length: int) -> str:
    return f"{prefix}{uuid4().hex[:length].upper()}"


def upload_expenses(payload: ExpenseUploadRequest, db: Session, principal: dict) -> ExpenseUploadResponse:
    """上传后即保存批次、明细与就诊号；同一就诊号只允许一个未冲正批次。"""
    active_batch = db.scalar(
        select(ExpenseBatch).where(
            ExpenseBatch.visit_no == payload.visit_no,
            ExpenseBatch.status == "ACTIVE",
        )
    )
    if active_batch:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorMessages.VISIT_BATCH_ACTIVE,
        )

    total = sum((item.amount for item in payload.items), Decimal("0.00")).quantize(CENT)
    batch = ExpenseBatch(
        batch_no=_gen_no("UP", 12),
        visit_no=payload.visit_no,
        insured_id=payload.insured_id,
        total_amount=total,
        item_count=len(payload.items),
        status="ACTIVE",
    )
    batch.items = [
        ExpenseItem(
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
        # 并发上传时由部分唯一索引兜底：同一就诊号只能有一个 ACTIVE 批次
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorMessages.VISIT_BATCH_ACTIVE,
        )
    db.refresh(batch)
    return ExpenseUploadResponse(
        batch_no=batch.batch_no,
        visit_no=batch.visit_no,
        accepted_count=batch.item_count,
        total_amount=batch.total_amount,
        status=batch.status,
        uploaded_at=batch.uploaded_at,
    )


def _calculate(batch: ExpenseBatch, region: str) -> dict[str, Decimal]:
    """服务端按参保地政策与已冻结明细核算，金额不接受 HIS 传入。"""
    total = sum((item.amount for item in batch.items), Decimal("0.00")).quantize(CENT)
    deductible = Decimal("650.00") if region.endswith("市") else Decimal("450.00")
    reimbursable = max(total - deductible, Decimal("0.00"))
    reimbursed = (reimbursable * REIMBURSEMENT_RATIO).quantize(CENT)
    account_pay = min(ACCOUNT_PAY_CAP, max(total - reimbursed, Decimal("0.00"))).quantize(CENT)
    self_pay = (total - reimbursed - account_pay).quantize(CENT)
    return {
        "total_amount": total,
        "reimbursed_amount": reimbursed,
        "account_pay_amount": account_pay,
        "self_pay_amount": self_pay,
        "deductible": deductible,
        "reimbursement_ratio": REIMBURSEMENT_RATIO,
    }


def pre_settle(payload: PreSettlementRequest, db: Session, principal: dict) -> PreSettlementResponse:
    """只提交批次号与参保地，服务端核算并生成预结算凭证；支持多次预结算比对。"""
    batch = db.scalar(
        select(ExpenseBatch).where(ExpenseBatch.batch_no == payload.batch_no).with_for_update()
    )
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ErrorMessages.BATCH_NOT_FOUND)
    if batch.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ErrorMessages.BATCH_REVERSED)

    amounts = _calculate(batch, payload.region)

    # 同批次再次预结算时旧凭证作废，仅最新 VALID 凭证可用于正式结算
    for voucher in db.scalars(
        select(PresettlementVoucher).where(
            PresettlementVoucher.batch_no == batch.batch_no,
            PresettlementVoucher.status == "VALID",
        )
    ).all():
        voucher.status = "SUPERSEDED"

    voucher = PresettlementVoucher(
        voucher_no=_gen_no("YJ", 16),
        batch_no=batch.batch_no,
        region=payload.region,
        status="VALID",
        **amounts,
    )
    db.add(voucher)
    db.commit()
    db.refresh(voucher)

    details = [
        PresettlementDetail(
            line_no=item.line_no,
            item_code=item.item_code,
            name=item.name,
            category=item.category,
            catalog_class=item.catalog_class,
            unit_price=item.unit_price,
            quantity=item.quantity,
            amount=item.amount,
            self_pay_ratio=item.self_pay_ratio,
        )
        for item in sorted(batch.items, key=lambda it: it.line_no)
    ]
    return PreSettlementResponse(
        voucher_no=voucher.voucher_no,
        batch_no=voucher.batch_no,
        region=voucher.region,
        total_amount=voucher.total_amount,
        reimbursed_amount=voucher.reimbursed_amount,
        account_pay_amount=voucher.account_pay_amount,
        self_pay_amount=voucher.self_pay_amount,
        deductible=voucher.deductible,
        reimbursement_ratio=voucher.reimbursement_ratio,
        status=voucher.status,
        created_at=voucher.created_at,
        details=details,
    )


def confirm_settlement(payload: SettlementConfirmRequest, db: Session, principal: dict) -> SettlementResponse:
    """正式结算只认凭证号；同一凭证不能重复成功（网络重试返回原结算单）。"""
    # 快速幂等路径：重试请求直接返回已成功的结算单
    existing = db.scalar(
        select(SettlementRecord).where(SettlementRecord.voucher_no == payload.voucher_no)
    )
    if existing:
        return SettlementResponse.model_validate(existing)

    try:
        voucher = db.scalar(
            select(PresettlementVoucher)
            .where(PresettlementVoucher.voucher_no == payload.voucher_no)
            .with_for_update()
        )
        if not voucher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorMessages.VOUCHER_NOT_FOUND,
            )
        if voucher.status == "SETTLED":
            db.rollback()
            existing = db.scalar(
                select(SettlementRecord).where(SettlementRecord.voucher_no == payload.voucher_no)
            )
            return SettlementResponse.model_validate(existing)
        if voucher.status == "SUPERSEDED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorMessages.VOUCHER_SUPERSEDED,
            )

        batch = db.scalar(
            select(ExpenseBatch).where(ExpenseBatch.batch_no == voucher.batch_no).with_for_update()
        )
        if not batch or batch.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorMessages.BATCH_REVERSED,
            )

        now = business_now()
        record = SettlementRecord(
            settlement_no=_gen_no("JS", 14),
            voucher_no=voucher.voucher_no,
            batch_no=batch.batch_no,
            visit_no=batch.visit_no,
            insured_id=batch.insured_id,
            total_amount=voucher.total_amount,
            reimbursed_amount=voucher.reimbursed_amount,
            account_pay_amount=voucher.account_pay_amount,
            self_pay_amount=voucher.self_pay_amount,
            status="SUCCESS",
            settlement_date=now.date(),
            created_at=now,
        )
        voucher.status = "SETTLED"
        voucher.settled_at = now
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            # ux_settlements_voucher 唯一约束兜底并发重试
            db.rollback()
            existing = db.scalar(
                select(SettlementRecord).where(SettlementRecord.voucher_no == payload.voucher_no)
            )
            return SettlementResponse.model_validate(existing)
        db.refresh(record)
        return SettlementResponse.model_validate(record)
    except HTTPException:
        db.rollback()
        raise


def reverse_settlement(settlement_no: str, db: Session, principal: dict) -> SettlementResponse:
    """当日全额冲正：原批次保留并标记 REVERSED，同一就诊号即可重新上传。冲正幂等。"""
    record = db.scalar(
        select(SettlementRecord).where(SettlementRecord.settlement_no == settlement_no).with_for_update()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ErrorMessages.SETTLEMENT_NOT_FOUND)
    if record.status == "REVERSED":
        # 网络重试不重复冲正，直接返回已冲正的原单
        return SettlementResponse.model_validate(record)
    if record.settlement_date != business_now().date():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorMessages.SETTLEMENT_NOT_REVERSIBLE,
        )

    now = business_now()
    record.status = "REVERSED"
    record.reversed_at = now

    batch = db.scalar(
        select(ExpenseBatch).where(ExpenseBatch.batch_no == record.batch_no).with_for_update()
    )
    if batch:
        batch.status = "REVERSED"
        batch.reversed_at = now

    voucher = db.scalar(
        select(PresettlementVoucher).where(PresettlementVoucher.voucher_no == record.voucher_no)
    )
    if voucher:
        voucher.status = "SUPERSEDED"

    db.commit()
    db.refresh(record)
    return SettlementResponse.model_validate(record)


def query_settlements(
    db: Session,
    principal: dict,
    settlement_no: str | None,
    insured_id: str | None,
    batch_no: str | None,
    visit_no: str | None,
    start: date | None,
    end: date | None,
) -> list[SettlementResponse]:
    """结算列表带来源批次与冲正时间。"""
    statement = select(SettlementRecord)
    if settlement_no:
        statement = statement.where(SettlementRecord.settlement_no == settlement_no)
    if insured_id:
        statement = statement.where(SettlementRecord.insured_id == insured_id)
    if batch_no:
        statement = statement.where(SettlementRecord.batch_no == batch_no)
    if visit_no:
        statement = statement.where(SettlementRecord.visit_no == visit_no)
    if start:
        statement = statement.where(SettlementRecord.created_at >= datetime.combine(start, time.min))
    if end:
        statement = statement.where(SettlementRecord.created_at < datetime.combine(end + timedelta(days=1), time.min))
    records = db.scalars(statement.order_by(SettlementRecord.created_at.desc())).all()
    return [SettlementResponse.model_validate(record) for record in records]
