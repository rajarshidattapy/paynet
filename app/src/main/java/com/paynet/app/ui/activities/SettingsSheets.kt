// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.activities

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.paynet.app.ui.theme.PayNetDarkGray
import com.paynet.app.ui.theme.PayNetMediumGray
import com.paynet.app.ui.theme.PayNetSurfaceDim
import com.paynet.app.ui.theme.PayNetTextWhite
import com.paynet.app.ui.theme.LocalPayNetAccentTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun SettingsSheet(
    title: String,
    onDismiss: () -> Unit,
    tag: String,
    dismissEnabled: Boolean = true,
    content: @Composable ColumnScope.() -> Unit
) {
    val maximumHeight = LocalConfiguration.current.screenHeightDp.dp * 0.80f
    val canDismiss by rememberUpdatedState(dismissEnabled)
    ModalBottomSheet(
        onDismissRequest = { if (canDismiss) onDismiss() },
        sheetState = rememberModalBottomSheetState(
            skipPartiallyExpanded = true,
            confirmValueChange = { canDismiss || it != SheetValue.Hidden }
        ),
        modifier = Modifier.semantics { testTagsAsResourceId = true }.testTag(tag),
        containerColor = PayNetSurfaceDim,
        contentColor = PayNetTextWhite,
        tonalElevation = 0.dp,
        shape = RoundedCornerShape(topStart = 26.dp, topEnd = 26.dp)
    ) {
        Column(Modifier.fillMaxWidth().heightIn(max = maximumHeight).padding(horizontal = 24.dp)) {
            Text(
                title,
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.semantics { heading() }
            )
            Spacer(Modifier.height(20.dp))
            Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                content()
                Spacer(Modifier.height(28.dp))
            }
        }
    }
}

@Composable
internal fun SettingsChoiceGroup(content: @Composable ColumnScope.() -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = PayNetDarkGray, modifier = Modifier.fillMaxWidth()) {
        Column(content = content)
    }
}

@Composable
internal fun SettingsChoiceDivider() {
    HorizontalDivider(color = PayNetMediumGray, thickness = 0.5.dp, modifier = Modifier.padding(horizontal = 16.dp))
}

@Composable
internal fun SettingsSheetLink(text: String, tag: String, onClick: () -> Unit) {
    val accent = LocalPayNetAccentTheme.current
    Row(
        Modifier.fillMaxWidth().testTag(tag).clickable(role = Role.Button, onClick = onClick)
            .heightIn(min = 56.dp).padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(text, color = accent.primary, fontSize = 15.sp, modifier = Modifier.weight(1f))
        Icon(Icons.Default.OpenInNew, contentDescription = null, tint = accent.primary, modifier = Modifier.size(18.dp))
    }
}
