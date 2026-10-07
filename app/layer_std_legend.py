"""layer_std_legend.py — «Leyenda de esta hoja» POR UTILIDAD en «Capas de la hoja».

Pedidos del usuario 2026-10-07: (1) DU06 no trae leyenda → armarla con el manual BOE y
las líneas de la hoja; (2) DU08 h.26: «ubicarlas e interpretarlas», en TODAS las
utilidades, también cuando el PDF trae su leyenda — antes la del PDF iba sola y las
«E», «TE» y «SE» eléctricas no se marcaban con ninguna fila (`leyenda_estandar.leyenda`).
Por utilidad: una cabecera (cuadrito, nombre y abreviatura BOE) y una fila por tipo de
línea —la muestra y la descripción de la leyenda del PDF que le corresponde, o, sin ella,
una muestra dibujada (su color, a trazos si es existente y continua si es propuesta, las
letras leídas y «//» si va a demoler) con su estado BOE—, las aéreas («no se reconoce»)
y sus estructuras. CASILLAS (3.er pedido, 2026-10-07: «activar más de una utilidad… que
se resalten las activas, ahorita no sé cuál está activa»): la de la cabecera marca toda
la utilidad (lo que se reconocerá: líneas y estructuras), la de cada fila ese tipo de
línea; un clic en la cabecera o en la fila es lo mismo. Todo lo marcado se resalta JUNTO
en la hoja (`changed` → `active_specs`, lo dibuja `layer_dialog_info`) y aquí queda con
borde y fondo del color de su utilidad.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr
from recognition_summary_view import utility_swatch
from ui_common import layer_qcolor
import leyenda_estandar as le
import pdf_layers
import recognition
import theme as _theme

SAMPLE_W, SAMPLE_H = 76, 20
MAX_NAMES = 3            # capas que se nombran en una fila (las demás, en el tooltip)


def sample_color(utility: str) -> QtGui.QColor:
    """Color de la utilidad sobre papel blanco (el blanco del drenaje, en gris)."""
    c = QtGui.QColor(layer_qcolor(utility or "OTRAS"))
    return QtGui.QColor(90, 90, 90) if c.lightness() > 200 else c


class LineSample(QtWidgets.QWidget):
    """Muestra dibujada de la línea de una fila, sobre papel blanco como la hoja."""

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
        pen = QtGui.QPen(color, 1.0 if f.rol == le.OVERHEAD else 1.6)
        pen.setCapStyle(QtCore.Qt.FlatCap)
        if not f.continua:
            pen.setDashPattern([4.0, 2.0])
        text = "oh" if f.rol == le.OVERHEAD else (f.letras[0] if f.letras else "")
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


def status_text(fila: le.Fila) -> str:
    if fila.rol == le.STRUCTURE:
        name = le.STRUCTURES.get(fila.utilidad, ("", "", le.STRUCTURE_OTHER))[2]
        return _tr(name)
    key = le.nombre_estado(fila.estado)
    st = _tr(key).format(n=fila.estado) if fila.estado.isdigit() else _tr(key)
    return _tr("Aérea · {estado}").format(estado=st) if fila.rol == le.OVERHEAD else st


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


def _row_tooltip(fila: le.Fila, texts: List[str]) -> str:
    lines = []
    if texts:
        lines.append(_tr("Leyenda del PDF: {d}").format(d=" · ".join(texts)))
    if fila.rol == le.OVERHEAD:
        lines.append(_tr("Línea AÉREA: se ve con su utilidad en «Capas del plano», pero no se reconoce "
                         "(la app reconoce las subterráneas)."))
    elif fila.rol == le.LINE:
        if fila.origen == le.FROM_NAME:
            lines.append(_tr("Estado «{c}» del nombre de la capa (BOE §8.1.6).").format(c=fila.estado))
        elif fila.origen == le.FROM_XREF:
            lines.append(_tr("Estado tomado del nombre del xref de la capa."))
        elif fila.origen == le.FROM_LEGEND:
            lines.append(_tr("Estado según la leyenda del PDF para esas letras."))
        elif fila.origen == le.FROM_LETTERS:
            lines.append(_tr("El nombre no dice el estado: letras en MAYÚSCULA = propuesta, en "
                             "minúscula = existente (leyendas de los planos)."))
        if fila.marcas:
            lines.append(_tr("«{m}» sobre la línea = a abandonar / abandonada.").format(m=fila.marcas))
        if fila.continua and not texts:
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


def accent(utility: str) -> QtGui.QColor:
    """Color de la utilidad para marcar lo ACTIVO en el panel (el blanco del drenaje, en
    gris si el tema es claro)."""
    c = QtGui.QColor(layer_qcolor(utility or "OTRAS"))
    dark = QtGui.QColor(_theme.tokens().surface).lightness() < 128
    return QtGui.QColor(110, 110, 110) if (c.lightness() > 200 and not dark) else c


ACTIVE_TINT = 0.22       # cuánto color de la utilidad lleva el fondo de lo activo


def active_qss(name: str, color: QtGui.QColor) -> str:
    """Marco ACTIVO de una tarjeta o fila: borde y fondo del color de su utilidad. El fondo
    es OPACO (la tarjeta de siempre mezclada con el color): no depende de lo que haya
    detrás y el texto del tema se sigue leyendo en claro y en oscuro."""
    base = QtGui.QColor(_theme.tokens().surface_alt)
    mix = QtGui.QColor(*(round(getattr(base, ch)() * (1 - ACTIVE_TINT) + getattr(color, ch)() * ACTIVE_TINT)
                         for ch in ("red", "green", "blue")))
    return (f"#{name} {{ background:{mix.name()}; border:2px solid {color.name()}; border-radius:6px; }}"
            f" #{name} QLabel {{ background:transparent; border:none; }}")


def _row_qss(dim: bool, active: bool, color: QtGui.QColor) -> str:
    if active:
        return active_qss("stdRow", color)
    t = _theme.tokens()
    base = (f"background:transparent; border:1px dashed {t.border};" if dim
            else f"background:{t.surface_alt}; border:1px solid {t.border_soft};")
    return (f"#stdRow {{ {base} border-radius:6px; }}"
            f" #stdRow:hover {{ border:1px solid {t.text_muted}; }}"
            " #stdRow QLabel { background:transparent; border:none; }")


def _head_qss(active: bool, color: QtGui.QColor) -> str:
    if active:
        return active_qss("stdHead", color)
    t = _theme.tokens()
    return ("#stdHead { background:transparent; border:1px solid transparent; border-radius:6px; }"
            f" #stdHead:hover {{ border:1px solid {t.text_muted}; }}"
            " #stdHead QLabel { background:transparent; border:none; }")


class StandardLegend(QtWidgets.QWidget):
    """Leyenda de la hoja por utilidad, con CASILLAS (ver el docstring del módulo).
    `changed()`: cambió lo marcado; `active_specs()` = lo que hay que resaltar."""
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.groups: List[le.Grupo] = []
        self._pdf: list = []
        self._rows: Dict[tuple, dict] = {}          # clave → {w, chk, fila, label, dim}
        self._heads: Dict[str, dict] = {}           # utilidad → {w, chk, name, keys}
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0); self._lay.setSpacing(4)

    def set_layers(self, layers: List[dict], pdf: Optional[list] = None) -> None:
        """Capas de la hoja ya con la decisión «Usar» aplicada (`without_letters`); `pdf`
        = filas de la leyenda del PDF [(fuente, LegendRow)]. Lo marcado se conserva si la
        fila sigue (misma utilidad, capas y rol); no avisa (`changed`): decide el panel."""
        keep = set(self.active_keys())
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget() is not None:
                it.widget().hide()                 # hasta que se borre no debe verse encima
                it.widget().deleteLater()
        self._rows, self._heads = {}, {}
        self._pdf = list(pdf or [])
        self.groups = le.leyenda(layers, pdf_rows=[r for _s, r in self._pdf] or None)
        t = _theme.tokens()
        for g in self.groups:
            name = _tr(recognition.utility_label(g.utilidad))
            head = _Clickable(); head.setObjectName("stdHead")
            head.setCursor(QtCore.Qt.PointingHandCursor)
            hl = QtWidgets.QHBoxLayout(head); hl.setContentsMargins(4, 4, 4, 2); hl.setSpacing(6)
            chk = QtWidgets.QCheckBox()
            chk.setToolTip(_tr("Ver en la hoja todas sus líneas y estructuras"))
            chk.clicked.connect(lambda _c=False, u=g.utilidad: self.toggle_utility(u))
            hl.addWidget(chk, 0)
            sw = QtWidgets.QLabel(); sw.setPixmap(utility_swatch(layer_qcolor(g.utilidad), 12))
            hl.addWidget(sw, 0)
            lb = QtWidgets.QLabel(name)
            f = lb.font(); f.setBold(True); lb.setFont(f)
            lb.setStyleSheet(f"color:{t.text};")
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
            head.activated.connect(lambda u=g.utilidad: self.toggle_utility(u))
            self._lay.addWidget(head)
            self._heads[g.utilidad] = {"w": head, "chk": chk, "name": name, "keys": []}
            for fila in g.filas:
                key = ("std", fila.utilidad, tuple(fila.capas), fila.rol)
                self._heads[g.utilidad]["keys"].append(key)
                self._lay.addWidget(self._row(layers, fila, name, key, key in keep))
            self._refresh_head(g.utilidad)

    # ── lo marcado ──
    def active_keys(self) -> List[tuple]:
        return [k for k, r in self._rows.items() if r["chk"].isChecked()]

    def active_specs(self) -> List[dict]:
        """Lo que hay que resaltar: un spec por fila marcada (`_utility_sets`)."""
        out = []
        for k in self.active_keys():
            f = self._rows[k]["fila"]
            out.append({"utility": f.utilidad, "layers": list(f.capas), "role": f.rol,
                        "label": self._rows[k]["label"]})
        return out

    def summary(self) -> List[str]:
        """Qué está marcado, corto: la utilidad entera por su nombre, si no cada fila."""
        out = []
        for u, h in self._heads.items():
            on = [k for k in h["keys"] if self._rows[k]["chk"].isChecked()]
            rec = [k for k in h["keys"] if k[3] != le.OVERHEAD]
            if rec and all(k in on for k in rec):
                out.append(h["name"])
                on = [k for k in on if k not in rec]
            out += [self._rows[k]["label"] for k in on]
        return out

    def clear(self) -> None:
        """Desmarca todo, sin avisar."""
        for k, r in self._rows.items():
            if r["chk"].isChecked():
                self._set(k, False)
        for u in self._heads:
            self._refresh_head(u)

    def toggle_utility(self, utility: str) -> None:
        """Casilla (o clic) de la utilidad: si estaba entera, la desmarca (también sus
        aéreas); si no, marca todo lo que se reconocerá (sus líneas y estructuras)."""
        h = self._heads.get(utility)
        if h is None:
            return
        rec = [k for k in h["keys"] if k[3] != le.OVERHEAD]
        whole = bool(rec) and all(self._rows[k]["chk"].isChecked() for k in rec)
        for k in h["keys"]:
            if whole:
                self._set(k, False)
            elif k in rec:
                self._set(k, True)
        self._refresh_head(utility)
        self.changed.emit()

    def set_row(self, key: tuple, on: bool) -> None:
        if key in self._rows:
            self._rows[key]["chk"].setChecked(on)

    def _set(self, key: tuple, on: bool) -> None:
        r = self._rows[key]
        r["chk"].blockSignals(True); r["chk"].setChecked(on); r["chk"].blockSignals(False)
        r["w"].setStyleSheet(_row_qss(r["dim"], on, accent(key[1])))

    def _on_row(self, key: tuple, on: bool) -> None:
        r = self._rows[key]
        r["w"].setStyleSheet(_row_qss(r["dim"], on, accent(key[1])))
        self._refresh_head(key[1])
        self.changed.emit()

    def _refresh_head(self, utility: str) -> None:
        h = self._heads[utility]
        rec = [k for k in h["keys"] if k[3] != le.OVERHEAD]
        on = [k for k in h["keys"] if self._rows[k]["chk"].isChecked()]
        whole = bool(rec) and all(k in on for k in rec)
        state = (QtCore.Qt.Checked if whole else QtCore.Qt.PartiallyChecked if on else QtCore.Qt.Unchecked)
        chk = h["chk"]
        chk.blockSignals(True)
        chk.setTristate(state == QtCore.Qt.PartiallyChecked)
        chk.setCheckState(state)
        chk.blockSignals(False)
        h["w"].setStyleSheet(_head_qss(bool(on), accent(utility)))

    # ── cruce con la leyenda del PDF ──
    def matched(self) -> set:
        """Índices (en `pdf`) de las filas de la leyenda del PDF que hay en esta hoja."""
        return {i for g in self.groups for f in g.filas for i in f.pdf}

    def filas_de_pdf(self, i: int) -> List[le.Fila]:
        return [f for g in self.groups for f in g.filas if i in f.pdf]

    def _row(self, layers, fila: le.Fila, util_name: str, key: tuple, on: bool) -> QtWidgets.QWidget:
        t = _theme.tokens()
        dim = fila.rol == le.OVERHEAD
        w = _Clickable(); w.setObjectName("stdRow"); w.setStyleSheet(_row_qss(dim, on, accent(fila.utilidad)))
        w.setCursor(QtCore.Qt.PointingHandCursor)
        lay = QtWidgets.QHBoxLayout(w); lay.setContentsMargins(6, 4, 6, 4); lay.setSpacing(6)
        chk = QtWidgets.QCheckBox()
        chk.setChecked(on)
        chk.setToolTip(_tr("Ver estas líneas en la hoja"))
        lay.addWidget(chk, 0, QtCore.Qt.AlignTop)
        texts = [self._pdf[i][1].text for i in fila.pdf]
        # muestra DIBUJADA (las letras leídas, legibles): la del PDF reducida a este
        # tamaño no deja ver las letras; va entera en la «Leyenda completa del PDF»
        lay.addWidget(LineSample(fila), 0, QtCore.Qt.AlignTop)
        col = QtWidgets.QVBoxLayout(); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(1)
        status = status_text(fila)
        title = texts[0] if texts else status
        top = QtWidgets.QLabel(title)
        top.setWordWrap(True)
        top.setStyleSheet(f"color:{t.text_muted if dim else t.text}; font-size:{11 if texts else 12}px;")
        col.addWidget(top)
        all_names = _layer_names(layers, fila)
        sub = _layers_text(all_names)
        if texts:
            sub = _tr("{estado} · {capas}").format(estado=status, capas=sub)
        names = QtWidgets.QLabel(sub)
        names.setWordWrap(True)
        names.setStyleSheet(f"color:{t.text_muted}; font-size:11px;")
        col.addWidget(names)
        if dim:
            note = QtWidgets.QLabel(_tr("No se reconoce"))
            note.setStyleSheet(f"color:{t.text_muted}; font-size:11px; font-style:italic;")
            col.addWidget(note)
        lay.addLayout(col, 1)
        tip = _row_tooltip(fila, texts)
        if len(all_names) > MAX_NAMES:
            tip = _tr("Capas: {capas}").format(capas=", ".join(all_names)) + "\n" + tip
        w.setToolTip(tip)
        label = "{u} — {s}".format(u=util_name, s=title)
        self._rows[key] = {"w": w, "chk": chk, "fila": fila, "label": label, "dim": dim}
        chk.toggled.connect(lambda v, k=key: self._on_row(k, v))
        w.activated.connect(chk.toggle)
        return w
