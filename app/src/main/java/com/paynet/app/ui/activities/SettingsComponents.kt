// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.activities

import android.Manifest
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.Contacts
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.Palette
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.paynet.app.R
import com.paynet.app.ui.home.HomeAppearance
import com.paynet.app.ui.theme.PayNetDarkGray
import com.paynet.app.ui.theme.PayNetMediumGray
import com.paynet.app.ui.theme.PayNetStatusError
import com.paynet.app.ui.theme.PayNetTextLightGray
import com.paynet.app.ui.theme.LocalPayNetAccentTheme

@Composable
internal fun SettingsHeading(onBack: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        TextButton(onClick = onBack, contentPadding = PaddingValues(end = 12.dp)) {
            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(6.dp))
            Text(stringResource(R.string.settings_back), fontSize = 16.sp)
        }
        Spacer(Modifier.weight(1f))
        Icon(
            Icons.Outlined.Settings,
            contentDescription = stringResource(R.string.settings_title),
            tint = LocalPayNetAccentTheme.current.primary,
            modifier = Modifier.padding(end = 12.dp).size(26.dp).testTag("settings-icon")
        )
    }
}

@Composable
internal fun AppearanceSettings(
    appearance: HomeAppearance,
    onToggleDesign: () -> Unit,
    onToggleColor: () -> Unit
) {
    val colorName = stringResource(if (appearance.monochrome) R.string.home_monochrome else R.string.home_blue)
    GroupCard {
        SettingsRow(
            Icons.Outlined.Dashboard,
            stringResource(R.string.home_design),
            stringResource(if (appearance.classic) R.string.home_classic else R.string.home_modern),
            style = SettingsRowStyle.CYCLE,
            onClick = onToggleDesign
        )
        GroupDivider()
        SettingsRow(
            Icons.Outlined.Palette,
            stringResource(R.string.home_color),
            colorName,
            style = SettingsRowStyle.CYCLE,
            onClick = onToggleColor
        )
    }
}

@Composable
internal fun PermissionSettings(permissions: Map<String, Boolean>, onRequest: (Array<String>) -> Unit) {
    GroupCard {
        PermissionRow(
            Icons.Outlined.Phone,
            "Phone",
            stringResource(R.string.settings_refined_phone_summary),
            permissions["phone"] == true
        ) { onRequest(arrayOf(Manifest.permission.CALL_PHONE, Manifest.permission.READ_PHONE_STATE)) }
        GroupDivider()
        PermissionRow(
            Icons.Outlined.CameraAlt,
            "Camera",
            stringResource(R.string.settings_refined_camera_summary),
            permissions["camera"] == true
        ) { onRequest(arrayOf(Manifest.permission.CAMERA)) }
        GroupDivider()
        PermissionRow(
            Icons.Outlined.Contacts,
            "Contacts",
            stringResource(R.string.settings_refined_contacts_summary),
            permissions["contacts"] == true
        ) { onRequest(arrayOf(Manifest.permission.READ_CONTACTS)) }
    }
}

@Composable
internal fun SectionHeader(title: String) {
    Text(
        title,
        color = PayNetTextLightGray,
        fontSize = 13.sp,
        fontWeight = FontWeight.Medium,
        modifier = Modifier.padding(start = 16.dp, top = 16.dp, bottom = 2.dp)
    )
}

@Composable
internal fun GroupCard(content: @Composable ColumnScope.() -> Unit) {
    Surface(shape = RoundedCornerShape(22.dp), color = PayNetDarkGray, modifier = Modifier.fillMaxWidth()) {
        Column(content = content)
    }
}

@Composable
internal fun GroupDivider() {
    HorizontalDivider(color = PayNetMediumGray, thickness = 0.5.dp, modifier = Modifier.padding(start = 56.dp))
}

@Composable
internal fun SettingsRow(
    icon: ImageVector,
    title: String,
    value: String,
    style: SettingsRowStyle = SettingsRowStyle.STANDARD,
    onClick: (() -> Unit)? = null
) {
    val destructive = style == SettingsRowStyle.DESTRUCTIVE
    val cycleValue = style == SettingsRowStyle.CYCLE
    val color = if (destructive) PayNetStatusError else LocalPayNetAccentTheme.current.primary
    Row(
        modifier = Modifier.fillMaxWidth()
            .testTag("settings-" + title.lowercase().replace(' ', '-'))
            .then(if (cycleValue) Modifier.semantics { stateDescription = value } else Modifier)
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
            .heightIn(min = 72.dp).padding(horizontal = 16.dp, vertical = 16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(16.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, color = if (destructive) PayNetStatusError else Color.White, fontSize = 16.sp)
            Text(value, color = PayNetTextLightGray, fontSize = 13.sp, lineHeight = 18.sp)
        }
        if (onClick != null) {
            Spacer(Modifier.width(8.dp))
            Icon(
                if (cycleValue) Icons.Default.SwapHoriz else Icons.Default.ChevronRight,
                null,
                tint = PayNetTextLightGray,
                modifier = Modifier.size(18.dp)
            )
        }
    }
}

@Composable
internal fun PermissionRow(
    icon: ImageVector,
    title: String,
    subtitle: String,
    granted: Boolean,
    onRequest: () -> Unit
) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 80.dp).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = LocalPayNetAccentTheme.current.primary, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(16.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, color = Color.White, fontSize = 16.sp)
            Text(subtitle, color = PayNetTextLightGray, fontSize = 13.sp, lineHeight = 18.sp)
        }
        Spacer(Modifier.width(8.dp))
        if (granted) {
            Icon(
                Icons.Default.Check,
                stringResource(R.string.settings_refined_allowed),
                tint = LocalPayNetAccentTheme.current.primary,
                modifier = Modifier.size(22.dp)
            )
        } else {
            TextButton(onClick = onRequest, modifier = Modifier.testTag("settings-grant-" + title.lowercase())) {
                Text(stringResource(R.string.settings_refined_allow), fontSize = 14.sp)
            }
        }
    }
}

@Composable
internal fun SettingsChoice(
    presentation: SettingsChoicePresentation,
    selected: Boolean,
    onClick: () -> Unit
) {
    Row(
        Modifier.fillMaxWidth().testTag("settings-${presentation.id}")
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
            .heightIn(min = 58.dp).padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (presentation.swatch != null) {
            Surface(Modifier.size(20.dp), shape = RoundedCornerShape(6.dp), color = presentation.swatch) {}
            Spacer(Modifier.width(14.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(presentation.title, color = Color.White, fontSize = 16.sp)
            presentation.subtitle?.let { Text(it, color = PayNetTextLightGray, fontSize = 13.sp, lineHeight = 18.sp) }
        }
        Spacer(Modifier.width(12.dp))
        if (selected) {
            Icon(
                Icons.Default.Check,
                stringResource(R.string.settings_refined_selected),
                tint = LocalPayNetAccentTheme.current.primary,
                modifier = Modifier.size(19.dp)
            )
        }
    }
}
