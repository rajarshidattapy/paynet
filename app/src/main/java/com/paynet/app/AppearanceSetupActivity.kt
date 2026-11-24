// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app

import android.animation.ValueAnimator
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutLinearInEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.DashboardCustomize
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import com.paynet.app.helpers.OnboardingFlow
import com.paynet.app.ui.home.HomeAppearance
import com.paynet.app.ui.home.HomeAppearancePreview
import com.paynet.app.ui.theme.PayNetVioletTheme
import com.paynet.app.ui.theme.PayNetOnboardingSecondary
import com.paynet.app.ui.theme.PayNetOnboardingSurface
import com.paynet.app.ui.theme.PayNetTheme
import com.paynet.app.ui.theme.PayNetWelcomeText
import com.paynet.app.ui.theme.LocalPayNetAccentTheme
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay

class AppearanceSetupActivity : ComponentActivity() {
    private var hasNavigated = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTheme(R.style.Theme_PayNet)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        if (!OnboardingFlow.needsAppearance(this)) {
            OnboardingFlow.openHome(this)
            return
        }
        setContent {
            CompositionLocalProvider(LocalPayNetAccentTheme provides PayNetVioletTheme) {
                PayNetTheme { AppearanceIntroduction() }
            }
        }
    }

    @Composable
    private fun AppearanceIntroduction() {
        // Preferences are the source of truth across recreation, including a
        // process loss after selection but before a saved-state snapshot.
        var showWelcome by remember { mutableStateOf(OnboardingFlow.hasChosenAppearance(this)) }
        BackHandler {
            if (showWelcome) {
                OnboardingFlow.reviewAppearance(this)
                showWelcome = false
            } else {
                startActivity(Intent(this, SetupActivity::class.java).putExtra(SetupActivity.EXTRA_REVIEW_SETUP, true))
                finish()
            }
        }
        if (showWelcome) {
            WelcomeMessage(onComplete = ::completeIntroduction)
        } else {
            AppearanceChoices { classic ->
                OnboardingFlow.chooseAppearance(this, classic)
                showWelcome = true
            }
        }
    }

    private fun completeIntroduction() {
        if (!hasNavigated && !isFinishing && lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
            hasNavigated = true
            OnboardingFlow.completeWelcome(this)
            OnboardingFlow.openHome(this)
        }
    }
}

@Composable
private fun AppearanceChoices(onSelected: (Boolean) -> Unit) {
    OnboardingPage(viewportTag = "appearance-content", stackTag = "appearance-stack") {
        AppearanceHeading()
        Spacer(Modifier.height(28.dp))
        AppearanceChoice(
            label = stringResource(R.string.appearance_modern),
            description = stringResource(R.string.appearance_modern_detail),
            tag = "appearance-modern",
            appearance = HomeAppearance(classic = false),
            onClick = { onSelected(false) }
        )
        Spacer(Modifier.height(12.dp))
        AppearanceChoice(
            label = stringResource(R.string.appearance_classic),
            description = stringResource(R.string.appearance_classic_detail),
            tag = "appearance-classic",
            appearance = HomeAppearance(classic = true),
            onClick = { onSelected(true) }
        )
    }
}

@Composable
private fun AppearanceHeading() {
    Icon(
        Icons.Outlined.DashboardCustomize,
        contentDescription = null,
        tint = PayNetVioletTheme.primary,
        modifier = Modifier.size(48.dp)
    )
    Spacer(Modifier.height(16.dp))
    Text(
        stringResource(R.string.appearance_title),
        modifier = Modifier.testTag("appearance-title"),
        color = Color.White,
        fontSize = 31.sp,
        fontWeight = FontWeight.SemiBold,
        textAlign = TextAlign.Center
    )
    Spacer(Modifier.height(8.dp))
    Text(
        stringResource(R.string.appearance_subtitle),
        color = PayNetOnboardingSecondary,
        fontSize = 15.sp,
        lineHeight = 22.sp,
        textAlign = TextAlign.Center
    )
}

@Composable
private fun AppearanceChoice(
    label: String,
    description: String,
    tag: String,
    appearance: HomeAppearance,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(22.dp))
            .background(PayNetOnboardingSurface)
            .testTag(tag)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(18.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        HomeAppearancePreview(appearance, Modifier.size(width = 108.dp, height = 112.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(label, color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Medium)
            Text(description, color = PayNetOnboardingSecondary, fontSize = 14.sp, lineHeight = 20.sp)
        }
    }
}

private const val WELCOME_ENTER_MS = 650
private const val WELCOME_HOLD_MS = 1600L
private const val WELCOME_EXIT_MS = 450
private const val WELCOME_REDUCED_HOLD_MS = 1600L

/** Animation restarts on resume; it never navigates while the app is in the background. */
@Composable
private fun WelcomeMessage(onComplete: () -> Unit) {
    val lifecycleOwner = LocalLifecycleOwner.current
    val complete by rememberUpdatedState(onComplete)
    val opacity = remember { Animatable(0f) }
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            if (ValueAnimator.areAnimatorsEnabled()) {
                opacity.snapTo(0f)
                opacity.animateTo(1f, tween(WELCOME_ENTER_MS, easing = LinearOutSlowInEasing))
                delay(WELCOME_HOLD_MS)
                opacity.animateTo(0f, tween(WELCOME_EXIT_MS, easing = FastOutLinearInEasing))
            } else {
                opacity.snapTo(1f)
                delay(WELCOME_REDUCED_HOLD_MS)
            }
            complete()
            awaitCancellation()
        }
    }
    Box(
        modifier = Modifier.fillMaxSize().background(Color.Black)
            .statusBarsPadding().navigationBarsPadding()
            .semantics { testTagsAsResourceId = true }
            .testTag("welcome-content")
            .padding(32.dp),
        contentAlignment = Alignment.Center
    ) {
        WelcomeCopy(opacity.value)
    }
}

@Composable
private fun WelcomeCopy(opacity: Float) {
    BasicText(
        text = stringResource(R.string.appearance_welcome),
        modifier = Modifier.fillMaxWidth().testTag("welcome-title").graphicsLayer { alpha = opacity },
        style = TextStyle(
            color = PayNetWelcomeText,
            fontFamily = FontFamily.SansSerif,
            fontSize = 44.sp,
            lineHeight = 52.sp,
            letterSpacing = (-1.2).sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center
        ),
        maxLines = 2,
        softWrap = false,
        autoSize = TextAutoSize.StepBased(minFontSize = 26.sp, maxFontSize = 44.sp, stepSize = 1.sp)
    )
}
