// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.utils

import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.SaverScope
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import com.paynet.app.PayContactState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PaymentPhoneInputTest {
    private val localNumber = "9876543210"

    @Test fun pastedIndianFormatsBecomeTheSameCompleteDestination() {
        listOf(
            localNumber,
            "98765 43210",
            "(98765)-43210",
            "+91 98765 43210",
            "+91 (98765) 43210",
            "91-98765-43210",
            "09876543210",
            "0 (98765) 43210",
            " +91\u00a098765\u202f43210 ",
            "+91 98765\u201143210",
            "\n\t+91 98765\n43210\r\n"
        ).forEach { input ->
            assertEquals(input, localNumber, PaymentPhoneInput.completeNumber(input))
            val result = normalize(input)
            assertEquals(input, localNumber, result?.text)
            assertEquals(input, TextRange(localNumber.length), result?.selection)
        }
    }

    @Test fun rejectsForeignNumbersUssdExtensionsAndMixedCharactersWithoutTruncation() {
        listOf(
            "+1 9876543210", "+44 9876543210", "449876543210", "00919876543210",
            "1239876543210", "98765432101", "9876543210 ext 2", "call 9876543210",
            "9876543210#", "*99#", "98765;43210", "98765,43210", "9+876543210",
            "+9198765432100", "98765/43210", "९८७६५४३२१०", "9876543210\n9876543210"
        ).forEach { input ->
            assertNull(input, normalize(input))
            assertNull(input, PaymentPhoneInput.completeNumber(input))
        }
    }

    @Test fun tenDigitNumbersBeginningWith91KeepTheirOwnDigits() {
        assertEquals("9123456780", PaymentPhoneInput.completeNumber("9123456780"))
        assertEquals("9123456780", PaymentPhoneInput.completeNumber("+91 9123456780"))
    }

    @Test fun partialTypingAndDeletingRemainEditableWithoutBecomingPayable() {
        listOf("", "9", "98765", "0", "0987654321", "+", "+9", "+91", "+91 98765", "91987654321")
            .forEach { input ->
                assertTrue(input, normalize(input) != null)
                assertNull(input, PaymentPhoneInput.completeNumber(input))
            }
        var value = TextFieldValue()
        "+919876543210".forEach { digit ->
            value = requireNotNull(normalize(value.text + digit))
        }
        assertEquals(localNumber, value.text)
        while (value.text.isNotEmpty()) {
            value = requireNotNull(normalize(value.text.dropLast(1)))
        }
        assertEquals("", value.text)
    }

    @Test fun completeNumbersStillRequireTheExistingNonzeroTenDigitPattern() {
        assertNull(PaymentPhoneInput.completeNumber("0000000000"))
        assertNull(PaymentPhoneInput.completeNumber("+91 0000000000"))
        assertEquals("1234567890", PaymentPhoneInput.completeNumber("1234567890"))
    }

    @Test fun normalizationMapsMidTextAndReversedSelectionInsteadOfJumpingToTheEnd() {
        val formatted = "+91 (98765) 43210"
        val reversedSelection = TextRange(formatted.indexOf(')'), formatted.indexOf('(') + 1)
        val result = requireNotNull(PaymentPhoneInput.normalize(TextFieldValue(formatted, reversedSelection)))
        assertEquals(localNumber, result.text)
        assertEquals(TextRange(localNumber.indexOf('4'), 0), result.selection)
        val spacedNumber = "98765 43210"
        val afterSpace = TextRange(spacedNumber.indexOf(' ') + 1)
        val middlePaste = requireNotNull(PaymentPhoneInput.normalize(TextFieldValue(spacedNumber, afterSpace)))
        assertEquals(TextRange(localNumber.indexOf('4')), middlePaste.selection)
    }

    @Test fun composingRegionIsMappedAlongWithCursor() {
        val spacedNumber = "98765 43210"
        val composedSuffix = TextRange(spacedNumber.indexOf('4'), spacedNumber.length)
        val result = requireNotNull(
            PaymentPhoneInput.normalize(TextFieldValue(spacedNumber, TextRange(spacedNumber.length), composedSuffix))
        )
        assertEquals(TextRange(localNumber.indexOf('4'), localNumber.length), result.composition)
        assertEquals(TextRange(localNumber.length), result.selection)
    }

    @Test fun savedTextFieldValueRestoresCanonicalNumberAndSelection() {
        val formatted = "+91 98765 43210"
        val cursor = TextRange(formatted.indexOf('6'))
        val value = requireNotNull(PaymentPhoneInput.normalize(TextFieldValue(formatted, cursor)))
        val scope = object : SaverScope {
            override fun canBeSaved(value: Any): Boolean = true
        }
        val saved = with(TextFieldValue.Saver) { scope.save(value) }
        val restored = TextFieldValue.Saver.restore(requireNotNull(saved))
        assertEquals(value.text, restored?.text)
        assertEquals(value.selection, restored?.selection)
    }

    @Test fun editingSelectedRecipientClearsTheNameButCursorMovesAndRejectedPastesDoNot() {
        val state = PayContactState(mutableStateOf(TextFieldValue()), mutableStateOf("1"), mutableStateOf(null))
        state.selectContact(localNumber, "Fixture contact")
        state.updatePhone(TextFieldValue(localNumber, TextRange(localNumber.indexOf('6'))))
        assertEquals("Fixture contact", state.selectedContactName)
        state.updatePhone(TextFieldValue("+44 9876543210"))
        assertEquals(localNumber, state.phoneNumber)
        assertEquals("Fixture contact", state.selectedContactName)
        state.updatePhone(TextFieldValue("+91 98765 43210"))
        assertEquals("Fixture contact", state.selectedContactName)
        state.updatePhone(TextFieldValue("987654321"))
        assertNull(state.selectedContactName)
        assertFalse(state.canTransfer)
        state.updatePhone(TextFieldValue("+91 98765 43211"))
        assertEquals("9876543211", state.phoneNumber)
        assertTrue(state.canTransfer)
    }

    private fun normalize(text: String): TextFieldValue? =
        PaymentPhoneInput.normalize(TextFieldValue(text, TextRange(text.length)))
}
