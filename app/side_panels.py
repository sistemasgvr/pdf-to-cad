"""Paneles laterales que se ocultan solos como una pestaña en el borde, igual que
las paletas de Civil 3D (pedido del usuario 2026-10-05).

Cada panel (QDockWidget de la ventana principal) lleva en su cabecera una
chincheta:
  - FIJADO (por defecto): el panel ocupa su franja como siempre.
  - OCULTAR AUTOMÁTICAMENTE: el panel se recoge en una pestaña vertical en su
    borde (izquierdo o derecho). Al pasar el ratón por la pestaña (o al hacer
    clic, o con Espacio/Enter si tiene el foco) se despliega ENCIMA del plano, con
    el mismo contenido; se vuelve a recoger al alejar el ratón o al hacer clic en
    el plano. No se recoge mientras hay un desplegable/menú o una ventana abierta,
    mientras se arrastra con el ratón, ni mientras se escribe en un campo del panel
    (ahí se recoge al hacer clic fuera). Su borde interior se arrastra para cambiar
    el ancho.
El estado y el ancho de cada panel se recuerdan entre sesiones.

El contenido (los mismos widgets) se mueve entre el dock y el panel desplegado:
ninguna otra parte de la app necesita saber en qué modo está.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import theme as _theme
from i18n import bind as _bind
from icons import icon as _icon

OPEN_DELAY_MS = 250          # pasar el ratón por la pestaña → se abre
CLOSE_DELAY_MS = 500         # ratón fuera del panel → se recoge
POLL_MS = 100
MIN_W = 300                  # mismo mínimo que los docks (fuente de 14 px)
TAB_W = 34


def _settings():
    """Preferencias de la app (las pruebas lo reemplazan para no tocar el registro)."""
    return QtCore.QSettings("pdf-to-cad", "app")


class SideTab(QtWidgets.QAbstractButton):
    """Pestaña vertical (icono + título girado) en el borde de la ventana."""

    hovered = QtCore.Signal(bool)

    def __init__(self, side, icon_name, parent=None):
        super().__init__(parent)
        self._side = side
        self._icon_name = icon_name
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.TabFocus)
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def _font(self):
        f = QtGui.QFont(self.font()); f.setBold(True)
        return f

    def sizeHint(self):                            # noqa: N802
        fm = QtGui.QFontMetrics(self._font())
        return QtCore.QSize(TAB_W, 14 + 20 + 10 + fm.horizontalAdvance(self.text()) + 16)

    def minimumSizeHint(self):                     # noqa: N802
        return self.sizeHint()

    def setText(self, text):                       # noqa: N802
        super().setText(text)
        self.setAccessibleName(text)
        self.updateGeometry()

    def enterEvent(self, e):                       # noqa: N802
        super().enterEvent(e)
        self.hovered.emit(True)

    def leaveEvent(self, e):                       # noqa: N802
        super().leaveEvent(e)
        self.hovered.emit(False)

    def paintEvent(self, _e):                      # noqa: N802
        t = _theme.tokens()
        activo = self.isChecked()
        hover = self.underMouse() or self.hasFocus()
        fondo = t.accent if activo else (t.accent_hover if hover else t.surface_alt)
        tinta = t.text_on_accent if (activo or hover) else t.text
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QtGui.QPen(QtGui.QColor(t.focus if (activo or hover) else t.border), 1.2))
        p.setBrush(QtGui.QColor(fondo))
        p.drawRoundedRect(r, 5, 5)
        pm = _icon(self._icon_name, color=tinta).pixmap(20, 20)
        p.drawPixmap(int((self.width() - 20) / 2), 12, pm)
        p.setFont(self._font())
        p.setPen(QtGui.QColor(tinta))
        fm = p.fontMetrics()
        cx = self.width() / 2.0
        if self._side == "left":                   # se lee de abajo arriba, mirando al panel
            p.translate(cx + fm.ascent() / 2.0 - 1, self.height() - 12)
            p.rotate(-90)
        else:                                      # se lee de arriba abajo
            p.translate(cx - fm.ascent() / 2.0 + 1, 12 + 20 + 10)
            p.rotate(90)
        p.drawText(0, 0, self.text())
        p.end()


class _Grip(QtWidgets.QWidget):
    """Borde interior del panel desplegado: se arrastra para cambiar el ancho."""

    def __init__(self, panel):
        super().__init__(panel.overlay)
        self._panel = panel
        self._x0 = None
        self._w0 = 0
        self.setCursor(QtCore.Qt.SizeHorCursor)
        self.setAttribute(QtCore.Qt.WA_Hover, True)

    def mousePressEvent(self, e):                  # noqa: N802
        if e.button() == QtCore.Qt.LeftButton:
            self._x0 = e.globalPosition().x()
            self._w0 = self._panel.overlay.width()

    def mouseMoveEvent(self, e):                   # noqa: N802
        if self._x0 is None:
            return
        dx = e.globalPosition().x() - self._x0
        nuevo = self._w0 + (dx if self._panel.side == "left" else -dx)
        self._panel.set_width(nuevo, guardar=False)

    def mouseReleaseEvent(self, e):                # noqa: N802
        if self._x0 is not None:
            self._x0 = None
            self._panel.set_width(self._panel.overlay.width(), guardar=True)

    def paintEvent(self, _e):                      # noqa: N802
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        color = t.accent if self.underMouse() or self._x0 is not None else t.border
        x = self.width() - 2 if self._panel.side == "left" else 1
        p.fillRect(QtCore.QRect(x, 0, 2, self.height()), QtGui.QColor(color))
        p.end()


class AutoHidePanel(QtCore.QObject):
    """Un panel lateral (QDockWidget) que puede ocultarse solo como pestaña."""

    toggled = QtCore.Signal(bool)                  # True = se oculta solo

    def __init__(self, win, dock, title_es, icon_name, side, key):
        super().__init__(win)
        self.win, self.dock, self.side, self.key = win, dock, side, key
        self._title_es = title_es
        self.content = dock.widget()
        self.autohide = False
        self._outside_ms = 0
        self.width = MIN_W                         # se repone el guardado en restore()
        area = QtCore.Qt.LeftDockWidgetArea if side == "left" else QtCore.Qt.RightDockWidgetArea
        # Cabecera del dock fijado: título + chincheta.
        self.dock_header, self.btn_pin_dock = self._header(fijado=True)
        dock.setTitleBarWidget(self.dock_header)
        # Tira del borde con la pestaña (oculta mientras el panel está fijado).
        self.tab_dock = QtWidgets.QDockWidget(win)
        self.tab_dock.setObjectName(f"panelTab_{key}")
        self.tab_dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.tab_dock.setTitleBarWidget(QtWidgets.QWidget())
        tira = QtWidgets.QWidget()
        tv = QtWidgets.QVBoxLayout(tira); tv.setContentsMargins(3, 6, 3, 6); tv.setSpacing(0)
        self.tab = SideTab(side, icon_name)
        _bind(self.tab, "setText", title_es)
        tv.addWidget(self.tab, 0, QtCore.Qt.AlignHCenter)
        tv.addStretch(1)
        self.tab_dock.setWidget(tira)
        self.tab_dock.setFixedWidth(TAB_W + 6)
        win.addDockWidget(area, self.tab_dock)
        self.tab_dock.hide()
        # Panel desplegado ENCIMA del plano (hijo de la ventana, fuera de los layouts).
        self.overlay = QtWidgets.QFrame(win)
        self.overlay.setObjectName("panelOverlay")
        self.overlay.hide()
        ov = QtWidgets.QVBoxLayout(self.overlay); ov.setContentsMargins(1, 1, 1, 1); ov.setSpacing(0)
        self.overlay_header, self.btn_pin_overlay = self._header(fijado=False)
        ov.addWidget(self.overlay_header)
        self._body = QtWidgets.QVBoxLayout(); self._body.setContentsMargins(0, 0, 0, 0)
        ov.addLayout(self._body, 1)
        self.grip = _Grip(self)
        # Tiempos de apertura/cierre.
        self._open_timer = QtCore.QTimer(self, singleShot=True, interval=OPEN_DELAY_MS)
        self._open_timer.timeout.connect(self.open)
        self._poll = QtCore.QTimer(self, interval=POLL_MS)
        self._poll.timeout.connect(self._check_close)
        self.tab.clicked.connect(self._tab_clicked)
        self.tab.hovered.connect(self._tab_hover)
        win.installEventFilter(self)
        _theme.THEME_BUS.changed.connect(lambda _n: self._retint())

    # ── cabeceras ──
    def _header(self, fijado):
        h = QtWidgets.QWidget()
        h.setObjectName("panelHeader")
        h.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QHBoxLayout(h); lay.setContentsMargins(10, 3, 4, 3); lay.setSpacing(4)
        lbl = QtWidgets.QLabel()
        lbl.setObjectName("panelHeaderTitle")
        _bind(lbl, "setText", self._title_es)
        btn = QtWidgets.QToolButton()
        btn.setObjectName("panelPin")
        btn.setAutoRaise(True)
        btn.setIconSize(QtCore.QSize(18, 18))
        btn.setFixedSize(32, 32)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setProperty("_pin_fijado", fijado)
        if fijado:
            _bind(btn, "setToolTip", "Ocultar automáticamente: el panel queda como una pestaña en el borde "
                                     "y se abre al pasar el ratón")
            _bind(btn, "setAccessibleName", "Ocultar automáticamente")
            btn.clicked.connect(lambda: self.set_autohide(True))
        else:
            _bind(btn, "setToolTip", "Fijar el panel (que no se oculte)")
            _bind(btn, "setAccessibleName", "Fijar el panel")
            btn.clicked.connect(lambda: self.set_autohide(False))
        btn.setIcon(_icon("mdi:pin" if fijado else "mdi:pin-outline"))
        lay.addWidget(lbl, 1)
        lay.addWidget(btn)
        return h, btn

    def _retint(self):
        self.btn_pin_dock.setIcon(_icon("mdi:pin"))
        self.btn_pin_overlay.setIcon(_icon("mdi:pin-outline"))
        self.tab.update()
        self.grip.update()

    # ── modos ──
    def restore(self):
        """Repone el estado y el ancho guardados (al abrir la app)."""
        try:
            s = _settings()
            ancho = int(s.value(f"panel_{self.key}_ancho", 0) or 0)
            auto = s.value(f"panel_{self.key}_auto", False, type=bool)
        except Exception:
            ancho, auto = 0, False
        if ancho:
            self.width = max(MIN_W, ancho)
        if auto:
            self.set_autohide(True, guardar=False)

    def set_autohide(self, on, guardar=True):
        on = bool(on)
        if on == self.autohide:
            return
        if on:
            if self.dock.isVisible() and self.dock.width() >= MIN_W:
                self.width = self.dock.width()
            self.dock.hide()
            self._body.addWidget(self.content)     # el dock suelta su contenido
            self.content.show()
            self.tab_dock.show()
            self.autohide = True
        else:
            self.close()
            self.dock.setWidget(self.content)
            self.tab_dock.hide()
            self.dock.show()
            self.win.resizeDocks([self.dock], [self.width], QtCore.Qt.Horizontal)
            self.autohide = False
        if guardar:
            self._save()
        self.toggled.emit(on)

    def set_width(self, w, guardar=True):
        self.width = int(max(MIN_W, min(w, self._max_width())))
        if self.overlay.isVisible():
            self._place()
        if guardar:
            self._save()

    def _max_width(self):
        return max(MIN_W, int(self.win.width() * 0.6))

    def _save(self):
        try:
            s = _settings()
            s.setValue(f"panel_{self.key}_auto", self.autohide)
            s.setValue(f"panel_{self.key}_ancho", int(self.width))
        except Exception:
            pass

    # ── desplegar / recoger ──
    def is_open(self):
        return self.overlay.isVisible()

    def open(self):
        self._open_timer.stop()
        if not self.autohide:
            return
        self._place()
        self.overlay.show()
        self.overlay.raise_()
        self.tab.setChecked(True)
        self._outside_ms = 0
        self._poll.start()
        QtWidgets.QApplication.instance().installEventFilter(self)

    def close(self):
        self._open_timer.stop()
        self._poll.stop()
        QtWidgets.QApplication.instance().removeEventFilter(self)
        if self.overlay.isVisible():
            self.overlay.hide()
        self.tab.setChecked(False)

    def _place(self):
        central = self.win.centralWidget()
        area = central.geometry() if central is not None else self.win.rect()
        w = int(max(MIN_W, min(self.width, self._max_width())))
        x = area.left() if self.side == "left" else area.right() - w + 1
        self.overlay.setGeometry(x, area.top(), w, area.height())
        gx = w - 8 if self.side == "left" else 0
        self.grip.setGeometry(gx, 0, 8, area.height())
        self.grip.raise_()

    def _tab_clicked(self):
        if self.overlay.isVisible():
            self.close()
        else:
            self.open()

    def _tab_hover(self, dentro):
        if dentro and self.autohide and not self.overlay.isVisible():
            self._open_timer.start()
        elif not dentro:
            self._open_timer.stop()

    @staticmethod
    def _contiene(w, pos_global):
        return w.isVisible() and w.rect().contains(w.mapFromGlobal(pos_global))

    def _check_close(self):
        app = QtWidgets.QApplication.instance()
        if (app.activePopupWidget() is not None or app.activeModalWidget() is not None
                or app.mouseButtons() != QtCore.Qt.NoButton):
            self._outside_ms = 0
            return
        pos = QtGui.QCursor.pos()
        if self._contiene(self.overlay, pos) or self._contiene(self.tab, pos):
            self._outside_ms = 0
            return
        foco = app.focusWidget()
        if (foco is not None and self.overlay.isAncestorOf(foco)
                and isinstance(foco, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                      QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit))):
            self._outside_ms = 0                   # escribiendo: se recoge al hacer clic fuera
            return
        self._outside_ms += POLL_MS
        if self._outside_ms >= CLOSE_DELAY_MS:
            self.close()

    def eventFilter(self, obj, ev):                # noqa: N802
        et = ev.type()
        if et == QtCore.QEvent.MouseButtonPress and self.overlay.isVisible():
            app = QtWidgets.QApplication.instance()
            if app.activePopupWidget() is None and app.activeModalWidget() is None:
                try:
                    pos = ev.globalPosition().toPoint()
                except AttributeError:
                    return False
                if not (self._contiene(self.overlay, pos) or self._contiene(self.tab, pos)):
                    QtCore.QTimer.singleShot(0, self.close)    # el clic sigue su curso (p.ej. al plano)
        elif obj is self.win and et == QtCore.QEvent.Resize and self.overlay.isVisible():
            self._place()
        return False
