// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.dialogs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ContactSearchTest {
    private val contacts = listOf(
        Contact("1", "Mira Kapoor", "9876543210"),
        Contact("2", "Arjun Rao", "9123456780")
    )

    @Test fun existingQueryStillFiltersContactsWhenTheyFinishLoading() {
        val queryTypedDuringLoading = "  MIRA  "
        assertTrue(filterContacts(emptyList(), queryTypedDuringLoading).isEmpty())
        assertEquals(listOf(contacts.first()), filterContacts(contacts, queryTypedDuringLoading))
    }

    @Test fun formattedNumberSearchMatchesTheStoredNumber() {
        assertEquals(listOf(contacts.first()), filterContacts(contacts, "98765-43210"))
        assertEquals(listOf(contacts.first()), filterContacts(contacts, "+91 98765 43210"))
        assertEquals(listOf(contacts.last()), filterContacts(contacts, "(912) 345"))
    }

    @Test fun blankQueryRestoresAllContactsAndMixedTextDoesNotMatchOnlyDigits() {
        assertEquals(contacts, filterContacts(contacts, "   "))
        assertTrue(filterContacts(contacts, "Unknown 98765").isEmpty())
    }
}
