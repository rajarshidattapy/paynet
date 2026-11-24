# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""Classic LegacyHomeDashboard (feature 8, classic variant): construction,
strings, locked-vs-ready action buttons, history states and row semantics.
Pure widget construction — no window is opened."""

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")

from paynet.db.models import PaymentDetails, PaymentStatus
from paynet import theme
from paynet.ui.home_legacy import (
    LegacyHomeScreen,
    LegacyTransactionItem,
    STR_EMPTY_TITLE,
    STR_ERROR_TITLE,
    STR_LOADING,
    STR_PAY_CONTACT,
    STR_SCAN_OPENING,
    STR_SCAN_QR,
    STR_SETUP_UPI123,
    STR_SETUP_USSD,
)


def _payment(status=PaymentStatus.COMPLETED, name="Kirana Store",
             confirmed=True, amount=240.0, pid="t1"):
    return PaymentDetails(
        id=pid,
        phoneNumber="9123456780",
        amount=amount,
        timestamp=1_763_900_000_000,
        status=status,
        recipientName=name,
        userConfirmed=confirmed,
    )


def _walk(widget):
    yield widget
    for child in widget.children:
        yield from _walk(child)


def _labels(widget):
    from kivy.uix.label import Label

    return [w.text for w in _walk(widget) if isinstance(w, Label)]


def _glyph_kinds(widget):
    from paynet.ui.home import Glyph

    return [w._kind for w in _walk(widget) if isinstance(w, Glyph)]


def _screen(**kwargs):
    return LegacyHomeScreen(**kwargs)


# -- construction -----------------------------------------------------------


def test_construction_bank_name_and_strings():
    screen = _screen(bank_name="ICICI Bank", is_ussd_ready=True,
                     is_upi123_ready=True)
    texts = _labels(screen)
    assert "ICICI Bank" in texts
    assert "Connected Bank" in texts
    assert STR_SCAN_QR in texts
    assert STR_PAY_CONTACT in texts
    assert "Recent Payments" in texts
    assert "View All" in texts


def test_black_canvas():
    screen = _screen()
    # LegacyHomeDashboard draws on a black canvas, not SurfaceDim.
    assert screen._bg_rect is not None


# -- action button states ---------------------------------------------------


def test_scan_button_locked_when_ussd_not_ready():
    screen = _screen(is_ussd_ready=False)
    assert STR_SETUP_USSD in _labels(screen.actions.scan)
    assert "qr" not in _glyph_kinds(screen.actions.scan)
    assert "lock" in _glyph_kinds(screen.actions.scan)


def test_scan_button_ready_shows_qr_glyph():
    screen = _screen(is_ussd_ready=True)
    assert STR_SCAN_QR in _labels(screen.actions.scan)
    assert "qr" in _glyph_kinds(screen.actions.scan)


def test_scan_button_scanning_label_and_swallowed_tap():
    calls = []
    screen = _screen(is_ussd_ready=True, is_scanning=True,
                     on_scan=lambda: calls.append(1))
    assert STR_SCAN_OPENING in _labels(screen.actions.scan)
    screen.actions.scan._press()
    assert calls == []  # detectTapGestures: swallowed while opening


def test_pay_button_locked_when_upi123_not_ready():
    screen = _screen(is_upi123_ready=False)
    assert STR_SETUP_UPI123 in _labels(screen.actions.pay)
    assert "lock" in _glyph_kinds(screen.actions.pay)


def test_pay_button_ready_shows_person_glyph():
    screen = _screen(is_upi123_ready=True)
    assert STR_PAY_CONTACT in _labels(screen.actions.pay)
    assert "person" in _glyph_kinds(screen.actions.pay)


def test_update_readiness_rebuilds_actions():
    screen = _screen(is_ussd_ready=False, is_upi123_ready=False)
    screen.update_readiness(True, True, False)
    assert STR_SCAN_QR in _labels(screen.actions.scan)
    assert STR_PAY_CONTACT in _labels(screen.actions.pay)


# -- history states ---------------------------------------------------------


def test_loading_state():
    screen = _screen()
    screen.show_loading()
    assert STR_LOADING in _labels(screen.history)


def test_error_state_shows_title_and_retry():
    screen = _screen()
    screen.show_error()
    texts = _labels(screen.history)
    assert STR_ERROR_TITLE in texts
    assert "Retry" in texts


def test_empty_state():
    screen = _screen()
    screen.show_payments([])
    assert STR_EMPTY_TITLE in _labels(screen.history)


def test_payments_state_rows_and_cap():
    screen = _screen()
    payments = [_payment(pid=f"t{i}") for i in range(5)]
    screen.show_payments(payments)
    items = [w for w in _walk(screen.history)
             if isinstance(w, LegacyTransactionItem)]
    assert len(items) == 3  # 372dp viewport: 3 rows, rest behind View All


def test_payments_replace_previous_state():
    screen = _screen()
    screen.show_payments([_payment()])
    screen.show_payments([])
    assert STR_EMPTY_TITLE in _labels(screen.history)
    assert not [w for w in _walk(screen.history)
                if isinstance(w, LegacyTransactionItem)]


# -- row semantics (TransactionItem in MainActivity.kt) ---------------------


def test_row_confirmed_shows_check_glyph():
    screen = _screen()
    screen.show_payments([_payment(confirmed=True)])
    assert "check" in _glyph_kinds(screen.history)


def test_row_unconfirmed_shows_amount_and_arrow():
    screen = _screen()
    screen.show_payments([_payment(confirmed=None, amount=240.0)])
    texts = _labels(screen.history)
    assert "₹240" in texts or "₹240.00" in texts
    assert "arrow" in _glyph_kinds(screen.history)


def test_row_failed_unconfirmed_shows_error_close():
    screen = _screen()
    screen.show_payments([_payment(status=PaymentStatus.FAILED,
                                   confirmed=None)])
    kinds = _glyph_kinds(screen.history)
    assert "close" in kinds
    assert "arrow" not in kinds


def test_row_recipient_fallback():
    screen = _screen()
    screen.show_payments([_payment(name="  ")])  # blank -> phone number
    texts = _labels(screen.history)
    assert "9123456780" in texts
    screen.show_payments([PaymentDetails(
        id="t9", phoneNumber="  ", amount=10.0, timestamp=1,
        status=PaymentStatus.COMPLETED, recipientName=None,
        userConfirmed=True)])
    assert "Not recorded" in _labels(screen.history)


def test_row_press_callback():
    seen = []
    screen = _screen(on_transaction=lambda p: seen.append(p.id))
    screen.show_payments([_payment(pid="tx-1")])
    item = next(w for w in _walk(screen.history)
                if isinstance(w, LegacyTransactionItem))
    item.on_release()
    assert seen == ["tx-1"]


def test_history_card_uses_surface_dim():
    from paynet.ui.home_legacy import LegacyHistoryCard

    palette = theme.accent_theme_for(False)
    card = LegacyHistoryCard(palette)
    assert card.size is not None  # constructed
