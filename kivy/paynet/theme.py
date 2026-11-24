# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/theme/Color.kt

"""PayNet design tokens — dark theme.

One value per visual role, exactly mirroring ui/theme/Color.kt so a color
change still happens in exactly one place on both codebases during the
migration. Values are Kivy-style RGBA tuples (0-1 floats).
"""


def _rgba(hex_value: int) -> tuple:
    """Decode a Compose Color(0xAARRGGBB) literal to a Kivy RGBA tuple."""
    a = (hex_value >> 24) & 0xFF
    r = (hex_value >> 16) & 0xFF
    g = (hex_value >> 8) & 0xFF
    b = hex_value & 0xFF
    return (r / 255, g / 255, b / 255, a / 255)


# Surfaces (darkest -> lightest)
BLACK = _rgba(0xFF08070C)
SURFACE_DIM = _rgba(0xFF0E0D14)       # screen background behind cards/lists
DARK_GRAY = _rgba(0xFF17161F)         # card / dialog surface
MEDIUM_GRAY = _rgba(0xFF232130)       # elevated surface: inputs, chips, avatars
LIGHT_GRAY = _rgba(0xFF2E2B3D)        # borders, dividers, inactive track
OUTLINE_GRAY = _rgba(0xFF423E55)      # stronger outline / disabled container
DISABLED_GRAY = _rgba(0xFF4E4A5F)     # disabled content / faint hint

# Text (dimmest -> brightest)
TEXT_GRAY = _rgba(0xFF6B6780)         # placeholder / hint
TEXT_LIGHT_GRAY = _rgba(0xFF8E8AA3)   # captions, labels, timestamps
TEXT_PALE = _rgba(0xFFC9C6D6)         # long-form body on dark dialogs
TEXT_WHITE = _rgba(0xFFFFFFFF)
WELCOME_TEXT = _rgba(0xFFF4F3FA)

# Card colors (light card variant)
CARD_BACKGROUND = _rgba(0xFFEBEAF2)
CARD_TEXT = _rgba(0xFF14121E)
CARD_SUBTEXT = _rgba(0xFF4A4658)

# Accents
ACCENT_VIOLET = _rgba(0xFF6A4FF0)
ACCENT_GREEN = _rgba(0xFF4CAF50)
ACCENT_GREEN_BRIGHT = _rgba(0xFF43E97B)

# Transaction status palette: one color per outcome, identical across the
# history list, detail dialog and result screen.
STATUS_SUCCESS = ACCENT_GREEN
STATUS_ERROR = _rgba(0xFFF44336)
STATUS_WARNING = _rgba(0xFFFF9800)
STATUS_NEUTRAL = _rgba(0xFF9E9E9E)


def status_color(status: str) -> tuple:
    """Single mapping from a transaction-status string to its display color."""
    s = (status or "").upper()
    if s in ("SUCCESS", "SUCCESSFUL", "COMPLETED"):
        return STATUS_SUCCESS
    if s in ("FAILED", "DECLINED"):
        return STATUS_ERROR
    if s in ("PENDING", "NEEDS_REVIEW"):
        return STATUS_WARNING
    return STATUS_NEUTRAL  # UNVERIFIED, CANCELLED, unknown
