# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/constants/PermissionConstants.kt
# and app/src/main/java/com/paynet/app/managers/PermissionManager.kt

"""Centralized permission constants and the runtime-permission gate.

DEVIATION (device-only, recorded in MIGRATION.md): ContextCompat /
Settings.canDrawOverlays are Android runtime reads. The port takes an
injected `checker` for individual permissions and an injected
`can_draw_overlays` callable; both default to "not granted" on the desktop
build so gates fail safe (toward requesting) rather than pretending access.
The overlay-settings intent is platform-only and always None here; the real
launcher wiring is feature 17.
"""

from typing import Callable, List, Optional

CALL_PHONE = "android.permission.CALL_PHONE"
READ_PHONE_STATE = "android.permission.READ_PHONE_STATE"
MODIFY_AUDIO_SETTINGS = "android.permission.MODIFY_AUDIO_SETTINGS"
CAMERA = "android.permission.CAMERA"
READ_CONTACTS = "android.permission.READ_CONTACTS"
VIBRATE = "android.permission.VIBRATE"
ANSWER_PHONE_CALLS = "android.permission.ANSWER_PHONE_CALLS"
RECEIVE_SMS = "android.permission.RECEIVE_SMS"


class PermissionConstants:
    """Port of PermissionConstants (object -> class with class attributes)."""

    # Standard Android permissions required by the app
    REQUIRED_PERMISSIONS = (
        CALL_PHONE,
        READ_PHONE_STATE,
        MODIFY_AUDIO_SETTINGS,
        CAMERA,
        READ_CONTACTS,
        VIBRATE,
    )

    # Critical permissions that are absolutely necessary for core functionality
    CRITICAL_PERMISSIONS = (
        CALL_PHONE,
        READ_PHONE_STATE,
    )

    # Phone-call permission group requested together before dialing.
    PHONE_PERMISSIONS = (
        CALL_PHONE,
        READ_PHONE_STATE,
        ANSWER_PHONE_CALLS,
        RECEIVE_SMS,
    )


class PermissionManager:
    """Port of managers/PermissionManager.kt.

    `checker` answers ContextCompat.checkSelfPermission(...) == GRANTED for
    one permission; `can_draw_overlays` answers Settings.canDrawOverlays.
    Kotlin's canDrawOverlays returns true below API M; the desktop build has
    no overlay window, so the default is False (fail safe, device-only)."""

    def __init__(
        self,
        checker: Optional[Callable[[str], bool]] = None,
        can_draw_overlays: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._checker = checker or (lambda _permission: False)
        self._can_draw_overlays = can_draw_overlays or (lambda: False)

    def check_all_permissions(self) -> bool:
        return all(self._checker(p) for p in PermissionConstants.REQUIRED_PERMISSIONS)

    def has_phone_permissions(self) -> bool:
        return self.is_permission_granted(CALL_PHONE) and self.is_permission_granted(
            READ_PHONE_STATE)

    def has_camera_permission(self) -> bool:
        return self.is_permission_granted(CAMERA)

    def check_overlay_permission(self) -> bool:
        return self._can_draw_overlays()

    def has_overlay_permission(self) -> bool:
        return self.check_overlay_permission()

    def overlay_permission_settings_intent(self) -> None:
        """DEVIATION: the ACTION_MANAGE_OVERLAY_PERMISSION intent is
        platform-only; always None on the desktop build (feature 17)."""
        return None

    def is_permission_granted(self, permission: str) -> bool:
        return bool(self._checker(permission))

    def get_missing_permissions(self) -> List[str]:
        return [p for p in PermissionConstants.REQUIRED_PERMISSIONS
                if not self._checker(p)]

    def can_draw_overlays(self) -> bool:
        return self._can_draw_overlays()

    def has_contact_permission(self) -> bool:
        return self.is_permission_granted(READ_CONTACTS)
