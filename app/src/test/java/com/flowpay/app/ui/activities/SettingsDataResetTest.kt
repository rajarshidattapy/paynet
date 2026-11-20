// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.activities

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SettingsDataResetTest {
    @Test fun failedHistoryDeletionPreservesPreferencesAndDoesNotLeaveSettings() = runBlocking {
        var settingsCleared = false
        var setupOpened = false

        val result = resetSettingsData(
            deleteTransactions = { throw IllegalStateException("Storage unavailable") },
            clearPreferences = { settingsCleared = true },
            openSetup = { setupOpened = true }
        )

        assertFalse(result)
        assertFalse(settingsCleared)
        assertFalse(setupOpened)
    }

    @Test fun successfulRetryClearsSettingsOnlyAfterHistoryAndThenReopensSetup() = runBlocking {
        val events = mutableListOf<String>()
        val result = resetSettingsData(
            deleteTransactions = { events += "history" },
            clearPreferences = { events += "settings" },
            openSetup = { events += "setup" }
        )
        assertTrue(result)
        assertEquals(listOf("history", "settings", "setup"), events)
    }

    @Test fun cancellationIsNotSwallowedAsAResetFailure() = runBlocking {
        var settingsCleared = false
        var cancelled = false
        try {
            resetSettingsData(
                deleteTransactions = { throw CancellationException("Activity finished") },
                clearPreferences = { settingsCleared = true },
                openSetup = { throw AssertionError("Must not reopen setup") }
            )
        } catch (_: CancellationException) {
            cancelled = true
        }
        assertTrue(cancelled)
        assertFalse(settingsCleared)
    }
}
