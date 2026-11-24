# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Feature 17: structural tests for the Android bindings, driven through a
# mocked jnius (the bindings are import-guarded and never touch Java on the
# desktop), plus the metrics POST request/response contract.

import io
import json
import threading
import time

import pytest

import paynet.platform.android as android
from paynet.permissions import PermissionConstants
from paynet.telephony.call_manager import PhonePlatform


# --- helpers: a minimal fake Java world ------------------------------------


class FakeClass:
    """Stands in for one autoclass()'d Java class: named attrs only."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)


class _FakeManager:
    def __init__(self, states=()):
        self._states = list(states) or [0]
        self._index = 0
        self.registered = None
        self.unregistered = False

    def getCallState(self):
        state = self._states[min(self._index, len(self._states) - 1)]
        self._index += 1
        return state

    def registerTelephonyCallback(self, _executor, listener):
        self.registered = listener

    def unregisterTelephonyCallback(self, _listener):
        self.unregistered = True


def _patch_context(monkeypatch, manager=None, package="com.paynet.app.sms"):
    context = FakeClass(
        getSystemService=lambda _name: manager,
        getMainExecutor=lambda: None,
        getPackageName=lambda: package,
    )
    activity = FakeClass(getApplicationContext=lambda: context)
    monkeypatch.setattr(android, "_activity", lambda: activity)
    monkeypatch.setattr(android, "_context", lambda: context)
    return context


# --- import guard -----------------------------------------------------------


def test_bindings_are_none_off_android():
    from paynet import platform
    assert platform.create_bindings() is None


def test_jnius_import_is_guarded():
    # Desktop: jnius is absent and the module still imported.
    assert android.JNIUS_IMPORT_ERROR is not None
    assert android.autoclass is None


# --- protocol conformance ---------------------------------------------------


def test_phone_platform_implements_the_whole_protocol():
    members = [name for name in dir(PhonePlatform) if not name.startswith("_")]
    for name in members:
        assert callable(getattr(android.AndroidPhonePlatform, name)), name


def test_telephony_adapter_surface():
    for name in ("register", "unregister", "current_state"):
        assert callable(getattr(android.AndroidTelephonyAdapter, name))


# --- permission checker -----------------------------------------------------


def test_permission_checker_reads_contextcompat(monkeypatch):
    _patch_context(monkeypatch)
    granted = {"android.permission.CALL_PHONE"}
    monkeypatch.setattr(android, "autoclass", lambda name: {
        "androidx.core.content.ContextCompat": FakeClass(
            checkSelfPermission=lambda _ctx, perm: 0 if perm in granted else -1),
        "android.content.pm.PackageManager": FakeClass(PERMISSION_GRANTED=0),
    }[name])
    checker = android.AndroidPermissionChecker()
    assert checker("android.permission.CALL_PHONE") is True
    assert checker("android.permission.CAMERA") is False


# --- telephony adapter --------------------------------------------------------


def test_adapter_polls_on_legacy_apis_and_reports_transitions(monkeypatch):
    manager = _FakeManager(states=[0, 0, 2, 2, 0])
    _patch_context(monkeypatch, manager)
    monkeypatch.setattr(android, "_version_sdk", lambda: 30)
    monkeypatch.setattr(android, "autoclass",
                        lambda name: FakeClass(TELEPHONY_SERVICE="phone"))
    monkeypatch.setattr(android, "CALL_STATE_POLL_S", 0.01)

    seen = []
    adapter = android.AndroidTelephonyAdapter()
    adapter.register(seen.append)
    deadline = time.time() + 2.0
    while time.time() < deadline and len(seen) < 3:
        time.sleep(0.01)
    adapter.unregister()

    assert seen[0] == 0 and 2 in seen  # idle, then offhook transition
    assert manager.registered is None  # polling path never registered
    assert adapter.current_state() in (0, 2)


def test_adapter_uses_telephony_callback_on_api_31(monkeypatch):
    manager = _FakeManager()
    _patch_context(monkeypatch, manager)
    monkeypatch.setattr(android, "_version_sdk", lambda: 34)
    monkeypatch.setattr(android, "autoclass",
                        lambda name: FakeClass(TELEPHONY_SERVICE="phone"))

    adapter = android.AndroidTelephonyAdapter()
    adapter.register(lambda _state: None)
    assert manager.registered is not None
    adapter.unregister()
    assert manager.unregistered is True


# --- metrics POST -------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_urllib_poster_request_shape_and_200_handling(monkeypatch):
    captured = {}

    class _Opener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse(200, b'{"registered": true}')

    monkeypatch.setattr(android.urllib.request, "build_opener",
                        lambda *_handlers: _Opener())
    result = android.urllib_poster(
        "https://collector.example.com/api/installs",
        {"installation_id": "abc", "version": "1.0.0-sms"})

    request = captured["request"]
    assert captured["timeout"] == 8
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert json.loads(request.data.decode()) == {
        "installation_id": "abc", "version": "1.0.0-sms"}
    assert result == {"registered": True}


def test_urllib_poster_failures_return_none(monkeypatch):
    class _Opener:
        def open(self, _request, timeout):
            raise OSError("no network")

    monkeypatch.setattr(android.urllib.request, "build_opener",
                        lambda *_handlers: _Opener())
    assert android.urllib_poster("https://x.example", {}) is None

    class _NotOk:
        def open(self, _request, timeout):
            return _FakeResponse(500, b"")

    monkeypatch.setattr(android.urllib.request, "build_opener",
                        lambda *_handlers: _NotOk())
    assert android.urllib_poster("https://x.example", {}) is None


# --- SMS bridge ---------------------------------------------------------------


def test_sms_bridge_listener_forwards_to_handle_sms():
    handled = []
    listener = android.SmsBridgeListener(
        lambda sender, body: handled.append((sender, body)) or True)
    listener.onSms("AM-HDFCBK", "Rs 125 debited")
    assert handled == [("AM-HDFCBK", "Rs 125 debited")]


def test_permission_groups_exposed_for_the_requester():
    assert "android.permission.RECEIVE_SMS" in PermissionConstants.PHONE_PERMISSIONS
    assert "android.permission.ANSWER_PHONE_CALLS" in PermissionConstants.PHONE_PERMISSIONS
