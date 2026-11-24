# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Feature 17 p4a hook: inject the manifest declarations stock buildozer has
# no keys for (github.com/kivy/buildozer/issues/1518). Manifest parity with
# the Kotlin app/src/main/AndroidManifest.xml:
#   - PayNetSmsReceiver: exported, protected by BROADCAST_SMS, priority 999,
#     SMS_RECEIVED action (receivers/SimpleSMSReceiver.kt in Kotlin).
#   - CallOverlayService parity is the in-app overlay host plus the
#     SYSTEM_ALERT_WINDOW permission; a system window over the dialer is the
#     documented feature-17 gap in MIGRATION.md.

from pathlib import Path

RECEIVER_XML = """
    <receiver
        android:name="com.paynet.app.kivy.PayNetSmsReceiver"
        android:enabled="true"
        android:exported="true"
        android:permission="android.permission.BROADCAST_SMS">
        <intent-filter android:priority="999">
            <action android:name="android.provider.Telephony.SMS_RECEIVED" />
        </intent-filter>
    </receiver>
"""

USES_FEATURE_XML = """
    <uses-feature android:name="android.hardware.camera" android:required="false" />
    <uses-feature android:name="android.hardware.camera.autofocus" android:required="false" />
"""


def after_apk_build(toolchain):
    manifest_file = (Path(toolchain._dist.dist_dir)
                     / "src" / "main" / "AndroidManifest.xml")
    old = manifest_file.read_text(encoding="utf-8")
    new = old.replace("</application>", RECEIVER_XML + "</application>")
    new = new.replace("<application", USES_FEATURE_XML + "<application", 1)
    if new == old:
        raise RuntimeError("p4a hook: failed to inject manifest declarations")
    manifest_file.write_text(new, encoding="utf-8")
    print("p4a hook: SMS receiver + camera features added to the manifest")
