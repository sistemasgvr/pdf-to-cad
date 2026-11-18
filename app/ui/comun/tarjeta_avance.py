"""Avance de un trabajo largo que NO bloquea (pedido del usuario 2026-10-23: el Informe automático tapaba la
ventana con «Cargando…» y no dejaba seguir trabajando).

`TarjetaAvance` = una tarjeta chica abajo a la derecha de una ventana (título, etapa, barra y «Cancelar»); solo
ocupa su rectángulo: el resto de la ventana sigue usable. `CapaTarjetas` = la misma interfaz que la capa
«Cargando…» (`busy.BusyOverlay`: `begin`/`step`/`end`/`active`), así `barra_pesada.AvancePesado(capa=…)` la usa
sin cambios; y puede MOSTRAR la misma tarjeta en otra ventana a mitad del trabajo (`agregar`: la Vista 3D
mientras el informe toma sus capturas).

La barra va SIEMPRE de 0 a 100 % con su cifra (reporte 2026-11-17, «Interpretando la hoja…» sin avance): con
`modelo=True` la pone quien llama (`barra_pesada`); si no, se reparte con lo que duró cada etapa la vez anterior
y el «i de n» de cada aviso (`nucleo/avance_aprendido`, como la capa «Cargando…»). `al_avance(texto, detalle,
fraccion)` = alguien más muestra el mismo avance (el panel Reconocer).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import centro_avisos, theme

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
        fila_b = QtWidgets.QHBoxLayout()
        fila_b.setSpacing(8)
        fila_b.addWidget(self.barra, 1)
        self.pct = QtWidgets.QLabel("0 %")
        self.pct.setObjectName("detalle")
        self.pct.setMinimumWidth(40)
        self.pct.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        fila_b.addWidget(self.pct)
        lay.addLayout(fila_b)
        self.setFixedWidth(ANCHO)
        centro_avisos.centro(host).agregar(self, centro_avisos.CARGA)

    def poner(self, texto=None, detalle=None, hecho=None, total=None):
        if texto is not None:
            self.lbl.setText(texto)
        if detalle is not None:
            self.detalle.setText(detalle)
        if hecho is not None and total:
            self.poner_fraccion(hecho / total)
        self._ubicar()

    def poner_fraccion(self, frac: float, medida: str = "cuenta"):
        """`medida` (`avance_aprendido.Seguidor.medida`): fuera de «cuenta» la cifra es una estimación: «≈ 42 %»."""
        from ui.comun.busy import cifra
        frac = max(0.0, min(1.0, float(frac)))
        self.barra.setValue(int(1000 * frac))
        self.pct.setText(cifra(frac, medida))

    def _ubicar(self):
        """La ubica el centro de avisos (`centro_avisos`: apilada con las demás, sobre el plano)."""
        centro_avisos.centro(self.host).colocar()

    def cerrar(self):
        self.hide()
        centro_avisos.centro(self.host).quitar(self)
        self.deleteLater()


class CapaTarjetas:
    """La tarjeta del trabajo en una o varias ventanas, con la interfaz de `busy.BusyOverlay`."""

    REFRESCO_MS = 150

    def __init__(self, host, cancel=None, al_avance=None):
        self.cancel = cancel
        self.al_avance = al_avance
        self.tarjetas = []
        self.active = False
        self._estado = {}
        self._hosts = [host]
        self._seg = None
        self._timer = None

    def begin(self, text, detail="", cancel=None, modelo=False, **_kw):
        self.active = True
        self._estado = {"texto": text, "detalle": detail}
        if not modelo:
            from ui.comun import tiempos_carga
            self._seg = tiempos_carga.seguidor(text)
            self._timer = QtCore.QTimer(self._hosts[0])
            self._timer.setInterval(self.REFRESCO_MS)
            self._timer.timeout.connect(self._refrescar)
            self._timer.start()
        for h in self._hosts:
            self._crear(h)
        self._refrescar()

    def fraccion(self) -> float:
        """Cuánto va, de 0 a 1."""
        if self._seg is not None:
            return self._seg.fraccion()
        e = self._estado
        return float(e["hecho"]) / float(e["total"]) if e.get("total") else 0.0

    def medida(self) -> str:
        """"cuenta" (real) o una estimación ("perfil"/"tiempo"): ver `avance_aprendido`."""
        if self._seg is not None:
            return self._seg.medida()
        e = self._estado
        return "cuenta" if e.get("total") and not e.get("estimado") else "tiempo"

    def _refrescar(self):
        if not self.active:
            return
        f = self.fraccion()
        m = self.medida()
        for t in self.tarjetas:
            t.poner_fraccion(f, m)
            t._ubicar()                    # un panel que se despliega o se recoge mueve el lugar libre
        if self.al_avance is not None:
            self.al_avance(self._estado.get("texto", ""), self._estado.get("detalle", ""), f)

    def _crear(self, host):
        t = TarjetaAvance(host, self.cancel)
        t.poner(self._estado.get("texto", ""), self._estado.get("detalle", ""))
        t.poner_fraccion(self.fraccion(), self.medida())
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

    def step(self, text=None, detail=None, done=None, total=None, pump=False, clave=None, estimado=None):
        if estimado is not None:
            self._estado["estimado"] = bool(estimado)
        if text is not None:
            self._estado["texto"] = text
        if detail is not None:
            self._estado["detalle"] = detail
        if done is not None and total:
            self._estado["hecho"], self._estado["total"] = done, total
        if self._seg is not None and (text is not None or detail is not None or total):
            e = self._estado
            self._seg.etapa(e.get("texto", "") + (" · " + e["detalle"] if e.get("detalle") else ""),
                            done if total else None, total, clave=clave)
        for t in self.tarjetas:
            t.poner(text, detail)
        self._refrescar()

    def end(self, guardar=True):
        """`guardar=False` (cancelado): lo que duró no sirve de ejemplo para la próxima vez."""
        self.active = False
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        seg, self._seg = self._seg, None
        if seg is not None and guardar:
            from ui.comun import tiempos_carga
            tiempos_carga.guardar(seg)
        for t in self.tarjetas:
            t.cerrar()
        self.tarjetas = []
