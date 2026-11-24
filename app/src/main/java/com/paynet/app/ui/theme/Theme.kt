// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import com.paynet.app.utils.findComponentActivity

/**
 * PayNet is deliberately dark-only: the payment overlay, dialogs and home
 * screen are all designed against a black surface. Dynamic (Material You)
 * color is intentionally NOT used — on Android 12+ it silently replaced the
 * brand palette with wallpaper-derived colors. The old "light" scheme was
 * fake (black background with light accents) and has been removed.
 */
@Composable
fun PayNetTheme(
    content: @Composable () -> Unit
) {
    val accent = LocalPayNetAccentTheme.current
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = view.context.findComponentActivity()?.window ?: return@SideEffect
            // Set status bar to black to match the dark UI theme
            window.statusBarColor = android.graphics.Color.parseColor("#08070C")
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = accent.primary, onPrimary = accent.onAccent,
            secondary = accent.accent, onSecondary = accent.onAccent,
            tertiary = accent.accentLight, onTertiary = accent.onAccent,
            background = PayNetBlack, surface = PayNetDarkGray,
            onBackground = PayNetTextWhite, onSurface = PayNetTextWhite
        ),
        typography = Typography,
        content = content
    )
}
