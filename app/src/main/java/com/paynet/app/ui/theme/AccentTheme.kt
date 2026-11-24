// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.theme

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import com.paynet.app.ui.home.HomeAppearance
import com.paynet.app.ui.home.rememberHomeAppearance

data class PayNetAccentTheme(
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

val PayNetVioletTheme = PayNetAccentTheme(
    primary = Color(0xFF6A4FF0),
    primaryDark = Color(0xFF4A32C0),
    headerGradientStart = Color(0xFF8B7CFF),
    headerGradientEnd = Color(0xFF6A4FF0),
    accent = Color(0xFF6A4FF0),
    accentLight = Color(0xFF9D8FFF)
)

val LocalPayNetAccentTheme = compositionLocalOf { PayNetVioletTheme }

val MonochromeAccentTheme = PayNetAccentTheme(
    primary = Color(0xFFF0F0EE),
    primaryDark = Color(0xFFD8D8D5),
    headerGradientStart = Color(0xFFFBFBFA),
    headerGradientEnd = Color(0xFFE8E8E5),
    accent = Color(0xFFF0F0EE),
    accentLight = Color.White,
    onAccent = Color(0xFF202023),
    settingsControl = Color.Black
)

fun accentThemeFor(monochrome: Boolean) = if (monochrome) MonochromeAccentTheme else PayNetVioletTheme

fun accentThemeFor(appearance: HomeAppearance) = accentThemeFor(appearance.monochrome)

/** One saved colour selection, observed live by every Compose Activity. */
@Composable
fun PayNetAccentProvider(content: @Composable () -> Unit) {
    val appearance by rememberHomeAppearance()
    CompositionLocalProvider(LocalPayNetAccentTheme provides accentThemeFor(appearance), content = content)
}
