"""capas_popup.py — el desplegable «Capas» del editor, como el administrador de capas de AutoCAD.

Pedido del usuario 2026-10-26: los planos de cada utilidad (antes pestañas al pie del lienzo) y las
utilidades dibujadas se encienden y apagan como capas. Un `BotonCapas` en la barra de herramientas
abre un `PanelCapas` (ventana emergente que se queda abierta mientras se hace clic dentro) con una
fila por capa: bombilla (encendida/apagada), muestra de color, nombre y cuántas hay. Clic en la
bombilla o en la fila = encender/apagar; clic derecho = «Ver solo esta» / «Encender todas».

Sin estado propio: la ventana le da una función `estado()` → `Estado` y recibe lo que el usuario
pide por `al_cambiar(tipo, clave, encendida)`, `al_solo(tipo, clave)` y `al_todas()`; después de cada
cambio el panel vuelve a leer `estado()` (si algo no se pudo, queda como de verdad está).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme
from ui.comun.icons import icon as _icon
from ui.comun.ui_common import swatch_icon

UTILIDAD, PLANO = "utilidad", "plano"
BOMBILLA_ON = "#f2b705"            # la bombilla de AutoCAD (no se pinta en el lienzo: es un icono)


@dataclass
class Fila:
    tipo: str                      # UTILIDAD | PLANO
    clave: object                  # capa ("AGUA") o grupo (int)
    nombre: str
    encendida: bool
    color: Optional[QtGui.QColor] = None
    detalle: str = ""              # cifra o PDF a la derecha
    globo: str = ""


@dataclass
class Estado:
    utilidades: List[Fila] = field(default_factory=list)
    planos: List[Fila] = field(default_factory=list)

    def apagadas(self) -> int:
        return sum(1 for f in self.utilidades + self.planos if not f.encendida)


class _FilaCapa(QtWidgets.QFrame):
    """Bombilla + color + nombre + detalle. Clic (o Espacio) = encender/apagar."""
    conmutar = QtCore.Signal()
    menu = QtCore.Signal(QtCore.QPoint)

    def __init__(self, fila: Fila, parent=None):
        super().__init__(parent)
        self.fila = fila
        self.setObjectName("filaCapa")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(6, 3, 8, 3)
        h.setSpacing(8)
        self.btn = QtWidgets.QToolButton()
        self.btn.setAutoRaise(True)
        self.btn.setIconSize(QtCore.QSize(18, 18))
        self.btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn.clicked.connect(self.conmutar)
        h.addWidget(self.btn)
        self.muestra = QtWidgets.QLabel()
        if fila.color is not None:
            self.muestra.setPixmap(swatch_icon(fila.color, 12).pixmap(12, 12))
        else:
            self.muestra.setPixmap(_icon("mdi:file-document-outline", color=theme.tokens().text_muted).pixmap(14, 14))
        h.addWidget(self.muestra)
        self.lbl = QtWidgets.QLabel(fila.nombre)
        h.addWidget(self.lbl, 1)
        self.det = QtWidgets.QLabel(fila.detalle)
        self.det.setObjectName("hint")
        h.addWidget(self.det)
        if fila.globo:
            self.setToolTip(fila.globo)
        self.pintar()

    def pintar(self):
        tk = theme.tokens()
        on = self.fila.encendida
        self.btn.setIcon(_icon("mdi:lightbulb-on" if on else "mdi:lightbulb-outline",
                               color=BOMBILLA_ON if on else tk.text_disabled))
        self.btn.setToolTip(_tr("Apagar") if on else _tr("Encender"))
        self.lbl.setStyleSheet("" if on else f"color: {tk.text_disabled};")
        self.setAccessibleName(f"{self.fila.nombre}: " + (_tr("encendida") if on else _tr("apagada")))

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.conmutar.emit()
            e.accept()
            return
        super().mousePressEvent(e)

    def contextMenuEvent(self, e):
        self.menu.emit(e.globalPos())

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.conmutar.emit()
            return
        super().keyPressEvent(e)


class PanelCapas(QtWidgets.QFrame):
    """La ventana emergente con las filas. Se arma de nuevo tras cada cambio (son pocas filas)."""

    def __init__(self, estado: Callable[[], Estado], al_cambiar, al_solo, al_todas, parent=None):
        super().__init__(parent, QtCore.Qt.Popup)
        self.setObjectName("panelCapas")
        self._estado, self._al_cambiar, self._al_solo, self._al_todas = estado, al_cambiar, al_solo, al_todas
        self._v = QtWidgets.QVBoxLayout(self)
        self._v.setContentsMargins(6, 6, 6, 8)
        self._v.setSpacing(1)
        self.filas: List[_FilaCapa] = []
        tk = theme.tokens()
        self.setStyleSheet(
            f"#panelCapas {{ background: {tk.surface}; border: 1px solid {tk.border}; border-radius: 6px; }}"
            f"#filaCapa {{ border-radius: 4px; }}"
            f"#filaCapa:hover, #filaCapa:focus {{ background: {tk.surface_alt}; }}"
            f"QLabel#seccionCapas {{ color: {tk.text_muted}; font-weight: bold; padding: 8px 6px 2px 6px; }}")
        self.armar()

    def armar(self):
        while self._v.count():
            it = self._v.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self.filas = []
        est = self._estado()
        cab = QtWidgets.QHBoxLayout()
        titulo = QtWidgets.QLabel(_tr("Capas"))
        f = titulo.font(); f.setBold(True); f.setPointSizeF(f.pointSizeF() + 1); titulo.setFont(f)
        cab.addWidget(titulo, 1)
        btn = QtWidgets.QPushButton(_icon("mdi:lightbulb-on", color=BOMBILLA_ON), _tr("Encender todas"))
        btn.setProperty("soft", True)
        btn.setEnabled(est.apagadas() > 0)
        btn.clicked.connect(self._todas)
        cab.addWidget(btn)
        caja = QtWidgets.QWidget()
        caja.setLayout(cab)
        self._v.addWidget(caja)
        if not est.utilidades and not est.planos:
            vacio = QtWidgets.QLabel(_tr("Todavía no hay utilidades dibujadas."))
            vacio.setObjectName("hint")
            vacio.setContentsMargins(6, 6, 6, 6)
            self._v.addWidget(vacio)
        for titulo_sec, filas in ((_tr("UTILIDADES (lo dibujado)"), est.utilidades),
                                  (_tr("PLANOS DEL PDF (fondo)"), est.planos)):
            if not filas:
                continue
            sec = QtWidgets.QLabel(titulo_sec)
            sec.setObjectName("seccionCapas")
            self._v.addWidget(sec)
            for fila in filas:
                w = _FilaCapa(fila)
                w.conmutar.connect(lambda fila=fila: self._conmutar(fila))
                w.menu.connect(lambda pos, fila=fila: self._menu(fila, pos))
                self._v.addWidget(w)
                self.filas.append(w)
        self.adjustSize()

    def fila(self, tipo, clave) -> Optional[_FilaCapa]:
        return next((w for w in self.filas if w.fila.tipo == tipo and w.fila.clave == clave), None)

    def _despues(self):
        foco = self.focusWidget()
        clave = (foco.fila.tipo, foco.fila.clave) if isinstance(foco, _FilaCapa) else None
        self.armar()
        if clave is not None:
            w = self.fila(*clave)
            if w is not None:
                w.setFocus()

    def _conmutar(self, fila: Fila):
        self._al_cambiar(fila.tipo, fila.clave, not fila.encendida)
        self._despues()

    def _todas(self):
        self._al_todas()
        self._despues()

    def _menu(self, fila: Fila, pos):
        m = QtWidgets.QMenu(self)
        a = m.addAction(_tr("Ver solo esta"))
        a.triggered.connect(lambda: (self._al_solo(fila.tipo, fila.clave), self._despues()))
        b = m.addAction(_tr("Encender todas"))
        b.triggered.connect(self._todas)
        m.exec(pos)


class BotonCapas(QtWidgets.QToolButton):
    """«Capas ▾» de la barra: abre el panel debajo de sí."""

    def __init__(self, estado, al_cambiar, al_solo, al_todas, parent=None):
        super().__init__(parent)
        self._args = (estado, al_cambiar, al_solo, al_todas)
        self.panel: Optional[PanelCapas] = None
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.clicked.connect(self.abrir)
        self.resumen()

    def abrir(self):
        if self.panel is not None:
            self.panel.close()
            self.panel.deleteLater()
        self.panel = PanelCapas(*self._args, parent=self)
        self.panel.adjustSize()
        abajo = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        pantalla = (self.screen() or QtGui.QGuiApplication.primaryScreen()).availableGeometry()
        x = min(abajo.x(), pantalla.right() - self.panel.width())
        self.panel.move(max(pantalla.left(), x), abajo.y())
        self.panel.show()
        if self.panel.filas:
            self.panel.filas[0].setFocus()

    def resumen(self, apagadas: int = 0):
        """Texto e icono según cuántas capas hay apagadas (la barra se ve de un vistazo)."""
        self.setIcon(_icon("mdi:layers-outline"))
        self.setText((_tr("Capas") if not apagadas else _tr("Capas · {n} apagada(s)").format(n=apagadas)) + "  ▾")
        self.setToolTip(_tr("Capas: encender y apagar las utilidades dibujadas y los planos de fondo de cada "
                            "PDF, como en AutoCAD. Solo cambia lo que se ve: el DXF sale completo."))
