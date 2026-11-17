"""Propiedades sin nada elegido (pedido del usuario 2026-11-13: con nada seleccionado el panel mostraba igual
«Cambiar tipo», «Editar/mover», «Ver datos extendidos» y «Eliminar», que no tienen sobre qué actuar).

Con nada elegido en la sección del Inventario que está a la vista, el panel muestra un estado vacío (icono, «Nada
seleccionado» y cómo elegir algo) y oculta esos botones y los grupos de propiedades con campos vacíos. Solo cambia
QUÉ se ve: los botones, sus funciones y la selección son los de siempre. Secciones con su propio panel (accesorios,
bancoductos) o sin selección conocida quedan como antes (`hay_seleccion` → None); superficies: la fila elegida.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from nucleo.model import TAB_BZ, TAB_CL, TAB_CURVE, TAB_LEADER, TAB_PIPE, TAB_REGION, TAB_SUP, TAB_TEXT
from traduccion.i18n import bind as _bind
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon

# sección del Inventario → índice de lo elegido en la ventana
_SELECCION = {TAB_PIPE: "sel_pipe", TAB_LEADER: "sel_leader", TAB_TEXT: "sel_text", TAB_REGION: "sel_region",
              TAB_BZ: "sel_bz", TAB_CURVE: "sel_curve", TAB_CL: "sel_cl"}
# se mostraban con los campos vacíos sin nada elegido («Cotas por tramo»: con los tramos de la utilidad que se
# eligió antes, reporte 2026-11-14)
_GRUPOS = ("gprop_bz", "gprop_curve", "gprop_cl", "gprop_segs")
_BOTONES = ("btn_ct", "btn_mv", "btn_edit", "btn_xd", "btn_del")


def poner(win, layout):
    """El estado vacío, arriba del panel de propiedades (oculto hasta que haga falta)."""
    caja = QtWidgets.QFrame()
    caja.setObjectName("propiedadesVacio")
    v = QtWidgets.QVBoxLayout(caja)
    v.setContentsMargins(16, 28, 16, 28)
    v.setSpacing(8)
    win._vacio_ico = QtWidgets.QLabel()
    win._vacio_ico.setAlignment(QtCore.Qt.AlignCenter)
    tit = _bind(QtWidgets.QLabel(), "setText", "Nada seleccionado")
    tit.setProperty("rol", "h3")
    tit.setAlignment(QtCore.Qt.AlignCenter)
    det = _bind(QtWidgets.QLabel(), "setText", "Haz clic en una utilidad, un buzón o una curva del plano, o elígela "
                                               "en el Inventario, para ver y editar sus propiedades.")
    det.setProperty("rol", "t3")
    det.setWordWrap(True)
    det.setAlignment(QtCore.Qt.AlignCenter)
    for w in (win._vacio_ico, tit, det):
        v.addWidget(w)
    caja.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)   # compacto, arriba
    caja.hide()
    layout.insertWidget(0, caja)
    win.vacio_propiedades = caja
    _theme.al_tema(caja, lambda _n: _estilo(win))
    _estilo(win)
    return caja


def _estilo(win):
    tk = _theme.tokens()
    win._vacio_ico.setPixmap(_icon("mdi:cursor-default-outline", color=tk.text_muted).pixmap(36, 36))


def hay_seleccion(win):
    """True/False si se sabe si hay algo elegido en la sección a la vista; None si esa sección no aplica."""
    if win._current_tab() == TAB_SUP and hasattr(win, "_sup_elegida"):   # superficies (2026-11-14)
        return win._sup_elegida() >= 0
    attr = _SELECCION.get(win._current_tab())
    if attr is None:
        return None
    if getattr(win, attr, -1) is not None and getattr(win, attr, -1) >= 0:
        return True
    if attr == "sel_pipe" and hasattr(win, "_selected_pipe_rows"):
        try:
            return bool(win._selected_pipe_rows())
        except Exception:                                   # noqa: BLE001
            return False
    return False


def sincronizar(win):
    """Al final de `_update_ui`: con nada elegido, el estado vacío en lugar de botones y campos vacíos."""
    caja = getattr(win, "vacio_propiedades", None)
    if caja is None:
        return
    vacio = hay_seleccion(win) is False
    if vacio:
        for nombre in _BOTONES + _GRUPOS:
            w = getattr(win, nombre, None)
            if w is not None:
                w.setVisible(False)
    caja.setVisible(vacio)
