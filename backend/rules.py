from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from .models import Program, RuleConfig, Transaction, TransactionStatus
from .storage import store


class RuleEngine:
    """Core rule evaluation logic for programmable payments."""

    def verify(self, transaction: Transaction, program: Program) -> TransactionStatus:
        rules = program.rules

        if not self._check_basic_rules(transaction, rules):
            return TransactionStatus.rejected

        if rules.require_checklist and not self._check_checklist(transaction.id):
            return TransactionStatus.held

        if rules.require_external_verification and not self._check_external(transaction):
            return TransactionStatus.held

        return TransactionStatus.completed

    def _check_basic_rules(self, txn: Transaction, rules: RuleConfig) -> bool:
        if rules.max_amount is not None and txn.amount > rules.max_amount:
            return False

        if txn.merchant_category:
            if rules.allowed_categories and txn.merchant_category not in rules.allowed_categories:
                return False
            if txn.merchant_category in rules.blocked_categories:
                return False

        if rules.daily_limit is not None:
            daily_total = self._get_daily_total(txn.from_user, txn.created_at, exclude_txn_id=txn.id)
            if daily_total + txn.amount > rules.daily_limit:
                return False

        return True

    def _get_daily_total(self, user_id: str, timestamp: datetime, exclude_txn_id: Optional[UUID] = None) -> int:
        total = 0
        for txn in store.list_transactions():
            if txn.from_user != user_id:
                continue

            if exclude_txn_id and txn.id == exclude_txn_id:
                continue

            if txn.status in {TransactionStatus.rejected, TransactionStatus.cancelled}:
                continue

            if txn.created_at.date() == timestamp.date():
                total += txn.amount
        return total

    def _check_checklist(self, transaction_id: UUID) -> bool:
        items = store.get_checklist_items_for_transaction(transaction_id)
        if not items:
            return True
        return all(item.is_completed for item in items)

    def _check_external(self, txn: Transaction) -> bool:
        # Placeholder for future integrations (logistics API, oracle, etc.)
        return True


engine = RuleEngine()
