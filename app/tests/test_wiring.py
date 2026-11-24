# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
"""App-shell wiring: the pieces ported in features 5-7 must actually be
connected in AppContainer / the pay-contact initiator, not just unit-tested
in isolation."""

import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("KIVY_NO_ARGS", "1")

from paynet.app import AppContainer
from paynet.db.settings import TestResults
from paynet.payment.initiate import TransferInitiator
from paynet.payment.session import PaymentSessionManager


def _fake_bindings():
    adapter = object()
    return SimpleNamespace(
        telephony_adapter=adapter,
        metrics_poster=lambda *_: None,
        # Same shape as the real Bindings: the checker is a callable, and
        # can_draw_overlays lives on the bindings themselves.
        permission_checker=lambda _permission: True,
        can_draw_overlays=lambda: True,
        phone_platform=mock.MagicMock(),
    )


def test_session_manager_shares_the_coordinator_that_owns_the_telephony_adapter(
        tmp_path):
    bindings = _fake_bindings()
    with mock.patch("paynet.platform.create_bindings", return_value=bindings):
        container = AppContainer(str(tmp_path))
    # Regression: the session manager used to be built with a telephony-less
    # coordinator that was then replaced, so it never saw a call on a device.
    assert container.payment_session_manager._coordinator \
        is container.call_coordinator
    assert container.call_coordinator._telephony is bindings.telephony_adapter


def test_desktop_container_has_no_telephony_and_no_call_manager(tmp_path):
    container = AppContainer(str(tmp_path))
    assert container.bindings is None
    assert container.call_manager is None
    assert container.call_coordinator._telephony is None


def test_cancelling_a_payment_closes_the_sms_window(tmp_path):
    container = AppContainer(str(tmp_path))
    detector = container.transaction_detector
    txn_id = container.payment_session_manager.begin("9123456780", "240")
    detector.start_operation("UPI_123", expected_amount="240",
                             phone_number="9123456780", session_txn_id=txn_id)
    assert detector.should_process_sms()

    container.payment_session_manager.on_user_cancelled()

    assert not detector.should_process_sms()


def test_startup_sweeps_stale_pending_rows_once(tmp_path):
    with mock.patch.object(
            PaymentSessionManager, "reconcile_stale_pending") as sweep:
        AppContainer(str(tmp_path))
    sweep.assert_called_once_with()


# --- pay-contact initiator ---------------------------------------------------


class _Session:
    def __init__(self):
        self.dial_failures = []

    def begin(self, phone, amount, recipient_name=None):
        return "txn-1"

    def on_dial_failed(self, reason):
        self.dial_failures.append(reason)


def _initiator(place_call, detector):
    session = _Session()
    results = SimpleNamespace(
        get_test_results=lambda: TestResults(upi123Enabled=True))
    return TransferInitiator(
        results, session, show_toast=lambda _m: None,
        place_call=place_call, detector=detector), session


def test_initiate_transfer_opens_the_sms_window_for_the_new_session():
    detector = mock.MagicMock()
    initiator, _ = _initiator(lambda p, a: True, detector)

    assert initiator.initiate_transfer("9123456780", "240") == "txn-1"

    detector.start_operation.assert_called_once_with(
        operation_type="UPI_123", expected_amount="240",
        phone_number="9123456780", session_txn_id="txn-1")


def test_a_failed_dial_cancels_the_session():
    initiator, session = _initiator(lambda p, a: False, mock.MagicMock())

    initiator.initiate_transfer("9123456780", "240")

    assert session.dial_failures == ["Could not start the payment call"]


def test_a_successful_dial_leaves_the_session_alone():
    initiator, session = _initiator(lambda p, a: True, mock.MagicMock())

    initiator.initiate_transfer("9123456780", "240")

    assert session.dial_failures == []


def test_no_call_layer_still_opens_the_window_and_never_cancels():
    detector = mock.MagicMock()
    initiator, session = _initiator(None, detector)

    initiator.initiate_transfer("9123456780", "240")

    detector.start_operation.assert_called_once()
    assert session.dial_failures == []


# --- the platform seams app.py reaches into -----------------------------------


def test_every_binding_path_app_py_reads_exists_on_bindings():
    """app.py reads `bindings.<x>` and `bindings.<x>.<y>` only when running
    on Android, so a typo there is invisible to every desktop test and
    crashes the app at startup on a phone."""
    import re
    import paynet.app as app_module
    import paynet.platform.android as android

    source = open(app_module.__file__, encoding="utf-8").read()
    paths = set(re.findall(
        r"bindings\.(\w+)(?:\s*\.\s*(\w+))?", source))
    assert paths, "expected app.py to use the platform bindings"
    # Construction reaches for the Android context and a few Java classes;
    # stub those handles so this runs on the desktop.
    with mock.patch.object(android, "_context", lambda: mock.MagicMock()),             mock.patch.object(android, "_activity", lambda: mock.MagicMock()),             mock.patch.object(android, "_version_sdk", lambda: 34),             mock.patch.object(android, "autoclass", lambda _n: mock.MagicMock()):
        bindings = android.Bindings()
    for first, second in sorted(paths):
        assert hasattr(bindings, first), f"Bindings.{first}"
        if second:
            assert hasattr(getattr(bindings, first), second), \
                f"Bindings.{first}.{second}"


def test_request_phone_permissions_asks_for_the_whole_phone_group():
    import paynet.platform.android as android
    from paynet.permissions import PermissionConstants

    requester = android.AndroidPermissionRequester()
    asked = []
    requester.request = lambda permissions, on_result: asked.append(
        tuple(permissions))

    requester.request_phone_permissions()

    assert asked == [tuple(PermissionConstants.PHONE_PERMISSIONS)]


# --- result notification ------------------------------------------------------


def test_notification_id_fits_a_java_int_and_is_stable_per_payment():
    from paynet.sms.notifier import notify_result

    posted = []
    result = {"transaction_id": "a-transaction-id", "status": "SUCCESS",
              "amount": "240", "bank_name": "HDFC Bank"}
    notify_result(result, post=lambda *args: posted.append(args))
    notify_result(result, post=lambda *args: posted.append(args))

    first, second = posted[0][0], posted[1][0]
    assert first == second
    assert 0 <= first <= 0x7FFFFFFF


def test_a_failing_post_never_raises_so_the_result_screen_still_opens():
    from paynet.sms.notifier import notify_result

    def boom(*_args):
        raise OverflowError("int too large")

    notify_result({"transaction_id": "t", "status": "SUCCESS"}, post=boom)
