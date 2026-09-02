"""canvas.py — El lienzo (QGraphicsView) donde se ve el PDF y se dibuja encima.

`Canvas` mantiene una referencia a la ventana principal (`win`, la clase Main de
app_window.py) y le reenvía los gestos del usuario (clic, doble clic, mover,
Enter/Escape, drag&drop) llamando a sus métodos. La lógica de qué hacer con cada
gesto vive en Main; aquí solo está el manejo del lienzo Qt (imagen del PDF, fondo
blanco/negro, opacidad, zoom con rueda y pan con botón central).

Extraído de app_window.py sin cambios de comportamiento (solo reubicación).
"""
from PySide6 import QtCore, QtGui, QtWidgets

from model import Z_PDF


class Canvas(QtWidgets.QGraphicsView):
    clicked = QtCore.Signal(float, float, object)
    dbl = QtCore.Signal(float, float)
    moved = QtCore.Signal(float, float)

    def __init__(self, win):
        super().__init__(); self.win = win
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor(13, 19, 33)); self.setAcceptDrops(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMouseTracking(True); self.viewport().setMouseTracking(True)
        self.pixmap_item = None; self._pan = False; self._pan0 = None; self._moving = False
        self.pdf_opacity = 1.0
        # Fondo DETRÁS del PDF (mismo tamaño que el PDF): blanco por defecto. Al
        # bajar la opacidad del PDF se ve este fondo en vez del azul del lienzo.
        # Se puede alternar a negro (ver set_pdf_bg / botón "Opacidad").
        self.pdf_bg_item = None
        self.pdf_bg_color = QtGui.QColor(255, 255, 255)

    def set_image(self, qimg):
        self.scene().clear()
        # Rectángulo de fondo (blanco/negro) por debajo del PDF, de su mismo tamaño.
        pm = QtGui.QPixmap.fromImage(qimg)
        self.pdf_bg_item = self.scene().addRect(
            QtCore.QRectF(pm.rect()), QtGui.QPen(QtCore.Qt.NoPen),
            QtGui.QBrush(self.pdf_bg_color))
        self.pdf_bg_item.setZValue(Z_PDF - 1)
        self.pixmap_item = self.scene().addPixmap(pm)
        self.pixmap_item.setZValue(Z_PDF)
        self.pixmap_item.setOpacity(self.pdf_opacity)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.resetTransform(); self.fitInView(self.pixmap_item, QtCore.Qt.KeepAspectRatio)

    def set_pdf_opacity(self, val):
        self.pdf_opacity = max(0.1, min(1.0, val))
        if self.pixmap_item: self.pixmap_item.setOpacity(self.pdf_opacity)

    def set_pdf_bg(self, color):
        """Color del fondo detrás del PDF (blanco o negro)."""
        self.pdf_bg_color = QtGui.QColor(color)
        if self.pdf_bg_item:
            self.pdf_bg_item.setBrush(QtGui.QBrush(self.pdf_bg_color))

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.win._on_enter(); e.accept(); return
        if e.key() == QtCore.Qt.Key_Escape:
            self.win._on_escape(); e.accept(); return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        if self.pixmap_item:
            f = 1.25 if e.angleDelta().y() > 0 else 0.8; self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = True; self._pan0 = e.position(); self.setCursor(QtCore.Qt.ClosedHandCursor); return
        if not self.pixmap_item: return super().mousePressEvent(e)
        self.setFocus(QtCore.Qt.MouseFocusReason)
        sp = self.mapToScene(e.position().toPoint())
        if self.win.mode == "move" and e.button() == QtCore.Qt.LeftButton:
            self._moving = True; self.win.begin_move(sp.x(), sp.y()); return
        if e.button() in (QtCore.Qt.LeftButton, QtCore.Qt.RightButton):
            self.clicked.emit(sp.x(), sp.y(), e.button()); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.pixmap_item:
            sp = self.mapToScene(e.position().toPoint()); self.moved.emit(sp.x(), sp.y())
        if self._pan:
            d = e.position() - self._pan0; self._pan0 = e.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y())); return
        if self._moving:
            sp = self.mapToScene(e.position().toPoint()); self.win.do_move(sp.x(), sp.y()); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = False; self.setCursor(QtCore.Qt.ArrowCursor); return
        if self._moving and e.button() == QtCore.Qt.LeftButton:
            self._moving = False; self.win.end_move(); return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.win.mode == "pipe": self.win.finish_pipe(); return
        sp = self.mapToScene(e.position().toPoint()); self.dbl.emit(sp.x(), sp.y())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            self.win.open_path(u.toLocalFile()); break
