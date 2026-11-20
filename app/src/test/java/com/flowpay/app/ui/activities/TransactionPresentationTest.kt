// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.activities

import com.flowpay.app.data.Transaction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Calendar

class TransactionPresentationTest {
    private companion object {
        const val CURRENT_YEAR = 2026
        const val PREVIOUS_YEAR = 2025
        const val EARLIER_YEAR = 2024
        const val TODAY = 3
        const val TRANSACTION_DAY = 15
        const val NOON = 12
    }

    private val row = Transaction(
        "presentation-test", "", "USER_CONFIRMED", "Example bank", "",
        recipientName = " SAMPLE MERCHANT ", phoneNumber = "9876543210",
        upiId = "merchant@bank", bankRef = "REF-12345"
    )

    @Test fun recipientFallbackIsConsistentAndDoesNotChangeRawData() {
        assertEquals("Sample Merchant", row.recipientLabel)
        assertEquals(row.recipientLabel, row.toPaymentDetails().recipientLabel)
        assertEquals(" SAMPLE MERCHANT ", row.recipientName)
        assertEquals("9876543210", row.copy(recipientName = " ").recipientLabel)
        val qr = row.copy(recipientName = null, phoneNumber = " ")
        assertEquals("merchant@bank", qr.recipientLabel)
        assertEquals(qr.recipientLabel, qr.toPaymentDetails().recipientLabel)
        assertNull(qr.copy(upiId = null).recipientLabel)
    }

    @Test fun unrecordedAmountRemainsDifferentFromRecordedZero() {
        assertFalse(row.toPaymentDetails().amountRecorded)
        assertFalse(row.copy(amount = " ").toPaymentDetails().amountRecorded)
        assertTrue(row.copy(amount = "0").toPaymentDetails().amountRecorded)
        assertTrue(row.copy(amount = "1.25").toPaymentDetails().amountRecorded)
    }

    @Test fun searchFindsIdentifiersAndTrimsPastedWhitespace() {
        assertTrue(row.matchesSearch("  MERCHANT@BANK  "))
        assertTrue(row.matchesSearch("ref-123"))
        assertTrue(row.matchesSearch("987654"))
        assertTrue(row.matchesSearch("sample"))
        assertTrue(row.matchesSearch(" "))
        assertFalse(row.matchesSearch("someone-else@bank"))
    }

    @Test fun olderDatesKeepTheirYear() {
        val now = date(CURRENT_YEAR, Calendar.NOVEMBER, TODAY)
        assertEquals("15 Oct", historicalDateLabel(date(CURRENT_YEAR, Calendar.OCTOBER, TRANSACTION_DAY), now))
        assertEquals("15 Oct 2025", historicalDateLabel(date(PREVIOUS_YEAR, Calendar.OCTOBER, TRANSACTION_DAY), now))
        assertNotEquals(
            historicalDateLabel(date(EARLIER_YEAR, Calendar.OCTOBER, TRANSACTION_DAY), now),
            historicalDateLabel(date(PREVIOUS_YEAR, Calendar.OCTOBER, TRANSACTION_DAY), now)
        )
    }

    private fun date(year: Int, month: Int, day: Int): Long = Calendar.getInstance().apply {
        clear()
        set(year, month, day, NOON, 0)
    }.timeInMillis
}
