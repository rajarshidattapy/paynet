// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.ui.activities

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material.icons.outlined.BarChart
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.PrivacyTip
import androidx.compose.material.icons.outlined.SimCard
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.flowpay.app.BuildConfig
import com.flowpay.app.FlowpayApplication
import com.flowpay.app.R
import com.flowpay.app.SetupActivity
import com.flowpay.app.data.SettingsRepository
import com.flowpay.app.helpers.SetupHelper
import com.flowpay.app.repository.TransactionRepository
import com.flowpay.app.ui.home.rememberHomeAppearance
import com.flowpay.app.ui.theme.FlowpayAccentProvider
import com.flowpay.app.ui.theme.FlowpayDarkGray
import com.flowpay.app.ui.theme.LocalFlowpayAccentTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class SettingsActivity : ComponentActivity() {
    private val refreshTrigger = mutableIntStateOf(0)
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { refreshTrigger.intValue++ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as? FlowpayApplication
        val repository = app?.settingsRepository ?: SettingsRepository(applicationContext)
        setTheme(R.style.Theme_Flowpay)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent {
            FlowpayAccentProvider {
                FlowpaySettingsTheme {
                    SettingsScreen(
                        onBackPressed = { finish() },
                        settingsRepository = repository,
                        onRequestPermissions = { permissionLauncher.launch(it) },
                        refreshTrigger = refreshTrigger
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        refreshTrigger.intValue++
    }
}

@Composable
fun FlowpaySettingsTheme(content: @Composable () -> Unit) {
    val accent = LocalFlowpayAccentTheme.current
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = accent.primary,
            secondary = accent.accent,
            onPrimary = accent.onAccent,
            onSecondary = accent.onAccent,
            background = Color.Black,
            surface = FlowpayDarkGray,
            onBackground = Color.White,
            onSurface = Color.White
        ),
        content = content
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel = viewModel(),
    onBackPressed: () -> Unit,
    settingsRepository: SettingsRepository? = null,
    onRequestPermissions: (Array<String>) -> Unit = {},
    refreshTrigger: MutableIntState = mutableIntStateOf(0)
) {
    val context = LocalContext.current
    val state = viewModel.state
    val appearance by rememberHomeAppearance()
    val preferences = remember(context) { context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE) }
    var primarySimId by rememberSaveable { mutableStateOf(preferences.getString("selected_primary_sim", "").orEmpty()) }
    var dialog by rememberSaveable { mutableStateOf<String?>(null) }
    val trigger by refreshTrigger
    LaunchedEffect(settingsRepository) { settingsRepository?.let { viewModel.loadFromRepository(it, context) } }
    LaunchedEffect(trigger) { viewModel.refreshPermissions(context) }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .statusBarsPadding()
            .navigationBarsPadding()
            .semantics { testTagsAsResourceId = true }
            .testTag("settings-content"),
        contentPadding = PaddingValues(start = 24.dp, end = 24.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { SettingsHeading(onBackPressed) }
        item { SectionHeader(stringResource(R.string.settings_refined_appearance)) }
        item {
            AppearanceSettings(
                appearance,
                onToggleDesign = { appearance.copy(classic = !appearance.classic).save(context) },
                onToggleColor = { appearance.copy(monochrome = !appearance.monochrome).save(context) }
            )
        }
        item { SectionHeader(stringResource(R.string.settings_refined_payments)) }
        item {
            GroupCard {
                SettingsRow(Icons.Outlined.AccountBalance, "Bank", state.selectedBank.name) { dialog = "bank" }
                GroupDivider()
                SettingsRow(Icons.Outlined.SimCard, "Primary SIM", simName(primarySimId)) { dialog = "sim" }
            }
        }
        item { SectionHeader(stringResource(R.string.settings_refined_permissions)) }
        item { PermissionSettings(state.permissions, onRequestPermissions) }
        item { SectionHeader(stringResource(R.string.settings_refined_about)) }
        item {
            GroupCard {
                SettingsRow(Icons.Outlined.Info, "Version", BuildConfig.VERSION_NAME) { dialog = "version" }
                if (com.flowpay.app.metrics.InstallReporter.configured()) {
                    GroupDivider()
                    SettingsRow(
                        Icons.Outlined.BarChart,
                        stringResource(R.string.install_count_settings),
                        stringResource(R.string.install_count_settings_summary)
                    ) {
                        context.startActivity(
                            Intent(context, com.flowpay.app.metrics.InstallCountActivity::class.java)
                                .putExtra("from_settings", true)
                        )
                    }
                }
                GroupDivider()
                SettingsRow(
                    Icons.Outlined.PrivacyTip,
                    stringResource(R.string.privacy_title),
                    stringResource(R.string.settings_refined_privacy_summary)
                ) { context.startActivity(Intent(context, PrivacyActivity::class.java)) }
            }
        }
        item { SectionHeader(stringResource(R.string.settings_refined_data)) }
        item {
            GroupCard {
                SettingsRow(
                    Icons.Outlined.Delete,
                    stringResource(R.string.settings_clear_data_title),
                    stringResource(R.string.settings_refined_reset_summary),
                    style = SettingsRowStyle.DESTRUCTIVE,
                    onClick = { dialog = "clear" }
                )
            }
        }
    }

    when (dialog) {
        "version" -> VersionDialog { dialog = null }
        "bank" -> BankPickerDialog(
            selectedBank = state.selectedBank,
            onBankSelected = { bank ->
                if (preferences.getString("selected_bank", "") != bank.id) {
                    SetupHelper.invalidatePaymentConfiguration(context)
                }
                viewModel.updateBank(bank)
                settingsRepository?.saveSettings(settingsRepository.settingsFlow.value.copy(bankId = bank.id))
                preferences.edit().putString("selected_bank", bank.id).apply()
                dialog = null
            },
            onDismiss = { dialog = null }
        )
        "sim" -> SimPickerDialog(
            selectedSimId = primarySimId,
            onSimSelected = { simId ->
                if (preferences.getString("selected_primary_sim", "") != simId) {
                    SetupHelper.invalidatePaymentConfiguration(context)
                }
                primarySimId = simId
                preferences.edit().putString("selected_primary_sim", simId).apply()
                dialog = null
            },
            onDismiss = { dialog = null }
        )
        "clear" -> ClearDataDialog(
            onDismiss = { if (!viewModel.isResetting) dialog = null },
            onConfirm = { viewModel.resetData { clearSettingsData(context, settingsRepository) } },
            resetting = viewModel.isResetting,
            failed = viewModel.resetFailed
        )
    }
}

private suspend fun clearSettingsData(context: Context, repository: SettingsRepository?): Boolean = resetSettingsData(
    deleteTransactions = {
        withContext(Dispatchers.IO) { TransactionRepository.getInstance(context).deleteAllTransactions() }
    },
    clearPreferences = {
        (repository ?: SettingsRepository(context)).clearAllData()
        context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).edit().clear().apply()
    },
    openSetup = {
        context.startActivity(
            Intent(context, SetupActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
        )
    }
)

@Composable
private fun simName(simId: String): String = when (simId) {
    "jio" -> "Jio"
    "airtel" -> "Airtel"
    "vodafone" -> "Vodafone"
    "bsnl" -> "BSNL"
    else -> stringResource(R.string.settings_not_set)
}
