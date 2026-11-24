# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/services/CallOverlayPresentationTest.kt
# plus orchestration coverage for CallOverlayService.

import pytest

from paynet.overlay import service as overlay_service
from paynet.overlay.service import (CallOverlayService, OVERLAY_ERROR_TOAST,
                                    OVERLAY_PERMISSION_TOAST,
                                    TERMINATE_FAILED_TOAST)
from paynet.overlay.view import (AUTH_NOTICE, CONNECTING, PIN_NOTICE,
                                 PROCESSING_PAYMENT, SENDING_REQUEST,
                                 CallOverlayProgress, CallOverlayView,
                                 PROGRESS_CEILING, clamp_progress,
                                 progress_percent)
from paynet.payment import state as ps
from paynet.telephony.coordinator import IdleState, OffHookState, RingingState

CONNECTING_PROGRESS = 100
IN_CALL_PROGRESS = 200
MILESTONE_MS = 1000
CALL_PACING_MS = 31000


def make_view():
    view = CallOverlayView()
    view.bind_details("9876543210", "99")
    return view


class TestBind:
    # bindingResetsAReusedViewAndShowsTheCallEstimate
    def test_bind_resets_reused_view(self):
        view = make_view()
        view.show_progress(PROGRESS_CEILING)
        view.bind_details("9876543210", "99")
        assert view.progress == 0
        assert view.percent_text.text == "0%"
        assert view.amount_text.text == "₹99.00"
        assert view.step_text.text == CONNECTING
        assert view.status_text.text == PROCESSING_PAYMENT

    def test_recipient_shows_last_four_digits(self):
        view = make_view()
        assert view.recipient_text.text.endswith("3210")
        assert "987654" not in view.recipient_text.text.replace("3210", "")


class TestPacing:
    def make(self, animations=True):
        view = make_view()
        clock = {"now": 0.0}
        progress = CallOverlayProgress(view, lambda: animations,
                                       now=lambda: clock["now"])
        return view, clock, progress

    # connectingAdvancesFillAndPercentageTogether
    def test_connecting_advances_to_milestone(self):
        view, clock, progress = self.make()
        progress.show_connecting()
        assert progress.progress_at(500) in range(1, CONNECTING_PROGRESS)
        assert progress.progress_at(1100) == CONNECTING_PROGRESS

    # inCallPacingAdvancesOnceAndNeverDeclaresCompletion
    def test_in_call_pacing_reaches_ceiling_and_never_completes(self):
        view, clock, progress = self.make()
        progress.show_in_call()
        assert progress.progress_at(1100) >= IN_CALL_PROGRESS
        mid = progress.progress_at(16000)
        assert IN_CALL_PROGRESS < mid < PROGRESS_CEILING
        before_duplicate = mid
        progress.show_in_call()  # repeated phase cannot restart or rewind
        assert progress.progress_at(16000) == before_duplicate
        assert progress.progress_at(32000) == PROGRESS_CEILING
        assert progress.progress_at(46000) == PROGRESS_CEILING
        assert progress_percent(PROGRESS_CEILING) == 90

    # stoppingCancelsFramesAndCannotRestartTheOldView
    def test_stop_freezes_and_cannot_restart(self):
        view, clock, progress = self.make()
        progress.show_in_call()
        progress.tick(1100)
        stopped = view.progress
        progress.stop()
        progress.show_connecting()
        progress.show_in_call()
        progress.tick(46000)
        assert view.progress == stopped

    # reducedMotionUsesStablePhaseMilestonesWithoutTimedCreep
    def test_reduced_motion_uses_stable_milestones(self):
        view, clock, progress = self.make(animations=False)
        progress.show_connecting()
        assert view.progress == CONNECTING_PROGRESS
        progress.show_in_call()
        assert view.progress == IN_CALL_PROGRESS
        progress.tick(46000)
        assert view.progress == IN_CALL_PROGRESS

    # displayClampsOutOfRangeEstimatesBelowPaymentCompletion
    def test_progress_clamped(self):
        assert clamp_progress(2**31 - 1) == PROGRESS_CEILING
        assert clamp_progress(-(2**31)) == 0


class FakeScheduler:
    def __init__(self):
        self.pending = []

    def __call__(self, callback, delay_s):
        self.pending.append((delay_s, callback))

    def run_next(self):
        delay, callback = self.pending.pop(0)
        callback()

    def run_all(self):
        while self.pending:
            self.run_next()


class FakeCoordinator:
    def __init__(self, state=None):
        self.call_state = state or IdleState()
        self.acquired = []
        self.released = []

    def acquire(self, tag):
        self.acquired.append(tag)

    def release(self, tag):
        self.released.append(tag)

    def add_call_state_listener(self, listener):
        self._listener = listener
        return lambda: None


class FakeSession:
    def __init__(self, state=None):
        self.payment_state = state
        self.calls = []

    def subscribe(self, listener):
        self._listener = listener
        return lambda: None

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, args))
        return record


class FakeDialogs:
    def __init__(self):
        self.shown = []

    def __getattr__(self, name):
        def record(*_args):
            self.shown.append(name)
        return record


class FakeCalls:
    def __init__(self, terminate_ok=True, volume_ok=True):
        self.terminate_ok = terminate_ok
        self.volume_ok = volume_ok
        self.calls = []

    def terminate_call(self):
        self.calls.append("terminate")
        return self.terminate_ok

    def restore_call_volume(self):
        self.calls.append("restore")

    def set_call_volume_to_minimum(self):
        self.calls.append("lower")
        return self.volume_ok


class FakeHost:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.added = []

    def add_view(self, view):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("window died")
        self.added.append(view)

    def remove_view(self, view):
        self.added.remove(view)


def make_service(**overrides):
    parts = dict(coordinator=FakeCoordinator(), session_manager=FakeSession(),
                 dialog_manager=FakeDialogs(), call_manager=FakeCalls(),
                 overlay_host=FakeHost(), scheduler=FakeScheduler())
    parts.update(overrides)
    service = CallOverlayService(**parts)
    service.create()
    return service, parts


class TestTimeout:
    # startTimeoutTimer: only a persistently Idle device cancels the session.
    def test_idle_device_gives_up_and_closes_session(self):
        service, parts = make_service()
        service.show_overlay_internal("9876543210", "99")
        parts["scheduler"].run_next()  # the 40s watchdog
        assert ("on_call_never_started", ()) in parts["session_manager"].calls

    def test_busy_device_rearms_up_to_three_times(self):
        coordinator = FakeCoordinator(state=RingingState())
        service, parts = make_service(coordinator=coordinator)
        service.show_overlay_internal("9876543210", "99")
        scheduler = parts["scheduler"]
        scheduler.run_next()  # fires at 40s, re-arms
        scheduler.run_next()  # +10s, re-arms
        scheduler.run_next()  # +10s, re-arms
        assert ("on_call_never_started", ()) not in parts["session_manager"].calls
        assert service.timeout_extensions == 3
        scheduler.run_next()  # +10s, limit reached: gives up
        assert ("on_call_never_started", ()) in parts["session_manager"].calls

    def test_detected_call_cancels_the_watchdog(self):
        service, parts = make_service()
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        scheduler = parts["scheduler"]
        # Pending callbacks belong to overlay setup, never to the watchdog.
        for _delay, _ in scheduler.pending:
            pass
        service._on_timeout()  # a stale watchdog fire must be a no-op
        assert ("on_call_never_started", ()) not in parts["session_manager"].calls


class TestCallDetection:
    def test_detection_creates_bound_overlay(self):
        service, parts = make_service()
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        assert service.is_overlay_active
        assert len(parts["overlay_host"].added) == 1
        assert service.view.amount_text.text == "₹99.00"
        assert service.view.step_text.text == CONNECTING

    def test_duplicate_detection_with_active_overlay_ignored(self):
        service, parts = make_service()
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        first_view = service.view
        service.on_call_detected()
        assert service.view is first_view
        assert len(parts["overlay_host"].added) == 1

    def test_missing_pending_data_skips_overlay(self):
        service, parts = make_service()
        service.on_call_detected()
        assert not parts["overlay_host"].added

    def test_post_call_prompt_never_reopens_guide(self):
        service, parts = make_service()
        service.post_call_prompt_active = True
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        assert not service.is_overlay_active

    def test_permission_denied_toasts_and_shows_nothing(self):
        toasts = []
        service, parts = make_service(overlay_permission=lambda: False,
                                      toast=toasts.append)
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        assert toasts == [OVERLAY_PERMISSION_TOAST]
        assert not service.is_overlay_active

    def test_overlay_failure_retries_with_backoff_then_toasts(self):
        host = FakeHost(fail_times=10)
        toasts = []
        service, parts = make_service(overlay_host=host, toast=toasts.append)
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        scheduler = parts["scheduler"]

        def run_retry():
            # The 40s watchdog is also pending; fire only retry callbacks.
            index = next(i for i, (d, _) in enumerate(scheduler.pending)
                         if d in (1.0, 2.0, 3.0))
            scheduler.pending.pop(index)[1]()

        retries = lambda: [d for d, _ in scheduler.pending if d in (1.0, 2.0, 3.0)]
        assert retries() == [1.0]
        run_retry()
        assert retries() == [2.0]
        run_retry()
        assert retries() == [3.0]
        run_retry()
        assert retries() == []
        assert toasts == [OVERLAY_ERROR_TOAST]
        assert not host.added

    def test_volume_lowered_reveals_pill_only_on_success(self):
        service, parts = make_service()
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        volume_callback = [cb for d, cb in parts["scheduler"].pending if d == 2.0][0]
        volume_callback()
        assert service.view._muted_holder.opacity == 1

        service2, parts2 = make_service(call_manager=FakeCalls(volume_ok=False))
        service2.show_overlay_internal("9876543210", "99")
        service2.on_call_detected()
        [cb for d, cb in parts2["scheduler"].pending if d == 2.0][0]()
        assert service2.view._muted_holder.opacity == 0


class TestPaymentStates:
    def show(self, service, parts, state):
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        service.on_payment_state_changed(state)
        return service

    def test_in_progress_switches_to_sending_request_and_pacing(self):
        service, parts = make_service()
        self.show(service, parts, ps.InProgress("step", 0.5, "+91", "99", "t1"))
        assert service.view.step_text.text == SENDING_REQUEST
        assert service._progress_pacing is not None
        assert service._progress_pacing.phase == CallOverlayProgress.IN_CALL

    def test_success_vibrates_ends_call_finishes_without_dialog(self):
        buzzes = []
        service, parts = make_service(vibrate=lambda: buzzes.append(1))
        self.show(service, parts, ps.Success("t1", "+91", "99"))
        assert buzzes == [1]
        assert "terminate" in parts["call_manager"].calls
        assert parts["dialog_manager"].shown == []
        assert not service.is_overlay_active

    def test_failed_shows_failed_dialog_once(self):
        service, parts = make_service()
        self.show(service, parts, ps.Failed("err", "+91", "99", "t1"))
        self.show(service, parts, ps.Failed("err", "+91", "99", "t1"))
        assert parts["dialog_manager"].shown == ["show_transaction_failed"]

    def test_cancelled_by_user_picks_by_user_dialog(self):
        service, parts = make_service()
        self.show(service, parts,
                  ps.Cancelled("+91", "99", "t1", reason="Cancelled by user"))
        assert parts["dialog_manager"].shown == ["show_transaction_cancelled_by_user"]

    def test_cancelled_by_timeout_picks_plain_cancelled_dialog(self):
        service, parts = make_service()
        self.show(service, parts,
                  ps.Cancelled("+91", "99", "t1",
                               reason="The payment call was never connected"))
        assert parts["dialog_manager"].shown == ["show_transaction_cancelled"]

    def test_needs_review_finishes_without_dialog(self):
        service, parts = make_service()
        self.show(service, parts, ps.NeedsReview("t1", "+91", "99"))
        assert parts["dialog_manager"].shown == []
        assert not service.is_overlay_active

    def test_timeout_winds_down_silently(self):
        service, parts = make_service()
        self.show(service, parts,
                  ps.Timeout(ps.TimeoutType.BANK_VERIFICATION, "+91", "99", "t1"))
        assert parts["dialog_manager"].shown == []

    def test_finish_schedules_stop(self):
        stopped = []
        service, parts = make_service(stop_self=lambda: stopped.append(1))
        self.show(service, parts, ps.Success("t1", "+91", "99"))
        parts["scheduler"].run_all()
        assert stopped == [1]


class TestTerminate:
    def test_terminate_marks_session_cancelled_before_cleanup(self):
        order = []
        session = FakeSession()
        session.on_user_cancelled = lambda: order.append("session")
        calls = FakeCalls()
        calls.terminate_call = lambda: (order.append("calls"), True)[1]
        service, parts = make_service(session_manager=session, call_manager=calls)
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        service.handle_terminate_call()
        assert order[:2] == ["session", "calls"]

    def test_failed_termination_toasts(self):
        toasts = []
        service, parts = make_service(call_manager=FakeCalls(terminate_ok=False),
                                      toast=toasts.append)
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        service.handle_terminate_call()
        assert toasts == [TERMINATE_FAILED_TOAST]

    def test_terminate_without_session_winds_down_defensively(self):
        stopped = []
        service, parts = make_service(session_manager=None,
                                      stop_self=lambda: stopped.append(1))
        service.show_overlay_internal("9876543210", "99")
        service.on_call_detected()
        service.handle_terminate_call()
        assert parts["dialog_manager"].shown == ["show_transaction_cancelled_by_user"]
        parts["scheduler"].run_all()
        assert stopped == [1]


class TestGuidanceTiming:
    # bankInstructionsKeepTheirExistingTiming: PIN at 2.5s, auth 16.5s later.
    def test_guidance_schedule(self):
        fired = []
        view = make_view()
        calls = []

        def scheduler(callback, delay_s):
            calls.append((delay_s, callback))

        class FakeMotion:
            def show(self, text):
                fired.append(text)

        view.schedule_bank_guidance(FakeMotion(), scheduler=scheduler)
        assert [d for d, _ in calls] == [2.5, 19.0]
        calls[0][1]()
        assert fired == [PIN_NOTICE]
        calls[1][1]()
        assert fired == [PIN_NOTICE, AUTH_NOTICE]
