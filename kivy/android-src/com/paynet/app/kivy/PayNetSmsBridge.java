// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay
// Feature 17: static bridge between the Java SMS receiver and Python.
// pyjnius cannot subclass BroadcastReceiver, so the receiver ships as Java
// source (added through buildozer's android.add_src) and forwards each
// assembled message to the Python-registered Listener.
package com.paynet.app.kivy;

public final class PayNetSmsBridge {

    public interface Listener {
        void onSms(String sender, String body);
    }

    private static Listener listener;

    private PayNetSmsBridge() {
    }

    public static synchronized void setListener(Listener value) {
        listener = value;
    }

    /** Called by PayNetSmsReceiver on the broadcast's background thread. */
    public static void dispatch(String sender, String body) {
        Listener current;
        synchronized (PayNetSmsBridge.class) {
            current = listener;
        }
        if (current != null) {
            current.onSms(sender, body);
        }
    }
}
