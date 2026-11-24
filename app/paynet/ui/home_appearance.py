# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/home/HomeAppearance.kt

"""Home layout preference and shared app-wide colour preference.

DEVIATION: SharedPreferences "PayNetPrefs" becomes a PrefsStore named
"PayNetPrefs"; the rememberHomeAppearance composable becomes Kivy screen
code re-reading on preference change (wired in the home screen).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

PREFS_NAME = "PayNetPrefs"
KEY_CLASSIC = "home_classic"
KEY_MONOCHROME = "home_monochrome"
KEY_OBSOLETE_BLOOD_RED = "home_blood_red"


@dataclass(frozen=True)
class HomeAppearance:
    classic: bool = False
    # Kotlin: monochrome: Boolean = !classic (derived from the other
    # default). None here means "not passed" and resolves to not classic.
    monochrome: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.monochrome is None:
            object.__setattr__(self, "monochrome", not self.classic)

    def save(self, prefs) -> None:
        prefs.put(KEY_CLASSIC, self.classic)
        prefs.put(KEY_MONOCHROME, self.monochrome)
        # The retired colour option is cleaned up on the next save, never
        # on read — and no other preference (bank selection, setup state)
        # is touched either way.
        prefs.remove(KEY_OBSOLETE_BLOOD_RED)

    @staticmethod
    def read(prefs) -> "HomeAppearance":
        classic = prefs.get(KEY_CLASSIC, False)
        return HomeAppearance(
            classic=classic,
            monochrome=prefs.get(KEY_MONOCHROME, not classic),
        )
