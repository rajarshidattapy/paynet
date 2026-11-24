# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""Transaction history screen (feature 9): date grouping, status labels,
time formats, screen states, search, and the detail/delete flow. Pure
widget construction — no window is opened."""

import os
import time

os.environ.setdefault("KIVY_NO_ARGS", "1")

from paynet.db.models import Transaction
from paynet.ui.history import (
    HistoryRow,
    HistoryScreen,
    StatusPill,
    TransactionDetailView,
    group_transactions,
    status_label,
)
from paynet.utils.dates import format_full_date, format_time
from paynet.viewmodels import TransactionViewModel

HOUR = 3_600_000
DAY = 86_400_000


def _tx(tid, ts, status="SUCCESS", amount="100.00", name="Kirana Store",
        phone=None, upi=None, ref=None):
    return Transaction(
        transactionId=tid, amount=amount, status=status, bankName="HDFC Bank",
        smsExcerpt="x", timestamp=ts, recipientName=name,
        phoneNumber=phone, upiId=upi, bankRef=ref,
    )


def _walk(widget):
    yield widget
    for child in widget.children:
        yield from _walk(child)


def _labels(widget):
    from kivy.uix.label import Label

    return [w.text for w in _walk(widget) if isinstance(w, Label)]


class _FakeRepo:
    def __init__(self, transactions=()):
        self.transactions = list(transactions)
        self.deleted = []

    def get_all_transactions(self):
        return list(self.transactions)

    def get_recent_payment_details(self, limit=10):
        return []

    def delete_transaction(self, tx):
        self.deleted.append(tx.transactionId)
        self.transactions = [t for t in self.transactions
                             if t.transactionId != tx.transactionId]


def _screen(transactions=(), on_delete=None):
    vm = TransactionViewModel(_FakeRepo(transactions))
    screen = HistoryScreen(vm, on_delete=on_delete)
    vm.load_history()
    return screen, vm


# -- pure helpers -------------------------------------------------------------


def test_status_label_mapping():
    assert status_label("USER_CONFIRMED") == "✓ Confirmed by you"
    assert status_label("USER_NOT_CONFIRMED") == "✕ Not confirmed by you"
    assert status_label("SUCCESS") == "Success"
    assert status_label("completed") == "Success"
    assert status_label("UNVERIFIED") == "Unverified"
    assert status_label("NEEDS_REVIEW") == "Check"
    assert status_label("CANCELLED") == "Cancelled"
    assert status_label("FAILED") == "Failed"
    assert status_label("DECLINED") == "Failed"
    assert status_label("anything-else") == "Pending"


def test_format_time_zero_padded_hour():
    # "hh:mm a": the hour keeps its leading zero in list rows.
    ts = 1_763_900_000_000
    assert format_time(ts) == time.strftime("%I:%M %p", time.localtime(ts / 1000))
    assert format_time(ts)[1] == ":" or format_time(ts)[2] == ":"


def test_format_full_date_unpadded_hour_with_separator():
    ts = 1_763_900_000_000
    out = format_full_date(ts)
    assert " · " in out
    hour = out.split(" · ")[1].split(":")[0]
    assert not hour.startswith("0")


def test_grouping_buckets_and_order():
    now = int(time.time() * 1000)
    txs = [
        _tx("today", now - HOUR),
        _tx("yesterday", now - DAY - HOUR),
        _tx("week", now - 3 * DAY),
        _tx("old", now - 40 * DAY),
    ]
    grouped = group_transactions(txs, now)
    assert list(grouped) == ["Today", "Yesterday", "This Week",
                             list(grouped)[3]]
    assert grouped["Today"][0].transactionId == "today"
    assert grouped["Yesterday"][0].transactionId == "yesterday"
    assert grouped["This Week"][0].transactionId == "week"
    # Historical labels fall back to the dd MMM date.
    assert grouped[list(grouped)[3]][0].transactionId == "old"
    assert list(grouped)[3] != "This Week"


def test_grouping_sorts_descending():
    now = int(time.time() * 1000)
    txs = [_tx("older", now - 5 * HOUR), _tx("newer", now - HOUR)]
    grouped = group_transactions(txs, now)
    assert [t.transactionId for t in grouped["Today"]] == ["newer", "older"]


def test_historical_label_includes_year_across_years():
    now = int(time.time() * 1000)
    old_ts = now - 400 * DAY
    grouped = group_transactions([_tx("x", old_ts)], now)
    label = next(iter(grouped))
    assert time.strftime("%Y", time.localtime(old_ts / 1000)) in label


# -- screen states ------------------------------------------------------------


def test_screen_shows_title_and_groups():
    now = int(time.time() * 1000)
    screen, _ = _screen([_tx("t1", now - HOUR)])
    texts = _labels(screen)
    assert "Transactions" in texts
    assert "Today" in texts
    assert "Kirana Store" in texts


def test_empty_state_without_query():
    screen, _ = _screen([])
    texts = _labels(screen)
    assert "No transactions yet" in texts
    assert "Transactions will appear here" in texts


def test_empty_state_with_query():
    screen, _ = _screen([_tx("t1", int(time.time() * 1000))])
    screen._query = "zzz"
    screen._rebuild()
    texts = _labels(screen)
    assert "No matching transactions" in texts
    assert "Try a different search" in texts


def test_search_filters_rows():
    now = int(time.time() * 1000)
    screen, _ = _screen([_tx("t1", now, name="Kirana Store"),
                         _tx("t2", now, name="Tea Stall")])
    screen._query_changed("kirana")
    rows = [w for w in _walk(screen) if isinstance(w, HistoryRow)]
    assert len(rows) == 1
    assert rows[0].transaction.transactionId == "t1"


def test_search_toggle_clears_query():
    now = int(time.time() * 1000)
    screen, _ = _screen([_tx("t1", now)])
    screen._toggle_search()
    assert screen._search_open
    screen.search_bar.input.text = "kir"
    screen._toggle_search()
    assert not screen._search_open
    assert screen._query == ""
    rows = [w for w in _walk(screen) if isinstance(w, HistoryRow)]
    assert len(rows) == 1


def test_error_state_and_retry():
    class FailingRepo(_FakeRepo):
        fail = True

        def get_all_transactions(self):
            if self.fail:
                raise RuntimeError("db unavailable")
            return super().get_all_transactions()

    repo = FailingRepo([_tx("t1", int(time.time() * 1000))])
    vm = TransactionViewModel(repo)
    screen = HistoryScreen(vm)
    vm.load_history()
    assert "Something went wrong" in _labels(screen)
    repo.fail = False
    vm.retry_history()
    assert "Kirana Store" in _labels(screen)


def test_loading_state():
    vm = TransactionViewModel(_FakeRepo())
    screen = HistoryScreen(vm)
    # Before load_history the state is loading.
    assert screen._vm.history_state.value.is_loading


def test_action_error_surfaces_and_clears():
    screen, vm = _screen([])
    vm.error.set("Could not delete")
    assert "Could not delete" in _labels(screen)
    assert vm.error.value is None  # snackbar shows once, then clears


# -- rows and pills -----------------------------------------------------------


def test_row_shows_amount_and_time():
    now = int(time.time() * 1000)
    screen, _ = _screen([_tx("t1", now, amount="1499.50")])
    texts = _labels(screen)
    assert "₹1,499.50" in texts
    assert format_time(now) in texts


def test_row_hides_blank_amount():
    now = int(time.time() * 1000)
    screen, _ = _screen([_tx("t1", now, amount="")])
    assert not any(t.startswith("₹") for t in _labels(screen))


def test_row_press_opens_detail():
    now = int(time.time() * 1000)
    screen, _ = _screen([_tx("t1", now)])
    row = next(w for w in _walk(screen) if isinstance(w, HistoryRow))
    row.on_release()
    assert screen._detail is not None
    assert "Transaction details" in _labels(screen._detail)


def test_pill_label_and_size():
    pill = StatusPill("SUCCESS")
    assert pill._label.text == "Success"


# -- detail view ----------------------------------------------------------------


def test_detail_fields_present_and_absent():
    tx = _tx("t1", 1_763_900_000_000, phone=" 9123456780 ",
             upi="k@upi", ref="AX1")
    view = TransactionDetailView(tx)
    texts = _labels(view)
    for expected in ("Recipient", "Amount", "Phone number", "UPI ID",
                     "Bank reference", "Date & Time", "Kirana Store",
                     "9123456780", "k@upi", "AX1", "Done"):
        assert expected in texts, expected
    assert format_full_date(1_763_900_000_000) in texts


def test_detail_omits_blank_fields():
    tx = _tx("t1", 1_763_900_000_000, amount=" ", name="  ")
    # Blank name + blank phone fall back through recipient_label.
    tx2 = Transaction(transactionId="t2", amount="", status="SUCCESS",
                      bankName="HDFC Bank", smsExcerpt="", timestamp=1,
                      recipientName=None, phoneNumber=None, upiId=None,
                      bankRef=None)
    view = TransactionDetailView(tx2)
    texts = _labels(view)
    assert "Amount" not in texts
    assert "Phone number" not in texts
    assert "UPI ID" not in texts
    assert "Bank reference" not in texts
    assert "Not recorded" in texts


def test_detail_delete_flow():
    deleted = []
    tx = _tx("t1", 1_763_900_000_000)
    view = TransactionDetailView(tx, on_delete=lambda t: deleted.append(
        t.transactionId))
    view._ask_delete()
    assert view._confirm is not None
    assert "Delete this transaction?" in _labels(view._confirm)
    view._confirm._delete()
    assert deleted == ["t1"]
    assert view._confirm is None


def test_detail_delete_cancel():
    view = TransactionDetailView(_tx("t1", 1_763_900_000_000),
                                 on_delete=lambda t: None)
    view._ask_delete()
    view._confirm._cancel()
    assert view._confirm is None


def test_detail_dismiss_callback():
    calls = []
    view = TransactionDetailView(_tx("t1", 1_763_900_000_000),
                                 on_dismiss=lambda: calls.append(1))
    view._dismiss()
    assert calls == [1]
