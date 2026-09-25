from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class ExpenseItem(BaseModel):
    item_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=32)
    catalog_class: str = Field(pattern="^(甲类|乙类|丙类)$")
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    self_pay_ratio: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)

    @field_validator("name", "category", "item_code")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value

    @model_validator(mode="after")
    def validate_amount(self) -> "ExpenseItem":
        expected_amount = (self.unit_price * self.quantity).quantize(Decimal("0.01"))
        if expected_amount != self.amount.quantize(Decimal("0.01")):
            raise ValueError("金额必须等于单价乘以数量")
        return self


class ExpenseUploadRequest(BaseModel):
    insured_id: str = Field(min_length=1, max_length=32)
    visit_no: str = Field(min_length=1, max_length=64)
    items: list[ExpenseItem] = Field(min_length=1)

    @field_validator("insured_id", "visit_no")
    @classmethod
    def strip_identity_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value


class ExpenseUploadResponse(BaseModel):
    batch_no: str
    visit_no: str
    accepted_count: int
    total_amount: Decimal
    status: str


class PreSettlementRequest(BaseModel):
    batch_no: str = Field(min_length=1, max_length=64)
    insured_region: str = Field(min_length=1, max_length=64)

    @field_validator("batch_no", "insured_region")
    @classmethod
    def strip_value(cls, value: str) -> str:
        return value.strip()


class PreSettlementItem(BaseModel):
    item_code: str
    name: str
    category: str
    catalog_class: str
    unit_price: Decimal
    quantity: Decimal
    amount: Decimal
    self_pay_ratio: Decimal

    model_config = {"from_attributes": True}


class PreSettlementResponse(BaseModel):
    voucher_no: str
    batch_no: str
    insured_region: str
    total_amount: Decimal
    reimbursed_amount: Decimal
    account_pay_amount: Decimal
    self_pay_amount: Decimal
    deductible: Decimal
    reimbursement_ratio: Decimal
    status: str
    calculated_at: datetime
    details: list[PreSettlementItem]


class SettlementConfirmRequest(BaseModel):
    voucher_no: str = Field(min_length=1, max_length=64)

    @field_validator("voucher_no")
    @classmethod
    def strip_voucher_no(cls, value: str) -> str:
        return value.strip()


class SettlementResponse(BaseModel):
    settlement_no: str
    voucher_no: str
    source_batch_no: str
    insured_id: str
    visit_no: str
    total_amount: Decimal
    reimbursed_amount: Decimal
    account_pay_amount: Decimal
    self_pay_amount: Decimal
    status: str
    created_at: datetime
    reversed_at: datetime | None = None

    model_config = {"from_attributes": True}
