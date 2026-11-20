// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.services

import android.animation.Keyframe
import android.animation.PropertyValuesHolder
import android.animation.ValueAnimator
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.animation.DecelerateInterpolator
import android.view.animation.LinearInterpolator
import android.widget.ProgressBar
import android.widget.TextView
import com.flowpay.app.R
import com.flowpay.app.utils.CurrencyFormat
import com.flowpay.app.utils.PhoneNumberUtils

/** Display-only construction, independent of the service's payment/session lifecycle. */
internal object CallOverlayView {
    private const val VISIBLE_PHONE_DIGITS = 4
    private const val ENTRANCE_SCALE = 0.98f
    private const val ENTRANCE_MS = 180L
    private const val ENTRANCE_DECELERATION = 1.5f
    private const val PIN_GUIDANCE_DELAY_MS = 2500L
    private const val AUTH_GUIDANCE_DELAY_AFTER_PIN_MS = 16500L
    private const val PROGRESS_MAX = 1000
    private const val PROGRESS_CEILING = 900
    private const val UNITS_PER_PERCENT = 10

    fun bind(view: View?, phoneNumber: String, amount: String) {
        view ?: return
        val context = view.context
        view.findViewById<TextView>(R.id.amountText)?.text =
            context.getString(R.string.amount_rupees, CurrencyFormat.inr(amount))
        view.findViewById<TextView>(R.id.currentStepText)?.text =
            PhoneNumberUtils.formatPhoneForDisplay(phoneNumber, VISIBLE_PHONE_DIGITS)
        showProgress(view, 0)
        view.findViewById<TextView>(R.id.statusText)?.text = context.getString(R.string.overlay_processing_payment)
        view.findViewById<TextView>(R.id.stepText)?.text = context.getString(R.string.overlay_connecting)
    }

    /** Call guidance only: elapsed time never reaches 100% or declares a payment outcome. */
    fun showProgress(view: View, value: Int) {
        val progress = value.coerceIn(0, PROGRESS_CEILING)
        view.findViewById<ProgressBar>(R.id.progressBar)?.apply {
            isIndeterminate = false
            max = PROGRESS_MAX
            this.progress = progress
        }
        view.findViewById<TextView>(R.id.progressPercent)?.apply {
            visibility = View.VISIBLE
            val percentage = progress / UNITS_PER_PERCENT
            val label = context.getString(R.string.percent_format, percentage)
            if (text.toString() != label || contentDescription == null) {
                text = label
                contentDescription = context.getString(R.string.overlay_call_progress_estimate, percentage)
            }
        }
    }

    fun scheduleBankGuidance(view: View, handler: android.os.Handler): CallOverlayMessageMotion {
        val motion = CallOverlayMessageMotion(view)
        val pinGuidance = Runnable { motion.show(R.string.overlay_pin_notice) }
        val authenticationGuidance = Runnable { motion.show(R.string.overlay_authentication_notice) }
        view.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(view: View) = Unit

            override fun onViewDetachedFromWindow(view: View) {
                handler.removeCallbacks(pinGuidance)
                handler.removeCallbacks(authenticationGuidance)
                view.removeOnAttachStateChangeListener(this)
            }
        })
        handler.postDelayed(pinGuidance, PIN_GUIDANCE_DELAY_MS)
        handler.postDelayed(
            authenticationGuidance,
            PIN_GUIDANCE_DELAY_MS + AUTH_GUIDANCE_DELAY_AFTER_PIN_MS
        )
        return motion
    }

    fun windowParameters() = WindowManager.LayoutParams().apply {
        // minSdk is 29; only the supported application-overlay type is reachable.
        type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH or
            WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED or
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
        format = PixelFormat.TRANSLUCENT
        width = WindowManager.LayoutParams.MATCH_PARENT
        height = WindowManager.LayoutParams.MATCH_PARENT
        gravity = Gravity.CENTER
        title = "Flowpay Overlay"
    }

    fun prepareEntrance(view: View?) {
        view?.apply {
            val animate = ValueAnimator.areAnimatorsEnabled()
            alpha = if (animate) 0f else 1f
            scaleX = if (animate) ENTRANCE_SCALE else 1f
            scaleY = scaleX
            translationY = 0f
        }
    }

    fun animateEntrance(view: View?) {
        if (!ValueAnimator.areAnimatorsEnabled()) {
            view?.apply {
                animate().cancel()
                alpha = 1f
                scaleX = 1f
                scaleY = 1f
                translationY = 0f
            }
            return
        }
        view?.animate()?.alpha(1f)?.scaleX(1f)?.scaleY(1f)?.translationY(0f)
            ?.setDuration(ENTRANCE_MS)?.setInterpolator(DecelerateInterpolator(ENTRANCE_DECELERATION))
            ?.start()
    }
}

/** Owns display pacing only; it cannot start a call or change a payment/session result. */
internal class CallOverlayProgress(
    private val view: View,
    private val animationsEnabled: () -> Boolean = ValueAnimator::areAnimatorsEnabled
) : View.OnAttachStateChangeListener {
    private var animator: ValueAnimator? = null
    private var phase: Phase? = null

    init {
        view.addOnAttachStateChangeListener(this)
    }

    fun showConnecting() {
        if (phase != null) return
        phase = Phase.CONNECTING
        animate(ValueAnimator.ofInt(currentProgress(), CONNECTING_PROGRESS), CONNECTING_PROGRESS, MILESTONE_MS)
    }

    fun showInCall() {
        if (phase == Phase.IN_CALL || phase == Phase.STOPPED) return
        phase = Phase.IN_CALL
        val current = currentProgress()
        val milestone = maxOf(current, IN_CALL_PROGRESS)
        val frames = PropertyValuesHolder.ofKeyframe(
            "progress",
            Keyframe.ofInt(0f, current),
            Keyframe.ofInt(MILESTONE_MS.toFloat() / CALL_PACING_MS, milestone),
            Keyframe.ofInt(1f, CALL_CEILING)
        )
        animate(ValueAnimator.ofPropertyValuesHolder(frames), milestone, CALL_PACING_MS)
    }

    fun stop() {
        phase = Phase.STOPPED
        cancelAnimation()
        view.removeOnAttachStateChangeListener(this)
    }

    override fun onViewAttachedToWindow(view: View) = Unit

    override fun onViewDetachedFromWindow(view: View) = stop()

    private fun currentProgress(): Int = view.findViewById<ProgressBar>(R.id.progressBar)?.progress ?: 0

    private fun animate(next: ValueAnimator, reducedMotionProgress: Int, durationMs: Long) {
        cancelAnimation()
        if (animationsEnabled()) {
            animator = next.apply {
                duration = durationMs
                interpolator = LinearInterpolator()
                addUpdateListener { CallOverlayView.showProgress(view, it.animatedValue as Int) }
                start()
            }
        } else {
            // Reduced motion retains a clear phase milestone without continuous movement.
            CallOverlayView.showProgress(view, reducedMotionProgress)
        }
    }

    private fun cancelAnimation() {
        animator?.apply {
            removeAllUpdateListeners()
            cancel()
        }
        animator = null
    }

    private enum class Phase { CONNECTING, IN_CALL, STOPPED }

    private companion object {
        const val CONNECTING_PROGRESS = 100
        const val IN_CALL_PROGRESS = 200
        const val CALL_CEILING = 900
        const val MILESTONE_MS = 1000L
        const val CALL_PACING_MS = 31000L
    }
}
