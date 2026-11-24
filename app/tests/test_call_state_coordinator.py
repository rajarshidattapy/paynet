# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/telephony/CallStateCoordinatorTest.kt

"""The single authority for device call state. The payment flow keys real
money decisions off these signals — whether the IVR call plausibly ran
(talk-time duration) and whether a call is still active — so state
transitions, session events, and listener lifetime must be exact.

handle_state_change is driven directly so the transition logic is tested
without a live telephony stack. Registration behavior is tested against a
fake TelephonyAdapter, replacing the Robolectric ShadowTelephonyManager
tests; the legacy PhoneStateListener path (API 29-30) has no Python
equivalent and is covered by the single pyjnius adapter in feature 7.
"""

from paynet.telephony.coordinator import (
    CALL_STATE_IDLE,
    CALL_STATE_OFFHOOK,
    CALL_STATE_RINGING,
    CallStateCoordinator,
    DEVICE_IDLE,
    DEVICE_OFFHOOK,
    DEVICE_RINGING,
    Ended,
    Started,
)


class FakeClock:
    def __init__(self, now=0):
        self.now = now

    def __call__(self):
        return self.now


class FakeTelephonyAdapter:
    """Stands in for the platform TelephonyManager binding."""

    def __init__(self):
        self.registered = False
        self.registration_attempts = 0
        self.deny_registration = False
        self.current = CALL_STATE_IDLE
        self.listener = None

    def register(self, on_state_change):
        self.registration_attempts += 1
        if self.deny_registration:
            raise PermissionError("READ_PHONE_STATE denied in fixture")
        self.registered = True
        self.listener = on_state_change

    def unregister(self):
        self.registered = False
        self.listener = None

    def current_state(self):
        return self.current

    def set_call_state(self, state):
        self.current = state
        if self.listener is not None:
            self.listener(state)


def record_session_events(coordinator):
    events = []
    coordinator.add_session_listener(events.append)
    return events


def test_telephony_states_map_to_the_coordinator_device_call_states():
    coordinator = CallStateCoordinator()

    assert coordinator.call_state is DEVICE_IDLE

    coordinator.handle_state_change(CALL_STATE_RINGING)
    assert coordinator.call_state is DEVICE_RINGING

    coordinator.handle_state_change(CALL_STATE_OFFHOOK)
    assert coordinator.call_state is DEVICE_OFFHOOK

    coordinator.handle_state_change(CALL_STATE_IDLE)
    assert coordinator.call_state is DEVICE_IDLE


def test_answered_call_emits_started_at_answer_and_ended_with_talk_time_duration():
    clock = FakeClock(1_000)
    coordinator = CallStateCoordinator(clock=clock)
    events = record_session_events(coordinator)

    coordinator.handle_state_change(CALL_STATE_RINGING)
    clock.now = 4_000  # rang for 3s before pickup
    coordinator.handle_state_change(CALL_STATE_OFFHOOK)
    clock.now = 64_000
    coordinator.handle_state_change(CALL_STATE_IDLE)

    # Duration must measure OFFHOOK -> IDLE (talk time), never include ring
    # time: the payment flow uses it to judge whether the IVR call plausibly
    # completed, and padding it with ringing would let an unanswered call
    # look like a finished payment call.
    assert events == [Started(4_000), Ended(60_000)]


def test_duplicate_offhook_callbacks_neither_reemit_started_nor_reset_the_session_start():
    clock = FakeClock(1_000)
    coordinator = CallStateCoordinator(clock=clock)
    events = record_session_events(coordinator)

    coordinator.handle_state_change(CALL_STATE_OFFHOOK)
    clock.now = 5_000
    # The framework re-delivers the current state (listener re-reads,
    # subscription changes). A duplicate must not restart the session clock
    # — that would understate call duration — nor double-fire the
    # session-started logic downstream.
    coordinator.handle_state_change(CALL_STATE_OFFHOOK)
    clock.now = 10_000
    coordinator.handle_state_change(CALL_STATE_IDLE)

    assert events == [Started(1_000), Ended(9_000)]


def test_missed_call_emits_no_session_events():
    coordinator = CallStateCoordinator(clock=FakeClock(1_000))
    events = record_session_events(coordinator)

    # RINGING -> IDLE with no pickup: nothing was ever active, so a missed
    # call must not look like a completed payment call.
    coordinator.handle_state_change(CALL_STATE_RINGING)
    coordinator.handle_state_change(CALL_STATE_IDLE)

    assert events == []


def test_wall_clock_going_backwards_yields_zero_duration_not_negative():
    clock = FakeClock(60_000)
    coordinator = CallStateCoordinator(clock=clock)
    events = record_session_events(coordinator)

    coordinator.handle_state_change(CALL_STATE_OFFHOOK)
    clock.now = 10_000  # NITZ/NTP resync moved the wall clock backwards mid-call
    coordinator.handle_state_change(CALL_STATE_IDLE)

    # A negative talk time would corrupt any downstream duration check.
    assert events == [Started(60_000), Ended(0)]


def test_reference_counting_keeps_the_listener_registered_until_the_last_consumer_releases():
    telephony = FakeTelephonyAdapter()
    coordinator = CallStateCoordinator(telephony=telephony)

    # Two consumers (e.g. overlay + session manager) hold references.
    coordinator.acquire("overlay")
    coordinator.acquire("session")

    telephony.set_call_state(CALL_STATE_RINGING)
    assert coordinator.call_state is DEVICE_RINGING, "registered listener must deliver state"

    # One consumer leaves; the other must keep receiving updates. If the
    # listener died here, the session manager would go blind mid-payment.
    coordinator.release("overlay")
    telephony.set_call_state(CALL_STATE_OFFHOOK)
    assert (
        coordinator.call_state is DEVICE_OFFHOOK
    ), "one remaining consumer must keep the listener alive"

    # Last consumer leaves: the listener must actually unregister, so later
    # device state changes no longer reach the coordinator.
    coordinator.release("session")
    assert not telephony.registered
    telephony.set_call_state(CALL_STATE_RINGING)
    assert (
        coordinator.call_state is DEVICE_OFFHOOK
    ), "fully released coordinator must stop observing"

    # Over-release is a no-op, and a later acquire re-registers and seeds
    # the CURRENT device state (here: still RINGING) so a consumer that
    # acquires mid-call is not stuck seeing a stale OffHook.
    coordinator.release("stray-double-release")
    coordinator.acquire("retry")
    assert telephony.registered
    assert coordinator.call_state is DEVICE_RINGING, "re-acquire must re-register and seed current state"


def test_listener_delivers_one_call_session_and_stops_after_the_last_release():
    telephony = FakeTelephonyAdapter()
    coordinator = CallStateCoordinator(telephony=telephony, clock=FakeClock(0))
    events = record_session_events(coordinator)

    coordinator.acquire("overlay")
    coordinator.acquire("payment")
    telephony.set_call_state(CALL_STATE_OFFHOOK)
    coordinator.release("overlay")
    telephony.set_call_state(CALL_STATE_OFFHOOK)  # duplicate re-delivery
    telephony.set_call_state(CALL_STATE_IDLE)
    assert events == [Started(0), Ended(0)]

    coordinator.release("payment")
    telephony.set_call_state(CALL_STATE_RINGING)
    assert coordinator.call_state is DEVICE_IDLE
    assert len(events) == 2


def test_a_permission_denied_registration_is_retried_on_the_next_acquire():
    telephony = FakeTelephonyAdapter()
    telephony.deny_registration = True
    coordinator = CallStateCoordinator(telephony=telephony, clock=FakeClock(0))
    events = record_session_events(coordinator)

    coordinator.acquire("before-permission")
    telephony.set_call_state(CALL_STATE_OFFHOOK)
    assert coordinator.call_state is DEVICE_IDLE
    assert events == []

    telephony.deny_registration = False
    coordinator.acquire("after-permission")
    assert telephony.registration_attempts == 2
    # Registering seeds the CURRENT device state (OFFHOOK), so a consumer
    # that acquires mid-call is not stuck seeing Idle.
    assert coordinator.call_state is DEVICE_OFFHOOK
    assert events == [Started(0)]

    coordinator.release("before-permission")
    telephony.set_call_state(CALL_STATE_IDLE)
    assert events == [Started(0), Ended(0)]
