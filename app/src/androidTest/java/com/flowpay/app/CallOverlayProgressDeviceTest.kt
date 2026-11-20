// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.animation.ValueAnimator
import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.content.IntentFilter
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import com.flowpay.app.services.CallOverlayMessageMotion
import com.flowpay.app.services.CallOverlayProgress
import com.flowpay.app.services.CallOverlayView
import com.flowpay.app.ui.activities.TransactionHistoryActivity
import com.flowpay.app.ui.theme.FlowpayViewTheme
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

private const val OVERLAY_TIMEOUT_MS = 6000L
private const val MOTION_FRAME_COUNT = 28
private const val FRAME_POLL_MS = 25L
private const val STOP_OBSERVATION_MS = 1200L
private const val CONNECTING_UNITS = 100
private const val IN_CALL_UNITS = 200
private const val MAX_CALL_UNITS = 900
private const val UNITS_PER_PERCENT = 10

/** Actual overlay rendering in an isolated Activity; no service, call or phone-setting changes. */
@RunWith(AndroidJUnit4::class)
class CallOverlayProgressDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val device = UiDevice.getInstance(instrumentation)
    private val monitors = mutableListOf<Instrumentation.ActivityMonitor>()
    private val controllers = mutableListOf<CallOverlayProgress>()
    private val messageMotions = mutableListOf<CallOverlayMessageMotion>()
    private val handler = Handler(Looper.getMainLooper())
    private var scenario: ActivityScenario<TransactionHistoryActivity>? = null

    @Before fun isolatedOnly() {
        assertEquals("Refusing overlay fixtures in production", "com.flowpay.app.setupcheck", context.packageName)
        for (action in listOf(
            Intent.ACTION_CALL, Intent.ACTION_DIAL, Intent.ACTION_VIEW,
            "android.intent.action.CALL_PRIVILEGED", "android.intent.action.CALL_EMERGENCY"
        )) {
            monitors += instrumentation.addMonitor(
                IntentFilter(action).apply { addDataScheme("tel") },
                Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null), true
            )
        }
        device.wakeUp()
    }

    @After fun cleanup() {
        try {
            instrumentation.runOnMainSync {
                controllers.forEach(CallOverlayProgress::stop)
                messageMotions.forEach(CallOverlayMessageMotion::stop)
                handler.removeCallbacksAndMessages(null)
            }
            scenario?.close()
            assertEquals("Overlay fixtures must never attempt a call", 0, monitors.sumOf { it.hits })
        } finally {
            monitors.forEach(instrumentation::removeMonitor)
        }
    }

    @Test fun visiblePercentageTracksTheBarAndCancelStopsUpdates() {
        val activity = ActivityScenario.launch(TransactionHistoryActivity::class.java).also { scenario = it }
        lateinit var root: View
        lateinit var progress: CallOverlayProgress
        activity.onActivity { screen ->
            root = render(screen)
            progress = controller(root)
            progress.showConnecting()
            root.findViewById<View>(R.id.terminateButton).setOnClickListener {
                // Match the service's explicit stop followed by removing its view, without any call operation.
                progress.stop()
                screen.setContentView(FrameLayout(screen))
            }
        }
        awaitProgress(root) { it == CONNECTING_UNITS }
        assertSynchronized(root)
        screenshot("overlay-progress-connecting")

        activity.onActivity {
            root.findViewById<TextView>(R.id.stepText).setText(R.string.overlay_sending_request)
            progress.showInCall()
            CallOverlayView.scheduleBankGuidance(root, handler)
        }
        val animated = ValueAnimator.areAnimatorsEnabled()
        awaitProgress(root) { if (animated) it > IN_CALL_UNITS else it == IN_CALL_UNITS }
        assertSynchronized(root)
        screenshot("overlay-progress-active")
        requireNotNull(device.findObject(By.res(context.packageName, "terminateButton"))).click()
        instrumentation.waitForIdleSync()
        val stopped = readProgress(root)
        SystemClock.sleep(STOP_OBSERVATION_MS)
        assertEquals(stopped, readProgress(root))
        assertFalse("Cancel removes the fixture", root.isAttachedToWindow)
    }

    @Test fun recreationDetachesOldPacingAndNewOverlayRemainsIndependent() {
        val activity = ActivityScenario.launch(TransactionHistoryActivity::class.java).also { scenario = it }
        lateinit var oldRoot: View
        activity.onActivity { screen ->
            oldRoot = render(screen)
            controller(oldRoot).showInCall()
            CallOverlayView.scheduleBankGuidance(oldRoot, handler)
        }
        awaitProgress(oldRoot) { it >= IN_CALL_UNITS }
        activity.recreate()
        val detachedProgress = readProgress(oldRoot)
        val detachedGuidance = readGuidance(oldRoot)
        lateinit var replacement: View
        activity.onActivity { screen ->
            replacement = render(screen)
            controller(replacement).showConnecting()
        }
        awaitProgress(replacement) { it == CONNECTING_UNITS }
        SystemClock.sleep(STOP_OBSERVATION_MS)
        assertFalse(oldRoot.isAttachedToWindow)
        assertEquals("Detached animation must stop", detachedProgress, readProgress(oldRoot))
        assertEquals("Detached guidance must not update", detachedGuidance, readGuidance(oldRoot))
        assertSynchronized(replacement)
        screenshot("overlay-progress-recreated")
    }

    @Test fun guidanceCopyAndCardHeightAnimateTogether() {
        val activity = ActivityScenario.launch(TransactionHistoryActivity::class.java).also { scenario = it }
        lateinit var root: View
        lateinit var motion: CallOverlayMessageMotion
        activity.onActivity { screen ->
            root = render(screen)
            root.findViewById<TextView>(R.id.stepText).setText(R.string.overlay_pin_notice)
            motion = CallOverlayMessageMotion(root).also(messageMotions::add)
        }
        device.waitForIdle()
        screenshot("guidance-pin-before")
        val heights = mutableSetOf<Int>()
        var oldHeight = 0
        instrumentation.runOnMainSync {
            oldHeight = root.findViewById<View>(R.id.overlayContainer).height
            motion.show(R.string.overlay_authentication_notice)
            if (ValueAnimator.areAnimatorsEnabled()) {
                assertEquals(context.getString(R.string.overlay_pin_notice), readText(root))
            }
        }
        val alphas = mutableListOf<Float>()
        repeat(MOTION_FRAME_COUNT) {
            SystemClock.sleep(FRAME_POLL_MS)
            instrumentation.runOnMainSync {
                heights += root.findViewById<View>(R.id.overlayContainer).height
                alphas += root.findViewById<TextView>(R.id.stepText).alpha
            }
        }
        instrumentation.runOnMainSync {
            val text = root.findViewById<TextView>(R.id.stepText)
            assertEquals(context.getString(R.string.overlay_authentication_notice), text.text.toString())
            assertEquals(1f, text.alpha, 0f)
            assertEquals(0f, text.translationY, 0f)
            assertTrue("The whole instruction must fit after reflow", text.height >= text.layout.height)
            if (ValueAnimator.areAnimatorsEnabled()) {
                assertTrue("Guidance should fade between messages", alphas.any { it > 0f && it < 1f })
                if (oldHeight != root.findViewById<View>(R.id.overlayContainer).height) {
                    assertTrue("The card must resize across intermediate frames", heights.size > 2)
                }
            }
        }
        screenshot("guidance-auth-after")
    }

    @Test fun guidanceRespectsReducedMotionAndDetachCancelsPendingCopy() {
        val activity = ActivityScenario.launch(TransactionHistoryActivity::class.java).also { scenario = it }
        lateinit var root: View
        activity.onActivity { screen ->
            root = render(screen)
        }
        device.waitForIdle()
        activity.onActivity { screen ->
            val immediate = CallOverlayMessageMotion(root) { false }.also(messageMotions::add)
            immediate.show(R.string.overlay_pin_notice)
            assertEquals(context.getString(R.string.overlay_pin_notice), readText(root))
            immediate.show(R.string.overlay_authentication_notice)
            assertEquals(context.getString(R.string.overlay_authentication_notice), readText(root))
            immediate.stop()
            immediate.show(R.string.overlay_pin_notice)
            assertEquals(context.getString(R.string.overlay_authentication_notice), readText(root))
            CallOverlayMessageMotion(root).also(messageMotions::add).show(R.string.overlay_pin_notice)
            screen.setContentView(FrameLayout(screen))
        }
        val detached = readGuidance(root)
        SystemClock.sleep(STOP_OBSERVATION_MS)
        assertEquals("Detached text must not be replaced by an old completion", detached, readGuidance(root))
        assertFalse(root.isAttachedToWindow)
    }

    private fun readText(root: View): String = root.findViewById<TextView>(R.id.stepText).text.toString()

    private fun render(activity: TransactionHistoryActivity): View {
        activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val root = activity.layoutInflater.inflate(R.layout.call_overlay_flowpay, null)
        CallOverlayView.bind(root, "9876543210", "99")
        FlowpayViewTheme.callOverlay(root)
        activity.setContentView(root)
        return root
    }

    private fun controller(root: View): CallOverlayProgress = CallOverlayProgress(root).also(controllers::add)

    private fun awaitProgress(root: View, ready: (Int) -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + OVERLAY_TIMEOUT_MS
        while (SystemClock.uptimeMillis() < deadline) {
            if (ready(readProgress(root))) return
            SystemClock.sleep(FRAME_POLL_MS)
        }
        assertTrue("Progress did not reach the expected phase: ${readProgress(root)}", false)
    }

    private fun readProgress(root: View): Int {
        var result = 0
        instrumentation.runOnMainSync { result = root.findViewById<ProgressBar>(R.id.progressBar).progress }
        return result
    }

    private fun readGuidance(root: View): String {
        var result = ""
        instrumentation.runOnMainSync { result = root.findViewById<TextView>(R.id.stepText).text.toString() }
        return result
    }

    private fun assertSynchronized(root: View) {
        instrumentation.runOnMainSync {
            val bar = root.findViewById<ProgressBar>(R.id.progressBar)
            val label = root.findViewById<TextView>(R.id.progressPercent)
            assertFalse(bar.isIndeterminate)
            assertTrue(bar.progress in 0..MAX_CALL_UNITS)
            assertEquals(
                context.getString(R.string.percent_format, bar.progress / UNITS_PER_PERCENT), label.text.toString()
            )
            assertEquals(View.VISIBLE, label.visibility)
            assertTrue("The percentage must fit outside the bar", label.left >= bar.width)
            assertTrue(label.width > 0 && label.height > 0)
        }
    }

    private fun screenshot(name: String) {
        assertTrue(device.takeScreenshot(File(context.getExternalFilesDir(null), "$name.png")))
    }
}
