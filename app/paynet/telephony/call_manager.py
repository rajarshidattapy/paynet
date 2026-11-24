# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/managers/CallManager.kt

"""Call placement, call-state tracking and call audio management.

DEVIATION: every Android service (dialer intents, TelephonyManager.listen,
AudioManager, TelecomManager, Toast, permission checks) sits behind the
PhonePlatform protocol; the pyjnius implementation ships with packaging
(feature 17) and is UNVERIFIED from desktop (see MIGRATION.md). What ports
1:1 is the decision and state logic: permission gates, the atomic USSD
double-dial guard, listener lifecycle and failure rollback, audio
mute/restore with stored-original semantics (ONLY the voice-call stream —
silencing a user's alarm during a 35s payment call is real-world harm),
and terminate_call's honest False without ANSWER_PHONE_CALLS.

GUARDRAIL: this code is never executed against a real dialer from the
migration environment — tests drive a fake platform only.
"""

from __future__ import annotations

import enum
import logging
import threading
from typing import Callable, Optional, Protocol

from ..constants import DEFAULT_UPI_SERVICE_NUMBER
from ..payment import call_string
from ..payment.messages import message_for

log = logging.getLogger("CallManager")

# android.telephony.TelephonyManager constants.
CALL_STATE_IDLE = 0
CALL_STATE_RINGING = 1
CALL_STATE_OFFHOOK = 2

# android.media.AudioManager constants.
MODE_NORMAL = 0
MODE_IN_CALL = 2
STREAM_VOICE_CALL = 0
FLAG_SHOW_UI = 1

PERMISSION_CALL_PHONE = "android.permission.CALL_PHONE"
PERMISSION_ANSWER_PHONE_CALLS = "android.permission.ANSWER_PHONE_CALLS"


class CallType(enum.Enum):
    USSD = "USSD"
    VOICE = "VOICE"
    UPI123 = "UPI123"
    MANUAL_TRANSFER = "MANUAL_TRANSFER"


class PhonePlatform(Protocol):
    """The Android surface CallManager needs. Faked in tests."""

    def has_permission(self, permission: str) -> bool:
        ...

    def start_call(self, uri: str) -> None:
        """ACTION_CALL intent. Raises on failure (dialer missing, revoked)."""
        ...

    def listen_call_state(self, listener: Callable[[int], None]) -> None:
        ...

    def unlisten_call_state(self, listener: Callable[[int], None]) -> None:
        ...

    def get_call_state(self) -> int:
        ...

    def get_stream_volume(self, stream: int) -> int:
        ...

    def set_stream_volume(self, stream: int, volume: int, flags: int) -> None:
        ...

    def get_mode(self) -> int:
        ...

    def set_mode(self, mode: int) -> None:
        ...

    def set_microphone_mute(self, muted: bool) -> None:
        ...

    def set_speakerphone_on(self, on: bool) -> None:
        ...

    def telecom_end_call(self) -> bool:
        ...

    def toast(self, message: str) -> None:
        ...


class CallManager:
    def __init__(self, platform: PhonePlatform) -> None:
        self._platform = platform
        self._original_call_volume = 0
        self._previous_audio_mode = MODE_NORMAL
        self._is_audio_muted = False

        self._is_call_in_progress = False
        self._current_call_type: Optional[CallType] = None
        self._on_call_ended: Optional[Callable[[CallType], None]] = None
        self._on_ussd_complete: Optional[Callable[[], None]] = None
        self._listener: Optional[Callable[[int], None]] = None

        # One lock per concern, mirroring the Kotlin synchronization objects.
        self._audio_lock = threading.RLock()
        self._call_state_lock = threading.RLock()
        self._callback_lock = threading.RLock()
        self._listener_lock = threading.RLock()

        # AtomicBoolean: check-and-set must be one step.
        self._ussd_dial_pending = False
        self._ussd_pending_lock = threading.Lock()

    # ---- calls ------------------------------------------------------------

    def initiate_call(
        self,
        phone_number: str,
        call_type: CallType,
        on_call_ended: Callable[[CallType], None],
        on_ussd_complete: Optional[Callable[[], None]] = None,
    ) -> None:
        if not self._platform.has_permission(PERMISSION_CALL_PHONE):
            log.error("CALL_PHONE permission not granted")
            return

        if call_type is CallType.USSD:
            self._handle_ussd_call(phone_number, on_ussd_complete)
            return

        with self._call_state_lock:
            self._current_call_type = call_type
            with self._callback_lock:
                self._on_call_ended = on_call_ended
            self._is_call_in_progress = True

        with self._listener_lock:
            self._listener = self._create_call_state_listener()
            self._platform.listen_call_state(self._listener)

        try:
            self._platform.start_call(f"tel:{phone_number}")
            log.debug("Call initiated: %s", call_type)
        except Exception:
            log.exception("Failed to initiate call")
            with self._call_state_lock:
                self._is_call_in_progress = False
                self._current_call_type = None
                self._clear_callbacks()
            self._unregister_listener()

    def _handle_ussd_call(
        self, ussd_code: str, on_ussd_complete: Optional[Callable[[], None]]
    ) -> None:
        # Prevent double-dial at the call-manager level (atomic check-and-set).
        with self._ussd_pending_lock:
            if self._ussd_dial_pending:
                log.warning("USSD dial already pending, ignoring duplicate")
                return
            self._ussd_dial_pending = True

        with self._callback_lock:
            self._on_ussd_complete = on_ussd_complete
        self._is_call_in_progress = True
        self._current_call_type = CallType.USSD

        log.debug("Starting USSD call: %s", ussd_code)

        def on_ended(call_type: CallType) -> None:
            if call_type is CallType.USSD:
                with self._ussd_pending_lock:
                    self._ussd_dial_pending = False
                with self._call_state_lock:
                    self._is_call_in_progress = False
                    self._current_call_type = None
                    callback = self._get_ussd_complete_callback()
                    if callback is not None:
                        callback()
                    self._clear_callbacks()

        with self._listener_lock:
            self._listener = self._create_call_state_listener(on_ended=on_ended)
            self._platform.listen_call_state(self._listener)

        # URL-encode the USSD code to preserve special characters like #.
        from urllib.parse import quote

        encoded = quote(ussd_code, safe="")
        try:
            self._platform.start_call(f"tel:{encoded}")
            log.debug("USSD call initiated: %s", ussd_code)
        except Exception:
            log.exception("Failed to initiate USSD call")
            with self._ussd_pending_lock:
                self._ussd_dial_pending = False
            with self._call_state_lock:
                self._is_call_in_progress = False
                self._current_call_type = None
                callback = self._get_ussd_complete_callback()
                if callback is not None:
                    callback()
                self._clear_callbacks()
            self._unregister_listener()

    def initiate_upi123_call(self, phone_number: Optional[str], amount: Optional[str]) -> bool:
        try:
            result = call_string.build(
                DEFAULT_UPI_SERVICE_NUMBER, phone_number or "", amount or ""
            )
            if isinstance(result, call_string.Invalid):
                log.error("UPI123 call rejected: %s", result.reason.name)
                self._platform.toast(message_for(result.reason))
                return False
            call_uri = result.call_string

            if not self._platform.has_permission(PERMISSION_CALL_PHONE):
                log.error("CALL_PHONE permission not granted")
                self._platform.toast(
                    "Phone call permission is required for manual payments. "
                    "Please grant permission in Settings."
                )
                return False

            # Call-state tracking and outcome interpretation are owned by
            # CallStateCoordinator / PaymentSessionManager — no per-call
            # listener is registered here.
            self._platform.start_call(call_uri)
            log.debug("UPI123 call started")
            return True
        except PermissionError:
            log.exception("Security exception while initiating call")
            self._platform.toast("Call permission denied")
            return False
        except Exception:
            log.exception("Unexpected error while initiating UPI123 call")
            self._platform.toast("Call failed")
            return False

    def construct_upi123_call_string(self, phone_number: str, amount: str) -> str:
        result = call_string.build(DEFAULT_UPI_SERVICE_NUMBER, phone_number, amount)
        if isinstance(result, call_string.Valid):
            return result.call_string
        raise ValueError(result.reason.name)

    # ---- call-state listener -------------------------------------------------

    def _create_call_state_listener(
        self, on_ended: Optional[Callable[[CallType], None]] = None
    ) -> Callable[[int], None]:
        def on_state_changed(state: int) -> None:
            log.debug("Call State: %d", state)
            if state == CALL_STATE_IDLE:
                if self._is_call_in_progress:
                    with self._call_state_lock:
                        self._is_call_in_progress = False
                        call_type = self._current_call_type
                        if call_type is not None:
                            if on_ended is not None:
                                on_ended(call_type)
                            else:
                                callback = self._get_call_ended_callback()
                                if callback is not None:
                                    callback(call_type)
                        self._current_call_type = None
                        self._clear_callbacks()
            elif state == CALL_STATE_OFFHOOK:
                if not self._is_call_in_progress:
                    self._is_call_in_progress = True
            # RINGING: call is ringing — nothing to do.

        return on_state_changed

    def _unregister_listener(self) -> None:
        with self._listener_lock:
            try:
                if self._listener is not None:
                    self._platform.unlisten_call_state(self._listener)
            except Exception:
                log.exception("Error unregistering phone state listener")
            finally:
                self._listener = None

    def end_call(self) -> None:
        with self._call_state_lock:
            self._is_call_in_progress = False
            self._current_call_type = None
            self._clear_callbacks()
        self._unregister_listener()

    def is_call_in_progress(self) -> bool:
        return self._is_call_in_progress

    def get_call_state(self) -> int:
        return self._platform.get_call_state()

    def terminate_call(self) -> bool:
        """Terminates the active call via TelecomManager.endCall().

        Requires ANSWER_PHONE_CALLS; without it this honestly returns False
        so the caller can tell the user to hang up manually."""
        try:
            if self.get_call_state() == CALL_STATE_IDLE:
                log.warning("No call in progress, cannot terminate")
                return False
            if not self._platform.has_permission(PERMISSION_ANSWER_PHONE_CALLS):
                log.warning("ANSWER_PHONE_CALLS not granted - cannot end call programmatically")
                return False
            terminated = self._platform.telecom_end_call()
            log.debug("TelecomManager.endCall() -> %s", terminated)
            if terminated:
                with self._call_state_lock:
                    self._is_call_in_progress = False
                    self._current_call_type = None
            return terminated
        except Exception:
            log.exception("Failed to terminate call")
            return False

    # ---- audio ---------------------------------------------------------------

    def mute_call_audio(self) -> bool:
        """Mutes ONLY the voice-call stream. Ring/alarm/notification streams
        must never be touched — silencing a user's alarm clock during a
        35-second payment call is real-world harm."""
        with self._audio_lock:
            try:
                self._original_call_volume = self._platform.get_stream_volume(STREAM_VOICE_CALL)
                self._previous_audio_mode = self._platform.get_mode()

                self._platform.set_mode(MODE_IN_CALL)
                if self._platform.get_mode() != MODE_IN_CALL:
                    log.warning("Failed to set audio mode to MODE_IN_CALL")
                    return False

                self._platform.set_microphone_mute(True)
                self._platform.set_speakerphone_on(False)

                try:
                    self._platform.set_stream_volume(STREAM_VOICE_CALL, 0, 0)
                except Exception:
                    log.exception("Failed to mute voice-call stream")

                self._is_audio_muted = True
                log.debug("Call audio muted")
                return True
            except Exception:
                log.exception("Failed to mute call audio")
                return False

    def unmute_call_audio(self) -> bool:
        """Restores audio mode, microphone and the voice-call volume (the
        only stream mute touches)."""
        with self._audio_lock:
            try:
                self._platform.set_mode(self._previous_audio_mode)
                if self._platform.get_mode() != self._previous_audio_mode:
                    log.warning("Failed to restore audio mode to %d", self._previous_audio_mode)

                self._platform.set_microphone_mute(False)

                try:
                    self._platform.set_stream_volume(STREAM_VOICE_CALL, self._original_call_volume, 0)
                    current = self._platform.get_stream_volume(STREAM_VOICE_CALL)
                    if current != self._original_call_volume:
                        log.warning(
                            "Failed to restore call volume, expected: %d, actual: %d",
                            self._original_call_volume,
                            current,
                        )
                except Exception:
                    log.exception("Failed to restore call volume")

                self._is_audio_muted = False
                log.debug("Call audio restored successfully")
                return True
            except Exception:
                log.exception("Failed to restore call audio")
                return False

    def set_call_volume_to_minimum(self) -> bool:
        """Sets call volume to minimum (1) for IVR calls, storing the
        original for restore_call_volume."""
        with self._audio_lock:
            try:
                if self._original_call_volume == 0:
                    self._original_call_volume = self._platform.get_stream_volume(STREAM_VOICE_CALL)

                self._platform.set_mode(MODE_IN_CALL)
                self._platform.set_stream_volume(STREAM_VOICE_CALL, 1, FLAG_SHOW_UI)
                current = self._platform.get_stream_volume(STREAM_VOICE_CALL)
                return current <= 1
            except Exception:
                log.exception("Failed to set call volume to minimum")
                return False

    def restore_call_volume(self) -> bool:
        """Restores call volume to the stored original level."""
        with self._audio_lock:
            try:
                if self._original_call_volume > 0:
                    self._platform.set_mode(self._previous_audio_mode)
                    self._platform.set_stream_volume(
                        STREAM_VOICE_CALL, self._original_call_volume, FLAG_SHOW_UI
                    )
                    current = self._platform.get_stream_volume(STREAM_VOICE_CALL)
                    return current == self._original_call_volume
                log.warning("No original call volume stored, cannot restore")
                return False
            except Exception:
                log.exception("Failed to restore call volume")
                return False

    def is_audio_muted(self) -> bool:
        return self._is_audio_muted

    # ---- callbacks / cleanup --------------------------------------------------

    def _get_call_ended_callback(self) -> Optional[Callable[[CallType], None]]:
        with self._callback_lock:
            return self._on_call_ended

    def _get_ussd_complete_callback(self) -> Optional[Callable[[], None]]:
        with self._callback_lock:
            return self._on_ussd_complete

    def _clear_callbacks(self) -> None:
        with self._callback_lock:
            self._on_call_ended = None
            self._on_ussd_complete = None

    def cleanup(self) -> None:
        """Release all resources and prevent leaks."""
        with self._audio_lock:
            try:
                if self._is_audio_muted:
                    self.unmute_call_audio()
            except Exception:
                log.exception("Error during audio cleanup")

        with self._call_state_lock:
            try:
                self._clear_callbacks()
                self._current_call_type = None
                self._is_call_in_progress = False
            except Exception:
                log.exception("Error during state cleanup")

        self._unregister_listener()
        log.debug("CallManager cleanup completed")
