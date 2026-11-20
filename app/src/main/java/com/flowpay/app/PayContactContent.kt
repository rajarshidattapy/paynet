// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.Manifest
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PermContactCalendar
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.flowpay.app.constants.AppConstants
import com.flowpay.app.managers.PermissionManager
import com.flowpay.app.payment.Upi123CallStringBuilder
import com.flowpay.app.payment.messageFor
import com.flowpay.app.ui.dialogs.ContactPickerDialog
import com.flowpay.app.ui.theme.FlowpayDarkGray
import com.flowpay.app.ui.theme.FlowpayLightGray
import com.flowpay.app.ui.theme.FlowpayOnboardingSecondary
import com.flowpay.app.ui.theme.FlowpayOutlineGray
import com.flowpay.app.ui.theme.FlowpayStatusError
import com.flowpay.app.ui.theme.FlowpayTextGray
import com.flowpay.app.ui.theme.FlowpayTextLightGray
import com.flowpay.app.ui.theme.LocalFlowpayAccentTheme
import com.flowpay.app.utils.PaymentPhoneInput
import com.flowpay.app.utils.findComponentActivity

private const val MAX_AMOUNT_INPUT_DIGITS = 6

internal class PayContactState(
    phone: MutableState<TextFieldValue>,
    amount: MutableState<String>,
    recipient: MutableState<String?>
) {
    var phoneInput by phone
    val phoneNumber: String get() = phoneInput.text
    var amount by amount
    var selectedContactName by recipient
    var showContactPicker by mutableStateOf(false)
    var showContactPermissionDialog by mutableStateOf(false)
    val isOverCap: Boolean
        get() = (amount.toLongOrNull() ?: 0L) > AppConstants.UPI123PAY_MAX_AMOUNT.toLong()
    val canTransfer: Boolean
        get() = Regex(AppConstants.PHONE_NUMBER_PATTERN).matches(phoneNumber) &&
            (amount.toLongOrNull()?.let { it in 1..AppConstants.UPI123PAY_MAX_AMOUNT.toLong() } == true)

    fun updatePhone(proposed: TextFieldValue) {
        PaymentPhoneInput.normalize(proposed)?.let { accepted ->
            if (accepted.text != phoneNumber) selectedContactName = null
            phoneInput = accepted
        }
    }

    fun selectContact(number: String, name: String) {
        phoneInput = TextFieldValue(number, TextRange(number.length))
        selectedContactName = name
        showContactPicker = false
    }
}

@Composable
private fun rememberPayContactState(): PayContactState {
    val phone = rememberSaveable(stateSaver = TextFieldValue.Saver) { mutableStateOf(TextFieldValue()) }
    val amount = rememberSaveable { mutableStateOf("") }
    val recipient = rememberSaveable { mutableStateOf<String?>(null) }
    return remember { PayContactState(phone, amount, recipient) }
}

@Composable
internal fun PayContactContent(onDismiss: () -> Unit, onConfirm: (String, String, String?) -> Unit) {
    val state = rememberPayContactState()
    val chooseContact = ContactPickerFlow(state)
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = FlowpayDarkGray,
        title = {
            Text(
                stringResource(R.string.pay_contact_title),
                color = Color.White,
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold
            )
        },
        text = { PayContactFields(state, chooseContact) },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(state.phoneNumber, state.amount, state.selectedContactName) },
                enabled = state.canTransfer
            ) {
                Text(
                    stringResource(R.string.action_transfer),
                    color = if (state.canTransfer) LocalFlowpayAccentTheme.current.accent else FlowpayTextGray
                )
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.action_cancel), color = FlowpayTextLightGray)
            }
        }
    )
}

@Composable
private fun PayContactFields(state: PayContactState, chooseContact: () -> Unit) {
    val context = LocalContext.current
    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        state.selectedContactName?.let { ContactRecipient(it) }
        ContactPhoneField(state, chooseContact)
        ContactAmountField(state)
        if (state.isOverCap) {
            Text(
                text = Upi123CallStringBuilder.Reason.AMOUNT_ABOVE_CAP.messageFor(context),
                color = FlowpayStatusError,
                fontSize = 12.sp,
                lineHeight = 16.sp
            )
        }
    }
}

@Composable
private fun ContactRecipient(name: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = LocalFlowpayAccentTheme.current.accent.copy(alpha = 0.15f)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Default.Person,
                null,
                tint = LocalFlowpayAccentTheme.current.accent,
                modifier = Modifier.size(16.dp)
            )
            Spacer(Modifier.width(8.dp))
            Text(
                stringResource(R.string.pay_contact_recipient, name),
                color = LocalFlowpayAccentTheme.current.accent,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium
            )
        }
    }
}

@Composable
private fun ContactPhoneField(state: PayContactState, chooseContact: () -> Unit) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.Top
    ) {
        OutlinedTextField(
            value = state.phoneInput,
            onValueChange = state::updatePhone,
            label = { Text(stringResource(R.string.home_field_mobile_label), color = FlowpayTextLightGray) },
            placeholder = { Text(stringResource(R.string.home_field_mobile_hint), color = FlowpayOnboardingSecondary) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            singleLine = true,
            modifier = Modifier.weight(1f),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = Color.White,
                unfocusedTextColor = Color.White,
                focusedBorderColor = FlowpayOutlineGray,
                unfocusedBorderColor = FlowpayLightGray,
                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent
            )
        )
        IconButton(
            onClick = chooseContact,
            modifier = Modifier.padding(top = 8.dp).size(48.dp)
                .background(LocalFlowpayAccentTheme.current.accent.copy(alpha = 0.2f), RoundedCornerShape(8.dp))
        ) {
            Icon(
                Icons.Default.PermContactCalendar,
                contentDescription = stringResource(R.string.choose_contact_action),
                tint = LocalFlowpayAccentTheme.current.accent
            )
        }
    }
}

@Composable
private fun ContactAmountField(state: PayContactState) {
    OutlinedTextField(
        value = state.amount,
        onValueChange = { if (it.all(Char::isDigit) && it.length <= MAX_AMOUNT_INPUT_DIGITS) state.amount = it },
        label = { Text(stringResource(R.string.home_field_amount_label), color = FlowpayTextLightGray) },
        placeholder = { Text(stringResource(R.string.home_field_amount_hint), color = FlowpayOnboardingSecondary) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        singleLine = true,
        isError = state.isOverCap,
        modifier = Modifier.fillMaxWidth(),
        colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = Color.White,
            unfocusedTextColor = Color.White,
            focusedBorderColor = if (state.isOverCap) FlowpayStatusError else FlowpayOutlineGray,
            unfocusedBorderColor = if (state.isOverCap) FlowpayStatusError else FlowpayLightGray,
            focusedContainerColor = Color.Transparent,
            unfocusedContainerColor = Color.Transparent
        )
    )
}

@Composable
private fun ContactPickerFlow(state: PayContactState): () -> Unit {
    val context = LocalContext.current
    val activity = remember(context) { context.findComponentActivity() }
    val permissions = remember(activity) { activity?.let { PermissionManager(it) } }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) state.showContactPicker = true
    }
    if (state.showContactPicker) {
        ContactPickerDialog(
            onDismiss = { state.showContactPicker = false },
            onContactSelected = { state.selectContact(it.phoneNumber, it.name) }
        )
    }
    if (state.showContactPermissionDialog) {
        PermissionExplanationDialog(
            title = stringResource(R.string.contacts_permission_title),
            message = stringResource(R.string.contacts_permission_body),
            confirmButtonText = stringResource(R.string.permission_continue),
            onConfirm = {
                state.showContactPermissionDialog = false
                launcher.launch(Manifest.permission.READ_CONTACTS)
            },
            onDismiss = { state.showContactPermissionDialog = false }
        )
    }
    return {
        when {
            permissions == null -> Toast.makeText(
                context.applicationContext,
                "Unable to open contacts from this screen.",
                Toast.LENGTH_SHORT
            ).show()
            permissions.hasContactPermission() -> state.showContactPicker = true
            else -> state.showContactPermissionDialog = true
        }
    }
}
