// SPDX-License-Identifier: Apache-2.0
package com.paynet.app

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.paynet.app.data.*
import com.paynet.app.helpers.TransactionDetector
import com.paynet.app.receivers.SmsIngestionPipeline
import com.paynet.app.repository.TransactionRepository
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

/** Synthetic bank messages only. No dial intents, money transfers or inbox queries. */
@RunWith(AndroidJUnit4::class)
class SmsIntegrationDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val app get() = PayNetApplication.from(context)!!
    private val repo get() = TransactionRepository.getInstance(context)
    private val detector get() = TransactionDetector.getInstance(context)
    private var serial = 0
    private fun message(amount: String = "500.00", ref: String = "512233440091") =
        "Rs.$amount sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref $ref"
    @Before fun prepare() = runBlocking {
        check(context.packageName == "com.paynet.app.sms")
        app.paymentSessionManager.onUserCancelled()
        delay(200)
        detector.stopOperation()
        repo.deleteAllTransactions()
    }
    @After fun cleanup() = runBlocking {
        app.paymentSessionManager.onUserCancelled()
        delay(200)
        detector.stopOperation()
        repo.deleteAllTransactions()
    }
    private suspend fun begin(): String {
        val id = app.paymentSessionManager.begin("9876543210", "500")
        withTimeout(4000) { while (repo.getTransactionById(id) == null) delay(20) }
        detector.startOperation("UPI_123", "500", "9876543210", id)
        return id
    }
    private suspend fun awaitStatus(id: String, status: String) {
        withTimeout(4000) { while(repo.getTransactionById(id)?.status != status) delay(20) }
    }
    @Test fun bankDebitConfirmsExistingRowAndDeduplicates() = runBlocking {
        val id = begin()
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK", message())
        awaitStatus(id, "SUCCESS")
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK", message())
        assertEquals(1, repo.getTransactionCount())
        val row = repo.getTransactionById(id)!!
        assertNotNull(row.verifiedAt)
        assertTrue(row.bankRef!!.matches(Regex("512233440091_[0-9]+")))
        assertFalse(row.smsExcerpt.contains("**1234"))
        assertEquals(PaymentStatus.COMPLETED, row.toPaymentDetails().status)
    }
    @Test fun bankFailureIsNotRecordedAsSuccess() = runBlocking {
        val id = begin()
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK",
            "Payment of Rs.500.00 to KIRANA STORE failed. UPI ref 512233440093 -HDFC Bank")
        awaitStatus(id, "FAILED")
        assertEquals(PaymentStatus.FAILED, repo.getTransactionById(id)!!.toPaymentDetails().status)
    }
    @Test fun messagesOutsidePaymentWindowAreIgnored() = runBlocking {
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK", message())
        assertEquals(0, repo.getTransactionCount())
    }
    @Test fun unrelatedCreditDoesNotConfirmOrConsumeWindow() = runBlocking {
        val id = begin()
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK",
            "Rs.500.00 credited to your HDFC Bank A/c **1234 via UPI ref 512233440092")
        assertEquals("PENDING", repo.getTransactionById(id)!!.status)
        assertTrue(detector.shouldProcessSMS())
    }
    @Test fun wrongAmountDoesNotConfirmPayment() = runBlocking {
        val id = begin()
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK", message("750.00"))
        assertEquals("PENDING", repo.getTransactionById(id)!!.status)
        assertTrue(detector.shouldProcessSMS())
    }
    @Test fun cancelledPaymentDoesNotAcceptLaterMessage() = runBlocking {
        val id = begin()
        app.paymentSessionManager.onUserCancelled()
        awaitStatus(id, "CANCELLED")
        withTimeout(4000) { while(detector.shouldProcessSMS()) delay(20) }
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK", message())
        assertEquals("CANCELLED", repo.getTransactionById(id)!!.status)
        assertEquals(1, repo.getTransactionCount())
    }
    @Test fun orphanedPendingRowReceivesConfirmationWithoutDuplicate() = runBlocking {
        val id = "synthetic-orphan"
        repo.insertPending(Transaction(id,"500","PENDING","","",deadlineAt=System.currentTimeMillis()+600000))
        detector.startOperation("UPI_123", "500", sessionTxnId=id)
        SmsIngestionPipeline.ingest(context, detector, "VK-HDFCBK", message())
        awaitStatus(id,"SUCCESS")
        assertEquals(1,repo.getTransactionCount())
    }
    @Test fun newQrWindowDoesNotInheritPreviousAmountOrRecipient() {
        detector.startOperation("UPI_123","500","9876543210","previous")
        detector.startOperation("QR_SCAN",sessionTxnId="qr")
        assertNull(detector.getPhoneNumber())
        val parsed=detector.processSMS("VK-HDFCBK",message("750.00"))
        assertNotNull(parsed)
        assertEquals("750.00",parsed!!.amount)
    }
}
