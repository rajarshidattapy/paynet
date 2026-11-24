# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/ui/activities/
# SettingsBankSourceTest.kt and SettingsDataResetTest.kt.

"""Behavioral tests for the settings screen state port."""

import pytest

from paynet.db.database import Database
from paynet.db.models import Transaction
from paynet.db.settings import (PrefsStore, SettingsRepository, TestResults,
                                TestResultsManager)
from paynet.repository import TransactionRepository
from paynet.settings import (BANKS, SettingsViewModel, reset_settings_data,
                             sim_name)
from paynet.ui.home_appearance import HomeAppearance

FIXTURE_TIMEOUT_SECONDS = 45


@pytest.fixture
def prefs(tmp_path):
    return PrefsStore(str(tmp_path), "PayNetPrefs")


@pytest.fixture
def repository(tmp_path):
    return SettingsRepository(str(tmp_path))


# --- SettingsBankSourceTest -----------------------------------------------------


def test_setup_bank_overrides_default_repository_bank(prefs, repository):
    prefs.put("selected_bank", "sbi")
    view_model = SettingsViewModel()

    view_model.load_from_repository(repository, prefs)

    assert view_model.state.selected_bank.id == "sbi"
    assert repository.settings.bankId == "hdfc"


def test_absent_empty_and_unknown_setup_bank_fall_back_to_repository(prefs, repository):
    saved = repository.settings
    saved.bankId = "axis"
    repository.save_settings(saved)
    view_model = SettingsViewModel()

    for setup_bank in (None, "", "unknown-bank"):
        if setup_bank is None:
            prefs.remove("selected_bank")
        else:
            prefs.put("selected_bank", setup_bank)

        view_model.load_from_repository(repository, prefs)

        assert view_model.state.selected_bank.id == "axis", f"Fallback for {setup_bank}"
        assert prefs.get("selected_bank", None) == setup_bank


def test_invalid_bank_in_both_sources_uses_known_default_without_saving(prefs, repository):
    prefs.put("selected_bank", "unknown-setup-bank")
    saved = repository.settings
    saved.bankId = "unknown-repository-bank"
    repository.save_settings(saved)
    view_model = SettingsViewModel()

    view_model.load_from_repository(repository, prefs)

    assert view_model.state.selected_bank == BANKS[0]
    assert prefs.get("selected_bank") == "unknown-setup-bank"
    assert repository.settings.bankId == "unknown-repository-bank"


def test_loading_settings_preserves_readiness_theme_history_and_options(
        prefs, repository, tmp_path):
    prefs.put("selected_bank", "sbi")
    prefs.put("selected_primary_sim", "airtel")
    prefs.put("setup_completed", True)
    prefs.put("test_configuration_completed", True)
    prefs.put("user_reported_ussd_not_working", True)
    HomeAppearance(classic=True, monochrome=False).save(prefs)
    results = TestResultsManager(str(tmp_path))
    results.save_test_results(TestResults(ussdEnabled=True, upi123Enabled=True,
                                          timestamp=123))
    saved = repository.settings
    saved.bankId = "hdfc"
    saved.ussdTimeout = FIXTURE_TIMEOUT_SECONDS
    saved.overlayEnabled = False
    saved.debugMode = True
    saved.setupCompleted = True
    saved.testConfigCompleted = True
    repository.save_settings(saved)
    database = Database(str(tmp_path / "paynet.db"))
    tx_repository = TransactionRepository(database)
    tx_repository.insert_pending(Transaction(
        transactionId="history-1", amount="125", status="PENDING",
        bankName="State Bank of India", smsExcerpt=""))
    view_model = SettingsViewModel()

    view_model.load_from_repository(repository, prefs)

    assert view_model.state.selected_bank.id == "sbi"
    assert view_model.state.ussd_timeout == FIXTURE_TIMEOUT_SECONDS
    assert not view_model.state.overlay_enabled
    assert view_model.state.debug_mode
    assert view_model.state.setup_completed
    assert repository.settings.bankId == "hdfc"
    assert prefs.get("selected_bank") == "sbi"
    assert prefs.get("test_configuration_completed", False)
    assert prefs.get("user_reported_ussd_not_working", False)
    assert results.get_test_results() is not None
    rows = tx_repository.get_all_transactions()
    assert len(rows) == 1
    assert rows[0].transactionId == "history-1"


# --- SettingsDataResetTest --------------------------------------------------------


def test_failed_history_deletion_preserves_preferences_and_stays():
    cleared = []
    opened = []

    result = reset_settings_data(
        delete_transactions=lambda: (_ for _ in ()).throw(
            RuntimeError("Storage unavailable")),
        clear_preferences=lambda: cleared.append(True),
        open_setup=lambda: opened.append(True))

    assert result is False
    assert cleared == []
    assert opened == []


def test_successful_retry_clears_after_history_then_reopens_setup():
    events = []

    result = reset_settings_data(
        delete_transactions=lambda: events.append("history"),
        clear_preferences=lambda: events.append("settings"),
        open_setup=lambda: events.append("setup"))

    assert result is True
    assert events == ["history", "settings", "setup"]


def test_base_exception_is_not_swallowed_as_a_reset_failure():
    cleared = []

    with pytest.raises(KeyboardInterrupt):
        reset_settings_data(
            delete_transactions=lambda: (_ for _ in ()).throw(
                KeyboardInterrupt("Activity finished")),
            clear_preferences=lambda: cleared.append(True),
            open_setup=lambda: pytest.fail("Must not reopen setup"))
    assert cleared == []


# --- ViewModel basics ---------------------------------------------------------------


def test_reset_data_guards_reentry_and_records_failure():
    view_model = SettingsViewModel()
    view_model.reset_data(lambda: False)
    assert view_model.reset_failed
    assert not view_model.is_resetting

    view_model.reset_data(lambda: True)
    assert not view_model.reset_failed


def test_update_bank_and_toggle_overlay():
    view_model = SettingsViewModel()
    view_model.update_bank(BANKS[3])
    assert view_model.state.selected_bank.id == "axis"
    assert view_model.state.overlay_enabled
    view_model.toggle_overlay()
    assert not view_model.state.overlay_enabled


def test_refresh_permissions_copies_the_provider_snapshot():
    view_model = SettingsViewModel()
    view_model.refresh_permissions(lambda: {"phone": True, "camera": False})
    assert view_model.state.permissions == {"phone": True, "camera": False}
    view_model.state.permissions["phone"] = False
    view_model.refresh_permissions(lambda: {"phone": True})
    assert view_model.state.permissions == {"phone": True}


def test_sim_name_mapping_and_fallback():
    assert sim_name("jio") == "Jio"
    assert sim_name("airtel") == "Airtel"
    assert sim_name("vodafone") == "Vodafone"
    assert sim_name("bsnl") == "BSNL"
    assert sim_name("") == "Not set"
    assert sim_name("unknown") == "Not set"


def test_bank_catalogue_matches_the_settings_order():
    assert [b.id for b in BANKS] == [
        "hdfc", "sbi", "icici", "axis", "kotak", "pnb", "bob", "yes", "idbi", "canara"]
