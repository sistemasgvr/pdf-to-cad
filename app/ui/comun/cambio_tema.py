"""cambio_tema.py — aviso con barra de carga mientras se cambia entre modo claro y oscuro (pedido del usuario
2026-11-13: «parece que se bugeara al demorar mucho a veces el cambio de tema»; 2026-11-14: «tiene que ser un toast
con barra de carga como lo venimos haciendo siempre», no un recuadro en el medio de la pantalla).

Es la MISMA tarjeta que el avance de los trabajos largos (`tarjeta_avance.TarjetaAvance`: abajo a la derecha,
título en negrita, detalle y barra fina), pero como ventanita propia (Tool, sin marco ni foco): cambiar el tema es UNA
llamada de Qt en el hilo de la interfaz (paleta + hoja de estilo: Qt re-pule cientos de widgets) y `theme.apply_theme`
congela el repintado de las ventanas mientras tanto; una hija de la ventana quedaría congelada con ella
(`SIN_CONGELAR`). Por eso el aviso aparece ANTES: la barra avanza `ANTES_MS`, recién entonces se cambia el tema, la
barra llega al final y la tarjeta queda a la vista al menos `MINIMO_MS` en total (sin parpadeo si fue rápido).

    cambio_tema.cambiar(win, aplicar, texto)     # muestra el aviso, llama `aplicar()` y lo cierra
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme

ANTES_MS = 160          # la barra se ve avanzar antes de que Qt se ponga a cambiar el tema
MINIMO_MS = 450         # tiempo mínimo a la vista (no parpadea si el cambio fue instantáneo)
PASO_MS = 16            # ~60 cuadros por segundo
ANTES_HASTA = 450       # milésimas de la barra al terminar `ANTES_MS` (el resto lo marca el cambio en sí)
MARGEN = 16             # como `tarjeta_avance`
ANCHO = 340
SIN_CONGELAR = "pdfcad_sin_congelar"   # propiedad: `apply_theme` no le apaga el repintado
_VIVOS: set = set()     # avisos en curso (los guarda hasta que terminan)


class AvisoCambioTema(QtWidgets.QFrame):
    """Tarjeta abajo a la derecha de la ventana: título, detalle y barra de carga (como `TarjetaAvance`)."""

    def __init__(self, ventana: QtWidgets.QWidget, texto: str):
        super().__init__(None, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
                         | QtCore.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setProperty(SIN_CONGELAR, True)
        self.setObjectName("tarjetaAvance")
        self._ventana = ventana
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        self.lbl = QtWidgets.QLabel(texto, self)
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        self.detalle = QtWidgets.QLabel(_tr("Aplicando los colores a la ventana…"), self)
        self.detalle.setObjectName("detalle")
        self.detalle.setWordWrap(True)
        lay.addWidget(self.detalle)
        self.barra = QtWidgets.QProgressBar(self)
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        self.barra.setAccessibleName(_tr("Cargando…"))
        lay.addWidget(self.barra)
        self.setFixedWidth(ANCHO)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(PASO_MS)
        self._timer.timeout.connect(self._avanzar)
        self._estilo()

    def _estilo(self):
        tk = theme.tokens()
        self.setStyleSheet(
            f"QFrame#tarjetaAvance{{background:{tk.surface_alt}; border:1px solid {tk.border}; border-radius:8px;}}"
            f"QLabel{{background:transparent; color:{tk.text};}}"
            f"QLabel#detalle{{color:{tk.text_muted};}}")
        self.lbl.setStyleSheet("font-weight:600;")

    def _avanzar(self):
        """Avanza hasta `ANTES_HASTA` en `ANTES_MS` (el tema todavía no se aplicó)."""
        paso = max(1, int(ANTES_HASTA * PASO_MS / max(1, ANTES_MS)))
        self.barra.setValue(min(ANTES_HASTA, self.barra.value() + paso))
        if self.barra.value() >= ANTES_HASTA:
            self._timer.stop()

    def _ubicar(self):
        self.adjustSize()
        v = self._ventana
        if v is None:
            self.move(QtGui.QCursor.pos())
            return
        abajo = MARGEN
        sb = v.statusBar() if isinstance(v, QtWidgets.QMainWindow) else None
        if sb is not None and sb.isVisible():
            abajo += sb.height()
        esquina = v.mapToGlobal(QtCore.QPoint(v.width(), v.height()))
        self.move(esquina - QtCore.QPoint(self.width() + MARGEN, self.height() + abajo))

    def mostrar(self):
        self.barra.setValue(0)
        self._ubicar()
        self._timer.start()
        self.show()
        self.raise_()

    def listo(self):
        """El tema ya cambió: barra completa."""
        self._timer.stop()
        self.barra.setValue(1000)
        self.detalle.setText(_tr("Listo"))

    def terminar(self):
        self._timer.stop()
        self.hide()


def cambiar(ventana: QtWidgets.QWidget, aplicar, texto: str, al_terminar=None):
    """Muestra el aviso, llama `aplicar()` tras `ANTES_MS` y lo cierra cuando pasó `MINIMO_MS` desde que apareció.
    `al_terminar()` se llama al cerrarlo (p. ej. para volver a aceptar clics en el botón). Devuelve el aviso."""
    aviso = AvisoCambioTema(ventana, texto)
    _VIVOS.add(aviso)          # lo suelta Python al final (con WA_DeleteOnClose, Qt y Python lo borraban dos veces)
    reloj = QtCore.QElapsedTimer()
    reloj.start()
    aviso.mostrar()

    def _fin():
        aviso.terminar()
        if al_terminar is not None:
            al_terminar()
        # soltarlo FUERA de su propio temporizador (borrarlo dentro de su slot tumba Qt)
        QtCore.QTimer.singleShot(0, lambda: _VIVOS.discard(aviso))

    def _aplicar():
        try:
            aplicar()
        finally:
            aviso._estilo()              # con los colores del tema nuevo
            aviso.listo()
            QtCore.QTimer.singleShot(max(0, MINIMO_MS - reloj.elapsed()), aviso, _fin)

    QtCore.QTimer.singleShot(ANTES_MS, aviso, _aplicar)
    return aviso
