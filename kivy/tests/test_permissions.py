# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# New coverage for the PermissionConstants/PermissionManager port (Kotlin
# ships no unit tests for these files).

from paynet.permissions import (ANSWER_PHONE_CALLS, CALL_PHONE, CAMERA,
                                MODIFY_AUDIO_SETTINGS, READ_CONTACTS,
                                READ_PHONE_STATE, RECEIVE_SMS, VIBRATE,
                                PermissionConstants, PermissionManager)


def test_permission_groups_match_the_kotlin_constants():
    assert PermissionConstants.REQUIRED_PERMISSIONS == (
        CALL_PHONE, READ_PHONE_STATE, MODIFY_AUDIO_SETTINGS,
        CAMERA, READ_CONTACTS, VIBRATE)
    assert PermissionConstants.CRITICAL_PERMISSIONS == (
        CALL_PHONE, READ_PHONE_STATE)
    assert PermissionConstants.PHONE_PERMISSIONS == (
        CALL_PHONE, READ_PHONE_STATE, ANSWER_PHONE_CALLS, RECEIVE_SMS)


def test_defaults_fail_safe_to_not_granted():
    manager = PermissionManager()
    assert manager.check_all_permissions() is False
    assert manager.has_phone_permissions() is False
    assert manager.has_camera_permission() is False
    assert manager.check_overlay_permission() is False
    assert manager.has_overlay_permission() is False
    assert manager.has_contact_permission() is False
    assert manager.can_draw_overlays() is False
    assert manager.get_missing_permissions() == list(
        PermissionConstants.REQUIRED_PERMISSIONS)
    # DEVIATION: the overlay-settings intent is platform-only.
    assert manager.overlay_permission_settings_intent() is None


def test_granted_set_drives_every_helper():
    granted = {CALL_PHONE, READ_PHONE_STATE, CAMERA}
    manager = PermissionManager(checker=granted.__contains__,
                                can_draw_overlays=lambda: True)
    assert manager.has_phone_permissions() is True
    assert manager.has_camera_permission() is True
    assert manager.has_contact_permission() is False
    assert manager.check_overlay_permission() is True
    assert manager.is_permission_granted(CAMERA) is True
    assert manager.is_permission_granted(READ_CONTACTS) is False
    assert manager.check_all_permissions() is False  # contacts/vibrate missing
    assert manager.get_missing_permissions() == [
        MODIFY_AUDIO_SETTINGS, READ_CONTACTS, VIBRATE]


def test_phone_permissions_require_both_call_and_state():
    only_call = PermissionManager(checker={CALL_PHONE}.__contains__)
    assert only_call.has_phone_permissions() is False
    only_state = PermissionManager(checker={READ_PHONE_STATE}.__contains__)
    assert only_state.has_phone_permissions() is False
