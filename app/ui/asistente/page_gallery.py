"""page_gallery.py — galería de hojas de «Origen» con una CASILLA por hoja.

Pedido del usuario 2026-10-19 («para evitar problemas y confusiones»): cada hoja
lleva una casilla abajo a la derecha, junto a su nombre; las hojas MARCADAS son las
que están en la hoja compuesta. Antes un clic en la miniatura la agregaba (y la
primera vez reemplazaba a la que puso el compositor): mirar y elegir eran lo mismo.
Ahora:

  · clic en la miniatura = verla (`picked`; en «Área a tomar» queda esa hoja);
  · clic en la casilla, Ctrl+clic, Espacio o Enter = marcarla / desmarcarla
    (`toggled`); el doble clic sobre la casilla cuenta una sola vez (un doble clic
    «de costumbre» la dejaba igual que antes);
  · flechas = mirar otra hoja (`gesture = "browse"` mientras cambia).

La casilla la dibuja `_CheckDelegate` (más grande que la de Qt: 22 px) con los
colores del tema; la marca vive en el ítem (`USED_ROLE`), la pone el compositor.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme as _theme

USED_ROLE = QtCore.Qt.UserRole + 1     # bool: la hoja está en la hoja compuesta (casilla marcada)
CHECK_PX = 22                          # lado de la casilla
CHECK_MARGIN = 8                       # separación del borde derecho e inferior de la tarjeta


def check_rect(item_rect: QtCore.QRect, lista: bool = False) -> QtCore.QRect:
    """Casilla de una tarjeta: abajo a la derecha, a la altura del nombre de la hoja; en lista (2.0.0),
    a la derecha y al medio de la fila."""
    if lista:
        return QtCore.QRect(item_rect.right() - CHECK_PX - CHECK_MARGIN,
                            item_rect.center().y() - CHECK_PX // 2, CHECK_PX, CHECK_PX)
    return QtCore.QRect(item_rect.right() - CHECK_PX - CHECK_MARGIN,
                        item_rect.bottom() - CHECK_PX - CHECK_MARGIN, CHECK_PX, CHECK_PX)


def paint_check(p: QtGui.QPainter, rect: QtCore.QRect, on: bool, hover: bool, selected: bool):
    """Casilla con los colores del tema. Sobre la tarjeta elegida (fondo acento) se
    invierte: marcada = blanca con la marca en acento; vacía = solo el borde blanco."""
    t = _theme.tokens()
    box = QtCore.QRectF(rect).adjusted(1, 1, -1, -1)
    if selected:
        fill = QtGui.QColor(t.text_on_accent) if on else QtGui.QColor(0, 0, 0, 40)
        edge, mark = QtGui.QColor(t.text_on_accent), QtGui.QColor(t.accent)
    else:
        fill = QtGui.QColor((t.accent_hover if hover else t.accent) if on else t.input_bg)
        edge = QtGui.QColor(t.focus if (on or hover) else t.text_muted)   # vacía: que se note
        mark = QtGui.QColor(t.text_on_accent)
    p.save()
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setPen(QtGui.QPen(edge, 3 if hover else 2))
    p.setBrush(fill)
    p.drawRoundedRect(box, 4, 4)
    if on:
        w, h = box.width(), box.height()
        pen = QtGui.QPen(mark, 2.6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(box.left() + 0.22 * w, box.top() + 0.52 * h),
                                        QtCore.QPointF(box.left() + 0.42 * w, box.top() + 0.72 * h),
                                        QtCore.QPointF(box.left() + 0.78 * w, box.top() + 0.30 * h)]))
    p.restore()


class _CheckDelegate(QtWidgets.QStyledItemDelegate):
    """La tarjeta de siempre (miniatura + nombre, la dibuja el estilo) y encima la casilla."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        gallery = self.parent()
        paint_check(painter, check_rect(option.rect, self.parent().viewMode() == QtWidgets.QListView.ListMode), bool(index.data(USED_ROLE)),
                    hover=getattr(gallery, "_hover_check", -1) == index.row(),
                    selected=bool(option.state & QtWidgets.QStyle.State_Selected))


class PageGallery(QtWidgets.QListWidget):
    """Galería de hojas que distingue lo que hace el USUARIO de los cambios por
    código (sincronizar la hoja de una pieza, pruebas): `picked(fila)` = clic en la
    miniatura (verla); `toggled(fila)` = la casilla de esa hoja (clic en ella,
    Ctrl+clic, Espacio o Enter)."""
    picked = QtCore.Signal(int)
    toggled = QtCore.Signal(int)
    gesture = None          # «pick» / «browse»: un gesto del usuario cambia la hoja (antes de la señal)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(_CheckDelegate(self))
        self.setMouseTracking(True)
        self._hover_check = -1

    def check_hit(self, pos: QtCore.QPoint) -> int:
        """Fila cuya casilla está bajo `pos` (coordenadas del viewport), o -1. La zona
        sensible es algo mayor que la casilla: cuesta menos acertarle."""
        item = self.itemAt(pos)
        if item is None:
            return -1
        hit = check_rect(self.visualItemRect(item), self.viewMode() == QtWidgets.QListView.ListMode).adjusted(-6, -6, 6, 6)
        return self.row(item) if hit.contains(pos) else -1

    def set_used(self, row: int, used: bool):
        item = self.item(row)
        if item is not None and bool(item.data(USED_ROLE)) != bool(used):
            item.setData(USED_ROLE, bool(used))

    def is_used(self, row: int) -> bool:
        item = self.item(row)
        return item is not None and bool(item.data(USED_ROLE))

    # ── ratón ───────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        item = self.itemAt(pos) if e.button() == QtCore.Qt.LeftButton else None
        if item is not None and (self.check_hit(pos) >= 0 or e.modifiers() & QtCore.Qt.ControlModifier):
            self.toggled.emit(self.row(item))
            e.accept()
            return
        self.gesture = "pick" if item is not None else None
        try:
            super().mousePressEvent(e)
        finally:
            self.gesture = None
        if item is not None:
            self.picked.emit(self.row(item))

    def mouseDoubleClickEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and self.check_hit(e.position().toPoint()) >= 0:
            e.accept()                          # el 2.º clic de un doble clic en la casilla: nada
            return
        super().mouseDoubleClickEvent(e)

    def mouseMoveEvent(self, e):
        self._set_hover(self.check_hit(e.position().toPoint()))
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._set_hover(-1)
        super().leaveEvent(e)

    def _set_hover(self, row: int):
        if row == self._hover_check:
            return
        for r in (self._hover_check, row):
            item = self.item(r) if r >= 0 else None
            if item is not None:
                self.viewport().update(self.visualItemRect(item))
        self._hover_check = row
        self.viewport().setCursor(QtCore.Qt.PointingHandCursor if row >= 0 else QtCore.Qt.ArrowCursor)

    def viewportEvent(self, e):
        if e.type() == QtCore.QEvent.ToolTip:
            row = self.check_hit(e.pos())
            if row >= 0:
                QtWidgets.QToolTip.showText(
                    e.globalPos(), _tr("Desmarcar: quitarla de la hoja compuesta") if self.is_used(row)
                    else _tr("Marcar: usar esta hoja en la hoja compuesta"), self.viewport())
                return True
        return super().viewportEvent(e)

    # ── teclado ─────────────────────────────────────────────────────────
    def keyPressEvent(self, e):
        if (e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space)
                and self.currentRow() >= 0):
            self.toggled.emit(self.currentRow())    # Espacio / Enter = la casilla de la hoja a la vista
            e.accept()
            return
        self.gesture = "browse"
        try:
            super().keyPressEvent(e)
        finally:
            self.gesture = None
