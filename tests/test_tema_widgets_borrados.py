"""Reporte 2026-11-11: cerrar «Capas de la hoja» o la vista previa y cambiar el tema daba
«Internal C++ object (GripSplitter) already deleted»: una lambda conectada a THEME_BUS seguía viva."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import shiboken6  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402


def _errores(monkeypatch):
    vistos = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: vistos.append(a[1]))
    monkeypatch.setattr(sys, "unraisablehook", lambda u: vistos.append(u.exc_value))
    return vistos


def test_cambiar_tema_con_widgets_ya_borrados(monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    from ui.comun.widgets import GripSplitter
    from ui.comun import rediseno
    vistos = _errores(monkeypatch)
    for _ in range(3):
        sp = GripSplitter()
        sp.addWidget(QtWidgets.QLabel("a"))
        sp.addWidget(QtWidgets.QLabel("b"))
        b = rediseno.boton_icono("cog", "Ajustes", lambda: None)
        shiboken6.delete(sp)
        shiboken6.delete(b)
    theme.THEME_BUS.changed.emit("light")
    theme.THEME_BUS.changed.emit("dark")
    assert vistos == []


def test_al_tema_llama_mientras_vive_y_se_desconecta_al_borrarse():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    w, llamadas = QtWidgets.QWidget(), []
    theme.al_tema(w, lambda n: llamadas.append(n))
    theme.THEME_BUS.changed.emit("light")
    shiboken6.delete(w)
    theme.THEME_BUS.changed.emit("dark")
    theme.THEME_BUS.changed.emit("light")
    assert llamadas == ["light"]
