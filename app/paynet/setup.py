# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/helpers/SetupHelper.kt and
# app/src/main/java/com/paynet/app/SetupAdvanceState.kt

"""Setup business logic: bank/SIM catalogues, validation, preference
persistence and the scan-to-pay USSD gates.

SharedPreferences "PayNetPrefs" is the PrefsStore named "PayNetPrefs";
TestResultsManager is the one from paynet.db.settings. The activity-side
auto-advance (SetupAutoAdvance) is driven by the screen with the same
state object and settle delay.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

PREFS = "PayNetPrefs"
KEY_USER_REPORTED_USSD_NOT_WORKING = "user_reported_ussd_not_working"

SETUP_SETTLE_MS = 600

# strings.xml / setup flow messages (verbatim from the Kotlin sources).
BLOCKED_JIO = "Scan to pay is not available — Jio does not support *99# USSD payments"
BLOCKED_USER_REPORTED = ("Scan to pay is not available — USSD does not work "
                         "for you on this device, so this feature can't be used.")
ERROR_ACCEPT_DISCLAIMER = "Please accept the disclaimer to proceed"
ERROR_SELECT_BANK = "Please select your bank"
ERROR_SELECT_PRIMARY_SIM = "Please select your primary SIM"
ERROR_SELECT_SECONDARY_SIM = "Please select your secondary SIM"


# --- *99# availability gates (SetupHelper companion) -------------------------

def is_primary_sim_ussd_capable(prefs) -> bool:
    """Jio (and similar) — primary SIM carrier does not support *99# here."""
    return (prefs.get("selected_primary_sim", "") or "") != "jio"


def has_user_reported_ussd_not_working(prefs) -> bool:
    """User chose "It doesn't work for me" during the *99# setup test."""
    return bool(prefs.get(KEY_USER_REPORTED_USSD_NOT_WORKING, False))


def set_user_reported_ussd_not_working(prefs, reported: bool) -> None:
    prefs.put(KEY_USER_REPORTED_USSD_NOT_WORKING, reported)


def clear_user_reported_ussd_not_working(prefs) -> None:
    prefs.remove(KEY_USER_REPORTED_USSD_NOT_WORKING)


def invalidate_payment_configuration(prefs, test_results) -> None:
    """Clear method readiness without touching saved setup or history."""
    test_results.clear_test_results()
    prefs.put("test_configuration_completed", False)
    prefs.remove(KEY_USER_REPORTED_USSD_NOT_WORKING)


def is_scan_to_pay_ussd_available(prefs) -> bool:
    """Carrier supports *99# and the user did not opt out in setup."""
    return (is_primary_sim_ussd_capable(prefs)
            and not has_user_reported_ussd_not_working(prefs))


def get_scan_to_pay_blocked_message(prefs) -> Optional[str]:
    """User-facing reason scan-to-pay is blocked, else None. Jio is checked
    before the user-reported flag so the correct message is shown."""
    if is_scan_to_pay_ussd_available(prefs):
        return None
    if not is_primary_sim_ussd_capable(prefs):
        return BLOCKED_JIO
    return BLOCKED_USER_REPORTED


# --- SetupHelper ---------------------------------------------------------------

@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    error_message: str


@dataclass(frozen=True)
class SetupData:
    selected_bank: str
    selected_primary_sim: str
    is_dual_sim_enabled: bool
    selected_secondary_sim: str
    disclaimer_accepted: bool


class SetupHelper:
    """Business logic for the setup screen, separated from the UI."""

    def __init__(self, prefs, test_results,
                 show_toast: Callable[[str], None],
                 navigate_to_test_configuration: Callable[[], None]):
        self._prefs = prefs
        self._test_results = test_results
        self._show_toast = show_toast
        self._navigate = navigate_to_test_configuration

    @staticmethod
    def get_banks() -> List[Tuple[str, str]]:
        return [
            ("sbi", "State Bank of India"),
            ("hdfc", "HDFC Bank"),
            ("icici", "ICICI Bank"),
            ("axis", "Axis Bank"),
            ("kotak", "Kotak Mahindra Bank"),
            ("pnb", "Punjab National Bank"),
            ("bob", "Bank of Baroda"),
            ("yes", "Yes Bank"),
            ("idbi", "IDBI Bank"),
            ("canara", "Canara Bank"),
        ]

    @staticmethod
    def get_sim_carriers() -> List[Tuple[str, str]]:
        return [
            ("jio", "Jio"),
            ("airtel", "Airtel"),
            ("vodafone", "Vodafone"),
            ("bsnl", "BSNL"),
        ]

    @classmethod
    def get_secondary_sim_options(cls, primary_sim: str) -> List[Tuple[str, str]]:
        all_carriers = cls.get_sim_carriers()
        if primary_sim:
            return [c for c in all_carriers if c[0] != primary_sim]
        return all_carriers

    @staticmethod
    def validate_disclaimer(disclaimer_accepted: bool) -> ValidationResult:
        if not disclaimer_accepted:
            return ValidationResult(False, ERROR_ACCEPT_DISCLAIMER)
        return ValidationResult(True, "")

    @staticmethod
    def validate_bank_selection(selected_bank: str) -> ValidationResult:
        if not selected_bank:
            return ValidationResult(False, ERROR_SELECT_BANK)
        return ValidationResult(True, "")

    @staticmethod
    def validate_primary_sim_selection(selected_primary_sim: str) -> ValidationResult:
        if not selected_primary_sim:
            return ValidationResult(False, ERROR_SELECT_PRIMARY_SIM)
        return ValidationResult(True, "")

    @staticmethod
    def validate_secondary_sim_selection(is_dual_sim_enabled: bool,
                                         selected_secondary_sim: str) -> ValidationResult:
        if is_dual_sim_enabled and not selected_secondary_sim:
            return ValidationResult(False, ERROR_SELECT_SECONDARY_SIM)
        return ValidationResult(True, "")

    @classmethod
    def validate_form(cls, setup_data: SetupData) -> ValidationResult:
        disclaimer = cls.validate_disclaimer(setup_data.disclaimer_accepted)
        if not disclaimer.is_valid:
            return disclaimer
        bank = cls.validate_bank_selection(setup_data.selected_bank)
        if not bank.is_valid:
            return bank
        primary = cls.validate_primary_sim_selection(setup_data.selected_primary_sim)
        if not primary.is_valid:
            return primary
        # Setup now asks only for the calling SIM. Preserve legacy
        # secondary-SIM values when saving, but never block the visible
        # form on a hidden field.
        return ValidationResult(True, "")

    def save_setup_data(self, setup_data: SetupData) -> None:
        prefs = self._prefs
        context_changed = (
            (prefs.get("selected_bank", "") or "") != setup_data.selected_bank
            or (prefs.get("selected_primary_sim", "") or "") != setup_data.selected_primary_sim
            or bool(prefs.get("is_dual_sim_enabled", False)) != setup_data.is_dual_sim_enabled
            or (prefs.get("selected_secondary_sim", "") or "") != setup_data.selected_secondary_sim
        )
        if context_changed:
            # Readiness belongs to the bank/SIM context in which it was
            # confirmed.
            invalidate_payment_configuration(prefs, self._test_results)
        prefs.put("setup_completed", True)
        prefs.put("selected_bank", setup_data.selected_bank)
        prefs.put("selected_primary_sim", setup_data.selected_primary_sim)
        prefs.put("is_dual_sim_enabled", setup_data.is_dual_sim_enabled)
        prefs.put("selected_secondary_sim", setup_data.selected_secondary_sim)
        prefs.put("disclaimer_accepted", setup_data.disclaimer_accepted)

    def complete_setup(self, setup_data: SetupData) -> None:
        validation = self.validate_form(setup_data)
        if validation.is_valid:
            self.save_setup_data(setup_data)
            self._navigate()
        else:
            self._show_toast(validation.error_message)

    def is_setup_completed(self) -> bool:
        return bool(self._prefs.get("setup_completed", False))


# --- Auto-advance state (SetupAdvanceState.kt) --------------------------------

@dataclass(frozen=True)
class SetupAdvanceState:
    selection: SetupData
    complete: bool
    allowed: bool
    advanced: bool
    editing: bool

    def can_proceed(self) -> bool:
        if not self.complete or not self.allowed:
            return False
        return not self.advanced and not self.editing


def setup_selection_complete(selection: SetupData, helper: SetupHelper) -> bool:
    valid_bank = any(bank == selection.selected_bank
                     for bank, _ in helper.get_banks())
    valid_primary = any(sim == selection.selected_primary_sim
                        for sim, _ in helper.get_sim_carriers())
    valid_accounts = valid_bank and valid_primary
    return selection.disclaimer_accepted and valid_accounts
