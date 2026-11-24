# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Feature 17: platform bindings. On Android these wrap the real OS services
# through pyjnius; everywhere else every binding stays None and the desktop
# stubs keep their injected-callable behavior (MIGRATION.md deviations).

"""Selects the platform binding set for the current runtime."""

from kivy.utils import platform as _kivy_platform


def create_bindings():
    """Returns the paynet.platform.android binding set on Android, else None.

    Composition root usage: every binding is Optional; None keeps the
    feature's documented device-only deviation."""
    if _kivy_platform != "android":
        return None
    from . import android
    return android.Bindings()
