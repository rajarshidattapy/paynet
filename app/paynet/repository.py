# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/repository/TransactionRepository.kt

"""Repository for managing transaction data — the clean interface between
UI/payment layers and the store. Implements the PaymentTransactionStore
seam that PaymentSessionManager writes through (feature 5)."""

from typing import List, Optional

from paynet.db.database import Database
from paynet.db.models import PaymentDetails, Transaction


class TransactionRepository:
    def __init__(self, db: Database):
        self._db = db

    # -- queries ----------------------------------------------------------

    def get_all_transactions(self) -> List[Transaction]:
        return self._db.get_all_transactions()

    def get_recent_transactions(self, limit: int = 10) -> List[Transaction]:
        return self._db.get_recent_transactions(limit)

    def get_recent_payment_details(self, limit: int = 10) -> List[PaymentDetails]:
        return [
            transaction.to_payment_details()
            for transaction in self._db.get_recent_confirmed_transactions(limit)
        ]

    def get_transactions_by_status(self, status: str) -> List[Transaction]:
        return self._db.get_transactions_by_status(status)

    def get_transactions_by_bank(self, bank_name: str) -> List[Transaction]:
        return self._db.get_transactions_by_bank(bank_name)

    def search_transactions(self, query: str) -> List[Transaction]:
        return self._db.search_transactions(f"%{query}%")

    def get_transaction_by_id(self, transaction_id: str) -> Optional[Transaction]:
        return self._db.get_transaction_by_id(transaction_id)

    # -- writes -------------------------------------------------------------

    def save_transaction(self, simple_transaction):
        self._db.insert_transaction(Transaction.from_simple_transaction(simple_transaction))

    def save_transactions(self, transactions: List[Transaction]):
        self._db.insert_transactions(transactions)

    def update_transaction(self, transaction: Transaction):
        self._db.update_transaction(transaction)

    def delete_transaction(self, transaction: Transaction):
        self._db.delete_transaction(transaction)

    def delete_transaction_by_id(self, transaction_id: str):
        self._db.delete_transaction_by_id(transaction_id)

    def delete_all_transactions(self):
        self._db.delete_all_transactions()

    def get_transaction_count(self) -> int:
        return self._db.get_transaction_count()

    def get_total_amount(self) -> Optional[float]:
        return self._db.get_total_amount()

    def get_transactions_by_date_range(
        self, start_time: int, end_time: int
    ) -> List[Transaction]:
        return self._db.get_transactions_by_date_range(start_time, end_time)

    # -- PaymentTransactionStore (used by the payment session) -------------

    def insert_pending(self, transaction: Transaction):
        self._db.insert_transaction(transaction)

    def transition_status(
        self, transaction_id: str, expected_status: str, new_status: str
    ) -> int:
        return self._db.transition_status(transaction_id, expected_status, new_status)

    def confirm_transaction(
        self, transaction_id: str, status: str, parsed, verified_at: int
    ) -> int:
        return self._db.confirm_transaction(
            transaction_id=transaction_id,
            status=status,
            bank_ref=parsed.transaction_id,
            bank_name=parsed.bank_name,
            sms_excerpt=parsed.sms_excerpt,
            upi_id=parsed.upi_id,
            recipient_name=parsed.recipient_name,
            amount=parsed.amount,
            verified_at=verified_at,
        )

    def delete_stale_pending(self, now: int) -> int:
        return self._db.delete_stale_pending(now)

    def delete_pending(self, transaction_id: str) -> int:
        return self._db.delete_pending(transaction_id)
