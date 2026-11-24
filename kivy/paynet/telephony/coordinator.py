# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/telephony/CallStateCoordinator.kt

"""The single authority for device call state.

The transition logic (handle_state_change, reference counting, registration
retry after a denied permission) is ported 1:1. Android's TelephonyManager is
replaced by a pluggable `telephony` adapter with register/unregister/
current_state methods; the pyjnius-backed adapter ships with the telephony
feature and is UNVERIFIED on desktop (see MIGRATION.md). Without an adapter
the coordinator still runs — handle_state_change can be driven directly,
which is also how the tests exercise it.

Kotlin's StateFlow/SharedFlow become a value property plus listener lists:
call_state listeners receive the new DeviceCallState, session-event
listeners receive each CallSessionEvent (the SharedFlow's tryEmit with
extraBufferCapacity=16 never drops, so a plain list is faithful).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol

log = logging.getLogger("CallStateCoordinator")

# Mirrors android.telephony.TelephonyManager constants.
CALL_STATE_IDLE = 0
CALL_STATE_RINGING = 1
CALL_STATE_OFFHOOK = 2


class DeviceCallState:
    """Sealed-interface equivalent: Idle / Ringing / OffHook singletons."""

    def __new__(cls):
        # Per-subclass singleton: read cls.__dict__ so a subclass never
        # inherits another state's instance through the base class.
        if cls.__dict__.get("_instance") is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return f"DeviceCallState.{type(self).__name__}"


class IdleState(DeviceCallState):
    pass


class RingingState(DeviceCallState):
    pass


class OffHookState(DeviceCallState):
    pass


DEVICE_IDLE = IdleState()
DEVICE_RINGING = RingingState()
DEVICE_OFFHOOK = OffHookState()


@dataclass(frozen=True)
class CallSessionEvent:
    """Base for Started / Ended."""


@dataclass(frozen=True)
class Started(CallSessionEvent):
    """A call became active (OFFHOOK)."""

    timestamp_ms: int


@dataclass(frozen=True)
class Ended(CallSessionEvent):
    """The active call ended (OFFHOOK -> IDLE)."""

    duration_ms: int


class TelephonyAdapter(Protocol):
    """Platform binding the coordinator registers with. Implemented by the
    pyjnius adapter on Android; faked in tests."""

    def register(self, on_state_change: Callable[[int], None]) -> None:
        """Register for platform call-state callbacks. May raise
        SecurityError-equivalent when READ_PHONE_STATE is not granted."""
        ...

    def unregister(self) -> None:
        ...

    def current_state(self) -> int:
        """One of CALL_STATE_IDLE / RINGING / OFFHOOK."""
        ...


class CallStateSource(Protocol):
    """What consumers (PaymentSessionManager, overlay) actually depend on —
    lets tests substitute a fake without a telephony stack."""

    @property
    def call_state(self) -> DeviceCallState:
        ...

    def acquire(self, tag: str) -> None:
        ...

    def release(self, tag: str) -> None:
        ...

    def add_session_listener(
        self, listener: Callable[[CallSessionEvent], None]
    ) -> Callable[[], None]:
        """Subscribe to session events; returns an unsubscribe handle."""
        ...


class CallStateCoordinator:
    """Exactly one telephony listener for the whole app; every consumer
    observes call_state / session events. Registration is reference-counted:
    the adapter is registered only while at least one consumer holds a
    reference. Tracked separately from the refcount: if register() fails
    (e.g. READ_PHONE_STATE not yet granted), the refcount stays elevated but
    `registered` stays false, so the NEXT acquire() retries."""

    def __init__(
        self,
        telephony: Optional[TelephonyAdapter] = None,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._telephony = telephony
        self._clock = clock
        self._call_state: DeviceCallState = DEVICE_IDLE
        self._call_state_listeners: List[Callable[[DeviceCallState], None]] = []
        self._session_listeners: List[Callable[[CallSessionEvent], None]] = []
        self._ref_count = 0
        # RLock: Kotlin's synchronized monitor is re-entrant and _register/
        # _unregister are called with it held (acquire/release) and also take
        # it themselves.
        self._registration_lock = threading.RLock()
        self._registered = False
        self._off_hook_since_ms = 0

    # ---- CallStateSource surface ----------------------------------------

    @property
    def call_state(self) -> DeviceCallState:
        return self._call_state

    def add_call_state_listener(
        self, listener: Callable[[DeviceCallState], None]
    ) -> Callable[[], None]:
        self._call_state_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._call_state_listeners:
                self._call_state_listeners.remove(listener)

        return unsubscribe

    def add_session_listener(
        self, listener: Callable[[CallSessionEvent], None]
    ) -> Callable[[], None]:
        self._session_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._session_listeners:
                self._session_listeners.remove(listener)

        return unsubscribe

    def acquire(self, tag: str) -> None:
        self._ref_count += 1
        with self._registration_lock:
            if self._ref_count > 0 and not self._registered:
                self._register(tag)
        log.debug("acquire(%s) refCount=%d", tag, self._ref_count)

    def release(self, tag: str) -> None:
        self._ref_count -= 1
        if self._ref_count <= 0:
            self._ref_count = 0
            with self._registration_lock:
                if self._registered:
                    self._unregister(tag)
        log.debug("release(%s) refCount=%d", tag, self._ref_count)

    # ---- registration -----------------------------------------------------

    def _register(self, tag: str) -> None:
        with self._registration_lock:
            if self._registered:
                return
            try:
                if self._telephony is not None:
                    self._telephony.register(self.handle_state_change)
                self._registered = True
                # Seed current state so consumers that acquire mid-call see OFFHOOK.
                if self._telephony is not None:
                    self.handle_state_change(self._telephony.current_state())
                log.debug("Telephony listener registered (%s)", tag)
            except PermissionError as e:
                # READ_PHONE_STATE not granted; consumers observe an Idle
                # flow until a later acquire() retries after the grant.
                log.error("Cannot register telephony listener: %s", e)
                self._registered = False

    def _unregister(self, tag: str) -> None:
        with self._registration_lock:
            try:
                if self._telephony is not None:
                    self._telephony.unregister()
                log.debug("Telephony listener unregistered (%s)", tag)
            except Exception:
                log.exception("Error unregistering telephony listener")
            finally:
                self._registered = False

    # ---- transition logic -------------------------------------------------

    def handle_state_change(self, state: int) -> None:
        if state == CALL_STATE_RINGING:
            new_state: DeviceCallState = DEVICE_RINGING
        elif state == CALL_STATE_OFFHOOK:
            new_state = DEVICE_OFFHOOK
        else:
            new_state = DEVICE_IDLE
        previous = self._call_state
        if previous is new_state:
            return
        self._call_state = new_state
        log.debug("Call state: %r -> %r", previous, new_state)
        for listener in list(self._call_state_listeners):
            listener(new_state)

        if new_state is DEVICE_OFFHOOK and previous is not DEVICE_OFFHOOK:
            self._off_hook_since_ms = self._clock()
            self._emit(Started(self._off_hook_since_ms))
        elif new_state is DEVICE_IDLE and previous is DEVICE_OFFHOOK:
            # Duration measures OFFHOOK -> IDLE (talk time), never ring time.
            # coerceAtLeast(0): a wall clock that jumps backwards mid-call
            # (NITZ/NTP resync) must not yield a negative talk time.
            duration = max(self._clock() - self._off_hook_since_ms, 0)
            self._emit(Ended(duration))

    def _emit(self, event: CallSessionEvent) -> None:
        for listener in list(self._session_listeners):
            listener(event)
