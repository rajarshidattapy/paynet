// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.activities

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.flowpay.app.R
import com.flowpay.app.ui.theme.FlowpayAccentProvider
import com.flowpay.app.ui.theme.FlowpayTheme

/** Bundled policy; no browser, network access or tracking is needed to read it. */
class PrivacyActivity : ComponentActivity() {
    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            FlowpayAccentProvider {
                FlowpayTheme {
                    Scaffold(
                        topBar = {
                            TopAppBar(
                                title = { Text(stringResource(R.string.privacy_title)) },
                                navigationIcon = {
                                    IconButton(onClick = { finish() }) {
                                        Icon(
                                            Icons.AutoMirrored.Filled.ArrowBack,
                                            stringResource(R.string.settings_back)
                                        )
                                    }
                                }
                            )
                        }
                    ) { insets ->
                        Column(
                            Modifier.fillMaxSize().padding(insets)
                                .verticalScroll(rememberScrollState()).padding(24.dp)
                        ) {
                            Text(stringResource(R.string.privacy_body), fontSize = 16.sp, lineHeight = 24.sp)
                        }
                    }
                }
            }
        }
    }
}
