"""Controles que se adaptan al ancho del panel (pedido del usuario 2026-10-05:
«que no haya scroll horizontal nunca»).

Un QPushButton/QCheckBox de Qt nunca parte su texto y su ancho mínimo es el del
texto entero; un QGroupBox tampoco puede ser más angosto que su título. En un
panel lateral eso empujaba el contenido fuera del borde (con la barra horizontal
apagada, quedaba cortado). Aquí:

  - `WrapButton` / `WrapCheckBox`: el texto se parte en líneas (palabras enteras)
    cuando el ancho no alcanza; su ancho mínimo es el de la palabra más larga.
    `text()` sigue devolviendo el texto completo (lo que se escribió con setText).
  - `ResponsiveGroupBox`: el título se acorta con «…» (completo en el tooltip) y
    no impone ancho mínimo; manda el contenido.
"""
from __future__ import annotations

import re

from PySide6 import QtCore, QtGui, QtWidgets


def wrap_lines(text: str, width: float, advance) -> list:
    """Parte `text` en líneas de ancho ≤ `width` medidas con `advance(str) -> px`.
    Palabras enteras (una palabra más larga que el ancho va sola en su línea). Los
    espacios del principio (separación del icono) se quedan en la primera línea."""
    out = []
    for parrafo in (text or "").split("\n"):
        m = re.match(r"^(\s*)(.*)$", parrafo, re.S)
        prefijo, palabras = m.group(1), m.group(2).split()
        if not palabras:
            out.append(parrafo)
            continue
        linea = prefijo + palabras[0]
        for p in palabras[1:]:
            cand = linea + " " + p
            if advance(cand) <= width:
                linea = cand
            else:
                out.append(linea)
                linea = p
        out.append(linea)
    return out


def palabra_mas_larga(text: str, advance) -> float:
    """Ancho de la palabra más larga (la primera con sus espacios iniciales)."""
    anchos = []
    for parrafo in (text or "").split("\n"):
        m = re.match(r"^(\s*)(.*)$", parrafo, re.S)
        palabras = m.group(2).split()
        if palabras:
            palabras[0] = m.group(1) + palabras[0]
        anchos += [advance(p) for p in palabras]
    return max(anchos, default=0)


class _WrapMixin:
    """Lógica común de WrapButton/WrapCheckBox (va ANTES de la clase Qt en la herencia)."""

    _CT = QtWidgets.QStyle.CT_PushButton

    def _wrap_init(self):
        self._full = ""
        self._shown = None
        pol = self.sizePolicy()
        pol.setHorizontalPolicy(QtWidgets.QSizePolicy.Preferred)
        self.setSizePolicy(pol)

    # ── texto completo ──
    def setText(self, text):                       # noqa: N802 (API de Qt)
        self._full = text or ""
        self._shown = None
        self._rewrap()

    def text(self):
        return self._full

    def setIcon(self, ic):                         # noqa: N802
        super().setIcon(ic)
        self._shown = None
        self._rewrap()

    # ── medidas ──
    def _size_for(self, text):
        fm = self.fontMetrics()
        ts = fm.size(QtCore.Qt.TextShowMnemonic, text) if text else QtCore.QSize(0, fm.height())
        w, h = ts.width(), max(ts.height(), fm.height())
        if not self.icon().isNull():
            isz = self.iconSize()
            w += isz.width() + 4
            h = max(h, isz.height())
        opt = QtWidgets.QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = text
        return self.style().sizeFromContents(self._CT, opt, QtCore.QSize(w, h), self)

    def _overhead(self):
        """Ancho que no es texto: bordes y relleno del estilo (+ indicador) + icono."""
        return self._size_for("").width()

    def sizeHint(self):                            # noqa: N802
        full = self._size_for(self._full)
        cur = self._size_for(self._shown if self._shown is not None else self._full)
        return QtCore.QSize(full.width(), cur.height())

    def minimumSizeHint(self):                     # noqa: N802
        cur = self._size_for(self._shown if self._shown is not None else self._full)
        larga = palabra_mas_larga(self._full, self.fontMetrics().horizontalAdvance)
        return QtCore.QSize(self._overhead() + int(larga) + 1, cur.height())

    # ── reparto en líneas según el ancho actual ──
    def _rewrap(self):
        texto = ""
        if self._full:
            fm = self.fontMetrics()
            texto = "\n".join(wrap_lines(self._full, self.width() - self._overhead(), fm.horizontalAdvance))
        if texto != self._shown:
            self._shown = texto
            QtWidgets.QAbstractButton.setText(self, texto)
            self.updateGeometry()

    def resizeEvent(self, e):                      # noqa: N802
        super().resizeEvent(e)
        self._rewrap()

    def changeEvent(self, e):                      # noqa: N802
        super().changeEvent(e)
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._shown = None
            self._rewrap()


class WrapButton(_WrapMixin, QtWidgets.QPushButton):
    """QPushButton cuyo texto se parte en líneas si el panel es angosto."""
    _CT = QtWidgets.QStyle.CT_PushButton

    def __init__(self, text="", parent=None):
        QtWidgets.QPushButton.__init__(self, parent)
        self._wrap_init()
        self.setText(text)


class WrapCheckBox(_WrapMixin, QtWidgets.QCheckBox):
    """QCheckBox cuyo texto se parte en líneas si el panel es angosto."""
    _CT = QtWidgets.QStyle.CT_CheckBox

    def __init__(self, text="", parent=None):
        QtWidgets.QCheckBox.__init__(self, parent)
        self._wrap_init()
        self.setText(text)


class ResponsiveGroupBox(QtWidgets.QGroupBox):
    """QGroupBox cuyo título se acorta con «…» y no impone ancho mínimo."""

    _MARGEN_TITULO = 28          # sangría + relleno del ::title en el QSS

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setTitle(title)

    def setTitle(self, title):                     # noqa: N802
        self._full = title or ""
        self._apply_title()

    def title(self):
        return self._full

    def _apply_title(self):
        disp = self._full
        if self._full:
            f = QtGui.QFont(self.font()); f.setBold(True)
            disp = QtGui.QFontMetrics(f).elidedText(
                self._full, QtCore.Qt.ElideRight, max(40, self.width() - self._MARGEN_TITULO))
        if disp != super().title():
            super().setTitle(disp)
            self.updateGeometry()
        recortado = disp != self._full
        if recortado or self.toolTip() == self._full:
            self.setToolTip(self._full if recortado else "")

    def minimumSizeHint(self):                     # noqa: N802
        s = super().minimumSizeHint()
        lay = self.layout()
        if lay is None:
            return s
        m = self.contentsMargins()
        w = lay.minimumSize().width() + m.left() + m.right()
        return QtCore.QSize(min(s.width(), max(w, 60)), s.height())

    def resizeEvent(self, e):                      # noqa: N802
        super().resizeEvent(e)
        self._apply_title()


class GridAdaptable(QtWidgets.QLayout):
    """Rejilla de botones con hasta `max_cols` columnas: usa tantas como quepan sin
    cortar ningún botón (2 si caben, 1 si el panel es angosto). Cada botón ocupa todo
    el ancho de su celda, como en un QGridLayout. Los ocultos no ocupan lugar."""

    def __init__(self, parent=None, max_cols=2, spacing=6):
        super().__init__(parent)
        self._items = []
        self._max = max(1, int(max_cols))
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):                       # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):                           # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):                           # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):                 # noqa: N802
        return QtCore.Qt.Orientations()

    def _visibles(self):
        return [it for it in self._items if not (it.widget() is not None and it.widget().isHidden())]

    def columnas(self, ancho):
        """Columnas que se usan con este ancho (sin márgenes)."""
        vis = self._visibles()
        if not vis:
            return 1
        minimo = max(it.minimumSize().width() for it in vis)
        cols = min(self._max, len(vis))
        while cols > 1 and (ancho - (cols - 1) * self._sp) / cols < minimo:
            cols -= 1
        return cols

    def hasHeightForWidth(self):                   # noqa: N802
        return True

    def heightForWidth(self, width):               # noqa: N802
        return self._do_layout(QtCore.QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):                   # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def minimumSize(self):                         # noqa: N802
        vis = self._visibles()
        m = self.contentsMargins()
        w = max((it.minimumSize().width() for it in vis), default=0) + m.left() + m.right()
        return QtCore.QSize(w, self.heightForWidth(w))

    def sizeHint(self):                            # noqa: N802
        vis = self._visibles()
        m = self.contentsMargins()
        cols = min(self._max, max(1, len(vis)))
        w = cols * max((it.sizeHint().width() for it in vis), default=0) + (cols - 1) * self._sp
        w += m.left() + m.right()
        return QtCore.QSize(w, self.heightForWidth(w))

    def _do_layout(self, rect, apply):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        vis = self._visibles()
        if not vis:
            return m.top() + m.bottom()
        cols = self.columnas(r.width())
        cell = (r.width() - (cols - 1) * self._sp) / cols
        y = r.y()
        for i in range(0, len(vis), cols):
            fila = vis[i:i + cols]
            h = max((it.heightForWidth(int(cell)) if it.hasHeightForWidth() else it.sizeHint().height())
                    for it in fila)
            for j, it in enumerate(fila):
                if apply:
                    x = r.x() + j * (cell + self._sp)
                    it.setGeometry(QtCore.QRect(int(round(x)), y, int(cell), h))
            y += h + self._sp
        return y - self._sp - rect.y() + m.bottom()
