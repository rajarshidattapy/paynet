# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ports the CallManager decision/state logic against a fake platform
# (the Kotlin had no unit tests for this class — coverage here is new but
# the semantics under test are the Kotlin's). GUARDRAIL: no real dialer,
# telephony or audio device is ever touched.

from paynet.telephony.call_manager import (
    CALL_STATE_IDLE,
    CALL_STATE_OFFHOOK,
    MODE_IN_CALL,
    MODE_NORMAL,
    STREAM_VOICE_CALL,
    CallManager,
    CallType,
)


class FakePlatform:
    def __init__(self):
        self.permissions = {"android.permission.CALL_PHONE": True}
        self.started_calls = []
        self.fail_next_start = False
        self.call_state = CALL_STATE_IDLE
        self.mode = MODE_NORMAL
        self.volumes = {STREAM_VOICE_CALL: 5}
        self.mic_mute = False
        self.speakerphone = False
        self.listeners = []
        self.telecom_end_result = True
        self.toasts = []

    def has_permission(self, permission):
        return self.permissions.get(permission, False)

    def start_call(self, uri):
        if self.fail_next_start:
            self.fail_next_start = False
            raise RuntimeError("no dialer")
        self.started_calls.append(uri)

    def listen_call_state(self, listener):
        self.listeners.append(listener)

    def unlisten_call_state(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def get_call_state(self):
        return self.call_state

    def get_stream_volume(self, stream):
        return self.volumes.get(stream, 0)

    def set_stream_volume(self, stream, volume, flags):
        self.volumes[stream] = volume

    def get_mode(self):
        return self.mode

    def set_mode(self, mode):
        self.mode = mode

    def set_microphone_mute(self, muted):
        self.mic_mute = muted

    def set_speakerphone_on(self, on):
        self.speakerphone = on

    def telecom_end_call(self):
        return self.telecom_end_result

    def toast(self, message):
        self.toasts.append(message)

    # Test driver: deliver a telephony state to every registered listener.
    def deliver_state(self, state):
        self.call_state = state
        for listener in list(self.listeners):
            listener(state)


def test_initiate_call_requires_call_phone_permission():
    platform = FakePlatform()
    platform.permissions["android.permission.CALL_PHONE"] = False
    manager = CallManager(platform)

    manager.initiate_call("9876543210", CallType.VOICE, on_call_ended=lambda _: None)

    assert platform.started_calls == []


def test_ussd_double_dial_guard_and_uri_encoding():
    platform = FakePlatform()
    manager = CallManager(platform)
    completed = []

    manager.initiate_call(
        "*99*1*2#", CallType.USSD, on_call_ended=lambda _: None,
        on_ussd_complete=lambda: completed.append(True),
    )
    # The pending guard rejects a duplicate before the first call ends.
    manager.initiate_call(
        "*99*1*2#", CallType.USSD, on_call_ended=lambda _: None,
        on_ussd_complete=lambda: completed.append(True),
    )

    # '#' must be percent-encoded or the dialer truncates the code.
    assert platform.started_calls == ["tel:%2A99%2A1%2A2%23"]

    # Call ends -> guard resets and the completion callback fires once.
    platform.deliver_state(CALL_STATE_IDLE)
    assert completed == [True]

    manager.initiate_call(
        "*99#", CallType.USSD, on_call_ended=lambda _: None,
        on_ussd_complete=lambda: completed.append(True),
    )
    assert platform.started_calls[-1] == "tel:%2A99%23"


def test_non_ussd_call_tracks_state_and_reports_end_once():
    platform = FakePlatform()
    manager = CallManager(platform)
    ended = []

    manager.initiate_call("9876543210", CallType.VOICE, on_call_ended=ended.append)
    assert manager.is_call_in_progress() is True

    platform.deliver_state(CALL_STATE_OFFHOOK)
    platform.deliver_state(CALL_STATE_IDLE)

    assert ended == [CallType.VOICE]
    assert manager.is_call_in_progress() is False

    # A later IDLE with nothing in progress reports nothing.
    platform.deliver_state(CALL_STATE_IDLE)
    assert ended == [CallType.VOICE]


def test_failed_start_rolls_back_state_and_unregisters():
    platform = FakePlatform()
    manager = CallManager(platform)
    ended = []
    platform.fail_next_start = True

    manager.initiate_call("9876543210", CallType.VOICE, on_call_ended=ended.append)

    assert manager.is_call_in_progress() is False
    assert platform.listeners == []
    # A stray IDLE after the rollback must not fire the callback.
    platform.deliver_state(CALL_STATE_IDLE)
    assert ended == []


def test_mute_touches_only_the_voice_call_stream_and_unmute_restores():
    platform = FakePlatform()
    platform.volumes = {STREAM_VOICE_CALL: 5, 2: 7, 4: 3}  # ring, alarm untouched
    manager = CallManager(platform)

    assert manager.mute_call_audio() is True
    assert manager.is_audio_muted() is True
    assert platform.mode == MODE_IN_CALL
    assert platform.mic_mute is True
    assert platform.volumes[STREAM_VOICE_CALL] == 0
    assert platform.volumes[2] == 7 and platform.volumes[4] == 3

    assert manager.unmute_call_audio() is True
    assert manager.is_audio_muted() is False
    assert platform.mode == MODE_NORMAL
    assert platform.mic_mute is False
    assert platform.volumes[STREAM_VOICE_CALL] == 5


def test_minimum_volume_stores_original_and_restore_returns_it():
    platform = FakePlatform()
    manager = CallManager(platform)

    assert manager.set_call_volume_to_minimum() is True
    assert platform.volumes[STREAM_VOICE_CALL] == 1

    assert manager.restore_call_volume() is True
    assert platform.volumes[STREAM_VOICE_CALL] == 5


def test_terminate_call_is_honest_without_permission_or_call():
    platform = FakePlatform()
    manager = CallManager(platform)

    # No call in progress.
    assert manager.terminate_call() is False

    # Call in progress but ANSWER_PHONE_CALLS missing.
    platform.call_state = CALL_STATE_OFFHOOK
    assert manager.terminate_call() is False

    platform.permissions["android.permission.ANSWER_PHONE_CALLS"] = True
    assert manager.terminate_call() is True


def test_upi123_rejects_invalid_input_and_respects_permission():
    platform = FakePlatform()
    manager = CallManager(platform)

    assert manager.initiate_upi123_call("", "") is False
    assert platform.started_calls == []
    assert platform.toasts, "invalid input must surface a message"

    platform.permissions["android.permission.CALL_PHONE"] = False
    assert manager.initiate_upi123_call("9876543210", "100") is False
    assert platform.started_calls == []

    platform.permissions["android.permission.CALL_PHONE"] = True
    assert manager.initiate_upi123_call("9876543210", "100") is True
    assert len(platform.started_calls) == 1


def test_cleanup_restores_audio_and_releases_everything():
    platform = FakePlatform()
    manager = CallManager(platform)
    manager.mute_call_audio()
    manager.initiate_call("9876543210", CallType.VOICE, on_call_ended=lambda _: None)

    manager.cleanup()

    assert manager.is_audio_muted() is False
    assert manager.is_call_in_progress() is False
    assert platform.listeners == []
    assert platform.volumes[STREAM_VOICE_CALL] == 5
