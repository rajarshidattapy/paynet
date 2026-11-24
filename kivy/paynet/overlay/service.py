# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/services/CallOverlayService.kt

"""The call overlay service orchestration, ported 1:1 with device seams
injected: the overlay host (window manager), overlay-permission check,
toasts, vibration and the scheduler are callables; the coordinator, session
manager, call manager and dialog manager are the already-ported modules.

DEVIATIONS (recorded in MIGRATION.md): the Android Service lifecycle
(onCreate/onStartCommand/onDestroy, binder, static serviceInstance) maps to
a plain object with create()/destroy(); the overlay renders inside the app
window instead of TYPE_APPLICATION_OVERLAY; vibration, overlay permission
and toasts are device-only injected callables.
"""

from paynet.overlay.logger import OverlayLogger
from paynet.overlay.view import (AUTH_NOTICE, CONNECTING, PIN_NOTICE,
                                 PROCESSING_PAYMENT, SENDING_REQUEST,
                                 CallOverlayMessageMotion, CallOverlayProgress,
                                 CallOverlayView)
from paynet.payment import state as payment_state_module
from paynet.telephony.coordinator import IdleState, OffHookState

TIMEOUT_DURATION_MS = 40000
TIMEOUT_EXTENSION_MS = 10000
MAX_TIMEOUT_EXTENSIONS = 3
STOP_DELAY_MS = 1000
VOLUME_LOWER_DELAY_MS = 2000
MAX_RETRIES = 3

OVERLAY_PERMISSION_TOAST = ("Overlay permission required for call protection. "
                            "Please grant permission in Settings.")
OVERLAY_ERROR_TOAST = "Failed to show call protection overlay. Please try again."
TERMINATE_FAILED_TOAST = ("Unable to end the call automatically. "
                          "Please hang up manually.")


class CallOverlayService:
    """Drives overlay content and result dialogs from the payment session.
    Duration heuristics never decide outcomes — the session does."""

    def __init__(self, coordinator=None, session_manager=None,
                 dialog_manager=None, call_manager=None, overlay_host=None,
                 overlay_permission=lambda: True, toast=lambda _msg: None,
                 vibrate=lambda: None, scheduler=None, stop_self=lambda: None,
                 logger=None, view_factory=CallOverlayView):
        self._coordinator = coordinator
        self._session = session_manager
        self._dialogs = dialog_manager
        self._calls = call_manager
        self._host = overlay_host
        self._overlay_permission = overlay_permission
        self._toast = toast
        self._vibrate = vibrate
        self._schedule = scheduler or _clock_scheduler
        self._stop_self = stop_self
        self._logger = logger or OverlayLogger(sink=lambda _line: None)
        self._view_factory = view_factory

        self.view = None
        self.is_overlay_active = False
        self.is_call_detected = False
        self.post_call_prompt_active = False
        self.pending_phone_number = ""
        self.pending_amount = ""
        self.timeout_extensions = 0
        self._timeout_cancelled = True
        self._retry_count = 0
        self._result_handled = False
        self._progress_pacing = None
        self._guidance_motion = None
        self._unsubscribes = []

    # -- lifecycle ------------------------------------------------------------

    def create(self):
        """onCreate: observe the single app-wide call-state authority and the
        payment session."""
        self._logger.log_service_event("SERVICE_CREATED")
        if self._coordinator is not None:
            self._coordinator.acquire("call-overlay-service")
            self._unsubscribes.append(
                self._coordinator.add_call_state_listener(self._on_call_state))
        if self._session is not None:
            self._unsubscribes.append(
                self._session.subscribe(self.on_payment_state_changed))

    def destroy(self):
        self._cancel_timeout()
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes = []
        if self._coordinator is not None:
            self._coordinator.release("call-overlay-service")
        self.hide_overlay_internal()
        self.is_call_detected = False

    # -- overlay show/hide ----------------------------------------------------

    def show_overlay_internal(self, phone_number, amount):
        """Reset for a new call and arm the 40s watchdog."""
        self._reset_service_state()
        self.pending_phone_number = phone_number
        self.pending_amount = amount
        self._start_timeout_timer()

    def _reset_service_state(self):
        self.is_overlay_active = False
        self.is_call_detected = False
        self.pending_phone_number = ""
        self.pending_amount = ""
        self._cancel_timeout()
        if self.view is not None:
            self._remove_view()

    # -- the 40s watchdog --------------------------------------------------------

    def _start_timeout_timer(self):
        self.timeout_extensions = 0
        self._timeout_cancelled = False
        self._schedule(self._on_timeout, TIMEOUT_DURATION_MS / 1000)

    def _cancel_timeout(self):
        self._timeout_cancelled = True

    def _on_timeout(self):
        """Before declaring "the call never started", consult the
        coordinator's live state: only a persistently Idle device cancels."""
        if self._timeout_cancelled:
            return
        give_up = True
        try:
            if self.is_call_detected:
                give_up = False
            else:
                device_busy = (self._coordinator is not None
                               and not isinstance(self._coordinator.call_state,
                                                  IdleState))
                if device_busy and self.timeout_extensions < MAX_TIMEOUT_EXTENSIONS:
                    self.timeout_extensions += 1
                    self._schedule(self._on_timeout, TIMEOUT_EXTENSION_MS / 1000)
                    give_up = False
        except Exception:
            # Never crash the main loop mid-payment; give up cleanly.
            give_up = True
        if give_up:
            if self._session is not None:
                self._session.on_call_never_started()
            self.hide_overlay_internal()
            self._stop_self()

    # -- call detection ----------------------------------------------------------

    def _on_call_state(self, state):
        if isinstance(state, OffHookState):
            self.on_call_detected()
        elif isinstance(state, IdleState) and self.is_call_detected:
            if self._calls is not None:
                self._calls.restore_call_volume()
            self.hide_overlay_internal()

    def on_call_detected(self):
        if self.post_call_prompt_active:
            return  # The bank callback must not reopen the in-call guide.
        self._logger.log_call_detection(self.pending_phone_number, "CALL_DETECTED")
        if not self.is_call_detected:
            self.is_call_detected = True
        elif self.is_overlay_active:
            return  # Duplicate detection.
        if not self.pending_phone_number or not self.pending_amount:
            return  # Missing pending payment data.
        self._cancel_timeout()
        self._show_overlay_with_retry(self.pending_phone_number,
                                      self.pending_amount)

    def _show_overlay_with_retry(self, phone_number, amount):
        try:
            self._create_system_overlay(phone_number, amount)
            self._retry_count = 0
        except Exception:
            if self._retry_count < MAX_RETRIES:
                self._retry_count += 1
                self._schedule(
                    lambda: self._show_overlay_with_retry(phone_number, amount),
                    (1000 * self._retry_count) / 1000)
            else:
                self._toast(OVERLAY_ERROR_TOAST)

    def _create_system_overlay(self, phone_number, amount):
        if not self._overlay_permission():
            self._logger.log_permission_event("SYSTEM_ALERT_WINDOW", False,
                                              "overlay_creation")
            self._toast(OVERLAY_PERMISSION_TOAST)
            return
        self._logger.log_permission_event("SYSTEM_ALERT_WINDOW", True,
                                          "overlay_creation")
        view = self._view_factory(on_terminate=self.handle_terminate_call)
        view.bind_details(phone_number, amount)
        self.view = view
        if self._host is not None:
            self._host.add_view(view)
        self.is_overlay_active = True
        self._logger.log_overlay_state("CREATED", True)

        self._progress_pacing = CallOverlayProgress(view)
        self._progress_pacing.show_connecting()
        view.update_status(PROCESSING_PAYMENT, CONNECTING)
        if (self._session is not None
                and isinstance(self._session.payment_state,
                               payment_state_module.InProgress)):
            self.on_payment_state_changed(self._session.payment_state)

        # Lower the IVR call volume once the call is active; reveal the pill
        # only if it actually worked, so the overlay never claims otherwise.
        def lower_volume():
            lowered = (self._calls.set_call_volume_to_minimum()
                       if self._calls is not None else False)
            if lowered and self.view is not None:
                self.view.show_muted_indicator()
        self._schedule(lower_volume, VOLUME_LOWER_DELAY_MS / 1000)

    def _remove_view(self):
        if self._host is not None and self.view is not None:
            self._host.remove_view(self.view)
        self.view = None

    def hide_overlay_internal(self):
        self._cancel_progress_pacing()
        if not self.is_overlay_active or self.view is None:
            return
        self._remove_view()
        self.is_overlay_active = False

    # -- payment-state driven results ---------------------------------------------

    def on_payment_state_changed(self, state):
        self._cancel_progress_pacing()
        dialogs = self._dialogs
        if isinstance(state, payment_state_module.InProgress):
            if self.view is not None:
                self.view.update_status(PROCESSING_PAYMENT, SENDING_REQUEST)
            self._start_in_call_pacing()
        elif isinstance(state, payment_state_module.WaitingForVerification):
            self._finish_with_result(lambda: None)
        elif isinstance(state, payment_state_module.Success):
            self._vibrate()
            self._end_call_on_confirmation()
            self._finish_with_result(lambda: None)
        elif isinstance(state, payment_state_module.Failed):
            self._end_call_on_confirmation()
            self._finish_with_result(
                lambda: dialogs and dialogs.show_transaction_failed())
        elif isinstance(state, payment_state_module.NeedsReview):
            self._end_call_on_confirmation()
            self._finish_with_result(lambda: None)
        elif isinstance(state, payment_state_module.Cancelled):
            by_user = "by user" in (state.reason or "").lower()
            self._finish_with_result(
                lambda: dialogs and (
                    dialogs.show_transaction_cancelled_by_user() if by_user
                    else dialogs.show_transaction_cancelled()))
        elif isinstance(state, payment_state_module.Timeout):
            # No payment to report: the row is discarded and nothing is shown.
            self._finish_with_result(lambda: None)

    def _end_call_on_confirmation(self):
        if self._calls is not None:
            try:
                self._calls.terminate_call()
            except Exception:
                pass

    def _finish_with_result(self, show_dialog):
        """Hide the overlay, show the result surface once, wind down."""
        if self._result_handled:
            return
        self._result_handled = True
        if self._calls is not None:
            self._calls.restore_call_volume()
        self.hide_overlay_internal()
        show_dialog()
        self._schedule(self._stop_self, STOP_DELAY_MS / 1000)

    def _start_in_call_pacing(self):
        if self.view is None:
            return
        self._progress_pacing = CallOverlayProgress(self.view)
        self._progress_pacing.show_in_call()
        self._guidance_motion = CallOverlayMessageMotion(self.view.step_text)
        self.view.schedule_bank_guidance(self._guidance_motion)

    def _cancel_progress_pacing(self):
        if self._guidance_motion is not None:
            self._guidance_motion.stop()
            self._guidance_motion = None
        if self._progress_pacing is not None:
            self._progress_pacing.stop()
            self._progress_pacing = None

    # -- terminate button -----------------------------------------------------------

    def handle_terminate_call(self):
        """Mark the session cancelled FIRST and unconditionally; audio/telecom
        cleanup is best-effort and must never prevent the cancellation."""
        if self._session is not None:
            self._session.on_user_cancelled()
        try:
            if self._calls is not None:
                self._calls.restore_call_volume()
                if not self._calls.terminate_call():
                    self._toast(TERMINATE_FAILED_TOAST)
            if self._session is None:
                self.hide_overlay_internal()
                if self._dialogs is not None:
                    self._dialogs.show_transaction_cancelled_by_user()
                self._schedule(self._stop_self, STOP_DELAY_MS / 1000)
        except Exception:
            self.hide_overlay_internal()
            self._schedule(self._stop_self, STOP_DELAY_MS / 1000)


def _clock_scheduler(callback, delay_s):
    from kivy.clock import Clock
    Clock.schedule_once(lambda *_: callback(), delay_s)
