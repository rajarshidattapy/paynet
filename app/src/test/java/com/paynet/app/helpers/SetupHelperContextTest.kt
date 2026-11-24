// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.helpers

import android.app.Application
import android.content.Context
import com.paynet.app.data.TestResults
import com.paynet.app.data.TestResultsManager
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
class SetupHelperContextTest {
    private val context: Context = RuntimeEnvironment.getApplication()
    private val preferences = context.getSharedPreferences("PayNetPrefs", Context.MODE_PRIVATE)
    private val results = TestResultsManager(context)
    private val callback = RecordingCallback()
    private val helper = SetupHelper(context, callback)
    private val setup = SetupHelper.SetupData(
        selectedBank = "sbi",
        selectedPrimarySim = "airtel",
        isDualSimEnabled = true,
        selectedSecondarySim = "vodafone",
        disclaimerAccepted = true
    )
    private val confirmed = TestResults(
        ussdEnabled = true,
        upi123Enabled = true,
        timestamp = 123L
    )

    @Before
    fun reset() {
        preferences.edit().clear().commit()
        context.getSharedPreferences("paynet_test_results", Context.MODE_PRIVATE)
            .edit().clear().commit()
        context.deleteDatabase("paynet_database")
    }

    @After
    fun cleanup() = reset()

    @Test
    fun eachBankOrSimContextChangeInvalidatesReadiness() {
        val changes = listOf(
            setup.copy(selectedBank = "hdfc"),
            setup.copy(selectedPrimarySim = "bsnl"),
            setup.copy(isDualSimEnabled = false),
            setup.copy(selectedSecondarySim = "jio")
        )
        for (changed in changes) {
            helper.saveSetupData(setup)
            seedReadiness()

            helper.completeSetup(changed)

            assertNull("Stale readiness for $changed", results.getTestResults())
            assertFalse(preferences.getBoolean("test_configuration_completed", true))
            assertFalse(preferences.contains("user_reported_ussd_not_working"))
            assertTrue(preferences.getBoolean("setup_completed", false))
            assertEquals(changed.selectedBank, preferences.getString("selected_bank", null))
            assertEquals(changed.selectedPrimarySim, preferences.getString("selected_primary_sim", null))
            assertEquals(changed.isDualSimEnabled, preferences.getBoolean("is_dual_sim_enabled", false))
            assertEquals(changed.selectedSecondarySim, preferences.getString("selected_secondary_sim", null))
        }
        assertEquals(changes.size, callback.navigationCount)
        assertTrue(callback.messages.isEmpty())
    }

    @Test
    fun firstSetupClearsOrphanedLegacyReadiness() {
        seedReadiness()

        helper.completeSetup(setup)

        assertNull(results.getTestResults())
        assertFalse(preferences.getBoolean("test_configuration_completed", true))
        assertFalse(preferences.contains("user_reported_ussd_not_working"))
        assertTrue(helper.isSetupCompleted())
        assertEquals(1, callback.navigationCount)
        assertTrue(callback.messages.isEmpty())
    }

    @Test
    fun identicalSetupPreservesReadinessAndCompletion() {
        helper.saveSetupData(setup)
        seedReadiness()

        helper.completeSetup(setup)

        assertEquals(confirmed, results.getTestResults())
        assertTrue(preferences.getBoolean("test_configuration_completed", false))
        assertTrue(SetupHelper.hasUserReportedUssdNotWorking(context))
        assertEquals(1, callback.navigationCount)
        assertTrue(callback.messages.isEmpty())
    }

    @Test
    fun hiddenLegacySecondaryChoicesNeverBlockOrInvalidateUnchangedSetup() {
        preferences.edit()
            .putBoolean(OnboardingFlow.APPEARANCE_COMPLETED, true)
            .putBoolean(OnboardingFlow.WELCOME_COMPLETED, true)
            .putBoolean("home_classic", true)
            .putBoolean("home_monochrome", false)
            .commit()
        val hiddenChoices = listOf("", "retired-carrier", setup.selectedPrimarySim)
        for (secondary in hiddenChoices) {
            val legacySetup = setup.copy(selectedSecondarySim = secondary)
            helper.saveSetupData(legacySetup)
            seedReadiness()

            helper.completeSetup(legacySetup)

            assertEquals(confirmed, results.getTestResults())
            assertTrue(preferences.getBoolean("test_configuration_completed", false))
            assertTrue(preferences.getBoolean("is_dual_sim_enabled", false))
            assertEquals(secondary, preferences.getString("selected_secondary_sim", null))
            assertTrue(preferences.getBoolean(OnboardingFlow.APPEARANCE_COMPLETED, false))
            assertTrue(preferences.getBoolean(OnboardingFlow.WELCOME_COMPLETED, false))
            assertTrue(preferences.getBoolean("home_classic", false))
            assertFalse(preferences.getBoolean("home_monochrome", true))
        }
        assertEquals(hiddenChoices.size, callback.navigationCount)
        assertTrue(callback.messages.isEmpty())
    }

    @Test
    fun directInvalidationPreservesStoredSetupFields() {
        helper.saveSetupData(setup)
        seedReadiness()

        SetupHelper.invalidatePaymentConfiguration(context)

        assertNull(results.getTestResults())
        assertFalse(preferences.getBoolean("test_configuration_completed", true))
        assertFalse(preferences.contains("user_reported_ussd_not_working"))
        assertEquals(setup.selectedBank, preferences.getString("selected_bank", null))
        assertEquals(setup.selectedPrimarySim, preferences.getString("selected_primary_sim", null))
        assertEquals(setup.selectedSecondarySim, preferences.getString("selected_secondary_sim", null))
        assertTrue(preferences.getBoolean("is_dual_sim_enabled", false))
        assertTrue(preferences.getBoolean("disclaimer_accepted", false))
        assertTrue(preferences.getBoolean("setup_completed", false))
        assertEquals(0, callback.navigationCount)
    }

    @Test
    fun changedSetupLeavesHistoryAndUnrelatedSettingsUntouched() {
        helper.saveSetupData(setup)
        seedReadiness()
        preferences.edit().putString("appearance_selection", "classic").commit()
        val testPreferences = context.getSharedPreferences("paynet_test_results", Context.MODE_PRIVATE)
        testPreferences.edit().putString("unrelated_metadata", "preserve").commit()
        // A separate SQLite fixture protects the on-disk history boundary without
        // opening the production encrypted database or loading its key manager.
        context.openOrCreateDatabase("paynet_database", Context.MODE_PRIVATE, null).use { database ->
            database.execSQL("CREATE TABLE transactions (transactionId TEXT, amount TEXT, bankName TEXT)")
            database.execSQL("INSERT INTO transactions VALUES ('history-1', '125', 'State Bank of India')")
        }

        helper.completeSetup(setup.copy(selectedBank = "hdfc"))

        assertNull(results.getTestResults())
        assertEquals("classic", preferences.getString("appearance_selection", null))
        assertEquals("preserve", testPreferences.getString("unrelated_metadata", null))
        context.openOrCreateDatabase("paynet_database", Context.MODE_PRIVATE, null).use { database ->
            database.rawQuery("SELECT transactionId, amount, bankName FROM transactions", null).use { rows ->
                assertTrue(rows.moveToFirst())
                assertEquals("history-1", rows.getString(0))
                assertEquals("125", rows.getString(1))
                assertEquals("State Bank of India", rows.getString(2))
                assertFalse(rows.moveToNext())
            }
        }
    }

    @Test
    fun invalidSetupKeepsExistingContextAndReportsTheError() {
        helper.saveSetupData(setup)
        seedReadiness()

        helper.completeSetup(setup.copy(selectedBank = ""))

        assertEquals(confirmed, results.getTestResults())
        assertEquals("sbi", preferences.getString("selected_bank", null))
        assertTrue(preferences.getBoolean("test_configuration_completed", false))
        assertTrue(SetupHelper.hasUserReportedUssdNotWorking(context))
        assertEquals(0, callback.navigationCount)
        assertEquals(listOf("Please select your bank"), callback.messages)
    }

    private fun seedReadiness() {
        results.saveTestResults(confirmed)
        preferences.edit()
            .putBoolean("test_configuration_completed", true)
            .putBoolean("user_reported_ussd_not_working", true)
            .commit()
    }

    private class RecordingCallback : SetupHelper.UICallback {
        var navigationCount = 0
        val messages = mutableListOf<String>()
        override fun navigateToTestConfiguration() { navigationCount++ }
        override fun showToast(message: String) { messages += message }
    }
}
