// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowOutward
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.QrCode
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.dp
import com.flowpay.app.ui.theme.HomeColors
import com.flowpay.app.ui.theme.accentThemeFor

/** An abstract, inert view of each arrangement, without branding, personal data or a device frame. */
@Composable
fun HomeAppearancePreview(appearance: HomeAppearance, modifier: Modifier = Modifier) {
    val palette = accentThemeFor(appearance)
    val control = palette.headerGradientEnd
    val ink = if (appearance.monochrome) HomeColors.ink else Color.White
    Column(
        modifier.clip(RoundedCornerShape(14.dp)).background(Color.Black)
            .clearAndSetSemantics {}.padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        if (appearance.classic) {
            PreviewOverviewCard(appearance, Modifier.fillMaxWidth().weight(1f))
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterHorizontally),
                verticalAlignment = Alignment.CenterVertically
            ) {
                PreviewAction(Icons.Default.QrCode, control, ink, Modifier.size(27.dp), round = true)
                PreviewAction(Icons.Default.Person, control, ink, Modifier.size(25.dp))
            }
        } else {
            Row(Modifier.fillMaxWidth().weight(1f), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                PreviewOverviewCard(appearance, Modifier.weight(1f).fillMaxSize())
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    PreviewAction(Icons.Default.ArrowOutward, control, ink, Modifier.size(29.dp))
                    PreviewAction(Icons.Default.QrCode, control, ink, Modifier.size(29.dp))
                }
            }
            Box(
                Modifier.fillMaxWidth().height(20.dp).background(HomeColors.previewHistory, RoundedCornerShape(6.dp))
            )
        }
    }
}

@Composable
private fun PreviewOverviewCard(appearance: HomeAppearance, modifier: Modifier) {
    val palette = accentThemeFor(appearance)
    Box(
        modifier.clip(RoundedCornerShape(9.dp)).background(
            Brush.linearGradient(listOf(palette.headerGradientStart, palette.headerGradientEnd))
        )
    )
}

@Composable
private fun PreviewAction(icon: ImageVector, fill: Color, ink: Color, modifier: Modifier, round: Boolean = false) {
    Box(
        modifier.background(fill, if (round) CircleShape else RoundedCornerShape(9.dp)),
        contentAlignment = Alignment.Center
    ) {
        Icon(icon, contentDescription = null, Modifier.size(15.dp), tint = ink)
    }
}
