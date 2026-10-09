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
borde y fondo del color de su utilidad. Al pasar el ratón, el tooltip trae la muestra en
GRANDE (4.º pedido, mismo día: «la miniatura más grandecita») y, si la leyenda del PDF
describe la fila, también su muestra recortada del PDF (`tooltip_html`).
"""
from __future__ import annotations

import html
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.asistente.recognition_summary_view import utility_swatch
from ui.comun.ui_common import layer_qcolor
from hoja import leyenda_estandar as le
from hoja import pdf_layers
from reconocimiento import recognition
from ui.comun import theme as _theme

SAMPLE_W, SAMPLE_H = 76, 20
TIP_SCALE = 3.0          # la muestra en el tooltip: 3× la de la fila
TIP_PDF_MAX_W = 480      # …y la del PDF (render a 3×), como mucho este ancho (px)
LEGEND_RENDER_ZOOM = 3.0  # zoom del render de la leyenda del PDF (`LegendWorker`)
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
        p = QtGui.QPainter(self)
        paint_sample(p, self.fila, self.width(), self.height())
        p.end()


def paint_sample(p: QtGui.QPainter, f: le.Fila, w: float, h: float, k: float = 1.0) -> None:
    """Dibuja la muestra de la fila `f` en un rectángulo w×h; `k` = escala de trazos y
    letras (1 en la fila, `TIP_SCALE` en el tooltip)."""
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor("white"))
    p.drawRoundedRect(QtCore.QRectF(0, 0, w, h), 3 * k, 3 * k)
    color = sample_color(f.utilidad)
    y, m = h / 2.0, 4 * k
    if f.rol == le.STRUCTURE:
        p.setPen(QtGui.QPen(color, 1.6 * k)); p.setBrush(QtCore.Qt.NoBrush)
        p.drawLine(QtCore.QPointF(m, y), QtCore.QPointF(w / 2 - 9 * k, y))
        p.drawRect(QtCore.QRectF(w / 2 - 9 * k, y - 6 * k, 18 * k, 12 * k))
        p.drawLine(QtCore.QPointF(w / 2 + 9 * k, y), QtCore.QPointF(w - m, y))
        return
    pen = QtGui.QPen(color, (1.0 if f.rol == le.OVERHEAD else 1.6) * k)
    pen.setCapStyle(QtCore.Qt.FlatCap)
    if not f.continua:
        pen.setDashPattern([4.0, 2.0])                 # en anchos de trazo: escala sola
    text = "oh" if f.rol == le.OVERHEAD else (f.letras[0] if f.letras else "")
    font = p.font(); font.setPixelSize(max(1, round(11 * k))); font.setBold(True); p.setFont(font)
    tw = QtGui.QFontMetricsF(font).horizontalAdvance(text) if text else 0.0
    cx = w * 0.62
    gap = tw + 6 * k if text else 0.0
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(m, y), QtCore.QPointF(cx - gap / 2, y))
    p.drawLine(QtCore.QPointF(cx + gap / 2, y), QtCore.QPointF(w - m, y))
    if text:
        p.setPen(color)
        p.drawText(QtCore.QRectF(cx - gap / 2, 0, gap, h), QtCore.Qt.AlignCenter, text)
    if f.marcas:
        p.setPen(QtGui.QPen(color, 1.4 * k))
        x0 = w * 0.24
        for i in range(len(f.marcas)):
            x = x0 + i * 4 * k
            p.drawLine(QtCore.QPointF(x - 2.5 * k, y + 5 * k), QtCore.QPointF(x + 2.5 * k, y - 5 * k))


def sample_pixmap(f: le.Fila, k: float = TIP_SCALE) -> QtGui.QPixmap:
    """La muestra de la fila en GRANDE (para el tooltip), nítida en pantallas HiDPI."""
    w, h, dpr = round(SAMPLE_W * k), round(SAMPLE_H * k), 2.0
    pm = QtGui.QPixmap(int(w * dpr), int(h * dpr)); pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    paint_sample(p, f, w, h, k)
    p.end()
    return pm


def pdf_sample(src: dict, row, cache: Optional[dict] = None) -> Optional[QtGui.QPixmap]:
    """Muestra de una fila de la leyenda del PDF, recortada del render de su hoja que trae
    `LegendWorker` (`src["images"]`: {hoja: (png, región)}) — a `LEGEND_RENDER_ZOOM`."""
    img = (src or {}).get("images", {}).get(row.page)
    if not img:
        return None
    cache = {} if cache is None else cache
    key = (id(src), row.page)
    if key not in cache:
        pm = QtGui.QPixmap()
        pm.loadFromData(img[0], "PNG")
        cache[key] = pm
    pm = cache[key]
    x0, y0, _x1, _y1 = img[1]
    k = LEGEND_RENDER_ZOOM
    s = row.sample
    return pm.copy(QtCore.QRect(int((s[0] - 2 - x0) * k), int((s[1] - 2 - y0) * k),
                                int((s[2] - s[0] + 4) * k), int((s[3] - s[1] + 4) * k)))


def img_html(pm: Optional[QtGui.QPixmap], max_w: int = 0) -> str:
    """`<img>` con la imagen incrustada (data URI: el tooltip de Qt la muestra), a su tamaño
    lógico o reducida a `max_w` px de ancho."""
    if pm is None or pm.isNull():
        return ""
    dpr = max(pm.devicePixelRatio(), 1.0)
    w, h = pm.width() / dpr, pm.height() / dpr
    if max_w and w > max_w:
        w, h = max_w, h * max_w / w
    ba = QtCore.QByteArray()
    buf = QtCore.QBuffer(ba); buf.open(QtCore.QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    b64 = bytes(ba.toBase64()).decode("ascii")
    return f"<img src='data:image/png;base64,{b64}' width='{round(w)}' height='{round(h)}'>"


def tooltip_html(images: List[str], text: str) -> str:
    """Tooltip con imágenes arriba (cada una en su línea, con su rótulo) y el texto debajo."""
    body = "".join(f"<div style='margin-bottom:6px'>{im}</div>" for im in images if im)
    lines = "<br>".join(html.escape(x) for x in (text or "").split("\n"))
    return f"<div>{body}<div>{lines}</div></div>"


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
        self._crops: dict = {}                     # render de la leyenda por hoja (para los tooltips)
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

    def _tip_images(self, fila: le.Fila, crops: dict) -> List[str]:
        """La muestra en grande y, si la leyenda del PDF describe la fila, la suya."""
        out = [img_html(sample_pixmap(fila))]
        for i in fila.pdf[:2]:
            src, row = self._pdf[i]
            pm = pdf_sample(src, row, crops)
            if pm is not None and not pm.isNull():
                cap = html.escape(_tr("Muestra en la leyenda del PDF:"))
                out.append(f"<span style='font-size:11px'>{cap}</span><br>"
                           + "<span style='background:white'>" + img_html(pm, TIP_PDF_MAX_W) + "</span>")
        return out

    def _row(self, layers, fila: le.Fila, util_name: str, key: tuple, on: bool) -> QtWidgets.QWidget:
        t = _theme.tokens()
        dim = fila.rol == le.OVERHEAD
        w = _Clickable(); w.setObjectName("stdRow"); w.setStyleSheet(_row_qss(dim, on, accent(fila.utilidad)))
        w.setCursor(QtCore.Qt.PointingHandCursor)
        # casilla | muestra | descripción en la 1.ª línea; estado y capas DEBAJO, desde la
        # muestra hasta el borde (pedido del usuario 2026-10-09: con todo a la derecha de la
        # muestra el texto se partía en una columna angosta y bajo la muestra quedaba vacío)
        lay = QtWidgets.QGridLayout(w); lay.setContentsMargins(6, 4, 6, 4)
        lay.setHorizontalSpacing(6); lay.setVerticalSpacing(2)
        chk = QtWidgets.QCheckBox()
        chk.setChecked(on)
        chk.setToolTip(_tr("Ver estas líneas en la hoja"))
        # a lo alto de toda la fila: la casilla es más alta que la muestra y, en la 1.ª
        # línea sola, dejaba un hueco antes del estado y las capas
        lay.addWidget(chk, 0, 0, 3, 1, QtCore.Qt.AlignTop)
        texts = [self._pdf[i][1].text for i in fila.pdf]
        # muestra DIBUJADA (las letras leídas, legibles): la del PDF reducida a este
        # tamaño no deja ver las letras; va entera en la «Leyenda completa del PDF»
        lay.addWidget(LineSample(fila), 0, 1, QtCore.Qt.AlignVCenter)
        status = status_text(fila)
        title = texts[0] if texts else status
        top = QtWidgets.QLabel(title)
        top.setWordWrap(True)
        top.setStyleSheet(f"color:{t.text_muted if dim else t.text}; font-size:{11 if texts else 12}px;")
        lay.addWidget(top, 0, 2)
        all_names = _layer_names(layers, fila)
        sub = _layers_text(all_names)
        if texts:
            sub = _tr("{estado} · {capas}").format(estado=status, capas=sub)
        names = QtWidgets.QLabel(sub)
        names.setWordWrap(True)
        names.setStyleSheet(f"color:{t.text_muted}; font-size:11px;")
        lay.addWidget(names, 1, 1, 1, 2)
        if dim:
            note = QtWidgets.QLabel(_tr("No se reconoce"))
            note.setStyleSheet(f"color:{t.text_muted}; font-size:11px; font-style:italic;")
            lay.addWidget(note, 2, 1, 1, 2)
        lay.setColumnStretch(2, 1)
        tip = _row_tooltip(fila, texts)
        if len(all_names) > MAX_NAMES:
            tip = _tr("Capas: {capas}").format(capas=", ".join(all_names)) + "\n" + tip
        w.setToolTip(tooltip_html(self._tip_images(fila, self._crops), tip))
        label = "{u} — {s}".format(u=util_name, s=title)
        self._rows[key] = {"w": w, "chk": chk, "fila": fila, "label": label, "dim": dim}
        chk.toggled.connect(lambda v, k=key: self._on_row(k, v))
        w.activated.connect(chk.toggle)
        return w
