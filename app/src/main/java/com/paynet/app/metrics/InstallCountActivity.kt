// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.metrics

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.lifecycleScope
import com.paynet.app.MainActivity
import com.paynet.app.R
import com.paynet.app.ui.theme.PayNetAccentProvider
import com.paynet.app.ui.theme.PayNetTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class InstallCountActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PayNetAccentProvider {
                PayNetTheme {
                    var saving by remember { mutableStateOf(false) }
                    Surface(Modifier.fillMaxSize()) {
                        Column(
                            Modifier
                                .fillMaxSize()
                                .systemBarsPadding()
                                .verticalScroll(rememberScrollState())
                                .padding(28.dp),
                            verticalArrangement = Arrangement.Center,
                            horizontalAlignment = Alignment.Start
                        ) {
                            Text(
                                stringResource(R.string.install_count_title),
                                fontSize = 34.sp,
                                lineHeight = 38.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                            Spacer(Modifier.height(20.dp))
                            Text(stringResource(R.string.install_count_body), lineHeight = 24.sp)
                            Spacer(Modifier.height(30.dp))
                            Button(
                                onClick = {
                                    saving = true
                                    save(true)
                                },
                                enabled = !saving
                            ) {
                                Text(stringResource(R.string.install_count_allow))
                            }
                            TextButton(
                                onClick = {
                                    saving = true
                                    save(false)
                                },
                                enabled = !saving
                            ) {
                                Text(stringResource(R.string.install_count_decline))
                            }
                        }
                    }
                }
            }
        }
    }

    private fun save(allow: Boolean) {
        lifecycleScope.launch {
            withContext(Dispatchers.IO) { InstallReporter.choose(applicationContext, allow) }
            if (!intent.getBooleanExtra("from_settings", false)) {
                startActivity(Intent(this@InstallCountActivity, MainActivity::class.java))
            }
            finish()
        }
    }
}
