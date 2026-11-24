# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/activities/SettingsModels.kt
# and app/src/main/java/com/paynet/app/ui/activities/SettingsDataReset.kt

"""Settings screen state and behavior.

The Compose viewModelScope coroutine becomes a synchronous call (the reset
itself is fast local storage); cancellation semantics map onto Python's
BaseException vs Exception split. Runtime permission reads are injected as
a provider (device-only on Android; see MIGRATION.md).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Optional

# build.gradle.kts versionName; the Kivy packaging keeps it in sync
# (buildozer.spec, feature 17).
VERSION_NAME = "1.0.0-sms"

NOT_SET = "Not set"

GITHUB_URL = "https://github.com/rajarshidattapy/paynet"


@dataclass(frozen=True)
class Bank:
    id: str
    name: str


# SettingsModels.kt `banks` — note the order differs from SetupHelper's
# catalogue (HDFC first here).
BANKS = [
    Bank("hdfc", "HDFC Bank"),
    Bank("sbi", "State Bank of India"),
    Bank("icici", "ICICI Bank"),
    Bank("axis", "Axis Bank"),
    Bank("kotak", "Kotak Mahindra Bank"),
    Bank("pnb", "Punjab National Bank"),
    Bank("bob", "Bank of Baroda"),
    Bank("yes", "Yes Bank"),
    Bank("idbi", "IDBI Bank"),
    Bank("canara", "Canara Bank"),
]

SIM_NAMES = [("jio", "Jio"), ("airtel", "Airtel"),
             ("vodafone", "Vodafone"), ("bsnl", "BSNL")]


def sim_name(sim_id: str) -> str:
    for sid, name in SIM_NAMES:
        if sid == sim_id:
            return name
    return NOT_SET


class SettingsRowStyle(Enum):
    STANDARD = 1
    DESTRUCTIVE = 2
    CYCLE = 3


@dataclass
class SettingsState:
    selected_bank: Bank = field(default_factory=lambda: BANKS[0])
    ussd_timeout: int = 30
    overlay_enabled: bool = True
    debug_mode: bool = False
    setup_completed: bool = True
    permissions: Dict[str, bool] = field(default_factory=dict)


def reset_settings_data(delete_transactions: Callable[[], None],
                        clear_preferences: Callable[[], None],
                        open_setup: Callable[[], None]) -> bool:
    """A failed history deletion must leave settings intact and must not
    reopen setup. BaseException (the CancellationException analogue:
    KeyboardInterrupt/SystemExit) propagates instead of reading as a
    reset failure."""
    try:
        delete_transactions()
        clear_preferences()
        open_setup()
        return True
    except Exception:
        return False


class SettingsViewModel:
    def __init__(self):
        self.state = SettingsState()
        self.is_resetting = False
        self.reset_failed = False

    def reset_data(self, reset: Callable[[], bool]) -> None:
        if self.is_resetting:
            return
        self.is_resetting = True
        self.reset_failed = False
        try:
            self.reset_failed = not reset()
        finally:
            self.is_resetting = False

    def update_bank(self, bank: Bank) -> None:
        self.state.selected_bank = bank

    def toggle_overlay(self) -> None:
        self.state.overlay_enabled = not self.state.overlay_enabled

    def refresh_permissions(self, permission_provider: Callable[[], Dict[str, bool]]):
        """The Android version reads CALL_PHONE/READ_PHONE_STATE, CAMERA,
        READ_CONTACTS and the overlay grant; on desktop the provider
        reports the honest state (all False)."""
        self.state.permissions = dict(permission_provider())

    def load_from_repository(self, settings_repository, prefs) -> None:
        saved = settings_repository.settings
        setup_bank_id = prefs.get("selected_bank", None)
        # Setup owns the payment bank; the repository is a legacy fallback.
        bank = next((b for b in BANKS if b.id == setup_bank_id), None) \
            or next((b for b in BANKS if b.id == saved.bankId), None) \
            or BANKS[0]
        self.state.selected_bank = bank
        self.state.ussd_timeout = saved.ussdTimeout
        self.state.overlay_enabled = saved.overlayEnabled
        self.state.debug_mode = saved.debugMode
        self.state.setup_completed = saved.setupCompleted
