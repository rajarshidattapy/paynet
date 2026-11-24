// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SimCard
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.paynet.app.helpers.SetupHelper
import com.paynet.app.ui.theme.PayNetVioletTheme
import com.paynet.app.ui.theme.PayNetOnboardingBody
import com.paynet.app.ui.theme.PayNetOnboardingOutline
import com.paynet.app.ui.theme.PayNetOnboardingSecondary
import com.paynet.app.ui.theme.PayNetOnboardingSurface
import com.paynet.app.ui.theme.PayNetTheme
import com.paynet.app.ui.theme.LocalPayNetAccentTheme

private val LocalSetupEditing = staticCompositionLocalOf<(String, Boolean) -> Unit> { { _, _ -> } }

class SetupActivity : ComponentActivity() {
    companion object {
        const val EXTRA_REVIEW_SETUP = "com.paynet.app.extra.REVIEW_SETUP"
    }

    private lateinit var setupHelper: SetupHelper

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setupHelper = SetupHelper(
            this,
            object : SetupHelper.UICallback {
                override fun showToast(message: String) {
                    runOnUiThread { Toast.makeText(this@SetupActivity, message, Toast.LENGTH_LONG).show() }
                }

                override fun navigateToTestConfiguration() {
                    startActivity(
                        Intent(this@SetupActivity, TestConfigurationActivity::class.java),
                        setupTransitionOptions(this@SetupActivity)
                    )
                    finish()
                }
            }
        )
        setTheme(R.style.Theme_PayNet)
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent {
            CompositionLocalProvider(LocalPayNetAccentTheme provides PayNetVioletTheme) {
                PayNetTheme {
                    SetupScreen(setupHelper = setupHelper)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SetupScreen(setupHelper: SetupHelper) {
    val context = LocalContext.current
    val preferences = remember(context) {
        context.getSharedPreferences("PayNetPrefs", Context.MODE_PRIVATE)
    }
    var selectedBank by rememberSaveable {
        mutableStateOf(preferences.getString("selected_bank", "").orEmpty())
    }
    var selectedPrimarySim by rememberSaveable {
        mutableStateOf(preferences.getString("selected_primary_sim", "").orEmpty())
    }
    // Preserve older installations' hidden SIM preferences without making them setup requirements.
    val selectedSecondarySim by rememberSaveable {
        mutableStateOf(preferences.getString("selected_secondary_sim", "").orEmpty())
    }
    val isDualSimEnabled by rememberSaveable {
        mutableStateOf(preferences.getBoolean("is_dual_sim_enabled", false))
    }
    var disclaimerAccepted by rememberSaveable {
        mutableStateOf(preferences.getBoolean("disclaimer_accepted", false))
    }
    var hasAdvanced by rememberSaveable { mutableStateOf(false) }
    val reviewSetup = (context as? SetupActivity)?.intent
        ?.getBooleanExtra(SetupActivity.EXTRA_REVIEW_SETUP, false) == true
    var canAdvance by rememberSaveable { mutableStateOf(!reviewSetup) }
    var editingSections by remember { mutableStateOf(emptySet<String>()) }
    val banks = setupHelper.getBanks()
    val simCarriers = setupHelper.getSimCarriers()
    val selection = SetupHelper.SetupData(
        selectedBank,
        selectedPrimarySim,
        isDualSimEnabled,
        selectedSecondarySim,
        disclaimerAccepted
    )
    SetupAutoAdvance(
        state = SetupAdvanceState(
            selection,
            setupSelectionComplete(selection, setupHelper),
            canAdvance,
            hasAdvanced,
            editingSections.isNotEmpty()
        ),
        readCurrent = {
            val current = SetupHelper.SetupData(
                selectedBank,
                selectedPrimarySim,
                isDualSimEnabled,
                selectedSecondarySim,
                disclaimerAccepted
            )
            SetupAdvanceState(
                current,
                setupSelectionComplete(current, setupHelper),
                canAdvance,
                hasAdvanced,
                editingSections.isNotEmpty()
            )
        },
        onAdvance = {
            hasAdvanced = true
            setupHelper.completeSetup(it)
        }
    )

    CompositionLocalProvider(
        LocalSetupEditing provides { section, editing ->
            editingSections = if (editing) editingSections + section else editingSections - section
        }
    ) {
        OnboardingPage(viewportTag = "setup-content", stackTag = "setup-stack") {
            SetupHeading()
            Spacer(Modifier.height(28.dp))
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(22.dp))
                    .background(PayNetOnboardingSurface)
            ) {
                SetupSelectionRow(
                    field = SetupField.Bank,
                    options = banks,
                    selected = selectedBank,
                    onSelected = {
                        selectedBank = it
                        canAdvance = true
                    }
                )
                SetupDivider()
                SetupSelectionRow(
                    field = SetupField.PrimarySim,
                    options = simCarriers,
                    selected = selectedPrimarySim,
                    onSelected = {
                        selectedPrimarySim = it
                        canAdvance = true
                    }
                )
            }
            Spacer(Modifier.height(16.dp))
            DisclaimerSection(disclaimerAccepted) {
                disclaimerAccepted = it
                canAdvance = true
            }
        }
    }
}

@Composable
private fun SetupHeading() {
    val accent = LocalPayNetAccentTheme.current
    Icon(
        imageVector = Icons.Outlined.AccountBalance,
        contentDescription = null,
        tint = accent.primary,
        modifier = Modifier.size(48.dp).testTag("setup-icon")
    )
    Spacer(Modifier.height(16.dp))
    Text(
        text = stringResource(R.string.setup_refined_title),
        modifier = Modifier.testTag("setup-title"),
        color = Color.White,
        fontSize = 31.sp,
        fontWeight = FontWeight.SemiBold,
        textAlign = TextAlign.Center
    )
    Spacer(Modifier.height(8.dp))
    Text(
        text = stringResource(R.string.setup_refined_subtitle),
        color = PayNetOnboardingSecondary,
        fontSize = 15.sp,
        lineHeight = 22.sp,
        textAlign = TextAlign.Center
    )
}

private enum class SetupField(val label: Int, val placeholder: Int, val tag: String) {
    Bank(R.string.setup_refined_bank, R.string.setup_choose_your_bank, "setup-bank"),
    PrimarySim(R.string.setup_primary_sim, R.string.setup_select_primary_sim, "setup-primary-sim")
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SetupSelectionRow(
    field: SetupField,
    options: List<Pair<String, String>>,
    selected: String,
    onSelected: (String) -> Unit
) {
    val accent = LocalPayNetAccentTheme.current
    val onEditing = LocalSetupEditing.current
    var expanded by remember { mutableStateOf(false) }
    DisposableEffect(expanded) {
        onEditing(field.tag, expanded)
        onDispose { onEditing(field.tag, false) }
    }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = {
        expanded = it
        onEditing(field.tag, it)
    }) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .testTag(field.tag)
                .menuAnchor()
                .heightIn(min = 76.dp)
                .padding(horizontal = 18.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                if (field == SetupField.Bank) Icons.Outlined.AccountBalance else Icons.Default.SimCard,
                contentDescription = null,
                tint = accent.primary,
                modifier = Modifier.size(22.dp)
            )
            Spacer(Modifier.width(12.dp))
            SetupSelectionText(field, options, selected, Modifier.weight(1f))
            Spacer(Modifier.width(12.dp))
            CompositionLocalProvider(LocalContentColor provides PayNetOnboardingSecondary) {
                ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded)
            }
        }
        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = {
                expanded = false
                onEditing(field.tag, false)
            },
            modifier = Modifier.background(PayNetOnboardingSurface)
        ) {
            options.forEach { (value, title) ->
                DropdownMenuItem(
                    text = { Text(title, color = Color.White, fontSize = 16.sp) },
                    onClick = {
                        expanded = false
                        onEditing(field.tag, false)
                        onSelected(value)
                    }
                )
            }
        }
    }
}

@Composable
private fun SetupSelectionText(
    field: SetupField,
    options: List<Pair<String, String>>,
    selected: String,
    modifier: Modifier
) {
    Column(modifier) {
        Text(
            stringResource(field.label),
            color = Color.White,
            fontSize = 17.sp,
            fontWeight = FontWeight.Medium
        )
        Spacer(Modifier.height(4.dp))
        Text(
            text = options.firstOrNull { it.first == selected }?.second ?: stringResource(field.placeholder),
            color = PayNetOnboardingSecondary,
            fontSize = 13.sp,
            lineHeight = 18.sp
        )
    }
}

@Composable
private fun SetupDivider() {
    HorizontalDivider(
        modifier = Modifier.padding(start = 52.dp),
        thickness = 0.5.dp,
        color = Color.White.copy(alpha = 0.08f)
    )
}

@Composable
private fun DisclaimerSection(isAccepted: Boolean, onAcceptedChange: (Boolean) -> Unit) {
    val accent = LocalPayNetAccentTheme.current
    val onEditing = LocalSetupEditing.current
    var isExpanded by rememberSaveable { mutableStateOf(false) }
    DisposableEffect(isExpanded) {
        onEditing("setup-disclaimer-reading", isExpanded)
        onDispose { onEditing("setup-disclaimer-reading", false) }
    }
    Column(Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .testTag("setup-disclaimer")
                .toggleable(value = isAccepted, role = Role.Checkbox, onValueChange = onAcceptedChange)
                .heightIn(min = 48.dp)
                .padding(horizontal = 4.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Checkbox(
                checked = isAccepted,
                onCheckedChange = null,
                modifier = Modifier.size(24.dp).clearAndSetSemantics { },
                colors = CheckboxDefaults.colors(
                    checkedColor = accent.primary,
                    checkmarkColor = Color.White,
                    uncheckedColor = PayNetOnboardingOutline
                )
            )
            Spacer(Modifier.width(12.dp))
            Text(
                text = stringResource(R.string.setup_refined_accept_disclaimer),
                color = PayNetOnboardingBody,
                fontSize = 14.sp,
                lineHeight = 20.sp
            )
        }
        TextButton(
            onClick = {
                isExpanded = !isExpanded
                onEditing("setup-disclaimer-reading", isExpanded)
            },
            modifier = Modifier.padding(start = 40.dp).heightIn(min = 48.dp),
            contentPadding = PaddingValues(horizontal = 0.dp),
            colors = ButtonDefaults.textButtonColors(contentColor = accent.primary)
        ) {
            Text(
                text = stringResource(
                    if (isExpanded) R.string.setup_refined_hide_disclaimer else R.string.setup_refined_read_disclaimer
                ),
                fontSize = 14.sp
            )
        }
        if (isExpanded) DisclaimerCopy()
    }
}

@Composable
private fun DisclaimerCopy() {
    Text(
        text = stringResource(R.string.disclaimer_text),
        color = PayNetOnboardingSecondary,
        fontSize = 13.sp,
        lineHeight = 20.sp,
        modifier = Modifier.padding(horizontal = 4.dp, vertical = 8.dp)
    )
}
