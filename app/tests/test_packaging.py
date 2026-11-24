# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Feature 17: packaging parity tests — the buildozer spec, the p4a manifest
# hook, the Java bridge sources and the CI workflow stay in lockstep with
# the Kotlin app's manifest and the ported permission constants.

import os
import re

KIVY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(KIVY_DIR)


def _spec():
    with open(os.path.join(KIVY_DIR, "buildozer.spec"), encoding="utf-8") as f:
        return f.read()


def _spec_value(spec, key):
    match = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", spec, re.MULTILINE)
    assert match, f"{key} missing from buildozer.spec"
    return match.group(1).strip()


MANIFEST_PERMISSIONS = [
    "INTERNET", "ACCESS_NETWORK_STATE", "CALL_PHONE", "READ_PHONE_STATE",
    "ANSWER_PHONE_CALLS", "CAMERA", "MODIFY_AUDIO_SETTINGS",
    "SYSTEM_ALERT_WINDOW", "READ_CONTACTS", "VIBRATE", "RECEIVE_SMS",
    "POST_NOTIFICATIONS",
]


def test_spec_permissions_match_the_kotlin_manifest():
    spec = _spec_value(_spec(), "android.permissions")
    assert [p.strip() for p in spec.split(",")] == MANIFEST_PERMISSIONS


def test_spec_identity_and_sdk_parity():
    spec = _spec()
    assert _spec_value(spec, "package.domain") == "com.paynet.app"
    assert _spec_value(spec, "package.name") == "sms"
    # buildozer joins domain + name: this is the Kotlin applicationId.
    assert (_spec_value(spec, "package.domain") + "."
            + _spec_value(spec, "package.name")) == "com.paynet.app.sms"
    assert _spec_value(spec, "version") == "1.0.0-sms"
    assert _spec_value(spec, "android.minapi") == "29"
    assert _spec_value(spec, "android.api") == "36"
    assert _spec_value(spec, "orientation") == "portrait"
    assert "arm64-v8a" in _spec_value(spec, "android.archs")
    assert "armeabi-v7a" in _spec_value(spec, "android.archs")
    assert "pyjnius" in _spec_value(spec, "requirements")
    assert "com.google.zxing:core:3.5.3" in _spec_value(
        spec, "android.gradle_dependencies")


def test_spec_wires_java_sources_and_the_manifest_hook():
    spec = _spec()
    add_src = _spec_value(spec, "android.add_src")
    assert add_src == "android-src"
    for java in ("PayNetSmsBridge.java", "PayNetSmsReceiver.java"):
        path = os.path.join(KIVY_DIR, add_src, "com/paynet/app/kivy", java)
        assert os.path.isfile(path), path
    assert _spec_value(spec, "p4a.hook") == "p4a/hook.py"
    assert os.path.isfile(os.path.join(KIVY_DIR, "p4a", "hook.py"))


def test_manifest_hook_declares_the_sms_receiver_with_kotlin_parity():
    with open(os.path.join(KIVY_DIR, "p4a", "hook.py"), encoding="utf-8") as f:
        hook = f.read()
    assert 'android:name="com.paynet.app.kivy.PayNetSmsReceiver"' in hook
    assert 'android:permission="android.permission.BROADCAST_SMS"' in hook
    assert 'android:priority="999"' in hook
    assert "android.provider.Telephony.SMS_RECEIVED" in hook
    assert 'android:exported="true"' in hook


def test_java_receiver_forwards_assembled_sms_to_the_bridge():
    with open(os.path.join(
            KIVY_DIR, "android-src/com/paynet/app/kivy/PayNetSmsReceiver.java"),
            encoding="utf-8") as f:
        source = f.read()
    # PDU extraction, multipart concatenation, goAsync lifetime, then the
    # Python bridge — the Kotlin receiver's shape.
    assert "getMessagesFromIntent" in source
    assert "getDisplayOriginatingAddress" in source
    assert "goAsync()" in source
    assert "PayNetSmsBridge.dispatch" in source


def test_spec_keeps_tests_and_dev_scripts_out_of_the_apk():
    spec = _spec()
    excluded = [d.strip() for d in _spec_value(spec, "source.exclude_dirs").split(",")]
    assert {"tests", "snapshot_failures", "p4a", "android-src"} <= set(excluded)
    for directory in ("tests", "p4a", "android-src"):
        assert os.path.isdir(os.path.join(KIVY_DIR, directory)), directory
    assert _spec_value(spec, "source.exclude_patterns") == "render_*.py"


def test_ci_workflow_runs_the_suite_from_the_app_directory():
    path = os.path.join(REPO_ROOT, ".github", "workflows", "build.yml")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        workflow = f.read()
    assert "pytest tests -q" in workflow
    assert "working-directory: app" in workflow
    # Every path the workflow names must exist (the folder was renamed once
    # already and CI silently pointed at nothing).
    for match in re.finditer(r"(?:working-directory:|-r|cache-dependency-path:)\s+(app\S*)", workflow):
        assert os.path.exists(os.path.join(REPO_ROOT, match.group(1))), match.group(1)
