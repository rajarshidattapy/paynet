package com.flowpay.app.metrics

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InstallReporterTest {
    @Test
    fun releaseRejectsCleartextAndMissingCollector() {
        assertFalse(InstallReporter.validEndpoint("", false))
        assertFalse(InstallReporter.validEndpoint("http://example.com/api/installs", false))
        assertFalse(InstallReporter.validEndpoint("http://127.0.0.1:8766/api/installs", false))
        assertTrue(InstallReporter.validEndpoint("https://example.com/api/installs", false))
    }

    @Test
    fun debugAllowsOnlyLoopbackCleartext() {
        assertTrue(InstallReporter.validEndpoint("http://127.0.0.1:8766/api/installs", true))
        assertFalse(InstallReporter.validEndpoint("http://example.com/api/installs", true))
    }

    @Test
    fun credentialsAndTrackingQueryRejected() {
        assertFalse(InstallReporter.validEndpoint("https://user:password@example.com/api/installs", false))
        assertFalse(InstallReporter.validEndpoint("https://example.com/api/installs?phone=1", false))
        assertFalse(InstallReporter.validEndpoint("https://example.com/api/installs#fragment", false))
    }
}
