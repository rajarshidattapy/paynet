// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay
//
// Home screen: the entry point to both payment rails (Scan QR and Pay
// Contact), recent payments, and settings. UI only — the transfer
// orchestration and permission gating live in MainActivityHelper.

package com.paynet.app

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowOutward
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.QrCode
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.paynet.app.constants.PermissionConstants
import com.paynet.app.data.PaymentDetails
import com.paynet.app.data.PaymentStatus
import com.paynet.app.helpers.MainActivityHelper
import com.paynet.app.helpers.OnboardingFlow
import com.paynet.app.managers.PermissionManager
import com.paynet.app.ui.theme.PayNetAccentProvider
import com.paynet.app.ui.theme.PayNetDarkGray
import com.paynet.app.ui.theme.PayNetMediumGray
import com.paynet.app.ui.theme.PayNetStatusError
import com.paynet.app.ui.theme.PayNetSurfaceDim
import com.paynet.app.ui.theme.PayNetTextLightGray
import com.paynet.app.ui.theme.PayNetTextPale
import com.paynet.app.ui.theme.PayNetTheme
import com.paynet.app.ui.theme.LocalPayNetAccentTheme
import com.paynet.app.utils.CurrencyFormat
import com.paynet.app.viewmodel.MainViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    companion object {
        private const val TAG = "PayNet"
    }

    // Helper for all business logic
    private lateinit var helper: MainActivityHelper

    // Shared with MainScreen (same instance via Compose viewModel()); carries
    // one-shot Activity -> Compose events, replacing the old static callbacks.
    private val mainViewModel: MainViewModel by viewModels()

    // Launches QRScannerActivity and, on return, un-sticks the QR button's
    // "Opening..." state via a QrScannerClosed event.
    private val qrScannerLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        mainViewModel.onQrScannerClosed()
    }

    // Launches the system "draw over other apps" settings screen; on return,
    // re-checks the permission and reports the outcome via toast (there is
    // no reliable resultCode for this settings screen, so re-checking is
    // the only correct way to know what happened).
    private val overlayPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        val granted = PermissionManager.canDrawOverlays(this)
        val message = if (granted) {
            "Overlay permission granted. You can now proceed with the transfer."
        } else {
            "Overlay permission is required for payment protection. Please enable it in Settings."
        }
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    // Phone-call permission group, requested before dialing or QR scanning.
    // There is no auto-retry: the user re-taps the action once granted.
    private val phonePermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val granted = results.values.all { it }
        if (!granted) {
            Toast.makeText(this, R.string.error_permissions_denied, Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (com.paynet.app.metrics.InstallReporter.needsChoice(this)) {
            startActivity(Intent(this, com.paynet.app.metrics.InstallCountActivity::class.java))
            finish()
            return
        }

        setTheme(R.style.Theme_PayNet)

        // Draw edge-to-edge so Compose's statusBarsPadding()/navigationBarsPadding()
        // are the single source of inset padding. The theme previously also set
        // android:fitsSystemWindows=true, which made the decor pad the content as
        // well — a double inset that, depending on inset-dispatch timing, showed
        // intermittent black bars at the top and bottom.
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)

        // Black system bars from the first frame
        window.statusBarColor = android.graphics.Color.BLACK
        window.navigationBarColor = android.graphics.Color.BLACK
        window.setBackgroundDrawableResource(android.R.color.black)
        window.decorView.setBackgroundColor(android.graphics.Color.BLACK)
        window.setFlags(
            android.view.WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS,
            android.view.WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            window.attributes.layoutInDisplayCutoutMode =
                android.view.WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        }
        window.decorView.post { enforceBlackStatusBar() }

        // Initialize helper with UI callbacks (matches the 6-method UICallback)
        helper = MainActivityHelper(
            this,
            object : MainActivityHelper.UICallback {
                override fun showToast(message: String) {
                    runOnUiThread { Toast.makeText(this@MainActivity, message, Toast.LENGTH_SHORT).show() }
                }

                override fun updatePaymentState(paymentState: com.paynet.app.states.PaymentState) {
                    Log.d(TAG, "Payment state updated: ${paymentState::class.simpleName}")
                }

                override fun navigateToSetup() {
                    startActivity(Intent(this@MainActivity, SetupActivity::class.java))
                    finish()
                }

                override fun navigateToTestConfiguration() {
                    startActivity(Intent(this@MainActivity, TestConfigurationActivity::class.java))
                    finish()
                }

                override fun finishActivity() {
                    finish()
                }

                override fun showOverlayPermissionExplanation() {
                    mainViewModel.onOverlayPermissionNeeded()
                }

                override fun launchQRScanner(intent: Intent) {
                    qrScannerLauncher.launch(intent)
                }

                override fun requestPhonePermissions() {
                    phonePermissionLauncher.launch(PermissionConstants.PHONE_PERMISSIONS)
                }
            }
        )

        helper.initialize()

        // The launch gate must know which screen to show before rendering, so
        // these two SharedPreferences flags are read synchronously. Reading
        // them faults the prefs file in once (a small, one-time disk read);
        // annotate it as permitted so the debug StrictMode tripwire stays
        // sharp for genuinely unexpected main-thread disk I/O instead of
        // crying wolf on this known-safe read every launch.
        val setupCompleted: Boolean
        val testCompleted: Boolean
        val appearancePending: Boolean
        val oldPolicy = android.os.StrictMode.allowThreadDiskReads()
        try {
            setupCompleted = helper.isSetupCompleted()
            testCompleted = helper.isTestCompleted()
            appearancePending = OnboardingFlow.needsAppearance(this)
        } finally {
            android.os.StrictMode.setThreadPolicy(oldPolicy)
        }

        if (!setupCompleted || !testCompleted || appearancePending) {
            when {
                !setupCompleted -> helper.navigateToSetup()
                !testCompleted -> helper.navigateToTestConfiguration()
                else -> OnboardingFlow.openAppearance(this)
            }
            finish()
            return
        }

        setContent {
            PayNetAccentProvider {
                PayNetTheme {
                    MainScreen(
                        onInitiateTransfer = { phoneNumber, amount, name ->
                            helper.initiateTransfer(phoneNumber, amount, name)
                        },
                        onQRScanClick = {
                            helper.startQRScanning()
                        },
                        onRequestOverlayPermission = {
                            PermissionManager(this).overlayPermissionSettingsIntent()?.let {
                                overlayPermissionLauncher.launch(it)
                            }
                        }
                    )
                }
            }
        }
    }

    override fun onPause() {
        super.onPause()
        if (::helper.isInitialized) helper.onPause()
    }

    override fun onResume() {
        super.onResume()
        if (::helper.isInitialized) helper.onResume()
        enforceBlackStatusBar()
    }

    private fun enforceBlackStatusBar() {
        window.statusBarColor = android.graphics.Color.BLACK
        window.navigationBarColor = android.graphics.Color.BLACK
        // Dark bars => light (white) icons. WindowInsetsControllerCompat
        // routes through WindowInsetsController on API 30+ and the legacy
        // systemUiVisibility flags on API 29, replacing the deprecated
        // direct flag manipulation.
        androidx.core.view.WindowInsetsControllerCompat(window, window.decorView)
            .isAppearanceLightStatusBars = false
    }

    override fun onStop() {
        super.onStop()
        if (::helper.isInitialized) helper.onStop()
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::helper.isInitialized) helper.onDestroy()
    }
}

// Payment Action Buttons - QR scan + Pay Contact.
//
// Each rail is locked until its own connectivity test has passed: Scan QR
// dials *99#, Pay Contact dials the UPI 123 IVR. One composable per button,
// because the locked/unlocked branches on both pushed the combined function
// past detekt's complexity and parameter limits.
@Composable
fun PaymentActionButtons(
    onQRScanClick: () -> Unit,
    onPayContactClick: () -> Unit,
    isUpi123Ready: Boolean,
    isUssdReady: Boolean,
    isScanning: Boolean
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        ScanQrButton(onQRScanClick, isUssdReady, isScanning)
        PayContactButton(onPayContactClick, isUpi123Ready)
    }
}

/** Scan QR — locked until the *99# connectivity test has passed. */
@Composable
private fun ScanQrButton(
    onQRScanClick: () -> Unit,
    isUssdReady: Boolean,
    isScanning: Boolean
) {
    var isQRPressed by remember { mutableStateOf(false) }
    val qrButtonScale by animateFloatAsState(
        targetValue = if (isQRPressed) 0.94f else 1f,
        animationSpec = tween(durationMillis = 200),
        label = "QR Button Scale"
    )
    // Scan QR Button
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Box(
            modifier = Modifier
                .size(70.dp)
                .shadow(
                    elevation = 12.dp,
                    shape = CircleShape,
                    ambientColor = LocalPayNetAccentTheme.current.headerGradientStart.copy(alpha = 0.3f),
                    spotColor = LocalPayNetAccentTheme.current.headerGradientEnd.copy(alpha = 0.4f)
                )
                .scale(qrButtonScale)
                .background(
                    brush = if (isUssdReady) {
                        Brush.linearGradient(
                            colors = listOf(
                                LocalPayNetAccentTheme.current.headerGradientStart,
                                LocalPayNetAccentTheme.current.headerGradientEnd
                            ),
                            start = Offset(0f, 0f),
                            end = Offset(1f, 1f)
                        )
                    } else {
                        Brush.linearGradient(colors = listOf(PayNetSurfaceDim, PayNetSurfaceDim))
                    },
                    shape = CircleShape
                )
                .border(1.dp, Color.White.copy(alpha = 0.15f), CircleShape)
                .pointerInput(Unit) {
                    detectTapGestures(
                        onPress = {
                            if (!isScanning) {
                                isQRPressed = true
                                tryAwaitRelease()
                                isQRPressed = false
                            }
                        },
                        onTap = { if (!isScanning) onQRScanClick() }
                    )
                },
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = when {
                    !isUssdReady -> Icons.Default.Lock
                    isScanning -> Icons.Default.QrCode
                    else -> Icons.Default.QrCodeScanner
                },
                contentDescription = stringResource(
                    if (isUssdReady) R.string.home_scan_qr else R.string.home_setup_ussd
                ),
                tint = if (isUssdReady) Color.White else Color.White.copy(alpha = 0.5f),
                modifier = Modifier.size(32.dp)
            )
        }

        Text(
            text = when {
                !isUssdReady -> stringResource(R.string.home_setup_ussd)
                isScanning -> stringResource(R.string.home_scan_opening)
                else -> stringResource(R.string.home_scan_qr)
            },
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            color = if (isUssdReady) Color.White else PayNetTextLightGray,
            textAlign = TextAlign.Center,
            style = TextStyle(
                shadow = Shadow(Color.Black.copy(alpha = 0.6f), Offset(0f, 1f), 3f)
            )
        )
    }

    // OR Divider
    Row(
        modifier = Modifier.padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Box(
            modifier = Modifier
                .width(50.dp)
                .height(1.dp)
                .background(Color.White.copy(alpha = 0.3f))
        )
        Spacer(modifier = Modifier.width(12.dp))
        Box(
            modifier = Modifier
                .background(Color.White.copy(alpha = 0.1f), CircleShape)
                .padding(horizontal = 10.dp, vertical = 4.dp)
        ) {
            Text(
                text = "OR",
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
                color = Color.White.copy(alpha = 0.8f)
            )
        }
        Spacer(modifier = Modifier.width(12.dp))
        Box(
            modifier = Modifier
                .width(50.dp)
                .height(1.dp)
                .background(Color.White.copy(alpha = 0.3f))
        )
    }
}

/** Pay Contact — locked until the UPI 123 IVR connectivity test has passed. */
@Composable
private fun PayContactButton(
    onPayContactClick: () -> Unit,
    isUpi123Ready: Boolean
) {
    var isPayPressed by remember { mutableStateOf(false) }
    val payButtonScale by animateFloatAsState(
        targetValue = if (isPayPressed) 0.94f else 1f,
        animationSpec = tween(durationMillis = 200),
        label = "Pay Button Scale"
    )
    // Pay Contact Button — inactive until the UPI 123 IVR test has
    // passed; in that state it prompts for setup and tapping it opens
    // the *99# / UPI 123 test screen.
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Box(
            modifier = Modifier
                .size(70.dp)
                .shadow(
                    elevation = if (isUpi123Ready) 12.dp else 0.dp,
                    shape = RoundedCornerShape(20.dp),
                    ambientColor = LocalPayNetAccentTheme.current.headerGradientStart.copy(alpha = 0.3f),
                    spotColor = LocalPayNetAccentTheme.current.headerGradientEnd.copy(alpha = 0.4f)
                )
                .scale(payButtonScale)
                .background(
                    brush = if (isUpi123Ready) {
                        Brush.linearGradient(
                            colors = listOf(
                                LocalPayNetAccentTheme.current.headerGradientStart,
                                LocalPayNetAccentTheme.current.headerGradientEnd
                            ),
                            start = Offset(0f, 0f),
                            end = Offset(1f, 1f)
                        )
                    } else {
                        Brush.linearGradient(
                            colors = listOf(PayNetMediumGray, PayNetDarkGray),
                            start = Offset(0f, 0f),
                            end = Offset(1f, 1f)
                        )
                    },
                    shape = RoundedCornerShape(20.dp)
                )
                .border(1.dp, Color.White.copy(alpha = 0.15f), RoundedCornerShape(20.dp))
                .pointerInput(Unit) {
                    detectTapGestures(
                        onPress = {
                            isPayPressed = true
                            tryAwaitRelease()
                            isPayPressed = false
                        },
                        onTap = { onPayContactClick() }
                    )
                },
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = if (isUpi123Ready) Icons.Default.Person else Icons.Default.Lock,
                contentDescription = if (isUpi123Ready) "Pay Contact" else "Set up UPI 123 IVR",
                tint = if (isUpi123Ready) Color.White else Color.White.copy(alpha = 0.5f),
                modifier = Modifier.size(32.dp)
            )
        }

        Text(
            text = if (isUpi123Ready) "Pay Contact" else "Set up UPI 123 IVR",
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            color = if (isUpi123Ready) Color.White else PayNetTextLightGray,
            textAlign = TextAlign.Center,
            style = TextStyle(
                shadow = Shadow(Color.Black.copy(alpha = 0.6f), Offset(0f, 1f), 3f)
            )
        )
    }
}

@Composable
fun MainScreen(
    onInitiateTransfer: (String, String, String?) -> Unit,
    onQRScanClick: () -> Unit,
    onRequestOverlayPermission: () -> Unit
) {
    PayNetMainContent(onInitiateTransfer, onQRScanClick, onRequestOverlayPermission)
}

@Composable
fun TransactionItem(payment: PaymentDetails, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .height(90.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = PayNetSurfaceDim),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 18.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(end = 12.dp),
                verticalArrangement = Arrangement.Center
            ) {
                Text(
                    text = payment.recipientLabel ?: stringResource(R.string.detail_recipient_unknown),
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = formatDate(payment.timestamp),
                    fontSize = 14.sp,
                    color = PayNetTextPale,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    fontWeight = FontWeight.Medium
                )
            }

            TransactionItemOutcome(payment)
        }
    }
}

@Composable
private fun TransactionItemOutcome(payment: PaymentDetails) {
    if (payment.userConfirmed != null) {
        Icon(
            imageVector = if (payment.userConfirmed == true) Icons.Default.Check else Icons.Default.Close,
            contentDescription = if (payment.userConfirmed == true) "Confirmed by you" else "Not confirmed by you",
            tint = LocalPayNetAccentTheme.current.headerGradientStart
        )
    } else if (payment.amountRecorded) {
        TransactionItemAmount(amount = payment.amount, status = payment.status)
    }
}

@Composable
private fun TransactionItemAmount(amount: Double, status: PaymentStatus) {
    // FAILED and CANCELLED read as "this payment did not go through" — a
    // cross, not the same outgoing arrow a successful payment gets. Every
    // other outcome (COMPLETED, PENDING, NEEDS_REVIEW, UNVERIFIED) keeps the
    // arrow: this row has no separate status chip (unlike transaction
    // history), so the icon is the only signal here.
    val failed = status == PaymentStatus.FAILED || status == PaymentStatus.CANCELLED
    val tint = if (failed) PayNetStatusError else LocalPayNetAccentTheme.current.headerGradientStart

    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.End,
        modifier = Modifier.padding(start = 8.dp)
    ) {
        Text(
            text = stringResource(R.string.amount_rupees, CurrencyFormat.inr(amount)),
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
            color = LocalPayNetAccentTheme.current.headerGradientStart,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
        Spacer(modifier = Modifier.width(8.dp))
        Icon(
            imageVector = if (failed) Icons.Default.Close else Icons.Default.ArrowOutward,
            contentDescription = stringResource(
                if (failed) R.string.cd_payment_failed else R.string.cd_payment_outgoing
            ),
            modifier = Modifier.size(18.dp),
            tint = tint
        )
    }
}

@Composable
fun PayContactDialog(
    onDismiss: () -> Unit,
    onConfirm: (String, String, String?) -> Unit
) {
    PayContactContent(onDismiss, onConfirm)
}

@Composable
fun PermissionExplanationDialog(
    title: String,
    message: String,
    confirmButtonText: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = PayNetDarkGray,
        title = {
            Text(
                text = title,
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold,
                color = Color.White
            )
        },
        text = {
            Text(
                text = message,
                fontSize = 14.sp,
                color = PayNetTextPale,
                lineHeight = 20.sp
            )
        },
        confirmButton = {
            TextButton(
                onClick = onConfirm,
                colors = ButtonDefaults.textButtonColors(
                    contentColor = LocalPayNetAccentTheme.current.accent
                )
            ) {
                Text(confirmButtonText)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.action_not_now), color = PayNetTextLightGray)
            }
        }
    )
}

// Utility functions
fun formatDate(timestamp: Long): String {
    val formatter = SimpleDateFormat("dd MMM, HH:mm", Locale("en", "IN"))
    return formatter.format(Date(timestamp))
}
