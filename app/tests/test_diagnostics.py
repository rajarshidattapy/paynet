# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported 1:1 from app/src/test/java/com/paynet/app/helpers/MainActivityReadinessTest.kt,
# plus new coverage for the TestConfigurationHelper port.

import pytest

from paynet import constants, onboarding
from paynet import setup as setup_logic
from paynet.db.database import Database
from paynet.db.models import Transaction
from paynet.db.settings import PrefsStore, TestResults, TestResultsManager
from paynet.repository import TransactionRepository
from paynet.telephony.call_manager import CallType
from paynet.ui.diagnostics import (MainActivityCallback, MainActivityHelper,
                                   STR_INVALID_AMOUNT, STR_INVALID_PHONE,
                                   STR_ENTER_PHONE_AND_AMOUNT,
                                   TestConfigurationHelper)


@pytest.fixture
def prefs(tmp_path):
    store = PrefsStore(str(tmp_path), "PayNetPrefs")
    store.put("selected_primary_sim", "airtel")
    return store


@pytest.fixture
def results(tmp_path):
    return TestResultsManager(str(tmp_path))


class RecordingCallback(MainActivityCallback):
    """RecordingCallback from MainActivityReadinessTest, ported 1:1."""

    def __init__(self):
        self.configuration_requests = 0
        self.permission_requests = 0
        self.overlay_requests = 0
        self.scanner_requests = 0
        self.messages = []
        self.payment_states = []

    def show_toast(self, message):
        self.messages.append(message)

    def update_payment_state(self, payment_state):
        self.payment_states.append(payment_state)

    def navigate_to_test_configuration(self):
        self.configuration_requests += 1

    def request_phone_permissions(self):
        self.permission_requests += 1

    def show_overlay_permission_explanation(self):
        self.overlay_requests += 1

    def launch_qr_scanner(self):
        self.scanner_requests += 1

    def navigate_to_setup(self):
        raise AssertionError("Unexpected setup navigation")

    def finish_activity(self):
        raise AssertionError("Unexpected finish request")


def _helper(prefs, results, callback, **kwargs):
    # The Kotlin readiness test never calls initialize(): the permission
    # manager stays null and the gates route to permission requests.
    return MainActivityHelper(prefs, results, callback, **kwargs)


def _assert_no_native_actions(callback):
    assert callback.permission_requests == 0
    assert callback.overlay_requests == 0
    assert callback.scanner_requests == 0
    assert callback.payment_states == []


# --- MainActivityReadinessTest, 1:1 -------------------------------------------


def test_missing_or_false_readiness_routes_both_actions_before_permission_requests(
        prefs, results):
    for stored in (None, TestResults()):
        results.clear_test_results()
        if stored is not None:
            results.save_test_results(stored)
        callback = RecordingCallback()
        helper = _helper(prefs, results, callback)

        helper.initiate_transfer("9876543210", "1")
        helper.start_qr_scanning()

        assert callback.configuration_requests == 2
        _assert_no_native_actions(callback)
        assert callback.messages == []


def test_contact_readiness_cannot_authorize_the_qr_rail(prefs, results):
    results.save_test_results(TestResults(ussdEnabled=False, upi123Enabled=True))
    callback = RecordingCallback()

    _helper(prefs, results, callback).start_qr_scanning()

    assert callback.configuration_requests == 1
    _assert_no_native_actions(callback)


def test_qr_readiness_cannot_authorize_the_contact_rail(prefs, results):
    results.save_test_results(TestResults(ussdEnabled=True, upi123Enabled=False))
    callback = RecordingCallback()

    _helper(prefs, results, callback).initiate_transfer("9876543210", "1")

    assert callback.configuration_requests == 1
    _assert_no_native_actions(callback)


def test_valid_readiness_reaches_only_the_existing_permission_gate(prefs, results):
    results.save_test_results(TestResults(ussdEnabled=True, upi123Enabled=True))
    callback = RecordingCallback()
    helper = _helper(prefs, results, callback)

    helper.initiate_transfer("9876543210", "1")
    helper.start_qr_scanning()

    assert callback.configuration_requests == 0
    assert callback.permission_requests == 2
    assert callback.overlay_requests == 0
    assert callback.scanner_requests == 0
    assert callback.payment_states == []


def test_invalid_contact_input_keeps_validation_ahead_of_the_readiness_gate(
        prefs, results):
    callback = RecordingCallback()
    helper = _helper(prefs, results, callback)

    helper.initiate_transfer("", "1")
    helper.initiate_transfer("123", "1")
    helper.initiate_transfer("9876543210", "0")

    assert callback.messages == [
        STR_ENTER_PHONE_AND_AMOUNT, STR_INVALID_PHONE, STR_INVALID_AMOUNT]
    assert callback.configuration_requests == 0
    _assert_no_native_actions(callback)


def test_carrier_restriction_keeps_its_message_ahead_of_qr_readiness(prefs, results):
    prefs.put("selected_primary_sim", "jio")
    callback = RecordingCallback()

    _helper(prefs, results, callback).start_qr_scanning()

    assert callback.messages == [setup_logic.get_scan_to_pay_blocked_message(prefs)]
    assert callback.configuration_requests == 0
    _assert_no_native_actions(callback)


def test_the_same_helper_rechecks_invalidated_results_and_preserves_unrelated_state(
        prefs, results, tmp_path):
    prefs.put("selected_bank", "sbi")
    prefs.put("setup_completed", True)
    prefs.put("test_configuration_completed", True)
    prefs.put(onboarding.APPEARANCE_COMPLETED, True)
    prefs.put(onboarding.WELCOME_COMPLETED, True)
    prefs.put("home_classic", True)
    prefs.put("home_monochrome", False)
    db = Database(str(tmp_path / "paynet.db"))
    repository = TransactionRepository(db)
    db.insert_transaction(Transaction(
        transactionId="existing-payment", amount="125", status="CONFIRMED",
        bankName="sbi", smsExcerpt="seeded", timestamp=1))
    results.save_test_results(TestResults(ussdEnabled=True, upi123Enabled=True))
    callback = RecordingCallback()
    helper = _helper(prefs, results, callback)
    helper.start_qr_scanning()
    assert callback.permission_requests == 1

    setup_logic.invalidate_payment_configuration(prefs, results)
    helper.initiate_transfer("9876543210", "1")
    helper.start_qr_scanning()

    assert callback.configuration_requests == 2
    # Invalidation must block before any additional permission request.
    assert callback.permission_requests == 1
    assert callback.overlay_requests == 0
    assert callback.scanner_requests == 0
    assert callback.payment_states == []
    assert results.get_test_results() is None
    assert prefs.get("test_configuration_completed", True) is False

    # Unrelated setup, appearance and history state survives.
    assert prefs.get("selected_bank") == "sbi"
    assert prefs.get("selected_primary_sim") == "airtel"
    assert prefs.get("setup_completed", False) is True
    assert prefs.get(onboarding.APPEARANCE_COMPLETED, False) is True
    assert prefs.get(onboarding.WELCOME_COMPLETED, False) is True
    assert prefs.get("home_classic", False) is True
    assert prefs.get("home_monochrome", True) is False
    history = repository.get_all_transactions()
    assert len(history) == 1
    assert history[0].transactionId == "existing-payment"
    assert history[0].amount == "125"


# --- TestConfigurationHelper coverage ----------------------------------------


class ManualClock:
    def __init__(self, now=0.0):
        self.now = now
        self.pending = []  # (fire_at, fn, cancelled)

    def __call__(self):
        return self.now

    def schedule(self, delay, fn):
        entry = [self.now + delay, fn, False]
        self.pending.append(entry)
        return entry

    def cancel(self, token):
        token[2] = True

    def advance(self, seconds):
        self.now += seconds
        for entry in list(self.pending):
            if not entry[2] and entry[0] <= self.now:
                self.pending.remove(entry)
                entry[1]()


@pytest.fixture
def diag(tmp_path):
    prefs = PrefsStore(str(tmp_path), "PayNetPrefs")
    prefs.put("selected_primary_sim", "airtel")
    results = TestResultsManager(str(tmp_path))
    clock = ManualClock()
    toasts, navigations, permission_requests = [], [], []
    dials, calls = [], []
    helper = TestConfigurationHelper(
        prefs, results,
        permission_manager=None,
        show_toast=toasts.append,
        navigate_to_main=lambda: navigations.append("main"),
        request_phone_permissions=lambda: permission_requests.append(1),
        dial=dials.append,
        start_call=lambda number, kind, on_end: calls.append(
            (number, kind, on_end)),
        clock=clock, scheduler=clock.schedule, cancel=clock.cancel)
    return (helper, prefs, results, clock, toasts, navigations,
            permission_requests, dials, calls)


def test_ussd_test_requires_phone_permissions_first(diag):
    (helper, prefs, results, clock, toasts, navigations,
     permission_requests, dials, calls) = diag
    helper.initialize()
    helper.initiate_call(CallType.USSD)
    assert toasts == ["Phone call permission is required to test USSD."]
    assert len(permission_requests) == 1
    assert dials == [] and helper.ussd_testing is False


def test_denied_permissions_toast(diag):
    helper = diag[0]
    helper.on_phone_permissions_result(False)
    assert diag[4] == ["Some permissions were denied. PayNet may not work "
                       "correctly without them."]
    helper.on_phone_permissions_result(True)
    assert len(diag[4]) == 1


def _granted(diag):
    from paynet.permissions import PermissionManager
    helper = diag[0]
    helper._permission_manager = PermissionManager(checker=lambda _p: True)
    return helper


def test_ussd_flow_reaches_configuration_options_after_25_seconds(diag):
    helper = _granted(diag)
    (helper, prefs, results, clock, toasts, navigations,
     permission_requests, dials, calls) = (helper, *diag[1:])
    helper.initialize()
    helper.initiate_call(CallType.USSD)
    assert dials == ["*99#"]
    states = helper.get_test_states()
    assert states.ussdTesting and states.showUssdDialog
    assert states.ussdProgressMessage == "Dialing *99#..."
    # A second tap while testing is ignored (duplicate-dial guard).
    helper.initiate_call(CallType.USSD)
    assert dials == ["*99#"]

    clock.advance(25.0)
    states = helper.get_test_states()
    assert not states.showUssdDialog and states.showUssdConfigurationOptions

    helper.handle_ussd_configuration_confirmation(True)
    assert helper.ussd_test_completed is True
    saved = results.get_test_results()
    assert saved.ussdEnabled is True and saved.upi123Enabled is False


def test_does_not_work_marks_user_reported_and_confirmation_x_is_not_yet(diag):
    helper = _granted(diag)
    prefs = diag[1]
    helper.initialize()
    # "It isn't working" from the progress step saves the user's opt-out.
    helper.initiate_call(CallType.USSD)
    helper.dismiss_ussd_dialog(from_does_not_work=True)
    assert helper.ussd_testing is False and helper.show_ussd_dialog is False
    assert setup_logic.has_user_reported_ussd_not_working(prefs) is True
    assert helper.ussd_test_completed is False
    # Retrying clears the user-reported flag.
    helper.initiate_call(CallType.USSD)
    assert setup_logic.has_user_reported_ussd_not_working(prefs) is False
    # Once the confirmation step is showing, dismiss (even from the X that
    # carries from_does_not_work) behaves like "Not yet": no flag is set.
    diag[3].advance(25.0)
    assert helper.show_ussd_configuration_options is True
    helper.dismiss_ussd_dialog(from_does_not_work=True)
    assert helper.show_ussd_configuration_options is False
    assert helper.ussd_testing is False
    assert setup_logic.has_user_reported_ussd_not_working(prefs) is False
    assert helper.ussd_test_completed is False


def test_upi123_flow_shows_options_two_seconds_after_the_call_ends(diag):
    helper, prefs, results, clock = diag[0], diag[1], diag[2], diag[3]
    calls = diag[8]
    helper.initialize()
    helper.initiate_upi123_test()
    assert helper.upi123_testing is True and helper.show_upi123_dialog is True
    assert calls[0][0] == constants.DEFAULT_UPI_SERVICE_NUMBER
    assert calls[0][1] == CallType.UPI123
    # Duplicate start is guarded.
    helper.initiate_upi123_test()
    assert len(calls) == 1

    calls[0][2](CallType.UPI123)  # call ended
    assert helper.upi123_testing is False
    assert helper.show_upi123_configuration_options is False  # 2 s delay first
    clock.advance(2.0)
    assert helper.show_upi123_dialog is False
    assert helper.show_upi123_configuration_options is True

    helper.handle_upi123_configuration_confirmation(True)
    saved = results.get_test_results()
    assert saved.upi123Enabled is True


def test_continue_and_skip_save_results_mark_completed_and_navigate(diag):
    helper, prefs, results = diag[0], diag[1], diag[2]
    navigations = diag[5]
    helper.initialize()
    helper.handle_upi123_configuration_confirmation(True)
    helper.continue_to_main()
    assert prefs.get(constants.KEY_TEST_COMPLETED) is True
    assert navigations == ["main"]
    assert results.get_test_results().upi123Enabled is True

    results.clear_test_results()
    prefs.put(constants.KEY_TEST_COMPLETED, False)
    helper2 = TestConfigurationHelper(
        prefs, results, navigate_to_main=lambda: navigations.append("main"),
        scheduler=diag[3].schedule, cancel=diag[3].cancel, clock=diag[3])
    helper2.initialize()
    helper2.skip_tests()
    assert prefs.get(constants.KEY_TEST_COMPLETED) is True
    assert navigations == ["main", "main"]


def test_can_continue_and_all_completed_respect_the_jio_waiver(tmp_path):
    prefs = PrefsStore(str(tmp_path), "PayNetPrefs")
    prefs.put("selected_primary_sim", "jio")  # USSD unavailable -> waived
    results = TestResultsManager(str(tmp_path))
    clock = ManualClock()
    helper = TestConfigurationHelper(prefs, results, clock=clock,
                                     scheduler=clock.schedule,
                                     cancel=clock.cancel)
    helper.initialize()
    assert helper.can_continue() is True      # waived USSD alone is enough
    assert helper.all_tests_completed() is False
    helper.handle_upi123_configuration_confirmation(True)
    assert helper.all_tests_completed() is True

    # A USSD-capable SIM without a test or waiver blocks both.
    prefs.put("selected_primary_sim", "airtel")
    helper2 = TestConfigurationHelper(prefs, results, clock=clock,
                                      scheduler=clock.schedule,
                                      cancel=clock.cancel)
    helper2.initialize()
    assert helper2.can_continue() is True    # upi123 still done
    assert helper2.all_tests_completed() is False


def test_scan_attempt_survives_a_recreate(diag):
    helper = _granted(diag)
    clock = diag[3]
    helper.initialize()
    helper.initiate_call(CallType.USSD)
    state = {}
    helper.save_scan_attempt(state)
    assert state["paynet.scan.deadline"] > 0
    helper.cleanup()

    restored = TestConfigurationHelper(
        diag[1], diag[2], clock=clock, scheduler=clock.schedule,
        cancel=clock.cancel)
    restored.initialize()
    restored.restore_scan_attempt(state)
    assert restored.ussd_testing is True and restored.show_ussd_dialog is True
    # The deadline (not a fresh 25 s) drives the timeout.
    clock.now = state["paynet.scan.deadline"]
    clock.advance(0.1)
    assert restored.show_ussd_configuration_options is True


def test_ussd_launch_failure_dismisses_and_toasts(diag):
    helper = _granted(diag)
    def failing_dial(_number):
        raise RuntimeError("no dialler")
    helper._dial = failing_dial
    helper.initialize()
    helper.initiate_call(CallType.USSD)
    assert helper.ussd_testing is False and helper.show_ussd_dialog is False
    assert diag[4] == ["Could not start the USSD call."]
