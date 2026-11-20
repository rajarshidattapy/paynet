// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.metrics

import android.content.Context
import android.util.AtomicFile
import com.flowpay.app.BuildConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.util.UUID

/** One consented first-open receipt. Independent of every payment repository. */
object InstallReporter {
    private const val RETRY_DELAY_MS = 30_000L
    private const val REQUEST_TIMEOUT_MS = 8_000

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutex = Mutex()
    private var nextAttempt = 0L
    private var retryScheduled = false

    @Volatile
    private var storageUnavailable = false

    private fun file(context: Context) = AtomicFile(File(context.noBackupFilesDir, "install-receipt.json"))

    fun configured(): Boolean = validEndpoint(BuildConfig.INSTALL_METRICS_URL, BuildConfig.DEBUG)

    fun validEndpoint(value: String, debug: Boolean): Boolean = runCatching {
        val uri = URI(value)
        uri.host != null && uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null &&
            (uri.scheme == "https" || (debug && uri.scheme == "http" && uri.host == "127.0.0.1"))
    }.getOrDefault(false)

    private fun read(context: Context): JSONObject = try {
        JSONObject(file(context).openRead().bufferedReader().use { it.readText() })
    } catch (_: IOException) {
        JSONObject()
    } catch (_: org.json.JSONException) {
        JSONObject()
    }

    private fun write(context: Context, state: JSONObject) {
        val target = file(context)
        val stream = target.startWrite()
        try {
            stream.write(state.toString().toByteArray(Charsets.UTF_8))
            target.finishWrite(stream)
        } catch (error: IOException) {
            target.failWrite(stream)
            throw error
        }
    }

    fun needsChoice(context: Context): Boolean {
        if (!configured() || storageUnavailable) return false
        val policy = android.os.StrictMode.allowThreadDiskReads()
        return try { !read(context).has("consent") } finally {
            android.os.StrictMode.setThreadPolicy(policy)
        }
    }

    suspend fun choose(context: Context, allow: Boolean) {
        mutex.withLock {
            val state = read(context)
            state.put("consent", allow)
            if (allow && !state.has("id")) state.put("id", UUID.randomUUID().toString())
            try {
                write(context, state)
            } catch (_: IOException) {
                // A reporting-storage failure must never prevent payments or force consent.
                storageUnavailable = true
            }
        }
        if (allow) report(context)
    }

    fun report(context: Context) {
        if (!configured() || storageUnavailable) return
        val app = context.applicationContext
        scope.launch {
            mutex.withLock {
                try {
                    val state = read(app)
                    if (!state.optBoolean("consent") || state.optBoolean("sent")) return@withLock
                    val now = android.os.SystemClock.elapsedRealtime()
                    if (now < nextAttempt) {
                        if (!retryScheduled) {
                            retryScheduled = true
                            val wait = nextAttempt - now
                            scope.launch {
                                delay(wait)
                                mutex.withLock { retryScheduled = false }
                                report(app)
                            }
                        }
                        return@withLock
                    }
                    nextAttempt = now + RETRY_DELAY_MS
                    val payload = JSONObject().put("installation_id", state.getString("id"))
                        .put("version", BuildConfig.VERSION_NAME).toString().toByteArray(Charsets.UTF_8)
                    val connection = URI(BuildConfig.INSTALL_METRICS_URL).toURL().openConnection() as HttpURLConnection
                    try {
                        connection.requestMethod = "POST"
                        connection.instanceFollowRedirects = false
                        connection.connectTimeout = REQUEST_TIMEOUT_MS
                        connection.readTimeout = REQUEST_TIMEOUT_MS
                        connection.doOutput = true
                        connection.setRequestProperty("Content-Type", "application/json")
                        connection.setFixedLengthStreamingMode(payload.size)
                        connection.outputStream.use { it.write(payload) }
                        if (connection.responseCode == HttpURLConnection.HTTP_OK) {
                            val response = connection.inputStream.bufferedReader().use { it.readText() }
                            if (JSONObject(response).optBoolean("registered")) {
                                state.put("sent", true)
                                write(app, state)
                            }
                        }
                    } finally {
                        connection.disconnect()
                    }
                } catch (_: IOException) {
                    // Keep the same ID, and retry on a later foreground/connection event.
                } catch (_: org.json.JSONException) {
                    // Do not acknowledge a malformed or unexpected server response.
                }
            }
        }
    }
}
