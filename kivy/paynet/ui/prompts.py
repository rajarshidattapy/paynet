# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from ui/dialogs/{UssdProgressDialog,Upi123ProgressDialog}.kt,
# managers/TransactionDialogManager.kt and
# ui/components/{PaymentPromptLayout,PaymentAnswerButton,SmsPermissionNotice}.kt

"""Payment prompts and transaction dialogs, built on the feature-12
OnboardingDialog scaffold.

DEVIATIONS (recorded in MIGRATION.md): the 3-second shortcut reveal uses
Kivy Clock instead of a LaunchedEffect; overlay window typing and
BadToken/SecurityException handling are Android window-manager concerns
with no Kivy equivalent (the dialogs are plain widgets here); actual SMS /
notification permission requests are device-only and injected.
"""

from typing import Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout

from paynet.ui.onboarding import (
    OnboardingDialog, OnboardingDialogAction, OnboardingDialogCopy,
    OnboardingDialogProgress, onboarding_confirmation_actions)

SHORTCUT_REVEAL_SECONDS = 3
PROMPT_MAX_WIDTH_DP = 380
PROMPT_HORIZONTAL_INSET_DP = 48
DISABLED_ALPHA = 0.5

USSD_PROGRESS_TITLE = "Set up scan and pay"
USSD_PROGRESS_MESSAGE = ("Your bank’s menu may take a few seconds to appear. "
                         "Follow the *99# setup instructions, then return here.")
USSD_CONFIRM_TITLE = "Is scan and pay set up?"
USSD_CONFIRM_MESSAGE = ("Confirm only after you finish your bank’s *99# setup "
                        "instructions.")
UPI123_PROGRESS_TITLE = "Set up contact payments"
UPI123_PROGRESS_MESSAGE = "Complete setup on the UPI 123Pay call, then end the call."
UPI123_CONFIRM_TITLE = "Are contact payments set up?"
UPI123_CONFIRM_MESSAGE = ("Confirm only after you finish your bank’s UPI 123Pay "
                          "setup instructions.")
CONTACT_WAITING = "Waiting for setup"
ALREADY_READY = "It's already set up"
DOES_NOT_WORK = "It isn't working"
INITIALIZING = "Initializing…"

CANCELLED_TITLE = "Transaction Cancelled"
CANCELLED_MESSAGE = ("The call ended before the payment flow could complete. "
                     "No payment was processed.")
CANCELLED_BY_USER_MESSAGE = "The transaction was cancelled. No payment was processed."
FAILED_TITLE = "Transaction Failed"
FAILED_MESSAGE = ("Your bank reported the payment as failed. Any debited amount "
                  "is normally reversed automatically — check your bank if it "
                  "isn't.")
AWAITING_TITLE = "Request Sent"
AWAITING_MESSAGE = ("Complete any bank callback, then return to PayNet to "
                    "record your answer.")
OK = "OK"
GOT_IT = "Got it"
TOAST_PAYMENT_CANCELLED = "Payment cancelled. No payment was processed."
TOAST_PAYMENT_FAILED = "Your bank reported the payment as failed."
TOAST_AWAITING = "Return to PayNet to record the outcome."

SMS_PERMISSION_TITLE = "Bank payment confirmations"
SMS_PERMISSION_EXPLANATION = ("Allow incoming SMS to detect your bank’s payment "
                              "result during an active payment attempt. PayNet "
                              "never reads your inbox. Messages are processed on "
                              "this device. Without this permission, automatic "
                              "confirmation is unavailable.")
SMS_PERMISSION_ALLOW = "Continue"
SMS_PERMISSION_LATER = "Not now"

PAYMENT_CALLBACK_TITLE = "Watch for a bank call"
PAYMENT_CALLBACK_BODY = ("Your bank may call you next. Answer, press 1 to "
                         "confirm and enter your UPI PIN in the call.")
PAYMENT_CALLBACK_LATER = "Not now"
PAYMENT_OUTCOME_TITLE = "Payment successful?"
PAYMENT_OUTCOME_HINT = "Check your bank if you’re unsure."
PAYMENT_ANSWER_LATER = "Not sure"


class _SetupDialog:
    """Shared behavior of UssdProgressDialog / Upi123ProgressDialog: while a
    *99# or UPI 123Pay setup runs elsewhere the bank side may already be
    ready, so after 3 s a shortcut appears; a wrong outcome reveals the
    confirmation actions instead (showConfigurationOptions). Not a widget:
    .build() returns the dialog to display; state stays inspectable here."""

    def __init__(self, progress_title, progress_message, confirm_title,
                 confirm_message, progress_step, show_does_not_work=False,
                 on_configured=None, on_not_configured=None,
                 on_dismiss=None, on_does_not_work=None):
        self._titles = (progress_title, progress_message, confirm_title,
                        confirm_message, progress_step)
        self._show_does_not_work = show_does_not_work
        self._on_configured = on_configured or (lambda: None)
        self._on_not_configured = on_not_configured or (lambda: None)
        self._on_dismiss = on_dismiss or (lambda: None)
        self._on_does_not_work = on_does_not_work or (lambda: None)
        self.showing_confirmation = False
        self.shortcuts_revealed = False
        self._reveal_event = Clock.schedule_once(
            lambda *_: self._reveal_shortcuts(), SHORTCUT_REVEAL_SECONDS)

    def _reveal_shortcuts(self):
        self.shortcuts_revealed = True

    def show_confirmation_options(self):
        """The user says the flow went wrong: swap guidance for a
        confirm-or-not pair, matching showConfigurationOptions=true."""
        self.showing_confirmation = True
        self._reveal_event.cancel()

    def build(self) -> OnboardingDialog:
        progress, progress_message, confirm, confirm_message, step = self._titles
        confirming = self.showing_confirmation
        dialog = OnboardingDialog(
            OnboardingDialogCopy(
                title=confirm if confirming else progress,
                message=confirm_message if confirming else progress_message),
            on_dismiss=self._on_dismiss)
        if not confirming:
            dialog.add_content(OnboardingDialogProgress(step))
        if confirming:
            for action in onboarding_confirmation_actions(self._on_configured,
                                                          self._on_not_configured):
                dialog.add_action(action)
        elif self.shortcuts_revealed:
            dialog.add_action(OnboardingDialogAction(ALREADY_READY, self._on_configured))
            if self._show_does_not_work:
                dialog.add_action(OnboardingDialogAction(
                    DOES_NOT_WORK, self._on_does_not_work, secondary=True))
        return dialog


def ussd_progress_dialog(on_configured=None, on_not_configured=None,
                         on_dismiss=None, on_does_not_work=None) -> _SetupDialog:
    return _SetupDialog(USSD_PROGRESS_TITLE, USSD_PROGRESS_MESSAGE,
                        USSD_CONFIRM_TITLE, USSD_CONFIRM_MESSAGE,
                        INITIALIZING, show_does_not_work=True,
                        on_configured=on_configured,
                        on_not_configured=on_not_configured,
                        on_dismiss=on_dismiss,
                        on_does_not_work=on_does_not_work)


def upi123_progress_dialog(on_configured=None, on_not_configured=None,
                           on_dismiss=None) -> _SetupDialog:
    return _SetupDialog(UPI123_PROGRESS_TITLE, UPI123_PROGRESS_MESSAGE,
                        UPI123_CONFIRM_TITLE, UPI123_CONFIRM_MESSAGE,
                        CONTACT_WAITING,
                        on_configured=on_configured,
                        on_not_configured=on_not_configured,
                        on_dismiss=on_dismiss)


class TransactionDialogManager:
    """Transaction outcome alerts keyed off the payment session. on_any_dismiss
    fires whenever the user dismisses a result dialog so the caller can
    acknowledge the session. If building the dialog itself fails (the
    injected factory raising), fall back to the toast and still acknowledge —
    except show_awaiting_confirmation, which never acknowledges in the Kotlin
    original."""

    def __init__(self, dialog_factory=None, toast=None, on_any_dismiss=None):
        self._dialog_factory = dialog_factory or _default_dialog_factory
        self._toast = toast or (lambda _message: None)
        self._on_any_dismiss = on_any_dismiss
        self.shown = []

    def _dismissed(self):
        if self._on_any_dismiss is not None:
            self._on_any_dismiss()

    def _show(self, title, message, button, fallback_toast, acknowledge=True):
        try:
            dialog = self._dialog_factory(
                title, message, button,
                on_dismiss=self._dismissed if acknowledge else None)
            self.shown.append(dialog)
        except Exception:
            self._toast(fallback_toast)
            if acknowledge:
                self._dismissed()

    def show_transaction_cancelled(self):
        self._show(CANCELLED_TITLE, CANCELLED_MESSAGE, OK,
                   TOAST_PAYMENT_CANCELLED)

    def show_transaction_cancelled_by_user(self):
        self._show(CANCELLED_TITLE, CANCELLED_BY_USER_MESSAGE, OK,
                   TOAST_PAYMENT_CANCELLED)

    def show_transaction_failed(self):
        self._show(FAILED_TITLE, FAILED_MESSAGE, OK, TOAST_PAYMENT_FAILED)

    def show_awaiting_confirmation(self):
        self._show(AWAITING_TITLE, AWAITING_MESSAGE, GOT_IT,
                   TOAST_AWAITING, acknowledge=False)


def _default_dialog_factory(title, message, button, on_dismiss=None):
    dialog = OnboardingDialog(OnboardingDialogCopy(title=title, message=message),
                              on_dismiss=on_dismiss or (lambda: None))
    dialog.add_action(OnboardingDialogAction(
        button, on_dismiss or (lambda: None)))
    return dialog


class PaymentAnswerButton(OnboardingDialogAction):
    """PaymentAnswerButton: an icon+label group that still behaves like a
    button; the Kivy action already is one."""

    def __init__(self, glyph, label, on_release, **kwargs):
        super().__init__(label, on_release, **kwargs)
        self.glyph_kind = glyph


class PaymentPrompt:
    """PaymentPromptLayout: window construction only; session ownership and
    timing stay with the caller. `notice=True` is the bank callback notice
    (no answers); otherwise the outcome question with yes/no answers.
    matches() decides whether the already-shown prompt is the right one."""

    def __init__(self, notice=False, on_answer=None, on_later=None):
        self.notice = notice
        self._on_answer = on_answer or (lambda _yes: None)
        self._on_later = on_later or (lambda: None)
        self.saving = False
        self.answers = []

    def build(self) -> OnboardingDialog:
        dialog = OnboardingDialog(
            OnboardingDialogCopy(
                title=PAYMENT_CALLBACK_TITLE if self.notice else PAYMENT_OUTCOME_TITLE,
                message=(PAYMENT_CALLBACK_BODY if self.notice
                         else PAYMENT_OUTCOME_HINT)),
            on_dismiss=self._on_later)
        if not self.notice:
            for glyph, label, yes in (("check", "Yes", True), ("close", "No", False)):
                action = PaymentAnswerButton(
                    glyph, label,
                    (lambda yes=yes: self._on_answer(yes)),
                    secondary=not yes)
                self.answers.append(action)
                dialog.add_action(action)
        later = OnboardingDialogAction(
            PAYMENT_CALLBACK_LATER if self.notice else PAYMENT_ANSWER_LATER,
            self._on_later, secondary=True)
        self.answers.append(later)
        dialog.add_action(later)
        self._dialog = dialog
        return dialog

    def set_saving(self, saving: bool):
        """While an answer persists, answers and later disable at half alpha."""
        self.saving = saving
        for action in self.answers:
            action.disabled = saving
            action.opacity = DISABLED_ALPHA if saving else 1.0

    def matches(self, key: str, displayed_key: Optional[str],
                showing: bool = True) -> bool:
        return showing and displayed_key == key

    @staticmethod
    def width_for(window_width_px: float, density: float = 1.0) -> float:
        """min(window - 48dp, 380dp) from PaymentPromptLayout.size."""
        return min(window_width_px - PROMPT_HORIZONTAL_INSET_DP * density,
                   PROMPT_MAX_WIDTH_DP * density)


class SmsPermissionNotice:
    """Explains the limited SMS access before Android asks for consent. The
    permission request itself is device-only: `permission_granted()` and
    `request_permissions()` are injected."""

    def __init__(self, permission_granted=lambda: False,
                 request_permissions=lambda: None):
        self._permission_granted = permission_granted
        self._request_permissions = request_permissions
        self.dismissed = False
        self.requested = False

    def build(self) -> Optional[OnboardingDialog]:
        """No dialog when permission is already granted or once dismissed."""
        if self._permission_granted() or self.dismissed:
            return None
        dialog = OnboardingDialog(
            OnboardingDialogCopy(title=SMS_PERMISSION_TITLE,
                                 message=SMS_PERMISSION_EXPLANATION),
            on_dismiss=self._dismiss)
        dialog.add_action(OnboardingDialogAction(
            SMS_PERMISSION_ALLOW, self._allow))
        dialog.add_action(OnboardingDialogAction(
            SMS_PERMISSION_LATER, self._dismiss, secondary=True))
        return dialog

    def _allow(self):
        self.requested = True
        self._request_permissions()
        self._dismiss()

    def _dismiss(self):
        self.dismissed = True
