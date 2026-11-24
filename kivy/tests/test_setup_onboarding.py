# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/helpers/OnboardingFlowTest.kt,
# app/src/test/java/com/paynet/app/helpers/SetupHelperContextTest.kt and
# app/src/test/java/com/paynet/app/helpers/SetupSingleSimSelectionTest.kt.

"""Behavioral tests for the setup + onboarding logic port."""

import pytest

from paynet import onboarding, setup as setup_logic
from paynet.db.database import Database
from paynet.db.models import Transaction
from paynet.db.settings import PrefsStore, TestResults, TestResultsManager
from paynet.repository import TransactionRepository
from paynet.setup import SetupAdvanceState, SetupData, SetupHelper
from paynet.ui.home_appearance import HomeAppearance


@pytest.fixture
def prefs(tmp_path):
    return PrefsStore(str(tmp_path), "PayNetPrefs")


@pytest.fixture
def results(tmp_path):
    return TestResultsManager(str(tmp_path))


class RecordingCallback:
    def __init__(self):
        self.navigation_count = 0
        self.messages = []

    def navigate(self):
        self.navigation_count += 1

    def toast(self, message):
        self.messages.append(message)


def make_helper(prefs, results, callback=None):
    callback = callback or RecordingCallback()
    return SetupHelper(prefs, results, callback.toast, callback.navigate), callback


SETUP = SetupData("sbi", "airtel", True, "vodafone", True)
CONFIRMED = TestResults(ussdEnabled=True, upi123Enabled=True, timestamp=123)


def seed_readiness(prefs, results):
    results.save_test_results(CONFIRMED)
    prefs.put("test_configuration_completed", True)
    prefs.put("user_reported_ussd_not_working", True)


# --- OnboardingFlowTest --------------------------------------------------------


def test_both_choice_and_welcome_are_required(prefs):
    for chosen in (False, True):
        for welcomed in (False, True):
            prefs.clear()
            prefs.put(onboarding.APPEARANCE_COMPLETED, chosen)
            prefs.put(onboarding.WELCOME_COMPLETED, welcomed)
            assert onboarding.has_chosen_appearance(prefs) is chosen
            assert onboarding.needs_appearance(prefs) is not (chosen and welcomed)


def test_choosing_either_layout_preserves_payment_readiness(prefs, results):
    results.save_test_results(CONFIRMED)
    prefs.put("selected_bank", "sbi")
    prefs.put("test_configuration_completed", True)
    for classic in (False, True):
        HomeAppearance(classic=not classic, monochrome=classic).save(prefs)
        onboarding.complete_welcome(prefs)

        onboarding.choose_appearance(prefs, classic)

        assert HomeAppearance.read(prefs) == HomeAppearance(classic=classic)
        assert onboarding.has_chosen_appearance(prefs)
        assert onboarding.needs_appearance(prefs), "The hello step must still run"
        assert not prefs.get(onboarding.WELCOME_COMPLETED, True)
        assert prefs.get("selected_bank") == "sbi"
        assert prefs.get("test_configuration_completed", False)
        assert results.get_test_results() == CONFIRMED


def test_reviewing_appearance_keeps_the_saved_look(prefs):
    appearance = HomeAppearance(classic=True, monochrome=False)
    appearance.save(prefs)
    onboarding.choose_appearance(prefs, classic=True)
    onboarding.complete_welcome(prefs)

    onboarding.review_appearance(prefs)

    assert HomeAppearance.read(prefs) == appearance
    assert not onboarding.has_chosen_appearance(prefs)
    assert not prefs.get(onboarding.WELCOME_COMPLETED, True)
    assert onboarding.needs_appearance(prefs)


def test_finishing_welcome_cannot_stand_in_for_a_choice(prefs, results):
    onboarding.complete_welcome(prefs)
    assert not onboarding.has_chosen_appearance(prefs)
    assert onboarding.needs_appearance(prefs)
    assert not prefs.get("setup_completed", False)
    assert not prefs.get("test_configuration_completed", False)
    assert results.get_test_results() is None


def test_after_payments_routes_to_the_unfinished_introduction(prefs):
    for chosen, welcomed in ((False, False), (True, False), (False, True), (True, True)):
        prefs.clear()
        prefs.put(onboarding.APPEARANCE_COMPLETED, chosen)
        prefs.put(onboarding.WELCOME_COMPLETED, welcomed)
        expected = (onboarding.ROUTE_HOME if (chosen and welcomed)
                    else onboarding.ROUTE_APPEARANCE)
        assert onboarding.route_after_payments(prefs) == expected


# --- SetupHelperContextTest ------------------------------------------------------


def test_each_bank_or_sim_context_change_invalidates_readiness(prefs, results):
    helper, callback = make_helper(prefs, results)
    changes = [
        SetupData("hdfc", "airtel", True, "vodafone", True),
        SetupData("sbi", "bsnl", True, "vodafone", True),
        SetupData("sbi", "airtel", False, "vodafone", True),
        SetupData("sbi", "airtel", True, "jio", True),
    ]
    for changed in changes:
        helper.save_setup_data(SETUP)
        seed_readiness(prefs, results)

        helper.complete_setup(changed)

        assert results.get_test_results() is None, f"Stale readiness for {changed}"
        assert not prefs.get("test_configuration_completed", True)
        assert not prefs.contains("user_reported_ussd_not_working")
        assert prefs.get("setup_completed", False)
        assert prefs.get("selected_bank") == changed.selected_bank
        assert prefs.get("selected_primary_sim") == changed.selected_primary_sim
        assert prefs.get("is_dual_sim_enabled", False) == changed.is_dual_sim_enabled
        assert prefs.get("selected_secondary_sim") == changed.selected_secondary_sim
    assert callback.navigation_count == len(changes)
    assert callback.messages == []


def test_first_setup_clears_orphaned_legacy_readiness(prefs, results):
    helper, callback = make_helper(prefs, results)
    seed_readiness(prefs, results)

    helper.complete_setup(SETUP)

    assert results.get_test_results() is None
    assert not prefs.get("test_configuration_completed", True)
    assert not prefs.contains("user_reported_ussd_not_working")
    assert helper.is_setup_completed()
    assert callback.navigation_count == 1
    assert callback.messages == []


def test_identical_setup_preserves_readiness_and_completion(prefs, results):
    helper, callback = make_helper(prefs, results)
    helper.save_setup_data(SETUP)
    seed_readiness(prefs, results)

    helper.complete_setup(SETUP)

    assert results.get_test_results() == CONFIRMED
    assert prefs.get("test_configuration_completed", False)
    assert setup_logic.has_user_reported_ussd_not_working(prefs)
    assert callback.navigation_count == 1
    assert callback.messages == []


def test_hidden_legacy_secondary_choices_never_block(prefs, results):
    helper, callback = make_helper(prefs, results)
    prefs.put(onboarding.APPEARANCE_COMPLETED, True)
    prefs.put(onboarding.WELCOME_COMPLETED, True)
    prefs.put("home_classic", True)
    prefs.put("home_monochrome", False)
    for secondary in ("", "retired-carrier", SETUP.selected_primary_sim):
        legacy = SetupData(SETUP.selected_bank, SETUP.selected_primary_sim,
                           True, secondary, True)
        helper.save_setup_data(legacy)
        seed_readiness(prefs, results)

        helper.complete_setup(legacy)

        assert results.get_test_results() == CONFIRMED
        assert prefs.get("test_configuration_completed", False)
        assert prefs.get("is_dual_sim_enabled", False)
        assert prefs.get("selected_secondary_sim") == secondary
        assert prefs.get(onboarding.APPEARANCE_COMPLETED, False)
        assert prefs.get(onboarding.WELCOME_COMPLETED, False)
        assert prefs.get("home_classic", False)
        assert not prefs.get("home_monochrome", True)


def test_save_setup_data_writes_every_field_without_navigating(prefs, results):
    helper, callback = make_helper(prefs, results)

    helper.save_setup_data(SETUP)

    assert prefs.get("selected_bank") == "sbi"
    assert prefs.get("selected_primary_sim") == "airtel"
    assert prefs.get("selected_secondary_sim") == "vodafone"
    assert prefs.get("is_dual_sim_enabled", False)
    assert prefs.get("disclaimer_accepted", False)
    assert prefs.get("setup_completed", False)
    assert callback.navigation_count == 0


def test_changed_setup_leaves_history_and_unrelated_settings_untouched(prefs, results, tmp_path):
    helper, callback = make_helper(prefs, results)
    helper.save_setup_data(SETUP)
    seed_readiness(prefs, results)
    prefs.put("appearance_selection", "classic")
    other_prefs = PrefsStore(str(tmp_path), "paynet_test_results")
    # TestResultsManager owns this same file; keep an unrelated key alongside.
    other_prefs.put("unrelated_metadata", "preserve")
    # History boundary: a real transaction row must survive invalidation.
    database = Database(str(tmp_path / "paynet.db"))
    repository = TransactionRepository(database)
    repository.insert_pending(Transaction(
        transactionId="history-1", amount="125", status="PENDING",
        bankName="State Bank of India", smsExcerpt=""))

    helper.complete_setup(SetupData("hdfc", "airtel", True, "vodafone", True))

    assert results.get_test_results() is None
    assert prefs.get("appearance_selection") == "classic"
    assert other_prefs.get("unrelated_metadata") == "preserve"
    rows = repository.get_all_transactions()
    assert len(rows) == 1
    assert rows[0].transactionId == "history-1"
    assert rows[0].amount == "125"


def test_invalid_setup_keeps_existing_context_and_reports_the_error(prefs, results):
    helper, callback = make_helper(prefs, results)
    helper.save_setup_data(SETUP)
    seed_readiness(prefs, results)

    helper.complete_setup(SetupData("", "airtel", True, "vodafone", True))

    assert results.get_test_results() == CONFIRMED
    assert prefs.get("selected_bank") == "sbi"
    assert prefs.get("test_configuration_completed", False)
    assert setup_logic.has_user_reported_ussd_not_working(prefs)
    assert callback.navigation_count == 0
    assert callback.messages == ["Please select your bank"]


# --- SetupSingleSimSelectionTest -------------------------------------------------


def test_only_visible_bank_calling_sim_and_consent_determine_completion(prefs, results):
    helper, callback = make_helper(prefs, results)
    selection = SetupData("sbi", "airtel", False, "", True)
    for dual in (False, True):
        for secondary in ("", "retired-carrier", "airtel", "vodafone"):
            legacy = SetupData(selection.selected_bank, selection.selected_primary_sim,
                               dual, secondary, True)
            assert setup_logic.setup_selection_complete(legacy, helper)
            assert SetupHelper.validate_form(legacy).is_valid
    assert callback.navigation_count == 0
    assert callback.messages == []


def test_hidden_legacy_choices_cannot_replace_a_valid_selection(prefs, results):
    helper, _ = make_helper(prefs, results)
    legacy = SetupData("sbi", "airtel", True, "retired-carrier", True)
    invalid = [
        SetupData("", "airtel", True, "retired-carrier", True),
        SetupData("retired-bank", "airtel", True, "retired-carrier", True),
        SetupData("sbi", "", True, "retired-carrier", True),
        SetupData("sbi", "retired-carrier", True, "retired-carrier", True),
        SetupData("sbi", "airtel", True, "retired-carrier", False),
    ]
    for incomplete in invalid:
        assert not setup_logic.setup_selection_complete(incomplete, helper)
    assert not SetupHelper.validate_form(
        SetupData("sbi", "airtel", True, "retired-carrier", False)).is_valid


# --- Scan-to-pay gates (SetupHelper companion) -------------------------------------


def test_scan_to_pay_blocked_message_orders_jio_before_user_report(prefs):
    assert setup_logic.get_scan_to_pay_blocked_message(prefs) is None
    setup_logic.set_user_reported_ussd_not_working(prefs, True)
    assert setup_logic.get_scan_to_pay_blocked_message(prefs) == setup_logic.BLOCKED_USER_REPORTED
    prefs.put("selected_primary_sim", "jio")
    assert setup_logic.get_scan_to_pay_blocked_message(prefs) == setup_logic.BLOCKED_JIO
    setup_logic.clear_user_reported_ussd_not_working(prefs)
    assert setup_logic.get_scan_to_pay_blocked_message(prefs) == setup_logic.BLOCKED_JIO
    prefs.put("selected_primary_sim", "airtel")
    assert setup_logic.get_scan_to_pay_blocked_message(prefs) is None


def test_invalidate_payment_configuration_clears_readiness_only(prefs, results):
    seed_readiness(prefs, results)
    prefs.put("selected_bank", "sbi")

    setup_logic.invalidate_payment_configuration(prefs, results)

    assert results.get_test_results() is None
    assert not prefs.get("test_configuration_completed", True)
    assert not prefs.contains("user_reported_ussd_not_working")
    assert prefs.get("selected_bank") == "sbi"


# --- SetupAdvanceState --------------------------------------------------------------


def test_advance_state_requires_completion_and_idle_ui():
    selection = SETUP
    assert SetupAdvanceState(selection, True, True, False, False).can_proceed()
    assert not SetupAdvanceState(selection, False, True, False, False).can_proceed()
    assert not SetupAdvanceState(selection, True, False, False, False).can_proceed()
    assert not SetupAdvanceState(selection, True, True, True, False).can_proceed()
    assert not SetupAdvanceState(selection, True, True, False, True).can_proceed()


def test_catalogues_and_secondary_options_match_the_kotlin_lists():
    assert [b for b, _ in SetupHelper.get_banks()] == [
        "sbi", "hdfc", "icici", "axis", "kotak", "pnb", "bob", "yes", "idbi", "canara"]
    assert [s for s, _ in SetupHelper.get_sim_carriers()] == [
        "jio", "airtel", "vodafone", "bsnl"]
    assert [s for s, _ in SetupHelper.get_secondary_sim_options("jio")] == [
        "airtel", "vodafone", "bsnl"]
    assert [s for s, _ in SetupHelper.get_secondary_sim_options("")] == [
        "jio", "airtel", "vodafone", "bsnl"]
