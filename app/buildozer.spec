# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Buildozer packaging spec for the PayNet Kivy port (feature 17).
# Manifest parity target: app/src/main/AndroidManifest.xml in the Kotlin app.

[app]

# (str) Title of your application
title = PayNet

# (str) Package name — matches the Kotlin applicationId (app/build.gradle.kts).
package.name = paynet.sms

# (str) Package domain (needed for android/java packaging)
package.domain = com.paynet.app

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (empty = all)
source.include_exts = py,png,jpg,kv,atlas,json

# (str) Application versioning (method 1)
version = 1.0.0-sms

# (list) Application requirements
# pyjnius powers the platform bindings in paynet/platform/android.py;
# pillow decodes gallery-picked QR images; zxing-cpp is NOT used (decode runs
# through the Android ZXing binding on device, injected on desktop).
requirements = python3,kivy,pyjnius,pillow

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
# Parity: the Kotlin QR/history/settings screens lock portrait.
orientation = portrait

# (bool) Indicate if the application should be fullscreen
fullscreen = 0

#
# Android specific
#

# (list) Permissions — parity with app/src/main/AndroidManifest.xml:
# INTERNET + ACCESS_NETWORK_STATE serve only the optional, one-time
# installation receipt (metrics/InstallReporter); ANSWER_PHONE_CALLS lets the
# in-call overlay's "End call" button hang up via TelecomManager.endCall();
# SYSTEM_ALERT_WINDOW is the call overlay; BROADCAST_SMS is declared on the
# receiver itself (see android.manifest.intent_filters / service below).
android.permissions = INTERNET,ACCESS_NETWORK_STATE,CALL_PHONE,READ_PHONE_STATE,ANSWER_PHONE_CALLS,CAMERA,MODIFY_AUDIO_SETTINGS,SYSTEM_ALERT_WINDOW,READ_CONTACTS,VIBRATE,RECEIVE_SMS,POST_NOTIFICATIONS

# (int) Minimum API required — parity with minSdk 29.
android.minapi = 29

# (int) Android API to use — parity with targetSdk 36.
android.api = 36

# (bool) Android logcat only print for your application (remove to see all)
#logcat_filters = *:S python:D

# (list) The Android archs to build for — parity with the Kotlin release
# scoping (arm64-v8a + armeabi-v7a; the audience is entry-level phones).
android.archs = arm64-v8a, armeabi-v7a

# (bool) AndroidX — ContextCompat/ActivityCompat permission APIs.
android.enable_androidx = True

# (list) Gradle dependencies — ZXing core for QR decode, parity with the
# Kotlin app's com.google.zxing:core:3.5.3 (gradle/libs.versions.toml).
android.gradle_dependencies = com.google.zxing:core:3.5.3

# (list) Java sources added to the build: the SMS_RECEIVED manifest receiver
# and its Python bridge (pyjnius cannot subclass BroadcastReceiver).
android.add_src = android-src

# (str) p4a hook: stock buildozer has no manifest key for a <receiver>
# element, so p4a/hook.py injects the receiver + service declarations into
# the generated AndroidManifest.xml (manifest parity with the Kotlin app).
p4a.hook = p4a/hook.py

# (str) The format used to package the app for release mode
# p4a.release = aab

# (bool) enables Android auto backup feature (Android API >=23)
android.backup_rules =

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 1

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
