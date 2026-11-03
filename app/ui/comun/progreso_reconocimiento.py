"""Avance del reconocimiento en una tarjeta junto al lienzo, sin velo sobre la ventana.

Es una ventanita propia (como las de `ventana_flotantes`): un hijo encima del lienzo obligaría a
repintar su fondo en cada aviso. Mientras dura, la edición queda en pausa y el plano se puede acercar
y desplazar. Misma forma de uso que `busy.BusyOverlay` (`begin`, `step`, `end`).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import ia_estilo, theme


class ProgresoReconocimiento(QtWidgets.QFrame):
    def __init__(self, host):
        super().__init__(host, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                         | QtCore.Qt.WindowDoesNotAcceptFocus | QtCore.Qt.NoDropShadowWindowHint)
        self.host = host
        self.viewport = host.canvas.viewport()
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.active = False
        self._text = self._detail = ""
        self._cancel = None
        self._locked = []
        self._vigilados = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(5)
        self.title = QtWidgets.QLabel()
        layout.addWidget(self.title)
        self.detail_label = QtWidgets.QLabel()
        layout.addWidget(self.detail_label)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(5)
        layout.addWidget(self.bar)
        pie = QtWidgets.QHBoxLayout()                    # el texto a todo el ancho, las acciones debajo
        self.note = QtWidgets.QLabel()
        pie.addWidget(self.note, 1)
        self.cancel_button = QtWidgets.QPushButton()
        self.cancel_button.clicked.connect(self._cancelar)
        pie.addWidget(self.cancel_button)
        layout.addLayout(pie)
        self._timer = QtCore.QTimer(self, interval=150, timeout=self._colocar)
        self._traducir()
        ia_estilo.al_cambiar_tema(self, self._estilo)
        self.hide()

    def _traducir(self):
        """La tarjeta vive tanto como la ventana: el idioma pudo cambiar desde la última vez."""
        self.cancel_button.setText(_tr("Cancelar"))
        self.note.setText(_tr("Vista provisional"))

    def _estilo(self):
        t = theme.tokens()
        self.setStyleSheet(f"QFrame {{ background:{t.surface}; color:{t.text}; border:1px solid {t.border};"
                          " border-radius:8px; } QLabel { border:none; }"
                          f"QProgressBar {{ border:none; background:{t.border_soft}; }}"
                          f"QProgressBar::chunk {{ background:{t.accent}; }}")
        self.title.setStyleSheet("border:none;font-weight:600;")
        self.note.setStyleSheet(f"border:none;color:{t.text_muted};font-size:10px;")

    def begin(self, text, detail="", cancel=None, **kwargs):
        if self.active:
            self.end()
        self.active = True
        self._text, self._detail, self._cancel = text, detail, cancel
        self._traducir()
        self.cancel_button.setEnabled(cancel is not None)
        self.bar.setRange(0, 0)
        self._pausar_edicion()
        # Un filtro en Python ve cada movimiento del ratón y repintado del lienzo: solo mientras reconoce.
        self._vigilados = [w for w in (self.host, self.viewport, getattr(self.host, "_flot_barra_win", None))
                           if w is not None]
        for widget in self._vigilados:
            widget.installEventFilter(self)
        self._timer.start()
        self._colocar()

    def _pausar_edicion(self):
        host = self.host
        allowed = {getattr(host, n, None) for n in ("_act_zoom_in", "_act_zoom_out")}
        widgets = [getattr(host, n, None) for n in
                   ("panel_izq", "panel_der", "btn_capas", "btn_export", "_flot_sel", "_flot_mover",
                    "btn_scale", "btn_normas", "_riel", "campo_buscar", "btn_asistente")]
        widgets = [getattr(w, "content", w) for w in widgets]
        objects = [a for a in host.findChildren(QtGui.QAction) if a not in allowed]
        objects += host.findChildren(QtGui.QShortcut)
        objects += [w for w in widgets if w is not None]
        self._locked = [(obj, obj.isEnabled()) for obj in objects]
        for obj, _enabled in self._locked:
            obj.setEnabled(False)
        self._old_readonly = host.canvas._recognition_readonly
        host.canvas._recognition_readonly = True

    def text(self):
        return self._text

    def detail(self):
        return self._detail

    def step(self, text=None, detail=None, done=None, total=None, **kwargs):
        if not self.active:
            return
        if text is not None:
            self._text = text
        if detail is not None:
            self._detail = detail
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(max(0, min(1000, int(1000 * (done or 0) / total))))
        self._colocar()

    def _colocar(self):
        modal = QtWidgets.QApplication.activeModalWidget()
        visible = (self.active and self.host.isVisible() and not self.host.isMinimized()
                   and self.viewport.isVisible() and (modal is None or modal is self.host))
        if not visible:
            self.hide()
            return
        self.setFixedWidth(max(140, min(340, self.viewport.width() - 28)))
        util = self.width() - 26
        self.title.setText(self.title.fontMetrics().elidedText(self._text, QtCore.Qt.ElideRight, util))
        self.title.setToolTip(self._text)
        fm = self.detail_label.fontMetrics()
        self.detail_label.setText("\n".join(fm.elidedText(line, QtCore.Qt.ElideRight, util)
                                            for line in self._detail.splitlines()[-2:]))
        self.detail_label.setToolTip(self._detail)
        self.ensurePolished()
        self.layout().activate()
        self.adjustSize()
        point = self.viewport.mapToGlobal(QtCore.QPoint(0, 0))
        x = point.x() + max(0, self.viewport.width() - self.width() - 14)
        y = point.y() + max(0, self.viewport.height() - self.height() - 14)
        toolbar = getattr(self.host, "_flot_barra_win", None)
        if toolbar is not None and toolbar.isVisible():
            rect = toolbar.geometry()
            if rect.intersects(QtCore.QRect(x, y, self.width(), self.height())):
                y = max(point.y(), rect.top() - self.height() - 8)
        self.move(x, y)
        if not self.isVisible():
            self.show()

    def mostrar_cancelando(self):
        """Un clic o Esc bastan: desde aquí la tarjeta dice que se está cancelando."""
        self._cancel = None
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText(_tr("Cancelando…"))

    def _cancelar(self):
        fn = self._cancel
        if fn is None:
            return
        self.mostrar_cancelando()
        QtCore.QTimer.singleShot(0, self, fn)

    def end(self):
        if not self.active:
            return
        self.active = False
        self._timer.stop()
        for widget in self._vigilados:
            widget.removeEventFilter(self)
        self._vigilados = []
        self._cancel = None
        self.hide()
        self.host.canvas._recognition_readonly = self._old_readonly
        self.host.canvas._pan = False
        self.host.canvas.setCursor(QtCore.Qt.ArrowCursor)
        self.host.canvas.set_mode_cursor(self.host.mode)
        for obj, enabled in self._locked:
            try:
                obj.setEnabled(enabled)
            except RuntimeError:
                pass
        self._locked = []

    def eventFilter(self, obj, event):
        if obj is self.host and event.type() == QtCore.QEvent.Close:
            event.ignore()
            return True
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move, QtCore.QEvent.Show,
                            QtCore.QEvent.Hide, QtCore.QEvent.WindowStateChange):
            QtCore.QTimer.singleShot(0, self, self._colocar)
        return False
