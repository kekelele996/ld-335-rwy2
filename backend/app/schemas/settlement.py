from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class ExpenseItem(BaseModel):
    item_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=32)
    catalog_class: str = Field(pattern="^[甲乙丙]类$")
    unit_price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    amount: Decimal = Field(gt=0)
    self_pay_ratio: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_amount(self) -> "ExpenseItem":
        expected = (self.unit_price * self.quantity).quantize(Decimal("0.01"))
        if self.amount != expected:
            raise ValueError("明细金额必须等于单价 × 数量（保留两位小数）")
        return self


class ExpenseUploadRequest(BaseModel):
    insured_id: str
    visit_no: str
    items: list[ExpenseItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_items(self) -> "ExpenseUploadRequest":
        codes = [item.item_code for item in self.items]
        if len(codes) != len(set(codes)):
            raise ValueError("费用明细存在重复项目编码")
        return self


class ExpenseUploadResponse(BaseModel):
    batch_no: str
    visit_no: str
    accepted_count: int
    total_amount: Decimal
    status: str
    uploaded_at: datetime


class PreSettlementRequest(BaseModel):
    # 预结算只提交批次号与参保地，金额由服务端依据已冻结的批次明细核算
    batch_no: str
    region: str = Field(min_length=1, max_length=64)


class PresettlementDetail(BaseModel):
    line_no: int
    item_code: str
    name: str
    category: str
    catalog_class: str
    unit_price: Decimal
    quantity: Decimal
    amount: Decimal
    self_pay_ratio: Decimal


class PreSettlementResponse(BaseModel):
    voucher_no: str
    batch_no: str
    region: str
    total_amount: Decimal
    reimbursed_amount: Decimal
    account_pay_amount: Decimal
    self_pay_amount: Decimal
    deductible: Decimal
    reimbursement_ratio: Decimal
    status: str
    created_at: datetime
    details: list[PresettlementDetail]


class SettlementConfirmRequest(BaseModel):
    # 正式结算只认凭证号，HIS 无法再改金额
    voucher_no: str


class SettlementResponse(BaseModel):
    settlement_no: str
    voucher_no: str
    batch_no: str
    visit_no: str
    insured_id: str
    total_amount: Decimal
    reimbursed_amount: Decimal
    account_pay_amount: Decimal
    self_pay_amount: Decimal
    status: str
    created_at: datetime
    reversed_at: datetime | None = None

    class Config:
        from_attributes = True
