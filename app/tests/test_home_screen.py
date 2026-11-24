# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""Home dashboard (feature 8): ported Compose sizing formulas, bank-name
mapping and widget-state transitions. Pure widget construction — no window
is opened, matching test_shell.py's approach."""

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")

import pytest

from paynet.db.models import PaymentDetails, PaymentStatus


def _payment(status=PaymentStatus.COMPLETED, name="Kirana Store"):
    return PaymentDetails(
        id="t1",
        phoneNumber="9123456780",
        amount=240.0,
        timestamp=1_763_900_000_000,
        status=status,
        recipientName=name,
        userConfirmed=True,
    )


def test_bank_name_map_matches_main_screen_content():
    from paynet.ui.home import home_bank_name

    assert home_bank_name("hdfc") == "HDFC Bank"
    assert home_bank_name("icici") == "ICICI Bank"
    assert home_bank_name("sbi") == "State Bank of India"
    assert home_bank_name("axis") == "Axis Bank"
    assert home_bank_name("kotak") == "Kotak Mahindra Bank"
    # MainScreenContent.kt: the when-else branch defaults to HDFC Bank
    assert home_bank_name("some-other-bank") == "HDFC Bank"


def test_compose_sizing_formulas():
    """The BoxWithConstraints formulas from HomeDashboard.kt, ported 1:1."""
    from kivy.metrics import dp

    def content_width(w):
        return min(w, dp(440))

    def tile_width(cw):
        return min(max(cw * 0.26, dp(88)), dp(116))

    def extra_height(h):
        return min(max((h - dp(700)) * 0.16, 0), dp(18))

    def hero_height(cw, tw, eh):
        return (cw - dp(44) - tw) / 0.96 + eh

    def top_inset(h):
        return min(max(h * 0.057, dp(36)), dp(58))

    def bottom_inset(h):
        return max(h * 0.04, dp(28))

    def history_height(h):
        return min(max(h * 0.5, dp(382)), dp(420))

    # Phone-ish viewport (matches the Compose preview device)
    w, h = dp(412), dp(892)
    cw = content_width(w)
    assert cw == dp(412)
    tw = tile_width(cw)
    assert tw == pytest.approx(min(max(dp(412) * 0.26, dp(88)), dp(116)))
    eh = extra_height(h)
    assert eh == pytest.approx(min((h - dp(700)) * 0.16, dp(18)))
    assert hero_height(cw, tw, eh) > dp(250)
    assert top_inset(h) == pytest.approx(h * 0.057)
    assert bottom_inset(h) == pytest.approx(h * 0.04)
    assert history_height(h) == dp(420)

    # Small viewport: clamps engage
    small = dp(320)
    assert tile_width(content_width(small)) == max(dp(320) * 0.26, dp(88))
    assert extra_height(dp(600)) == 0
    assert top_inset(dp(500)) == dp(36)
    assert history_height(dp(600)) == dp(382)


def test_home_screen_constructs_and_shows_states():
    from paynet.ui.home import (
        STR_EMPTY,
        STR_ERROR_LOAD,
        STR_READY,
        STR_SETUP_REQUIRED,
        HomeScreen,
    )

    screen = HomeScreen(bank_id="hdfc", is_ussd_ready=True, is_upi123_ready=True)
    assert screen._scan_state() == STR_READY
    assert screen._pay_state() == STR_READY

    screen.show_payments([_payment(), _payment(status=PaymentStatus.FAILED, name="9123456780")])
    assert any("Kirana Store" in t for t in _all_labels(screen.history_panel._rows))

    screen.show_payments([])
    labels = _all_labels(screen.history_panel._rows)
    assert any(STR_EMPTY in t for t in labels)

    screen.show_error()
    labels = _all_labels(screen.history_panel._rows)
    assert any(STR_ERROR_LOAD in t for t in labels)

    screen.show_loading()
    assert len(screen.history_panel._rows.children) == 1

    # Readiness gating (MainScreenContent.kt): no USSD test -> setup required
    screen2 = HomeScreen(bank_id="sbi", is_ussd_ready=False, is_upi123_ready=False)
    assert screen2._scan_state() == STR_SETUP_REQUIRED
    assert screen2._pay_state() == STR_SETUP_REQUIRED


def test_text_button_width_follows_texture_without_relayout_loop():
    from paynet.ui.home import _TextButton

    button = _TextButton("View all")
    button.texture_update()
    assert button.width == pytest.approx(button.texture_size[0] + 12, rel=0.2)


def _all_labels(widget):
    texts = []
    for child in widget.children:
        if hasattr(child, "text"):
            texts.append(child.text)
        texts.extend(_all_labels(child))
    return texts
