// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.home

import android.content.Context
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class HomeAppearanceTest {
    private val context: Context = RuntimeEnvironment.getApplication()

    @After fun cleanup() { context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).edit().clear().commit() }

    @Test fun defaultIsModernMonochrome() { assertEquals(HomeAppearance(), HomeAppearance.read(context)) }

    @Test fun classicBluePersistsWithoutTouchingBank() {
        context.getSharedPreferences(
            "FlowpayPrefs",
            Context.MODE_PRIVATE
        ).edit().putString("selected_bank", "sbi").commit()
        val expected = HomeAppearance(classic = true, monochrome = false)
        expected.save(context)
        assertEquals(expected, HomeAppearance.read(context))
        assertEquals(
            "sbi",
            context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).getString("selected_bank", null)
        )
    }

    @Test fun appearanceDoesNotGrantPaymentSetup() {
        HomeAppearance(classic = true).save(context)
        assertNull(com.flowpay.app.data.TestResultsManager(context).getTestResults())
        assertFalse(
            context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).getBoolean("setup_completed", false)
        )
    }

    @Test fun removedColourFallsBackToStoredBlueWithoutChangingOtherPreferences() {
        val prefs = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
        prefs.edit().putBoolean("home_blood_red", true).putBoolean("home_monochrome", false)
            .putString("selected_bank", "sbi").putBoolean("setup_completed", true).commit()
        assertEquals(HomeAppearance(monochrome = false), HomeAppearance.read(context))
        assertTrue(prefs.contains("home_blood_red"))
        assertEquals("sbi", prefs.getString("selected_bank", null))
        assertTrue(prefs.getBoolean("setup_completed", false))
    }

    @Test fun nextSaveRemovesObsoleteColourWithoutChangingSelectionOrSetup() {
        val prefs = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
        prefs.edit().putBoolean("home_blood_red", true).putBoolean("home_monochrome", false)
            .putString("selected_bank", "sbi").putBoolean("setup_completed", true).commit()
        HomeAppearance.read(context).copy(classic = true).save(context)
        assertEquals(HomeAppearance(classic = true, monochrome = false), HomeAppearance.read(context))
        assertFalse(prefs.contains("home_blood_red"))
        assertEquals("sbi", prefs.getString("selected_bank", null))
        assertTrue(prefs.getBoolean("setup_completed", false))
    }

    @Test fun legacyPreferencesKeepExistingBlueAndClassicSelection() {
        context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).edit()
            .putBoolean("home_classic", true).putBoolean("home_monochrome", false).commit()
        assertEquals(HomeAppearance(classic = true, monochrome = false), HomeAppearance.read(context))
    }

    @Test fun removedColourDoesNotOverrideStoredMonochrome() {
        context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).edit()
            .putBoolean("home_monochrome", true).putBoolean("home_blood_red", true).commit()
        assertEquals(HomeAppearance(), HomeAppearance.read(context))
    }
}
