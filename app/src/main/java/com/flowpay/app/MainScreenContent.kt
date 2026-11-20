// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.flowpay.app.constants.AppConstants
import com.flowpay.app.data.TestResultsManager
import com.flowpay.app.managers.PermissionManager
import com.flowpay.app.ui.activities.SettingsActivity
import com.flowpay.app.ui.activities.TransactionHistoryActivity
import com.flowpay.app.ui.components.TransactionDetailDialog
import com.flowpay.app.ui.home.HomeDashboard
import com.flowpay.app.viewmodel.MainUiEvent
import com.flowpay.app.viewmodel.MainViewModel
import com.flowpay.app.viewmodel.TransactionViewModel
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay

private class MainScreenState(
    bank: String,
    ussdReady: Boolean,
    upiReady: Boolean,
    payContactVisible: MutableState<Boolean>
) {
    var savedBank by mutableStateOf(bank)
    var isUssdReady by mutableStateOf(ussdReady)
    var isUpi123Ready by mutableStateOf(upiReady)
    var isScanning by mutableStateOf(false)
    var showPayContact by payContactVisible
    var showOverlayPermissionDialog by mutableStateOf(false)
}

@Composable
internal fun FlowpayMainContent(
    onInitiateTransfer: (String, String, String?) -> Unit,
    onQRScanClick: () -> Unit,
    onRequestOverlayPermission: () -> Unit
) {
    com.flowpay.app.ui.components.SmsPermissionNotice()
    val transactionViewModel: TransactionViewModel = viewModel()
    val state = rememberMainScreenState(transactionViewModel)
    Surface(modifier = Modifier.fillMaxSize(), color = Color.Black) {
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            MainDashboard(state, transactionViewModel, onQRScanClick)
            MainDialogs(state, transactionViewModel, onInitiateTransfer, onRequestOverlayPermission)
        }
    }
}

@Composable
private fun rememberMainScreenState(transactionViewModel: TransactionViewModel): MainScreenState {
    val context = LocalContext.current
    val preferences = remember(context) { context.getSharedPreferences(AppConstants.PREFS_NAME, Context.MODE_PRIVATE) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val testResults = remember(context) { TestResultsManager(context) }
    val payContactVisible = rememberSaveable { mutableStateOf(false) }
    val state = remember {
        MainScreenState(
            preferences.getString(AppConstants.KEY_SELECTED_BANK, "hdfc") ?: "hdfc",
            testResults.getTestResults()?.ussdEnabled == true,
            testResults.getTestResults()?.upi123Enabled == true,
            payContactVisible
        )
    }
    val mainViewModel: MainViewModel = viewModel()
    LaunchedEffect(mainViewModel) {
        mainViewModel.events.collect { event ->
            when (event) {
                MainUiEvent.QrScannerClosed -> state.isScanning = false
                MainUiEvent.OverlayPermissionNeeded -> state.showOverlayPermissionDialog = true
            }
        }
    }
    LaunchedEffect(lifecycle, preferences, testResults) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            state.savedBank = preferences.getString(AppConstants.KEY_SELECTED_BANK, "hdfc") ?: "hdfc"
            state.isUpi123Ready = testResults.getTestResults()?.upi123Enabled == true
            state.isUssdReady = testResults.getTestResults()?.ussdEnabled == true
            state.isScanning = false
            transactionViewModel.refresh()
            awaitCancellation()
        }
    }
    LaunchedEffect(state.isScanning) {
        if (state.isScanning) {
            delay(AppConstants.USSD_SESSION_TIMEOUT)
            if (state.isScanning) state.isScanning = false
        }
    }
    return state
}

@Composable
private fun MainDashboard(state: MainScreenState, transactions: TransactionViewModel, onScan: () -> Unit) {
    val context = LocalContext.current
    val recentPayments by transactions.recentTransactions.collectAsState()
    val isLoading by transactions.isLoading.collectAsState()
    val error by transactions.error.collectAsState()
    HomeDashboard(
        selectedBankName = homeBankName(state.savedBank),
        recentPayments = recentPayments,
        isLoading = isLoading,
        error = error,
        onRetry = transactions::refresh,
        onTransaction = { transactions.selectTransaction(it.id) },
        onSettings = { context.startActivity(Intent(context, SettingsActivity::class.java)) },
        onHistory = { context.startActivity(Intent(context, TransactionHistoryActivity::class.java)) },
        onQRScanClick = { startHomeScan(context, state, onScan) },
        onPayContactClick = { openHomeContactPayment(context, state) },
        isUpi123Ready = state.isUpi123Ready,
        isUssdReady = state.isUssdReady,
        isScanning = state.isScanning
    )
}

private fun startHomeScan(context: Context, state: MainScreenState, onScan: () -> Unit) {
    if (!state.isUssdReady) {
        context.startActivity(Intent(context, TestConfigurationActivity::class.java))
    } else {
        state.isScanning = true
        onScan()
    }
}

private fun openHomeContactPayment(context: Context, state: MainScreenState) {
    when {
        !state.isUpi123Ready -> context.startActivity(Intent(context, TestConfigurationActivity::class.java))
        !PermissionManager.canDrawOverlays(context) -> state.showOverlayPermissionDialog = true
        else -> state.showPayContact = true
    }
}

@Composable
private fun MainDialogs(
    state: MainScreenState,
    transactions: TransactionViewModel,
    onInitiateTransfer: (String, String, String?) -> Unit,
    onRequestOverlayPermission: () -> Unit
) {
    val selectedTransaction by transactions.selectedTransaction.collectAsState()
    selectedTransaction?.let { transaction ->
        TransactionDetailDialog(
            transaction = transaction,
            onDismiss = transactions::clearSelectedTransaction,
            onDelete = {
                transactions.deleteTransaction(transaction)
                transactions.clearSelectedTransaction()
            }
        )
    }
    if (state.showPayContact) {
        PayContactDialog(
            onDismiss = { state.showPayContact = false },
            onConfirm = { phone, amount, name ->
                state.showPayContact = false
                onInitiateTransfer(phone, amount, name)
            }
        )
    }
    if (state.showOverlayPermissionDialog) {
        PermissionExplanationDialog(
            title = stringResource(R.string.overlay_permission_title),
            message = stringResource(R.string.overlay_permission_body),
            confirmButtonText = stringResource(R.string.permission_continue),
            onConfirm = {
                state.showOverlayPermissionDialog = false
                onRequestOverlayPermission()
            },
            onDismiss = { state.showOverlayPermissionDialog = false }
        )
    }
}

private fun homeBankName(bank: String): String = when (bank) {
    "sbi" -> "State Bank of India"
    "hdfc" -> "HDFC Bank"
    "icici" -> "ICICI Bank"
    "axis" -> "Axis Bank"
    "kotak" -> "Kotak Mahindra Bank"
    "pnb" -> "Punjab National Bank"
    "bob" -> "Bank of Baroda"
    "yes" -> "Yes Bank"
    "idbi" -> "IDBI Bank"
    "canara" -> "Canara Bank"
    else -> "HDFC Bank"
}
