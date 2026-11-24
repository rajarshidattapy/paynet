// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app

import android.app.Activity
import android.app.Application
import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Bundle
import android.os.StrictMode
import android.util.Log
import com.paynet.app.data.SettingsRepository
import com.paynet.app.di.AppContainer
import com.paynet.app.metrics.InstallReporter
import com.paynet.app.payment.PaymentSessionManager
import com.paynet.app.telephony.CallStateCoordinator
import kotlinx.coroutines.CoroutineScope

class PayNetApplication : Application() {

    /** The manual composition root; see [AppContainer]. */
    val container: AppContainer by lazy { AppContainer(applicationContext) }

    // Delegating accessors so existing call sites
    // (PayNetApplication.from(context)?.paymentSessionManager, etc.) keep
    // working while construction lives in the container.
    val appScope: CoroutineScope get() = container.appScope
    val settingsRepository: SettingsRepository get() = container.settingsRepository
    val callStateCoordinator: CallStateCoordinator get() = container.callStateCoordinator
    val paymentSessionManager: PaymentSessionManager get() = container.paymentSessionManager

    companion object {
        private const val TAG = "PayNetApplication"

        /** Convenience accessor for receivers/services that only hold a Context. */
        fun from(context: Context): PayNetApplication? =
            context.applicationContext as? PayNetApplication
    }

    override fun onCreate() {
        super.onCreate()
        if (InstallReporter.configured()) {
            registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
                override fun onActivityResumed(activity: Activity) {
                    InstallReporter.report(applicationContext)
                }
                override fun onActivityCreated(activity: Activity, state: Bundle?) = Unit
                override fun onActivityStarted(activity: Activity) = Unit
                override fun onActivityPaused(activity: Activity) = Unit
                override fun onActivityStopped(activity: Activity) = Unit
                override fun onActivitySaveInstanceState(activity: Activity, state: Bundle) = Unit
                override fun onActivityDestroyed(activity: Activity) = Unit
            })
            val network = getSystemService(ConnectivityManager::class.java)
            network.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
                override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                    if (caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) {
                        InstallReporter.report(applicationContext)
                    }
                }
            })
        }
        // Debug-only tripwire: the first database materialisation (SQLCipher
        // open, Keystore unwrap, upgrade migration) must never run on the
        // main thread — it once did, from this very method. penaltyLog keeps
        // debug builds usable while making any regression loudly visible.
        if (BuildConfig.DEBUG) {
            StrictMode.setThreadPolicy(
                StrictMode.ThreadPolicy.Builder()
                    .detectDiskReads()
                    .detectDiskWrites()
                    .detectNetwork()
                    .penaltyLog()
                    .build()
            )
        }
        // Discard any PENDING rows whose deadline passed while the app was
        // dead. The store resolves lazily on IO (see LazyTransactionStore),
        // so this no longer opens the database on the main thread.
        container.paymentWindowObserver.start()
        paymentSessionManager.reconcileStalePending()
        Log.d(TAG, "PayNetApplication initialized")
    }
}
