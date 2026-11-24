// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.services

import android.animation.ValueAnimator
import android.transition.ChangeBounds
import android.transition.TransitionManager
import android.view.View
import android.view.ViewGroup
import android.view.animation.AnimationUtils
import android.widget.TextView
import com.paynet.app.R

/** Coordinates guidance copy and card reflow without owning any payment or call state. */
internal class CallOverlayMessageMotion(
    private val root: View,
    private val animationsEnabled: () -> Boolean = ValueAnimator::areAnimatorsEnabled
) : View.OnAttachStateChangeListener {
    private val message: TextView = root.findViewById(R.id.stepText)
    private var stopped = false

    init {
        root.addOnAttachStateChangeListener(this)
    }

    fun show(textResource: Int) {
        if (stopped) return
        resetMotion()
        if (!animationsEnabled() || !root.isAttachedToWindow || !root.isLaidOut) {
            message.setText(textResource)
            return
        }
        val easing = AnimationUtils.loadInterpolator(root.context, R.interpolator.paynet_settle)
        val distance = SHIFT_DP * root.resources.displayMetrics.density
        message.animate().alpha(0f).translationY(-distance).setDuration(FADE_OUT_MS)
            .setInterpolator(easing).withEndAction {
                if (!stopped) {
                    (root as? ViewGroup)?.let { parent ->
                        TransitionManager.beginDelayedTransition(
                            parent,
                            ChangeBounds().setDuration(REFLOW_MS).setInterpolator(easing)
                        )
                    }
                    message.setText(textResource)
                    message.translationY = distance
                    message.animate().alpha(1f).translationY(0f).setDuration(REFLOW_MS)
                        .setInterpolator(easing).start()
                }
            }.start()
    }

    fun stop() {
        stopped = true
        resetMotion()
        root.removeOnAttachStateChangeListener(this)
    }

    override fun onViewAttachedToWindow(view: View) = Unit

    override fun onViewDetachedFromWindow(view: View) = stop()

    private fun resetMotion() {
        message.animate().withEndAction(null).cancel()
        message.alpha = 1f
        message.translationY = 0f
        (root as? ViewGroup)?.let(TransitionManager::endTransitions)
    }

    private companion object {
        const val SHIFT_DP = 6f
        const val FADE_OUT_MS = 100L
        const val REFLOW_MS = 300L
    }
}
