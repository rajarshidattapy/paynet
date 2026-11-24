// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.payment

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Locks the exact DTMF dial string for the UPI 123Pay IVR flow.
 * A malformed string here dials a wrong DTMF sequence against a live
 * payment IVR — these tests are the contract.
 */
class Upi123CallStringBuilderTest {

    private fun buildValid(service: String = "08045163666", phone: String = "9876543210", amount: String = "100") =
        Upi123CallStringBuilder.build(service, phone, amount)

    private fun assertInvalid(result: Upi123CallStringBuilder.Result, label: String) {
        assertTrue("expected Invalid for $label but was $result", result is Upi123CallStringBuilder.Result.Invalid)
    }

    @Test
    fun golden_call_string_is_byte_identical() {
        val result = buildValid()
        assertEquals(
            Upi123CallStringBuilder.Result.Valid("tel:08045163666,,1,9876543210,,100,,1"),
            result
        )
    }

    @Test
    fun custom_service_number_is_preserved() {
        val result = buildValid(service = "08045163581")
        assertEquals(
            Upi123CallStringBuilder.Result.Valid("tel:08045163581,,1,9876543210,,100,,1"),
            result
        )
    }

    // The 123Pay IVR accepts amounts strictly below Rs 5,000, so Rs 4,999 is
    // the highest that actually goes through.
    @Test
    fun maximum_allowed_amount_builds() {
        val result = buildValid(amount = "4999")
        assertEquals(
            Upi123CallStringBuilder.Result.Valid("tel:08045163666,,1,9876543210,,4999,,1"),
            result
        )
    }

    @Test
    fun amount_above_123pay_cap_is_rejected() {
        assertInvalid(buildValid(amount = "5000"), "amount over cap")
        assertInvalid(buildValid(amount = "10000"), "amount over cap")
    }

    @Test
    fun zero_and_negative_amounts_are_rejected() {
        assertInvalid(buildValid(amount = "0"), "zero amount")
        assertInvalid(buildValid(amount = "-5"), "negative amount")
    }

    @Test
    fun decimal_amounts_are_rejected___IVR_consumes_whole_rupee_digits() {
        assertInvalid(buildValid(amount = "100.50"), "decimal amount")
    }

    @Test
    fun non_numeric_amount_is_rejected() {
        assertInvalid(buildValid(amount = "abc"), "alpha amount")
        assertInvalid(buildValid(amount = ""), "empty amount")
    }

    @Test
    fun phone_number_must_be_exactly_ten_digits_not_starting_with_zero() {
        assertInvalid(buildValid(phone = "987654321"), "9 digits")
        assertInvalid(buildValid(phone = "98765432101"), "11 digits")
        assertInvalid(buildValid(phone = "0876543210"), "leading zero")
        assertInvalid(buildValid(phone = ""), "empty phone")
    }

    @Test
    fun dtmf_injection_attempts_are_neutralised_or_rejected() {
        // Separators/letters are stripped before validation; anything that
        // still isn't a clean 10-digit number must be rejected.
        assertInvalid(buildValid(phone = "98765#4321"), "hash in phone (9 digits after strip)")
        assertInvalid(buildValid(amount = "1,,9999999999,,1"), "DTMF sequence smuggled in amount")
        assertInvalid(buildValid(amount = "100;rm"), "separator in amount")

        // Formatting characters that strip down to a valid number are fine —
        // and the output must contain only the clean digits.
        val formatted = buildValid(phone = "98765-43210")
        assertEquals(
            Upi123CallStringBuilder.Result.Valid("tel:08045163666,,1,9876543210,,100,,1"),
            formatted
        )
    }

    @Test
    fun invalid_service_number_is_rejected() {
        assertInvalid(buildValid(service = "12345"), "short service number")
        assertInvalid(buildValid(service = ""), "empty service number")
    }
}
