# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/ui/home/HomeAppearanceTest.kt

from paynet.db.settings import PrefsStore, TestResultsManager
from paynet.ui.home_appearance import HomeAppearance


def new_prefs(tmp_path):
    return PrefsStore(str(tmp_path), "PayNetPrefs")


def test_default_is_modern_monochrome(tmp_path):
    prefs = new_prefs(tmp_path)
    assert HomeAppearance.read(prefs) == HomeAppearance()


def test_classic_blue_persists_without_touching_bank(tmp_path):
    prefs = new_prefs(tmp_path)
    prefs.put("selected_bank", "sbi")
    expected = HomeAppearance(classic=True, monochrome=False)
    expected.save(prefs)
    assert HomeAppearance.read(prefs) == expected
    assert prefs.get("selected_bank") == "sbi"


def test_appearance_does_not_grant_payment_setup(tmp_path):
    prefs = new_prefs(tmp_path)
    HomeAppearance(classic=True).save(prefs)
    results = TestResultsManager(str(tmp_path))
    assert results.get_test_results() is None
    assert prefs.get("setup_completed", False) is False


def test_removed_colour_falls_back_to_stored_blue_without_changing_other_preferences(tmp_path):
    prefs = new_prefs(tmp_path)
    prefs.put("home_blood_red", True)
    prefs.put("home_monochrome", False)
    prefs.put("selected_bank", "sbi")
    prefs.put("setup_completed", True)
    assert HomeAppearance.read(prefs) == HomeAppearance(monochrome=False)
    assert prefs.contains("home_blood_red")
    assert prefs.get("selected_bank") == "sbi"
    assert prefs.get("setup_completed", False) is True


def test_next_save_removes_obsolete_colour_without_changing_selection_or_setup(tmp_path):
    prefs = new_prefs(tmp_path)
    prefs.put("home_blood_red", True)
    prefs.put("home_monochrome", False)
    prefs.put("selected_bank", "sbi")
    prefs.put("setup_completed", True)
    read = HomeAppearance.read(prefs)
    HomeAppearance(classic=True, monochrome=read.monochrome).save(prefs)
    assert HomeAppearance.read(prefs) == HomeAppearance(classic=True, monochrome=False)
    assert not prefs.contains("home_blood_red")
    assert prefs.get("selected_bank") == "sbi"
    assert prefs.get("setup_completed", False) is True


def test_legacy_preferences_keep_existing_blue_and_classic_selection(tmp_path):
    prefs = new_prefs(tmp_path)
    prefs.put("home_classic", True)
    prefs.put("home_monochrome", False)
    assert HomeAppearance.read(prefs) == HomeAppearance(classic=True, monochrome=False)


def test_removed_colour_does_not_override_stored_monochrome(tmp_path):
    prefs = new_prefs(tmp_path)
    prefs.put("home_monochrome", True)
    prefs.put("home_blood_red", True)
    assert HomeAppearance.read(prefs) == HomeAppearance()
