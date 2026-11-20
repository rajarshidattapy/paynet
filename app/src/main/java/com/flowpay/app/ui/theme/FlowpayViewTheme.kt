// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.theme

import android.content.Context
import android.content.SharedPreferences
import android.content.res.ColorStateList
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.compose.ui.graphics.toArgb
import com.flowpay.app.R
import com.flowpay.app.ui.home.HomeAppearance

/** The same saved palette for XML screens, payment prompts and app-owned overlays. */
object FlowpayViewTheme {
    fun observe(root: View, apply: (View) -> Unit) {
        apply(root)
        if (root.getTag(R.id.flowpayPaletteObserver) != null) return
        val prefs = root.context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == null || key == "home_monochrome") root.post { apply(root) }
        }
        val attach = object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(view: View) {
                prefs.registerOnSharedPreferenceChangeListener(listener)
                apply(view)
            }
            override fun onViewDetachedFromWindow(view: View) {
                prefs.unregisterOnSharedPreferenceChangeListener(
                    listener
                )
            }
        }
        root.setTag(R.id.flowpayPaletteObserver, attach)
        root.addOnAttachStateChangeListener(attach)
        if (root.isAttachedToWindow) prefs.registerOnSharedPreferenceChangeListener(listener)
    }

    private fun palette(root: View) = accentThemeFor(HomeAppearance.read(root.context))

    private fun foreground(view: View, color: Int) {
        when (view) {
            is TextView -> view.setTextColor(color)
            is ImageView -> view.imageTintList = ColorStateList.valueOf(color)
        }
        if (view is ViewGroup) for (i in 0 until view.childCount) foreground(view.getChildAt(i), color)
    }

    fun paymentAnswers(root: View) {
        val palette = palette(root)
        root.findViewById<View>(R.id.paymentAnswerYes)?.let { button ->
            val fill = GradientDrawable().apply {
                cornerRadius = 14f * root.resources.displayMetrics.density
                setColor(palette.primaryDark.toArgb())
            }
            val ripple = ColorStateList.valueOf(palette.onPrimaryDark.copy(alpha = .16f).toArgb())
            button.background = RippleDrawable(ripple, fill, null)
            foreground(button, palette.onPrimaryDark.toArgb())
        }
    }

    fun paymentPrompt(root: View) {
        paymentAnswers(root)
        val palette = palette(root)
        root.findViewById<ImageView>(R.id.paymentPromptIcon)?.apply {
            imageTintList = ColorStateList.valueOf(palette.primary.toArgb())
            backgroundTintList = ColorStateList.valueOf(palette.primary.copy(alpha = .14f).toArgb())
        }
    }

    fun scanner(root: View) {
        // Camera chrome stays neutral in every app theme.
        val palette = MonochromeAccentTheme
        paymentAnswers(root)
        val frame = root.findViewById<ViewGroup>(R.id.scannerOverlay)
        if (frame != null) {
            for (i in 0 until frame.childCount) {
                (frame.getChildAt(i) as? ImageView)?.imageTintList =
                    ColorStateList.valueOf(palette.primary.toArgb())
            }
        }
        for (id in listOf(R.id.btnBack, R.id.btnFlash, R.id.btnGallery)) {
            root.findViewById<ImageView>(id)?.let { scannerControl(it, id == R.id.btnFlash) }
        }
        root.findViewById<View>(R.id.instructionsBox)?.apply {
            backgroundTintList = ColorStateList.valueOf(palette.headerGradientEnd.toArgb())
            foreground(this, palette.onAccent.toArgb())
        }
        root.findViewById<ProgressBar>(R.id.progressBar)?.apply {
            indeterminateTintList = ColorStateList.valueOf(palette.primary.toArgb())
            progressTintList = ColorStateList.valueOf(palette.primary.toArgb())
        }
    }

    private fun scannerControl(control: ImageView, flash: Boolean) {
        val palette = MonochromeAccentTheme
        val ink = if (control.isSelected) palette.onAccent else palette.primary
        control.imageTintList = ColorStateList.valueOf(ink.toArgb())
        if (flash) {
            control.backgroundTintList = if (control.isSelected) {
                ColorStateList.valueOf(palette.primary.toArgb())
            } else {
                null
            }
        }
    }

    fun callOverlay(root: View) {
        val palette = palette(root)
        // This existing overlay uses a light card, so monochrome foregrounds are dark.
        val ink = if (HomeAppearance.read(
                root.context
            ).monochrome
        ) {
            palette.onAccent.toArgb()
        } else {
            palette.primaryDark.toArgb()
        }
        for (id in listOf(R.id.flowPayLogo, R.id.progressPercent)) root.findViewById<TextView>(id)?.setTextColor(ink)
        root.findViewById<View>(R.id.securityBadge)?.let {
            foreground(it, ink)
            it.backgroundTintList = ColorStateList.valueOf((ink and 0x00FFFFFF) or 0x18000000)
        }
        root.findViewById<ProgressBar>(R.id.progressBar)?.apply {
            progressTintList = ColorStateList.valueOf(ink)
            indeterminateTintList = ColorStateList.valueOf(ink)
        }
    }
}
