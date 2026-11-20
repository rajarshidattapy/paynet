// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.data

import android.content.Context
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.IOException
import java.security.ProviderException
import javax.crypto.AEADBadTagException

/**
 * The key-loss recovery contract: a wrapped passphrase blob that can no
 * longer be unwrapped (Keystore entry lost/invalidated, e.g. after some
 * device restores or OS updates) must NEVER propagate an exception — it
 * runs on the app's first database touch, so a throw is a permanent launch
 * crash loop. Instead the stale blob is discarded, the wrapping key is
 * reset, and a fresh passphrase is generated.
 */
@RunWith(AndroidJUnit4::class)
class DatabaseKeyManagerRecoveryTest {

    /** Reversible fake of the Keystore wrapper; can simulate a lost key. */
    private class FakeWrapper(
        var failUnwrap: Boolean = false,
        private val unwrapError: () -> Throwable = { AEADBadTagException("wrapping key lost") },
        /** Number of leading wrap() calls that fail; the rest succeed. */
        private var failWrapTimes: Int = 0,
        private val wrapError: () -> Throwable = { AEADBadTagException("cannot wrap") }
    ) : DatabaseKeyManager.Wrapper {
        var discarded = false
        var unwrapAttempts = 0
        var wrapAttempts = 0

        override fun wrap(plain: ByteArray): DatabaseKeyManager.WrappedBlob {
            wrapAttempts++
            if (failWrapTimes > 0) {
                failWrapTimes--
                throw wrapError()
            }
            return DatabaseKeyManager.WrappedBlob(sealed = plain.reversedArray(), iv = ByteArray(12))
        }

        override fun unwrap(sealed: ByteArray, iv: ByteArray): ByteArray {
            unwrapAttempts++
            if (failUnwrap) throw unwrapError()
            return sealed.reversedArray()
        }

        override fun discardKey() {
            discarded = true
        }
    }

    private val context: Context = InstrumentationRegistry.getInstrumentation().context
    private val prefs
        get() = context.getSharedPreferences(DatabaseKeyManager.PREFS_NAME, Context.MODE_PRIVATE)

    @Before
    fun clearPrefs() {
        prefs.edit().clear().commit()
    }

    @Test
    fun first_call_creates_a_passphrase_and_later_calls_return_the_same_one() {
        val wrapper = FakeWrapper()
        val first = DatabaseKeyManager.getOrCreatePassphrase(context, wrapper)
        val second = DatabaseKeyManager.getOrCreatePassphrase(context, wrapper)

        assertNotNull(first)
        assertTrue(first.isNotEmpty())
        assertEquals("stable across calls", first, second)
        assertEquals("second call unwraps the stored blob", 1, wrapper.unwrapAttempts)
    }

    @Test
    fun unwrap_failure_recovers_cleanly_instead_of_throwing() {
        // Seed a healthy blob first.
        val healthy = FakeWrapper()
        val original = DatabaseKeyManager.getOrCreatePassphrase(context, healthy)
        val staleBlob = prefs.getString(DatabaseKeyManager.PREF_WRAPPED, null)
        assertNotNull(staleBlob)

        // Simulate the Keystore entry being lost: unwrap now throws.
        val broken = FakeWrapper(failUnwrap = true)
        val regenerated = DatabaseKeyManager.getOrCreatePassphrase(context, broken)

        // No exception escaped; a fresh passphrase was produced and persisted.
        assertNotNull(regenerated)
        assertTrue(regenerated.isNotEmpty())
        assertNotEquals("stale passphrase must not be reused", original, regenerated)
        assertTrue("stale wrapping key must be discarded", broken.discarded)
        assertNotEquals(
            "a new blob must replace the stale one",
            staleBlob,
            prefs.getString(DatabaseKeyManager.PREF_WRAPPED, null)
        )

        // And the recovery is stable: the next call unwraps the new blob.
        broken.failUnwrap = false
        assertEquals(regenerated, DatabaseKeyManager.getOrCreatePassphrase(context, broken))
    }

    @Test
    fun unchecked_ProviderException_on_unwrap_recovers_instead_of_crashing() {
        // ProviderException is a RuntimeException, so it bypassed the original
        // catch(GeneralSecurityException) entirely and crash-looped the app on
        // its first database touch. Seen on OEM/StrongBox keystore builds.
        val healthy = FakeWrapper()
        val original = DatabaseKeyManager.getOrCreatePassphrase(context, healthy)

        val broken = FakeWrapper(
            failUnwrap = true,
            unwrapError = { ProviderException("keystore daemon died") }
        )
        val regenerated = DatabaseKeyManager.getOrCreatePassphrase(context, broken)

        assertTrue(regenerated.isNotEmpty())
        assertNotEquals(original, regenerated)
        assertTrue("stale wrapping key must be discarded", broken.discarded)
    }

    @Test
    fun IOException_on_unwrap_recovers_instead_of_crashing() {
        // KeyStore.load against a corrupted keystore file.
        val healthy = FakeWrapper()
        DatabaseKeyManager.getOrCreatePassphrase(context, healthy)

        val broken = FakeWrapper(
            failUnwrap = true,
            unwrapError = { IOException("keystore file corrupt") }
        )
        val regenerated = DatabaseKeyManager.getOrCreatePassphrase(context, broken)

        assertTrue(regenerated.isNotEmpty())
        assertTrue(broken.discarded)
    }

    @Test
    fun a_transient_wrap_failure_is_retried_with_a_fresh_wrapping_key() {
        // wrap() was completely unguarded before: the usual cause is an
        // existing keystore entry that can no longer be used, so dropping it
        // and retrying once should succeed and still persist the blob.
        val wrapper = FakeWrapper(
            failWrapTimes = 1,
            wrapError = { ProviderException("existing entry unusable") }
        )
        val passphrase = DatabaseKeyManager.getOrCreatePassphrase(context, wrapper)

        assertTrue(passphrase.isNotEmpty())
        assertEquals("must retry exactly once", 2, wrapper.wrapAttempts)
        assertTrue("the unusable entry must be dropped before retrying", wrapper.discarded)
        assertNotNull(
            "the retry succeeded, so the blob must be persisted",
            prefs.getString(DatabaseKeyManager.PREF_WRAPPED, null)
        )
        // And it round-trips: the persisted blob unwraps to the same value.
        assertEquals(passphrase, DatabaseKeyManager.getOrCreatePassphrase(context, wrapper))
    }

    @Test
    fun a_permanently_unusable_keystore_still_returns_a_passphrase() {
        // Nothing can be persisted, but the app must still launch. History
        // stops surviving restarts; that beats an app that cannot open.
        val wrapper = FakeWrapper(
            failWrapTimes = Int.MAX_VALUE,
            wrapError = { ProviderException("keystore permanently unavailable") }
        )
        val passphrase = DatabaseKeyManager.getOrCreatePassphrase(context, wrapper)

        assertTrue("no exception escaped and a usable key came back", passphrase.isNotEmpty())
        assertEquals("tried once, then retried once, then gave up", 2, wrapper.wrapAttempts)
        assertNull(
            "an unwrappable blob must never be persisted",
            prefs.getString(DatabaseKeyManager.PREF_WRAPPED, null)
        )
    }

    @Test
    fun a_bug_in_our_own_code_is_not_laundered_into_key_regeneration() {
        // The recovery is deliberately narrow. IllegalStateException is not a
        // keystore failure, so it must surface rather than silently produce a
        // fresh passphrase and discard the user's history.
        val wrapper = FakeWrapper(
            failWrapTimes = 1,
            wrapError = { IllegalStateException("programming error") }
        )
        assertThrows(IllegalStateException::class.java) {
            DatabaseKeyManager.getOrCreatePassphrase(context, wrapper)
        }
    }

    @Test
    fun corrupted_prefs_blob_recovers_cleanly_instead_of_throwing() {
        // Garbage that decodes as base64 but can never unwrap.
        prefs.edit()
            .putString(DatabaseKeyManager.PREF_WRAPPED, "Z2FyYmFnZQ==")
            .putString(DatabaseKeyManager.PREF_IV, "aXZpdml2aXZpdg==")
            .commit()

        val wrapper = FakeWrapper(failUnwrap = true)
        val passphrase = DatabaseKeyManager.getOrCreatePassphrase(context, wrapper)

        assertTrue(passphrase.isNotEmpty())
        assertTrue(wrapper.discarded)
        assertFalse(
            "garbage blob must be replaced",
            prefs.getString(DatabaseKeyManager.PREF_WRAPPED, null) == "Z2FyYmFnZQ=="
        )
    }
}
