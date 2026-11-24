# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/PayNetApplication.kt and
# app/src/main/java/com/paynet/app/di/AppContainer.kt

"""PayNet Kivy application shell.

Composition root: AppContainer mirrors the Kotlin hand-wired DI graph —
constructed here, referenced by every screen/service. Screens are added
feature by feature per MIGRATION.md; the shell (window, theme, navigation)
is stable from phase 2 onward.
"""

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager

from paynet import theme


class AppContainer:
    """The manual, framework-free composition root (port of di/AppContainer).
    Process-scoped services are constructed and held here; everything else
    reaches them through the app instance."""

    def __init__(self):
        # Populated feature by feature (settings repository, session
        # manager, telephony coordinator, ...). See MIGRATION.md.
        pass


class HomeScreen(Screen):
    pass


class PayNetApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.container = AppContainer()

    def build(self):
        self.title = "PayNet"
        sm = ScreenManager()
        home = HomeScreen(name="home")
        home.add_widget(
            Label(
                text="PayNet",
                color=theme.WELCOME_TEXT,
            )
        )
        sm.add_widget(home)
        return sm
