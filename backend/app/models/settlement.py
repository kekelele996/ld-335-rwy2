from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timezone import business_now
from app.db.session import Base


class PreSettlementVoucher(Base):
    __tablename__ = "pre_settlement_vouchers"
    __table_args__ = (
        Index(
            "ix_pre_settlement_vouchers_active_batch",
            "batch_no",
            unique=True,
            postgresql_where=text("status = 'CALCULATED'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    voucher_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    batch_no: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("expense_batches.batch_no"),
        index=True,
    )
    insured_region: Mapped[str] = mapped_column(String(64))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reimbursed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    account_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    self_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    deductible: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reimbursement_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    status: Mapped[str] = mapped_column(String(32), default="CALCULATED", index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    batch = relationship("ExpenseBatch")
    settlement: Mapped["SettlementRecord | None"] = relationship(
        back_populates="voucher",
        uselist=False,
    )


class SettlementRecord(Base):
    __tablename__ = "settlement_records"
    __table_args__ = (
        Index(
            "ix_settlement_records_successful_voucher",
            "voucher_no",
            unique=True,
            postgresql_where=text("status IN ('SUCCESS', 'REVERSED')"),
        ),
        Index(
            "ix_settlement_records_active_visit",
            "visit_no",
            unique=True,
            postgresql_where=text("status = 'SUCCESS'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    settlement_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    voucher_no: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("pre_settlement_vouchers.voucher_no"),
        index=True,
    )
    source_batch_no: Mapped[str] = mapped_column(String(64), index=True)
    insured_id: Mapped[str] = mapped_column(String(32), index=True)
    visit_no: Mapped[str] = mapped_column(String(64), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reimbursed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    account_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    self_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now, index=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    voucher: Mapped[PreSettlementVoucher] = relationship(back_populates="settlement")
