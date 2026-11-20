// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.ui.activities

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewModelScope
import com.flowpay.app.data.SettingsRepository
import kotlinx.coroutines.launch

// Data Classes
data class Bank(
    val id: String,
    val name: String
)

data class SettingsState(
    val selectedBank: Bank = banks.first(),
    val ussdTimeout: Int = 30,
    val overlayEnabled: Boolean = true,
    val debugMode: Boolean = false,
    val setupCompleted: Boolean = true,
    val permissions: Map<String, Boolean> = emptyMap()
)

internal data class SettingsChoicePresentation(
    val id: String,
    val title: String,
    val swatch: Color? = null,
    val subtitle: String? = null
)

// Bank Data
val banks = listOf(
    Bank("hdfc", "HDFC Bank"),
    Bank("sbi", "State Bank of India"),
    Bank("icici", "ICICI Bank"),
    Bank("axis", "Axis Bank"),
    Bank("kotak", "Kotak Mahindra Bank"),
    Bank("pnb", "Punjab National Bank"),
    Bank("bob", "Bank of Baroda"),
    Bank("yes", "Yes Bank"),
    Bank("idbi", "IDBI Bank"),
    Bank("canara", "Canara Bank")
)

// ViewModel
class SettingsViewModel : androidx.lifecycle.ViewModel() {
    var state by mutableStateOf(SettingsState())
        private set
    var isResetting by mutableStateOf(false)
        private set
    var resetFailed by mutableStateOf(false)
        private set

    fun resetData(reset: suspend () -> Boolean) {
        if (isResetting) return
        isResetting = true
        resetFailed = false
        viewModelScope.launch {
            try {
                resetFailed = !reset()
            } finally {
                isResetting = false
            }
        }
    }

    fun updateBank(bank: Bank) {
        state = state.copy(selectedBank = bank)
    }

    fun toggleOverlay() {
        state = state.copy(overlayEnabled = !state.overlayEnabled)
    }

    fun refreshPermissions(context: Context) {
        val perms = mapOf(
            "phone" to (
                permissionGranted(context, Manifest.permission.CALL_PHONE) &&
                    permissionGranted(context, Manifest.permission.READ_PHONE_STATE)
                ),
            "camera" to permissionGranted(context, Manifest.permission.CAMERA),
            "contacts" to permissionGranted(context, Manifest.permission.READ_CONTACTS),
            "overlay" to (
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) Settings.canDrawOverlays(context) else true
                )
        )
        state = state.copy(permissions = perms)
    }

    fun loadFromRepository(settingsRepository: SettingsRepository, context: Context) {
        val saved = settingsRepository.settingsFlow.value
        val setupBankId = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
            .getString("selected_bank", null)
        // Setup owns the payment bank; the repository is a legacy fallback.
        val bank = banks.find { it.id == setupBankId }
            ?: banks.find { it.id == saved.bankId }
            ?: banks.first()
        state = state.copy(
            selectedBank = bank,
            ussdTimeout = saved.ussdTimeout,
            overlayEnabled = saved.overlayEnabled,
            debugMode = saved.debugMode,
            setupCompleted = saved.setupCompleted
        )
    }
}

private fun permissionGranted(context: Context, permission: String): Boolean =
    ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

internal enum class SettingsRowStyle { STANDARD, DESTRUCTIVE, CYCLE }
