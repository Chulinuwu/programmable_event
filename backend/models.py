from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PositiveInt, model_validator


class ChecklistActor(str, Enum):
    sender = "sender"
    receiver = "receiver"
    admin = "admin"


class ChecklistTemplateItem(BaseModel):
    description: str
    required_by: ChecklistActor


class RuleConfig(BaseModel):
    allowed_categories: List[str] = Field(default_factory=list)
    blocked_categories: List[str] = Field(default_factory=list)
    max_amount: Optional[int] = None
    daily_limit: Optional[int] = None
    require_checklist: bool = False
    checklist_template: List[ChecklistTemplateItem] = Field(default_factory=list)
    require_external_verification: bool = False

class ProgramBase(BaseModel):
    name: str
    rules: RuleConfig
    description: Optional[str] = None
    created_by: str = "admin"
    allowed_users: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ensure_creator_access(self) -> "ProgramBase":
        if self.created_by and self.created_by not in self.allowed_users:
            self.allowed_users.append(self.created_by)
        # Deduplicate while preserving order
        seen = set()
        unique_users: List[str] = []
        for user_id in self.allowed_users:
            if user_id in seen:
                continue
            seen.add(user_id)
            unique_users.append(user_id)
        self.allowed_users = unique_users
        return self


class ProgramCreate(ProgramBase):
    pass


class Program(ProgramBase):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TransactionStatus(str, Enum):
    pending = "PENDING"
    held = "HELD"
    completed = "COMPLETED"
    rejected = "REJECTED"
    cancelled = "CANCELLED"


class TransactionBase(BaseModel):
    program_id: UUID
    from_user: str
    to_user: str
    amount: PositiveInt
    merchant_id: Optional[str] = None
    merchant_category: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def _validate_category(cls, values: "TransactionBase") -> "TransactionBase":
        if values.merchant_id and not values.merchant_category:
            raise ValueError("merchant_category is required when merchant_id is provided")
        return values


class TransactionCreate(TransactionBase):
    timestamp: Optional[datetime] = None


class Transaction(TransactionBase):
    id: UUID = Field(default_factory=uuid4)
    status: TransactionStatus = TransactionStatus.pending
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    transaction_ts: datetime = Field(default_factory=datetime.utcnow)
    checklist_item_ids: List[UUID] = Field(default_factory=list)
    settled: bool = False
    funds_reserved: bool = False


class ChecklistItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    transaction_id: UUID
    description: str
    required_by: ChecklistActor
    is_completed: bool = False
    completed_by: Optional[str] = None
    completed_at: Optional[datetime] = None


class ChecklistItemResponse(ChecklistItem):
    pass


class TransactionSummary(Transaction):
    pass


class TransactionDetail(Transaction):
    checklist: List[ChecklistItemResponse] = Field(default_factory=list)


class ChecklistCompletionRequest(BaseModel):
    actor: ChecklistActor
    user_id: str


class Merchant(BaseModel):
    id: str
    category: str
    name: str


class User(BaseModel):
    id: str
    display_name: str
    balance: int = 0


class UserCreate(User):
    pass
