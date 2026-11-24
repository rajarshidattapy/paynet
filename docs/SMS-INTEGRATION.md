# SMS build integration

SMS source integration. APK binaries are not published.

- Based on the current version-26 UI, retaining setup, theme, history and animation refinements.
- Original parser and SMS pipeline from Flowpayup/Payments-Without-Internet commit cd56960.
- Separate application ID: com.paynet.app.sms; version code 27; label PayNet SMS.
- The non-SMS source and APKs remain separate and unchanged.
- RECEIVE_SMS only, no READ_SMS. Matching is restricted to an active operation window.
- Bank-message results replace manual outcome prompts in this variant.
- The parser is unchanged. Starting a fresh operation now clears stale amount/recipient filters.
- Result-screen AppCompat theme restored following a device-test crash.

Build with JDK 17 and Android SDK 36/build-tools 35.0.0:

    ./gradlew :app:assembleDebug :app:testDebugUnitTest
    ./gradlew :app:assembleRelease -PallowNoMetrics

Release signing uses local keystore.properties and is not included in source control.
Unsigned CI builds additionally require -PallowUnsigned.

Run synthetic integration tests on the separate SMS install:

    ./gradlew :app:connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.paynet.app.SmsIntegrationDeviceTest

The tests do not dial, transfer money or read the inbox. They cover debit confirmation,
failure, duplicate delivery, unrelated credits, amount mismatch, cancellation,
orphaned pending rows and fresh QR operation windows. They delete only synthetic
records in com.paynet.app.sms; do not run this test class against a populated SMS install.

Initial device run exposed a result-screen theme crash, now fixed.
All 8 synthetic integration tests pass on Samsung SM-M055F.
All 226 unit tests, lint, detekt and coverage checks pass.
Signed release launch verified on Samsung; original non-SMS app remains version 26.
A real bank-message flow has not been verified.
No real bank transaction was performed.

The QR deadline closure and success, failure and unverified result screens also pass Samsung device checks.
