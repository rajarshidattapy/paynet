// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.features.qr_scanner.presentation

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PersistableBundle
import android.os.SystemClock
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.StringRes
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import com.paynet.app.PayNetApplication
import com.paynet.app.R
import com.paynet.app.data.TransactionSource
import com.paynet.app.data.UPIData
import com.paynet.app.features.qr_scanner.domain.QRCodeAnalyzer
import com.paynet.app.features.qr_scanner.domain.QRCodeParser
import com.paynet.app.features.qr_scanner.domain.messageFor
import com.paynet.app.helpers.SetupHelper
import com.paynet.app.managers.PermissionManager
import com.paynet.app.ui.theme.PayNetViewTheme
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class QRScannerActivity : ComponentActivity() {

    companion object {
        const val RESULT_CANCELLED = 0
        const val RESULT_SUCCESS = 1
        const val RESULT_ERROR = 2

        /** How long the invalid-QR banner stays up before fading out. */
        private const val SCAN_ERROR_VISIBLE_MS = 3500L
        private const val FEEDBACK_FADE_MS = 180L
        private const val STATUS_TEXT_SP = 16f
        private const val ERROR_TITLE_SP = 15f
        private const val ERROR_BODY_SP = 14f
        private const val DISABLED_ALPHA = 0.5f

        /** Longest edge a gallery image is downsampled to before decoding. */
        private const val GALLERY_MAX_EDGE_PX = 2048
    }

    private lateinit var viewFinder: PreviewView
    private lateinit var scannerOverlay: View
    private lateinit var progressBar: View
    private lateinit var tvStatus: TextView
    private lateinit var tvScanError: TextView
    private lateinit var btnBack: View
    private lateinit var btnTerminate: View
    private lateinit var topBar: View
    private lateinit var instructionsBox: View
    private lateinit var instructionsHeaderInitial: View
    private lateinit var instructionsExpanded: View
    private lateinit var btnFlash: ImageButton
    private lateinit var btnGallery: ImageButton
    private lateinit var bottomActionBar: View
    private lateinit var scanLine: View
    private var scanLineAnimator: android.animation.ObjectAnimator? = null
    private lateinit var cameraExecutor: ExecutorService
    private var imageAnalyzer: ImageAnalysis? = null
    private var activeCodeAnalyzer: QRCodeAnalyzer? = null
    private var liveAnalysisGeneration = 0L
    private var scannerResumed = false
    private var galleryPending = false
    private var galleryUri: Uri? = null
    private var galleryDecodeJob: Job? = null
    private var galleryResult: Result<String?>? = null
    private var camera: Camera? = null
    private var isFlashOn = false
    private lateinit var permissionManager: PermissionManager
    private var isUSSDProcessActive = false
    private var messageHandler: android.os.Handler? = null

    // Centralized handler for all delayed callbacks — cleaned up in onDestroy
    private val mainHandler = Handler(Looper.getMainLooper())

    // Guards against processing the same QR more than once per flow.
    @Volatile
    private var isProcessingQRCode = false

    // Ensures USSD is dialed once per payment flow — without this, returning
    // from the dialer re-triggers the dial and loops.
    @Volatile
    private var hasDialedUSSD = false

    // Set when this screen closes itself on [WAITING_SCREEN_TIMEOUT_MS]
    // rather than because the user abandoned the payment. The two must not be
    // conflated: onDestroy cancels the session on `isFinishing`, and a cancel

    // deliberately outlives the verification deadline by a grace margin so a
    // slow bank confirmation is never dropped. When this timer was a hardcoded
    // 150 s — a quarter of the deadline — reaching that cancel path capped the
    // QR rail's real confirmation window at 150 s: a user still inside the
    // *99# menus (paste VPA, amount, UPI PIN) when it fired had the window

    // arrived to a closed window — money moved, history said CANCELLED, and
    // nothing surfaced. The timer may dismiss the screen; it may not end the
    // payment.
    @Volatile
    private var finishedByWaitingScreenTimeout = false

    // Whether this flow put a payee VPA on the clipboard (wiped in onDestroy).
    private var copiedVpaToken: String? = null
    private var copiedVpa: String? = null
    private var qrTransactionId: String? = null
    private var qrGuideVisible = false
    private var qrTriggeredAt: Long? = null
    private var qrAnswerSaving = false
    private val revealQrAnswers = Runnable { showSmsWaitingState() }

    // Permission launcher for runtime permissions
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        handlePermissionResult(permissions)
    }

    // Permission launcher for CALL_PHONE permission in dialUSSD flow
    private val callPhonePermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            dialUSSD()
        } else {
            showError(getString(R.string.error_call_permission_required_payments))
        }
    }

    /**
     * Android's photo picker. Deliberately NOT a storage permission: the
     * picker returns a one-shot read grant for the single image the user
     * chose, so the app never gains access to the gallery as a whole. That
     * keeps the "no storage permission" claim in README/ARCHITECTURE true.
     */
    private val galleryPickerLauncher = registerForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri ->
        if (uri == null) {
            Log.d("QRScanner", "Gallery pick cancelled")
            finishGallerySelection()
        } else {
            decodeQrFromGallery(uri)
        }
    }

    /**
     * Keeps the floating chrome clear of the system bars.
     *
     * On targetSdk 35 the window is edge-to-edge, and this activity applied no
     * insets at all — so the instructions card sat at y=0, underneath the
     * status bar and the display cutout, with its first line clipped. The
     * camera preview is deliberately left full-bleed; only the overlay chrome
     * is inset, so the viewfinder still fills the screen.
     */
    private fun applyWindowInsets() {
        val root = findViewById<View>(android.R.id.content)
        ViewCompat.setOnApplyWindowInsetsListener(root) { _, windowInsets ->
            val bars = windowInsets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            (instructionsBox.layoutParams as? ViewGroup.MarginLayoutParams)?.let {
                it.topMargin = bars.top + resources.getDimensionPixelSize(R.dimen.qr_chrome_gap)
                instructionsBox.layoutParams = it
            }
            (topBar.layoutParams as? ViewGroup.MarginLayoutParams)?.let {
                it.topMargin = bars.top + resources.getDimensionPixelSize(R.dimen.qr_chrome_gap)
                topBar.layoutParams = it
            }
            (bottomActionBar.layoutParams as? ViewGroup.MarginLayoutParams)?.let {
                it.bottomMargin = bars.bottom +
                    resources.getDimensionPixelSize(R.dimen.qr_bottom_bar_gap)
                bottomActionBar.layoutParams = it
            }
            windowInsets
        }
    }

    /**
     * Check if the activity is still alive and safe to access views
     */
    private fun isActivityAlive(): Boolean = !isFinishing && !isDestroyed

    private fun isScannerVisible(): Boolean = isActivityAlive() && scannerResumed

    private fun hasPaymentInProgress(): Boolean = isProcessingQRCode || qrGuideVisible

    private fun canAcceptLiveQr(): Boolean = isScannerVisible() && !galleryPending && !hasPaymentInProgress()

    // Broadcast receiver for USSD overlay dismissal
    private val overlayDismissReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == "DISMISS_OVERLAY") {
                Log.d("QRScanner", "USSD guide dismissed - awaiting user response")
                if (isUSSDProcessActive) {
                    updateBlackScreenStatus(R.string.qr_status_ussd_completed)
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        try {
            Log.d("QRScanner", "=== QR SCANNER ACTIVITY CREATED ===")
            super.onCreate(savedInstanceState)
            setContentView(R.layout.activity_qr_scanner)
            lifecycleScope.launch {
                PayNetApplication.from(this@QRScannerActivity)?.paymentSessionManager?.paymentState?.collect { state ->
                    if (com.paynet.app.payment.shouldCloseQrWaitingScreen(qrTransactionId, state)
                    ) {
                        finishedByWaitingScreenTimeout = true
                        finish()
                    }
                }
            }
            PayNetViewTheme.observe(findViewById(android.R.id.content), PayNetViewTheme::scanner)

            SetupHelper.getScanToPayBlockedMessage(this)?.let { msg ->
                Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
                setResult(RESULT_CANCELLED)
                finish()
                return
            }

            // Initialize views
            viewFinder = findViewById(R.id.viewFinder)
            scannerOverlay = findViewById(R.id.scannerOverlay)
            progressBar = findViewById(R.id.progressBar)
            tvStatus = findViewById(R.id.tvStatus)
            tvScanError = findViewById(R.id.tvScanError)
            btnBack = findViewById(R.id.btnBack)
            btnTerminate = findViewById(R.id.btnTerminate)
            topBar = findViewById(R.id.topBar)
            instructionsBox = findViewById(R.id.instructionsBox)
            instructionsHeaderInitial = findViewById(R.id.instructionsHeaderInitial)
            instructionsExpanded = findViewById(R.id.instructionsExpanded)
            btnFlash = findViewById(R.id.btnFlash)
            btnGallery = findViewById(R.id.btnGallery)
            bottomActionBar = findViewById(R.id.bottomActionBar)
            scanLine = findViewById(R.id.scanLine)

            applyWindowInsets()

            Log.d("QRScanner", "Views initialized successfully")

            // Initialize permission manager
            permissionManager = PermissionManager(this)
            Log.d("QRScanner", "Permission manager initialized")

            cameraExecutor = Executors.newSingleThreadExecutor()
            Log.d("QRScanner", "Camera executor created")

            btnBack.setOnClickListener {
                Log.d("QRScanner", "Back button clicked")
                setResult(RESULT_CANCELLED)
                finish()
            }

            btnTerminate.setOnClickListener {
                if (qrAnswerSaving) return@setOnClickListener
                qrAnswerSaving = true
                mainHandler.removeCallbacksAndMessages(null)
                lifecycleScope.launch {
                    qrTransactionId?.let { transactionId ->
                        PayNetApplication.from(this@QRScannerActivity)?.paymentSessionManager
                            ?.onUserCancelled()
                    }
                    finishedByWaitingScreenTimeout = true
                    finish()
                    overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
                }
            }

            btnFlash.setOnClickListener {
                isFlashOn = !isFlashOn
                camera?.cameraControl?.enableTorch(isFlashOn)
                btnFlash.setImageResource(
                    if (isFlashOn) R.drawable.ic_flash_on else R.drawable.ic_flash_off
                )
                btnFlash.setBackgroundResource(
                    if (isFlashOn) {
                        R.drawable.bottom_action_button_active_bg
                    } else {
                        R.drawable.bottom_action_button_bg
                    }
                )
                btnFlash.isSelected = isFlashOn
                PayNetViewTheme.scanner(findViewById(android.R.id.content))
            }

            btnGallery.setOnClickListener {
                openGalleryPicker()
            }

            // Register broadcast receivers
            val overlayFilter = IntentFilter("DISMISS_OVERLAY")
            LocalBroadcastManager.getInstance(this).registerReceiver(overlayDismissReceiver, overlayFilter)

            Log.d("QRScanner", "Starting permission check...")
            qrTransactionId = savedInstanceState?.getString("qrTransactionId")
            copiedVpaToken = savedInstanceState?.getString("copiedVpaToken")
            copiedVpa = savedInstanceState?.getString("copiedVpa")
            if (savedInstanceState?.getBoolean("qrGuideVisible") == true) {
                hasDialedUSSD = savedInstanceState.getBoolean("hasDialedUSSD")
                qrTriggeredAt = savedInstanceState.getLong("qrTriggeredAt", -1L).takeIf { it >= 0L }
                isProcessingQRCode = true
                isUSSDProcessActive = qrTriggeredAt != null
                showBlackScreenWithStatus(getString(R.string.qr_payment_guide_status))
                showSmsWaitingState()
            } else {
                galleryPending = savedInstanceState?.getBoolean("galleryPending") == true
                galleryUri = savedInstanceState?.getString("galleryUri")?.let(Uri::parse)
                if (galleryPending) setGalleryControlsEnabled(false)
                checkPermissionsAndStartCamera()
            }
        } catch (e: Exception) {
            Log.e("QRScanner", "Error in onCreate", e)
            Toast.makeText(this, R.string.error_qr_scanner_init, Toast.LENGTH_LONG).show()
            setResult(RESULT_ERROR)
            finish()
        }
    }

    /**
     * Check CAMERA permission before starting camera
     */
    private fun checkPermissionsAndStartCamera() {
        Log.d("QRScanner", "Checking CAMERA permission before starting camera")

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            Log.d("QRScanner", "Camera permission not granted, requesting...")
            permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECEIVE_SMS))
        } else {
            Log.d("QRScanner", "Camera permission already granted, starting camera")
            startCamera()
        }
    }

    /**
     * Handle CAMERA permission request results
     */
    private fun handlePermissionResult(permissions: Map<String, Boolean>) {
        val cameraGranted = permissions[Manifest.permission.CAMERA] == true &&
            permissions[Manifest.permission.RECEIVE_SMS] == true

        if (cameraGranted) {
            Log.d("QRScanner", "Camera permission granted, starting camera")
            startCamera()
        } else {
            Log.w("QRScanner", "Camera permission denied")
            Toast.makeText(
                this,
                "Camera permission is required for QR scanning",
                Toast.LENGTH_LONG
            ).show()
            setResult(RESULT_ERROR)
            finish()
        }
    }

    private fun startCamera() {
        try {
            Log.d("QRScanner", "Starting camera initialization...")
            val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

            cameraProviderFuture.addListener({
                try {
                    if (!isActivityAlive()) return@addListener

                    val cameraProvider = cameraProviderFuture.get()
                    Log.d("QRScanner", "Camera provider obtained successfully")

                    // Preview
                    val preview = Preview.Builder().build().also {
                        it.setSurfaceProvider(viewFinder.surfaceProvider)
                    }
                    Log.d("QRScanner", "Preview configured")

                    // QR Code Analysis
                    imageAnalyzer = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                    Log.d("QRScanner", "Image analyzer configured")

                    // Select back camera
                    val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

                    try {
                        // Unbind use cases before rebinding
                        cameraProvider.unbindAll()
                        Log.d("QRScanner", "Previous use cases unbound")

                        // Bind use cases to camera — safe null check instead of !!
                        val analyzer = imageAnalyzer ?: run {
                            Log.e("QRScanner", "Image analyzer is null, cannot bind camera")
                            return@addListener
                        }
                        camera = cameraProvider.bindToLifecycle(
                            this, cameraSelector, preview, analyzer
                        )
                        Log.d("QRScanner", "Camera use cases bound successfully")
                        resumeLiveScanning()
                    } catch (exc: Exception) {
                        Log.e("QRScanner", "Use case binding failed", exc)
                        runOnUiThread {
                            if (!isActivityAlive()) return@runOnUiThread
                            Toast.makeText(
                                this,
                                R.string.error_camera_init_failed,
                                Toast.LENGTH_LONG
                            ).show()
                        }
                    }
                } catch (e: Exception) {
                    Log.e("QRScanner", "Error in camera setup", e)
                    runOnUiThread {
                        if (!isActivityAlive()) return@runOnUiThread
                        Toast.makeText(this, R.string.error_camera_setup, Toast.LENGTH_LONG).show()
                    }
                }
            }, ContextCompat.getMainExecutor(this))
        } catch (e: Exception) {
            Log.e("QRScanner", "Failed to start camera", e)
            Toast.makeText(this, R.string.error_camera_setup, Toast.LENGTH_LONG).show()
        }
    }

    private fun processQRCode(qrCode: String) {
        // Camera callbacks and picker results share this main-thread handoff.
        if (Looper.myLooper() != Looper.getMainLooper()) {
            mainHandler.post { processQRCode(qrCode) }
            return
        }
        try {
            // Already processing a QR — a second decode must not dial again.
            if (!canAcceptLiveQr()) {
                Log.d("QRScanner", "Already processing QR code, ignoring duplicate detection")
                return
            }

            // Set processing flag
            isProcessingQRCode = true

            // The analyzer pauses itself after detection. Keep it attached until
            // parsing succeeds so an unsuitable QR can re-arm the same decoder.
            Log.d("QRScanner", "QR Code detected")

            // Show loading
            runOnUiThread {
                if (!isActivityAlive()) return@runOnUiThread
                scannerOverlay.visibility = View.GONE
                bottomActionBar.visibility = View.GONE
                scanLineAnimator?.cancel()
                progressBar.visibility = View.VISIBLE
                tvStatus.text = getString(R.string.qr_processing)
                tvStatus.visibility = View.VISIBLE
            }

            // Parse UPI data. A code that isn't a usable UPI QR is a normal,
            // expected thing to point a scanner at — it must not be treated
            // like a payment failure, and the parser's specific reason is far
            // more useful to the user than a generic "invalid".
            when (val result = QRCodeParser.parse(qrCode)) {
                is QRCodeParser.ParseResult.Valid -> {
                    Log.d("QRScanner", "Successfully parsed UPI data")
                    initiateUSSDPayment(result.data)
                }
                is QRCodeParser.ParseResult.Invalid -> {
                    Log.w("QRScanner", "QR rejected: ${result.reason.name}")
                    showInvalidQrCode(result.reason.messageFor(this))
                }
            }
        } catch (e: Exception) {
            Log.e("QRScanner", "Error processing QR code", e)
            showError(getString(R.string.error_qr_processing))
            // Reset processing flag on error
            isProcessingQRCode = false
        }
    }

    private fun initiateUSSDPayment(upiData: UPIData) {
        // Always proceed with payment - skip amount dialog
        // VPA will be copied to clipboard and USSD will be dialed instantly
        proceedWithPayment(upiData)
    }

    private fun proceedWithPayment(upiData: UPIData) {
        try {
            stopLiveAnalysis()
            Log.d("QRScanner", "=== STARTING SIMPLE QR PAYMENT PROCESS ===")

            // Validate VPA
            if (upiData.vpa.isBlank()) {
                Log.e("QRScanner", "VPA is blank, cannot proceed")
                showError(getString(R.string.error_qr_invalid_vpa))
                return
            }

            if (!beginQrPaymentSession(upiData)) return

            // Show black screen with status
            showBlackScreenWithStatus("Processing payment...")

            // 1. Copy VPA to clipboard so the user can paste it into the USSD
            //    menu. It is a payee identifier (PII), so it is flagged
            //    sensitive and wiped in onDestroy when the flow ends.
            copyVpaToClipboard(upiData.vpa)

            // 2. Dial USSD code after a short delay (only once per flow)
            mainHandler.postDelayed({
                try {
                    if (!isActivityAlive()) return@postDelayed
                    if (hasDialedUSSD) {
                        Log.d("QRScanner", "USSD already dialed this flow, skipping duplicate dial")
                        return@postDelayed
                    }
                    hasDialedUSSD = true
                    Log.d("QRScanner", "Dialing USSD code: *99*1*3#")
                    updateBlackScreenStatus(R.string.qr_status_initiating_call)
                    dialUSSD()
                } catch (e: Exception) {
                    Log.e("QRScanner", "Failed to dial USSD: ${e.message}", e)
                    showError(getString(R.string.error_ussd_call_failed))
                }
            }, 1000) // 1 second delay to ensure overlay is ready
        } catch (e: Exception) {
            Log.e("QRScanner", "Unexpected error in proceedWithPayment: ${e.message}", e)
            showError(getString(R.string.error_unexpected))
        }
    }

    private fun beginQrPaymentSession(upiData: UPIData): Boolean {
        val sessionManager = PayNetApplication.from(this)?.paymentSessionManager
        val sessionTxnId = sessionManager?.begin(
            phoneNumber = "",
            amount = upiData.amount ?: "",
            upiId = upiData.vpa,
            source = TransactionSource.QR,
            recipientName = upiData.payeeName?.takeIf { it.isNotBlank() }
                ?: Regex("[0-9]+").findAll(upiData.vpa.substringBefore('@')).maxByOrNull { it.value.length }?.value
                ?: upiData.vpa
        )
        if (sessionTxnId != null) {
            com.paynet.app.helpers.TransactionDetector.getInstance(this).startOperation(
                operationType = "QR_SCAN",
                expectedAmount = upiData.amount,
                sessionTxnId = sessionTxnId
            )
        }
        qrTransactionId = sessionTxnId
        return sessionTxnId != null
    }

    /**
     * Copies the payee VPA to the clipboard so the user can paste it into the
     * USSD menu. Flagged sensitive on Android 13+ so it stays out of clipboard
     * previews; [clearVpaClipboard] wipes it when the flow ends.
     */
    private fun copyVpaToClipboard(vpa: String) {
        try {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("VPA", vpa)
            val token = java.util.UUID.randomUUID().toString()
            clip.description.extras = PersistableBundle().apply {
                putString("com.paynet.app.CLIP_OWNER", token)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true)
                }
            }
            clipboard.setPrimaryClip(clip)
            copiedVpaToken = token
            copiedVpa = vpa
            Log.d("QRScanner", "VPA copied to clipboard successfully")
            // No status update here: the system already shows its own
            // "copied" confirmation on Android 13+, and step 1 of the
            // on-screen instructions already tells the user to paste it.
            // Announcing it a third time was just noise.
        } catch (e: SecurityException) {
            // Not critical — the flow can continue without the clipboard copy.
            Log.e("QRScanner", "Failed to copy VPA to clipboard: ${e.message}")
        } catch (e: IllegalStateException) {
            Log.e("QRScanner", "Failed to copy VPA to clipboard: ${e.message}")
        }
    }

    /**
     * Clears the payee VPA so it doesn't linger for other apps.
     *
     * Uses clearPrimaryClip() rather than writing an empty clip: on Android
     * 13+ EVERY setPrimaryClip() raises the system "Copied to clipboard"
     * chip, so overwriting produced a second, baffling "copied" popup at the
     * moment the session ended — after the user had already finished. Clearing
     * is not a copy, so nothing is announced, and it genuinely empties the
     * clipboard instead of parking an empty string on it.
     */
    private fun clearVpaClipboard() {
        val token = copiedVpaToken ?: return
        try {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val current = clipboard.primaryClip
            // A later copy belongs to the user, even if its text happens to match our VPA.
            if (current?.description?.extras?.getString("com.paynet.app.CLIP_OWNER") == token &&
                current.itemCount == 1 && current.getItemAt(0).text?.toString() == copiedVpa
            ) {
                clipboard.clearPrimaryClip()
                Log.d("QRScanner", "PayNet VPA cleared from clipboard")
            }
        } catch (e: SecurityException) {
            Log.e("QRScanner", "Error clearing clipboard: ${e.message}")
        } catch (e: IllegalStateException) {
            Log.e("QRScanner", "Error clearing clipboard: ${e.message}")
        } finally {
            copiedVpaToken = null
            copiedVpa = null
        }
    }

    private fun dialUSSD() {
        val ussdCode = "*99*1*3#"
        val encodedHash = Uri.encode("#")
        val ussd = ussdCode.replace("#", encodedHash)

        Log.d("QRScanner", "Preparing to dial USSD: $ussdCode")

        // Check CALL_PHONE permission before dialing — use modern launcher API
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CALL_PHONE)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.e("QRScanner", "CALL_PHONE permission not granted - requesting")
            callPhonePermissionLauncher.launch(Manifest.permission.CALL_PHONE)
            return
        }

        val intent = Intent(Intent.ACTION_CALL).apply {
            data = Uri.parse("tel:$ussd")
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }

        try {
            Log.d("QRScanner", "Starting USSD call activity")
            updateBlackScreenStatus(R.string.qr_status_call_initiated)
            startActivity(intent)
            Log.d("QRScanner", "USSD call initiated successfully")

            // Start the extended message sequence for USSD process
            startUSSDProcessMessages()
        } catch (e: Exception) {
            Log.e("QRScanner", "Failed to dial USSD: ${e.message}", e)

            // window keeps listening for a payment that never happened and
            // could adopt an unrelated confirmation.
            PayNetApplication.from(this)?.paymentSessionManager
                ?.onDialFailed("Could not start the payment call")
            showError(getString(R.string.error_ussd_call_failed))
        }
    }

    /**
     * Start extended message sequence during USSD process
     */
    private fun startUSSDProcessMessages() {
        Log.d("QRScanner", "Entering USSD wait phase")
        isUSSDProcessActive = true
        if (qrTriggeredAt == null) qrTriggeredAt = SystemClock.elapsedRealtime()
        showSmsWaitingState()

        // Honest, static status. PayNet cannot see the USSD menu or the bank's
        // progress, so it does not fake step-by-step progress — it states what
        // the user should do and what it is genuinely waiting for.
        updateBlackScreenStatus(R.string.qr_payment_guide_status)

        // The bank-message pipeline owns the result; call state never implies success.
    }

    /**
     * Show black screen with status message
     */
    private fun showBlackScreenWithStatus(message: String) {
        runOnUiThread {
            if (!isActivityAlive()) return@runOnUiThread
            Log.d("QRScanner", "Showing black screen with status: $message")

            qrGuideVisible = true
            // Hide camera and scanner elements
            viewFinder.visibility = View.GONE
            scannerOverlay.visibility = View.GONE
            bottomActionBar.visibility = View.GONE
            scanLineAnimator?.cancel()
            progressBar.visibility = View.GONE
            topBar.visibility = View.GONE // Hide top bar to prevent overlap

            // Show instructions box at the top with initial state
            instructionsBox.visibility = View.VISIBLE
            instructionsHeaderInitial.visibility = View.VISIBLE
            instructionsExpanded.visibility = View.GONE

            // Animate transition to expanded state after 4 seconds
            mainHandler.postDelayed({
                if (!isActivityAlive()) return@postDelayed
                animateInstructionsTransition()
            }, 4000)

            // Show black screen with status
            tvStatus.text = message
            tvStatus.visibility = View.VISIBLE
            tvStatus.setTextColor(ContextCompat.getColor(this, android.R.color.white))
            tvStatus.textSize = STATUS_TEXT_SP

            // Show terminate button
            btnTerminate.visibility = View.VISIBLE

            // Set black background
            findViewById<View>(
                android.R.id.content
            ).setBackgroundColor(ContextCompat.getColor(this, android.R.color.black))
        }
    }

    /**
     * Animate transition from initial header to expanded steps list
     */
    private fun animateInstructionsTransition() {
        runOnUiThread {
            if (!isActivityAlive()) return@runOnUiThread
            Log.d("QRScanner", "Animating instructions transition to expanded state")

            // Fade out initial header
            instructionsHeaderInitial.animate()
                .alpha(0f)
                .setDuration(300)
                .withEndAction {
                    if (!isActivityAlive()) return@withEndAction
                    instructionsHeaderInitial.visibility = View.GONE

                    // Fade in expanded view
                    instructionsExpanded.alpha = 0f
                    instructionsExpanded.visibility = View.VISIBLE
                    instructionsExpanded.animate()
                        .alpha(1f)
                        .setDuration(400)
                        .start()
                }
                .start()
        }
    }

    /**
     * Update the status message on the black waiting screen.
     *
     * Takes a string resource, never a [String], and that is the point: this
     * is user-visible payment copy, and every literal that ever reached it
     * was invisible to both copy gates. lint's `HardcodedText` never leaves
     * XML, and `build.yml`'s grep is line-oriented — one call site here opens
     * its paren on one line and puts the literal on the next, so a gate
     * widened to match `updateBlackScreenStatus\(\s*"` reported green while a
     * hardcoded string sat in the payment flow. Requiring a resource id makes
     * `updateBlackScreenStatus("…")` a compile error instead of something a
     * regex has to be taught to notice.
     *
     * [formatArg] is a single optional argument rather than a `vararg`
     * deliberately: only one caller formats, and a spread would trip detekt's
     * default `SpreadOperator` rule (the build sets `buildUponDefaultConfig`),
     * whose baseline only ratchets down.
     */
    private fun updateBlackScreenStatus(@StringRes messageRes: Int, formatArg: Any? = null) {
        runOnUiThread {
            if (!isActivityAlive()) return@runOnUiThread
            val message =
                if (formatArg == null) getString(messageRes) else getString(messageRes, formatArg)
            Log.d("QRScanner", "Updating black screen status: $message")
            tvStatus.text = message
        }
    }

    /** Reserve the input before launching the picker, including during its transition. */
    private fun openGalleryPicker() {
        if (!isScannerVisible() || galleryPending || hasPaymentInProgress()) return
        galleryPending = true
        stopLiveAnalysis()
        setGalleryControlsEnabled(false)
        try {
            galleryPickerLauncher.launch(
                PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
            )
        } catch (error: ActivityNotFoundException) {
            galleryPickerFailed(error)
        } catch (error: SecurityException) {
            galleryPickerFailed(error)
        } catch (error: IllegalStateException) {
            galleryPickerFailed(error)
        } catch (error: IllegalArgumentException) {
            galleryPickerFailed(error)
        }
    }

    private fun galleryPickerFailed(error: Exception) {
        Log.w("QRScanner", "Photo picker could not open", error)
        finishGallerySelection()
        showInvalidQrCode(getString(R.string.qr_gallery_unreadable))
    }

    private fun setGalleryControlsEnabled(enabled: Boolean) {
        for (control in listOf(btnGallery, btnFlash)) {
            control.isEnabled = enabled
            control.alpha = if (enabled) 1f else DISABLED_ALPHA
        }
    }

    private fun finishGallerySelection() {
        galleryPending = false
        galleryUri = null
        galleryResult = null
        setGalleryControlsEnabled(true)
        progressBar.visibility = View.GONE
        tvStatus.visibility = View.GONE
        scannerOverlay.visibility = View.VISIBLE
        resumeLiveScanning()
    }

    private fun decodeQrFromGallery(uri: Uri) {
        if (!isActivityAlive() || hasPaymentInProgress() || galleryDecodeJob != null) return
        galleryPending = true
        galleryUri = uri
        stopLiveAnalysis()
        setGalleryControlsEnabled(false)
        tvScanError.visibility = View.GONE
        scannerOverlay.visibility = View.GONE
        progressBar.visibility = View.VISIBLE
        tvStatus.setText(R.string.qr_gallery_reading)
        tvStatus.setTextColor(ContextCompat.getColor(this, android.R.color.white))
        tvStatus.visibility = View.VISIBLE
        galleryDecodeJob = lifecycleScope.launch {
            val decoded = try {
                val value = withContext(Dispatchers.IO) {
                    val source = ImageDecoder.createSource(contentResolver, uri)
                    val bitmap = ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
                        // getPixels() throws on a HARDWARE bitmap, which is
                        // what ImageDecoder hands back by default — the QR
                        // decoder needs readable pixels.
                        decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                        decoder.isMutableRequired = false
                        // Cap the working size: gallery photos can be 100MP,
                        // and a QR stays readable far below that.
                        val longest = maxOf(info.size.width, info.size.height)
                        if (longest > GALLERY_MAX_EDGE_PX) {
                            decoder.setTargetSampleSize(longest / GALLERY_MAX_EDGE_PX + 1)
                        }
                    }
                    try {
                        QRCodeAnalyzer.decodeBitmap(bitmap)
                    } finally {
                        bitmap.recycle()
                    }
                }
                Result.success(value)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: IOException) {
                galleryReadFailed(error)
            } catch (error: SecurityException) {
                galleryReadFailed(error)
            } catch (error: IllegalArgumentException) {
                galleryReadFailed(error)
            } catch (error: IllegalStateException) {
                galleryReadFailed(error)
            }
            if (!isActivityAlive()) return@launch
            galleryDecodeJob = null
            galleryResult = decoded
            consumeGalleryResult()
        }
    }

    private fun galleryReadFailed(error: Exception): Result<String?> {
        Log.w("QRScanner", "Gallery image could not be read", error)
        return Result.failure(error)
    }

    private fun consumeGalleryResult() {
        if (!scannerResumed || !isActivityAlive()) return
        val decoded = galleryResult ?: return
        // Do not briefly reattach the live analyzer between gallery decode and
        // processing: the explicitly chosen image owns this handoff.
        galleryResult = null
        galleryUri = null
        galleryPending = false
        setGalleryControlsEnabled(true)
        when {
            decoded.isFailure -> showInvalidQrCode(getString(R.string.qr_gallery_unreadable))
            decoded.getOrNull() == null -> showInvalidQrCode(getString(R.string.qr_gallery_no_code))
            else -> processQRCode(requireNotNull(decoded.getOrNull()))
        }
    }

    /** Invalid codes reuse the analyzer, preserving its duplicate cooldown. */
    private fun resumeLiveScanning() {
        val cameraExecutorReady = ::cameraExecutor.isInitialized && !cameraExecutor.isShutdown
        if (!canAcceptLiveQr() || !cameraExecutorReady) return
        val analysis = imageAnalyzer ?: return
        if (activeCodeAnalyzer == null) {
            val generation = ++liveAnalysisGeneration
            val decoder = QRCodeAnalyzer { code ->
                mainHandler.post {
                    // A frame may finish after a picker opens or the screen
                    // pauses. Never let that stale frame start a payment.
                    if (generation == liveAnalysisGeneration && scannerResumed && !galleryPending) {
                        processQRCode(code)
                    }
                }
            }
            activeCodeAnalyzer = decoder
            analysis.setAnalyzer(cameraExecutor, decoder)
        }
        startScanLineAnimation()
    }

    private fun stopLiveAnalysis() {
        liveAnalysisGeneration++
        imageAnalyzer?.clearAnalyzer()
        activeCodeAnalyzer = null
        scanLineAnimator?.cancel()
    }

    /**
     * A scanned code that isn't a usable UPI QR. This is NOT an error state:
     * the camera keeps running, the banner explains what was wrong, and
     * scanning re-arms so the user can just aim at another code.
     *
     * Previously this went through [showError], which blanked the preview to a
     * black screen with red "Error:" text AND fired a duplicate toast, then sat
     * dead for three seconds — which reads as the scanner having crashed.
     */
    private fun showInvalidQrCode(reason: String) {
        runOnUiThread {
            if (!isActivityAlive()) return@runOnUiThread
            val title = getString(R.string.qr_invalid_title)
            val message = "$title\n$reason"
            if (tvScanError.text.toString() != message) {
                tvScanError.text = android.text.SpannableString(message).apply {
                    setSpan(android.text.style.StyleSpan(android.graphics.Typeface.BOLD), 0, title.length, 0)
                    setSpan(android.text.style.RelativeSizeSpan(ERROR_TITLE_SP / ERROR_BODY_SP), 0, title.length, 0)
                }
            }
            val wasVisible = tvScanError.visibility == View.VISIBLE
            viewFinder.visibility = View.VISIBLE
            scannerOverlay.visibility = View.VISIBLE
            bottomActionBar.visibility = View.VISIBLE
            topBar.visibility = View.VISIBLE
            progressBar.visibility = View.GONE
            tvStatus.visibility = View.GONE
            tvScanError.visibility = View.VISIBLE
            if (!wasVisible) {
                tvScanError.alpha = 0f
                tvScanError.animate().alpha(1f).setDuration(FEEDBACK_FADE_MS).start()
            }

            // Re-arm immediately: the next frame holding a good QR should be
            // accepted even while the banner is still on screen.
            isProcessingQRCode = false
            activeCodeAnalyzer?.resetProcessing()
            resumeLiveScanning()

            mainHandler.removeCallbacks(hideScanErrorRunnable)
            mainHandler.postDelayed(hideScanErrorRunnable, SCAN_ERROR_VISIBLE_MS)
        }
    }

    private val hideScanErrorRunnable = Runnable {
        if (isActivityAlive() && ::tvScanError.isInitialized) {
            tvScanError.visibility = View.GONE
        }
    }

    private fun showError(message: String) {
        runOnUiThread {
            if (!isActivityAlive()) return@runOnUiThread
            Log.e("QRScanner", "Showing error: $message")

            // Show error on black screen
            updateBlackScreenStatus(R.string.qr_error_prefix, message)
            tvStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_red_light))

            // Show toast for additional feedback
            Toast.makeText(this, message, Toast.LENGTH_LONG).show()

            // Resume scanning after 3 seconds with proper error recovery
            mainHandler.postDelayed({
                if (!isActivityAlive()) return@postDelayed
                try {
                    Log.d("QRScanner", "Resuming QR scanning after error")
                    // Reset to camera view
                    qrGuideVisible = false
                    qrTriggeredAt = null
                    mainHandler.removeCallbacks(revealQrAnswers)
                    findViewById<View>(R.id.qrOutcomePanel).visibility = View.GONE
                    viewFinder.visibility = View.VISIBLE
                    scannerOverlay.visibility = View.VISIBLE
                    bottomActionBar.visibility = View.VISIBLE
                    topBar.visibility = View.VISIBLE // Show top bar again
                    tvStatus.visibility = View.GONE
                    instructionsBox.visibility = View.GONE
                    btnTerminate.visibility = View.GONE
                    // Reset flash state
                    isFlashOn = false
                    camera?.cameraControl?.enableTorch(false)
                    btnFlash.setImageResource(R.drawable.ic_flash_off)
                    btnFlash.setBackgroundResource(R.drawable.bottom_action_button_bg)
                    startScanLineAnimation()

                    // Reset instruction states
                    instructionsHeaderInitial.visibility = View.VISIBLE
                    instructionsHeaderInitial.alpha = 1f
                    instructionsExpanded.visibility = View.GONE
                    instructionsExpanded.alpha = 1f

                    findViewById<View>(
                        android.R.id.content
                    ).setBackgroundColor(ContextCompat.getColor(this, android.R.color.black))

                    // Resuming after an error: clear both the processing and dialed flags.
                    isProcessingQRCode = false
                    hasDialedUSSD = false
                    stopLiveAnalysis()
                    resumeLiveScanning()
                } catch (e: Exception) {
                    Log.e("QRScanner", "Failed to resume scanning", e)
                    Toast.makeText(this, R.string.error_qr_resume_failed, Toast.LENGTH_LONG).show()
                }
            }, 3000)
        }
    }

    private fun startScanLineAnimation() {
        if (!::scanLine.isInitialized || scanLine.visibility != View.VISIBLE || !scannerResumed) return
        scanLineAnimator?.cancel()
        val density = resources.displayMetrics.density
        // Scanner frame is 260dp; margins 12dp each side; line is 2dp — travel ~234dp
        val maxTranslation = ((260 - 12 * 2 - 2) * density)
        scanLineAnimator = android.animation.ObjectAnimator.ofFloat(
            scanLine, "translationY", 0f, maxTranslation
        ).apply {
            duration = 2000
            repeatMode = android.animation.ValueAnimator.REVERSE
            repeatCount = android.animation.ValueAnimator.INFINITE
            interpolator = android.view.animation.AccelerateDecelerateInterpolator()
            start()
        }
    }

    override fun onPause() {
        scannerResumed = false
        super.onPause()
        Log.d("QRScanner", "Activity paused - stopping camera and terminating USSD overlay")

        // Send app paused broadcast to USSD overlay service
        try {
            val intent = Intent("APP_PAUSED")
            LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
            Log.d("QRScanner", "App paused broadcast sent")
        } catch (e: Exception) {
            Log.e("QRScanner", "Error sending app paused broadcast: ${e.message}")
        }

        // Terminate USSD overlay when activity is paused

        try {
            stopLiveAnalysis()
            // Do NOT reset isProcessingQRCode here: when user goes to dialer we pause;
            // if we reset the flag, onResume would re-attach the analyzer and dial again in a loop.
            // Flag is reset only in onDestroy or in showError() when resuming scanning.
        } catch (e: Exception) {
            Log.e("QRScanner", "Error stopping camera on pause: ${e.message}", e)
        }
    }

    override fun onStop() {
        super.onStop()
        Log.d("QRScanner", "Activity stopped - terminating USSD overlay")

        // Send app stopped broadcast to USSD overlay service
        try {
            val intent = Intent("APP_STOPPED")
            LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
            Log.d("QRScanner", "App stopped broadcast sent")
        } catch (e: Exception) {
            Log.e("QRScanner", "Error sending app stopped broadcast: ${e.message}")
        }

        // Terminate USSD overlay when activity is stopped
    }

    override fun onResume() {
        super.onResume()
        scannerResumed = true
        PayNetViewTheme.scanner(findViewById(android.R.id.content))
        if (qrGuideVisible) showSmsWaitingState()
        Log.d("QRScanner", "Activity resumed - restarting camera")
        try {
            // Guard against shutdown executor
            if (!::cameraExecutor.isInitialized || cameraExecutor.isShutdown) {
                Log.w("QRScanner", "Camera executor not available, skipping analyzer reattach")
                return
            }
            if (galleryPending && galleryResult != null) {
                consumeGalleryResult()
            } else if (galleryPending && galleryDecodeJob == null) {
                galleryUri?.let(::decodeQrFromGallery)
            }
            resumeLiveScanning()
        } catch (e: Exception) {
            Log.e("QRScanner", "Error restarting camera on resume: ${e.message}", e)
        }
    }

    private fun showSmsWaitingState() {
        findViewById<View>(R.id.qrOutcomePanel).visibility = View.GONE
        updateBlackScreenStatus(R.string.sms_waiting_confirmation)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("galleryPending", galleryPending)
        outState.putString("galleryUri", galleryUri?.toString())
        outState.putString("qrTransactionId", qrTransactionId)
        outState.putBoolean("qrGuideVisible", qrGuideVisible)
        outState.putBoolean("hasDialedUSSD", hasDialedUSSD)
        qrTriggeredAt?.let { outState.putLong("qrTriggeredAt", it) }
        outState.putString("copiedVpaToken", copiedVpaToken)
        outState.putString("copiedVpa", copiedVpa)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        try {
            scannerResumed = false
            galleryDecodeJob?.cancel()
            galleryDecodeJob = null
            stopLiveAnalysis()
            Log.d("QRScanner", "Destroying QR scanner activity...")

            // Cancel ALL pending callbacks from centralized handler
            mainHandler.removeCallbacksAndMessages(null)

            // Send app destroyed broadcast to USSD overlay service
            try {
                val intent = Intent("APP_DESTROYED")
                LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
                Log.d("QRScanner", "App destroyed broadcast sent")
            } catch (e: Exception) {
                Log.e("QRScanner", "Error sending app destroyed broadcast: ${e.message}")
            }

            // Terminate USSD overlay when activity is destroyed

            // Stop USSD process
            isUSSDProcessActive = false
            messageHandler?.removeCallbacksAndMessages(null)

            // Reset processing flags.
            isProcessingQRCode = false
            hasDialedUSSD = false

            // Leaving this screen with a payment still in flight (system back,

            // closes with it and the next scan isn't refused as "already in
            // progress". A no-op once the session reached a terminal state,
            // and `isFinishing` keeps a config change from cancelling a live
            // payment. `finishedByWaitingScreenTimeout` excludes the one exit
            // that is NOT the user abandoning anything: our own waiting-screen
            // timer giving the screen back on its own timeout while the
            // payment is still legitimately in flight.
            if (isFinishing && !finishedByWaitingScreenTimeout) {
                PayNetApplication.from(this)?.paymentSessionManager
                    ?.takeIf { it.paymentState.value.getTransactionIdValue() == qrTransactionId }
                    ?.onUserCancelled()
            }

            // A configuration change must preserve the VPA until this flow actually ends.
            if (isFinishing) clearVpaClipboard()

            // Cancel scan line animation
            scanLineAnimator?.cancel()
            scanLineAnimator = null

            // Unregister broadcast receivers
            try {
                LocalBroadcastManager.getInstance(this).unregisterReceiver(overlayDismissReceiver)
            } catch (e: Exception) {
                Log.e("QRScanner", "Error unregistering receivers: ${e.message}")
            }

            // Clear image analyzer first
            imageAnalyzer?.clearAnalyzer()
            imageAnalyzer = null

            // Shutdown camera executor safely
            if (::cameraExecutor.isInitialized && !cameraExecutor.isShutdown) {
                cameraExecutor.shutdown()
                Log.d("QRScanner", "Camera executor shutdown")
            }

            Log.d("QRScanner", "QR scanner activity destroyed successfully")
        } catch (e: Exception) {
            Log.e("QRScanner", "Error during activity destruction: ${e.message}", e)
        } finally {
            super.onDestroy()
        }
    }
}
