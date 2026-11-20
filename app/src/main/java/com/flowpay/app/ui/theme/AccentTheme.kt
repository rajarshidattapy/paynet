// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.ui.theme

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import com.flowpay.app.ui.home.HomeAppearance
import com.flowpay.app.ui.home.rememberHomeAppearance

data class FlowpayAccentTheme(
    val primary: Color,
    val primaryDark: Color,
    val headerGradientStart: Color,
    val headerGradientEnd: Color,
    val accent: Color,
    val accentLight: Color,
    val onAccent: Color = Color.White,
    val settingsControl: Color = primaryDark,
    val onSettingsControl: Color = Color.White,
    val onPrimaryDark: Color = onAccent
)

val BlueAccentTheme = FlowpayAccentTheme(
    primary = Color(0xFF5B8DEF),
    primaryDark = Color(0xFF1976D2),
    headerGradientStart = Color(0xFF7BA8F5),
    headerGradientEnd = Color(0xFF6A96EE),
    accent = Color(0xFF4A90E2),
    accentLight = Color(0xFF4A9EFF)
)

val LocalFlowpayAccentTheme = compositionLocalOf { BlueAccentTheme }

val MonochromeAccentTheme = FlowpayAccentTheme(
    primary = Color(0xFFF0F0EE),
    primaryDark = Color(0xFFD8D8D5),
    headerGradientStart = Color(0xFFFBFBFA),
    headerGradientEnd = Color(0xFFE8E8E5),
    accent = Color(0xFFF0F0EE),
    accentLight = Color.White,
    onAccent = Color(0xFF202023),
    settingsControl = Color.Black
)

fun accentThemeFor(monochrome: Boolean) = if (monochrome) MonochromeAccentTheme else BlueAccentTheme

fun accentThemeFor(appearance: HomeAppearance) = accentThemeFor(appearance.monochrome)

/** One saved colour selection, observed live by every Compose Activity. */
@Composable
fun FlowpayAccentProvider(content: @Composable () -> Unit) {
    val appearance by rememberHomeAppearance()
    CompositionLocalProvider(LocalFlowpayAccentTheme provides accentThemeFor(appearance), content = content)
}
