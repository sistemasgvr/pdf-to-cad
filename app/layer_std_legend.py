"""layer_std_legend.py — «Leyenda del plano» SEGÚN EL ESTÁNDAR en «Capas de la hoja».

Pedido del usuario 2026-10-07: si el PDF no trae leyenda (DU06), armarla con los datos
del manual BOE y las líneas que hay en la hoja (`leyenda_estandar.leyenda`). Por
utilidad: una cabecera (cuadrito, nombre y abreviatura BOE) y una fila por tipo de línea
—muestra dibujada como en un plano (su color, a trazos si es existente y continua si es
propuesta, las letras leídas en el hueco y «//» si va a demoler)— + sus estructuras.
Clic en la cabecera = toda la utilidad; en una fila = esas capas (`activated(spec)`,
lo resalta `layer_dialog_info`). Menos texto: lo largo va al tooltip.
"""
from __future__ import annotations

from typing import List

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr
from recognition_summary_view import utility_swatch
from ui_common import layer_qcolor
import leyenda_estandar as le
import pdf_layers
import recognition
import theme as _theme

SAMPLE_W, SAMPLE_H = 76, 20


def sample_color(utility: str) -> QtGui.QColor:
    """Color de la utilidad sobre papel blanco (el blanco del drenaje, en gris)."""
    c = QtGui.QColor(layer_qcolor(utility or "OTRAS"))
    return QtGui.QColor(90, 90, 90) if c.lightness() > 200 else c


class LineSample(QtWidgets.QWidget):
    """Muestra de la línea de una fila, sobre papel blanco como la hoja."""

    def __init__(self, fila: le.Fila):
        super().__init__()
        self.fila = fila
        self.setFixedSize(SAMPLE_W, SAMPLE_H)

    def paintEvent(self, _e):
        f = self.fila
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor("white"))
        p.drawRoundedRect(QtCore.QRectF(self.rect()), 3, 3)
        color = sample_color(f.utilidad)
        w, h = self.width(), self.height()
        y = h / 2.0
        if f.rol == le.STRUCTURE:
            p.setPen(QtGui.QPen(color, 1.6)); p.setBrush(QtCore.Qt.NoBrush)
            p.drawLine(QtCore.QPointF(4, y), QtCore.QPointF(w / 2 - 9, y))
            p.drawRect(QtCore.QRectF(w / 2 - 9, y - 6, 18, 12))
            p.drawLine(QtCore.QPointF(w / 2 + 9, y), QtCore.QPointF(w - 4, y))
            p.end()
            return
        pen = QtGui.QPen(color, 1.6)
        pen.setCapStyle(QtCore.Qt.FlatCap)
        if not f.continua:
            pen.setDashPattern([4.0, 2.0])
        text = f.letras[0] if f.letras else ""
        font = p.font(); font.setPixelSize(11); font.setBold(True); p.setFont(font)
        tw = QtGui.QFontMetricsF(font).horizontalAdvance(text) if text else 0.0
        cx = w * 0.62
        gap = tw + 6 if text else 0.0
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(4, y), QtCore.QPointF(cx - gap / 2, y))
        p.drawLine(QtCore.QPointF(cx + gap / 2, y), QtCore.QPointF(w - 4, y))
        if text:
            p.setPen(color)
            p.drawText(QtCore.QRectF(cx - gap / 2, 0, gap, h), QtCore.Qt.AlignCenter, text)
        if f.marcas:
            p.setPen(QtGui.QPen(color, 1.4))
            x0 = w * 0.24
            for i in range(len(f.marcas)):
                x = x0 + i * 4
                p.drawLine(QtCore.QPointF(x - 2.5, y + 5), QtCore.QPointF(x + 2.5, y - 5))
        p.end()


def _status_text(fila: le.Fila) -> str:
    if fila.rol == le.STRUCTURE:
        name = le.STRUCTURES.get(fila.utilidad, ("", "", le.STRUCTURE_OTHER))[2]
        return _tr(name)
    key = le.nombre_estado(fila.estado)
    return _tr(key).format(n=fila.estado) if fila.estado.isdigit() else _tr(key)


MAX_NAMES = 3            # capas que se nombran en una fila (las demás, en el tooltip)


def _layer_names(layers: List[dict], fila: le.Fila) -> List[str]:
    by_name = {L["name"]: L for L in layers}
    out = []
    for n in fila.capas:
        short = pdf_layers.short_name(n)
        L = by_name.get(n) or {}
        if fila.utilidad in (L.get("letter_utilities") or ()) and not L.get("name_utility"):
            short = _tr("{capa} (por sus letras)").format(capa=short)
        if short not in out:
            out.append(short)
    return out


def _layers_text(names: List[str]) -> str:
    if len(names) <= MAX_NAMES:
        return " · ".join(names)
    return _tr("{capas} y {n} más").format(capas=" · ".join(names[:MAX_NAMES]), n=len(names) - MAX_NAMES)


def _row_tooltip(fila: le.Fila) -> str:
    lines = []
    if fila.rol == le.LINE:
        if fila.origen == le.FROM_NAME:
            lines.append(_tr("Estado «{c}» del nombre de la capa (BOE §8.1.6).").format(c=fila.estado))
        elif fila.origen == le.FROM_XREF:
            lines.append(_tr("Estado tomado del nombre del xref de la capa."))
        elif fila.origen == le.FROM_LETTERS:
            lines.append(_tr("El nombre no dice el estado: letras en MAYÚSCULA = propuesta, en "
                             "minúscula = existente (leyendas de los planos)."))
        if fila.marcas:
            lines.append(_tr("«{m}» sobre la línea = a abandonar / abandonada.").format(m=fila.marcas))
        if fila.continua:
            lines.append(_tr("Propuesta: línea continua (BOE fig. 3.1.7.1-2)."))
        if len(fila.letras) > 1:
            lines.append(_tr("Letras leídas: {l}").format(l=", ".join(fila.letras)))
    lt = le.linetype(fila.abbr) if fila.abbr else None
    if lt:
        lines.append(_tr("Estándar BOE: {a} — {en} ({es}).").format(a=fila.abbr, en=lt[0], es=_tr(lt[1])))
    lines.append(_tr("Clic: ver estas líneas en la hoja (otro clic, ver todo)."))
    return "\n".join(lines)


class _Clickable(QtWidgets.QFrame):
    activated = QtCore.Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.activated.emit()
            return
        super().mouseReleaseEvent(e)


def _row_qss() -> str:
    t = _theme.tokens()
    return (f"#stdRow {{ background:{t.surface_alt}; border:1px solid {t.border_soft}; border-radius:6px; }}"
            f" #stdRow:hover {{ border:1px solid {t.text_muted}; }}"
            " #stdRow QLabel { background:transparent; border:none; }")


def _head_qss() -> str:
    t = _theme.tokens()
    return ("#stdHead { background:transparent; border:1px solid transparent; border-radius:6px; }"
            f" #stdHead:hover {{ border:1px solid {t.text_muted}; }}"
            " #stdHead QLabel { background:transparent; border:none; }")


class StandardLegend(QtWidgets.QWidget):
    """Leyenda armada con el estándar. `activated(spec)`: {"utility": U} (toda la
    utilidad) o {"utility": U, "layers": [...], "role": rol, "label": texto}."""
    activated = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self.groups: List[le.Grupo] = []
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0); self._lay.setSpacing(4)

    def set_layers(self, layers: List[dict]) -> None:
        """Capas de la hoja ya con la decisión «Usar» aplicada (`without_letters`)."""
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        self.groups = le.leyenda(layers)
        t = _theme.tokens()
        for g in self.groups:
            name = _tr(recognition.utility_label(g.utilidad))
            head = _Clickable(); head.setObjectName("stdHead"); head.setStyleSheet(_head_qss())
            head.setCursor(QtCore.Qt.PointingHandCursor)
            hl = QtWidgets.QHBoxLayout(head); hl.setContentsMargins(4, 4, 4, 2); hl.setSpacing(6)
            sw = QtWidgets.QLabel(); sw.setPixmap(utility_swatch(layer_qcolor(g.utilidad), 12))
            hl.addWidget(sw, 0)
            lb = QtWidgets.QLabel(name)
            f = lb.font(); f.setBold(True); lb.setFont(f)
            hl.addWidget(lb, 0)
            if g.abbr:
                ab = QtWidgets.QLabel(g.abbr)
                ab.setStyleSheet(f"color:{t.text_muted}; font-size:11px;")
                hl.addWidget(ab, 0)
            hl.addStretch(1)
            lt = le.linetype(g.abbr) if g.abbr else None
            tip = [_tr("Estándar BOE: {a} — {en} ({es}).").format(a=g.abbr, en=lt[0], es=_tr(lt[1]))] if lt else []
            tip.append(_tr("Clic: ver en la hoja todas sus líneas y estructuras (otro clic, ver todo)."))
            head.setToolTip("\n".join(tip))
            head.activated.connect(lambda u=g.utilidad, n=name: self.activated.emit(
                {"utility": u, "label": n}))
            self._lay.addWidget(head)
            for fila in g.filas:
                self._lay.addWidget(self._row(layers, fila, name))

    def _row(self, layers, fila: le.Fila, util_name: str) -> QtWidgets.QWidget:
        t = _theme.tokens()
        w = _Clickable(); w.setObjectName("stdRow"); w.setStyleSheet(_row_qss())
        w.setCursor(QtCore.Qt.PointingHandCursor)
        lay = QtWidgets.QHBoxLayout(w); lay.setContentsMargins(6, 4, 6, 4); lay.setSpacing(8)
        lay.addWidget(LineSample(fila), 0, QtCore.Qt.AlignTop)
        col = QtWidgets.QVBoxLayout(); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(1)
        status = _status_text(fila)
        top = QtWidgets.QLabel(status)
        top.setWordWrap(True)
        top.setStyleSheet(f"color:{t.text}; font-size:12px;")
        col.addWidget(top)
        all_names = _layer_names(layers, fila)
        names = QtWidgets.QLabel(_layers_text(all_names))
        names.setWordWrap(True)
        names.setStyleSheet(f"color:{t.text_muted}; font-size:11px;")
        col.addWidget(names)
        lay.addLayout(col, 1)
        tip = _row_tooltip(fila)
        if len(all_names) > MAX_NAMES:
            tip = _tr("Capas: {capas}").format(capas=", ".join(all_names)) + "\n" + tip
        w.setToolTip(tip)
        label = "{u} — {s}".format(u=util_name, s=status)
        w.activated.connect(lambda f=fila, lb=label: self.activated.emit(
            {"utility": f.utilidad, "layers": list(f.capas), "role": f.rol, "label": lb}))
        return w
