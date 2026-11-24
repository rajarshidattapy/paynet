# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/constants/AppConstants.kt

"""Application-wide constants (port of AppConstants)."""

USSD_SESSION_TIMEOUT_MS = 30_000

MIN_AMOUNT_VALUE = 1.0
MAX_AMOUNT_VALUE = 100_000.0

DEFAULT_UPI_SERVICE_NUMBER = "08045163666"

# Per-transaction cap for the UPI 123Pay IVR rail: the flow accepts amounts
# strictly below Rs 5,000, so Rs 4,999 is the highest that goes through.
# Distinct from MAX_AMOUNT_VALUE, the generic input ceiling.
UPI123PAY_MAX_AMOUNT = 4_999.0

# Preference keys (SharedPreferences -> paynet/db/settings.py)
PREFS_NAME = "PayNetPrefs"
KEY_SETUP_COMPLETED = "setup_completed"
KEY_TEST_COMPLETED = "test_configuration_completed"
KEY_SELECTED_BANK = "selected_bank"
KEY_NOTIFICATIONS_ASKED = "notifications_permission_asked"

PHONE_NUMBER_PATTERN = r"^[1-9][0-9]{9}$"
