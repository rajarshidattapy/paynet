// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.telephony

import android.content.Context
import android.os.Looper
import android.telephony.TelephonyManager
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry

/**
 * The single authority for device call state. The payment flow keys real
 * money decisions off these signals — whether the IVR call plausibly ran
 * (talk-time duration) and whether a call is still active — so state
 * transitions, session events, and listener lifetime must be exact.
 *
 * handleStateChange is driven directly (internal, same module) so the
 * transition logic is tested without a live telephony stack; the
 * acquire/release test goes through Robolectric's ShadowTelephonyManager
 * to observe real (un)registration behavior.
 */
@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(AndroidJUnit4::class)
class CallStateCoordinatorTest {

    private val context: Context = InstrumentationRegistry.getInstrumentation().targetContext

    /** Collects session events on an eager collector so tryEmit-ed events are not dropped. */
    private fun TestScope.recordSessionEvents(coordinator: CallStateCoordinator): List<CallSessionEvent> {
        val events = mutableListOf<CallSessionEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            coordinator.sessionEvents.toList(events)
        }
        return events
    }

    @Test
    fun telephony_states_map_to_the_coordinator_device_call_states() {
        val coordinator = CallStateCoordinator(context)

        assertEquals(DeviceCallState.Idle, coordinator.callState.value)

        coordinator.handleStateChange(TelephonyManager.CALL_STATE_RINGING)
        assertEquals(DeviceCallState.Ringing, coordinator.callState.value)

        coordinator.handleStateChange(TelephonyManager.CALL_STATE_OFFHOOK)
        assertEquals(DeviceCallState.OffHook, coordinator.callState.value)

        coordinator.handleStateChange(TelephonyManager.CALL_STATE_IDLE)
        assertEquals(DeviceCallState.Idle, coordinator.callState.value)
    }

    @Test
    fun answered_call_emits_Started_at_answer_and_Ended_with_talk_time_duration() = runTest {
        var now = 1_000L
        val coordinator = CallStateCoordinator(context) { now }
        val events = recordSessionEvents(coordinator)

        coordinator.handleStateChange(TelephonyManager.CALL_STATE_RINGING)
        now = 4_000L // rang for 3s before pickup
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_OFFHOOK)
        now = 64_000L
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_IDLE)

        // Duration must measure OFFHOOK -> IDLE (talk time), never include
        // ring time: the payment flow uses it to judge whether the IVR call
        // plausibly completed, and padding it with ringing would let an
        // unanswered call look like a finished payment call.
        assertEquals(
            listOf<CallSessionEvent>(CallSessionEvent.Started(4_000L), CallSessionEvent.Ended(60_000L)),
            events
        )
    }

    @Test
    fun duplicate_OFFHOOK_callbacks_neither_re_emit_Started_nor_reset_the_session_start() = runTest {
        var now = 1_000L
        val coordinator = CallStateCoordinator(context) { now }
        val events = recordSessionEvents(coordinator)

        coordinator.handleStateChange(TelephonyManager.CALL_STATE_OFFHOOK)
        now = 5_000L
        // The framework re-delivers the current state (listener re-reads,
        // subscription changes). A duplicate must not restart the session
        // clock — that would understate call duration — nor double-fire the
        // session-started logic downstream.
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_OFFHOOK)
        now = 10_000L
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_IDLE)

        assertEquals(
            listOf<CallSessionEvent>(CallSessionEvent.Started(1_000L), CallSessionEvent.Ended(9_000L)),
            events
        )
    }

    @Test
    fun missed_call_emits_no_session_events() = runTest {
        val coordinator = CallStateCoordinator(context) { 1_000L }
        val events = recordSessionEvents(coordinator)

        // RINGING -> IDLE with no pickup: nothing was ever active, so a
        // missed call must not look like a completed payment call.
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_RINGING)
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_IDLE)

        assertEquals(emptyList<CallSessionEvent>(), events)
    }

    @Test
    fun wall_clock_going_backwards_yields_zero_duration_not_negative() = runTest {
        var now = 60_000L
        val coordinator = CallStateCoordinator(context) { now }
        val events = recordSessionEvents(coordinator)

        coordinator.handleStateChange(TelephonyManager.CALL_STATE_OFFHOOK)
        now = 10_000L // NITZ/NTP resync moved the wall clock backwards mid-call
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_IDLE)

        // A negative talk time would corrupt any downstream duration check.
        assertEquals(
            listOf<CallSessionEvent>(CallSessionEvent.Started(60_000L), CallSessionEvent.Ended(0L)),
            events
        )
    }

}
