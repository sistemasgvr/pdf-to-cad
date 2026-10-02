"""widgets.py — Widgets Qt reutilizables y autocontenidos de la UI.

Piezas pequeñas que no dependen de la ventana principal (solo de PySide6):
- InlineEdit: editor de texto embebido (Enter aplica, Shift+Enter salto de línea).
- _SegInvSpinBox: spinbox de la tabla "Cotas por tramo" (Enter confirma en celda).
- _NoWheelFilter: filtro global que bloquea la rueda sobre spinboxes/combos.
- ZoomPanView: QGraphicsView de solo lectura con zoom (rueda) y pan (botón
  central). La usan las vistas previas del asistente (capas de la hoja y
  reconocimiento). Movida verbatim desde recognition_dialog._PreviewView.

Extraído de app_window.py sin cambios de comportamiento (solo reubicación).
"""
from PySide6 import QtCore, QtGui, QtWidgets

import theme as _theme
from i18n import t as _tr


class InlineEdit(QtWidgets.QTextEdit):
    """Editor embebido. Enter = aplicar; Ctrl+Shift+Enter o Shift+Enter = salto de
    línea. El commit se difiere con un timer para no destruir el widget dentro de
    su propio evento (eso provocaba cierres inesperados)."""
    committed = QtCore.Signal(str)

    def __init__(self, text):
        super().__init__(); self.setPlainText(text); self._done = False
        self._apply_theme()
        _theme.THEME_BUS.changed.connect(self._apply_theme)

    def _apply_theme(self, *_):
        t = _theme.tokens()
        self.setStyleSheet(f"background:{t.input_bg};color:{t.success};"
                           f"border:2px solid {t.focus};border-radius:3px;")

    def _commit(self):
        if not self._done:
            self._done = True; txt = self.toPlainText()
            QtCore.QTimer.singleShot(0, lambda: self.committed.emit(txt))

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            m = e.modifiers()
            if (m & QtCore.Qt.ShiftModifier):     # Shift(+Ctrl)+Enter → salto de línea
                self.insertPlainText("\n"); return
            self._commit(); return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e); self._commit()


class _SegInvSpinBox(QtWidgets.QDoubleSpinBox):
    """QDoubleSpinBox de la tabla "Cotas por tramo": Enter/Return confirma el
    valor tecleado ahí mismo. Embebido en una celda de QTableWidget (vía
    setCellWidget), el widget contenedor puede quedarse con la tecla Enter
    antes de que dispare editingFinished normalmente — se maneja acá a mano
    para no depender de esa cadena de eventos."""
    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.interpretText()
            event.accept()
            # Diferido: el slot conectado reconstruye la tabla (destruye este
            # mismo spinbox) — no hacerlo en medio de este keyPressEvent.
            QtCore.QTimer.singleShot(0, self.editingFinished.emit)
            return
        super().keyPressEvent(event)


class _NoWheelFilter(QtCore.QObject):
    """Bloquea la rueda del ratón sobre QSpinBox / QDoubleSpinBox / QComboBox
    (y sus derivados). Motivo: al desplazarse por un panel con la rueda,
    quedar el puntero sobre uno de esos campos incrementa/decrementa el valor
    o cambia el item del combo sin querer — el usuario perdía datos ya
    introducidos por un gesto que solo pretendía mover la vista.

    Se instala una sola vez sobre la QApplication y cubre TODOS los widgets
    existentes y futuros, sin tener que subclasificarlos uno por uno. El
    evento wheel se ignora en esos widgets (así lo hereda el padre y sigue
    desplazando el panel); en el resto de widgets pasa tal cual.
    """
    _WHEEL_BLOCKED = (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox)

    def eventFilter(self, obj, ev):
        if (ev.type() == QtCore.QEvent.Wheel
                and isinstance(obj, self._WHEEL_BLOCKED)):
            ev.ignore()
            return True
        return False


class ZoomPanView(QtWidgets.QGraphicsView):
    """Vista previa con zoom (rueda) y pan (botón central). Sin edición."""
    viewChanged = QtCore.Signal()
    def __init__(self):
        super().__init__()
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHints(
            QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self._pan = False
        self._pan0 = None

    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)
        self.viewChanged.emit()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.viewChanged.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.viewChanged.emit()

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = True
            self._pan0 = e.position().toPoint()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan and self._pan0 is not None:
            d = e.position().toPoint() - self._pan0
            self._pan0 = e.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - d.y())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = False
            self._pan0 = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)


class MiniMap(QtWidgets.QWidget):
    """Minimapa en la esquina inferior izquierda de una `ZoomPanView`: miniatura
    de la hoja mostrada con un recuadro de lo que se ve en pantalla. Clic o
    arrastre en el mapa centra la vista ahí. `set_thumbnail(pixmap, scene_rect)`
    lo alimenta (la miniatura se reescala sola); `viewChanged` lo redibuja."""
    MARGIN = 10
    MAX_W, MAX_H = 150, 110       # pequeño: en pantallas chicas no puede robar sitio a la vista

    def __init__(self, view, sync_zoom=False):
        super().__init__(view.viewport())
        self.view = view
        self._sync_zoom = sync_zoom
        self._thumb = None            # QPixmap ya escalado al tamaño del widget
        self._src = None              # QPixmap original
        self._layout = None           # [(QRectF escena, etiqueta)] en modo esquema
        self._scene_rect = QtCore.QRectF()
        self._full_scene_rect = QtCore.QRectF()
        self._zoom = 1.0
        self._dragging = False
        self.setCursor(QtCore.Qt.PointingHandCursor)
        if sync_zoom:
            self.setToolTip(_tr("Zoom sincronizado con la vista · clic o arrastre: navegar · doble clic: ver todas las hojas"))
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        view.viewChanged.connect(self._on_view_changed)
        view.viewport().installEventFilter(self)
        self.hide()

    def set_thumbnail(self, pixmap, scene_rect):
        """Modo imagen: `pixmap` es toda la hoja; `scene_rect` su rect en la escena."""
        self._layout = None
        self._src = pixmap
        self._set_extent(scene_rect)
        if pixmap is None or pixmap.isNull() or self._scene_rect.isEmpty():
            self.hide(); return
        scale = min(self.MAX_W / pixmap.width(), self.MAX_H / pixmap.height())
        w, h = max(1, int(pixmap.width() * scale)), max(1, int(pixmap.height() * scale))
        self._thumb = pixmap.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self._fit_and_show(self._thumb.width(), self._thumb.height())

    def set_layout(self, items, scene_rect):
        """Modo esquema: `items` = [(QRectF en escena, etiqueta), …] — cómo están
        organizadas las hojas (posición relativa y número), sin el dibujo."""
        self._thumb = None
        self._src = None
        self._layout = [(QtCore.QRectF(r), str(label)) for r, label in items]
        self._set_extent(scene_rect)
        if not self._layout or self._scene_rect.isEmpty():
            self.hide(); return
        scale = min(self.MAX_W / self._full_scene_rect.width(), self.MAX_H / self._full_scene_rect.height())
        self._fit_and_show(max(1, int(self._full_scene_rect.width() * scale)),
                           max(1, int(self._full_scene_rect.height() * scale)))

    def _set_extent(self, scene_rect):
        self._full_scene_rect = QtCore.QRectF(scene_rect)
        if self._full_scene_rect.isEmpty():
            self._zoom = 1.0
            self._scene_rect = QtCore.QRectF(self._full_scene_rect)
            return
        self._sync_zoom_to_view()

    def _sync_zoom_to_view(self):
        full = self._full_scene_rect
        if full.isEmpty():
            return
        if not self._sync_zoom:
            self._zoom = 1.0
            self._scene_rect = QtCore.QRectF(full)
            return
        viewport = self.view.viewport()
        fit_scale = min(max(1, viewport.width())/full.width(), max(1, viewport.height())/full.height())
        transform = self.view.transform()
        scale = (transform.m11()**2 + transform.m12()**2)**0.5
        self._zoom = max(1.0, min(256.0, scale/fit_scale))
        self._set_zoom_rect(self.view.mapToScene(viewport.rect().center()))

    def _set_zoom_rect(self, center):
        full = self._full_scene_rect
        w, h = full.width()/self._zoom, full.height()/self._zoom
        x = max(full.left(), min(full.right()-w, center.x()-w/2))
        y = max(full.top(), min(full.bottom()-h, center.y()-h/2))
        self._scene_rect = QtCore.QRectF(x, y, w, h)

    def wheelEvent(self, event):
        viewport = self.view.viewport()
        position = viewport.rect().center()
        forwarded = QtGui.QWheelEvent(QtCore.QPointF(position), QtCore.QPointF(viewport.mapToGlobal(position)),
            event.pixelDelta(), event.angleDelta(), event.buttons(), event.modifiers(),
            event.phase(), event.inverted())
        self.view.wheelEvent(forwarded)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._dragging = False
            if hasattr(self.view, "fit_all"):
                self.view.fit_all()
            else:
                self.view.fitInView(self._full_scene_rect, QtCore.Qt.KeepAspectRatio)
                self.view.viewChanged.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _fit_and_show(self, w, h):
        self._map_w, self._map_h = w, h
        self.setFixedSize(w + 2, h + 2)
        self._place()
        self.show()
        self.raise_()
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.view.viewport() and event.type() == QtCore.QEvent.Resize:
            self._place()
        return super().eventFilter(obj, event)

    def _place(self):
        vp = self.view.viewport()
        self.move(self.MARGIN, vp.height() - self.height() - self.MARGIN)

    def _on_view_changed(self):
        # QGraphicsView scrolls its viewport children along with the scene.
        # Restore this overlay to viewport coordinates after every camera move.
        self._place()
        self._sync_zoom_to_view()
        self.raise_()
        self.update()

    # ── coords ──
    def _scene_to_map(self, p):
        r = self._scene_rect
        if r.isEmpty():
            return QtCore.QPointF()
        return QtCore.QPointF(1 + (p.x() - r.left()) / r.width() * self._map_w,
                              1 + (p.y() - r.top()) / r.height() * self._map_h)

    def _map_to_scene(self, p):
        r = self._scene_rect
        return QtCore.QPointF(r.left() + (p.x() - 1) / self._map_w * r.width(),
                              r.top() + (p.y() - 1) / self._map_h * r.height())

    # ── pintar ──
    def paintEvent(self, _event):
        if self._thumb is None and not self._layout:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(255, 255, 255, 235))
        if self._thumb is not None:
            full, area = self._full_scene_rect, self._scene_rect
            source = QtCore.QRectF((area.x()-full.x())/full.width()*self._src.width(),
                (area.y()-full.y())/full.height()*self._src.height(),
                area.width()/full.width()*self._src.width(), area.height()/full.height()*self._src.height())
            painter.drawPixmap(QtCore.QRectF(1, 1, self._map_w, self._map_h), self._src, source)
        else:
            # esquema: una caja por hoja con su etiqueta, en su posición relativa
            font = painter.font(); font.setPointSize(8); font.setBold(True); painter.setFont(font)
            for r, label in self._layout:
                box = QtCore.QRectF(self._scene_to_map(r.topLeft()), self._scene_to_map(r.bottomRight()))
                painter.setBrush(QtGui.QColor(232, 240, 253))
                painter.setPen(QtGui.QPen(QtGui.QColor("#5b7fb5"), 1))
                painter.drawRect(box)
                painter.setPen(QtGui.QColor("#1f3a68"))
                text = painter.fontMetrics().elidedText(label, QtCore.Qt.ElideMiddle, int(max(10.0, box.width() - 4)))
                painter.drawText(box, QtCore.Qt.AlignCenter | QtCore.Qt.TextDontClip, text)
        painter.setPen(QtGui.QPen(QtGui.QColor(120, 120, 120), 1))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        vis = self.view.mapToScene(self.view.viewport().rect()).boundingRect().intersected(self._scene_rect)
        if not vis.isEmpty():
            tl, br = self._scene_to_map(vis.topLeft()), self._scene_to_map(vis.bottomRight())
            box = QtCore.QRectF(tl, br)
            painter.setBrush(QtGui.QColor(43, 111, 209, 45))
            painter.setPen(QtGui.QPen(QtGui.QColor("#2b6fd1"), 2))
            painter.drawRect(box)
        painter.end()

    # ── navegar ──
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and (self._thumb is not None or self._layout):
            self._dragging = True
            self.view.centerOn(self._map_to_scene(event.position()))
            self.view.viewChanged.emit()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.view.centerOn(self._map_to_scene(event.position()))
            self.view.viewChanged.emit()
            event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()


def maximize_on_show(dialog):
    """Hace que un QDialog abra MAXIMIZADO a la primera. `setWindowState` antes
    de `exec()` no cuaja en Windows (QDialog recoloca la ventana respecto al
    padre al mostrarla); hay que pedirlo una vuelta del bucle de eventos
    después del primer Show, cuando la ventana nativa ya existe."""
    class _OnShow(QtCore.QObject):
        def eventFilter(self, obj, event):
            if event.type() == QtCore.QEvent.Show and not getattr(obj, "_maximized_once", False):
                obj._maximized_once = True
                QtCore.QTimer.singleShot(0, lambda: obj.setWindowState(
                    (obj.windowState() & ~QtCore.Qt.WindowMinimized) | QtCore.Qt.WindowMaximized))
            return False
    flt = _OnShow(dialog)
    dialog.installEventFilter(flt)
    return flt


def side_panel_width(total_width: int, preferred: int = 420, minimum: int = 300) -> int:
    """Ancho para un panel lateral: el preferido, pero nunca más del 32 % de la
    ventana ni menos del mínimo (pantallas pequeñas)."""
    return max(minimum, min(preferred, int(total_width * 0.32)))


class _VerticalLabel(QtWidgets.QWidget):
    """Texto girado 90° (para la tira de un panel plegado)."""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._text = text
        self.setMinimumWidth(22)

    def paintEvent(self, _e):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        font = painter.font(); font.setBold(True); painter.setFont(font)
        painter.translate(self.width() / 2 + painter.fontMetrics().height() / 2 - 2, self.height() - 6)
        painter.rotate(-90)
        painter.drawText(0, 0, self._text)
        painter.end()


class CollapsiblePanel(QtWidgets.QFrame):
    """Panel con cabecera (título + botón «plegar»). Plegado, queda una tira
    estrecha con el título en vertical y el botón para desplegar: así en
    pantallas pequeñas se gana sitio para el panel que se está usando.
    `body_layout` es donde va el contenido; `toggled(bool)` avisa al padre."""
    STRIP_W = 34
    toggled = QtCore.Signal(bool)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        from icons import icon as _icon
        self._title = title
        self._collapsed = False
        self._can_collapse = True
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # cuerpo (cabecera + contenido)
        self.body = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(self.body)
        vbox.setContentsMargins(12, 10, 12, 10); vbox.setSpacing(8)
        head = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(title)
        font = lbl.font(); font.setBold(True); font.setPointSize(font.pointSize() + 1); lbl.setFont(font)
        head.addWidget(lbl, 1)
        self.btn_collapse = QtWidgets.QToolButton()
        self.btn_collapse.setIcon(_icon("mdi:chevron-left")); self.btn_collapse.setAutoRaise(True)
        self.btn_collapse.setToolTip(_tr("Plegar este panel para dar más sitio a los demás"))
        self.btn_collapse.clicked.connect(lambda: self.set_collapsed(True))
        head.addWidget(self.btn_collapse)
        vbox.addLayout(head)
        self.body_layout = vbox
        outer.addWidget(self.body, 1)
        # tira (plegado)
        self.strip = QtWidgets.QWidget()
        self.strip.setFixedWidth(self.STRIP_W)
        sbox = QtWidgets.QVBoxLayout(self.strip)
        sbox.setContentsMargins(2, 6, 2, 6); sbox.setSpacing(4)
        self.btn_expand = QtWidgets.QToolButton()
        self.btn_expand.setIcon(_icon("mdi:chevron-right")); self.btn_expand.setAutoRaise(True)
        self.btn_expand.setToolTip(_tr("Desplegar"))
        self.btn_expand.clicked.connect(lambda: self.set_collapsed(False))
        sbox.addWidget(self.btn_expand, 0, QtCore.Qt.AlignHCenter)
        sbox.addWidget(_VerticalLabel(title), 1)
        self.strip.hide()
        outer.addWidget(self.strip)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapse_allowed(self, allowed: bool):
        """El padre lo apaga en el ÚLTIMO panel abierto: siempre queda uno visible."""
        self._can_collapse = bool(allowed)
        self.btn_collapse.setEnabled(self._can_collapse)
        self.btn_collapse.setToolTip(_tr("Plegar este panel para dar más sitio a los demás")
                                     if self._can_collapse else
                                     _tr("Siempre queda al menos un panel abierto"))

    def set_collapsed(self, on: bool):
        on = bool(on)
        if on == self._collapsed or (on and not self._can_collapse):
            return
        self._collapsed = on
        self.body.setVisible(not on)
        self.strip.setVisible(on)
        if on:
            self.setMinimumWidth(self.STRIP_W); self.setMaximumWidth(self.STRIP_W)
        else:
            self.setMinimumWidth(0); self.setMaximumWidth(16777215)
        self.toggled.emit(on)


class FlowLayout(QtWidgets.QLayout):
    """Fila de widgets que pasa a la línea siguiente cuando no cabe (leyendas,
    chips): en un panel angosto no se corta ni obliga a ensanchar el panel."""

    def __init__(self, parent=None, h_spacing: int = 12, v_spacing: int = 4):
        super().__init__(parent)
        self._items: list = []
        self._h, self._v = h_spacing, v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, apply: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            w = it.widget()
            if w is not None and w.isHidden():
                continue
            hint = it.sizeHint()
            if line_h and x + hint.width() > r.right() + 1:       # no cabe: línea siguiente
                x, y, line_h = r.x(), y + line_h + self._v, 0
            if apply:
                it.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x += hint.width() + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


class _GripHandle(QtWidgets.QSplitterHandle):
    """Tirador visible: línea fina + agarradera central con puntos; se ilumina
    con el color de acento al pasar el ratón o al arrastrar."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hot = False
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.setToolTip(_tr("Arrastra para cambiar el ancho"))

    def event(self, ev):
        if ev.type() in (QtCore.QEvent.HoverEnter, QtCore.QEvent.HoverLeave):
            self._hot = ev.type() == QtCore.QEvent.HoverEnter
            self.update()
        return super().event(ev)

    def mousePressEvent(self, ev):
        self._hot = True; self.update()
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self._hot = self.underMouse(); self.update()

    def paintEvent(self, _ev):
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect())
        horiz = self.orientation() == QtCore.Qt.Horizontal
        line = QtGui.QColor(t.accent if self._hot else t.border)
        c = r.center()
        # línea a todo lo largo
        p.setPen(QtGui.QPen(line, 2 if self._hot else 1))
        if horiz:
            p.drawLine(QtCore.QPointF(c.x(), r.top() + 4), QtCore.QPointF(c.x(), r.bottom() - 4))
        else:
            p.drawLine(QtCore.QPointF(r.left() + 4, c.y()), QtCore.QPointF(r.right() - 4, c.y()))
        # agarradera central (píldora con 3 puntos)
        w, h = (8.0, 44.0) if horiz else (44.0, 8.0)
        pill = QtCore.QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
        p.setPen(QtGui.QPen(line, 1))
        p.setBrush(QtGui.QColor(t.accent if self._hot else t.surface_alt))
        p.drawRoundedRect(pill, 4, 4)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(t.text_on_accent if self._hot else t.text_muted))
        for k in (-10, 0, 10):
            dot = QtCore.QPointF(c.x(), c.y() + k) if horiz else QtCore.QPointF(c.x() + k, c.y())
            p.drawEllipse(dot, 1.6, 1.6)
        p.end()


class GripSplitter(QtWidgets.QSplitter):
    """QSplitter con tirador visible (`_GripHandle`): se nota que se puede arrastrar."""

    def __init__(self, orientation=QtCore.Qt.Horizontal, parent=None, handle_width=12):
        super().__init__(orientation, parent)
        self.setHandleWidth(handle_width)
        self.setChildrenCollapsible(False)
        self.setStyleSheet("QSplitter::handle { background: transparent; border: none; }")
        _theme.THEME_BUS.changed.connect(lambda *_: [self.handle(i).update()
                                                     for i in range(self.count())])

    def createHandle(self):
        return _GripHandle(self.orientation(), self)
