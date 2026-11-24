<p align="center">
  <img src="docs/readme/paynet-wordmark.png" width="240" alt="PayNet">
</p>

<h3 align="center">UPI payments, even offline.</h3>

<p align="center">
  An Android app for paying over <code>*99#</code> USSD and UPI 123PAY when mobile data is gone but the cellular network is not.
</p>

<p align="center">
  <a href="https://github.com/rajarshidattapy/paynet/actions/workflows/build.yml"><img src="https://github.com/rajarshidattapy/paynet/actions/workflows/build.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-6A4FF0" alt="Apache 2.0"></a>
  <img src="https://img.shields.io/badge/Android-10%2B-6A4FF0" alt="Android 10+">
  <img src="https://img.shields.io/badge/Kotlin-Compose-6A4FF0" alt="Kotlin + Compose">
</p>

---

Mobile data drops. UPI apps stop at the login screen. The phone can still place a call, and India's offline payment rails still work — PayNet is the interface that gets you to them.

No account. No wallet. No data connection. Scan a QR code or pick a contact, and PayNet walks the payment through your bank's own USSD or voice flow while an on-screen guide keeps the steps in view.

<p align="center">
  <img src="docs/home.png" width="300" alt="PayNet home screen">
</p>

## What it does

- **Scan QR → `*99#` USSD.** Point the camera at any UPI QR code and follow the bank's payment menu in the dialler.
- **Pay Contact → UPI 123PAY.** Choose a contact or paste a number, enter the amount, and complete the call-based IVR flow with the on-screen guide alongside.
- **Two rails, one fallback.** `*99#` is unavailable on Jio; the phone-number route uses UPI 123PAY, including on Jio where supported. Availability still depends on your bank and operator, so setup checks both.
- **On-device history.** Bank confirmation messages matched during an active payment window supply the outcome. Records stay encrypted on your phone — nothing is uploaded.

Your bank handles the money. PayNet never holds funds and never sees your UPI PIN — that is entered only in the bank's dialler or IVR.

## Why it exists

A declined transaction and a payment that never starts are different problems. India already has payment services that work without mobile data — `*99#` over USSD and UPI 123PAY over a voice call — but finding the right menu, in the right order, mid-payment, is where people give up. PayNet owns that last mile: recipient selection, QR scanning, step guidance and outcome matching, while the bank's flow does the banking.

## Engineering notes

**The app does not own the whole flow.** USSD menus and voice calls run outside the app. The hand-off to the dialler is unavoidable, so PayNet provides an on-screen guide during calls. It does not use an accessibility service to read or control another app.

**A call ending is not a payment confirmation.** Neither rail gives a reliable success callback. Incoming bank messages are matched only during an active payment window, duplicate messages do not create duplicate results, and a missing confirmation never becomes an assumed outcome.

**History stays on the device.** Payment records use Room with SQLCipher encryption. The database secret is protected through Android Keystore, and the database and key material are excluded from cloud backup and device transfer.

**Your PIN stays with your bank.** Enter it in the bank's USSD or call flow. PayNet does not read or store it.

## Running it

You need JDK 17, Android SDK 36 and Build Tools 35.0.0. With `ANDROID_HOME` set:

```sh
git clone https://github.com/rajarshidattapy/paynet.git
cd paynet
printf 'sdk.dir=%s\n' "$ANDROID_HOME" > local.properties
./gradlew assembleDebug
```

The debug APK lands in `app/build/outputs/apk/debug/`; `./gradlew installDebug` pushes it to a connected device. Dependency downloads need internet — the payment rails do not.

To use it you need **Android 10 or later**, an **Indian SIM linked to a UPI-enabled bank account**, and cellular coverage with support for your chosen route.

## Reading the code

Kotlin and Jetpack Compose, Room + SQLCipher for persistence, CameraX + ZXing for scanning. Start here:

| File | What to look for |
| :--- | :--- |
| [`payment/Upi123CallStringBuilder.kt`](app/src/main/java/com/paynet/app/payment/Upi123CallStringBuilder.kt) | Recipient and amount validation before constructing the call's DTMF string. |
| [`payment/PaymentSessionManager.kt`](app/src/main/java/com/paynet/app/payment/PaymentSessionManager.kt) | Payment lifecycle and state transitions. |
| [`managers/CallManager.kt`](app/src/main/java/com/paynet/app/managers/CallManager.kt) | Dialler interaction, call state and audio restoration. |
| [`services/CallOverlayService.kt`](app/src/main/java/com/paynet/app/services/CallOverlayService.kt) | The on-screen guide during a call. |

More detail lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/TESTING.md](docs/TESTING.md) and [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

## Security

PayNet touches payment flows, USSD dialling and SMS parsing. **Do not file public issues for vulnerabilities** — see [docs/SECURITY.md](docs/SECURITY.md) for the reporting address, supported versions and the data-handling threat model.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). PayNet is an independent project, not affiliated with NPCI, any bank or any telecom operator.
