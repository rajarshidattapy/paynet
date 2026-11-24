# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/helpers/TestConfigurationHelper.kt,
# app/src/main/java/com/paynet/app/TestConfigurationActivity.kt and
# app/src/main/java/com/paynet/app/helpers/MainActivityHelper.kt

"""Diagnostics: the test-configuration screen and the readiness gates that
route to it.

DEVIATIONS (recorded in MIGRATION.md):
- Placing the real *99# / UPI 123Pay calls, the ACTION_CALL intent and the
  phone-permission launcher are device-only: injected callables
  (`dial`, `start_call`, `request_phone_permissions`), never triggered from
  the desktop build.
- MainActivityHelper.warnIfVoiceSimMismatch is SubscriptionManager-bound and
  stays device-only (an injected `voice_sim_warning` callable, default None);
  it never blocks.
- The Compose 100 ms state-polling LaunchedEffect maps to a Kivy Clock
  interval re-reading helper.get_test_states().
- utils/ContextExt.kt (findComponentActivity) is an Android context-wrapper
  walk with no Kivy equivalent: not ported, recorded here.
- Page transitions, status-bar insets and edge-to-edge are dropped.
"""

import enum
from dataclasses import dataclass
from typing import Callable, Optional

from paynet import constants
from paynet import setup as setup_logic
from paynet.permissions import PermissionManager, RECEIVE_SMS
from paynet.telephony.call_manager import CallType

# strings.xml
STR_PERMISSIONS_DENIED = ("Some permissions were denied. PayNet may not work "
                          "correctly without them.")
STR_CALL_PERMISSION_REQUIRED_USSD = "Phone call permission is required to test USSD."
STR_USSD_CALL_FAILED = "Could not start the USSD call."
STR_REQUESTING_PERMISSIONS = "Requesting the permissions PayNet needs…"
STR_OPENING_SCANNER = "Opening the QR scanner…"
STR_PHONE_PERMISSION_REQUIRED = "PayNet needs phone permissions to place the payment call."
STR_PAYMENT_NOT_STARTED = "The payment could not be started. Please try again."
STR_SMS_PERMISSION_EXPLANATION = (
    "Allow incoming SMS to detect your bank’s payment result during an "
    "active payment attempt. PayNet never reads your inbox. Messages are "
    "processed on this device. Without this permission, automatic "
    "confirmation is unavailable.")
STR_ENTER_PHONE_AND_AMOUNT = "Enter both a phone number and an amount."
STR_INVALID_PHONE = "Enter a valid 10-digit phone number."
STR_INVALID_AMOUNT = "Enter a valid amount."

USSD_SETUP_TIMEOUT_S = 25.0
UPI123_CONFIG_DELAY_S = 2.0
SCAN_DEADLINE_KEY = "paynet.scan.deadline"


@dataclass
class TestStates:
    """TestConfigurationHelper.TestStates, ported 1:1."""
    ussdTesting: bool = False
    showUssdDialog: bool = False
    ussdTestCompleted: bool = False
    upi123Testing: bool = False
    upi123TestCompleted: bool = False
    voiceTesting: bool = False
    showVoiceDialog: bool = False
    voiceTestCompleted: bool = False
    showCallCompleteButton: bool = False
    ussdProgressMessage: str = "Initializing..."
    showUssdConfigurationOptions: bool = False
    showUpi123Dialog: bool = False
    showUpi123ConfigurationOptions: bool = False


class TestConfigurationHelper:
    """Port of helpers/TestConfigurationHelper.kt: all business logic for the
    test-configuration screen.

    `scheduler(delay_seconds, fn)` fires fn once; `cancel(token)` drops a
    pending fire. Both map to Handler.postDelayed/removeCallbacks (Kivy Clock
    by default; manual in tests)."""

    def __init__(
        self,
        prefs,
        test_results,
        permission_manager: Optional[PermissionManager] = None,
        show_toast: Callable[[str], None] = lambda _m: None,
        navigate_to_main: Callable[[], None] = lambda: None,
        request_phone_permissions: Callable[[], None] = lambda: None,
        dial: Optional[Callable[[str], None]] = None,
        start_call: Optional[Callable] = None,
        clock: Callable[[], float] = None,
        scheduler: Optional[Callable[[float, Callable[[], None]], object]] = None,
        cancel: Optional[Callable[[object], None]] = None,
    ) -> None:
        self._prefs = prefs
        self._test_results = test_results
        self._permission_manager = permission_manager or PermissionManager()
        self._show_toast = show_toast
        self._navigate_to_main = navigate_to_main
        self._request_phone_permissions = request_phone_permissions
        # DEVIATION: device-only call placement, injected and None on desktop.
        self._dial = dial
        # start_call(phone_number, call_type, on_call_ended) -> None; stands in
        # for CallManager.initiateCall.
        self._start_call = start_call
        import time as _time
        self._clock = clock or _time.monotonic
        if scheduler is None:
            from kivy.clock import Clock
            scheduler = lambda delay, fn: Clock.schedule_once(lambda *_: fn(), delay)
            cancel = lambda token: token.cancel()
        self._scheduler = scheduler
        self._cancel = cancel

        self._ussd_timeout_token = None
        self._upi123_delay_token = None
        self._scan_deadline = 0.0

        self.current_testing_type: Optional[CallType] = None
        self.ussd_testing = False
        self.show_ussd_dialog = False
        self.ussd_test_completed = False
        self.show_call_complete_button = False
        self.upi123_test_completed = False
        self.voice_testing = False
        self.show_voice_dialog = False
        self.voice_test_completed = False
        self.upi123_testing = False
        self.show_upi123_dialog = False
        self.show_upi123_configuration_options = False
        self.ussd_progress_message = "Initializing..."
        self.show_ussd_configuration_options = False

    # -- lifecycle ----------------------------------------------------------

    def initialize(self) -> None:
        """Reopening configuration retains readiness in both the UI and
        subsequent saves. Unavailable methods are not successful tests."""
        saved = self._test_results.get_test_results()
        self.ussd_test_completed = bool(saved and saved.ussdEnabled)
        self.upi123_test_completed = bool(saved and saved.upi123Enabled)

    def cleanup(self) -> None:
        self._cancel_ussd_timeout()
        self._cancel_upi123_delay()

    def on_phone_permissions_result(self, granted: bool) -> None:
        if not granted:
            self._show_toast(STR_PERMISSIONS_DENIED)

    # -- test calls -----------------------------------------------------------

    def initiate_call(self, call_type: CallType) -> None:
        if call_type == CallType.USSD and (self.ussd_testing or self.ussd_test_completed):
            return
        if not self._permission_manager.has_phone_permissions():
            self._show_toast(STR_CALL_PERMISSION_REQUIRED_USSD)
            self._request_phone_permissions()
            return

        number = {
            CallType.USSD: "*99#",
            CallType.VOICE: "1234567890",
            CallType.UPI123: "1234567890",
            CallType.MANUAL_TRANSFER: "1234567890",
        }[call_type]

        if call_type == CallType.USSD:
            setup_logic.set_user_reported_ussd_not_working(self._prefs, False)
            self.ussd_testing = True
            self.show_ussd_dialog = True
            self.ussd_progress_message = "Dialing *99#..."
        elif call_type in (CallType.VOICE, CallType.MANUAL_TRANSFER):
            self.voice_testing = True
            self.show_voice_dialog = True
        else:  # UPI123 has its own method
            return

        self.current_testing_type = call_type

        if call_type == CallType.USSD:
            # The dialler owns the USSD menu; no call-state listener may
            # dispatch a second request for this setup attempt.
            self._start_ussd_timeout()
            try:
                if self._dial is not None:
                    self._dial(number)
                # else: DEVIATION, device-only dial never triggered.
            except Exception:
                self._report_ussd_launch_failure()
            return

        def _on_call_ended(ended_type: CallType) -> None:
            if ended_type in (CallType.VOICE, CallType.MANUAL_TRANSFER):
                self.voice_testing = False
                self.show_voice_dialog = False
                self.voice_test_completed = True
                self.show_call_complete_button = True
            elif ended_type == CallType.USSD:
                self.show_call_complete_button = True
            self.current_testing_type = None

        if self._start_call is not None:
            self._start_call(number, call_type, _on_call_ended)

    def initiate_upi123_test(self) -> None:
        if self.upi123_test_completed or self.upi123_testing:
            return
        self.upi123_testing = True
        self.show_upi123_dialog = True

        def _on_call_ended(ended_type: CallType) -> None:
            if ended_type != CallType.UPI123 or not self.upi123_testing:
                return
            # Call ended: show the configuration dialog after a 2 s delay.
            self.upi123_testing = False
            self._cancel_upi123_delay()

            def _show_options():
                self._upi123_delay_token = None
                if not self.upi123_test_completed:
                    self.show_upi123_dialog = False
                    self.show_upi123_configuration_options = True

            self._upi123_delay_token = self._scheduler(UPI123_CONFIG_DELAY_S,
                                                       _show_options)

        if self._start_call is not None:
            self._start_call(constants.DEFAULT_UPI_SERVICE_NUMBER,
                             CallType.UPI123, _on_call_ended)

    # -- USSD timeout -----------------------------------------------------------

    def save_scan_attempt(self, state: dict) -> None:
        if self.ussd_testing:
            state[SCAN_DEADLINE_KEY] = self._scan_deadline

    def restore_scan_attempt(self, state: Optional[dict]) -> None:
        if not state:
            return
        deadline = state.get(SCAN_DEADLINE_KEY, 0)
        if deadline <= 0 or self.ussd_test_completed:
            return
        self.ussd_testing = True
        self.show_ussd_dialog = True
        self._start_ussd_timeout(deadline)

    def _start_ussd_timeout(self, deadline: Optional[float] = None) -> None:
        if deadline is None:
            deadline = self._clock() + USSD_SETUP_TIMEOUT_S
        self._scan_deadline = deadline
        self._cancel_ussd_timeout()

        def _on_timeout():
            self._ussd_timeout_token = None
            if self.ussd_testing and not self.ussd_test_completed:
                self.show_ussd_dialog = False
                self.show_ussd_configuration_options = True

        delay = min(max(deadline - self._clock(), 0.0), USSD_SETUP_TIMEOUT_S)
        self._ussd_timeout_token = self._scheduler(delay, _on_timeout)

    def _cancel_ussd_timeout(self) -> None:
        if self._ussd_timeout_token is not None:
            self._cancel(self._ussd_timeout_token)
            self._ussd_timeout_token = None

    def _cancel_upi123_delay(self) -> None:
        if self._upi123_delay_token is not None:
            self._cancel(self._upi123_delay_token)
            self._upi123_delay_token = None

    def _report_ussd_launch_failure(self) -> None:
        self.dismiss_ussd_dialog()
        self._show_toast(STR_USSD_CALL_FAILED)

    # -- dialog dismissals -------------------------------------------------

    def dismiss_ussd_dialog(self, from_does_not_work: bool = False) -> None:
        """Close from the X button, or dismiss progress early.
        from_does_not_work also saves the user's choice to keep scan to pay
        off. If the confirmation step is showing, behaves like "Not yet"."""
        if self.show_ussd_configuration_options:
            self.handle_ussd_configuration_confirmation(False)
            return
        self._cancel_ussd_timeout()
        self.ussd_testing = False
        self.show_ussd_dialog = False
        self.show_ussd_configuration_options = False
        if from_does_not_work:
            setup_logic.set_user_reported_ussd_not_working(self._prefs, True)

    def dismiss_upi123_dialog(self) -> None:
        """Close from the X button. If confirming setup, behaves like
        "Not yet"."""
        if self.show_upi123_configuration_options:
            self.handle_upi123_configuration_confirmation(False)
            return
        self._cancel_upi123_delay()
        self.upi123_testing = False
        self.show_upi123_dialog = False
        self.show_upi123_configuration_options = False

    # -- confirmations ---------------------------------------------------------

    def handle_ussd_configuration_confirmation(self, configured: bool) -> None:
        self._cancel_ussd_timeout()
        self.show_ussd_configuration_options = False
        self.show_ussd_dialog = False
        self.ussd_testing = False
        if configured:
            setup_logic.set_user_reported_ussd_not_working(self._prefs, False)
            self.ussd_test_completed = True
            self.show_call_complete_button = True
            self._save_test_results(self.ussd_test_completed,
                                    self.upi123_test_completed)

    def handle_upi123_configuration_confirmation(self, configured: bool) -> None:
        self._cancel_upi123_delay()
        self.show_upi123_configuration_options = False
        self.show_upi123_dialog = False
        self.upi123_testing = False
        if configured:
            self.upi123_test_completed = True
            self.show_call_complete_button = True
            self._save_test_results(self.ussd_test_completed,
                                    self.upi123_test_completed)

    # -- results / navigation ------------------------------------------------

    def _save_test_results(self, ussd_completed: bool, upi123_completed: bool) -> None:
        from paynet.db.settings import TestResults
        self._test_results.save_test_results(
            TestResults(ussdEnabled=ussd_completed, upi123Enabled=upi123_completed))

    def get_test_results(self):
        return self._test_results.get_test_results()

    def skip_tests(self) -> None:
        self._save_test_results(self.ussd_test_completed, self.upi123_test_completed)
        self._prefs.put(constants.KEY_TEST_COMPLETED, True)
        self._navigate_to_main()

    def continue_to_main(self) -> None:
        self._save_test_results(self.ussd_test_completed, self.upi123_test_completed)
        self._prefs.put(constants.KEY_TEST_COMPLETED, True)
        self._navigate_to_main()

    def _ussd_waived(self) -> bool:
        return (not setup_logic.is_primary_sim_ussd_capable(self._prefs)
                or setup_logic.has_user_reported_ussd_not_working(self._prefs))

    def can_continue(self) -> bool:
        return (self.ussd_test_completed or self._ussd_waived()
                or self.upi123_test_completed)

    def all_tests_completed(self) -> bool:
        return ((self.ussd_test_completed or self._ussd_waived())
                and self.upi123_test_completed)

    def get_test_states(self) -> TestStates:
        return TestStates(
            ussdTesting=self.ussd_testing,
            showUssdDialog=self.show_ussd_dialog,
            ussdTestCompleted=self.ussd_test_completed,
            upi123Testing=self.upi123_testing,
            upi123TestCompleted=self.upi123_test_completed,
            voiceTesting=self.voice_testing,
            showVoiceDialog=self.show_voice_dialog,
            voiceTestCompleted=self.voice_test_completed,
            showCallCompleteButton=self.show_call_complete_button,
            ussdProgressMessage=self.ussd_progress_message,
            showUssdConfigurationOptions=self.show_ussd_configuration_options,
            showUpi123Dialog=self.show_upi123_dialog,
            showUpi123ConfigurationOptions=self.show_upi123_configuration_options,
        )


# ---------------------------------------------------------------------------
# helpers/MainActivityHelper.kt: the MainActivity readiness gates.
# ---------------------------------------------------------------------------


class MainActivityCallback:
    """Port of MainActivityHelper.UICallback (all no-op by default)."""

    def show_toast(self, message: str) -> None:
        pass

    def update_payment_state(self, payment_state) -> None:
        pass

    def navigate_to_setup(self) -> None:
        pass

    def navigate_to_test_configuration(self) -> None:
        pass

    def finish_activity(self) -> None:
        pass

    def show_overlay_permission_explanation(self) -> None:
        pass

    def launch_qr_scanner(self) -> None:
        pass

    def request_phone_permissions(self) -> None:
        pass


class MainActivityHelper:
    """Port of helpers/MainActivityHelper.kt.

    The transfer-initiation half also backs feature 10's TransferInitiator;
    this port keeps the Kotlin gate ORDER 1:1, including the permission legs
    (RECEIVE_SMS -> phone -> overlay) that feature 10 recorded as a
    device-only deviation. `has_permission` answers a runtime-permission
    read (default False = not granted, fail safe); `can_draw_overlays`
    answers Settings.canDrawOverlays; the session/detector/call/overlay
    wiring is injected and None on the desktop build."""

    def __init__(
        self,
        prefs,
        test_results,
        callback: MainActivityCallback,
        permission_manager: Optional[PermissionManager] = None,
        has_permission: Optional[Callable[[str], bool]] = None,
        can_draw_overlays: Optional[Callable[[], bool]] = None,
        session_manager=None,
        start_operation: Optional[Callable[..., None]] = None,
        place_upi123_call: Optional[Callable[[str, str], bool]] = None,
        show_overlay: Optional[Callable[[str, str], None]] = None,
        voice_sim_warning: Optional[Callable[[], None]] = None,
    ) -> None:
        self._prefs = prefs
        self._test_results = test_results
        self._callback = callback
        # Kotlin leaves the managers null until initialize(); the readiness
        # test never initializes, and `null?.hasPhonePermissions() != true`
        # routes to the permission request. None reproduces that exactly.
        self._permission_manager = permission_manager
        self._has_permission = has_permission or (lambda _p: False)
        self._can_draw_overlays = can_draw_overlays or (lambda: False)
        self._session_manager = session_manager
        self._start_operation = start_operation
        self._place_upi123_call = place_upi123_call
        self._show_overlay = show_overlay
        # DEVIATION: SubscriptionManager-bound, device-only, never blocks.
        self._voice_sim_warning = voice_sim_warning

    def initialize(self, permission_manager: PermissionManager) -> None:
        self._permission_manager = permission_manager

    # -- setup flags ---------------------------------------------------------

    def is_setup_completed(self) -> bool:
        return bool(self._prefs.get(constants.KEY_SETUP_COMPLETED, False))

    def is_test_completed(self) -> bool:
        return bool(self._prefs.get(constants.KEY_TEST_COMPLETED, False))

    # -- QR rail -----------------------------------------------------------

    def start_qr_scanning(self) -> None:
        blocked = setup_logic.get_scan_to_pay_blocked_message(self._prefs)
        if blocked is not None:
            self._callback.show_toast(blocked)
            return
        results = self._test_results.get_test_results()
        if not (results and results.ussdEnabled):
            self._callback.navigate_to_test_configuration()
            return
        # Phone permissions only (the camera is the scanner screen's own gate).
        if self._permission_manager is None or not self._permission_manager.has_phone_permissions():
            self._callback.show_toast(STR_REQUESTING_PERMISSIONS)
            self._callback.request_phone_permissions()
        else:
            self._callback.show_toast(STR_OPENING_SCANNER)
            self._callback.launch_qr_scanner()

    # -- transfer rail -------------------------------------------------------

    def _is_transfer_input_valid(self, phone_number: str, amount: str) -> bool:
        if not phone_number.strip() or not amount.strip():
            self._callback.show_toast(STR_ENTER_PHONE_AND_AMOUNT)
            return False
        from paynet.payment import validation
        if not validation.is_valid_phone_number(phone_number):
            self._callback.show_toast(STR_INVALID_PHONE)
            return False
        try:
            amount_value = float(amount)
        except ValueError:
            amount_value = None
        if amount_value is None or amount_value < constants.MIN_AMOUNT_VALUE:
            self._callback.show_toast(STR_INVALID_AMOUNT)
            return False
        if amount_value > constants.UPI123PAY_MAX_AMOUNT:
            # Same reason, same wording as the call-string builder raises
            # further down the path (Reason.AMOUNT_ABOVE_CAP).
            from paynet.payment.call_string import Reason
            from paynet.payment.messages import message_for
            self._callback.show_toast(message_for(Reason.AMOUNT_ABOVE_CAP))
            return False
        return True

    def can_initiate_transfer(self, phone_number: str, amount: str) -> bool:
        if not self._is_transfer_input_valid(phone_number, amount):
            return False
        results = self._test_results.get_test_results()
        if not (results and results.upi123Enabled):
            self._callback.navigate_to_test_configuration()
            return False
        if not self._has_permission(RECEIVE_SMS):
            self._callback.show_toast(STR_SMS_PERMISSION_EXPLANATION)
            self._callback.request_phone_permissions()
            return False
        if self._permission_manager is None or not self._permission_manager.has_phone_permissions():
            self._callback.show_toast(STR_PHONE_PERMISSION_REQUIRED)
            self._callback.request_phone_permissions()
            return False
        overlays_ok = (self._permission_manager.check_overlay_permission()
                       and self._can_draw_overlays())
        if not overlays_ok:
            self._callback.show_overlay_permission_explanation()
            return False
        return True

    def initiate_transfer(self, phone_number: str, amount: str,
                          recipient_name: Optional[str] = None):
        """Returns the new transaction id, or None when a gate refused."""
        if not self.can_initiate_transfer(phone_number, amount):
            return None
        if self._voice_sim_warning is not None:
            self._voice_sim_warning()
        if self._session_manager is None:
            self._callback.show_toast(STR_PAYMENT_NOT_STARTED)
            return None
        # The PENDING row is written before anything is dialled; a new
        # payment supersedes any session still in flight.
        transaction_id = self._session_manager.begin(
            phone_number, amount, recipient_name=recipient_name)
        if self._start_operation is not None:
            self._start_operation(operation_type="UPI_123",
                                  expected_amount=amount,
                                  phone_number=phone_number,
                                  session_txn_id=transaction_id)
        success = (self._place_upi123_call(phone_number, amount)
                   if self._place_upi123_call is not None else False)
        if success:
            if self._show_overlay is not None:
                self._show_overlay(phone_number, amount)
        else:
            self._session_manager.on_dial_failed("Could not start the payment call")
        return transaction_id


# ---------------------------------------------------------------------------
# TestConfigurationActivity: the screen.
# ---------------------------------------------------------------------------

from kivy.clock import Clock  # noqa: E402
from kivy.graphics import Color as KvColor  # noqa: E402
from kivy.graphics import Rectangle as KvRectangle  # noqa: E402
from kivy.graphics import RoundedRectangle  # noqa: E402
from kivy.metrics import dp  # noqa: E402
from kivy.uix.anchorlayout import AnchorLayout  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.floatlayout import FloatLayout  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402

from paynet import theme  # noqa: E402
from paynet.ui.home import Glyph  # noqa: E402
from paynet.ui.onboarding import (OnboardingDialog, OnboardingDialogAction,  # noqa: E402
                                  OnboardingDialogCopy, OnboardingPage)
from paynet.ui.prompts import ussd_progress_dialog, upi123_progress_dialog  # noqa: E402

TEST_SETUP_TITLE = "Set up payments"
TEST_SETUP_SUBTITLE = "Choose a method to set up on your bank-linked SIM."
TEST_SETUP_SCAN = "Scan and pay"
TEST_SETUP_CONTACT = "Pay a contact"
TEST_SETUP_JIO = "Unavailable on Jio"
TEST_SETUP_RETRY_SCAN = "Not set up. Tap to try again."
TEST_SETUP_USSD_SERVICE = "Set up with *99#"
TEST_SETUP_UPI_SERVICE = "Set up with UPI 123Pay"
TEST_SETUP_NOT_CHECKED = "Not checked"
TEST_SETUP_CHECKING = "Setting up…"
TEST_SETUP_READY = "Set up"
TEST_SETUP_UNAVAILABLE = "Unavailable"
TEST_SETUP_START_CALL = "Start setup call"
ACTION_CANCEL = "Cancel"
SCAN_CALL_TITLE = "Set up scan and pay?"
SCAN_CALL_MESSAGE = ("PayNet will call *99# using your phone's default calling "
                     "SIM. Make sure it's the SIM linked to your bank.\n\n"
                     "Your bank’s menu may take a few seconds to appear.")
CONTACT_CALL_TITLE = "Set up contact payments?"
CONTACT_CALL_MESSAGE = ("PayNet will call UPI 123Pay using your phone's "
                        "default calling SIM. Make sure it's the SIM linked "
                        "to your bank.")
CALL_PIN_NOTE = "Enter your UPI PIN only in your bank's prompts. PayNet never reads it."

STATE_POLL_S = 0.1  # the Compose 100 ms periodic state check


class PaymentMethodStatus(enum.Enum):
    NOT_CHECKED = "not_checked"
    CHECKING = "checking"
    READY = "ready"
    UNAVAILABLE = "unavailable"


_STATUS_TEXT = {
    PaymentMethodStatus.NOT_CHECKED: TEST_SETUP_NOT_CHECKED,
    PaymentMethodStatus.CHECKING: TEST_SETUP_CHECKING,
    PaymentMethodStatus.READY: TEST_SETUP_READY,
    PaymentMethodStatus.UNAVAILABLE: TEST_SETUP_UNAVAILABLE,
}


class PaymentMethodRow(BoxLayout):
    """PaymentMethodRow: 88dp-min row with a leading glyph, a title/service
    column and a trailing status accessory (ellipsis spinner while checking,
    check when ready, chevron otherwise, nothing when unavailable)."""

    def __init__(self, title, service, status, note=None, enabled=True,
                 glyph="›", on_press=None, accent=None, **kwargs):
        accent = accent or theme.VIOLET_ACCENT_THEME
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(88))
        super().__init__(**kwargs)
        self.padding = (dp(20), dp(18), dp(20), dp(18))
        self.spacing = dp(16)
        self.status = status
        self._on_press = on_press
        # Kotlin's `enabled` gates clicking only; colors carry the look.
        # (Not Widget.disabled: Kivy dims the whole subtree at 0.38 alpha.)
        self._row_enabled = enabled

        unavailable = status == PaymentMethodStatus.UNAVAILABLE
        icon_color = theme.TEXT_LIGHT_GRAY if unavailable else accent.accent
        self.add_widget(Glyph(glyph, icon_color, size_hint=(None, None),
                              size=(dp(24), dp(24)),
                              pos_hint={"center_y": 0.5}))

        column = BoxLayout(orientation="vertical", size_hint=(1, 1))
        title_color = theme.TEXT_LIGHT_GRAY if unavailable else (1, 1, 1, 1)
        self._title = Label(text=title, font_size="17sp", bold=True,
                            color=title_color, halign="left", valign="middle",
                            size_hint=(1, 1))
        self._title.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        column.add_widget(self._title)
        if status == PaymentMethodStatus.READY:
            service_text = TEST_SETUP_READY
        elif status == PaymentMethodStatus.CHECKING:
            service_text = TEST_SETUP_CHECKING
        else:
            service_text = service
        self._service = Label(text=service_text, font_size="13sp",
                              color=theme.TEXT_LIGHT_GRAY, halign="left",
                              valign="top", size_hint=(1, 1))
        self._service.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        column.add_widget(self._service)
        if note:
            self._note = Label(text=note, font_size="13sp",
                               color=theme.TEXT_LIGHT_GRAY, halign="left",
                               valign="top", size_hint=(1, 1))
            self._note.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
            column.add_widget(self._note)
        self.add_widget(column)

        # Trailing accessory: ellipsis spinner / check / chevron / nothing.
        if status == PaymentMethodStatus.CHECKING:
            self.add_widget(Label(text="…", font_size="20sp", color=accent.accent,
                                  size_hint=(None, 1), width=dp(24)))
        elif status == PaymentMethodStatus.READY:
            self.add_widget(Glyph("check", accent.accent,
                                  size_hint=(None, None), size=(dp(22), dp(22)),
                                  pos_hint={"center_y": 0.5}))
        elif status == PaymentMethodStatus.NOT_CHECKED:
            self.add_widget(Glyph("chevron_right", theme.TEXT_LIGHT_GRAY,
                                  size_hint=(None, None), size=(dp(20), dp(20)),
                                  pos_hint={"center_y": 0.5}))

    def on_touch_down(self, touch):
        if self._row_enabled and self.collide_point(*touch.pos):
            if self._on_press is not None:
                self._on_press()
            return True
        return super().on_touch_down(touch)


class TestConfigurationScreen(FloatLayout):
    """TestConfigurationScreen: black onboarding page with the two payment
    methods, the consent dialog before a real setup call, the setup progress
    dialogs, and an auto-advance to MainActivity once everything is ready.

    on_open_setup_review stands in for openSetupReview (SetupActivity in
    review mode); on_navigate_main for OnboardingFlow.afterPayments."""

    def __init__(self, helper: TestConfigurationHelper,
                 on_open_setup_review=lambda: None,
                 on_navigate_main=lambda: None,
                 accent=None, **kwargs):
        super().__init__(**kwargs)
        self._helper = helper
        self._on_open_setup_review = on_open_setup_review
        self._on_navigate_main = on_navigate_main
        self._accent = accent or theme.VIOLET_ACCENT_THEME
        self._pending_method: Optional[str] = None  # "scan" | "contact"
        self._advanced_to_main = False
        self._overlay = None

        self._page = OnboardingPage()
        self._page.add_content(self._build_content())
        self.add_widget(self._page)

        self._back = Glyph("back", self._accent.accent,
                           size_hint=(None, None), size=(dp(20), dp(20)))
        self._back.pos = (dp(14), self.height - dp(8) - dp(34))
        self._back_hit = Widget(size_hint=(None, None), size=(dp(48), dp(48)))
        self._back_hit.pos_hint = {"x": 0.01, "top": 0.99}
        self.add_widget(self._back)
        self.add_widget(self._back_hit)
        self.bind(height=lambda w, _: setattr(
            w._back, "pos", (dp(14), w.height - dp(8) - dp(34))))

        self._poll = Clock.schedule_interval(lambda *_: self._refresh(),
                                             STATE_POLL_S)
        self._refresh()

    # -- content ----------------------------------------------------------

    def _build_content(self):
        states = self._helper.get_test_states()
        is_jio = not setup_logic.is_primary_sim_ussd_capable(self._helper._prefs)
        user_reported = setup_logic.has_user_reported_ussd_not_working(
            self._helper._prefs)

        content = BoxLayout(orientation="vertical", size_hint=(1, None),
                            spacing=dp(32))
        content.bind(minimum_height=content.setter("height"))

        heading = BoxLayout(orientation="vertical", size_hint=(1, None),
                            spacing=dp(10))
        heading.bind(minimum_height=heading.setter("height"))
        icon = AnchorLayout(size_hint=(1, None), height=dp(48))
        icon.add_widget(Glyph("sim", self._accent.accent,
                              size_hint=(None, None), size=(dp(48), dp(48))))
        heading.add_widget(icon)
        title = Label(text=TEST_SETUP_TITLE, font_size="31sp", bold=True,
                      color=(1, 1, 1, 1), size_hint=(1, None), height=dp(40))
        heading.add_widget(title)
        subtitle = Label(text=TEST_SETUP_SUBTITLE, font_size="16sp",
                         color=theme.TEXT_LIGHT_GRAY, size_hint=(1, None))
        subtitle.line_height = 23 / 16
        subtitle.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        subtitle.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))
        heading.add_widget(subtitle)
        content.add_widget(heading)

        busy = self._busy(states)
        ussd_status = (PaymentMethodStatus.UNAVAILABLE if is_jio else
                       PaymentMethodStatus.CHECKING if states.ussdTesting else
                       PaymentMethodStatus.READY if states.ussdTestCompleted else
                       PaymentMethodStatus.NOT_CHECKED)
        ussd_note = (TEST_SETUP_RETRY_SCAN
                     if user_reported and not is_jio else None)
        self._ussd_row = PaymentMethodRow(
            TEST_SETUP_SCAN,
            TEST_SETUP_JIO if is_jio else TEST_SETUP_USSD_SERVICE,
            ussd_status, note=ussd_note,
            enabled=not busy and not is_jio and not states.ussdTestCompleted,
            glyph="qr", on_press=self._press_scan, accent=self._accent)
        upi_status = (PaymentMethodStatus.CHECKING if states.upi123Testing else
                      PaymentMethodStatus.READY if states.upi123TestCompleted else
                      PaymentMethodStatus.NOT_CHECKED)
        self._upi_row = PaymentMethodRow(
            TEST_SETUP_CONTACT, TEST_SETUP_UPI_SERVICE, upi_status,
            enabled=not busy and not states.upi123TestCompleted,
            glyph="person", on_press=self._press_contact, accent=self._accent)
        # The two rows sit inside one rounded surface card with an indented
        # divider, as in the Compose Column(clip + PayNetOnboardingSurface).
        card = FloatLayout(size_hint=(1, None))
        rows = BoxLayout(orientation="vertical", size_hint=(1, None))
        rows.bind(minimum_height=rows.setter("height"))
        divider = BoxLayout(size_hint=(1, None), height=dp(0.5))
        with divider.canvas.before:
            KvColor(1, 1, 1, 0.12)
            divider._bg = KvRectangle(pos=divider.pos, size=divider.size)
        divider.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                     size=lambda w, _: setattr(w._bg, "size", w.size))
        divider.padding = (dp(60), 0, 0, 0)
        rows.add_widget(self._ussd_row)
        rows.add_widget(divider)
        rows.add_widget(self._upi_row)
        with card.canvas.before:
            KvColor(rgba=theme.ONBOARDING_SURFACE)
            card._bg = RoundedRectangle(radius=[dp(20)])
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        rows.pos_hint = {"x": 0, "y": 0}
        card.add_widget(rows)
        rows.bind(height=lambda w, h: setattr(card, "height", h))
        card.height = dp(178)
        content.add_widget(card)
        self._content = content
        return content

    # -- state ------------------------------------------------------------

    def _busy(self, states: TestStates) -> bool:
        return (states.ussdTesting or states.upi123Testing
                or self._pending_method is not None
                or states.showUssdDialog or states.showUpi123Dialog
                or states.showUssdConfigurationOptions
                or states.showUpi123ConfigurationOptions)

    def _refresh(self, *_):
        states = self._helper.get_test_states()
        self._rebuild_rows(states)
        self._sync_overlay(states)
        if (self._helper.all_tests_completed() and not self._busy(states)
                and not self._advanced_to_main):
            self._advanced_to_main = True
            self._helper.continue_to_main()
            self._on_navigate_main()

    def _rebuild_rows(self, states):
        # The two rows depend on helper state; rebuild the content column
        # (cheaper than property-diffing two rows) but only when it changed.
        signature = (states.ussdTesting, states.ussdTestCompleted,
                     states.upi123Testing, states.upi123TestCompleted,
                     self._busy(states))
        if getattr(self, "_row_signature", None) == signature:
            return
        self._row_signature = signature
        self._page.clear_content()
        self._page.add_content(self._build_content())

    # -- presses ------------------------------------------------------------

    def _press_scan(self):
        states = self._helper.get_test_states()
        if not states.ussdTestCompleted and not states.ussdTesting:
            self._pending_method = "scan"
            self._refresh()

    def _press_contact(self):
        states = self._helper.get_test_states()
        if not states.upi123TestCompleted and not states.upi123Testing:
            self._pending_method = "contact"
            self._refresh()

    # -- overlays ----------------------------------------------------------

    def _sync_overlay(self, states):
        if self._overlay is not None:
            self.remove_widget(self._overlay)
            self._overlay = None
        if self._pending_method is not None:
            self._overlay = self._build_consent_dialog(self._pending_method)
        elif states.showUssdDialog or states.showUssdConfigurationOptions:
            dialog = ussd_progress_dialog(
                on_configured=lambda: self._confirm_ussd(True),
                on_not_configured=lambda: self._confirm_ussd(False),
                on_dismiss=lambda: self._dismiss_ussd(False),
                on_does_not_work=lambda: self._dismiss_ussd(True),
                progress_step=states.ussdProgressMessage)
            if states.showUssdConfigurationOptions:
                dialog.show_confirmation_options()
            self._overlay = dialog.build()
        elif states.showUpi123Dialog or states.showUpi123ConfigurationOptions:
            dialog = upi123_progress_dialog(
                on_configured=lambda: self._confirm_upi123(True),
                on_not_configured=lambda: self._confirm_upi123(False),
                on_dismiss=self._dismiss_upi123)
            if states.showUpi123ConfigurationOptions:
                dialog.show_confirmation_options()
            self._overlay = dialog.build()
        if self._overlay is not None:
            self._overlay.size = self.size
            self._overlay.pos = self.pos
            self.add_widget(self._overlay)

    def _build_consent_dialog(self, method):
        copy = OnboardingDialogCopy(
            title=SCAN_CALL_TITLE if method == "scan" else CONTACT_CALL_TITLE,
            message=(SCAN_CALL_MESSAGE if method == "scan"
                     else CONTACT_CALL_MESSAGE))
        dialog = OnboardingDialog(copy, on_dismiss=self._cancel_pending)
        note = Label(text=CALL_PIN_NOTE, font_size="14sp",
                     color=theme.TEXT_LIGHT_GRAY, halign="left",
                     size_hint=(1, None))
        note.line_height = 20 / 14
        note.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        note.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))
        dialog.add_content(note)

        def _start():
            chosen = self._pending_method
            self._pending_method = None
            if chosen == "scan":
                self._helper.ussd_testing = True
                self._helper.initiate_call(CallType.USSD)
            elif chosen == "contact":
                self._helper.upi123_testing = True
                self._helper.initiate_upi123_test()
            self._refresh()

        dialog.add_action(OnboardingDialogAction(TEST_SETUP_START_CALL, _start))
        dialog.add_action(OnboardingDialogAction(ACTION_CANCEL,
                                                 self._cancel_pending,
                                                 secondary=True))
        return dialog

    def _cancel_pending(self):
        self._pending_method = None
        self._refresh()

    def _confirm_ussd(self, configured):
        self._helper.handle_ussd_configuration_confirmation(configured)
        self._refresh()

    def _dismiss_ussd(self, does_not_work):
        self._helper.dismiss_ussd_dialog(from_does_not_work=does_not_work)
        self._refresh()

    def _confirm_upi123(self, configured):
        self._helper.handle_upi123_configuration_confirmation(configured)
        self._refresh()

    def _dismiss_upi123(self):
        self._helper.dismiss_upi123_dialog()
        self._refresh()

    # -- back --------------------------------------------------------------

    def on_touch_down(self, touch):
        if self._back_hit.collide_point(*touch.pos) and not self._busy(
                self._helper.get_test_states()):
            self._on_open_setup_review()
            return True
        return super().on_touch_down(touch)

    def on_destroy(self):
        if getattr(self, "_poll", None) is not None:
            self._poll.cancel()
            self._poll = None
        self._helper.cleanup()
