// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.utils

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Pins the grouping rule that three separate surfaces used to disagree on.
 *
 * The bug this guards against was not a rounding error — it was
 * `String.format("%,.2f")`, whose `,` flag takes only the *separator* from
 * the locale and always groups in threes. It cannot produce the Indian
 * 3-2-2 pattern for any Locale, so the result screen rendered
 * `100,000.00` while history rendered `1,00,000.00` for the same payment.
 */
class CurrencyFormatTest {

    private companion object {
        const val NEGATIVE_FIVE_HUNDRED = -500.0
    }

    @Test
    fun groups_lakhs_in_the_Indian_3_2_2_pattern__not_in_threes() {
        assertEquals("1,00,000.00", CurrencyFormat.inr("100000"))
        assertEquals("12,34,567.00", CurrencyFormat.inr("1234567"))
    }

    @Test
    fun groups_thousands_the_same_way_western_formatting_would() {
        assertEquals("1,000.00", CurrencyFormat.inr("1000"))
        assertEquals("99,999.00", CurrencyFormat.inr("99999"))
    }

    @Test
    fun always_shows_exactly_two_decimal_places() {
        assertEquals("500.00", CurrencyFormat.inr("500"))
        assertEquals("500.50", CurrencyFormat.inr("500.5"))
        assertEquals("500.75", CurrencyFormat.inr("500.75"))
    }

    @Test
    fun the_String_and_Double_overloads_agree() {
        listOf("1", "500.5", "100000", "1234567.89").forEach { raw ->
            assertEquals(
                "overloads disagreed for $raw",
                CurrencyFormat.inr(raw),
                CurrencyFormat.inr(raw.toDouble())
            )
        }
    }

    @Test
    fun small_amounts_carry_no_separator() {
        assertEquals("1.00", CurrencyFormat.inr("1"))
        assertEquals("0.01", CurrencyFormat.inr("0.01"))
        assertEquals("999.00", CurrencyFormat.inr("999"))
    }

    /** The 3-then-2s rule has to keep holding well past a lakh. */
    @Test
    fun keeps_grouping_in_twos_above_a_lakh() {
        // 10 lakh, 1 crore, 100 crore
        assertEquals("10,00,000.00", CurrencyFormat.inr("1000000"))
        assertEquals("1,00,00,000.00", CurrencyFormat.inr("10000000"))
        assertEquals("1,00,00,00,000.00", CurrencyFormat.inr("1000000000"))
    }

    /**
     * Not reachable from a bank debit today, but the formatter is the one
     * place that decides — it must not mangle the sign if a caller ever
     * hands it a reversal.
     */
    @Test
    fun negative_amounts_keep_their_sign_outside_the_grouping() {
        assertEquals("-1,00,000.00", CurrencyFormat.inr("-100000"))
        assertEquals("-500.00", CurrencyFormat.inr(NEGATIVE_FIVE_HUNDRED))
    }

    /**
     * Rounds, never truncates — and rounds HALF_EVEN, which is what
     * `NumberFormat` did before the grouping was pinned here. Keeping the
     * same rounding mode means no amount that already displayed one way
     * started displaying another. Hence `0.125` -> `0.12`, not `0.13`.
     */
    @Test
    fun rounds_to_two_places__half_even__rather_than_truncating() {
        assertEquals("0.12", CurrencyFormat.inr("0.125"))
        assertEquals("0.14", CurrencyFormat.inr("0.135"))
        assertEquals("1,00,000.12", CurrencyFormat.inr("100000.123"))
        assertEquals("1,00,000.13", CurrencyFormat.inr("100000.126"))
    }

    /**
     * The honest-failure case. A bank template the parser only partly
     * understood must still show the user whatever it did capture — never a
     * blank, an error, or a fabricated `0.00`. This is why the surfaces call
     * the String overload on the raw amount instead of
     * `toDoubleOrNull() ?: 0.0`, which rendered an unparseable amount as
     * `₹0.00` — a number the bank never sent.
     */
    @Test
    fun a_non_numeric_amount_is_passed_through_untouched() {
        assertEquals("", CurrencyFormat.inr(""))
        assertEquals("N/A", CurrencyFormat.inr("N/A"))
        assertEquals("1,000", CurrencyFormat.inr("1,000")) // commas already in; not re-parsed
    }
}
