// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.scanner

import android.app.Application
import android.graphics.ImageFormat
import androidx.camera.core.ImageProxy
import com.flowpay.app.features.qr_scanner.domain.QRCodeAnalyzer
import com.flowpay.app.features.qr_scanner.domain.QRCodeParser
import com.google.zxing.BarcodeFormat
import com.google.zxing.MultiFormatWriter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.lang.reflect.Proxy
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/** Decoder-only valid fixtures can never reach a payment activity or dialer. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
class QRCodeAnalyzerRecoveryTest {
    private companion object {
        const val FRAME_SIZE = 300
        const val WHITE_LUMINANCE = 0xFF
    }

    @Test
    fun invalidThenValidFrameIsAcceptedWithoutRestartingTheAnalyzer() {
        val received = mutableListOf<String>()
        lateinit var analyzer: QRCodeAnalyzer
        analyzer = QRCodeAnalyzer { code ->
            received += code
            if (QRCodeParser.parse(code) is QRCodeParser.ParseResult.Invalid) analyzer.resetProcessing()
        }
        val invalid = frame("https://example.org/not-a-payment")
        val valid = frame("upi://pay?pa=fixture@example&pn=Offline%20test")
        analyzer.analyze(invalid.first)
        analyzer.analyze(valid.first)
        assertEquals(2, received.size)
        assertTrue(QRCodeParser.parse(received.last()) is QRCodeParser.ParseResult.Valid)
        assertTrue(invalid.second.get())
        assertTrue(valid.second.get())
    }

    @Test
    fun rejectedCodeCooldownDoesNotBlockADifferentValidCode() {
        val received = mutableListOf<String>()
        lateinit var analyzer: QRCodeAnalyzer
        analyzer = QRCodeAnalyzer { code ->
            received += code
            analyzer.resetProcessing()
        }
        val invalid = "https://example.org/not-a-payment"
        analyzer.analyze(frame(invalid).first)
        val duplicate = frame(invalid)
        analyzer.analyze(duplicate.first)
        analyzer.analyze(frame("upi://pay?pa=fixture@example").first)
        assertEquals(2, received.size)
        assertTrue(duplicate.second.get())
    }

    @Test
    fun acceptedCodeStaysLockedUntilExplicitRecoveryAndAlwaysClosesFrames() {
        val received = mutableListOf<String>()
        val analyzer = QRCodeAnalyzer { received += it }
        analyzer.analyze(frame("upi://pay?pa=first@example").first)
        val next = frame("upi://pay?pa=second@example")
        analyzer.analyze(next.first)
        assertEquals(listOf("upi://pay?pa=first@example"), received)
        assertTrue(next.second.get())
        analyzer.resetProcessing()
        analyzer.analyze(frame("upi://pay?pa=second@example").first)
        assertEquals(2, received.size)
    }

    private fun frame(text: String): Pair<ImageProxy, AtomicBoolean> {
        val size = FRAME_SIZE
        val matrix = MultiFormatWriter().encode(text, BarcodeFormat.QR_CODE, size, size)
        val bytes = ByteArray(size * size) { index ->
            if (matrix[index % size, index / size]) 0 else WHITE_LUMINANCE.toByte()
        }
        val plane = Proxy.newProxyInstance(
            ImageProxy.PlaneProxy::class.java.classLoader,
            arrayOf(ImageProxy.PlaneProxy::class.java)
        ) { _, method, _ ->
            when (method.name) {
                "getPixelStride" -> 1
                "getRowStride" -> size
                "getBuffer" -> ByteBuffer.wrap(bytes)
                else -> error("Unexpected plane method ${method.name}")
            }
        } as ImageProxy.PlaneProxy
        val closed = AtomicBoolean(false)
        val image = Proxy.newProxyInstance(
            ImageProxy::class.java.classLoader,
            arrayOf(ImageProxy::class.java)
        ) { _, method, _ ->
            when (method.name) {
                "getFormat" -> ImageFormat.YUV_420_888
                "getPlanes" -> arrayOf(plane)
                "getWidth", "getHeight" -> size
                "close" -> {
                    closed.set(true)
                    null
                }
                else -> error("Unexpected image method ${method.name}")
            }
        } as ImageProxy
        return image to closed
    }
}
