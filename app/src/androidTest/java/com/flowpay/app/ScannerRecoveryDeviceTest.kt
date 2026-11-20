// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.Manifest
import android.app.Activity
import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.ImageFormat
import android.net.Uri
import android.os.SystemClock
import android.view.View
import android.widget.TextView
import androidx.camera.core.ImageProxy
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleCallback
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.UiDevice
import com.flowpay.app.features.qr_scanner.domain.QRCodeAnalyzer
import com.flowpay.app.features.qr_scanner.presentation.QRScannerActivity
import com.google.zxing.BarcodeFormat
import com.google.zxing.MultiFormatWriter
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.lang.reflect.Proxy
import java.nio.ByteBuffer
import java.util.concurrent.ExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** Only invalid QR payloads reach this activity; all dial intents are blocked. */
@RunWith(AndroidJUnit4::class)
class ScannerRecoveryDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val device = UiDevice.getInstance(instrumentation)
    private val preferences = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
    private var savedPreferences: Map<String, *>? = null
    private var scenario: ActivityScenario<QRScannerActivity>? = null
    private val monitors = mutableListOf<Instrumentation.ActivityMonitor>()
    private val fixtureFiles = mutableListOf<File>()

    @Before
    fun prepareIsolatedScanner() {
        assertEquals("Scanner fixtures must never run in production", "com.flowpay.app.setupcheck", context.packageName)
        assertEquals("Grant CAMERA to the isolated test app before running scanner tests",
            PackageManager.PERMISSION_GRANTED, context.checkSelfPermission(Manifest.permission.CAMERA))
        savedPreferences = HashMap(preferences.all)
        preferences.edit().putString("selected_primary_sim", "airtel")
            .putBoolean("user_reported_ussd_not_working", false).commit()
        for (action in listOf(Intent.ACTION_CALL, Intent.ACTION_DIAL,
            "android.intent.action.CALL_PRIVILEGED", "android.intent.action.CALL_EMERGENCY", Intent.ACTION_VIEW)) {
            monitors += instrumentation.addMonitor(IntentFilter(action).apply { addDataScheme("tel") },
                Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null), true)
        }
        device.wakeUp()
    }

    @After
    fun cleanupIsolatedScanner() {
        if (savedPreferences == null) return
        try {
            scenario?.close()
            instrumentation.waitForIdleSync()
            assertEquals("Scanner recovery must never attempt a call", 0, monitors.sumOf { it.hits })
        } finally {
            monitors.forEach(instrumentation::removeMonitor)
            fixtureFiles.forEach(File::delete)
            val editor = preferences.edit().clear()
            savedPreferences!!.forEach { (key, value) ->
                when (value) {
                    is String -> editor.putString(key, value)
                    is Boolean -> editor.putBoolean(key, value)
                    is Int -> editor.putInt(key, value)
                    is Long -> editor.putLong(key, value)
                    is Float -> editor.putFloat(key, value)
                    is Set<*> -> { @Suppress("UNCHECKED_CAST") editor.putStringSet(key, value as Set<String>) }
                }
            }
            editor.commit()
        }
    }

    @Test
    fun liveInvalidCodeRearmsSameAnalyzerAndAcceptsTheNextFrame() {
        val screen = launchScanner()
        lateinit var decoder: QRCodeAnalyzer
        lateinit var executor: ExecutorService
        screen.onActivity {
            decoder = field(it, "activeCodeAnalyzer") as QRCodeAnalyzer
            executor = field(it, "cameraExecutor") as ExecutorService
        }
        executor.submit { decoder.analyze(frame("https://example.org/not-a-payment")) }.get(5, TimeUnit.SECONDS)
        awaitScreen { it.findViewById<TextView>(R.id.tvScanError).text.contains(context.getString(R.string.qr_reason_not_upi)) }
        screen.onActivity {
            assertSame("Invalid recovery should keep the decoder and its cooldown", decoder, field(it, "activeCodeAnalyzer"))
            assertFalse(field(it, "isProcessingQRCode") as Boolean)
        }
        // A second, different invalid payload proves that the live callback is
        // rearmed without introducing any payment handoff into this device test.
        executor.submit { decoder.analyze(frame("upi://pay?pa=invalid")) }.get(5, TimeUnit.SECONDS)
        awaitScreen { it.findViewById<TextView>(R.id.tvScanError).text.contains(context.getString(R.string.qr_reason_invalid_payee)) }
        screen.onActivity { assertNull(field(it, "qrTransactionId")) }
    }

    @Test
    fun galleryReadingExcludesStaleLiveFramesAndRecoversAfterNoCode() {
        val screen = launchScanner()
        val blank = blankImage()
        screen.onActivity {
            val oldDecoder = field(it, "activeCodeAnalyzer") as QRCodeAnalyzer
            invoke(it, "decodeQrFromGallery", Uri::class.java, Uri.fromFile(blank))
            assertTrue(field(it, "galleryPending") as Boolean)
            assertNull(field(it, "activeCodeAnalyzer"))
            assertFalse(it.findViewById<View>(R.id.btnGallery).isEnabled)
            assertEquals(View.VISIBLE, it.findViewById<View>(R.id.progressBar).visibility)
            assertEquals(context.getString(R.string.qr_gallery_reading), it.findViewById<TextView>(R.id.tvStatus).text.toString())
            (field(it, "cameraExecutor") as ExecutorService).submit {
                oldDecoder.analyze(frame("https://example.org/stale-frame"))
            }.get(5, TimeUnit.SECONDS)
        }
        awaitScreen { it.findViewById<TextView>(R.id.tvScanError).text.contains(context.getString(R.string.qr_gallery_no_code)) }
        awaitScreen { field(it, "activeCodeAnalyzer") != null }
        screen.onActivity {
            assertFalse(field(it, "galleryPending") as Boolean)
            assertTrue(it.findViewById<View>(R.id.btnGallery).isEnabled)
            assertNull(field(it, "qrTransactionId"))
        }
    }

    @Test
    fun galleryResultWaitsUntilResumedBeforeRestoringScanner() {
        val screen = launchScanner()
        val blank = blankImage()
        screen.moveToState(Lifecycle.State.STARTED)
        screen.onActivity { invoke(it, "decodeQrFromGallery", Uri::class.java, Uri.fromFile(blank)) }
        awaitScreen { field(it, "galleryResult") != null }
        screen.onActivity {
            assertTrue(field(it, "galleryPending") as Boolean)
            assertNull(field(it, "activeCodeAnalyzer"))
            assertEquals(View.GONE, it.findViewById<View>(R.id.tvScanError).visibility)
            assertNull(field(it, "qrTransactionId"))
        }
        screen.moveToState(Lifecycle.State.RESUMED)
        awaitScreen { it.findViewById<TextView>(R.id.tvScanError).text.contains(context.getString(R.string.qr_gallery_no_code)) }
        awaitScreen { field(it, "activeCodeAnalyzer") != null }
        screen.onActivity {
            assertFalse(field(it, "galleryPending") as Boolean)
            assertNull(field(it, "qrTransactionId"))
        }
    }

    @Test
    fun queuedGalleryUriSurvivesRecreationWithoutResumingTheOldActivity() {
        val screen = launchScanner()
        val blank = blankImage()
        screen.moveToState(Lifecycle.State.STARTED)
        screen.onActivity { invoke(it, "decodeQrFromGallery", Uri::class.java, Uri.fromFile(blank)) }
        awaitScreen { field(it, "galleryResult") != null }
        screen.onActivity {
            assertTrue(field(it, "galleryPending") as Boolean)
            assertNull(field(it, "activeCodeAnalyzer"))
        }
        recreateWhilePaused(screen)
        screen.moveToState(Lifecycle.State.RESUMED)
        awaitScreen { it.findViewById<TextView>(R.id.tvScanError).text.contains(context.getString(R.string.qr_gallery_no_code)) }
        awaitScreen { field(it, "activeCodeAnalyzer") != null }
        screen.onActivity { assertNull(field(it, "qrTransactionId")) }
    }

    private fun recreateWhilePaused(screen: ActivityScenario<QRScannerActivity>) {
        lateinit var original: QRScannerActivity
        val replacement = AtomicReference<QRScannerActivity>()
        val observer = ActivityLifecycleCallback { activity, stage ->
            if (activity is QRScannerActivity && activity !== original && stage == Stage.CREATED) {
                replacement.set(activity)
            }
        }
        try {
            screen.onActivity {
                original = it
                ActivityLifecycleMonitorRegistry.getInstance().addLifecycleCallback(observer)
                // ActivityScenario.recreate() first RESUMES the old instance,
                // which legitimately consumes its completed gallery result.
                // Request Android recreation directly to test the saved URI
                // while that result is still queued behind the paused screen.
                it.recreate()
            }
            val deadline = SystemClock.elapsedRealtime() + 10_000
            while (replacement.get() == null && SystemClock.elapsedRealtime() < deadline) {
                SystemClock.sleep(50)
            }
            assertNotNull("Android did not replace the paused scanner", replacement.get())
            instrumentation.waitForIdleSync()
            screen.onActivity { assertSame(replacement.get(), it) }
        } finally {
            instrumentation.runOnMainSync {
                ActivityLifecycleMonitorRegistry.getInstance().removeLifecycleCallback(observer)
            }
        }
    }

    @Test
    fun pickerCancellationRestoresLiveScanning() {
        val screen = launchScanner()
        screen.onActivity { it.findViewById<View>(R.id.btnGallery).performClick() }
        awaitScreen { !(field(it, "scannerResumed") as Boolean) }
        device.pressBack()
        awaitScreen { field(it, "scannerResumed") == true && field(it, "activeCodeAnalyzer") != null }
        screen.onActivity {
            assertFalse(field(it, "galleryPending") as Boolean)
            assertTrue(it.findViewById<View>(R.id.btnGallery).isEnabled)
            assertNull(field(it, "qrTransactionId"))
        }
    }

    private fun launchScanner(): ActivityScenario<QRScannerActivity> {
        val launched = ActivityScenario.launch(QRScannerActivity::class.java)
        scenario = launched
        launched.onActivity { it.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
        awaitScreen { field(it, "activeCodeAnalyzer") != null }
        return launched
    }

    private fun awaitScreen(predicate: (QRScannerActivity) -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + 10_000
        do {
            var ready = false
            scenario!!.onActivity { ready = predicate(it) }
            if (ready) return
            SystemClock.sleep(50)
        } while (SystemClock.elapsedRealtime() < deadline)
        fail("Scanner state did not settle within 10 seconds")
    }

    private fun field(activity: QRScannerActivity, name: String): Any? =
        QRScannerActivity::class.java.getDeclaredField(name).apply { isAccessible = true }.get(activity)

    private fun invoke(activity: QRScannerActivity, name: String, type: Class<*>, value: Any) {
        QRScannerActivity::class.java.getDeclaredMethod(name, type).apply { isAccessible = true }.invoke(activity, value)
    }

    private fun blankImage(): File {
        val file = File.createTempFile("scanner-recovery-", ".png", context.cacheDir)
        fixtureFiles += file
        val bitmap = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.WHITE) }
        try { file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        finally { bitmap.recycle() }
        return file
    }

    private fun frame(text: String): ImageProxy {
        val size = 300
        val matrix = MultiFormatWriter().encode(text, BarcodeFormat.QR_CODE, size, size)
        val bytes = ByteArray(size * size) { index -> if (matrix[index % size, index / size]) 0 else 0xFF.toByte() }
        val plane = Proxy.newProxyInstance(ImageProxy.PlaneProxy::class.java.classLoader,
            arrayOf(ImageProxy.PlaneProxy::class.java)) { _, method, _ ->
            when (method.name) {
                "getPixelStride" -> 1
                "getRowStride" -> size
                "getBuffer" -> ByteBuffer.wrap(bytes)
                else -> error("Unexpected plane method ${method.name}")
            }
        } as ImageProxy.PlaneProxy
        return Proxy.newProxyInstance(ImageProxy::class.java.classLoader,
            arrayOf(ImageProxy::class.java)) { _, method, _ ->
            when (method.name) {
                "getFormat" -> ImageFormat.YUV_420_888
                "getPlanes" -> arrayOf(plane)
                "getWidth", "getHeight" -> size
                "close" -> null
                else -> error("Unexpected image method ${method.name}")
            }
        } as ImageProxy
    }
}
