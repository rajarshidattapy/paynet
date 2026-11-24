// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.utils

import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import com.paynet.app.constants.AppConstants

/** Accepts familiar Indian phone formatting without guessing a destination from arbitrary digits. */
internal object PaymentPhoneInput {
    private const val LOCAL_LENGTH = 10
    private const val COUNTRY_CODE = "91"
    private const val TRUNK_PREFIX = "0"
    private val completeNumberPattern = Regex(AppConstants.PHONE_NUMBER_PATTERN)

    /** Null rejects the edit; incomplete accepted input remains editable but cannot be submitted. */
    fun normalize(value: TextFieldValue): TextFieldValue? {
        val compact = value.text.filterNot(::isSeparator)
        val normalized = normalizeCompact(compact) ?: return null
        val prefixLength = compact.length - normalized.length
        fun offset(original: Int): Int =
            (value.text.take(original).count { !isSeparator(it) } - prefixLength).coerceIn(0, normalized.length)

        return value.copy(
            text = normalized,
            selection = TextRange(offset(value.selection.start), offset(value.selection.end)),
            composition = value.composition?.let { TextRange(offset(it.start), offset(it.end)) }
        )
    }

    /** The contact picker must use the same complete-number rules as manual entry. */
    fun completeNumber(text: String): String? =
        normalizeCompact(text.filterNot(::isSeparator))?.takeIf(completeNumberPattern::matches)

    private fun normalizeCompact(text: String): String? {
        return when {
            text.startsWith('+') -> normalizeInternational(text)
            text.any { it !in '0'..'9' } -> null
            text.length <= LOCAL_LENGTH -> text
            text.length == LOCAL_LENGTH + TRUNK_PREFIX.length && text.startsWith(TRUNK_PREFIX) ->
                text.drop(TRUNK_PREFIX.length)
            text.length == LOCAL_LENGTH + COUNTRY_CODE.length && text.startsWith(COUNTRY_CODE) ->
                text.drop(COUNTRY_CODE.length)
            text.length < LOCAL_LENGTH + COUNTRY_CODE.length && text.startsWith(COUNTRY_CODE) -> text
            else -> null
        }
    }

    private fun normalizeInternational(text: String): String? {
        val digits = text.drop(1)
        val hasIndianPrefix = COUNTRY_CODE.startsWith(digits) || digits.startsWith(COUNTRY_CODE)
        if (digits.any { it !in '0'..'9' } || !hasIndianPrefix || digits.length > LOCAL_LENGTH + COUNTRY_CODE.length) {
            return null
        }
        return if (digits.length == LOCAL_LENGTH + COUNTRY_CODE.length) digits.drop(COUNTRY_CODE.length) else text
    }

    private fun isSeparator(character: Char): Boolean =
        character.isWhitespace() || character in "-()\u00a0\u202f\u2010\u2011\u2013"
}
