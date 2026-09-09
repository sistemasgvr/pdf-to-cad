"""Pruebas del sistema de tema (theme.py). No abre ventana."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import theme
from PySide6 import QtWidgets


def _app():
    # QApplication es singleton; en el runner de pytest reusamos si existe
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_theme_tokens_disjoint():
    # Los dos temas comparten estructura pero difieren en fondo/texto
    assert theme.DARK.name == "dark" and theme.LIGHT.name == "light"
    assert theme.DARK.window != theme.LIGHT.window
    assert theme.DARK.text != theme.LIGHT.text


def test_apply_theme_switches_tokens_and_signals():
    app = _app()
    events = []
    theme.THEME_BUS.changed.connect(lambda name: events.append(name))
    theme.apply_theme(app, "light")
    assert theme.tokens().name == "light"
    theme.apply_theme(app, "dark")
    assert theme.tokens().name == "dark"
    assert events[-2:] == ["light", "dark"]


def test_toggle_alternates():
    app = _app()
    theme.apply_theme(app, "dark")
    assert theme.toggle(app) == "light"
    assert theme.toggle(app) == "dark"


def test_build_stylesheet_has_no_unresolved_placeholders():
    import re
    css = theme.build_stylesheet(theme.LIGHT)
    # Regresión clásica: un `{token}` que quedó sin f-string aparecería como
    # el nombre literal del atributo — algo como `{t.accent}` o `{accent}`.
    unresolved = re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_.]*\}", css)
    assert unresolved == [], f"Placeholders sin resolver: {unresolved[:5]}"
    assert theme.LIGHT.accent in css and theme.LIGHT.text in css
