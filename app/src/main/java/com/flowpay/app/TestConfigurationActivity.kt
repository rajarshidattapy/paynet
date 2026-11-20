// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material.icons.outlined.SimCard
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.flowpay.app.constants.PermissionConstants
import com.flowpay.app.helpers.OnboardingFlow
import com.flowpay.app.helpers.SetupHelper
import com.flowpay.app.helpers.TestConfigurationHelper
import com.flowpay.app.managers.CallType
import com.flowpay.app.ui.dialogs.OnboardingDialog
import com.flowpay.app.ui.dialogs.OnboardingDialogAction
import com.flowpay.app.ui.dialogs.OnboardingDialogCopy
import com.flowpay.app.ui.dialogs.Upi123ProgressDialog
import com.flowpay.app.ui.dialogs.UssdProgressDialog
import com.flowpay.app.ui.theme.BlueAccentTheme
import com.flowpay.app.ui.theme.FlowpayOnboardingSecondary
import com.flowpay.app.ui.theme.FlowpayOnboardingSurface
import com.flowpay.app.ui.theme.FlowpayTextLightGray
import com.flowpay.app.ui.theme.FlowpayTheme
import com.flowpay.app.ui.theme.LocalFlowpayAccentTheme
import kotlinx.coroutines.delay

class TestConfigurationActivity : ComponentActivity() {
    private lateinit var testHelper: TestConfigurationHelper

    // Phone-call permission group, requested before a test dial. No auto-retry:
    // the user re-taps the test action once granted.
    private val phonePermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        testHelper.onPhonePermissionsResult(results.values.all { it })
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize test helper
        testHelper = TestConfigurationHelper(
            this,
            object : TestConfigurationHelper.UICallback {
                override fun showToast(message: String) {
                    runOnUiThread {
                        android.widget.Toast.makeText(this@TestConfigurationActivity, message, android.widget.Toast.LENGTH_LONG).show()
                    }
                }

                override fun updateUssdTesting(isTesting: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateUssdDialog(show: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateUssdTestCompleted(completed: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateUpi123Testing(isTesting: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateUpi123TestCompleted(completed: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateUpi123Dialog(show: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateUpi123ConfigurationOptions(show: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateVoiceTesting(isTesting: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateVoiceDialog(show: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateVoiceTestCompleted(completed: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateCallCompleteButton(show: Boolean) {
                    // State will be managed by the composable
                }

                override fun updateUssdProgressMessage(message: String) {
                    // State will be managed by the composable
                }

                override fun updateUssdConfigurationOptions(show: Boolean) {
                    // State will be managed by the composable
                }

                override fun navigateToMain() {
                    OnboardingFlow.afterPayments(this@TestConfigurationActivity)
                }

                override fun requestPhonePermissions() {
                    phonePermissionLauncher.launch(PermissionConstants.PHONE_PERMISSIONS)
                }
            }
        )

        // Initialize the helper
        testHelper.initialize()
        testHelper.restoreScanAttempt(savedInstanceState)

        setTheme(R.style.Theme_Flowpay)
        // Edge-to-edge: Compose insets are the single source of padding (see MainActivity).
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent {
            CompositionLocalProvider(LocalFlowpayAccentTheme provides BlueAccentTheme) {
                FlowpayTheme {
                    TestConfigurationScreen(testHelper = testHelper)
                }
            }
        }
    }

    override fun onSaveInstanceState(outState: android.os.Bundle) {
        testHelper.saveScanAttempt(outState)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        super.onDestroy()
        // Unregisters the CallManager's PhoneStateListener and cancels
        // pending timeout runnables — without this, a listener registered
        // for an in-flight test call leaks past the screen.
        if (::testHelper.isInitialized) {
            testHelper.cleanup()
        }
    }
}

@Composable
fun TestConfigurationScreen(testHelper: TestConfigurationHelper) {
    val context = LocalContext.current
    // Get test states from helper
    val testStates = testHelper.getTestStates()
    var ussdTestCompleted by remember { mutableStateOf(testStates.ussdTestCompleted) }
    var upi123TestCompleted by remember { mutableStateOf(testStates.upi123TestCompleted) }
    var ussdTesting by remember { mutableStateOf(testStates.ussdTesting) }
    var upi123Testing by remember { mutableStateOf(testStates.upi123Testing) }
    // Hold the real setup call until the user explicitly confirms it.
    var pendingMethod by remember { mutableStateOf<SetupCallMethod?>(null) }
    var showUssdDialog by remember { mutableStateOf(testStates.showUssdDialog) }
    var showUpi123Dialog by remember { mutableStateOf(testStates.showUpi123Dialog) }
    var showUssdConfigurationOptions by remember { mutableStateOf(testStates.showUssdConfigurationOptions) }
    var showUpi123ConfigurationOptions by remember { mutableStateOf(testStates.showUpi123ConfigurationOptions) }
    var ussdProgressMessage by remember { mutableStateOf(testStates.ussdProgressMessage) }
    var showCallCompleteButton by remember { mutableStateOf(testStates.showCallCompleteButton) }
    var advancedToMain by rememberSaveable { mutableStateOf(false) }

    // Load existing test results
    LaunchedEffect(Unit) {
        val existingResults = testHelper.getTestResults()
        if (existingResults != null) {
            ussdTestCompleted = existingResults.ussdEnabled
            upi123TestCompleted = existingResults.upi123Enabled
        }
    }

    // Update states when helper states change
    LaunchedEffect(testStates) {
        ussdTestCompleted = testStates.ussdTestCompleted
        upi123TestCompleted = testStates.upi123TestCompleted
        ussdTesting = testStates.ussdTesting
        upi123Testing = testStates.upi123Testing
        showUssdDialog = testStates.showUssdDialog
        showUpi123Dialog = testStates.showUpi123Dialog
        showUssdConfigurationOptions = testStates.showUssdConfigurationOptions
        showUpi123ConfigurationOptions = testStates.showUpi123ConfigurationOptions
        ussdProgressMessage = testStates.ussdProgressMessage
        showCallCompleteButton = testStates.showCallCompleteButton
    }

    // Add a periodic state check to ensure UI updates
    LaunchedEffect(Unit) {
        while (true) {
            delay(100) // Check every 100ms
            val currentStates = testHelper.getTestStates()
            ussdTestCompleted = currentStates.ussdTestCompleted
            upi123TestCompleted = currentStates.upi123TestCompleted
            ussdTesting = currentStates.ussdTesting
            upi123Testing = currentStates.upi123Testing
            showUssdDialog = currentStates.showUssdDialog
            showUpi123Dialog = currentStates.showUpi123Dialog
            showUssdConfigurationOptions = currentStates.showUssdConfigurationOptions
            showUpi123ConfigurationOptions = currentStates.showUpi123ConfigurationOptions
            ussdProgressMessage = currentStates.ussdProgressMessage
            showCallCompleteButton = currentStates.showCallCompleteButton
        }
    }

    val busy = ussdTesting || upi123Testing || pendingMethod != null ||
        showUssdDialog || showUpi123Dialog || showUssdConfigurationOptions ||
        showUpi123ConfigurationOptions
    val allMethodsReady = testHelper.allTestsCompleted()
    BackHandler {
        if (!busy) openSetupReview(context)
    }
    LaunchedEffect(ussdTestCompleted, upi123TestCompleted, allMethodsReady, busy) {
        if (allMethodsReady && !busy && !advancedToMain) {
            advancedToMain = true
            testHelper.continueToMain()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .semantics { testTagsAsResourceId = true }
    ) {
        OnboardingPage("config-content", "config-stack") {
            TestSetupHeading()
            Spacer(modifier = Modifier.height(32.dp))
            val isJioSim = !SetupHelper.isPrimarySimUssdCapable(context)
            val userReportedUssdIssue = SetupHelper.hasUserReportedUssdNotWorking(context)
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(20.dp))
                    .background(FlowpayOnboardingSurface)
            ) {
                PaymentMethodRow(
                    method = PaymentMethodPresentation(
                        title = stringResource(R.string.test_setup_scan),
                        service = stringResource(
                            if (isJioSim) R.string.test_setup_jio else R.string.test_setup_ussd_service
                        ),
                        status = when {
                            isJioSim -> PaymentMethodStatus.Unavailable
                            ussdTesting -> PaymentMethodStatus.Checking
                            ussdTestCompleted -> PaymentMethodStatus.Ready
                            else -> PaymentMethodStatus.NotChecked
                        },
                        note = if (userReportedUssdIssue && !isJioSim) {
                            stringResource(R.string.test_setup_retry_scan)
                        } else {
                            null
                        },
                        enabled = !busy && !isJioSim && !ussdTestCompleted
                    ),
                    icon = Icons.Outlined.QrCodeScanner,
                    tag = "config-ussd",
                    onClick = {
                        if (!ussdTestCompleted && !ussdTesting) {
                            pendingMethod = SetupCallMethod.Scan
                        }
                    }
                )
                HorizontalDivider(
                    modifier = Modifier.padding(start = 60.dp),
                    thickness = 0.5.dp,
                    color = Color.White.copy(alpha = 0.12f)
                )
                PaymentMethodRow(
                    method = PaymentMethodPresentation(
                        title = stringResource(R.string.test_setup_contact),
                        service = stringResource(R.string.test_setup_upi_service),
                        status = when {
                            upi123Testing -> PaymentMethodStatus.Checking
                            upi123TestCompleted -> PaymentMethodStatus.Ready
                            else -> PaymentMethodStatus.NotChecked
                        },
                        enabled = !busy && !upi123TestCompleted
                    ),
                    icon = Icons.Outlined.Person,
                    tag = "config-upi123",
                    onClick = {
                        if (!upi123TestCompleted && !upi123Testing) {
                            pendingMethod = SetupCallMethod.Contact
                        }
                    }
                )
            }
        }

        IconButton(
            onClick = { openSetupReview(context) },
            enabled = !busy,
            modifier = Modifier
                .align(Alignment.TopStart)
                .statusBarsPadding()
                .padding(start = 12.dp, top = 8.dp)
                .size(48.dp)
                .testTag("config-back")
        ) {
            Icon(
                Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = stringResource(R.string.testcfg_back_to_setup),
                tint = BlueAccentTheme.accent,
                modifier = Modifier.size(20.dp)
            )
        }

        // USSD Progress Dialog
        UssdProgressDialog(
            isVisible = showUssdDialog || showUssdConfigurationOptions,
            progressMessage = ussdProgressMessage,
            showConfigurationOptions = showUssdConfigurationOptions,
            onConfigured = { testHelper.handleUssdConfigurationConfirmation(true) },
            onNotConfigured = { testHelper.handleUssdConfigurationConfirmation(false) },
            onDismiss = { testHelper.dismissUssdDialog(fromDoesNotWork = false) },
            onDoesNotWork = { testHelper.dismissUssdDialog(fromDoesNotWork = true) }
        )

        // UPI123 Progress Dialog
        Upi123ProgressDialog(
            isVisible = showUpi123Dialog || showUpi123ConfigurationOptions,
            showConfigurationOptions = showUpi123ConfigurationOptions,
            onConfigured = { testHelper.handleUpi123ConfigurationConfirmation(true) },
            onNotConfigured = { testHelper.handleUpi123ConfigurationConfirmation(false) },
            onDismiss = { testHelper.dismissUpi123Dialog() }
        )

        // Consent before placing a real test call to the carrier.
        pendingMethod?.let { method ->
            OnboardingDialog(
                copy = OnboardingDialogCopy(
                    title = stringResource(method.title),
                    message = stringResource(method.message)
                ),
                onDismiss = { pendingMethod = null },
                modifier = Modifier.testTag("config-consent-dialog"),
                content = {
                    Text(
                        text = stringResource(R.string.onboarding_call_pin_note),
                        modifier = Modifier.padding(top = 16.dp),
                        color = FlowpayOnboardingSecondary,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )
                },
                actions = {
                    OnboardingDialogAction(
                        text = stringResource(R.string.test_setup_start_call),
                        onClick = {
                            if (pendingMethod != method) return@OnboardingDialogAction
                            pendingMethod = null
                            when (method) {
                                SetupCallMethod.Scan -> {
                                    ussdTesting = true
                                    testHelper.initiateCall(CallType.USSD)
                                }
                                SetupCallMethod.Contact -> {
                                    upi123Testing = true
                                    testHelper.initiateUpi123Test()
                                }
                            }
                        },
                        modifier = Modifier.testTag("config-consent-start")
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    OnboardingDialogAction(
                        text = stringResource(R.string.action_cancel),
                        onClick = { pendingMethod = null },
                        secondary = true,
                        modifier = Modifier.testTag("config-consent-cancel")
                    )
                }
            )
        }
    }
}

private enum class SetupCallMethod(val title: Int, val message: Int) {
    Scan(R.string.onboarding_scan_call_title, R.string.onboarding_scan_call_message),
    Contact(R.string.onboarding_contact_call_title, R.string.onboarding_contact_call_message)
}

private fun openSetupReview(context: Context) {
    context.startActivity(
        Intent(context, SetupActivity::class.java).putExtra(SetupActivity.EXTRA_REVIEW_SETUP, true),
        setupTransitionOptions(context, backwards = true)
    )
    (context as? android.app.Activity)?.finish()
}

@Composable
private fun TestSetupHeading() {
    Column(
        modifier = Modifier.fillMaxWidth().testTag("config-header"),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            Icons.Outlined.SimCard,
            contentDescription = null,
            modifier = Modifier.size(48.dp).testTag("config-icon"),
            tint = BlueAccentTheme.accent
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = stringResource(R.string.test_setup_title),
            modifier = Modifier.testTag("config-title"),
            color = Color.White,
            fontSize = 31.sp,
            lineHeight = 37.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center
        )
        Spacer(modifier = Modifier.height(10.dp))
        Text(
            text = stringResource(R.string.test_setup_subtitle),
            color = FlowpayTextLightGray,
            fontSize = 16.sp,
            lineHeight = 23.sp,
            textAlign = TextAlign.Center
        )
    }
}

private enum class PaymentMethodStatus { NotChecked, Checking, Ready, Unavailable }

private data class PaymentMethodPresentation(
    val title: String,
    val service: String,
    val status: PaymentMethodStatus,
    val note: String? = null,
    val enabled: Boolean = true
)

@Composable
private fun PaymentMethodRow(
    method: PaymentMethodPresentation,
    icon: ImageVector,
    tag: String,
    onClick: () -> Unit
) {
    val status = stringResource(
        when (method.status) {
            PaymentMethodStatus.NotChecked -> R.string.test_setup_not_checked
            PaymentMethodStatus.Checking -> R.string.test_setup_checking
            PaymentMethodStatus.Ready -> R.string.test_setup_ready
            PaymentMethodStatus.Unavailable -> R.string.test_setup_unavailable
        }
    )
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 88.dp)
            .testTag(tag)
            .semantics(mergeDescendants = true) { stateDescription = status }
            .clickable(enabled = method.enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 18.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = if (method.status == PaymentMethodStatus.Unavailable) {
                FlowpayTextLightGray
            } else {
                BlueAccentTheme.accent
            },
            modifier = Modifier.size(24.dp)
        )
        Spacer(modifier = Modifier.width(16.dp))
        PaymentMethodText(method, Modifier.weight(1f))
        Spacer(modifier = Modifier.width(12.dp))
        PaymentMethodAccessory(method.status)
    }
}

@Composable
private fun PaymentMethodText(method: PaymentMethodPresentation, modifier: Modifier) {
    Column(modifier = modifier) {
        Text(
            text = method.title,
            fontSize = 17.sp,
            lineHeight = 22.sp,
            fontWeight = FontWeight.Medium,
            color = if (method.status == PaymentMethodStatus.Unavailable) FlowpayTextLightGray else Color.White
        )
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = when (method.status) {
                PaymentMethodStatus.Ready -> stringResource(R.string.test_setup_ready)
                PaymentMethodStatus.Checking -> stringResource(R.string.test_setup_checking)
                else -> method.service
            },
            color = FlowpayTextLightGray,
            fontSize = 13.sp,
            lineHeight = 18.sp
        )
        method.note?.let {
            Spacer(modifier = Modifier.height(4.dp))
            Text(it, color = FlowpayTextLightGray, fontSize = 13.sp, lineHeight = 18.sp)
        }
    }
}

@Composable
private fun PaymentMethodAccessory(status: PaymentMethodStatus) {
    Box(modifier = Modifier.size(24.dp), contentAlignment = Alignment.Center) {
        when (status) {
            PaymentMethodStatus.Checking -> CircularProgressIndicator(
                modifier = Modifier.size(20.dp),
                color = BlueAccentTheme.accent,
                strokeWidth = 2.dp
            )
            PaymentMethodStatus.Ready -> Icon(
                imageVector = Icons.Default.Check,
                contentDescription = stringResource(R.string.test_setup_completed),
                tint = BlueAccentTheme.accent,
                modifier = Modifier.size(22.dp)
            )
            PaymentMethodStatus.NotChecked -> Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = null,
                tint = FlowpayTextLightGray,
                modifier = Modifier.size(20.dp)
            )
            PaymentMethodStatus.Unavailable -> Unit
        }
    }
}
