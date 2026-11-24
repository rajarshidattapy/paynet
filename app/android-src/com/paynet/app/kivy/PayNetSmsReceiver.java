// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay
// Feature 17: the SMS_RECEIVED manifest receiver, parity with the Kotlin
// app's receivers/SimpleSMSReceiver.kt PDU assembly. PDU extraction and
// multipart concatenation happen here (Java); every guard and the ingestion
// itself live in Python (paynet/sms/receiver.py) behind PayNetSmsBridge.
package com.paynet.app.kivy;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.provider.Telephony;
import android.telephony.SmsMessage;

public class PayNetSmsReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null
                || !Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction())) {
            return;
        }
        SmsMessage[] parts = Telephony.Sms.Intents.getMessagesFromIntent(intent);
        if (parts == null || parts.length == 0) {
            return;
        }
        // Multipart messages share the originating address; concatenate the
        // bodies exactly as the Kotlin receiver does before guarding.
        String sender = parts[0].getDisplayOriginatingAddress();
        StringBuilder body = new StringBuilder();
        for (SmsMessage part : parts) {
            if (part != null && part.getMessageBody() != null) {
                body.append(part.getMessageBody());
            }
        }
        // goAsync(): the broadcast stays alive while Python's pipeline runs
        // on this background thread (mirrors Dispatchers.IO in the Kotlin
        // receiver).
        final BroadcastReceiver.PendingResult pending = goAsync();
        final String finalSender = sender;
        final String finalBody = body.toString();
        new Thread(() -> {
            try {
                PayNetSmsBridge.dispatch(finalSender, finalBody);
            } finally {
                pending.finish();
            }
        }).start();
    }
}
