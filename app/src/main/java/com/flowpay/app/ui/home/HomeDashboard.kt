// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.home

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowOutward
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.QrCode
import androidx.compose.material.icons.outlined.CreditCard
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ripple
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.text
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.flowpay.app.R
import com.flowpay.app.data.PaymentDetails
import com.flowpay.app.data.PaymentStatus
import com.flowpay.app.formatDate
import com.flowpay.app.ui.theme.HomeColors
import com.flowpay.app.ui.theme.accentThemeFor

/** Native rendering of Flowpay Web's two home layouts. All actions are supplied by MainScreen. */
@Composable
@Suppress("LongMethod", "LongParameterList", "CyclomaticComplexMethod")
fun HomeDashboard(
    selectedBankName: String,
    recentPayments: List<PaymentDetails>,
    isLoading: Boolean,
    error: String?,
    onRetry: () -> Unit,
    onTransaction: (PaymentDetails) -> Unit,
    onSettings: () -> Unit,
    onHistory: () -> Unit,
    onQRScanClick: () -> Unit,
    onPayContactClick: () -> Unit,
    isUpi123Ready: Boolean,
    isUssdReady: Boolean,
    isScanning: Boolean
) {
    val appearance by rememberHomeAppearance()
    if (appearance.classic && !appearance.monochrome) {
        LegacyHomeDashboard(
            selectedBankName, recentPayments, isLoading, error, onRetry, onTransaction,
            onQRScanClick, onPayContactClick, isUpi123Ready, isUssdReady, isScanning
        )
        return
    }
    val classic = appearance.classic
    val palette = accentThemeFor(appearance)
    val canvas = if (classic) Color.Black else HomeColors.modernCanvas
    val controls = if (appearance.monochrome) HomeColors.pearl else palette.headerGradientEnd
    val controlInk = if (appearance.monochrome) HomeColors.controlInk else Color.White
    val scanState =
        stringResource(
            when {
                isScanning -> R.string.home_opening
                isUssdReady -> R.string.home_ready
                else -> R.string.home_setup_required
            }
        )
    val payState = stringResource(if (isUpi123Ready) R.string.home_ready else R.string.home_setup_required)
    BoxWithConstraints(Modifier.fillMaxSize().background(canvas).statusBarsPadding().navigationBarsPadding()) {
        val contentWidth = maxWidth.coerceAtMost(440.dp)
        // Direct equivalents of the local page's final Modern CSS rules.
        val tileWidth = (contentWidth * .26f).coerceIn(88.dp, 116.dp)
        val extraHeight = ((maxHeight - 700.dp) * .16f).coerceIn(0.dp, 18.dp)
        val heroHeight = (contentWidth - 44.dp - tileWidth) / .96f + extraHeight
        val topInset = (maxHeight * .057f).coerceIn(36.dp, 58.dp)
        val bottomInset = (maxHeight * .04f).coerceAtLeast(28.dp)
        val historyHeight = (maxHeight * .5f).coerceIn(382.dp, 420.dp)
        Column(
            Modifier.widthIn(max = 440.dp).fillMaxWidth().align(Alignment.TopCenter)
                .verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)
                .padding(top = if (classic) 24.dp else topInset, bottom = if (classic) 24.dp else bottomInset),
            verticalArrangement = Arrangement.spacedBy(32.dp)
        ) {
            if (classic) {
                BrandCard(selectedBankName, appearance, onSettings, Modifier.fillMaxWidth().height(220.dp))
                Column(
                    Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(20.dp)
                ) {
                    ClassicAction(
                        R.string.home_scan_label, R.string.home_scan, Icons.Default.QrCode, controls, controlInk,
                        true, !isScanning, scanState, onQRScanClick
                    )
                    Row(
                        Modifier.width(220.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        HorizontalDivider(Modifier.weight(1f), color = HomeColors.divider)
                        Text(stringResource(R.string.home_or), color = HomeColors.muted, fontSize = 11.sp)
                        HorizontalDivider(Modifier.weight(1f), color = HomeColors.divider)
                    }
                    ClassicAction(
                        R.string.home_pay_contact, R.string.home_send, Icons.Default.Person, controls, controlInk,
                        false, true, payState, onPayContactClick
                    )
                }
            } else {
                Row(Modifier.fillMaxWidth().height(heroHeight), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    BrandCard(selectedBankName, appearance, onSettings, Modifier.weight(1f).fillMaxHeight(), web = true)
                    Column(
                        Modifier.width(tileWidth).fillMaxHeight(),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        HomeAction(
                            stringResource(R.string.home_send), Icons.Default.ArrowOutward, controls, controlInk,
                            Modifier.weight(
                                1f
                            ).fillMaxWidth(),
                            state = payState, corner = 28.dp, iconSize = 24.dp, onClick = onPayContactClick
                        )
                        HomeAction(
                            stringResource(R.string.home_scan), Icons.Default.QrCode, controls, controlInk,
                            Modifier.weight(
                                1f
                            ).fillMaxWidth(),
                            enabled = !isScanning, state = scanState, corner = 28.dp, iconSize = 26.dp,
                            onClick = onQRScanClick
                        )
                    }
                }
            }
            if (classic) {
                RecentPayments(
                    recentPayments, isLoading, error, true, controls, controlInk, scanState, !isScanning,
                    onRetry, onTransaction, onHistory, onQRScanClick
                )
            } else {
                ModernRecentPayments(
                    recentPayments, isLoading, error, historyHeight, controls, controlInk,
                    scanState, !isScanning, onRetry, onTransaction, onHistory, onQRScanClick
                )
            }
        }
    }
}

@Composable
@Suppress("LongMethod", "LongParameterList", "CyclomaticComplexMethod")
private fun BrandCard(
    bank: String,
    appearance: HomeAppearance,
    onSettings: () -> Unit,
    modifier: Modifier,
    web: Boolean = false
) {
    val mono = appearance.monochrome
    val settingsLabel = stringResource(R.string.home_settings)
    val palette = accentThemeFor(appearance)
    val ink = when {
        mono -> if (web) HomeColors.webInk else HomeColors.ink
        web -> Color.White
        else -> HomeColors.blueInk
    }
    val muted = when {
        mono -> HomeColors.cardMuted
        web -> Color.White.copy(alpha = .82f)
        else -> HomeColors.blueMuted
    }
    val gradient = if (mono) {
        if (web) {
            listOf(
                HomeColors.pearlGradientStart,
                HomeColors.pearlGradientEnd
            )
        } else {
            listOf(HomeColors.classicPearlGradientStart, HomeColors.classicPearlGradientEnd)
        }
    } else {
        listOf(palette.headerGradientStart, palette.headerGradientEnd)
    }
    Box(
        modifier.clip(RoundedCornerShape(if (web) 28.dp else 24.dp)).background(Brush.linearGradient(gradient))
            .semantics { contentDescription = "Flowpay card" }
    ) {
        Column(Modifier.fillMaxSize().padding(if (web) 24.dp else if (mono) 22.dp else 20.dp)) {
            Box(Modifier.fillMaxWidth().height(if (web) 32.dp else if (mono) 36.dp else 44.dp)) {
                Wordmark(
                    Modifier.align(Alignment.CenterStart).padding(end = if (web) 48.dp else 42.dp)
                        .fillMaxWidth().height(if (web) 32.dp else 30.dp),
                    if (web) 116.dp else if (mono) 126.dp else 132.dp,
                    white = !mono
                )
                if (!web) {
                    IconButton(
                        onClick = onSettings,
                        modifier = Modifier.align(
                            Alignment.CenterEnd
                        ).size(44.dp).semantics {
                            contentDescription = settingsLabel
                        }
                    ) {
                        Box(
                            Modifier.size(
                                32.dp
                            ).background(
                                (if (mono) Color.Black.copy(alpha = .045f) else Color.White.copy(alpha = .3f)),
                                CircleShape
                            ),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                painterResource(R.drawable.home_settings),
                                stringResource(R.string.home_settings),
                                Modifier.size(18.dp),
                                tint = ink
                            )
                        }
                    }
                }
            }
            Spacer(Modifier.height(if (web) 4.dp else if (mono) 2.dp else 0.dp))
            Text(
                stringResource(R.string.home_tagline),
                color = if (mono && web) HomeColors.webTagline else muted,
                fontSize = if (web) 13.sp else 12.sp,
                lineHeight = 18.sp
            )
            Spacer(Modifier.weight(1f))
            if (mono && !appearance.classic && !web) {
                HorizontalDivider(color = HomeColors.ink.copy(alpha = .10f))
                Spacer(Modifier.height(18.dp))
            }
            Row(
                Modifier.fillMaxWidth().then(
                    if (appearance.classic) {
                        Modifier.clip(RoundedCornerShape(18.dp))
                            .background(Color.Black.copy(alpha = .025f)).padding(14.dp)
                    } else {
                        Modifier
                    }
                ),
                verticalAlignment = if (web) Alignment.Bottom else Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        stringResource(R.string.home_connected_bank),
                        color = muted,
                        fontSize = if (web) 11.sp else 10.sp,
                        lineHeight = 16.sp,
                        letterSpacing = if (appearance.classic) 0.sp else .6.sp
                    )
                    Spacer(Modifier.height(5.dp))
                    Text(
                        bank,
                        color = ink,
                        fontSize = if (web || mono) 18.sp else 19.sp,
                        lineHeight = if (web) 24.sp else 23.sp,
                        letterSpacing = if (web) (-.2).sp else 0.sp,
                        fontWeight = FontWeight.Medium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Box(Modifier.size(if (web) 22.dp else 20.dp), contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.Outlined.CreditCard,
                        null,
                        Modifier.size(if (web) 17.dp else 20.dp),
                        tint = if (mono && web) HomeColors.webWallet else muted
                    )
                }
            }
        }
        if (web) {
            IconButton(
                onClick = onSettings,
                modifier = Modifier.align(Alignment.TopEnd).padding(top = 18.dp, end = 20.dp).size(44.dp).semantics {
                    contentDescription = settingsLabel
                }
            ) {
                Box(
                    Modifier.size(30.dp).background(
                        Color.White.copy(alpha = .3f),
                        CircleShape
                    ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        painterResource(R.drawable.home_settings),
                        stringResource(R.string.home_settings),
                        Modifier.size(15.dp),
                        tint = if (mono) HomeColors.webSettings else ink
                    )
                }
            }
        }
    }
}

@Composable
private fun Wordmark(modifier: Modifier, maxWidth: Dp, white: Boolean = false) {
    // Render the same source PNG and SVG viewBox as Web, without its surrounding transparent padding.
    val bitmap = ImageBitmap.imageResource(
        if (white) R.drawable.home_wordmark_white_source else R.drawable.home_wordmark_source
    )
    val crop = if (white) IntOffset(16, 161) to IntSize(539, 123) else IntOffset(82, 182) to IntSize(382, 90)
    Canvas(
        modifier.semantics {
            contentDescription = "Flowpay"
            role = Role.Image
        }
    ) {
        val width = minOf(size.width, maxWidth.toPx())
        val height = width * crop.second.height / crop.second.width
        drawImage(
            bitmap,
            srcOffset = crop.first,
            srcSize = crop.second,
            dstOffset = IntOffset(0, ((size.height - height) / 2).toInt()),
            dstSize = IntSize(width.toInt(), height.toInt())
        )
    }
}

/** Size the Classic logo to its visible artwork, without a text line box around it. */
@Composable
internal fun ClassicBlueWordmark() {
    val bitmap = ImageBitmap.imageResource(R.drawable.home_wordmark_white_source)
    val measured = rememberTextMeasurer().measure(
        AnnotatedString("Flowpay"),
        style = TextStyle(fontSize = 32.sp, fontWeight = FontWeight.Bold)
    )
    val width = with(LocalDensity.current) { measured.size.width.toDp() }
    Canvas(Modifier.size(width, width * 123f / 539f).semantics { text = AnnotatedString("Flowpay") }) {
        drawImage(
            bitmap,
            srcOffset = IntOffset(16, 161),
            srcSize = IntSize(539, 123),
            dstSize = IntSize(size.width.toInt(), size.height.toInt())
        )
    }
}

@Composable
@Suppress("LongMethod", "LongParameterList", "CyclomaticComplexMethod")
internal fun HomeAction(
    label: String,
    icon: ImageVector,
    background: Color,
    ink: Color,
    modifier: Modifier,
    enabled: Boolean = true,
    state: String,
    round: Boolean = false,
    corner: Dp = 24.dp,
    iconSize: Dp? = null,
    onClick: () -> Unit
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) .97f else 1f, label = "Home action press")
    Box(
        modifier.scale(scale).clip(if (round) CircleShape else RoundedCornerShape(corner)).background(background)
            .semantics {
                contentDescription = label
                stateDescription = state
            }
            .clickable(
                enabled = enabled,
                role = Role.Button,
                interactionSource = interaction,
                indication = ripple(),
                onClick = onClick
            ),
        contentAlignment = Alignment.Center
    ) {
        if (icon == Icons.Default.ArrowOutward) {
            Icon(painterResource(R.drawable.home_arrow), null, Modifier.size(iconSize ?: 27.dp), tint = ink)
        } else {
            Icon(
                icon,
                null,
                Modifier.size(iconSize ?: if (icon == Icons.Default.QrCode) 30.dp else 25.dp),
                tint = ink
            )
        }
    }
}

@Composable
@Suppress("LongMethod", "LongParameterList", "CyclomaticComplexMethod")
private fun ClassicAction(
    label: Int,
    description: Int,
    icon: ImageVector,
    background: Color,
    ink: Color,
    scan: Boolean,
    enabled: Boolean,
    state: String,
    onClick: () -> Unit
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        HomeAction(
            stringResource(
                description
            ),
            icon, background, ink,
            Modifier.size(
                if (scan) 78.dp else 72.dp
            ),
            enabled, state, scan, corner = 24.dp, onClick = onClick
        )
        Text(stringResource(label), color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
@Suppress("LongMethod", "LongParameterList", "CyclomaticComplexMethod")
private fun RecentPayments(
    payments: List<PaymentDetails>,
    loading: Boolean,
    error: String?,
    classic: Boolean,
    control: Color,
    ink: Color,
    scanState: String,
    scanEnabled: Boolean,
    onRetry: () -> Unit,
    onTransaction: (PaymentDetails) -> Unit,
    onHistory: () -> Unit,
    onScan: () -> Unit
) {
    val panel = if (classic) HomeColors.classicHistory else HomeColors.previewHistory
    Box(
        Modifier.fillMaxWidth().then(if (classic) Modifier.height(392.dp) else Modifier)
            .clip(RoundedCornerShape(24.dp)).background(panel).testTag("home-recent-panel")
    ) {
        Column(
            (if (classic) Modifier.fillMaxSize() else Modifier.fillMaxWidth())
                .padding(horizontal = 20.dp, vertical = 20.dp)
        ) {
            Row(Modifier.fillMaxWidth().testTag("home-recent-header"), verticalAlignment = Alignment.CenterVertically) {
                if (classic) {
                    Icon(Icons.Default.History, null, Modifier.size(20.dp), tint = HomeColors.muted)
                    Spacer(Modifier.width(12.dp))
                }
                Column(Modifier.weight(1f)) {
                    Text(
                        stringResource(R.string.home_recent),
                        color = Color.White,
                        fontSize = 17.sp,
                        lineHeight = 24.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    if (classic) Text(stringResource(R.string.home_latest), color = HomeColors.muted, fontSize = 11.sp)
                }
                TextButton(onClick = onHistory, contentPadding = PaddingValues(start = 10.dp, end = 0.dp)) {
                    Text(stringResource(R.string.home_view_all), color = HomeColors.muted, fontSize = 11.sp)
                }
            }
            Spacer(Modifier.height(10.dp))
            Column(
                Modifier.fillMaxWidth().then(if (classic) Modifier.weight(1f) else Modifier)
                    .verticalScroll(rememberScrollState()).testTag("home-recent-list")
            ) {
                when {
                    loading -> Box(Modifier.fillMaxWidth().height(170.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(Modifier.size(24.dp), color = control, strokeWidth = 2.dp)
                    }
                    error != null -> Column(Modifier.fillMaxWidth().padding(vertical = 30.dp)) {
                        Text(
                            stringResource(R.string.error_load_transactions),
                            color = HomeColors.muted,
                            fontSize = 14.sp
                        )
                        TextButton(onClick = onRetry) { Text(stringResource(R.string.home_retry), color = Color.White) }
                    }
                    payments.isEmpty() -> Box(
                        Modifier.fillMaxWidth().height(if (classic) 272.dp else 208.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(stringResource(R.string.home_empty), color = HomeColors.muted, fontSize = 14.sp)
                    }
                    else -> payments.forEachIndexed { index, payment ->
                        Row(
                            Modifier.fillMaxWidth().heightIn(
                                min = 76.dp
                            ).clickable(role = Role.Button) { onTransaction(payment) }
                                .padding(vertical = 14.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            if (!classic) {
                                val name = payment.recipientLabel.orEmpty()
                                val initials = name.split(" ").filter { it.firstOrNull()?.isLetter() == true }
                                    .take(2).mapNotNull { it.firstOrNull()?.uppercaseChar() }.joinToString("")
                                Box(
                                    Modifier.size(34.dp).clip(CircleShape).background(HomeColors.avatar),
                                    contentAlignment = Alignment.Center
                                ) {
                                    if (initials.isEmpty()) {
                                        Icon(
                                            Icons.Default.Person,
                                            null,
                                            Modifier.size(17.dp),
                                            tint = HomeColors.pearl
                                        )
                                    } else {
                                        Text(
                                            initials,
                                            color = HomeColors.pearl,
                                            fontSize = 11.sp,
                                            fontWeight = FontWeight.Medium
                                        )
                                    }
                                }
                                Spacer(Modifier.width(12.dp))
                            }
                            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                                Text(
                                    payment.recipientLabel ?: stringResource(R.string.detail_recipient_unknown),
                                    color = Color.White,
                                    fontSize = 16.sp,
                                    lineHeight = 23.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    formatDate(payment.timestamp),
                                    color = HomeColors.muted,
                                    fontSize = 12.sp,
                                    lineHeight = 18.sp
                                )
                            }
                            val icon = when (payment.userConfirmed) { true -> Icons.Default.Check
                                false -> Icons.Default.Close
                                null -> Icons.Default.ArrowOutward }
                            val status = stringResource(
                                when {
                                    payment.userConfirmed == true -> R.string.home_confirmed
                                    payment.userConfirmed == false -> R.string.home_not_confirmed
                                    payment.status == PaymentStatus.PENDING -> R.string.home_pending
                                    else -> R.string.home_unverified
                                }
                            )
                            Icon(icon, status, Modifier.size(18.dp), tint = HomeColors.muted)
                        }
                        if (index < payments.lastIndex) {
                            HorizontalDivider(
                                Modifier.padding(start = if (classic) 0.dp else 46.dp),
                                color = Color.White.copy(alpha = .075f)
                            )
                        }
                    }
                }
            }
            if (!classic) Spacer(Modifier.height(72.dp))
        }
        if (!classic) {
            HomeAction(
                stringResource(R.string.home_scan_to_pay), Icons.Default.QrCode, control, ink,
                Modifier.align(
                    Alignment.BottomCenter
                ).padding(bottom = 16.dp).size(60.dp),
                scanEnabled, scanState, true, onClick = onScan
            )
        }
    }
}
