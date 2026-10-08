"""composite_tabs.py — pestañas del compositor: «Origen · Área a tomar · Hoja compuesta».

Pedido del usuario 2026-10-03: en tres columnas a cada vista le quedaba poco sitio;
ahora cada una ocupa la ventana entera y se pasa de una a otra con estas pestañas
(siempre clicables: se puede volver a cualquiera). Sin números para no confundirlas
con los pasos del asistente (1 Componer hoja › 2 Capas › 3 Vista previa).

Cada pestaña lleva una INSIGNIA opcional a la derecha: un número (piezas de la hoja
compuesta) o un aviso «!» (algo pendiente en esa vista). Se pinta a mano para que la
insignia quede dentro de la pestaña y con el mismo alto que los botones del diálogo.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun.icons import icon as _icon
from ui.comun import theme as _theme

BADGE_COUNT, BADGE_WARN = "count", "warn"
TAB_H = 40


class _Tab(QtWidgets.QAbstractButton):
    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.badge: Optional[Tuple[str, str]] = None     # (texto, nivel)
        self.setMinimumHeight(TAB_H)

    def set_badge(self, text: Optional[str], level: str = BADGE_COUNT):
        self.badge = (str(text), level) if text not in (None, "") else None
        self.updateGeometry(); self.update()

    def _badge_w(self, fm) -> int:
        return fm.horizontalAdvance(self.badge[0]) + 14 if self.badge else 0

    def sizeHint(self):
        f = QtGui.QFont(self.font()); f.setBold(True)
        fm = QtGui.QFontMetrics(f)
        w = 16 + 20 + 8 + fm.horizontalAdvance(self.text()) + 16
        if self.badge:
            w += 8 + self._badge_w(fm)
        return QtCore.QSize(w, TAB_H)

    def paintEvent(self, _e):
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = self.isChecked()
        hover = self.underMouse() and not on
        if on:
            p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(t.accent))
        else:
            p.setPen(QtGui.QPen(QtGui.QColor(t.focus if hover else t.border), 1))
            p.setBrush(QtGui.QColor(t.hover if hover else t.surface_alt))
        p.drawRoundedRect(r, 8, 8)
        if self.hasFocus() and not on:
            p.setPen(QtGui.QPen(QtGui.QColor(t.focus), 2)); p.setBrush(QtCore.Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 7, 7)
        ink = QtGui.QColor(t.text_on_accent if on else t.text)
        x = 16
        pm = _icon(self._icon_name, color=ink.name()).pixmap(20, 20)
        p.drawPixmap(int(x), int((self.height() - 20) / 2), pm)
        x += 28
        f = QtGui.QFont(self.font()); f.setBold(on)
        p.setFont(f); p.setPen(ink)
        fm = QtGui.QFontMetrics(f)
        p.drawText(QtCore.QRectF(x, 0, fm.horizontalAdvance(self.text()) + 4, self.height()),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.text())
        if self.badge:
            text, level = self.badge
            bf = QtGui.QFont(self.font()); bf.setBold(True)
            bfm = QtGui.QFontMetrics(bf)
            bw = bfm.horizontalAdvance(text) + 14
            br = QtCore.QRectF(x + fm.horizontalAdvance(self.text()) + 10, (self.height() - 20) / 2, max(bw, 20), 20)
            if level == BADGE_WARN:
                bg, fg = QtGui.QColor(t.selection), QtGui.QColor("#1e2531")
            elif on:
                bg, fg = QtGui.QColor(t.text_on_accent), QtGui.QColor(t.accent)
            else:
                bg, fg = QtGui.QColor(t.border), QtGui.QColor(t.text)
            p.setPen(QtCore.Qt.NoPen); p.setBrush(bg)
            p.drawRoundedRect(br, 10, 10)
            p.setFont(bf); p.setPen(fg)
            p.drawText(br, QtCore.Qt.AlignCenter, text)
        p.end()


class WorkTabs(QtWidgets.QWidget):
    """Fila de pestañas. `currentChanged(int)` al elegir otra (clic, Enter o
    flechas ← → con el foco en una pestaña)."""

    currentChanged = QtCore.Signal(int)

    def __init__(self, items: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(8)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self.tabs: List[_Tab] = []
        for i, (icon_name, text) in enumerate(items):
            tab = _Tab(icon_name, text)
            self._group.addButton(tab, i)
            row.addWidget(tab)
            self.tabs.append(tab)
        row.addStretch(1)
        self._group.idClicked.connect(self._on_clicked)
        self._current = -1

    def current(self) -> int:
        return self._current

    def set_current(self, index: int, emit: bool = True):
        if not 0 <= index < len(self.tabs):
            return
        self.tabs[index].setChecked(True)
        if index != self._current:
            self._current = index
            if emit:
                self.currentChanged.emit(index)

    def _on_clicked(self, index: int):
        self.set_current(index)

    def set_badge(self, index: int, text: Optional[str], level: str = BADGE_COUNT):
        self.tabs[index].set_badge(text, level)

    def keyPressEvent(self, e):
        step = {QtCore.Qt.Key_Left: -1, QtCore.Qt.Key_Right: 1}.get(e.key())
        if step and self._current >= 0:
            nxt = (self._current + step) % len(self.tabs)
            self.set_current(nxt)
            self.tabs[nxt].setFocus()
            return
        super().keyPressEvent(e)
