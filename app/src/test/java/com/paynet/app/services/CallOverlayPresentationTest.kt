// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.services

import android.app.Application
import android.content.Context
import android.content.ContextWrapper
import android.content.res.Resources
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.TextView
import com.paynet.app.R
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode
import org.robolectric.shadows.ShadowChoreographer
import java.time.Duration
import java.util.concurrent.TimeUnit

private const val BEFORE_PIN_DELAY_MS = 2499L
private const val BEFORE_AUTH_DELAY_MS = 16499L
private const val MID_MILESTONE_MS = 500L
private const val AFTER_MILESTONE_MS = 1100L
private const val PARTIAL_CALL_MS = 15000L
private const val AFTER_CALL_MS = 35000L
private const val CONNECTING_PROGRESS = 100
private const val IN_CALL_PROGRESS = 200
private const val CALL_CEILING = 900
private const val BAR_MAX = 1000
private const val UNITS_PER_PERCENT = 10
private const val FRAME_MS = 16L

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
@LooperMode(LooperMode.Mode.PAUSED)
class CallOverlayPresentationTest {
    private val application: Application = RuntimeEnvironment.getApplication()
    private val controllers = mutableListOf<CallOverlayProgress>()
    private val handler = Handler(Looper.getMainLooper())
    private var originalFrameDelay = Duration.ZERO
    private var originallyPaused = false
    private val context: Context = object : ContextWrapper(application) {
        // Keep these display tests independent of the application resource table.
        private val strings = object : Resources(
            application.assets,
            application.resources.displayMetrics,
            application.resources.configuration
        ) {
            override fun getText(id: Int): CharSequence = when (id) {
                R.string.amount_rupees -> "₹%1\$s"
                R.string.percent_format -> "%1\$d%%"
                R.string.overlay_call_progress_estimate -> "Call progress estimate, %1\$d percent"
                R.string.overlay_processing_payment -> "Processing payment"
                R.string.overlay_connecting -> "Connecting"
                R.string.overlay_pin_notice -> "PIN instruction"
                R.string.overlay_authentication_notice -> "Authentication instruction"
                else -> super.getText(id)
            }
        }
        override fun getResources(): Resources = strings
    }

    @Before fun controlAnimationFrames() {
        originalFrameDelay = ShadowChoreographer.getFrameDelay()
        originallyPaused = ShadowChoreographer.isPaused()
        // PAUSED Loopers still auto-drain vsync by default in Robolectric 4.14.
        // Pause that separate clock so intermediate frames remain observable.
        ShadowChoreographer.setPaused(true)
        ShadowChoreographer.setFrameDelay(Duration.ofMillis(FRAME_MS))
    }

    @After fun stopAnimations() {
        controllers.forEach(CallOverlayProgress::stop)
        handler.removeCallbacksAndMessages(null)
        ShadowChoreographer.setFrameDelay(originalFrameDelay)
        ShadowChoreographer.setPaused(originallyPaused)
    }

    @Test fun bindingResetsAReusedViewAndShowsTheCallEstimate() {
        val root = fixture()
        CallOverlayView.showProgress(root, CALL_CEILING)

        CallOverlayView.bind(root, "9876543210", "99")

        assertFalse(bar(root).isIndeterminate)
        assertEquals(BAR_MAX, bar(root).max)
        assertEquals(0, bar(root).progress)
        assertEquals("0%", percentage(root).text.toString())
        assertEquals(View.VISIBLE, percentage(root).visibility)
        assertEquals("Call progress estimate, 0 percent", percentage(root).contentDescription)
        assertEquals("₹99.00", root.findViewById<TextView>(R.id.amountText).text.toString())
        assertEquals("Connecting", root.findViewById<TextView>(R.id.stepText).text.toString())
    }

    @Test fun connectingAdvancesFillAndPercentageTogether() {
        val root = fixture()
        controller(root).showConnecting()
        advance(MID_MILESTONE_MS)
        assertTrue(
            "Connecting should be between milestones: ${bar(root).progress}",
            bar(root).progress in 1 until CONNECTING_PROGRESS
        )
        assertSynchronized(root)
        advance(AFTER_MILESTONE_MS)
        assertEquals(CONNECTING_PROGRESS, bar(root).progress)
        assertSynchronized(root)
    }

    @Test fun inCallPacingAdvancesOnceAndNeverDeclaresCompletion() {
        val root = fixture()
        val progress = controller(root)
        progress.showInCall()
        advance(AFTER_MILESTONE_MS)
        assertTrue(
            "The call should reach its 20% milestone: ${bar(root).progress}",
            bar(root).progress >= IN_CALL_PROGRESS
        )
        advance(PARTIAL_CALL_MS)
        assertTrue(
            "The call should still be advancing: ${bar(root).progress}",
            bar(root).progress in IN_CALL_PROGRESS until CALL_CEILING
        )
        val beforeDuplicate = bar(root).progress
        progress.showInCall()
        assertEquals("A repeated phase cannot restart or rewind pacing", beforeDuplicate, bar(root).progress)
        advance(PARTIAL_CALL_MS)
        assertEquals(CALL_CEILING, bar(root).progress)
        advance(AFTER_CALL_MS)
        assertEquals(CALL_CEILING, bar(root).progress)
        assertEquals("90%", percentage(root).text.toString())
        assertSynchronized(root)
    }

    @Test fun stoppingCancelsFramesAndCannotRestartTheOldView() {
        val root = fixture()
        val progress = controller(root)
        progress.showInCall()
        advance(AFTER_MILESTONE_MS)
        progress.stop()
        val stopped = bar(root).progress
        progress.showConnecting()
        progress.showInCall()
        advance(AFTER_CALL_MS)
        assertEquals(stopped, bar(root).progress)
        assertSynchronized(root)
    }

    @Test fun detachedViewStopsAndAReplacementStartsIndependently() {
        val oldRoot = fixture()
        val oldProgress = controller(oldRoot)
        oldProgress.showInCall()
        advance(AFTER_MILESTONE_MS)
        oldProgress.onViewDetachedFromWindow(oldRoot)
        val stopped = bar(oldRoot).progress
        val replacement = fixture()
        controller(replacement).showConnecting()
        advance(AFTER_MILESTONE_MS)
        assertEquals(stopped, bar(oldRoot).progress)
        assertEquals(CONNECTING_PROGRESS, bar(replacement).progress)
    }

    @Test fun reducedMotionUsesStablePhaseMilestonesWithoutTimedCreep() {
        val root = fixture()
        val progress = controller(root, animationsEnabled = false)
        progress.showConnecting()
        assertEquals(CONNECTING_PROGRESS, bar(root).progress)
        progress.showInCall()
        assertEquals(IN_CALL_PROGRESS, bar(root).progress)
        advance(AFTER_CALL_MS)
        assertEquals(IN_CALL_PROGRESS, bar(root).progress)
        assertEquals("20%", percentage(root).text.toString())
        assertSynchronized(root)
    }

    @Test fun displayClampsOutOfRangeEstimatesBelowPaymentCompletion() {
        val root = fixture()
        CallOverlayView.showProgress(root, Int.MAX_VALUE)
        assertEquals(CALL_CEILING, bar(root).progress)
        assertEquals("90%", percentage(root).text.toString())
        CallOverlayView.showProgress(root, Int.MIN_VALUE)
        assertEquals(0, bar(root).progress)
        assertEquals("0%", percentage(root).text.toString())
    }

    @Test fun bankInstructionsKeepTheirExistingTiming() {
        val root = fixture()
        val instruction = root.findViewById<TextView>(R.id.stepText)
        instruction.text = "Initial instruction"

        CallOverlayView.scheduleBankGuidance(root, handler)
        advance(BEFORE_PIN_DELAY_MS)
        assertEquals("Initial instruction", instruction.text.toString())
        advance(1)
        assertEquals(context.getString(R.string.overlay_pin_notice), instruction.text.toString())
        advance(BEFORE_AUTH_DELAY_MS)
        assertFalse(instruction.text.toString() == context.getString(R.string.overlay_authentication_notice))
        advance(1)
        assertEquals(context.getString(R.string.overlay_authentication_notice), instruction.text.toString())
    }

    private fun fixture(): FrameLayout = FrameLayout(context).apply {
        addView(ProgressBar(context, null, android.R.attr.progressBarStyleHorizontal).apply { id = R.id.progressBar })
        val textIds = listOf(
            R.id.progressPercent,
            R.id.amountText,
            R.id.currentStepText,
            R.id.statusText,
            R.id.stepText
        )
        for (viewId in textIds) {
            addView(TextView(context).apply { id = viewId })
        }
        CallOverlayView.bind(this, "9876543210", "99")
    }

    private fun controller(root: View, animationsEnabled: Boolean = true): CallOverlayProgress =
        CallOverlayProgress(root) { animationsEnabled }.also(controllers::add)

    private fun bar(root: View): ProgressBar = root.findViewById(R.id.progressBar)
    private fun percentage(root: View): TextView = root.findViewById(R.id.progressPercent)
    private fun advance(milliseconds: Long) {
        var remaining = milliseconds
        while (remaining > 0) {
            val step = minOf(FRAME_MS, remaining)
            shadowOf(Looper.getMainLooper()).idleFor(step, TimeUnit.MILLISECONDS)
            remaining -= step
        }
    }

    private fun assertSynchronized(root: View) {
        assertEquals("${bar(root).progress / UNITS_PER_PERCENT}%", percentage(root).text.toString())
        assertFalse(bar(root).isIndeterminate)
    }
}
