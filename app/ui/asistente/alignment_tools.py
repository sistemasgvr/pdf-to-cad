"""alignment_tools.py — guías de la hoja compuesta (solo escena: nunca entran al
PDF compuesto ni a las exportaciones).

  - `AlignmentRuler`: regla graduada en pies, arrastrable; su borde inferior es
    la guía de alineación. Asa redonda en el extremo derecho para girarla.
    Bloqueada no recibe clics (las hojas se mueven por debajo) y lo muestra.
  - `PieceProtractor`: transportador sobre la pieza seleccionada, de TAMAÑO FIJO
    en pantalla. Se arrastra el punto verde: imán a 0°/90°/180°/270°, Ctrl =
    ajuste fino (el ratón gira 10 veces menos, centésimas), Shift = pasos de
    15°, doble clic = volver al eje más cercano (reporte del usuario 2026-10-02:
    volver a 0° desde −0.33° con el puntero era casi imposible).
  - `MeasureTag`: etiqueta de lectura (distancia, ángulo) de tamaño fijo.

La aritmética de los ángulos vive en `composite_scan.py` (pura, con pruebas).
"""
import math

from PySide6 import QtCore, QtGui, QtWidgets

from hoja import composite_scan as S

_ACCENT = "#244db2"
_HANDLE = "#43c23a"
_AXIS_OK = "#1f9d55"


class AngleDrag:
    """Arrastre de un ángulo alrededor de un centro. Normal: sigue al ratón;
    Ctrl: gira ×0.1 (fino); Shift: pasos de 15°. Se acumula el giro del ratón
    entre movimientos, así cambiar de modificador a mitad del arrastre no salta."""

    def __init__(self, start_value: float, mouse_angle: float):
        self.raw = float(start_value)
        self.last = float(mouse_angle)

    def move(self, mouse_angle: float, modifiers) -> tuple:
        fine = bool(modifiers & QtCore.Qt.ControlModifier)
        coarse = bool(modifiers & QtCore.Qt.ShiftModifier)
        d = S.signed_angle(mouse_angle - self.last)
        self.last = float(mouse_angle)
        self.raw += d * (S.FINE_DRAG_GAIN if fine else 1.0)
        return S.snap_angle(self.raw, fine=fine, coarse=coarse)


def _mouse_angle(p: QtCore.QPointF) -> float:
    """Ángulo (°, antihorario en pantalla) de un vector con y hacia abajo."""
    return math.degrees(math.atan2(-p.y(), p.x()))


def _cosmetic(color, width=1.0, style=QtCore.Qt.SolidLine) -> QtGui.QPen:
    pen = QtGui.QPen(QtGui.QColor(color), width, style)
    pen.setCosmetic(True)
    return pen


def _pill(painter: QtGui.QPainter, center: QtCore.QPointF, text: str, bg, fg="#ffffff", px=13):
    """Rótulo redondeado centrado en `center` (coordenadas de píxel)."""
    font = QtGui.QFont(painter.font())
    font.setPixelSize(px)
    font.setBold(True)
    painter.setFont(font)
    fm = QtGui.QFontMetricsF(font)
    w, h = fm.horizontalAdvance(text) + 14, fm.height() + 6
    r = QtCore.QRectF(center.x() - w / 2, center.y() - h / 2, w, h)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(bg))
    painter.drawRoundedRect(r, h / 2, h / 2)
    painter.setPen(QtGui.QColor(fg))
    painter.drawText(r, QtCore.Qt.AlignCenter, text)
    return r


class _RulerHandle(QtWidgets.QGraphicsObject):
    """Asa de giro de la regla (tamaño fijo en pantalla, hija de la regla)."""
    R = 9.0

    def __init__(self, ruler: "AlignmentRuler"):
        super().__init__(ruler)
        self.ruler = ruler
        self._hover = False
        self._drag = None
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.setZValue(5)

    def boundingRect(self):
        r = self.R + 4
        return QtCore.QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self):
        path = QtGui.QPainterPath()
        path.addEllipse(QtCore.QPointF(), self.R + 3, self.R + 3)
        return path

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2))
        painter.setBrush(QtGui.QColor(_HANDLE))
        r = self.R + (2 if self._hover or self._drag else 0)
        painter.drawEllipse(QtCore.QPointF(), r, r)
        # flecha de giro
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.6))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawArc(QtCore.QRectF(-4.5, -4.5, 9, 9), 30 * 16, 260 * 16)

    def hoverEnterEvent(self, e):
        self._hover = True; self.update()

    def hoverLeaveEvent(self, e):
        self._hover = False; self.update()

    def _pivot_angle(self, scene_pos):
        o = self.ruler.mapToScene(QtCore.QPointF(0, 0))
        return _mouse_angle(scene_pos - o)

    def mousePressEvent(self, e):
        self._drag = AngleDrag(self.ruler.angle(), self._pivot_angle(e.scenePos()))
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            value, _ = self._drag.move(self._pivot_angle(e.scenePos()), e.modifiers())
            self.ruler.configure(angle=value)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.update()
        e.accept()

    def mouseDoubleClickEvent(self, e):
        self.ruler.configure(angle=S.nearest_axis(self.ruler.angle()))
        e.accept()


class AlignmentRuler(QtWidgets.QGraphicsObject):
    changed = QtCore.Signal()

    def __init__(self, scale):
        super().__init__()
        self.length = 600.0
        self.width = 40.0
        self.scale_fn = scale
        self.locked = False
        self.setZValue(200)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(QtCore.Qt.SizeAllCursor)
        self.handle = _RulerHandle(self)
        self.badge = _RulerBadge(self)
        self._place_handle()

    def angle(self) -> float:
        """Rumbo de la regla (°, antihorario)."""
        return S.signed_angle(-self.rotation())

    def boundingRect(self):
        return QtCore.QRectF(-2, -self.width - 2, self.length + 4, self.width + 4)

    def _place_handle(self):
        # Sobre el borde guía: el ángulo del ratón respecto al origen es el de la regla.
        self.handle.setPos(self.length, 0)
        self.handle.setVisible(not self.locked)
        self.badge.setPos(0, -self.width)
        self.badge.update()

    def configure(self, length=None, width=None, angle=None, locked=None):
        self.prepareGeometryChange()
        if length is not None:
            self.length = max(10.0, float(length))
        if width is not None:
            self.width = max(5.0, float(width))
        if angle is not None:
            self.setRotation(-float(angle))
        if locked is not None:
            self.locked = bool(locked)
            self.setAcceptedMouseButtons(QtCore.Qt.NoButton if locked else QtCore.Qt.LeftButton)
            self.setCursor(QtCore.Qt.ArrowCursor if locked else QtCore.Qt.SizeAllCursor)
        self._place_handle()
        self.update()
        self.changed.emit()

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self.changed.emit()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._drag_start = event.scenePos()
        self._drag_position = self.pos()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self.locked:
            self.setPos(self._drag_position + event.scenePos() - self._drag_start)
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        color = QtGui.QColor("#5b6472" if self.locked else _ACCENT)
        pen = _cosmetic(color)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor(120, 128, 140, 60) if self.locked else QtGui.QColor(100, 120, 255, 55))
        painter.drawRect(QtCore.QRectF(0, -self.width, self.length, self.width))
        # El borde inferior es la referencia exacta de alineación.
        painter.setPen(_cosmetic("#d1342f" if self.locked else color, 2))
        painter.drawLine(QtCore.QPointF(0, 0), QtCore.QPointF(self.length, 0))
        painter.setPen(pen)
        screen_scale = max(0.0001, math.hypot(painter.transform().m11(), painter.transform().m12()))
        raw_step = 70 / screen_scale * self.scale_fn()
        power = 10 ** math.floor(math.log10(max(raw_step, 1e-8)))
        step = next(v * power for v in (1, 2, 5, 10) if v * power >= raw_step)
        spacing = step / self.scale_fn()
        font = QtGui.QFont(painter.font())
        font.setPixelSize(12)
        for i in range(min(2000, int(self.length / (spacing/5)) + 1)):
            x = i * spacing / 5
            major = i % 5 == 0
            painter.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, -min(self.width, (15 if major else 7)/screen_scale)))
            if major:
                painter.save()
                painter.translate(x, -self.width/2)
                painter.scale(1/screen_scale, 1/screen_scale)
                painter.setFont(font)
                painter.drawText(QtCore.QRectF(3, -8, 85, 18), f"{i//5*step:g}'")
                painter.restore()

    @staticmethod
    def paint_lock(painter, c: QtCore.QPointF):
        painter.setPen(QtGui.QPen(QtGui.QColor("#d1342f"), 1.8))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawArc(QtCore.QRectF(c.x() - 4, c.y() - 9, 8, 9), 0, 180 * 16)
        painter.setBrush(QtGui.QColor("#d1342f"))
        painter.drawRoundedRect(QtCore.QRectF(c.x() - 6, c.y() - 4, 12, 9), 2, 2)


class _RulerBadge(QtWidgets.QGraphicsItem):
    """Candado y rumbo de la regla, derechos y de tamaño fijo, sobre su origen."""

    def __init__(self, ruler: "AlignmentRuler"):
        super().__init__(ruler)
        self.ruler = ruler
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self.setZValue(5)

    def boundingRect(self):
        return QtCore.QRectF(-4, -30, 130, 30)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        x = 0.0
        if self.ruler.locked:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(255, 255, 255, 220))
            painter.drawRoundedRect(QtCore.QRectF(x, -26, 22, 22), 5, 5)
            AlignmentRuler.paint_lock(painter, QtCore.QPointF(x + 11, -11))
            x += 26
        a = self.ruler.angle()
        if abs(a) > 1e-9:
            font = QtGui.QFont(painter.font())
            font.setPixelSize(12)
            fm = QtGui.QFontMetricsF(font)
            text = f"{a:.2f}°"
            w = fm.horizontalAdvance(text) + 12
            _pill(painter, QtCore.QPointF(x + w / 2, -15), text,
                  "#5b6472" if self.ruler.locked else _ACCENT, px=12)


class PieceProtractor(QtWidgets.QGraphicsObject):
    """Transportador de tamaño fijo en pantalla centrado en la pieza seleccionada."""
    angleChanged = QtCore.Signal(float)
    RADIUS = 115.0
    HANDLE_R = 10.0

    def __init__(self):
        super().__init__()
        self.radius = self.RADIUS
        self.angle = 0.0
        self.on_axis = True
        self._drag = None
        self._fine = False
        self._hover = False
        self.setZValue(210)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.CrossCursor)

    def boundingRect(self):
        r = self.radius + 48
        return QtCore.QRectF(-r, -r, 2*r, 2*r)

    def handle_point(self):
        th = math.radians(self.angle)
        return QtCore.QPointF(self.radius*math.cos(th), -self.radius*math.sin(th))

    def shape(self):
        # Solo el punto verde recibe clics; las hojas se siguen moviendo a través del dial.
        path = QtGui.QPainterPath()
        path.addEllipse(self.handle_point(), self.HANDLE_R + 6, self.HANDLE_R + 6)
        return path

    def configure(self, center, radius=None, angle=0.0):
        """`radius` se ignora (el dial mide lo mismo en pantalla a cualquier zoom);
        se conserva por compatibilidad."""
        self.prepareGeometryChange()
        self.angle = S.signed_angle(angle)
        self.on_axis = any(abs(self.angle % 360.0 - c) < 1e-6 for c in S.CARDINALS)
        self.setPos(center)
        self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.radius
        accent = QtGui.QColor(_ACCENT)
        # Ejes de referencia (0°/90°) más largos que el dial, a trazos.
        painter.setPen(_cosmetic(QtGui.QColor(36, 77, 178, 150), 1, QtCore.Qt.DashLine))
        painter.drawLine(QtCore.QPointF(-r - 36, 0), QtCore.QPointF(r + 36, 0))
        painter.drawLine(QtCore.QPointF(0, -r - 36), QtCore.QPointF(0, r + 36))
        painter.setPen(_cosmetic(accent))
        painter.setBrush(QtGui.QColor(130, 140, 255, 38))
        painter.drawEllipse(QtCore.QPointF(), r, r)
        # Sector del giro actual (desde 0°).
        if abs(self.angle) > 1e-6:
            fill = QtGui.QColor(_HANDLE)
            fill.setAlpha(70)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(fill)
            painter.drawPie(QtCore.QRectF(-r * 0.62, -r * 0.62, r * 1.24, r * 1.24), 0,
                            int(round(self.angle * 16)))
        painter.setPen(_cosmetic(accent))
        font = QtGui.QFont(painter.font())
        font.setPixelSize(11)
        painter.setFont(font)
        for degree in range(0, 360, 5):
            th = math.radians(degree)
            inner = r * (0.86 if degree % 30 == 0 else 0.91 if degree % 15 == 0 else 0.95)
            painter.drawLine(QtCore.QPointF(inner*math.cos(th), -inner*math.sin(th)),
                             QtCore.QPointF(r*math.cos(th), -r*math.sin(th)))
            if degree % 30 == 0:
                label = S.signed_angle(degree)
                p = QtCore.QPointF(r*0.74*math.cos(th), -r*0.74*math.sin(th))
                painter.drawText(QtCore.QRectF(p.x()-20, p.y()-9, 40, 18), QtCore.Qt.AlignCenter,
                                 f"{label:g}")
        h = self.handle_point()
        painter.setPen(_cosmetic(_AXIS_OK if self.on_axis else "#2a3550", 2))
        painter.drawLine(QtCore.QPointF(), h)
        # Lectura grande bajo el centro: verde cuando está exactamente en un eje.
        _pill(painter, QtCore.QPointF(0, 22), f"{self.angle:.2f}°",
              _AXIS_OK if self.on_axis else "#2a3550", px=14)
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2))
        painter.setBrush(QtGui.QColor(_HANDLE))
        hr = self.HANDLE_R + (3 if self._hover or self._drag else 0)
        painter.drawEllipse(h, hr, hr)
        if self.on_axis:
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2))
            painter.drawLine(h + QtCore.QPointF(-4, 0), h + QtCore.QPointF(-1, 3))
            painter.drawLine(h + QtCore.QPointF(-1, 3), h + QtCore.QPointF(4, -3))

    def hoverEnterEvent(self, e):
        self._hover = True; self.update()

    def hoverLeaveEvent(self, e):
        self._hover = False; self.update()

    def mousePressEvent(self, event):
        self._drag = AngleDrag(self.angle, _mouse_angle(event.pos()))
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None and math.hypot(event.pos().x(), event.pos().y()) > 2:
            value, _ = self._drag.move(_mouse_angle(event.pos()), event.modifiers())
            if abs(value - self.angle) > 1e-9:
                self.angleChanged.emit(value)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.angleChanged.emit(S.nearest_axis(self.angle))
        event.accept()


class MeasureTag(QtWidgets.QGraphicsItem):
    """Rótulo de medida (tamaño fijo en pantalla) junto al punto de la escena."""

    def __init__(self):
        super().__init__()
        self.text = ""
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self.setZValue(220)

    def set_text(self, text: str):
        self.prepareGeometryChange()
        self.text = text
        self.update()

    def boundingRect(self):
        return QtCore.QRectF(-160, -40, 320, 34)

    def paint(self, painter, option, widget=None):
        if self.text:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            _pill(painter, QtCore.QPointF(0, -22), self.text, "#0a7f99", px=13)
