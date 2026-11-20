<p>
  <a href="https://www.flowpayup.com/"><picture><source media="(prefers-color-scheme: light)" srcset="docs/readme/wordmark-light-theme.png"><img src="docs/readme/wordmark-white.png" width="200" alt="Flowpay"></picture></a>
</p>

# Payments without internet

*An Android app for UPI payments over `*99#` USSD and UPI 123PAY.*

UPI payments can stop before a transaction even begins: the phone has a cellular signal, but the app cannot connect over mobile data. Flowpay gives Android users a way into the USSD and voice-based payment services that already exist, through a familiar interface for scanning a QR code or paying a phone number.

No Flowpay account. No wallet to top up. **No mobile data or Wi-Fi needed to pay.** Just one bar of cellular signal to get started.

**[Build the app](#build-from-source)** &nbsp; · &nbsp; [How it works](#what-it-does) &nbsp; · &nbsp; [Read the code](#reading-the-code) &nbsp; · &nbsp; [Website](https://www.flowpayup.com/)

<p align="center">
  <img src="docs/readme/home-rounded.png" width="300" alt="Flowpay home screen in red and black, with payment shortcuts and recent payments">
</p>

## Why it was built

The starting question was simple: why should losing mobile data make it so difficult to pay from a smartphone that can still place a call?

A declined transaction and a payment that never starts are different problems. If an app cannot connect, the user may never reach the point of entering an amount or authorising a payment. Improving what happens after submission does not solve that earlier failure.

India already has payment services that work without mobile data. `*99#` uses USSD menus; UPI 123PAY provides a voice-based route. But knowing those services exist is only the beginning. The user still has to find the right entry point, navigate the prompts and work out what happened when the session ends.

That is the part Flowpay works on. It brings recipient selection, QR scanning and payment guidance into an Android interface, while the bank’s USSD or voice flow handles the payment. Cellular coverage, bank support and operator support still apply, but the user has a place to start.

## What it does

Flowpay brings two existing payment routes into one app:

- **Scan QR → `*99#` USSD.** Scan a UPI QR code and follow the bank’s payment menu in the dialler.
- **Pay Contact → UPI 123PAY.** Choose a contact or paste a phone number, enter the amount, and follow the call-based payment flow. An on-screen guide keeps the steps in view.

Your bank handles the payment. Flowpay does not hold your money or read your UPI PIN.

### Why both routes

USSD and voice calls have different network requirements. `*99#` is unavailable on Jio; the phone-number route uses UPI 123PAY, including on Jio where supported. Availability depends on your bank and operator, so setup checks matter.

### Inside the app

- **From setup to payment.** Select your bank and SIM, then set up the payment routes available to you. During a call, an on-screen guide keeps the instructions visible alongside your progress.
- **Start with a QR code or a phone number.** Open the scanner from the home screen, choose someone from your contacts, or paste a number and enter the amount.
- **Keep a record on your phone.** Matching bank messages supply the payment result. Confirmed records stay together in recent payments on your phone.

## Get started

Build the SMS version using the instructions below. Neither of these APKs is published yet. The separate version without SMS access is kept outside this source release.

You need:

- **Android 10 or later.**
- An **Indian SIM linked to your UPI-enabled bank account**.
- **Cellular coverage** and support for your chosen payment route.

Choose your bank and SIM, then complete payment setup. Downloading source and build dependencies requires internet; the payment routes use USSD or voice calls.

## Engineering notes

The difficult part is keeping a payment understandable across an app, the system dialler and a bank’s prompts.

**The app does not own the whole flow.** USSD menus and voice calls run outside Flowpay. A hand-off to the dialler is unavoidable, so the app provides an on-screen guide during calls. It does not use an accessibility service to read or control another app.

**A call ending is not a payment confirmation.** These routes do not give Flowpay a reliable success callback. The source version matches incoming bank messages during an active payment window. Duplicate messages do not create duplicate results. A missing confirmation does not prove that a payment failed.

**History stays on the device.** Payment records use Room with SQLCipher encryption. The database secret is protected through Android Keystore, and the database and key material are excluded from cloud backup and device transfer.

**Your PIN stays with your bank.** Enter it in the bank’s USSD or call flow. Flowpay does not read or store it. The offline release build does not declare the Internet permission.

Your payment history is a personal record, not a bank receipt. If an outcome is unclear, check with your bank or the recipient before trying again.

<details>
<summary><strong>Check the APK yourself</strong></summary>

Use Android SDK tools to inspect a locally built APK:

```sh
apkanalyzer manifest permissions Flowpay.apk
apksigner verify --print-certs Flowpay.apk
```

Release builds require your signing key. No signing keys or APK files are included in this repository.

Camera access supports QR scanning; contacts access supports recipient selection. Phone and SIM access support setup and calls. Display-over-other-apps access supports the call guide.

</details>

## Reading the code

**This source includes SMS confirmation. The separate APK without SMS access remains unpublished.** Incoming messages are processed only during a payment attempt; the app does not read the inbox.

Flowpay is built with Kotlin and Jetpack Compose, with Room for local persistence and CameraX + ZXing for QR scanning. Start here:

| File | What to look for |
| :--- | :--- |
| [`payment/Upi123CallStringBuilder.kt`](app/src/main/java/com/flowpay/app/payment/Upi123CallStringBuilder.kt) | Recipient and amount validation before constructing the call’s DTMF string. |
| [`payment/PaymentSessionManager.kt`](app/src/main/java/com/flowpay/app/payment/PaymentSessionManager.kt) | Payment lifecycle and state transitions. |
| [`managers/CallManager.kt`](app/src/main/java/com/flowpay/app/managers/CallManager.kt) | Dialler interaction, call state and audio restoration. |
| [`services/CallOverlayService.kt`](app/src/main/java/com/flowpay/app/services/CallOverlayService.kt) | The on-screen guide during a call. |

## Build from source

Use JDK 17, Android SDK 36 and Build Tools 35.0.0. With `ANDROID_HOME` set:

```sh
git clone https://github.com/Flowpayup/Payments-Without-Internet.git
cd Payments-Without-Internet
printf 'sdk.dir=%s\n' "$ANDROID_HOME" > local.properties
./gradlew assembleDebug
```

The debug APK is in `app/build/outputs/apk/debug/`. Use `./gradlew installDebug` with an Android device connected to install it. Dependency downloads require internet.

See the [architecture](docs/ARCHITECTURE.md), [testing notes](docs/TESTING.md) and [contribution guide](CONTRIBUTING.md) for implementation details.

**Found an edge case?** [Open an issue](https://github.com/Flowpayup/Payments-Without-Internet/issues) with the app version, device, Android version and steps to reproduce it. Carrier-specific failures and interrupted payment flows are especially useful. Leave payment details and PINs out. Report vulnerabilities through [Security](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE) and [LEGAL.md](LEGAL.md). Flowpay is an independent project, not affiliated with a bank or telecom operator.

---

[Website](https://www.flowpayup.com/) · [Instagram](https://www.instagram.com/flowpayup/) · [GitHub Releases](https://github.com/Flowpayup/Payments-Without-Internet/releases)
