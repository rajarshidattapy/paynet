# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ports the TransactionViewModel/MainViewModel semantics (the Kotlin had no
# ViewModel unit tests; these pin the ported behavior, including the
# re-query-after-write deviation that replaces Room's observable queries).

from paynet.db.models import PaymentDetails, PaymentStatus, Transaction
from paynet.viewmodels import (
    ERROR_DELETE_TRANSACTION,
    ERROR_LOAD_TRANSACTIONS,
    MainUiEvent,
    MainViewModel,
    TransactionViewModel,
)


def sample_transaction(txn_id="t1", amount="100"):
    return Transaction(
        transactionId=txn_id,
        amount=amount,
        status="SUCCESS",
        bankName="HDFC Bank",
        smsExcerpt="₹100 debited",
        timestamp=1,
    )


def sample_payment_details(details_id="t1"):
    return PaymentDetails(
        id=details_id,
        phoneNumber="9876543210",
        recipientName="Kirana Store",
        amount=100.0,
        timestamp=1,
        status=PaymentStatus.COMPLETED,
    )


class FakeRepository:
    def __init__(self):
        self.transactions = [sample_transaction("t1"), sample_transaction("t2", "50")]
        self.recent = [sample_payment_details("t1")]
        self.fail = False

    def _maybe_fail(self):
        if self.fail:
            raise RuntimeError("db unavailable")

    def get_all_transactions(self):
        self._maybe_fail()
        return list(self.transactions)

    def get_recent_payment_details(self, limit=10):
        self._maybe_fail()
        return list(self.recent)

    def get_transaction_by_id(self, transaction_id):
        self._maybe_fail()
        return next((t for t in self.transactions if t.transactionId == transaction_id), None)

    def search_transactions(self, query):
        self._maybe_fail()
        return [t for t in self.transactions if query.lower() in t.bankName.lower()]

    def get_transactions_by_status(self, status):
        self._maybe_fail()
        return [t for t in self.transactions if t.status == status]

    def get_transactions_by_bank(self, bank_name):
        self._maybe_fail()
        return [t for t in self.transactions if t.bankName == bank_name]

    def delete_transaction(self, transaction):
        self._maybe_fail()
        self.transactions = [t for t in self.transactions if t.transactionId != transaction.transactionId]

    def delete_transaction_by_id(self, transaction_id):
        self._maybe_fail()
        self.transactions = [t for t in self.transactions if t.transactionId != transaction_id]

    def delete_all_transactions(self):
        self._maybe_fail()
        self.transactions = []
        self.recent = []


def test_main_view_model_emits_to_subscribers():
    vm = MainViewModel()
    events = []
    unsubscribe = vm.subscribe(events.append)

    vm.on_qr_scanner_closed()
    vm.on_overlay_permission_needed()

    assert events == [MainUiEvent.QR_SCANNER_CLOSED, MainUiEvent.OVERLAY_PERMISSION_NEEDED]

    unsubscribe()
    vm.on_qr_scanner_closed()
    assert len(events) == 2


def test_load_recent_transactions_publishes_results_once():
    vm = TransactionViewModel(FakeRepository())
    states = []
    vm.is_loading.subscribe(states.append)

    vm.load_recent_transactions()

    assert [t.id for t in vm.recent_transactions.value] == ["t1"]
    assert vm.is_loading.value is False
    assert states == [True, False]

    # The active-observer guard: a second call doesn't reload or republish.
    vm.load_recent_transactions()
    assert states == [True, False]


def test_load_recent_transactions_error_sets_banner_and_stops_loading():
    repo = FakeRepository()
    repo.fail = True
    vm = TransactionViewModel(repo)

    vm.load_recent_transactions()

    assert vm.error.value == ERROR_LOAD_TRANSACTIONS
    assert vm.is_loading.value is False
    # Error text comes from resources, never from the exception message.
    assert "db unavailable" not in vm.error.value


def test_load_history_states_and_guard():
    vm = TransactionViewModel(FakeRepository())

    vm.load_history()

    state = vm.history_state.value
    assert state.is_loading is False
    assert state.error is None
    assert [t.transactionId for t in state.transactions] == ["t1", "t2"]


def test_select_and_clear_transaction():
    vm = TransactionViewModel(FakeRepository())

    vm.select_transaction("t2")
    assert vm.selected_transaction.value.transactionId == "t2"

    vm.clear_selected_transaction()
    assert vm.selected_transaction.value is None


def test_delete_requeries_the_published_lists():
    repo = FakeRepository()
    vm = TransactionViewModel(repo)
    vm.load_recent_transactions()
    vm.load_history()

    vm.delete_transaction_by_id("t1")

    assert [t.transactionId for t in vm.history_state.value.transactions] == ["t2"]
    assert vm.error.value is None


def test_clear_all_empties_recent_immediately():
    repo = FakeRepository()
    vm = TransactionViewModel(repo)
    vm.load_recent_transactions()

    vm.clear_all_transactions()

    assert vm.recent_transactions.value == []
    assert repo.transactions == []


def test_delete_failure_sets_error_and_keeps_rows():
    repo = FakeRepository()
    vm = TransactionViewModel(repo)
    repo.fail = True

    vm.delete_transaction_by_id("t1")

    assert vm.error.value == ERROR_DELETE_TRANSACTION
    assert len(repo.transactions) == 2


def test_refresh_reloads_after_clearing_error():
    repo = FakeRepository()
    vm = TransactionViewModel(repo)
    repo.fail = True
    vm.load_recent_transactions()
    assert vm.error.value == ERROR_LOAD_TRANSACTIONS

    repo.fail = False
    repo.recent = [sample_payment_details("t2")]
    vm.refresh()

    assert vm.error.value is None
    assert [t.id for t in vm.recent_transactions.value] == ["t2"]
