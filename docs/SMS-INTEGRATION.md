# SMS build integration

SMS source integration. APK binaries are not published. The Python/Kivy code
has buildozer packaging (`app/buildozer.spec`) that has not been built or run
on a device yet.

- The Kivy app is a port of the SMS variant of the earlier Kotlin app; it reports its version as `1.0.0-sms` (`AppContainer` in `app/paynet/app.py`). The Kotlin variant's application ID (`com.paynet.app.sms`) is reproduced by `app/buildozer.spec` (domain `com.paynet.app` + name `sms`); its version code is not.
- Original parser and SMS pipeline from Flowpayup/Payments-Without-Internet commit cd56960, ported to `app/paynet/sms/` (`parser.py`, `detector.py`, `pipeline.py`, `receiver.py`, `notifier.py`).
- RECEIVE_SMS only, no READ_SMS. Matching is restricted to an active operation window.
- Bank-message results replace manual outcome prompts in this variant.
- The parser is unchanged by the port. Starting a fresh operation (`TransactionDetector.start_operation`) clears stale amount/recipient filters.
- The Android side — assembling an SMS from its PDUs in the Java `PayNetSmsReceiver`, forwarding it through `PayNetSmsBridge`, posting the result notification and launching the result screen — is written (`app/android-src/`, `app/paynet/platform/android.py`) but has not been run on a device.

Run and test from `app/`:

    python main.py
    python -m pytest tests -q

There is no APK build, release signing, or device test run for the Python code yet.

The synthetic integration scenarios run hermetically, against fakes and a temporary sqlite database:

    python -m pytest tests/test_sms_pipeline.py tests/test_sms_receiver_notifier.py tests/test_payment_session.py tests/test_payment_window.py tests/test_sms_parser.py -q

The tests do not dial, transfer money or read the inbox. They cover debit confirmation,
failure, duplicate delivery, unrelated credits, amount mismatch, cancellation,
orphaned pending rows and opening the window for a QR payment (`tests/test_qr_scanner.py`).
They write only to temporary directories. [TESTING.md](TESTING.md) shows how to replay
a bank SMS through the same pipeline by hand.

## Status of the Python port

All unit tests pass on desktop. The SMS receiver binding, notifications and
result-screen launch have not been run on any device. A real bank-message flow
has not been verified. No real bank transaction was performed.

## History: the Kotlin SMS build

Recorded for reference; none of this was re-run against the Python code.

- On a Samsung SM-M055F, all 8 synthetic on-device SMS integration tests passed, after a result-screen theme crash found in the first device run was fixed.
- The QR deadline closure and success, failure and unverified result screens also passed Samsung device checks.
- A signed release launch was verified on Samsung.
- A real bank-message flow was not verified, and no real bank transaction was performed.
