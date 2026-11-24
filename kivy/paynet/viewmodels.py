# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/viewmodel/MainViewModel.kt
# and app/src/main/java/com/paynet/app/viewmodel/TransactionViewModel.kt

"""View state holders for the home/history UI.

DEVIATION (recorded in MIGRATION.md): Room's observable queries (a Flow
that re-emits after every write) become explicit re-queries — after each
mutation the ViewModel reloads from the synchronous repository and republishes
its state. Coroutine dispatch disappears; repository calls are synchronous
sqlite3 (fast enough off the UI thread's critical path, and Kivy screens
schedule them via Clock where needed). StateFlow becomes value + listener
lists, as in feature 5.

Error strings are the strings.xml values, never an exception message.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .db.models import PaymentDetails, Transaction
from .repository import TransactionRepository

log = logging.getLogger("TransactionViewModel")

# strings.xml values.
ERROR_LOAD_TRANSACTIONS = "Could not load your transactions."
ERROR_OPEN_TRANSACTION = "Could not open that transaction."
ERROR_DELETE_TRANSACTION = "Could not delete that transaction."
ERROR_CLEAR_TRANSACTIONS = "Could not clear your transaction history."


class MainUiEvent(enum.Enum):
    """One-shot events from the app layer up to the home screen."""

    # The QR scanner activity returned; clear the "Opening…" button state.
    QR_SCANNER_CLOSED = "qr_scanner_closed"
    # A payment needs overlay permission; show the explanation dialog.
    OVERLAY_PERMISSION_NEEDED = "overlay_permission_needed"


class MainViewModel:
    """The SharedFlow becomes a plain listener list (its extraBufferCapacity
    existed only to survive configuration changes, which Kivy doesn't have)."""

    def __init__(self) -> None:
        self._listeners: List[Callable[[MainUiEvent], None]] = []

    def subscribe(self, listener: Callable[[MainUiEvent], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _emit(self, event: MainUiEvent) -> None:
        for listener in list(self._listeners):
            listener(event)

    def on_qr_scanner_closed(self) -> None:
        self._emit(MainUiEvent.QR_SCANNER_CLOSED)

    def on_overlay_permission_needed(self) -> None:
        self._emit(MainUiEvent.OVERLAY_PERMISSION_NEEDED)


@dataclass
class TransactionHistoryState:
    transactions: List[Transaction] = field(default_factory=list)
    is_loading: bool = True
    error: Optional[str] = None


class _Observable:
    """A mutable value with subscribers (StateFlow replacement)."""

    def __init__(self, value):
        self._value = value
        self._listeners: List[Callable] = []

    @property
    def value(self):
        return self._value

    def set(self, value) -> None:
        self._value = value
        for listener in list(self._listeners):
            listener(value)

    def subscribe(self, listener: Callable) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe


class TransactionViewModel:
    """ViewModel for transaction data and UI state."""

    def __init__(self, repository: TransactionRepository) -> None:
        self._repository = repository

        self.recent_transactions: _Observable = _Observable([])
        self.is_loading: _Observable = _Observable(False)
        self.error: _Observable = _Observable(None)
        # The transaction whose detail dialog is open, if any.
        self.selected_transaction: _Observable = _Observable(None)
        self.history_state: _Observable = _Observable(TransactionHistoryState())

        self._history_loaded = False
        self._recent_loaded = False

    def load_history(self) -> None:
        """Kotlin keeps one Room observer while the ViewModel lives; the
        guard against double-loading ports as _history_loaded."""
        if self._history_loaded:
            return
        self._history_loaded = True
        state = self.history_state.value
        self.history_state.set(
            TransactionHistoryState(
                transactions=state.transactions,
                is_loading=len(state.transactions) == 0,
                error=None,
            )
        )
        try:
            transactions = self._repository.get_all_transactions()
            self.history_state.set(
                TransactionHistoryState(transactions=transactions, is_loading=False)
            )
        except Exception:
            log.exception("Failed to load history")
            current = self.history_state.value
            self.history_state.set(
                TransactionHistoryState(
                    transactions=current.transactions,
                    is_loading=False,
                    error=ERROR_LOAD_TRANSACTIONS,
                )
            )

    def load_recent_transactions(self) -> None:
        """Load recent transactions (last 10)."""
        if self._recent_loaded:
            return
        self._recent_loaded = True
        self.is_loading.set(len(self.recent_transactions.value) == 0)
        self.error.set(None)
        try:
            transactions = self._repository.get_recent_payment_details(10)
            self.recent_transactions.set(transactions)
            self.is_loading.set(False)
        except Exception:
            log.exception("Failed to load transactions")
            self.error.set(ERROR_LOAD_TRANSACTIONS)
            self.is_loading.set(False)

    def select_transaction(self, transaction_id: str) -> None:
        """Open the detail dialog for a recent-payments row. The list
        carries only the summary PaymentDetails, so the full row is fetched
        by id."""
        try:
            self.selected_transaction.set(
                self._repository.get_transaction_by_id(transaction_id)
            )
        except Exception:
            log.exception("Failed to open transaction")
            self.error.set(ERROR_OPEN_TRANSACTION)

    def clear_selected_transaction(self) -> None:
        """Close the detail dialog."""
        self.selected_transaction.set(None)

    def load_all_transactions(self) -> List[Transaction]:
        return self._repository.get_all_transactions()

    def search_transactions(self, query: str) -> List[Transaction]:
        return self._repository.search_transactions(query)

    def get_transactions_by_status(self, status: str) -> List[Transaction]:
        return self._repository.get_transactions_by_status(status)

    def get_transactions_by_bank(self, bank_name: str) -> List[Transaction]:
        return self._repository.get_transactions_by_bank(bank_name)

    def delete_transaction(self, transaction: Transaction) -> None:
        try:
            self._repository.delete_transaction(transaction)
            self._reload_after_write()
        except Exception:
            log.exception("Failed to delete transaction")
            self.error.set(ERROR_DELETE_TRANSACTION)

    def delete_transaction_by_id(self, transaction_id: str) -> None:
        try:
            self._repository.delete_transaction_by_id(transaction_id)
            self._reload_after_write()
        except Exception:
            log.exception("Failed to delete transaction")
            self.error.set(ERROR_DELETE_TRANSACTION)

    def clear_all_transactions(self) -> None:
        try:
            self._repository.delete_all_transactions()
            self.recent_transactions.set([])
            self._reload_after_write()
        except Exception:
            log.exception("Failed to clear transactions")
            self.error.set(ERROR_CLEAR_TRANSACTIONS)

    def retry_history(self) -> None:
        """The error state's Retry action: the Kotlin screen calls
        loadHistory() again; the port must drop the load-once guard first."""
        self._history_loaded = False
        self.load_history()

    def clear_error(self) -> None:
        self.error.set(None)

    def refresh(self) -> None:
        self.error.set(None)
        self._recent_loaded = False
        self.load_recent_transactions()

    def _reload_after_write(self) -> None:
        """Room observers received writes automatically; this port
        re-queries instead."""
        if self._recent_loaded:
            try:
                self.recent_transactions.set(self._repository.get_recent_payment_details(10))
            except Exception:
                log.exception("Failed to reload recent transactions")
        if self._history_loaded:
            try:
                self.history_state.set(
                    TransactionHistoryState(
                        transactions=self._repository.get_all_transactions(),
                        is_loading=False,
                    )
                )
            except Exception:
                log.exception("Failed to reload history")
