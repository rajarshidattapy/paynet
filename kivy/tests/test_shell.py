# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""Smoke test: the app shell constructs without opening a window."""

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")


def test_theme_tokens_match_the_compose_palette():
    from paynet import theme

    assert theme.ACCENT_VIOLET == (0x6A / 255, 0x4F / 255, 0xF0 / 255, 1.0)
    assert theme.status_color("SUCCESS") == theme.STATUS_SUCCESS
    assert theme.status_color("failed") == theme.STATUS_ERROR
    assert theme.status_color("pending") == theme.STATUS_WARNING
    assert theme.status_color("cancelled") == theme.STATUS_NEUTRAL
    assert theme.status_color("anything-else") == theme.STATUS_NEUTRAL


def test_app_module_imports():
    import paynet.app  # noqa: F401
    import main  # noqa: F401
