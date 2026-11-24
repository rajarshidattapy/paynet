# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/helpers/OnboardingFlow.kt

"""One-time appearance introduction flow.

Appearance is a one-time introduction, independent of bank/SIM checks.
SharedPreferences "PayNetPrefs" is the PrefsStore of the same name.
Activity navigation (openAppearance/openHome/afterPayments) becomes a pure
routing decision the app shell executes on its ScreenManager.
"""

from paynet.ui.home_appearance import HomeAppearance

APPEARANCE_COMPLETED = "appearance_setup_completed"
WELCOME_COMPLETED = "welcome_completed"

# Routing destinations returned by route_after_payments.
ROUTE_APPEARANCE = "appearance"
ROUTE_HOME = "home"


def needs_appearance(prefs) -> bool:
    return (not prefs.get(APPEARANCE_COMPLETED, False)
            or not prefs.get(WELCOME_COMPLETED, False))


def has_chosen_appearance(prefs) -> bool:
    return bool(prefs.get(APPEARANCE_COMPLETED, False))


def choose_appearance(prefs, classic: bool) -> None:
    HomeAppearance(classic=classic).save(prefs)
    prefs.put(APPEARANCE_COMPLETED, True)
    prefs.put(WELCOME_COMPLETED, False)


def review_appearance(prefs) -> None:
    prefs.put(APPEARANCE_COMPLETED, False)
    prefs.put(WELCOME_COMPLETED, False)


def complete_welcome(prefs) -> None:
    prefs.put(WELCOME_COMPLETED, True)


def route_after_payments(prefs) -> str:
    """OnboardingFlow.afterPayments: the screen that should be current once
    a payment-related flow leaves the stack."""
    return ROUTE_APPEARANCE if needs_appearance(prefs) else ROUTE_HOME
