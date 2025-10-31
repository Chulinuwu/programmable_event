from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    ChecklistActor,
    ChecklistCompletionRequest,
    ChecklistItem,
    ChecklistItemResponse,
    ChecklistTemplateItem,
    Merchant,
    Program,
    ProgramCreate,
    RuleConfig,
    Transaction,
    TransactionCreate,
    TransactionDetail,
    TransactionStatus,
    User,
    UserCreate,
)
from .rules import engine
from .storage import store


app = FastAPI(
    title="Programmable Payment PoC",
    description="Backend API for programmable payment proof of concept.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def seed_data() -> None:
    """Populate the in-memory store with sample data for demos."""
    # Seed users
    default_users = [
        User(id="user_a", display_name="User A", balance=20000),
        User(id="user_b", display_name="User B", balance=5000),
        User(id="user_c", display_name="User C", balance=8000),
        User(id="gov_wallet", display_name="Gov Stimulus Wallet", balance=1_000_000),
        User(id="admin", display_name="Admin", balance=0),
    ]
    for default_user in default_users:
        if not store.get_user(default_user.id):
            store.upsert_user(default_user)

    # Seed merchants
    merchants = [
        Merchant(id="m001", category="food", name="ร้านส้มตำป้าแดง"),
        Merchant(id="m002", category="entertainment", name="ผับริมทาง"),
        Merchant(id="m003", category="medical", name="โรงพยาบาลกรุงเทพ"),
        Merchant(id="m004", category="retail", name="7-Eleven"),
    ]
    for merchant in merchants:
        store.upsert_merchant(merchant)

    # Seed demo programs if none exist
    if not store.list_programs():
        escrow_program = ProgramCreate(
            name="Freelance Escrow",
            description="Escrow program for freelance milestone payments",
            rules=RuleConfig(
                max_amount=10000,
                allowed_categories=["services"],
                require_checklist=True,
                checklist_template=[
                    ChecklistTemplateItem(description="ส่ง mockup", required_by=ChecklistActor.receiver),
                    ChecklistTemplateItem(description="ส่งงานเสร็จ", required_by=ChecklistActor.receiver),
                    ChecklistTemplateItem(description="ผู้ว่าจ้างยืนยันงาน", required_by=ChecklistActor.sender),
                ],
            ),
            created_by="user_a",
            allowed_users=["user_a", "user_b"],
        )
        stimulus_program = ProgramCreate(
            name="Government Stimulus",
            description="จำกัดการใช้จ่ายกับหมวด merchant ที่กำหนด",
            rules=RuleConfig(
                max_amount=500,
                daily_limit=3000,
                allowed_categories=["food", "medical", "retail"],
                blocked_categories=["entertainment", "gambling"],
            ),
            created_by="gov_wallet",
            allowed_users=["gov_wallet", "user_a", "user_b", "user_c"],
        )

        store.create_program(escrow_program)
        store.create_program(stimulus_program)


@app.on_event("startup")
def on_startup() -> None:
    seed_data()


# Utility functions ---------------------------------------------------------

def _get_program(program_id: UUID) -> Program:
    program = store.get_program(program_id)
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return program


def _ensure_from_user(user_id: str) -> User:
    user = store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found")
    return user


def _ensure_to_user(user_id: str) -> User:
    user = store.get_user(user_id)
    if not user:
        user = User(id=user_id, display_name=user_id.capitalize(), balance=0)
        store.upsert_user(user)
    return user


def _format_user_label(user_id: str) -> str:
    user = store.get_user(user_id)
    if user:
        return f"{user.display_name} ({user.id})"
    return user_id


def _reserve_funds(transaction: Transaction) -> None:
    if transaction.funds_reserved:
        return
    from_user = _ensure_from_user(transaction.from_user)
    if from_user.balance < transaction.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")
    from_user.balance -= transaction.amount
    store.upsert_user(from_user)
    transaction.funds_reserved = True


def _release_funds(transaction: Transaction) -> None:
    if not transaction.funds_reserved or transaction.settled:
        return
    from_user = _ensure_from_user(transaction.from_user)
    from_user.balance += transaction.amount
    store.upsert_user(from_user)
    transaction.funds_reserved = False


def _settle_funds(transaction: Transaction) -> None:
    if transaction.settled:
        return
    recipient = _ensure_to_user(transaction.to_user)
    recipient.balance += transaction.amount
    store.upsert_user(recipient)
    transaction.settled = True


def _apply_status_transition(transaction: Transaction, new_status: TransactionStatus) -> Transaction:
    previous_status = transaction.status
    transaction.status = new_status

    if new_status == TransactionStatus.rejected:
        _release_funds(transaction)
    elif new_status == TransactionStatus.cancelled:
        _release_funds(transaction)
    elif new_status == TransactionStatus.held:
        _reserve_funds(transaction)
    elif new_status == TransactionStatus.completed:
        _reserve_funds(transaction)
        _settle_funds(transaction)

    transaction.updated_at = datetime.utcnow()
    return transaction


def _evaluate_transaction(transaction: Transaction) -> Transaction:
    program = _get_program(transaction.program_id)
    new_status = engine.verify(transaction, program)
    transaction = _apply_status_transition(transaction, new_status)
    return store.save_transaction(transaction)


def _build_transaction_detail(transaction: Transaction) -> TransactionDetail:
    checklist = [
        ChecklistItemResponse(**item.model_dump())
        for item in store.get_checklist_items_for_transaction(transaction.id)
    ]
    detail = TransactionDetail(**transaction.model_dump(), checklist=checklist)
    return detail


def _generate_checklist(transaction: Transaction, program: Program) -> None:
    if not program.rules.require_checklist:
        return
    if not program.rules.checklist_template:
        return

    items = []
    for template in program.rules.checklist_template:
        item = ChecklistItem(
            transaction_id=transaction.id,
            description=template.description,
            required_by=template.required_by,
        )
        transaction.checklist_item_ids.append(item.id)
        items.append(item)
    store.add_checklist_items(items)
    store.save_transaction(transaction)


# ---------------------------- Users ---------------------------------------


@app.get("/api/users", response_model=List[User])
def list_users() -> List[User]:
    return store.list_users()


@app.get("/api/users/{user_id}", response_model=User)
def get_user(user_id: str) -> User:
    user = store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.post("/api/users", response_model=User, status_code=status.HTTP_201_CREATED)
def create_or_update_user(payload: UserCreate) -> User:
    user = User(**payload.model_dump())
    store.upsert_user(user)
    return user


# --------------------------- Merchants ------------------------------------


@app.get("/api/merchants", response_model=List[Merchant])
def list_merchants() -> List[Merchant]:
    return store.list_merchants()


@app.get("/api/merchants/{merchant_id}", response_model=Merchant)
def get_merchant(merchant_id: str) -> Merchant:
    merchant = store.get_merchant(merchant_id)
    if not merchant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    return merchant


# --------------------------- Programs -------------------------------------


@app.post("/api/programs", response_model=Program, status_code=status.HTTP_201_CREATED)
def create_program(payload: ProgramCreate) -> Program:
    _ensure_to_user(payload.created_by)
    for user_id in payload.allowed_users:
        _ensure_to_user(user_id)
    program = store.create_program(payload)
    return program


@app.get("/api/programs", response_model=List[Program])
def list_programs() -> List[Program]:
    return store.list_programs()


@app.get("/api/programs/{program_id}", response_model=Program)
def get_program(program_id: UUID) -> Program:
    return _get_program(program_id)


@app.patch("/api/programs/{program_id}", response_model=Program)
def update_program(program_id: UUID, payload: ProgramCreate) -> Program:
    _ensure_to_user(payload.created_by)
    for user_id in payload.allowed_users:
        _ensure_to_user(user_id)
    updated = store.update_program(program_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return updated


@app.delete("/api/programs/{program_id}", response_model=dict)
def delete_program(program_id: UUID, actor_id: str = Query(..., description="User ID of the actor requesting deletion")) -> dict:
    if actor_id != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can delete programs")
    deleted = store.delete_program(program_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return {"deleted": True}


# -------------------------- Transactions ----------------------------------


@app.post("/api/transactions", response_model=TransactionDetail, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate) -> TransactionDetail:
    program = _get_program(payload.program_id)
    if program.allowed_users:
        allowed_set = set(program.allowed_users)
        missing_roles = []
        if payload.from_user not in allowed_set:
            missing_roles.append(f"from_user '{_format_user_label(payload.from_user)}'")
        if payload.to_user not in allowed_set:
            missing_roles.append(f"to_user '{_format_user_label(payload.to_user)}'")
        if missing_roles:
            allowed_display = ", ".join(_format_user_label(uid) for uid in program.allowed_users)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "ผู้ใช้ไม่ได้รับสิทธิ์ในการใช้โปรแกรมนี้: "
                    + ", ".join(missing_roles)
                    + f" • Allowed users: {allowed_display}"
                ),
            )
    _ensure_from_user(payload.from_user)
    _ensure_to_user(payload.to_user)

    data = payload.model_dump()
    if not data.get("timestamp"):
        data["timestamp"] = datetime.utcnow()

    merchant_id = data.get("merchant_id")
    if merchant_id:
        merchant = store.get_merchant(merchant_id)
        if not merchant:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown merchant")
        data["merchant_category"] = merchant.category

    txn_create = TransactionCreate(**data)
    transaction = store.create_transaction(txn_create)

    _generate_checklist(transaction, program)
    transaction = _evaluate_transaction(transaction)

    return _build_transaction_detail(transaction)


@app.get("/api/transactions", response_model=List[TransactionDetail])
def list_transactions() -> List[TransactionDetail]:
    return [_build_transaction_detail(txn) for txn in store.list_transactions()]


@app.get("/api/transactions/{transaction_id}", response_model=TransactionDetail)
def get_transaction(transaction_id: UUID) -> TransactionDetail:
    transaction = store.get_transaction(transaction_id)
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return _build_transaction_detail(transaction)


@app.post("/api/transactions/{transaction_id}/cancel", response_model=TransactionDetail)
def cancel_transaction(transaction_id: UUID) -> TransactionDetail:
    transaction = store.get_transaction(transaction_id)
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    if transaction.status in {TransactionStatus.completed, TransactionStatus.cancelled, TransactionStatus.rejected}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction already finalized")
    transaction = _apply_status_transition(transaction, TransactionStatus.cancelled)
    store.save_transaction(transaction)
    return _build_transaction_detail(transaction)


@app.get("/api/transactions/{transaction_id}/checklist", response_model=List[ChecklistItemResponse])
def get_checklist(transaction_id: UUID) -> List[ChecklistItemResponse]:
    transaction = store.get_transaction(transaction_id)
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return [
        ChecklistItemResponse(**item.model_dump())
        for item in store.get_checklist_items_for_transaction(transaction_id)
    ]


# ---------------------------- Checklist -----------------------------------


@app.post("/api/checklist/{item_id}/complete", response_model=TransactionDetail)
def complete_checklist_item(item_id: UUID, payload: ChecklistCompletionRequest) -> TransactionDetail:
    item = store.get_checklist_item(item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    if item.is_completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Checklist item already completed")
    if payload.actor != item.required_by and payload.actor != ChecklistActor.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Actor not allowed to complete this item")

    item.is_completed = True
    item.completed_at = datetime.utcnow()
    item.completed_by = payload.user_id
    store.save_checklist_item(item)

    transaction = store.get_transaction(item.transaction_id)
    if not transaction:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transaction not found")
    transaction = _evaluate_transaction(transaction)
    return _build_transaction_detail(transaction)


@app.post("/api/checklist/{item_id}/uncomplete", response_model=TransactionDetail)
def uncomplete_checklist_item(item_id: UUID, payload: ChecklistCompletionRequest) -> TransactionDetail:
    item = store.get_checklist_item(item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    if not item.is_completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Checklist item is not completed")

    transaction = store.get_transaction(item.transaction_id)
    if not transaction:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transaction not found")
    if transaction.settled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot uncomplete checklist for settled transaction",
        )

    item.is_completed = False
    item.completed_at = None
    item.completed_by = None
    store.save_checklist_item(item)

    transaction = _apply_status_transition(transaction, TransactionStatus.held)
    store.save_transaction(transaction)
    return _build_transaction_detail(transaction)


# Health check --------------------------------------------------------------


@app.get("/health", response_model=dict)
def health() -> dict:
    return {"status": "ok"}
