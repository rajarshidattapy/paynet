// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.ui.activities

import android.app.Application
import android.content.Context
import com.flowpay.app.data.SettingsRepository
import com.flowpay.app.data.TestResults
import com.flowpay.app.data.TestResultsManager
import com.flowpay.app.ui.home.HomeAppearance
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

private const val FIXTURE_TIMEOUT_SECONDS = 45

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
class SettingsBankSourceTest {
    private val context: Context = RuntimeEnvironment.getApplication()
    private val preferences = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
    private val repositoryPreferences = context.getSharedPreferences("flowpay_settings", Context.MODE_PRIVATE)
    private val resultPreferences = context.getSharedPreferences("flowpay_test_results", Context.MODE_PRIVATE)

    @Before
    fun reset() {
        preferences.edit().clear().commit()
        repositoryPreferences.edit().clear().commit()
        resultPreferences.edit().clear().commit()
        context.deleteDatabase("flowpay_database")
    }

    @After
    fun cleanup() = reset()

    @Test
    fun setupBankOverridesDefaultRepositoryBank() {
        preferences.edit().putString("selected_bank", "sbi").commit()
        val repository = SettingsRepository(context)
        val viewModel = SettingsViewModel()

        viewModel.loadFromRepository(repository, context)

        assertEquals("sbi", viewModel.state.selectedBank.id)
        assertEquals("hdfc", repository.settingsFlow.value.bankId)
        assertFalse(repositoryPreferences.contains("bank_id"))
    }

    @Test
    fun absentEmptyAndUnknownSetupBankFallBackToRepository() {
        val repository = SettingsRepository(context)
        repository.saveSettings(repository.settingsFlow.value.copy(bankId = "axis"))
        val viewModel = SettingsViewModel()

        for (setupBank in listOf(null, "", "unknown-bank")) {
            preferences.edit().putString("selected_bank", setupBank).commit()

            viewModel.loadFromRepository(repository, context)

            assertEquals("Fallback for $setupBank", "axis", viewModel.state.selectedBank.id)
            assertEquals(setupBank, preferences.getString("selected_bank", null))
        }
    }

    @Test
    fun invalidBankInBothSourcesUsesKnownDefaultWithoutSavingIt() {
        preferences.edit().putString("selected_bank", "unknown-setup-bank").commit()
        val repository = SettingsRepository(context)
        repository.saveSettings(repository.settingsFlow.value.copy(bankId = "unknown-repository-bank"))
        val viewModel = SettingsViewModel()

        viewModel.loadFromRepository(repository, context)

        assertEquals(banks.first(), viewModel.state.selectedBank)
        assertEquals("unknown-setup-bank", preferences.getString("selected_bank", null))
        assertEquals("unknown-repository-bank", repository.settingsFlow.value.bankId)
    }

    @Test
    fun loadingSettingsPreservesReadinessThemeHistoryAndRepositoryOptions() {
        preferences.edit()
            .putString("selected_bank", "sbi")
            .putString("selected_primary_sim", "airtel")
            .putBoolean("setup_completed", true)
            .putBoolean("test_configuration_completed", true)
            .putBoolean("user_reported_ussd_not_working", true)
            .commit()
        HomeAppearance(classic = true, monochrome = false).save(context)
        TestResultsManager(context).saveTestResults(TestResults(true, true, timestamp = 123L))
        val repository = SettingsRepository(context)
        val saved = repository.settingsFlow.value.copy(
            bankId = "hdfc",
            ussdTimeout = FIXTURE_TIMEOUT_SECONDS,
            overlayEnabled = false,
            debugMode = true,
            setupCompleted = true,
            testConfigCompleted = true
        )
        repository.saveSettings(saved)
        val beforeSetup = preferences.all.toMap()
        val beforeRepository = repositoryPreferences.all.toMap()
        val beforeResults = resultPreferences.all.toMap()
        // Isolated history fixture: loading settings must not open or replace it.
        context.openOrCreateDatabase("flowpay_database", Context.MODE_PRIVATE, null).use { database ->
            database.execSQL("CREATE TABLE transactions (transactionId TEXT, amount TEXT)")
            database.execSQL("INSERT INTO transactions VALUES ('history-1', '125')")
        }
        val viewModel = SettingsViewModel()

        viewModel.loadFromRepository(repository, context)

        assertEquals("sbi", viewModel.state.selectedBank.id)
        assertEquals(FIXTURE_TIMEOUT_SECONDS, viewModel.state.ussdTimeout)
        assertFalse(viewModel.state.overlayEnabled)
        assertTrue(viewModel.state.debugMode)
        assertTrue(viewModel.state.setupCompleted)
        assertEquals(saved, repository.settingsFlow.value)
        assertEquals(beforeSetup, preferences.all)
        assertEquals(beforeRepository, repositoryPreferences.all)
        assertEquals(beforeResults, resultPreferences.all)
        context.openOrCreateDatabase("flowpay_database", Context.MODE_PRIVATE, null).use { database ->
            database.rawQuery("SELECT transactionId, amount FROM transactions", null).use { rows ->
                assertTrue(rows.moveToFirst())
                assertEquals("history-1", rows.getString(0))
                assertEquals("125", rows.getString(1))
                assertFalse(rows.moveToNext())
            }
        }
    }
}
