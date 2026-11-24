// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.ui.activities

import kotlinx.coroutines.CancellationException

/** A failed history deletion must leave settings intact and must not reopen setup. */
internal suspend fun resetSettingsData(
    deleteTransactions: suspend () -> Unit,
    clearPreferences: () -> Unit,
    openSetup: () -> Unit
): Boolean = try {
    deleteTransactions()
    clearPreferences()
    openSetup()
    true
} catch (cancelled: CancellationException) {
    throw cancelled
} catch (_: Exception) {
    false
}
