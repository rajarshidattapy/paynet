// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.ui.dialogs

import android.content.ContentResolver
import android.database.Cursor
import android.provider.ContactsContract
import android.util.Log
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.flowpay.app.R
import com.flowpay.app.ui.theme.FlowpayDarkGray
import com.flowpay.app.ui.theme.FlowpayLightGray
import com.flowpay.app.ui.theme.FlowpayMediumGray
import com.flowpay.app.ui.theme.FlowpayOnboardingSecondary
import com.flowpay.app.ui.theme.FlowpayOutlineGray
import com.flowpay.app.ui.theme.FlowpayTextLightGray
import com.flowpay.app.ui.theme.LocalFlowpayAccentTheme
import com.flowpay.app.utils.PaymentPhoneInput
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val INDIAN_NUMBER_WITH_COUNTRY_CODE_LENGTH = 12
private const val INDIAN_COUNTRY_CODE = "91"

/**
 * Data class representing a contact with phone number
 */
data class Contact(
    val id: String,
    val name: String,
    val phoneNumber: String
)

/**
 * Contact picker dialog that displays a searchable list of contacts
 * Uses Flowpay's dark theme styling
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ContactPickerDialog(
    onDismiss: () -> Unit,
    onContactSelected: (Contact) -> Unit
) {
    val context = LocalContext.current
    var contacts by remember { mutableStateOf<List<Contact>>(emptyList()) }
    var searchQuery by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(true) }
    var loadFailed by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    // Filtering depends on both inputs, including contacts arriving after someone starts typing.
    val filteredContacts = remember(contacts, searchQuery) { filterContacts(contacts, searchQuery) }

    // Load contacts when dialog opens
    LaunchedEffect(reload) {
        isLoading = true
        loadFailed = false
        val loadedContacts = try {
            loadContacts(context.contentResolver)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (e: SecurityException) {
            Log.e("ContactPicker", "Contacts permission denied or restricted", e)
            loadFailed = true
            emptyList()
        } catch (e: Exception) {
            Log.e("ContactPicker", "Failed to load contacts", e)
            loadFailed = true
            emptyList()
        }
        contacts = loadedContacts
        isLoading = false
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.fillMaxHeight(0.8f).imePadding().testTag("contact-picker"),
        containerColor = FlowpayDarkGray,
        title = {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    stringResource(R.string.polish_contacts_title),
                    color = Color.White,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold
                )
                IconButton(onClick = onDismiss) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = stringResource(R.string.polish_contacts_close),
                        tint = FlowpayTextLightGray
                    )
                }
            }
        },
        text = {
            Column(
                modifier = Modifier.fillMaxSize()
            ) {
                // Search bar
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { searchQuery = it },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 16.dp),
                    placeholder = {
                        Text(stringResource(R.string.contacts_search_hint), color = FlowpayOnboardingSecondary)
                    },
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Default.Search,
                            contentDescription = null,
                            tint = FlowpayTextLightGray
                        )
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White,
                        focusedBorderColor = FlowpayOutlineGray,
                        unfocusedBorderColor = FlowpayLightGray,
                        cursorColor = LocalFlowpayAccentTheme.current.accent,
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent
                    ),
                    singleLine = true
                )

                // Contacts list
                if (isLoading) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = LocalFlowpayAccentTheme.current.accent)
                    }
                } else if (loadFailed) {
                    Column(
                        modifier = Modifier.fillMaxWidth().weight(1f),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            stringResource(R.string.polish_contacts_failed),
                            color = FlowpayOnboardingSecondary,
                            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                        )
                        TextButton(onClick = { reload++ }) { Text(stringResource(R.string.polish_contacts_retry)) }
                    }
                } else if (filteredContacts.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = stringResource(
                                if (searchQuery.isBlank()) {
                                    R.string.polish_contacts_empty
                                } else {
                                    R.string.polish_contacts_no_matches
                                }
                            ),
                            color = FlowpayOnboardingSecondary,
                            fontSize = 16.sp
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f)
                    ) {
                        items(filteredContacts, key = { it.phoneNumber }) { contact ->
                            ContactItem(
                                contact = contact,
                                onClick = {
                                    onContactSelected(contact)
                                    onDismiss()
                                }
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {}
    )
}

internal fun filterContacts(contacts: List<Contact>, query: String): List<Contact> {
    val term = query.trim()
    if (term.isEmpty()) return contacts
    val digits = term.filter(Char::isDigit)
    val hasCountryCode = digits.length == INDIAN_NUMBER_WITH_COUNTRY_CODE_LENGTH &&
        digits.startsWith(INDIAN_COUNTRY_CODE)
    val number = if (hasCountryCode) {
        digits.drop(INDIAN_COUNTRY_CODE.length)
    } else {
        digits
    }
    return contacts.filter { contact ->
        contact.name.contains(term, ignoreCase = true) ||
            (number.isNotEmpty() && term.all { it.isDigit() || it in "+- ()" } && contact.phoneNumber.contains(number))
    }
}

/**
 * Individual contact item in the list
 */
@Composable
fun ContactItem(
    contact: Contact,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .clickable { onClick() },
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(
            containerColor = FlowpayMediumGray
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Contact icon
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .background(
                        color = LocalFlowpayAccentTheme.current.accent.copy(alpha = 0.2f),
                        shape = RoundedCornerShape(20.dp)
                    ),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Person,
                    contentDescription = null,
                    tint = LocalFlowpayAccentTheme.current.accent,
                    modifier = Modifier.size(24.dp)
                )
            }

            Spacer(modifier = Modifier.width(12.dp))

            // Contact details
            Column(
                modifier = Modifier.weight(1f)
            ) {
                Text(
                    text = contact.name,
                    color = Color.White,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = contact.phoneNumber,
                    color = FlowpayTextLightGray,
                    fontSize = 14.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }
}

/**
 * Load contacts from the device's contact database
 * Returns a list of contacts with 10-digit phone numbers
 */
suspend fun loadContacts(contentResolver: ContentResolver): List<Contact> = withContext(Dispatchers.IO) {
    val contactsList = mutableListOf<Contact>()
    val projection = arrayOf(
        ContactsContract.CommonDataKinds.Phone.CONTACT_ID,
        ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
        ContactsContract.CommonDataKinds.Phone.NUMBER
    )

    val cursor: Cursor? = contentResolver.query(
        ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
        projection,
        null,
        null,
        "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} ASC"
    )

    cursor?.use {
        val idColumn = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.CONTACT_ID)
        val nameColumn = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
        val numberColumn = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)
        if (idColumn < 0 || nameColumn < 0 || numberColumn < 0) {
            return@withContext emptyList()
        }

        while (it.moveToNext()) {
            val id = it.getString(idColumn)
            val name = it.getString(nameColumn) ?: "Unknown"
            val number = it.getString(numberColumn) ?: ""

            val cleanedNumber = PaymentPhoneInput.completeNumber(number)
            if (cleanedNumber != null) {
                contactsList.add(Contact(id, name, cleanedNumber))
            }
        }
    }

    // Remove duplicates based on phone number
    contactsList.distinctBy { it.phoneNumber }
}
