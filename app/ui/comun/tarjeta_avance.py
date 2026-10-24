"""Avance de un trabajo largo que NO bloquea (pedido del usuario 2026-10-23: el Informe automático tapaba la
ventana con «Cargando…» y no dejaba seguir trabajando).

`TarjetaAvance` = una tarjeta chica abajo a la derecha de una ventana (título, etapa, barra y «Cancelar»); solo
ocupa su rectángulo: el resto de la ventana sigue usable. `CapaTarjetas` = la misma interfaz que la capa
«Cargando…» (`busy.BusyOverlay`: `begin`/`step`/`end`/`active`), así `barra_pesada.AvancePesado(capa=…)` la usa
sin cambios; y puede MOSTRAR la misma tarjeta en otra ventana a mitad del trabajo (`agregar`: la Vista 3D
mientras el informe toma sus capturas).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme

MARGEN = 16
ANCHO = 340


class TarjetaAvance(QtWidgets.QFrame):
    def __init__(self, host, cancel=None):
        super().__init__(host)
        self.host = host
        self.setObjectName("tarjetaAvance")
        tk = theme.tokens()
        self.setStyleSheet(
            f"QFrame#tarjetaAvance{{background:{tk.surface_alt}; border:1px solid {tk.border}; border-radius:8px;}}"
            f"QLabel{{background:transparent; color:{tk.text};}}"
            f"QLabel#detalle{{color:{tk.text_muted};}}")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        fila = QtWidgets.QHBoxLayout()
        self.lbl = QtWidgets.QLabel()
        self.lbl.setStyleSheet("font-weight:600;")
        self.lbl.setWordWrap(True)
        fila.addWidget(self.lbl, 1)
        self.btn = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn.setAutoDefault(False)
        self.btn.setVisible(cancel is not None)
        if cancel is not None:
            self.btn.clicked.connect(cancel)
        fila.addWidget(self.btn)
        lay.addLayout(fila)
        self.detalle = QtWidgets.QLabel()
        self.detalle.setObjectName("detalle")
        self.detalle.setWordWrap(True)
        lay.addWidget(self.detalle)
        self.barra = QtWidgets.QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        lay.addWidget(self.barra)
        self.setFixedWidth(ANCHO)
        host.installEventFilter(self)

    def poner(self, texto=None, detalle=None, hecho=None, total=None):
        if texto is not None:
            self.lbl.setText(texto)
        if detalle is not None:
            self.detalle.setText(detalle)
        if hecho is not None and total:
            self.barra.setValue(int(1000 * hecho / total))
        self._ubicar()

    def _ubicar(self):
        self.adjustSize()
        abajo = MARGEN
        sb = self.host.statusBar() if isinstance(self.host, QtWidgets.QMainWindow) else None
        if sb is not None and sb.isVisible():
            abajo += sb.height()
        self.move(max(0, self.host.width() - self.width() - MARGEN), max(0, self.host.height() - self.height() - abajo))
        self.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() == QtCore.QEvent.Resize:
            self._ubicar()
        return False

    def cerrar(self):
        self.host.removeEventFilter(self)
        self.hide()
        self.deleteLater()


class CapaTarjetas:
    """La tarjeta del trabajo en una o varias ventanas, con la interfaz de `busy.BusyOverlay`."""

    def __init__(self, host, cancel=None):
        self.cancel = cancel
        self.tarjetas = []
        self.active = False
        self._estado = {}
        self._hosts = [host]

    def begin(self, text, detail="", cancel=None, **_kw):
        self.active = True
        self._estado = {"texto": text, "detalle": detail}
        for h in self._hosts:
            self._crear(h)

    def _crear(self, host):
        t = TarjetaAvance(host, self.cancel)
        t.poner(self._estado.get("texto", ""), self._estado.get("detalle", ""), self._estado.get("hecho"),
                self._estado.get("total"))
        t.show()
        t._ubicar()
        self.tarjetas.append(t)

    def agregar(self, host):
        """Mostrar también la tarjeta en `host` (otra ventana)."""
        if host is None or any(t.host is host for t in self.tarjetas):
            return
        self._hosts.append(host)
        if self.active:
            self._crear(host)

    def step(self, text=None, detail=None, done=None, total=None, pump=False):
        if text is not None:
            self._estado["texto"] = text
        if detail is not None:
            self._estado["detalle"] = detail
        if done is not None and total:
            self._estado["hecho"], self._estado["total"] = done, total
        for t in self.tarjetas:
            t.poner(text, detail, done, total)

    def end(self):
        self.active = False
        for t in self.tarjetas:
            t.cerrar()
        self.tarjetas = []
