# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Behavioral tests for the settings/prefs port (SettingsRepository,
# TestResultsManager, PrefsStore).

from paynet.db.settings import (
    PrefsStore,
    SavedSettings,
    SettingsRepository,
    TestResults,
    TestResultsManager,
)


def test_defaults_match_the_kotlin_saved_settings(tmp_path):
    repository = SettingsRepository(str(tmp_path))
    settings = repository.settings
    assert settings.bankId == "hdfc"
    assert settings.ussdTimeout == 30
    assert settings.overlayEnabled is True
    assert settings.debugMode is False
    assert settings.setupCompleted is False
    assert settings.testConfigCompleted is False


def test_save_persists_across_instances(tmp_path):
    repository = SettingsRepository(str(tmp_path))
    repository.save_settings(SavedSettings(bankId="axis", ussdTimeout=45, debugMode=True))
    reloaded = SettingsRepository(str(tmp_path))
    assert reloaded.settings.bankId == "axis"
    assert reloaded.settings.ussdTimeout == 45
    assert reloaded.settings.debugMode is True


def test_listeners_fire_on_save_and_clear(tmp_path):
    repository = SettingsRepository(str(tmp_path))
    seen = []
    repository.add_listener(seen.append)
    repository.save_settings(SavedSettings(bankId="sbi"))
    repository.clear_all_data()
    assert seen[0].bankId == "sbi"
    assert seen[1] == SavedSettings()


def test_reset_to_defaults(tmp_path):
    repository = SettingsRepository(str(tmp_path))
    repository.save_settings(SavedSettings(bankId="axis"))
    repository.reset_to_defaults()
    assert repository.settings == SavedSettings()


def test_prefs_store_round_trip_and_clear(tmp_path):
    prefs = PrefsStore(str(tmp_path), "PayNetPrefs")
    prefs.put("selected_bank", "sbi")
    prefs.put("setup_completed", True)
    assert PrefsStore(str(tmp_path), "PayNetPrefs").get("selected_bank") == "sbi"
    assert prefs.contains("setup_completed")
    prefs.clear()
    assert not prefs.contains("selected_bank")
    assert prefs.all() == {}


def test_test_results_manager(tmp_path):
    manager = TestResultsManager(str(tmp_path))
    assert manager.get_test_results() is None
    assert not manager.has_completed_tests()
    assert not manager.are_all_tests_completed()

    manager.save_test_results(TestResults(ussdEnabled=True, timestamp=123))
    assert manager.has_completed_tests()
    assert not manager.are_all_tests_completed()

    manager.save_test_results(TestResults(ussdEnabled=True, upi123Enabled=True, timestamp=123))
    results = manager.get_test_results()
    assert results.ussdEnabled and results.upi123Enabled
    assert results.timestamp == 123
    assert results.testVersion == "1.0"
    assert manager.are_all_tests_completed()

    manager.clear_test_results()
    assert manager.get_test_results() is None


def test_corrupt_test_results_json_reads_as_absent(tmp_path):
    prefs = PrefsStore(str(tmp_path), TestResultsManager.PREFS_NAME)
    prefs.put(TestResultsManager.KEY_TEST_RESULTS, "{not json")
    manager = TestResultsManager(str(tmp_path))
    assert manager.get_test_results() is None
