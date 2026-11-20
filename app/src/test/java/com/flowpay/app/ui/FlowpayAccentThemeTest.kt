package com.flowpay.app.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import com.flowpay.app.ui.home.HomeAppearance
import com.flowpay.app.ui.theme.BlueAccentTheme
import com.flowpay.app.ui.theme.MonochromeAccentTheme
import com.flowpay.app.ui.theme.accentThemeFor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

private const val LIGHT_CHANNEL_MIN = .9f
private const val DARK_CHANNEL_MAX = .2f
private const val NORMAL_TEXT_CONTRAST_MIN = 4.5f
private const val CONTRAST_LUMINANCE_OFFSET = .05f

class FlowpayAccentThemeTest {
    @Test fun monochromeUsesDarkInkOnLightControls() {
        val palette = accentThemeFor(true)
        assertEquals(MonochromeAccentTheme, palette)
        assertTrue(palette.primary.red > LIGHT_CHANNEL_MIN)
        assertTrue(palette.onAccent.red < DARK_CHANNEL_MAX)
        assertNotEquals(palette.primary, palette.onAccent)
    }

    @Test fun blueSelectionKeepsTheEstablishedPalette() {
        assertEquals(BlueAccentTheme, accentThemeFor(false))
        assertTrue(BlueAccentTheme.primary.blue > BlueAccentTheme.primary.red)
        assertNotEquals(accentThemeFor(false).primary, accentThemeFor(true).primary)
    }

    @Test fun monochromeControlsKeepReadableForegrounds() {
        val palette = accentThemeFor(HomeAppearance())
        assertTrue(contrast(palette.primaryDark, palette.onPrimaryDark) >= NORMAL_TEXT_CONTRAST_MIN)
        assertTrue(contrast(palette.primary, palette.onAccent) >= NORMAL_TEXT_CONTRAST_MIN)
    }

    @Test fun appearanceSelectionPreservesEstablishedPalettes() {
        assertEquals(MonochromeAccentTheme, accentThemeFor(HomeAppearance()))
        assertEquals(BlueAccentTheme, accentThemeFor(HomeAppearance(monochrome = false)))
    }

    private fun contrast(first: Color, second: Color): Float {
        val firstLuminance = first.luminance()
        val secondLuminance = second.luminance()
        return (maxOf(firstLuminance, secondLuminance) + CONTRAST_LUMINANCE_OFFSET) /
            (minOf(firstLuminance, secondLuminance) + CONTRAST_LUMINANCE_OFFSET)
    }
}
