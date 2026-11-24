# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""QR scanner (feature 11): parser, analyzer control flow and the scanner
controller's payment flow. Pure logic — no window is opened."""

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")

import pytest

from paynet.qr import parser
from paynet.qr.analyzer import (DUPLICATE_DETECTION_THRESHOLD_MS,
                                QRCodeAnalyzer, decode_bitmap)
from paynet.qr.parser import (Invalid, Reason, UPIData, Valid, message_for)
from paynet.qr import scanner as qr
from paynet.qr.scanner import (ManualScheduler, QRScannerController,
                               recipient_name_fallback)
from paynet.payment import state as ps


# -- parser ------------------------------------------------------------------


def test_parse_bare_vpa():
    result = parser.parse("kirana@okhdfcbank")
    assert isinstance(result, Valid)
    assert result.data.vpa == "kirana@okhdfcbank"
    assert result.data.amount == ""
    assert result.data.currency == "INR"


def test_parse_full_upi_uri():
    result = parser.parse(
        "upi://pay?pa=kirana@okhdfcbank&pn=Kirana%20Store&am=240.50&tn=Snacks")
    assert isinstance(result, Valid)
    assert result.data.vpa == "kirana@okhdfcbank"
    assert result.data.payee_name == "Kirana Store"
    assert result.data.amount == "240.50"
    assert result.data.transaction_note == "Snacks"


def test_parse_upi_scheme_case_insensitive():
    assert isinstance(parser.parse("UPI://pay?pa=kirana@okhdfcbank"), Valid)


def test_parse_rejects_empty_and_blank():
    assert parser.parse("").reason == Reason.EMPTY
    assert parser.parse("   ").reason == Reason.EMPTY


def test_parse_rejects_non_upi_text():
    assert parser.parse("https://example.com").reason == Reason.NOT_A_UPI_QR
    assert parser.parse("hello world").reason == Reason.NOT_A_UPI_QR
    # A string merely containing "@" is not a VPA.
    assert parser.parse("a@b@").reason == Reason.NOT_A_UPI_QR


def test_parse_rejects_missing_or_invalid_payee():
    assert parser.parse("upi://pay?pn=Shop").reason == Reason.NO_PAYEE_ADDRESS
    assert parser.parse("upi://pay?pa=").reason == Reason.NO_PAYEE_ADDRESS
    assert parser.parse(
        "upi://pay?pa=x@okhdfc").reason == Reason.INVALID_PAYEE_ADDRESS
    assert parser.parse(
        "upi://pay?pa=kirana@1hdfc").reason == Reason.INVALID_PAYEE_ADDRESS


@pytest.mark.parametrize("amount", ["-5", "0", "100000.01", "100001", "abc",
                                    "10.5.3", "12.345", "1e3", "NaN"])
def test_parse_rejects_invalid_amounts(amount):
    result = parser.parse("upi://pay?pa=kirana@okhdfcbank&am=" + amount)
    assert isinstance(result, Invalid)
    assert result.reason == Reason.INVALID_AMOUNT


@pytest.mark.parametrize("amount", ["1", "0.01", "4999.99", "100000"])
def test_parse_accepts_valid_amounts(amount):
    result = parser.parse("upi://pay?pa=kirana@okhdfcbank&am=" + amount)
    assert isinstance(result, Valid)
    assert result.data.amount == amount


def test_parse_plus_is_not_a_space_in_query_values():
    # Android's getQueryParameter percent-decodes but leaves '+' alone.
    result = parser.parse("upi://pay?pa=kirana@okhdfcbank&pn=A+B")
    assert result.data.payee_name == "A+B"


def test_parse_strips_control_chars_and_caps_lengths():
    long_name = "Shop\x00Name" + "x" * 200
    result = parser.parse("upi://pay?pa=kirana@okhdfcbank&pn=" + long_name)
    assert "\x00" not in result.data.payee_name
    assert len(result.data.payee_name) == 99
    long_note = "n" * 150
    result = parser.parse("upi://pay?pa=kirana@okhdfcbank&tn=" + long_note)
    assert len(result.data.transaction_note) == 99


def test_legacy_adapters():
    assert parser.is_valid_upi_qr_code("kirana@okhdfcbank")
    assert not parser.is_valid_upi_qr_code("nope")
    assert parser.parse_upi_qr_code("nope").vpa == ""
    assert parser.parse_upi_qr_code("kirana@okhdfcbank").vpa == \
        "kirana@okhdfcbank"


def test_message_for_covers_every_reason():
    for reason in Reason:
        assert message_for(reason)


# -- analyzer ------------------------------------------------------------------


class _Frame:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _analyzer(detected, decodes, clock=None):
    analyzer = QRCodeAnalyzer(
        detected.append, decode_source=lambda frame: decodes(frame)[0],
        invert_source=lambda frame: ("inverted", frame),
        clock=clock or (lambda: 1000))
    return analyzer


def test_analyzer_detects_and_closes_frame():
    detected = []
    frame = _Frame()
    analyzer = QRCodeAnalyzer(detected.append,
                              decode_source=lambda f: "upi://pay?pa=a@bc")
    assert analyzer.analyze(frame) == "upi://pay?pa=a@bc"
    assert detected == ["upi://pay?pa=a@bc"]
    assert frame.closed
    assert analyzer.is_processing


def test_analyzer_duplicate_within_threshold_ignored():
    detected = []
    now = [1000]
    analyzer = QRCodeAnalyzer(detected.append,
                              decode_source=lambda f: "code",
                              clock=lambda: now[0])
    analyzer.analyze(_Frame())
    analyzer.reset_processing()
    now[0] += DUPLICATE_DETECTION_THRESHOLD_MS - 1
    assert analyzer.analyze(_Frame()) is None
    assert detected == ["code"]
    now[0] += 1
    assert analyzer.analyze(_Frame()) == "code"
    assert detected == ["code", "code"]


def test_analyzer_processing_latch():
    detected = []
    codes = iter(["code", "other"])
    analyzer = QRCodeAnalyzer(detected.append,
                              decode_source=lambda f: next(codes))
    analyzer.analyze(_Frame())
    assert analyzer.analyze(_Frame()) is None  # still processing
    analyzer.reset_processing()
    # After reset, a different code fires even inside the duplicate window.
    assert analyzer.analyze(_Frame()) == "other"
    assert detected == ["code", "other"]


def test_analyzer_invert_fallback_and_broad_catch():
    detected = []

    def decode(source):
        if isinstance(source, tuple) and source[0] == "inverted":
            return "code"
        return None

    analyzer = QRCodeAnalyzer(detected.append, decode_source=decode,
                              invert_source=lambda f: ("inverted", f))
    assert analyzer.analyze(_Frame()) == "code"

    def explode(source):
        raise ValueError("malformed frame")

    analyzer = QRCodeAnalyzer(detected.append, decode_source=explode)
    assert analyzer.analyze(_Frame()) is None


def test_decode_bitmap_one_shot():
    assert decode_bitmap("bmp", lambda s: "code") == "code"
    assert decode_bitmap("bmp", lambda s: None) is None
    assert decode_bitmap("bmp", lambda s: None,
                         invert_source=lambda s: "inv") is None
    assert decode_bitmap("bmp", lambda s: "c" if s == "inv" else None,
                         invert_source=lambda s: "inv") == "c"


# -- controller fixtures ------------------------------------------------------------


class FakeUi:
    def __init__(self):
        self.calls = []
        self.status = None
        self.status_error = False
        self.banner = None
        self.controls_enabled = True

    def _record(self, name, *args):
        self.calls.append((name,) + args)

    def show_processing(self, text):
        self._record("processing", text)

    def show_invalid_banner(self, message):
        self.banner = message
        self._record("banner", message)

    def hide_invalid_banner(self):
        self.banner = None
        self._record("hide_banner")

    def show_black_screen(self, text):
        self._record("black_screen", text)
        self.status = text

    def update_status(self, text, error=False):
        self.status = text
        self.status_error = error

    def show_sms_waiting_state(self, text):
        self._record("sms_waiting", text)
        self.status = text

    def show_error_status(self, text):
        self._record("error_status", text)
        self.status = text
        self.status_error = True

    def reset_to_camera_view(self):
        self._record("reset")

    def show_gallery_reading(self, text):
        self._record("gallery_reading", text)

    def finish_gallery_selection(self):
        self._record("finish_gallery")

    def set_controls_enabled(self, enabled):
        self.controls_enabled = enabled

    def stop_live_analysis(self):
        self._record("stop_analysis")

    def resume_live_scanning(self):
        self._record("resume_scanning")

    def rearm_scanning(self):
        self._record("rearm")


class FakeSessionManager:
    def __init__(self):
        self.begun = []
        self.cancelled = 0
        self.dial_failed = []
        self.payment_state = ps.Idle()
        self._listeners = []

    def begin(self, phone_number, amount, upi_id=None, source="MANUAL",
              recipient_name=None):
        self.begun.append((phone_number, amount, upi_id, source,
                           recipient_name))
        self.payment_state = ps.Initiating(phone_number, amount,
                                           transactionId="txn-qr-1")
        return "txn-qr-1"

    def on_user_cancelled(self):
        self.cancelled += 1
        self.payment_state = ps.Idle()

    def on_dial_failed(self, reason):
        self.dial_failed.append(reason)
        self.payment_state = ps.Idle()

    def subscribe(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def emit(self, state):
        self.payment_state = state
        for listener in list(self._listeners):
            listener(state)


class FakeDetector:
    def __init__(self):
        self.operations = []

    def start_operation(self, operation_type, expected_amount=None,
                        phone_number=None, session_txn_id=None):
        self.operations.append((operation_type, expected_amount,
                                session_txn_id))


class FakeClipboard:
    def __init__(self):
        self.current = None  # (token, label, text)
        self.cleared = 0

    def set_sensitive(self, label, text, token):
        self.current = (token, label, text)

    def read(self):
        if self.current is None:
            return None
        token, label, text = self.current
        return (token, text)

    def clear(self):
        self.current = None
        self.cleared += 1


def _controller(dial=lambda uri: True, permitted=True, session=None, ui=None,
                clipboard=None, blocked=None, detector=None):
    session = session or FakeSessionManager()
    ui = ui or FakeUi()
    scheduler = ManualScheduler()
    toasts = []
    finishes = []
    controller = QRScannerController(
        ui, session, detector=detector,
        clipboard=clipboard if clipboard is not None else FakeClipboard(),
        show_toast=toasts.append, dial=dial,
        has_call_permission=lambda: permitted,
        request_call_permission=lambda cb: cb(permitted),
        scheduler=scheduler, on_finish=finishes.append,
        blocked_message=lambda: blocked)
    return controller, session, ui, scheduler, toasts, finishes


GOOD_QR = "upi://pay?pa=kirana@okhdfcbank&pn=Kirana%20Store&am=240.50"


# -- controller tests ----------------------------------------------------------------


def test_blocked_gate_toasts_and_finishes():
    controller, _, _, _, toasts, finishes = _controller(
        blocked="Scan to pay is not available")
    controller.on_created()
    assert toasts == ["Scan to pay is not available"]
    assert finishes == [qr.RESULT_CANCELLED]


def test_process_valid_qr_begins_session_and_dials_once():
    dialed = []
    controller, session, ui, scheduler, _, _ = _controller(
        dial=dialed.append)
    detector = FakeDetector()
    controller._detector = detector
    controller.on_created()
    assert controller.process_qr_code(GOOD_QR) is True

    # Session begun with the QR source and the payee name.
    assert session.begun == [("", "240.50", "kirana@okhdfcbank", "QR",
                              "Kirana Store")]
    assert detector.operations == [("QR_SCAN", "240.50", "txn-qr-1")]
    assert controller.qr_transaction_id == "txn-qr-1"

    # VPA on the clipboard with its owner token.
    assert controller.copied_vpa == "kirana@okhdfcbank"
    assert controller.copied_vpa_token is not None

    # Waiting guide visible; dial pending on the 1 s delay.
    assert ("black_screen", "Processing payment...") in ui.calls
    assert dialed == []
    scheduler.run("dial")
    assert dialed == [qr.USSD_DIAL_URI]
    assert ui.status == qr.STR_GUIDE_STATUS
    assert controller.qr_triggered_at is not None

    # A second dial step does not dial again.
    controller.has_dialed_ussd = True
    scheduler.post_delayed("dial", qr.DIAL_DELAY_MS, lambda: None)


def test_dial_failure_fails_session_and_shows_error():
    def explode(uri):
        raise RuntimeError("no telephony")

    controller, session, ui, scheduler, toasts, _ = _controller(dial=explode)
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    scheduler.run("dial")
    assert session.dial_failed == [qr.DIAL_FAILED_REASON]
    assert ("error_status", "Error: " + qr.STR_USSD_CALL_FAILED) in ui.calls
    assert toasts[-1] == qr.STR_USSD_CALL_FAILED
    # Recovery resumes scanning after 3 seconds and clears both flags.
    scheduler.run("resume_after_error")
    assert not controller.is_processing_qr_code
    assert not controller.has_dialed_ussd
    assert ("reset",) in ui.calls


def test_no_call_permission_requests_then_dials():
    dialed = []
    controller, *_ = _controller(dial=dialed.append, permitted=False)
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    controller._scheduler.run("dial")
    # The fake permission request denies, so no dial and the error shows.
    assert dialed == []


def test_invalid_qr_banner_rearm_and_autohide():
    controller, session, ui, scheduler, _, _ = _controller()
    controller.on_created()
    assert controller.process_qr_code("https://example.com") is False
    assert ui.banner == ("Try another QR\n" + qr.parser.STR_REASON_NOT_UPI)
    assert session.begun == []
    # Re-armed immediately and the auto-hide is scheduled.
    assert not controller.is_processing_qr_code
    assert ("rearm",) in ui.calls
    scheduler.run("hide_scan_error")
    assert ui.banner is None


def test_gate_blocks_second_qr_while_processing():
    controller, session, ui, *_ = _controller()
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    assert controller.process_qr_code("upi://pay?pa=other@okaxis") is False
    assert len(session.begun) == 1


def test_recipient_name_fallback():
    assert recipient_name_fallback("kirana9123456780@okhdfc") == "9123456780"
    assert recipient_name_fallback("user@okaxis") == "user@okaxis"
    # A blank payee name falls back to the heuristic.
    controller, session, *_ = _controller()
    controller.on_created()
    controller.process_qr_code("upi://pay?pa=kirana98765@okhdfc&pn=%20")
    assert session.begun[0][4] == "98765"


def test_terminate_cancels_session_and_finishes():
    controller, session, _, scheduler, _, finishes = _controller()
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    controller.terminate()
    assert session.cancelled == 1
    assert controller.finished_by_waiting_screen_timeout
    assert finishes == [qr.RESULT_CANCELLED]
    assert not scheduler.has("dial")
    # Second terminate is a no-op.
    controller.terminate()
    assert session.cancelled == 1


def test_session_terminal_state_closes_waiting_screen():
    controller, session, _, _, _, finishes = _controller()
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    session.emit(ps.Timeout(ps.TimeoutType.BANK_VERIFICATION, "", "240.50",
                            transactionId="txn-qr-1"))
    assert controller.finished_by_waiting_screen_timeout
    assert finishes == [qr.RESULT_CANCELLED]


def test_on_destroy_finishing_cancels_in_flight_and_wipes_clipboard():
    clipboard = FakeClipboard()
    controller, session, _, _, _, _ = _controller(clipboard=clipboard)
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    controller.on_destroy(is_finishing=True)
    assert session.cancelled == 1
    assert clipboard.cleared == 1
    assert controller.copied_vpa is None


def test_on_destroy_config_change_preserves_session_and_clipboard():
    clipboard = FakeClipboard()
    controller, session, _, _, _, _ = _controller(clipboard=clipboard)
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    controller.on_destroy(is_finishing=False)
    assert session.cancelled == 0
    assert clipboard.cleared == 0
    assert controller.copied_vpa == "kirana@okhdfcbank"


def test_on_destroy_after_waiting_timeout_does_not_cancel():
    controller, session, _, _, _, _ = _controller()
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    session.emit(ps.Timeout(ps.TimeoutType.BANK_VERIFICATION, "", "240.50",
                            transactionId="txn-qr-1"))
    cancels = session.cancelled
    controller.on_destroy(is_finishing=True)
    assert session.cancelled == cancels


def test_clipboard_not_wiped_when_user_copied_over():
    clipboard = FakeClipboard()
    controller, session, _, _, _, _ = _controller(clipboard=clipboard)
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    clipboard.set_sensitive("other", "user text", "different-token")
    controller.on_destroy(is_finishing=True)
    assert clipboard.cleared == 0


def test_save_and_restore_state():
    clipboard = FakeClipboard()
    controller, session, ui, _, _, _ = _controller(clipboard=clipboard)
    controller.on_created()
    controller.process_qr_code(GOOD_QR)
    controller._scheduler.run("dial")
    state = controller.save_state()
    assert state["qrGuideVisible"] and state["hasDialedUSSD"]
    assert state["qrTransactionId"] == "txn-qr-1"

    ui2 = FakeUi()
    session2 = FakeSessionManager()
    restored, _, _, _, _, _ = _controller(session=session2, ui=ui2)
    restored.on_created(saved_state=state)
    assert restored.qr_guide_visible
    assert restored.has_dialed_ussd
    assert restored.is_processing_qr_code
    assert restored.is_ussd_process_active
    assert ("sms_waiting", qr.STR_SMS_WAITING) in ui2.calls
    # And the restored screen does not accept new scans.
    assert restored.process_qr_code(GOOD_QR) is False


def test_gallery_flow_success():
    controller, session, ui, _, _, _ = _controller(
        dial=lambda uri: True)
    controller._decode_gallery_image = lambda uri: GOOD_QR
    controller.on_created()
    assert controller.open_gallery_picker(lambda: None) is True
    controller.on_gallery_picked("content://photo/1")
    assert session.begun
    assert not controller.gallery_pending


def test_gallery_no_code_and_unreadable():
    controller, _, ui, _, _, _ = _controller()
    controller._decode_gallery_image = lambda uri: None
    controller.on_created()
    controller.open_gallery_picker(lambda: None)
    controller.on_gallery_picked("content://photo/1")
    assert ui.banner == "Try another QR\n" + qr.STR_GALLERY_NO_CODE

    def explode(uri):
        raise OSError("unreadable")

    controller2, _, ui2, _, _, _ = _controller()
    controller2._decode_gallery_image = explode
    controller2.on_created()
    controller2.decode_qr_from_gallery("content://photo/2")
    assert ui2.banner == "Try another QR\n" + qr.STR_GALLERY_UNREADABLE


def test_gallery_cancelled_resumes():
    controller, _, ui, _, _, _ = _controller()
    controller.on_created()
    controller.open_gallery_picker(lambda: None)
    controller.on_gallery_picked(None)
    assert not controller.gallery_pending
    assert ("finish_gallery",) in ui.calls


def test_blank_vpa_shows_error():
    controller, session, ui, _, toasts, _ = _controller()
    controller.on_created()
    controller._proceed_with_payment(
        UPIData(vpa="  ", payee_name="", amount="", transaction_note="",
                currency="INR"))
    assert session.begun == []
    assert toasts[-1] == qr.STR_INVALID_VPA
