"""tool_strip.py — fila única de herramientas que se adapta al ancho.

Pedido del usuario (2026-10-02, «Componer hoja de trabajo»): una sola barra
ordenada por grupos, sin filas de más. Con poco ancho (paneles «Origen» y
«Área a tomar» abiertos) los botones marcados como compactables pasan a solo
icono —el nombre sigue en el tooltip— en vez de cortarse o empujar el panel.
"""
from PySide6 import QtCore, QtWidgets

import theme as _theme


class ToolStrip(QtWidgets.QWidget):
    TEXT_PAD = 10        # px extra que ocupa un botón con texto (separación icono-texto)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        # La fila no impone su ancho al panel: si no cabe, se compacta.
        lay.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._compactable = []
        self.compact = False

    def add(self, widget, compact: bool = False):
        self.layout().addWidget(widget)
        if compact:
            if isinstance(widget, QtWidgets.QPushButton):
                widget.setProperty("fullText", widget.text())
            self._compactable.append(widget)
        return widget

    def add_separator(self) -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.VLine)
        line.setFixedSize(1, 26)
        line.setStyleSheet(f"background:{_theme.tokens().border}; border:none;")
        self.layout().addWidget(line)
        return line

    def add_stretch(self):
        self.layout().addStretch(1)

    # ── ancho ───────────────────────────────────────────────────────────
    def _text_of(self, w) -> str:
        return w.property("fullText") if isinstance(w, QtWidgets.QPushButton) else w.text()

    def full_width(self) -> int:
        """Ancho que necesita la fila CON texto (aunque ahora esté compacta)."""
        width = self.layout().sizeHint().width()
        if self.compact:
            for w in self._compactable:
                if w.isVisibleTo(self):
                    width += w.fontMetrics().horizontalAdvance(self._text_of(w)) + self.TEXT_PAD
        return width

    def set_compact(self, on: bool):
        self.compact = bool(on)
        for w in self._compactable:
            if isinstance(w, QtWidgets.QToolButton):
                w.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if on
                                     else QtCore.Qt.ToolButtonTextBesideIcon)
            else:
                w.setText("" if on else w.property("fullText"))

    def _fit(self):
        want = self.full_width() > self.width()
        if want != self.compact:
            self.set_compact(want)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def event(self, e):
        ok = super().event(e)
        if e.type() == QtCore.QEvent.LayoutRequest:     # apareció/desapareció un grupo
            self._fit()
        return ok
