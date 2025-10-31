from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from uuid import UUID

from .models import (
    ChecklistItem,
    Merchant,
    Program,
    ProgramCreate,
    Transaction,
    TransactionCreate,
    User,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "store.json"


class MemoryStore:
    """File-backed store that keeps PoC data in a local JSON file."""

    def __init__(self) -> None:
        self.programs: Dict[UUID, Program] = {}
        self.transactions: Dict[UUID, Transaction] = {}
        self.checklists: Dict[UUID, ChecklistItem] = {}
        self.users: Dict[str, User] = {}
        self.merchants: Dict[str, Merchant] = {}
        self._load()

    # ------------------------------------------------------------------ utils
    def _load(self) -> None:
        if not DATA_FILE.exists():
            return
        try:
            with DATA_FILE.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except json.JSONDecodeError:
            return

        for raw_program in payload.get("programs", []):
            program = Program.model_validate(raw_program)
            self.programs[program.id] = program

        for raw_txn in payload.get("transactions", []):
            txn = Transaction.model_validate(raw_txn)
            self.transactions[txn.id] = txn

        for raw_item in payload.get("checklists", []):
            item = ChecklistItem.model_validate(raw_item)
            self.checklists[item.id] = item

        for raw_user in payload.get("users", []):
            user = User.model_validate(raw_user)
            self.users[user.id] = user

        for raw_merchant in payload.get("merchants", []):
            merchant = Merchant.model_validate(raw_merchant)
            self.merchants[merchant.id] = merchant

    def _persist(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "programs": [program.model_dump(mode="json") for program in self.programs.values()],
            "transactions": [txn.model_dump(mode="json") for txn in self.transactions.values()],
            "checklists": [item.model_dump(mode="json") for item in self.checklists.values()],
            "users": [user.model_dump(mode="json") for user in self.users.values()],
            "merchants": [merchant.model_dump(mode="json") for merchant in self.merchants.values()],
        }
        with DATA_FILE.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------- programs
    def create_program(self, payload: ProgramCreate) -> Program:
        program = Program(**payload.model_dump())
        self.programs[program.id] = program
        self._persist()
        return program

    def list_programs(self) -> List[Program]:
        return list(self.programs.values())

    def get_program(self, program_id: UUID) -> Optional[Program]:
        return self.programs.get(program_id)

    def update_program(self, program_id: UUID, payload: ProgramCreate) -> Optional[Program]:
        program = self.programs.get(program_id)
        if not program:
            return None
        updated = program.model_copy(update=payload.model_dump())
        self.programs[program_id] = updated
        self._persist()
        return updated

    def delete_program(self, program_id: UUID) -> bool:
        deleted = self.programs.pop(program_id, None) is not None
        if deleted:
            self._persist()
        return deleted

    # ----------------------------------------------------------- transactions
    def create_transaction(self, payload: TransactionCreate) -> Transaction:
        data = payload.model_dump(exclude_none=True)
        timestamp = data.pop("timestamp", None)
        if timestamp:
            data["transaction_ts"] = timestamp
            data.setdefault("created_at", timestamp)
            data.setdefault("updated_at", timestamp)
        transaction = Transaction(**data)
        self.transactions[transaction.id] = transaction
        self._persist()
        return transaction

    def list_transactions(self) -> List[Transaction]:
        return list(self.transactions.values())

    def get_transaction(self, transaction_id: UUID) -> Optional[Transaction]:
        return self.transactions.get(transaction_id)

    def save_transaction(self, transaction: Transaction) -> Transaction:
        transaction.updated_at = datetime.utcnow()
        self.transactions[transaction.id] = transaction
        self._persist()
        return transaction

    # -------------------------------------------------------------- checklist
    def add_checklist_items(self, items: Iterable[ChecklistItem]) -> None:
        for item in items:
            self.checklists[item.id] = item
        self._persist()

    def get_checklist_items_for_transaction(self, transaction_id: UUID) -> List[ChecklistItem]:
        return [item for item in self.checklists.values() if item.transaction_id == transaction_id]

    def get_checklist_item(self, item_id: UUID) -> Optional[ChecklistItem]:
        return self.checklists.get(item_id)

    def save_checklist_item(self, item: ChecklistItem) -> ChecklistItem:
        self.checklists[item.id] = item
        self._persist()
        return item

    # ------------------------------------------------------------------ users
    def upsert_user(self, user: User) -> User:
        self.users[user.id] = user
        self._persist()
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def list_users(self) -> List[User]:
        return list(self.users.values())

    # --------------------------------------------------------------- merchants
    def upsert_merchant(self, merchant: Merchant) -> Merchant:
        self.merchants[merchant.id] = merchant
        self._persist()
        return merchant

    def get_merchant(self, merchant_id: str) -> Optional[Merchant]:
        return self.merchants.get(merchant_id)

    def list_merchants(self) -> List[Merchant]:
        return list(self.merchants.values())


store = MemoryStore()

