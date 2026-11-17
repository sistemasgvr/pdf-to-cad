"""Panel derecho: «Propiedades | Asistente» siempre a la vista (pedido del usuario 2026-11-14: «con la ventana del
asistente necesito una forma más fácil de navegar hacia las propiedades, o que se navegue solito al seleccionar un
elemento»).

Lo que recomiendan las pautas de diseño para un inspector:
- El MODO se ve y se cambia con un clic: en la cabecera del panel (la fija y la del panel que se oculta solo) el
  título pasa a ser un segmentado «Propiedades | Asistente» (los mismos `mostrar_asistente` de siempre).
- Propiedades SIGUE a la selección del usuario: el clic en el plano y en las listas ya lo hacía
  (`ver_propiedades`); ahora también elegir con el teclado en una lista del Inventario. Una selección que no hizo el
  usuario (el enlace de un conflicto en el chat, «ir a» de Resolver) no cambia de página: la conversación sigue.
El título de la cabecera sigue existiendo (oculto) y `_titulo_panel_der` lo mantiene al día, como antes.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from traduccion.i18n import bind as _bind

PROPIEDADES, ASISTENTE = 0, 1


class _BotonModo(QtWidgets.QPushButton):
    """Botón del segmentado: baja hasta lo que mide su texto (en el idioma de ahora), nunca cortado."""

    def minimumSizeHint(self):                           # noqa: N802
        h = super().minimumSizeHint().height()
        return QtCore.QSize(self.fontMetrics().horizontalAdvance(self.text()) + 24, h)


def _segmentado(win):
    f = QtWidgets.QFrame()
    f.setObjectName("segmentado")
    f.setProperty("rol", "modos_panel_der")
    lay = QtWidgets.QHBoxLayout(f)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    grupo = QtWidgets.QButtonGroup(f)
    botones = []
    for i, (clave, ayuda) in enumerate((("Propiedades", "Ver las propiedades de lo elegido"),
                                        ("Asistente", "Chat, conflictos y Civil 3D con la IA"))):
        b = _BotonModo()
        _bind(b, "setText", clave)
        _bind(b, "setToolTip", ayuda)
        b.setProperty("kind", "seg")
        b.setCheckable(True)
        b.setAutoDefault(False)
        grupo.addButton(b, i)
        lay.addWidget(b)
        botones.append(b)
    grupo.idClicked.connect(lambda i: win.mostrar_asistente(i == ASISTENTE))
    # compactos: el «seg» del tema trae un mínimo de ~150–180 px por botón y el panel no bajaría de 386 px; cada uno
    # baja hasta lo que mide su texto (`_BotonModo`)
    f.setStyleSheet("QPushButton { padding: 3px 10px; }")
    f.botones = botones
    return f


def poner(win):
    """Segmentado en las dos cabeceras del panel derecho (llamar tras crear `panel_der`)."""
    panel = getattr(win, "panel_der", None)
    if panel is None:
        return
    win._modos_der = []
    for cab in (panel.dock_header, panel.overlay_header):
        lay = cab.layout()
        lbl = cab.findChild(QtWidgets.QLabel, "panelHeaderTitle")
        seg = _segmentado(win)
        if lbl is not None:
            lbl.hide()
            lay.insertWidget(max(0, lay.indexOf(lbl)), seg)
        else:
            lay.insertWidget(0, seg)
        lay.insertStretch(lay.indexOf(seg) + 1, 1)
        win._modos_der.append(seg)
    sincronizar(win)


def sincronizar(win):
    """Marca el modo a la vista (lo llama `_titulo_panel_der`, o sea cada `mostrar_asistente`)."""
    pila = getattr(win, "pila_derecha", None)
    i = pila.currentIndex() if pila is not None else PROPIEDADES
    for seg in getattr(win, "_modos_der", ()):
        b = seg.botones[i]
        if not b.isChecked():
            b.blockSignals(True)
            b.setChecked(True)
            b.blockSignals(False)


def seguir_teclado(win, listas):
    """Elegir con el teclado en una lista del Inventario también muestra Propiedades (el clic ya lo hacía). Solo con
    la lista enfocada: un cambio hecho por código (el chat, «ir a») no saca al usuario del Asistente."""
    for lista in listas:
        lista.currentRowChanged.connect(lambda _f, l=lista: l.window().focusWidget() is l and win.ver_propiedades())
