# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from the observer half of
# app/src/test/java/com/paynet/app/payment/PaymentWindowObserverTest.kt

"""The observer closes the SMS operation window when — and only when — a
payment session is cancelled, whichever cancel route produced it."""

from paynet.payment import state as ps
from paynet.payment.window import PaymentWindowObserver

from test_payment_session import FakeCallStateSource, FakeStore, ManualWatchdog, new_manager


def test_observer_disarms_on_user_cancellation():
    manager, _, source, _, _ = new_manager()
    disarmed = []
    observer = PaymentWindowObserver(manager, on_disarm=lambda: disarmed.append(True))
    observer.start()

    manager.begin("9876543210", "500")
    source.call_started(at=0)
    manager.on_user_cancelled()

    assert disarmed == [True], "cancelling the session must close the SMS window"


def test_observer_disarms_on_dial_failure_and_short_call_and_never_started():
    # Every cancel route funnels through the same Cancelled state.
    for cancel_route in ("dial_failed", "short_call", "never_started"):
        manager, _, source, _, _ = new_manager()
        disarmed = []
        PaymentWindowObserver(manager, on_disarm=lambda: disarmed.append(True)).start()

        manager.begin("9876543210", "500")
        if cancel_route == "dial_failed":
            manager.on_dial_failed("Could not start the payment call")
        elif cancel_route == "short_call":
            source.call_started(at=0)
            source.call_ended(duration_ms=2_000)
        else:
            manager.on_call_never_started()

        assert disarmed == [True], f"{cancel_route} must close the SMS window"


def test_observer_does_not_disarm_on_success_timeout_or_progress():
    manager, _, source, watchdog, _ = new_manager()
    disarmed = []
    PaymentWindowObserver(manager, on_disarm=lambda: disarmed.append(True)).start()

    manager.begin("9876543210", "500")
    source.call_started(at=0)
    source.call_ended(duration_ms=40_000)  # WaitingForVerification
    watchdog.fire()  # Timeout — window outlives the deadline on purpose

    assert disarmed == [], "a timeout leaves the window to expire on its own"


def test_observer_does_not_disarm_on_confirmed_success():
    from test_payment_session import bank_sms

    manager, _, source, _, _ = new_manager()
    disarmed = []
    PaymentWindowObserver(manager, on_disarm=lambda: disarmed.append(True)).start()

    manager.begin("9876543210", "500")
    source.call_started(at=0)
    manager.on_sms_confirmed(bank_sms(amount="500"))

    assert disarmed == [], "success consumes the window in the ingestion path"
