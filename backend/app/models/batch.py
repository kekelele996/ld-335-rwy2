from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timezone import business_now
from app.db.session import Base


class ExpenseBatch(Base):
    __tablename__ = "expense_batches"
    __table_args__ = (
        Index(
            "ix_expense_batches_open_visit",
            "visit_no",
            unique=True,
            postgresql_where=text("status IN ('UPLOADED', 'PRE_SETTLED')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    batch_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    visit_no: Mapped[str] = mapped_column(String(64), index=True)
    insured_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="UPLOADED", index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    item_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)

    items: Mapped[list["ExpenseItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ExpenseItem.line_no",
    )


class ExpenseItem(Base):
    __tablename__ = "expense_items"
    __table_args__ = (
        Index("ix_expense_items_batch_line", "batch_no", "line_no", unique=True),
        Index("ix_expense_items_batch_code", "batch_no", "item_code", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    batch_no: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("expense_batches.batch_no", ondelete="CASCADE"),
        index=True,
    )
    line_no: Mapped[int] = mapped_column(Integer)
    item_code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    catalog_class: Mapped[str] = mapped_column(String(16))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    self_pay_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)

    batch: Mapped[ExpenseBatch] = relationship(back_populates="items")
