// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.services

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Rect
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.util.Log
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import android.widget.Toast
import com.paynet.app.PayNetApplication
import com.paynet.app.R
import com.paynet.app.managers.TransactionDialogManager
import com.paynet.app.payment.PaymentSessionManager
import com.paynet.app.states.PaymentState
import com.paynet.app.telephony.CallStateCoordinator
import com.paynet.app.telephony.DeviceCallState
import com.paynet.app.ui.theme.PayNetViewTheme
import com.paynet.app.utils.OverlayLogger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class CallOverlayService : Service() {

    companion object {
        private const val TAG = "CallOverlayService"
        private const val ACTION_START_OVERLAY = "START_OVERLAY"
        private const val ACTION_STOP_OVERLAY = "STOP_OVERLAY"
        private const val TIMEOUT_DURATION = 40000L // 40 seconds timeout
        private const val TIMEOUT_EXTENSION_MS = 10000L // re-arm step while device not idle
        private const val MAX_TIMEOUT_EXTENSIONS = 3 // bounded: +30s worst case

        // Cleared in onDestroy(), so the reference is bounded by the service
        // lifecycle. Lint's StaticFieldLeak is baselined for this line; see
        // SECURITY.md "Known deferred issues".
        private var serviceInstance: CallOverlayService? = null

        /**
         * Shows the call overlay with payment details
         */
        fun showOverlay(context: Context, phoneNumber: String, amount: String) {
            try {
                Log.d(TAG, "=== Starting call overlay ===")

                // Stop any existing service first
                if (serviceInstance != null) {
                    Log.d(TAG, "Stopping existing service before starting new one")
                    context.stopService(Intent(context, CallOverlayService::class.java))
                    Handler(Looper.getMainLooper()).postDelayed({
                        startNewService(context, phoneNumber, amount)
                    }, 500)
                } else {
                    startNewService(context, phoneNumber, amount)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start call overlay service: ${e.message}")
            }
        }

        private fun startNewService(context: Context, phoneNumber: String, amount: String) {
            try {
                val intent = Intent(context, CallOverlayService::class.java).apply {
                    putExtra("action", ACTION_START_OVERLAY)
                    putExtra("phone_number", phoneNumber)
                    putExtra("amount", amount)
                }
                context.startService(intent)

                // Wait for service to be ready before proceeding
                Handler(Looper.getMainLooper()).postDelayed({
                    if (serviceInstance == null) {
                        Log.w(TAG, "Service not ready, retrying...")
                        context.startService(intent)
                    }
                }, 100)

                Log.d(TAG, "Call overlay service started")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start new service: ${e.message}")
            }
        }

        /**
         * Hides the call overlay
         */
        fun hideOverlay(context: Context) {
            try {
                val intent = Intent(context, CallOverlayService::class.java).apply {
                    putExtra("action", ACTION_STOP_OVERLAY)
                }
                context.startService(intent)
                Log.d(TAG, "Call overlay hide requested")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to hide call overlay: ${e.message}")
            }
        }
    }

    private val binder = CallOverlayBinder()
    private var isOverlayActive = false
    private var overlayView: View? = null
    private var windowManager: WindowManager? = null
    private var isOverlayShowing = false

    // Timeout management
    private var timeoutHandler: Handler? = null
    private var timeoutRunnable: Runnable? = null
    private var timeoutExtensions = 0
    private var isCallDetected = false
    private var postCallPromptActive = false
    private var serviceStartTime = 0L
    private var pendingPhoneNumber = ""
    private var pendingAmount = ""

    // Call/payment state observation and dialog management
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var coordinator: CallStateCoordinator? = null
    private var sessionManager: PaymentSessionManager? = null
    private var coordinatorAcquired = false
    private var resultHandled = false
    private var dialogManager: TransactionDialogManager? = null

    // Call management
    private var callManager: com.paynet.app.managers.CallManager? = null

    // Retry bookkeeping for overlay creation (see showOverlayWithRetry).
    private var retryCount = 0
    private val maxRetries = 3

    // Bank instructions are cancelled on every state change and when the overlay hides.
    private val pacingHandler = Handler(Looper.getMainLooper())
    private var progressPacing: CallOverlayProgress? = null
    private var guidanceMotion: CallOverlayMessageMotion? = null

    inner class CallOverlayBinder : Binder() {
        fun getService(): CallOverlayService = this@CallOverlayService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    // Deliberately NOT a foreground service. On targetSdk 35 an FGS needs a
    // foregroundServiceType the app can't honestly claim ("phoneCall"
    // requires MANAGE_OWN_CALLS + a ConnectionService; "specialUse" invites
    // Play review friction). Survival is covered without it: the service is
    // started while the app is foreground, and once the call goes OFFHOOK
    // its TYPE_APPLICATION_OVERLAY window keeps the process perceptible for
    // the call's duration; the pre-OFFHOOK gap is bounded by the 40s(+30s)
    // watchdog, well inside the started-service grace period. Revisit only
    // if field logs ever show mid-call service death.
    override fun onCreate() {
        super.onCreate()
        val startTime = System.currentTimeMillis()
        serviceInstance = this
        serviceStartTime = startTime

        OverlayLogger.logServiceEvent(
            "SERVICE_CREATED",
            mapOf(
                "timestamp" to startTime
            )
        )

        // Initialize timeout handler
        timeoutHandler = Handler(Looper.getMainLooper())

        // Initialize dialog manager; dismissing a result dialog acknowledges
        // the payment session so the result isn't shown again elsewhere.
        dialogManager = TransactionDialogManager(this) {
            sessionManager?.acknowledgeResult()
        }

        // Initialize call manager
        callManager = com.paynet.app.managers.CallManager(this)

        // Observe the single app-wide call-state authority and the payment
        // session. These replace the service's own PhoneStateListener and
        // the old duration-based outcome guessing.
        PayNetApplication.from(this)?.let { app ->
            coordinator = app.callStateCoordinator
            sessionManager = app.paymentSessionManager
            coordinator?.acquire("call-overlay-service")
            coordinatorAcquired = true

            serviceScope.launch {
                app.callStateCoordinator.callState.collect { state ->
                    when (state) {
                        is DeviceCallState.OffHook -> onCallDetected()
                        is DeviceCallState.Idle -> if (isCallDetected) {
                            callManager?.restoreCallVolume()
                            hideOverlayInternal()
                        }
                        else -> Unit
                    }
                }
            }

            serviceScope.launch {
                app.paymentSessionManager.paymentState.collectLatest { state ->
                    onPaymentStateChanged(state)
                }
            }
        }

        Log.d(TAG, "CallOverlayService initialization complete")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "CallOverlayService started with action: ${intent?.getStringExtra("action")}")

        when (intent?.getStringExtra("action")) {
            ACTION_START_OVERLAY -> {
                val phoneNumber = intent.getStringExtra("phone_number") ?: ""
                val amount = intent.getStringExtra("amount") ?: ""
                showOverlayInternal(phoneNumber, amount)
            }
            ACTION_STOP_OVERLAY -> {
                hideOverlayInternal()
            }
        }

        // NOT sticky: a system restart with a null intent would only produce
        // a zombie service with no pending payment to protect.
        return START_NOT_STICKY
    }

    /**
     * Drives overlay content and result dialogs from the payment session.
     * Duration heuristics never decide outcomes — the session does.
     */
    private fun onPaymentStateChanged(state: PaymentState) {
        // Any real state change supersedes the in-call pacing.
        cancelProgressPacing()
        when (state) {
            is PaymentState.InProgress -> {
                updateOverlayStatus(
                    status = getString(R.string.overlay_processing_payment),
                    step = getString(R.string.overlay_sending_request)
                )
                startInCallPacing()
            }
            is PaymentState.WaitingForVerification -> {
                finishWithResult { }
            }
            is PaymentState.Success -> {
                vibrate()
                endCallOnConfirmation()

                // success surface; no extra dialog from the service.
                finishWithResult { }
            }
            is PaymentState.Failed -> {
                endCallOnConfirmation()
                finishWithResult { dialogManager?.showTransactionFailed() }
            }
            is PaymentState.NeedsReview -> {
                endCallOnConfirmation()

                // the NEEDS_REVIEW status extra) is the review surface; no
                // extra dialog from the service.
                finishWithResult { }
            }
            is PaymentState.Cancelled -> {
                val byUser = state.reason.contains("by user", ignoreCase = true)
                finishWithResult {
                    if (byUser) {
                        dialogManager?.showTransactionCancelledByUser()
                    } else {
                        dialogManager?.showTransactionCancelled()
                    }
                }
            }
            is PaymentState.Timeout -> {
                // payment to report: the row is discarded and nothing is
                // shown. Just wind the overlay down.
                finishWithResult { }
            }
            else -> Unit
        }
    }

    private fun endCallOnConfirmation() {
        val ended = runCatching { callManager?.terminateCall() ?: false }.getOrDefault(false)
        Log.d(TAG, "Confirmation arrived - auto-hangup ${if (ended) "succeeded" else "not needed"}")
    }

    /** Hide the overlay, show the result surface once, and wind the service down. */
    private fun finishWithResult(showDialog: () -> Unit) {
        if (resultHandled) return
        resultHandled = true
        callManager?.restoreCallVolume()
        hideOverlayInternal()
        showDialog()
        Handler(Looper.getMainLooper()).postDelayed({ stopSelf() }, 1000)
    }

    /** Restore the call guide's pacing, independently of the unchanged bank instructions. */
    private fun startInCallPacing() {
        val view = overlayView ?: return
        progressPacing = CallOverlayProgress(view).also { it.showInCall() }
        guidanceMotion = CallOverlayView.scheduleBankGuidance(view, pacingHandler)
    }

    /** Stops the in-call pacing so a settled state is never overwritten. */
    private fun cancelProgressPacing() {
        pacingHandler.removeCallbacksAndMessages(null)
        guidanceMotion?.stop()
        guidanceMotion = null
        progressPacing?.stop()
        progressPacing = null
    }

    /** Update the overlay texts/progress to reflect the real session state. */
    private fun updateOverlayStatus(status: String, step: String) {
        // Service callbacks and session collection already run on the main thread.
        overlayView?.let { view ->
            view.findViewById<TextView>(R.id.statusText)?.text = status
            view.findViewById<TextView>(R.id.stepText)?.text = step
        }
    }

    private fun vibrate() {
        val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(
                VibrationEffect.createOneShot(
                    200,
                    VibrationEffect.DEFAULT_AMPLITUDE
                )
            )
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(200)
        }
    }

    /**
     * Check if overlay permission is granted
     */
    private fun checkOverlayPermission(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(this)
        } else {
            true // Pre-Marshmallow doesn't need this permission
        }
    }

    /**
     * Show error toast when overlay permission is not granted
     */
    private fun showPermissionErrorToast() {
        Handler(Looper.getMainLooper()).post {
            Toast.makeText(
                this,
                "Overlay permission required for call protection. Please grant permission in Settings.",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    /**
     * Show overlay with retry mechanism
     */
    private fun showOverlayWithRetry(phoneNumber: String, amount: String) {
        try {
            createSystemOverlay(phoneNumber, amount)
            retryCount = 0 // Reset on success
            Log.d(TAG, "Overlay created successfully")
        } catch (e: Exception) {
            if (retryCount < maxRetries) {
                retryCount++
                Log.w(TAG, "Overlay creation failed, retrying ($retryCount/$maxRetries): ${e.message}")
                Handler(Looper.getMainLooper()).postDelayed({
                    showOverlayWithRetry(phoneNumber, amount)
                }, (1000 * retryCount).toLong()) // Exponential backoff
            } else {
                Log.e(TAG, "Max retries exceeded for overlay creation, giving up")
                showOverlayErrorToast()
            }
        }
    }

    /**
     * Show error toast when overlay creation fails
     */
    private fun showOverlayErrorToast() {
        Handler(Looper.getMainLooper()).post {
            Toast.makeText(
                this,
                "Failed to show call protection overlay. Please try again.",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    private fun showOverlayInternal(phoneNumber: String, amount: String) {
        try {
            Log.d(TAG, "=== CallOverlayService.showOverlayInternal() ===")
            Log.d(TAG, "Call overlay service started")
            Log.d(TAG, "Current state - isOverlayActive: $isOverlayActive, isCallDetected: $isCallDetected")

            // Reset state for a new call.
            resetServiceState()

            // Store phone number and amount for when call is detected
            pendingPhoneNumber = phoneNumber
            pendingAmount = amount

            // Start timeout timer - overlay will be hidden after 40 seconds if no call detected
            startTimeoutTimer()

            Log.d(TAG, "=== CallOverlayService ready for call detection ===")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start call overlay service: ${e.message}")
        }
    }

    /**
     * Reset service state for new call
     */
    private fun resetServiceState() {
        Log.d(TAG, "Resetting service state for new call")
        isOverlayActive = false
        isOverlayShowing = false
        isCallDetected = false
        pendingPhoneNumber = ""
        pendingAmount = ""

        // Cancel any existing timeouts
        timeoutRunnable?.let {
            timeoutHandler?.removeCallbacks(it)
        }

        // Hide any existing overlay
        if (overlayView != null) {
            try {
                windowManager?.removeView(overlayView)
                overlayView = null
            } catch (e: Exception) {
                Log.e(TAG, "Error removing existing overlay: ${e.message}")
            }
        }

        Log.d(TAG, "Service state reset complete")
    }

    /**
     * Start the 40-second timeout timer.
     *
     * Before declaring "the call never started", the runnable consults the
     * coordinator's live state: if the device is ringing/off-hook (or the
     * OFFHOOK collector is simply lagging), the timer re-arms in 10s steps
     * (max 3, +30s total) instead of cancelling a session whose call is in
     * fact connecting. Only a persistently Idle device cancels.
     */
    @Suppress("TooGenericExceptionCaught") // see comment below: must never crash the main looper mid-payment
    private fun startTimeoutTimer() {
        Log.d(TAG, "Starting 40-second timeout timer")

        timeoutExtensions = 0
        timeoutRunnable = Runnable {
            val shouldGiveUp = try {
                if (isCallDetected) {
                    false
                } else {
                    val deviceBusy = coordinator?.callState?.value !is DeviceCallState.Idle
                    if (deviceBusy && timeoutExtensions < MAX_TIMEOUT_EXTENSIONS) {
                        timeoutExtensions++
                        Log.d(
                            TAG,
                            "Timeout reached but device not idle - re-arming " +
                                "($timeoutExtensions/$MAX_TIMEOUT_EXTENSIONS)"
                        )
                        timeoutHandler?.postDelayed(timeoutRunnable!!, TIMEOUT_EXTENSION_MS)
                        false
                    } else {
                        Log.d(TAG, "Timeout reached - no call detected, stopping service")
                        true
                    }
                }
            } catch (e: Exception) {
                // This Runnable executes on the main looper (timeoutHandler =
                // Handler(Looper.getMainLooper())): an uncaught exception here
                // would crash the whole app AND skip the session notification
                // below, stranding the payment until the 10-minute deadline.
                // Log and still give up cleanly rather than let either happen.
                Log.e(TAG, "Error in timeout timer: ${e.message}", e)
                true
            }

            if (shouldGiveUp) {
                // The dial never produced an active call; close the session
                // honestly instead of leaving it to the 10-minute deadline.
                sessionManager?.onCallNeverStarted()
                hideOverlayInternal()
                stopSelf()
            }
        }

        timeoutHandler?.postDelayed(timeoutRunnable!!, TIMEOUT_DURATION)
    }

    /**
     * Handle call detection - show overlay when call is actually dialed
     */
    fun onCallDetected() {
        if (postCallPromptActive) return // The bank callback must not reopen the in-call guide.
        OverlayLogger.logCallDetection(
            pendingPhoneNumber,
            "CALL_DETECTED",
            "isCallDetected: $isCallDetected, isOverlayActive: $isOverlayActive"
        )

        Log.d(TAG, "=== onCallDetected() called ===")
        Log.d(TAG, "isCallDetected: $isCallDetected")
        Log.d(TAG, "isOverlayActive: $isOverlayActive")
        Log.d(TAG, "serviceInstance: $serviceInstance")

        // Bail out unless the service finished initializing.
        if (serviceInstance == null) {
            Log.e(TAG, "Service instance is null - cannot show overlay")
            return
        }

        // New call (not one already detected) — reset state.
        if (!isCallDetected) {
            Log.d(TAG, "New call detected - resetting state")
            isCallDetected = true
        } else {
            Log.d(TAG, "Call already detected, checking if overlay is active")
            if (isOverlayActive) {
                Log.d(TAG, "Overlay already active, ignoring duplicate detection")
                return
            }
        }

        if (pendingPhoneNumber.isNullOrBlank() || pendingAmount.isNullOrBlank()) {
            Log.e(TAG, "Missing pending payment data - cannot show overlay")
            return
        }

        Log.d(TAG, "Call detected - showing overlay")

        // Cancel timeout timer since call was detected
        timeoutRunnable?.let {
            timeoutHandler?.removeCallbacks(it)
            Log.d(TAG, "Timeout timer cancelled")
        }

        // Overlay must be created on the main thread; retried, see showOverlayWithRetry.
        Handler(Looper.getMainLooper()).post {
            try {
                Log.d(TAG, "Creating system overlay on main thread...")
                showOverlayWithRetry(pendingPhoneNumber, pendingAmount)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to create overlay: ${e.message}")
                showOverlayErrorToast()
            }
        }
    }

    private fun createSystemOverlay(phoneNumber: String, amount: String) {
        Log.d(TAG, "=== createSystemOverlay() called ===")

        // Check overlay permission before creating overlay
        if (!checkOverlayPermission()) {
            OverlayLogger.logPermissionEvent("SYSTEM_ALERT_WINDOW", false, "overlay_creation")
            Log.e(TAG, "Overlay permission not granted - cannot show overlay")
            showPermissionErrorToast()
            return
        }

        OverlayLogger.logPermissionEvent("SYSTEM_ALERT_WINDOW", true, "overlay_creation")

        try {
            windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
            Log.d(TAG, "WindowManager obtained: $windowManager")

            val inflater = LayoutInflater.from(this)
            Log.d(TAG, "LayoutInflater obtained: $inflater")

            overlayView = inflater.inflate(R.layout.call_overlay_paynet, null)
            overlayView?.let { PayNetViewTheme.observe(it, PayNetViewTheme::callOverlay) }
            Log.d(TAG, "Overlay view inflated: $overlayView")

            CallOverlayView.bind(overlayView, phoneNumber, amount)
            val layoutParams = CallOverlayView.windowParameters()
            CallOverlayView.prepareEntrance(overlayView)

            // Add the overlay view with error handling
            try {
                Log.d(TAG, "Adding overlay view to WindowManager...")
                Log.d(TAG, "overlayView: $overlayView")
                Log.d(TAG, "layoutParams: $layoutParams")

                windowManager?.addView(overlayView, layoutParams)
                isOverlayActive = true
                isOverlayShowing = true

                OverlayLogger.logOverlayState(
                    "CREATED",
                    true,
                    details = mapOf(
                        "phoneNumber" to phoneNumber,
                        "amount" to amount,
                        "isOverlayActive" to isOverlayActive,
                        "isOverlayShowing" to isOverlayShowing
                    )
                )

                Log.d(TAG, "System overlay created and shown successfully")
                Log.d(TAG, "isOverlayActive: $isOverlayActive, isOverlayShowing: $isOverlayShowing")

                CallOverlayView.animateEntrance(overlayView)

                overlayView?.let { view ->
                    progressPacing = CallOverlayProgress(view).also { it.showConnecting() }
                }

                // This bar estimates call guidance; only the session supplies payment outcomes.
                updateOverlayStatus(
                    status = getString(R.string.overlay_processing_payment),
                    step = getString(R.string.overlay_connecting)
                )

                if (sessionManager?.paymentState?.value is PaymentState.InProgress) {
                    onPaymentStateChanged(sessionManager!!.paymentState.value)
                }

                // Setup touch handling for interactive overlay
                setupOverlayTouchHandling()

                // Setup terminate button
                setupTerminateButton()

                // Lower the IVR call volume - delay to ensure the call is active.
                // Only reveal the "Call volume lowered" pill if it actually
                // worked, so the overlay never claims an action that didn't run.
                Handler(Looper.getMainLooper()).postDelayed({
                    Log.d(TAG, "Setting call volume to minimum after delay")
                    val lowered = callManager?.setCallVolumeToMinimum() ?: false
                    if (lowered) {
                        overlayView?.findViewById<View>(R.id.mutedIndicator)?.visibility = View.VISIBLE
                    }
                }, 2000) // 2 second delay to ensure call is active
            } catch (e: Exception) {
                Log.e(TAG, "Failed to add overlay view: ${e.message}")
                // Clean up on failure
                cancelProgressPacing()
                overlayView?.animate()?.cancel()
                overlayView = null
                isOverlayActive = false
                isOverlayShowing = false
                throw e
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create system overlay: ${e.message}")
        }
    }

    /**
     * Setup touch event handling for interactive overlay
     */
    private fun setupOverlayTouchHandling() {
        overlayView?.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    // Check if touch is on the card area
                    val cardView = view.findViewById<View>(R.id.overlayContainer)
                    val cardRect = Rect()
                    cardView.getHitRect(cardRect)

                    // Convert touch coordinates to card coordinates
                    val cardX = event.x - cardView.x
                    val cardY = event.y - cardView.y

                    if (cardRect.contains(cardX.toInt(), cardY.toInt())) {
                        Log.d(TAG, "Touch on overlay card - handling")
                        // Touch is on the card, handle it
                        true
                    } else {
                        Log.d(TAG, "Touch outside overlay card - passing through")
                        // Touch is outside card, let it pass through to native dialer
                        false
                    }
                }
                MotionEvent.ACTION_UP -> {
                    Log.d(TAG, "Touch released on overlay")
                    // A touch listener that consumes ACTION_UP swallows the
                    // click that accessibility services synthesise, so the
                    // overlay would be unreachable via TalkBack. Forwarding to
                    // performClick keeps it announced and actionable.
                    view.performClick()
                    true
                }
                else -> false
            }
        }
    }

    /**
     * Setup terminate button click handler
     */
    private fun setupTerminateButton() {
        val terminateButton = overlayView?.findViewById<android.widget.Button>(R.id.terminateButton)
        if (terminateButton != null) {
            Log.d(TAG, "Terminate button found, setting up click listener")
            terminateButton.setOnClickListener {
                Log.d(TAG, "Terminate button clicked - starting termination process")
                handleTerminateCall()
            }
        } else {
            Log.e(TAG, "Terminate button not found in overlay view!")
        }
    }

    /**
     * Handle terminate call button click
     */
    private fun handleTerminateCall() {
        Log.d(TAG, "=== HANDLING TERMINATE CALL REQUEST ===")

        // Mark the session cancelled first and unconditionally — the
        // payment-state collector hides the overlay and shows the
        // cancellation dialog exactly once. This must run outside the try
        // below: audio/telecom cleanup is best-effort UI polish and must
        // never be able to prevent the session from being marked cancelled.
        sessionManager?.onUserCancelled()

        try {
            callManager?.restoreCallVolume()

            val callTerminated = callManager?.terminateCall() ?: false
            if (!callTerminated) {
                Log.w(TAG, "Failed to terminate call programmatically")
                Toast.makeText(
                    this,
                    "Unable to end the call automatically. Please hang up manually.",
                    Toast.LENGTH_LONG
                ).show()
            }

            // If no session was active (defensive), still wind down cleanly.
            if (sessionManager == null) {
                hideOverlayInternal()
                dialogManager?.showTransactionCancelledByUser()
                Handler(Looper.getMainLooper()).postDelayed({ stopSelf() }, 1000)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling terminate call: ${e.message}", e)
            hideOverlayInternal()
            Handler(Looper.getMainLooper()).postDelayed({ stopSelf() }, 1000)
        }
    }

    private fun hideOverlayInternal() {
        try {
            // Stop pacing first: a running animator must never outlive the
            // view it drives.
            cancelProgressPacing()
            overlayView?.animate()?.cancel()
            if (!isOverlayActive || overlayView == null) {
                Log.w(TAG, "Overlay not active, ignoring hide request")
                return
            }

            Log.d(TAG, "Hiding system overlay")

            // Remove the overlay view from window manager
            windowManager?.removeView(overlayView)
            overlayView = null
            isOverlayActive = false
            isOverlayShowing = false

            Log.d(TAG, "System overlay hidden successfully")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to hide system overlay: ${e.message}")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            // Cancel timeout timer
            timeoutRunnable?.let {
                timeoutHandler?.removeCallbacks(it)
            }

            // Stop observing call/payment state
            serviceScope.cancel()
            if (coordinatorAcquired) {
                coordinator?.release("call-overlay-service")
                coordinatorAcquired = false
            }

            hideOverlayInternal() // Clean up overlay if still active
        } catch (e: Exception) {
            Log.e(TAG, "Error during service teardown: ${e.message}")
        }
        isOverlayActive = false
        isOverlayShowing = false
        isCallDetected = false

        serviceInstance = null
        Log.d(TAG, "CallOverlayService destroyed - ready for restart")
    }
}
