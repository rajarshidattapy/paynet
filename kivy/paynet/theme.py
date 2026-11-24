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


# ---- Home dashboard palette (ui/theme/HomeColors.kt) ----------------------

HOME_INK = _rgba(0xFF202023)
HOME_MUTED = _rgba(0xFF929299)
HOME_PEARL = _rgba(0xFFF0F0EE)
HOME_MODERN_CANVAS = _rgba(0xFF0B0B0C)
HOME_CONTROL_INK = _rgba(0xFF242429)
HOME_DIVIDER = _rgba(0xFF19191C)
HOME_WEB_INK = _rgba(0xFF171719)
HOME_VIOLET_INK = _rgba(0xFF221647)
HOME_CARD_MUTED = _rgba(0xFF727279)
HOME_VIOLET_MUTED = _rgba(0xFF37255F)
HOME_PEARL_GRADIENT_START = _rgba(0xFFFBFBFA)
HOME_PEARL_GRADIENT_END = _rgba(0xFFE8E8E5)
HOME_CLASSIC_PEARL_GRADIENT_START = _rgba(0xFFF7F7F4)
HOME_CLASSIC_PEARL_GRADIENT_END = _rgba(0xFFF1F1EE)
HOME_WEB_TAGLINE = _rgba(0xFF616162)
HOME_WEB_WALLET = _rgba(0xFF9AA5B3)
HOME_WEB_SETTINGS = _rgba(0xFF45454B)
HOME_MODERN_HISTORY = _rgba(0xFF0A0A0A)
HOME_HISTORY_TEXT = _rgba(0xFFF2F2F4)
HOME_HISTORY_ACTION = _rgba(0xFFB8B8C1)
HOME_HISTORY_MUTED = _rgba(0xFFA1A1AA)
HOME_CLASSIC_HISTORY = _rgba(0xFF101010)
HOME_PREVIEW_HISTORY = _rgba(0xFF121213)
HOME_AVATAR = _rgba(0xFF252527)


class AccentTheme:
    """ui/theme/AccentTheme.kt PayNetAccentTheme."""

    def __init__(self, primary, primary_dark, header_gradient_start,
                 header_gradient_end, accent, accent_light,
                 on_accent=(1, 1, 1, 1), settings_control=None,
                 on_settings_control=(1, 1, 1, 1), on_primary_dark=None):
        self.primary = primary
        self.primary_dark = primary_dark
        self.header_gradient_start = header_gradient_start
        self.header_gradient_end = header_gradient_end
        self.accent = accent
        self.accent_light = accent_light
        self.on_accent = on_accent
        self.settings_control = settings_control if settings_control is not None else primary_dark
        self.on_settings_control = on_settings_control
        self.on_primary_dark = on_primary_dark if on_primary_dark is not None else on_accent


VIOLET_ACCENT_THEME = AccentTheme(
    primary=ACCENT_VIOLET,
    primary_dark=_rgba(0xFF4A32C0),
    header_gradient_start=_rgba(0xFF8B7CFF),
    header_gradient_end=ACCENT_VIOLET,
    accent=ACCENT_VIOLET,
    accent_light=_rgba(0xFF9D8FFF),
)

MONOCHROME_ACCENT_THEME = AccentTheme(
    primary=HOME_PEARL,
    primary_dark=_rgba(0xFFD8D8D5),
    header_gradient_start=HOME_PEARL_GRADIENT_START,
    header_gradient_end=HOME_PEARL_GRADIENT_END,
    accent=HOME_PEARL,
    accent_light=(1, 1, 1, 1),
    on_accent=HOME_INK,
    settings_control=(0, 0, 0, 1),
)


def accent_theme_for(monochrome: bool) -> AccentTheme:
    return MONOCHROME_ACCENT_THEME if monochrome else VIOLET_ACCENT_THEME
