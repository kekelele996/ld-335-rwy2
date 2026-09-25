from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timezone import business_now
from app.db.session import Base


class ExpenseBatch(Base):
    """费用上传批次：费用链路的唯一凭据，上传后金额即冻结，结算全程只认批次。"""

    __tablename__ = "expense_batches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    batch_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    visit_no: Mapped[str] = mapped_column(String(64), index=True)
    insured_id: Mapped[str] = mapped_column(String(32), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    item_count: Mapped[int]
    # ACTIVE 可结算；REVERSED 已随结算冲正，保留留痕，此时同一就诊号可重新上传
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["ExpenseItem"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )

    # 同一就诊号只允许存在一个未冲正批次（部分唯一索引在 init.sql 中声明）
    __table_args__ = (
        Index(
            "ux_expense_batches_visit_active",
            visit_no,
            unique=True,
            postgresql_where=(status == "ACTIVE"),
        ),
    )


class ExpenseItem(Base):
    """费用明细：随批次持久化，预结算/正式结算金额一律由服务端据此重算。"""

    __tablename__ = "expense_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("expense_batches.id"))
    line_no: Mapped[int]
    item_code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32))
    catalog_class: Mapped[str] = mapped_column(String(8))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    self_pay_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4))

    batch: Mapped["ExpenseBatch"] = relationship(back_populates="items")


class PresettlementVoucher(Base):
    """预结算凭证：服务端基于批次核算生成，正式结算只认凭证号。"""

    __tablename__ = "presettlement_vouchers"

    id: Mapped[int] = mapped_column(primary_key=True)
    voucher_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    batch_no: Mapped[str] = mapped_column(String(64), ForeignKey("expense_batches.batch_no"), index=True)
    region: Mapped[str] = mapped_column(String(64))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reimbursed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    account_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    self_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    deductible: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reimbursement_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    # VALID 可用于正式结算；SUPERSEDED 被同批次新凭证取代；SETTLED 已正式结算
    status: Mapped[str] = mapped_column(String(16), default="VALID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SettlementRecord(Base):
    """正式结算单：由凭证生成，一凭证最多一张成功结算单（数据库层唯一约束）。"""

    __tablename__ = "settlement_records"
    __table_args__ = (
        UniqueConstraint("voucher_no", name="ux_settlements_voucher"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    settlement_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    voucher_no: Mapped[str] = mapped_column(String(64), index=True)
    batch_no: Mapped[str] = mapped_column(String(64), index=True)
    visit_no: Mapped[str] = mapped_column(String(64), index=True)
    insured_id: Mapped[str] = mapped_column(String(32), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reimbursed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    account_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    self_pay_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # SUCCESS 成功；REVERSED 当日全额冲正
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS")
    settlement_date: Mapped[date] = mapped_column(
        Date, default=lambda: business_now().date(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
