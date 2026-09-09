"""Pruebas del módulo de iconos SVG."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui, QtWidgets

import icons


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_icon_returns_qicon_for_known_name():
    _app()
    ic = icons.icon("mdi:pencil-outline")
    assert isinstance(ic, QtGui.QIcon)
    assert not ic.pixmap(24, 24).isNull()


def test_icon_fallback_for_missing_name():
    _app()
    ic = icons.icon("mdi:this-does-not-exist-xyz")
    assert isinstance(ic, QtGui.QIcon)   # devuelve fallback, no lanza


def test_icon_tinting_changes_pixmap():
    _app()
    a = icons.icon("mdi:pencil-outline", color="#ff0000").pixmap(24, 24).toImage()
    b = icons.icon("mdi:pencil-outline", color="#00ff00").pixmap(24, 24).toImage()
    # Al menos un pixel debe diferir → los colores realmente se aplicaron
    assert a != b


def test_resolve_path_defaults_to_mdi():
    p1 = icons._resolve_path("pencil-outline")
    p2 = icons._resolve_path("mdi:pencil-outline")
    assert p1 == p2
    assert p1.endswith(os.path.join("mdi", "pencil-outline.svg"))
