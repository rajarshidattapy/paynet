package com.paynet.app.metrics

import android.app.Application
import android.content.Context
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeFalse
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
class InstallReceiptStateTest {
    private lateinit var context: Context
    private lateinit var receipt: File

    @Before
    fun reset() {
        // These state tests must never contact a configured real collector.
        assumeFalse(InstallReporter.configured())
        context = RuntimeEnvironment.getApplication()
        receipt = File(context.noBackupFilesDir, "install-receipt.json")
        receipt.delete()
        File(receipt.path + ".bak").delete()
    }

    @Test
    fun decliningNeverGeneratesAnIdentifier() = runBlocking {
        InstallReporter.choose(context, false)
        val state = JSONObject(receipt.readText())
        assertFalse(state.getBoolean("consent"))
        assertFalse(state.has("id"))
        assertFalse(state.optBoolean("sent"))
    }

    @Test
    fun retriesAndChangedConsentKeepTheSameInstallationId() = runBlocking {
        InstallReporter.choose(context, true)
        val first = JSONObject(receipt.readText()).getString("id")
        InstallReporter.choose(context, false)
        InstallReporter.choose(context, true)
        assertEquals(first, JSONObject(receipt.readText()).getString("id"))
        assertFalse(JSONObject(receipt.readText()).optBoolean("sent"))
    }

    @Test
    fun alreadyAcknowledgedReceiptSurvivesOptOutAndBackIn() = runBlocking {
        InstallReporter.choose(context, true)
        val state = JSONObject(receipt.readText()).put("sent", true)
        receipt.writeText(state.toString())
        InstallReporter.choose(context, false)
        InstallReporter.choose(context, true)
        val final = JSONObject(receipt.readText())
        assertTrue(final.getBoolean("sent"))
        assertEquals(state.getString("id"), final.getString("id"))
        assertTrue(receipt.path.contains("no_backup"))
    }
}
