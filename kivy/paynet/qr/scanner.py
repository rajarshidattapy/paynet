# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""QR scanner flow controller — 1:1 port of the payment-flow logic of
features/qr_scanner/presentation/QRScannerActivity.kt, with every Android
effect (camera, torch, clipboard, dialer, toasts, Handler, finish) injected
so the flow is fully testable from the desktop.

Ported exactly: the canAcceptLiveQr gate, parse-then-proceed handoff, the
QR payment session begin (TransactionSource.QR + recipient-name fallback),
the operation window start, the sensitive VPA clipboard copy/wipe with its
owner token, the dial-once guard and 1 s dial delay, the CALL_PHONE
permission round-trip, the invalid-QR banner with its 3.5 s auto-hide and
immediate re-arm, the 3 s error recovery that resets every flag, the
terminate path, the finish-vs-config-change onDestroy cancellation
semantics, the gallery pick/decode/consume flow, and the session-state
watcher that closes the waiting screen without ending the payment.

Not ported (dead in the Kotlin): the revealQrAnswers runnable is only ever
cancelled, never posted — the old 150 s waiting-screen timer was removed —
and qrOutcomePanel is only ever hidden. Camera preview, torch, the photo
picker and the actual USSD dial are device-only and recorded as such in
MIGRATION.md.
"""

import time
import uuid

from paynet.qr import parser
from paynet.qr.parser import Invalid, Valid, message_for
from paynet.payment.state import should_close_qr_waiting_screen
from paynet.status import SOURCE_QR

# Activity result codes.
RESULT_CANCELLED = 0
RESULT_SUCCESS = 1
RESULT_ERROR = 2

# How long the invalid-QR banner stays up before fading out.
SCAN_ERROR_VISIBLE_MS = 3500
# Delay before the USSD dial so the overlay is ready.
DIAL_DELAY_MS = 1000
# Delay before the instructions card expands into the step list.
INSTRUCTIONS_EXPAND_DELAY_MS = 4000
# Delay before scanning resumes after an error.
ERROR_RESUME_MS = 3000

USSD_CODE = "*99*1*3#"
# Intent data built by dialUSSD: '#' percent-encoded inside a tel: URI.
USSD_DIAL_URI = "tel:" + USSD_CODE.replace("#", "%23")

# strings.xml copy.
STR_PROCESSING_QR = "Processing QR code…"
STR_PROCESSING_PAYMENT = "Processing payment..."
STR_INVALID_TITLE = "Try another QR"
STR_ERROR_PREFIX = "Error: %1$s"
STR_INVALID_VPA = "That is not a valid UPI QR code."
STR_QR_PROCESSING_ERROR = "Could not read that QR code. Please try again."
STR_INITIATING_CALL = "Calling your bank…"
STR_CALL_INITIATED = "Call started"
STR_GUIDE_STATUS = "Complete the payment in your bank’s menu."
STR_SMS_WAITING = "Waiting for your bank’s confirmation message"
STR_USSD_CALL_FAILED = "Could not start the USSD call."
STR_CALL_PERMISSION_REQUIRED = (
    "Phone call permission is required for USSD payments.")
STR_UNEXPECTED = "Something went wrong. Please try again."
STR_GALLERY_READING = "Reading QR…"
STR_GALLERY_NO_CODE = "No QR code found in that image"
STR_GALLERY_UNREADABLE = "That image could not be opened"

DIAL_FAILED_REASON = "Could not start the payment call"


def recipient_name_fallback(vpa: str) -> str:
    """The QR rail has no contact name; the receiver label is the longest
    digit run in the VPA's local part (many merchant VPAs embed the phone
    number), falling back to the whole VPA."""
    import re

    local = vpa.split("@")[0]
    runs = re.findall(r"[0-9]+", local)
    if not runs:
        return vpa
    return max(runs, key=len)


class ManualScheduler:
    """Handler(Looper.getMainLooper()) port: keyed postDelayed so a newer
    post replaces an older one, plus cancel/cancelAll. The Kivy UI supplies
    the same interface over Clock; tests drive it manually."""

    def __init__(self):
        self._tasks = {}

    def post_delayed(self, key, delay_ms, fn):
        self._tasks[key] = (delay_ms, fn)

    def cancel(self, key):
        self._tasks.pop(key, None)

    def cancel_all(self):
        self._tasks.clear()

    def has(self, key):
        return key in self._tasks

    def run(self, key):
        _, fn = self._tasks.pop(key)
        fn()


class QRScannerController:
    """UI-agnostic owner of the scanner's payment state. The screen
    implements the ui hooks; every platform effect is a constructor
    injection."""

    def __init__(self, ui, session_manager, detector=None, clipboard=None,
                 show_toast=None, dial=None,
                 has_call_permission=lambda: False,
                 request_call_permission=None,
                 scheduler=None, on_finish=None,
                 blocked_message=lambda: None, clock=None,
                 decode_gallery_image=None):
        self._ui = ui
        self._session_manager = session_manager
        self._detector = detector
        self._clipboard = clipboard
        self._toast = show_toast or (lambda message: None)
        self._dial = dial
        self._has_call_permission = has_call_permission
        self._request_call_permission = (
            request_call_permission or (lambda on_result: on_result(False)))
        self._scheduler = scheduler or ManualScheduler()
        self._finish = on_finish or (lambda result: None)
        self._blocked_message = blocked_message
        self._clock = clock or (lambda: int(time.monotonic() * 1000))
        self._decode_gallery_image = decode_gallery_image
        self._unsubscribe = None

        # State fields mirror the activity's.
        self.scanner_resumed = True
        self.is_processing_qr_code = False
        self.has_dialed_ussd = False
        self.is_ussd_process_active = False
        self.finished_by_waiting_screen_timeout = False
        self.copied_vpa_token = None
        self.copied_vpa = None
        self.qr_transaction_id = None
        self.qr_guide_visible = False
        self.qr_triggered_at = None
        self.qr_answer_saving = False
        self.gallery_pending = False
        self.gallery_uri = None
        self.gallery_decode_active = False

    # ---- lifecycle ----------------------------------------------------------

    def on_created(self, saved_state=None):
        """onCreate: subscribe to session state, apply the scan-to-pay gate,
        restore or start fresh."""
        self._unsubscribe = self._session_manager.subscribe(
            self._on_session_state)
        blocked = self._blocked_message()
        if blocked is not None:
            self._toast(blocked)
            self._finish(RESULT_CANCELLED)
            return
        if saved_state:
            self.qr_transaction_id = saved_state.get("qrTransactionId")
            self.copied_vpa_token = saved_state.get("copiedVpaToken")
            self.copied_vpa = saved_state.get("copiedVpa")
            if saved_state.get("qrGuideVisible"):
                self.has_dialed_ussd = saved_state.get("hasDialedUSSD", False)
                triggered = saved_state.get("qrTriggeredAt", -1)
                self.qr_triggered_at = triggered if triggered >= 0 else None
                self.is_processing_qr_code = True
                self.is_ussd_process_active = self.qr_triggered_at is not None
                self.qr_guide_visible = True
                self._ui.show_black_screen(STR_GUIDE_STATUS)
                self._ui.show_sms_waiting_state(STR_SMS_WAITING)
            else:
                self.gallery_pending = saved_state.get("galleryPending",
                                                       False)
                self.gallery_uri = saved_state.get("galleryUri")
                if self.gallery_pending:
                    self._ui.set_controls_enabled(False)

    def save_state(self):
        state = {
            "galleryPending": self.gallery_pending,
            "galleryUri": self.gallery_uri,
            "qrTransactionId": self.qr_transaction_id,
            "qrGuideVisible": self.qr_guide_visible,
            "hasDialedUSSD": self.has_dialed_ussd,
            "copiedVpaToken": self.copied_vpa_token,
            "copiedVpa": self.copied_vpa,
        }
        if self.qr_triggered_at is not None:
            state["qrTriggeredAt"] = self.qr_triggered_at
        return state

    def on_pause(self):
        # Do NOT reset is_processing_qr_code here: when the user goes to the
        # dialer we pause; if we reset the flag, on_resume would re-attach
        # the analyzer and dial again in a loop. It is reset only in
        # on_destroy or in show_error when resuming scanning.
        self.scanner_resumed = False
        self._ui.stop_live_analysis()

    def on_resume(self):
        self.scanner_resumed = True
        if self.qr_guide_visible:
            self._ui.show_sms_waiting_state(STR_SMS_WAITING)
        self._ui.resume_live_scanning()

    def on_destroy(self, is_finishing):
        self.scanner_resumed = False
        self._scheduler.cancel_all()
        self._ui.stop_live_analysis()
        self.is_ussd_process_active = False
        self.is_processing_qr_code = False
        self.has_dialed_ussd = False
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

        # Leaving this screen with a payment still in flight (system back,
        # close button) cancels the session, so the confirmation window
        # closes with it and the next scan isn't refused as "already in
        # progress". A no-op once the session reached a terminal state, and
        # is_finishing keeps a config change from cancelling a live
        # payment. finished_by_waiting_screen_timeout excludes the one exit
        # that is NOT the user abandoning anything: the session-state
        # watcher giving the screen back while the payment is legitimately
        # in flight.
        if is_finishing and not self.finished_by_waiting_screen_timeout:
            manager = self._session_manager
            if (manager.payment_state.get_transaction_id()
                    == self.qr_transaction_id):
                manager.on_user_cancelled()

        # A configuration change must preserve the VPA until this flow
        # actually ends.
        if is_finishing:
            self.clear_vpa_clipboard()

    def _on_session_state(self, state):
        # A deadline ends the waiting UI without asserting a bank outcome or
        # closing the SMS grace window.
        if should_close_qr_waiting_screen(self.qr_transaction_id, state):
            self.finished_by_waiting_screen_timeout = True
            self._finish(RESULT_CANCELLED)

    # ---- gates --------------------------------------------------------------

    def has_payment_in_progress(self):
        return self.is_processing_qr_code or self.qr_guide_visible

    def can_accept_live_qr(self):
        return (self.scanner_resumed and not self.gallery_pending
                and not self.has_payment_in_progress())

    # ---- scan flow ------------------------------------------------------------

    def process_qr_code(self, qr_code):
        """Camera callbacks and picker results share this entry point."""
        # Already processing a QR — a second decode must not dial again.
        if not self.can_accept_live_qr():
            return False

        self.is_processing_qr_code = True
        self._ui.show_processing(STR_PROCESSING_QR)

        # A code that isn't a usable UPI QR is a normal, expected thing to
        # point a scanner at — it must not be treated like a payment
        # failure, and the parser's specific reason is far more useful to
        # the user than a generic "invalid".
        try:
            result = parser.parse(qr_code)
            if isinstance(result, Valid):
                self._proceed_with_payment(result.data)
                return True
            self.show_invalid_qr_code(message_for(result.reason))
            return False
        except Exception:
            self.show_error(STR_QR_PROCESSING_ERROR)
            # Reset processing flag on error.
            self.is_processing_qr_code = False
            return False

    def _proceed_with_payment(self, upi_data):
        """initiateUSSDPayment: always proceed — no amount dialog. The VPA
        is copied to the clipboard and USSD is dialed instantly."""
        self._ui.stop_live_analysis()

        if not upi_data.vpa.strip():
            self.show_error(STR_INVALID_VPA)
            return

        if not self._begin_qr_payment_session(upi_data):
            return

        self.qr_guide_visible = True
        self._ui.show_black_screen(STR_PROCESSING_PAYMENT)
        self._copy_vpa_to_clipboard(upi_data.vpa)

        def dial_step():
            if self.has_dialed_ussd:
                # USSD is dialed once per payment flow — without this,
                # returning from the dialer re-triggers the dial and loops.
                return
            self.has_dialed_ussd = True
            self._ui.update_status(STR_INITIATING_CALL)
            self.dial_ussd()

        self._scheduler.post_delayed("dial", DIAL_DELAY_MS, dial_step)

    def _begin_qr_payment_session(self, upi_data):
        name = (upi_data.payee_name if upi_data.payee_name.strip()
                else recipient_name_fallback(upi_data.vpa))
        txn_id = self._session_manager.begin(
            phone_number="", amount=upi_data.amount, upi_id=upi_data.vpa,
            source=SOURCE_QR, recipient_name=name)
        if txn_id is not None and self._detector is not None:
            self._detector.start_operation(
                operation_type="QR_SCAN", expected_amount=upi_data.amount,
                session_txn_id=txn_id)
        self.qr_transaction_id = txn_id
        return txn_id is not None

    def dial_ussd(self):
        # Check CALL_PHONE permission before dialing.
        if not self._has_call_permission():
            self._request_call_permission(
                lambda granted: self.dial_ussd() if granted
                else self.show_error(STR_CALL_PERMISSION_REQUIRED))
            return
        try:
            self._ui.update_status(STR_CALL_INITIATED)
            if self._dial is None:
                raise RuntimeError("telephony is device-only in this build")
            self._dial(USSD_DIAL_URI)
            self._start_ussd_process_messages()
        except Exception:
            # Without this, the confirmation window keeps listening for a
            # payment that never happened and could adopt an unrelated
            # confirmation.
            self._session_manager.on_dial_failed(DIAL_FAILED_REASON)
            self.show_error(STR_USSD_CALL_FAILED)

    def _start_ussd_process_messages(self):
        self.is_ussd_process_active = True
        if self.qr_triggered_at is None:
            self.qr_triggered_at = self._clock()
        # Honest, static status. PayNet cannot see the USSD menu or the
        # bank's progress, so it does not fake step-by-step progress — it
        # states what the user should do and what it is genuinely waiting
        # for. The bank-message pipeline owns the result; call state never
        # implies success.
        self._ui.show_sms_waiting_state(STR_SMS_WAITING)
        self._ui.update_status(STR_GUIDE_STATUS)

    # ---- clipboard ------------------------------------------------------------

    def _copy_vpa_to_clipboard(self, vpa):
        """Copies the payee VPA to the clipboard so the user can paste it
        into the USSD menu. Flagged sensitive so it stays out of clipboard
        previews; clear_vpa_clipboard wipes it when the flow ends."""
        if self._clipboard is None:
            return
        token = uuid.uuid4().hex
        try:
            self._clipboard.set_sensitive("VPA", vpa, token)
            self.copied_vpa_token = token
            self.copied_vpa = vpa
        except Exception:
            # Not critical — the flow can continue without the copy.
            pass

    def clear_vpa_clipboard(self):
        """Clears the payee VPA so it doesn't linger for other apps. A later
        copy belongs to the user, even if its text happens to match our
        VPA."""
        token = self.copied_vpa_token
        if token is None:
            return
        try:
            current = self._clipboard.read()
            if (current is not None and current[0] == token
                    and current[1] == self.copied_vpa):
                self._clipboard.clear()
        except Exception:
            pass
        finally:
            self.copied_vpa_token = None
            self.copied_vpa = None

    # ---- feedback states --------------------------------------------------------

    def show_invalid_qr_code(self, reason_message):
        """A scanned code that isn't a usable UPI QR. This is NOT an error
        state: the camera keeps running, the banner explains what was
        wrong, and scanning re-arms so the user can just aim at another
        code."""
        self._ui.show_invalid_banner(
            "%s\n%s" % (STR_INVALID_TITLE, reason_message))
        # Re-arm immediately: the next frame holding a good QR should be
        # accepted even while the banner is still on screen.
        self.is_processing_qr_code = False
        self._ui.rearm_scanning()
        self._scheduler.cancel("hide_scan_error")
        self._scheduler.post_delayed("hide_scan_error", SCAN_ERROR_VISIBLE_MS,
                                     self._ui.hide_invalid_banner)

    def show_error(self, message):
        self._ui.show_error_status(STR_ERROR_PREFIX.replace("%1$s", message))
        self._toast(message)
        self._scheduler.post_delayed("resume_after_error", ERROR_RESUME_MS,
                                     self._resume_after_error)

    def _resume_after_error(self):
        # Resuming after an error: clear both the processing and dialed
        # flags.
        self.qr_guide_visible = False
        self.qr_triggered_at = None
        self.is_processing_qr_code = False
        self.has_dialed_ussd = False
        self._ui.reset_to_camera_view()

    # ---- buttons ----------------------------------------------------------------

    def back(self):
        self._finish(RESULT_CANCELLED)

    def terminate(self):
        if self.qr_answer_saving:
            return
        self.qr_answer_saving = True
        self._scheduler.cancel_all()
        if self.qr_transaction_id is not None:
            self._session_manager.on_user_cancelled()
        self.finished_by_waiting_screen_timeout = True
        self._finish(RESULT_CANCELLED)

    # ---- gallery ------------------------------------------------------------------

    def open_gallery_picker(self, launch_picker):
        """Reserve the input before launching the picker, including during
        its transition. launch_picker() raises when the picker cannot
        open."""
        if (not self.scanner_resumed or self.gallery_pending
                or self.has_payment_in_progress()):
            return False
        self.gallery_pending = True
        self._ui.stop_live_analysis()
        self._ui.set_controls_enabled(False)
        try:
            launch_picker()
        except Exception:
            self.finish_gallery_selection()
            self.show_invalid_qr_code(STR_GALLERY_UNREADABLE)
        return True

    def on_gallery_picked(self, uri):
        """The picker returns a one-shot read grant for the single image the
        user chose, so the app never gains access to the gallery as a
        whole."""
        if uri is None:
            self.finish_gallery_selection()
        else:
            self.decode_qr_from_gallery(uri)

    def finish_gallery_selection(self):
        self.gallery_pending = False
        self.gallery_uri = None
        self._ui.set_controls_enabled(True)
        self._ui.finish_gallery_selection()

    def decode_qr_from_gallery(self, uri):
        if self.has_payment_in_progress() or self.gallery_decode_active:
            return
        self.gallery_pending = True
        self.gallery_uri = uri
        self.gallery_decode_active = True
        self._ui.stop_live_analysis()
        self._ui.set_controls_enabled(False)
        self._ui.hide_invalid_banner()
        self._ui.show_gallery_reading(STR_GALLERY_READING)
        try:
            decoded = self._decode_gallery_image(uri)
            failed = False
        except Exception:
            decoded = None
            failed = True
        finally:
            self.gallery_decode_active = False
        # Do not briefly reattach the live analyzer between gallery decode
        # and processing: the explicitly chosen image owns this handoff.
        self.gallery_pending = False
        self.gallery_uri = None
        self._ui.set_controls_enabled(True)
        if failed:
            self.show_invalid_qr_code(STR_GALLERY_UNREADABLE)
        elif decoded is None:
            self.show_invalid_qr_code(STR_GALLERY_NO_CODE)
        else:
            self.process_qr_code(decoded)
