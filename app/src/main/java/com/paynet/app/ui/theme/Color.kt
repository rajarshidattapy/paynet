// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.theme

import androidx.compose.ui.graphics.Color

// ─────────────────────────────────────────────────────────────────────────
// PayNet design tokens — dark theme.
//
// Every Compose screen draws from these; inline Color(0x…) literals outside
// this package are a CI failure (see the palette-gate step in build.yml).
// The ramp consolidates the near-duplicate greys that had accreted across
// screens (0x1E1E1E vs 0x1A1A1A, 0x8A8A8A vs 0x888888, …) into one value
// per visual role, so "card grey" or "secondary text" can be changed in
// exactly one place.
// ─────────────────────────────────────────────────────────────────────────

// Surfaces (darkest → lightest)
val PayNetBlack = Color(0xFF08070C)

/** Screen background behind cards/lists. */
val PayNetSurfaceDim = Color(0xFF0E0D14)

/** Card / dialog surface. */
val PayNetDarkGray = Color(0xFF17161F)

/** Elevated surface: input fields, chips, avatars. */
val PayNetMediumGray = Color(0xFF232130)

/** Borders, dividers, inactive track. */
val PayNetLightGray = Color(0xFF2E2B3D)

/** Stronger outline / disabled container. */
val PayNetOutlineGray = Color(0xFF423E55)

/** Disabled content / faint hint. */
val PayNetDisabledGray = Color(0xFF4E4A5F)

// Text (dimmest → brightest)
/** Placeholder / hint text. */
val PayNetTextGray = Color(0xFF6B6780)

/** Secondary text: captions, labels, timestamps. */
val PayNetTextLightGray = Color(0xFF8E8AA3)

/** Long-form body text on dark dialogs. */
val PayNetTextPale = Color(0xFFC9C6D6)

val PayNetTextWhite = Color(0xFFFFFFFF)

/** Soft white used by the welcome headline. */
val PayNetWelcomeText = Color(0xFFF4F3FA)

// Card Colors (light card variant)
val PayNetCardBackground = Color(0xFFEBEAF2)
val PayNetCardText = Color(0xFF14121E)
val PayNetCardSubtext = Color(0xFF4A4658)

// Accents
val PayNetAccentViolet = Color(0xFF6A4FF0)
val PayNetAccentGreen = Color(0xFF4CAF50)

/** Bright green used as the light end of success gradients. */
val PayNetAccentGreenBright = Color(0xFF43E97B)

// ─────────────────────────────────────────────────────────────────────────
// Transaction status palette. One color per outcome, used identically in
// the history list, detail dialog and result screen so a status never
// changes meaning between screens.
// ─────────────────────────────────────────────────────────────────────────

/** SUCCESS — bank confirmed. */
val PayNetStatusSuccess = PayNetAccentGreen

/** FAILED / declined, and destructive actions (delete, clear). */
val PayNetStatusError = Color(0xFFF44336)

/** NEEDS_REVIEW / PENDING — user attention required. */
val PayNetStatusWarning = Color(0xFFFF9800)

/** UNVERIFIED / CANCELLED — outcome unknown or nothing happened. Neutral:
 *  deliberately neither success-green nor failure-red. */
val PayNetStatusNeutral = Color(0xFF9E9E9E)

/**
 * The single mapping from a [com.paynet.app.data.TransactionStatus] string
 * to its display color. Replaces the byte-identical getStatusColor()
 * functions that had been copy-pasted into multiple screens.
 */
fun statusColor(status: String): Color = when (status.uppercase()) {
    "SUCCESS", "SUCCESSFUL", "COMPLETED" -> PayNetStatusSuccess
    "FAILED", "DECLINED" -> PayNetStatusError
    "PENDING", "NEEDS_REVIEW" -> PayNetStatusWarning
    else -> PayNetStatusNeutral // UNVERIFIED, CANCELLED, unknown
}
