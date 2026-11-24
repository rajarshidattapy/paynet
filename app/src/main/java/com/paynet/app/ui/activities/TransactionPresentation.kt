// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.ui.activities

import com.paynet.app.data.Transaction
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

internal fun Transaction.matchesSearch(query: String): Boolean {
    val text = query.trim()
    return text.isEmpty() || listOf(
        recipientName, recipientLabel, phoneNumber, upiId, bankRef, bankName, amount
    ).any { it?.contains(text, ignoreCase = true) == true }
}

/** Include the year for older records, keeping dates from different years distinct. */
internal fun historicalDateLabel(timestamp: Long, now: Long): String {
    val current = Calendar.getInstance().apply { timeInMillis = now }
    val date = Calendar.getInstance().apply { timeInMillis = timestamp }
    val pattern = if (date.get(Calendar.YEAR) == current.get(Calendar.YEAR)) "dd MMM" else "dd MMM yyyy"
    return SimpleDateFormat(pattern, Locale("en", "IN")).format(Date(timestamp))
}
