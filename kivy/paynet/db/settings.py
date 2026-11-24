# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/data/{SettingsRepository,TestResults}.kt

"""Settings persistence, replacing SharedPreferences with a small JSON
key-value store (one file per preferences name).

Deviation recorded in MIGRATION.md: StateFlow becomes a plain in-memory
value plus a listener list; the UI re-reads `settings` on demand.
"""

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional


class PrefsStore:
    """A JSON-file-backed SharedPreferences analogue (string/int/bool values)."""

    def __init__(self, directory: str, name: str):
        self._path = os.path.join(directory, f"{name}.json")
        self._lock = threading.RLock()
        self._values = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    def _flush(self):
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self._values, handle)
        os.replace(tmp, self._path)

    def get(self, key: str, default=None):
        with self._lock:
            return self._values.get(key, default)

    def put(self, key: str, value):
        with self._lock:
            self._values[key] = value
            self._flush()

    def remove(self, key: str):
        with self._lock:
            self._values.pop(key, None)
            self._flush()

    def clear(self):
        with self._lock:
            self._values = {}
            self._flush()

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._values

    def all(self) -> dict:
        with self._lock:
            return dict(self._values)


@dataclass
class SavedSettings:
    bankId: str = "hdfc"
    ussdTimeout: int = 30
    overlayEnabled: bool = True
    debugMode: bool = False
    setupCompleted: bool = False
    testConfigCompleted: bool = False


class SettingsRepository:
    PREFS_NAME = "paynet_settings"

    def __init__(self, directory: str):
        self._prefs = PrefsStore(directory, self.PREFS_NAME)
        self._settings = self._load_settings()
        self._listeners = []

    @property
    def settings(self) -> SavedSettings:
        return self._settings

    def add_listener(self, listener: Callable[[SavedSettings], None]):
        self._listeners.append(listener)

    def save_settings(self, settings: SavedSettings):
        self._prefs.put("bank_id", settings.bankId)
        self._prefs.put("ussd_timeout", settings.ussdTimeout)
        self._prefs.put("overlay_enabled", settings.overlayEnabled)
        self._prefs.put("debug_mode", settings.debugMode)
        self._prefs.put("setup_completed", settings.setupCompleted)
        self._prefs.put("test_config_completed", settings.testConfigCompleted)
        self._settings = settings
        for listener in self._listeners:
            listener(settings)

    def _load_settings(self) -> SavedSettings:
        return SavedSettings(
            bankId=self._prefs.get("bank_id", "hdfc") or "hdfc",
            ussdTimeout=self._prefs.get("ussd_timeout", 30),
            overlayEnabled=self._prefs.get("overlay_enabled", True),
            debugMode=self._prefs.get("debug_mode", False),
            setupCompleted=self._prefs.get("setup_completed", False),
            testConfigCompleted=self._prefs.get("test_config_completed", False),
        )

    def clear_all_data(self):
        self._prefs.clear()
        self._settings = SavedSettings()
        for listener in self._listeners:
            listener(self._settings)

    def reset_to_defaults(self):
        self.save_settings(SavedSettings())


@dataclass
class TestResults:
    ussdEnabled: bool = False
    upi123Enabled: bool = False
    timestamp: int = 0
    testVersion: str = "1.0"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = int(time.time() * 1000)


class TestResultsManager:
    PREFS_NAME = "paynet_test_results"
    KEY_TEST_RESULTS = "test_results"

    def __init__(self, directory: str):
        self._prefs = PrefsStore(directory, self.PREFS_NAME)

    def save_test_results(self, results: TestResults):
        self._prefs.put(self.KEY_TEST_RESULTS, json.dumps(asdict(results)))

    def clear_test_results(self):
        self._prefs.remove(self.KEY_TEST_RESULTS)

    def get_test_results(self) -> Optional[TestResults]:
        raw = self._prefs.get(self.KEY_TEST_RESULTS)
        if raw is None:
            return None
        try:
            obj = json.loads(raw)
            return TestResults(
                ussdEnabled=obj.get("ussdEnabled", False),
                upi123Enabled=obj.get("upi123Enabled", False),
                timestamp=obj.get("timestamp", int(time.time() * 1000)),
                testVersion=obj.get("testVersion", "1.0"),
            )
        except (ValueError, TypeError):
            return None

    def has_completed_tests(self) -> bool:
        results = self.get_test_results()
        return bool(results and (results.ussdEnabled or results.upi123Enabled))

    def are_all_tests_completed(self) -> bool:
        results = self.get_test_results()
        return bool(results and results.ussdEnabled and results.upi123Enabled)
