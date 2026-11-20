// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.telephony

import android.content.Context
import android.os.Build
import android.os.Looper
import android.telephony.TelephonyManager
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.ClassName
import org.robolectric.annotation.Config
import org.robolectric.annotation.Implementation
import org.robolectric.annotation.Implements
import org.robolectric.shadow.api.Shadow
import org.robolectric.shadows.ShadowTelephonyManager
import org.robolectric.util.ReflectionHelpers
import java.util.concurrent.Executor

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
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CallStateCoordinatorTest {

    private val context: Context = RuntimeEnvironment.getApplication()

    /** Collects session events on an eager collector so tryEmit-ed events are not dropped. */
    private fun TestScope.recordSessionEvents(coordinator: CallStateCoordinator): List<CallSessionEvent> {
        val events = mutableListOf<CallSessionEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            coordinator.sessionEvents.toList(events)
        }
        return events
    }

    @Test
    fun `telephony states map to the coordinator device call states`() {
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
    fun `answered call emits Started at answer and Ended with talk-time duration`() = runTest {
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
    fun `duplicate OFFHOOK callbacks neither re-emit Started nor reset the session start`() = runTest {
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
    fun `missed call emits no session events`() = runTest {
        val coordinator = CallStateCoordinator(context) { 1_000L }
        val events = recordSessionEvents(coordinator)

        // RINGING -> IDLE with no pickup: nothing was ever active, so a
        // missed call must not look like a completed payment call.
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_RINGING)
        coordinator.handleStateChange(TelephonyManager.CALL_STATE_IDLE)

        assertEquals(emptyList<CallSessionEvent>(), events)
    }

    @Test
    fun `wall clock going backwards yields zero duration not negative`() = runTest {
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

    @Test
    fun `reference counting keeps the listener registered until the last consumer releases`() {
        val telephonyManager = context.getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
        val shadowTelephony = shadowOf(telephonyManager)
        val coordinator = CallStateCoordinator(context)

        // Two consumers (e.g. overlay + session manager) hold references.
        coordinator.acquire("overlay")
        coordinator.acquire("session")

        shadowTelephony.setCallState(TelephonyManager.CALL_STATE_RINGING)
        shadowOf(Looper.getMainLooper()).idle()
        assertEquals(
            "registered listener must deliver state",
            DeviceCallState.Ringing,
            coordinator.callState.value
        )

        // One consumer leaves; the other must keep receiving updates. If the
        // listener died here, the session manager would go blind mid-payment.
        coordinator.release("overlay")
        shadowTelephony.setCallState(TelephonyManager.CALL_STATE_OFFHOOK)
        shadowOf(Looper.getMainLooper()).idle()
        assertEquals(
            "one remaining consumer must keep the listener alive",
            DeviceCallState.OffHook,
            coordinator.callState.value
        )

        // Last consumer leaves: the listener must actually unregister, so
        // later device state changes no longer reach the coordinator.
        coordinator.release("session")
        shadowTelephony.setCallState(TelephonyManager.CALL_STATE_RINGING)
        shadowOf(Looper.getMainLooper()).idle()
        assertEquals(
            "fully released coordinator must stop observing",
            DeviceCallState.OffHook,
            coordinator.callState.value
        )

        // Over-release is a no-op, and a later acquire re-registers and
        // seeds the CURRENT device state (here: still RINGING) so a consumer
        // that acquires mid-call is not stuck seeing a stale OffHook.
        coordinator.release("stray-double-release")
        coordinator.acquire("retry")
        shadowOf(Looper.getMainLooper()).idle()
        assertEquals(
            "re-acquire must re-register and seed current state",
            DeviceCallState.Ringing,
            coordinator.callState.value
        )
    }

    @Test
    fun `legacy listener delivers one call session and stops after the last release`() = runTest {
        val originalSdk = Build.VERSION.SDK_INT
        // Both Android listener APIs exist in the cached API34 test runtime.
        // Select the legacy adapter without downloading a second Android image.
        ReflectionHelpers.setStaticField(Build.VERSION::class.java, "SDK_INT", Build.VERSION_CODES.R)
        val telephony = shadowOf(context.getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager)
        val coordinator = CallStateCoordinator(context) { 0L }
        val events = recordSessionEvents(coordinator)
        try {
            coordinator.acquire("overlay")
            coordinator.acquire("payment")
            telephony.setCallState(TelephonyManager.CALL_STATE_OFFHOOK)
            shadowOf(Looper.getMainLooper()).idle()
            coordinator.release("overlay")
            telephony.setCallState(TelephonyManager.CALL_STATE_OFFHOOK)
            telephony.setCallState(TelephonyManager.CALL_STATE_IDLE)
            shadowOf(Looper.getMainLooper()).idle()
            assertEquals(
                listOf<CallSessionEvent>(CallSessionEvent.Started(0L), CallSessionEvent.Ended(0L)),
                events
            )
            coordinator.release("payment")
            telephony.setCallState(TelephonyManager.CALL_STATE_RINGING)
            shadowOf(Looper.getMainLooper()).idle()
            assertEquals(DeviceCallState.Idle, coordinator.callState.value)
            assertEquals(2, events.size)
        } finally {
            coordinator.release("cleanup")
            ReflectionHelpers.setStaticField(Build.VERSION::class.java, "SDK_INT", originalSdk)
        }
    }

    @Test
    @Config(shadows = [RegistrationPermissionShadow::class])
    fun `a permission-denied registration is retried on the next acquire`() = runTest {
        val manager = context.getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
        val telephony = Shadow.extract<RegistrationPermissionShadow>(manager)
        val coordinator = CallStateCoordinator(context) { 0L }
        val events = recordSessionEvents(coordinator)
        telephony.denyRegistration = true
        try {
            coordinator.acquire("before-permission")
            telephony.setCallState(TelephonyManager.CALL_STATE_OFFHOOK)
            shadowOf(Looper.getMainLooper()).idle()
            assertEquals(DeviceCallState.Idle, coordinator.callState.value)
            assertTrue(events.isEmpty())

            telephony.denyRegistration = false
            coordinator.acquire("after-permission")
            shadowOf(Looper.getMainLooper()).idle()
            assertEquals(2, telephony.registrationAttempts)
            assertEquals(DeviceCallState.OffHook, coordinator.callState.value)
            assertEquals(listOf<CallSessionEvent>(CallSessionEvent.Started(0L)), events)

            coordinator.release("before-permission")
            telephony.setCallState(TelephonyManager.CALL_STATE_IDLE)
            shadowOf(Looper.getMainLooper()).idle()
            assertEquals(
                listOf<CallSessionEvent>(CallSessionEvent.Started(0L), CallSessionEvent.Ended(0L)),
                events
            )
        } finally {
            telephony.denyRegistration = false
            coordinator.release("after-permission")
            coordinator.release("cleanup")
        }
    }

    /** Model Android denying listener registration before READ_PHONE_STATE is granted. */
    @Implements(TelephonyManager::class)
    class RegistrationPermissionShadow : ShadowTelephonyManager() {
        var denyRegistration = false
        var registrationAttempts = 0

        @Implementation(minSdk = Build.VERSION_CODES.S)
        override fun registerTelephonyCallback(
            executor: Executor,
            @ClassName("android.telephony.TelephonyCallback") callback: Any
        ) {
            registrationAttempts++
            if (denyRegistration) throw SecurityException("READ_PHONE_STATE denied in fixture")
            super.registerTelephonyCallback(executor, callback)
        }
    }
}
