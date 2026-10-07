"""layer_dialog_info.py — `LayerInfoMixin` de «Capas de la hoja»: el panel IZQUIERDO
(`layer_info_panel.LayerInfoPanel`) dentro del diálogo.

  · Tres columnas, como la vista previa: «Leyenda» (plegable) | hoja | capas.
  · «Usar» de una capa reconocida por sus letras → `self._letters_off` y el árbol se
    rearma con `pdf_layers.without_letters` (la capa vuelve a su grupo por nombre).
  · Resaltar en la hoja (clic en una tarjeta, en una fila de la leyenda o en una
    utilidad de la leyenda del estándar): las líneas de esas capas —en una capa
    mezclada, solo las de esa utilidad— con el color de su utilidad, el resto de la hoja
    atenuado y la vista encuadrada en ellas. La tarjeta de una capa por sus letras
    muestra además, en línea fina, el RESTO de las líneas de su utilidad (2.º pedido
    2026-10-07: junto a las «T» de G-XREF iban las «t» de C-TELE-UNGD-E, también telecom
    al importar, y no se veían). Qué trazo es de qué utilidad: `leyenda_estandar`.
  · La leyenda del PDF se lee en otro hilo (`LegendWorker`) y queda en `legend_cache`
    (de la ventana principal): al volver a este paso ya está.
El diálogo aporta `self.split` (vista | panel derecho), `self.view`, `self._page`,
`self._doc`, `self._layers_raw`, `self._layers`, `self._letters_off`, `hidden_names()`,
`_fill_list()` y `_refresh_recog_checks()`.
"""
from __future__ import annotations

from collections import defaultdict

from PySide6 import QtCore, QtGui, QtWidgets

import fitz

from busy import busy
from i18n import t as _tr
from layer_info_panel import LayerInfoPanel, LegendWorker
from ui_common import layer_qcolor
from widgets import CollapsiblePanel, NaturalHeightScroll
import leyenda_estandar as le
import leyenda_trazos
import pdf_layers
import recognition_letters as letters_mod
from recognition import utility_label as _utility_label
import theme as _theme

INFO_MIN_W = 260
DIM_ALPHA = 175          # velo sobre la hoja mientras se resalta (0–255)


def _sources_key(sources) -> tuple:
    return tuple((s.get("name", ""), len(s.get("data") or b""), s.get("path") or "") for s in sources)


def _qpath(d: dict, matrix, zoom: float) -> QtGui.QPainterPath:
    """Trazo de `get_drawings` → QPainterPath en coordenadas de la escena (render a `zoom`)."""
    def P(q):
        p = fitz.Point(q) * matrix
        return QtCore.QPointF(p.x * zoom, p.y * zoom)
    path = QtGui.QPainterPath()
    last = None
    for it in d.get("items") or ():
        kind = it[0]
        if kind == "l":
            a, b = P(it[1]), P(it[2])
            if last is None or (a - last).manhattanLength() > 0.01:
                path.moveTo(a)
            path.lineTo(b)
            last = b
        elif kind == "c":
            a = P(it[1])
            if last is None or (a - last).manhattanLength() > 0.01:
                path.moveTo(a)
            last = P(it[4])
            path.cubicTo(P(it[2]), P(it[3]), last)
        elif kind == "re":
            r = it[1]
            path.addPolygon(QtGui.QPolygonF([P((r.x0, r.y0)), P((r.x1, r.y0)), P((r.x1, r.y1)),
                                             P((r.x0, r.y1)), P((r.x0, r.y0))]))
            last = None
        elif kind == "qu":
            q = it[1]
            path.addPolygon(QtGui.QPolygonF([P(q.ul), P(q.ur), P(q.lr), P(q.ll), P(q.ul)]))
            last = None
    return path


def layer_tooltip(L: dict) -> str:
    """Nombre completo de la capa y, si va a su grupo por las LETRAS de su línea,
    por qué (`pdf_layers.page_layers` → `letters`, `letter_utilities`, `name_utility`)."""
    tip = L["name"]
    utils = list(L.get("letter_utilities") or ())
    if not L.get("letters") or not utils:
        return tip
    names = ", ".join(_tr(_utility_label(u)) for u in utils)
    if L.get("name_utility"):
        why = _tr("Su nombre dice {n}, pero las letras de su línea («{c}») dicen {u}: se reconoce "
                  "como {u}.").format(n=_tr(_utility_label(L["name_utility"])),
                                      c=L["letters"], u=names)
    elif len(utils) > 1:
        codes = L.get("letter_codes") or {}
        each = ", ".join("«{c}» {u}".format(c=codes.get(u, "?"), u=_tr(_utility_label(u)))
                         for u in utils)
        why = _tr("Capa con líneas de varias utilidades ({u}). Cada línea se reconoce "
                  "por sus letras.").format(u=each)
    else:
        why = _tr("Su nombre no es de ninguna utilidad, pero las letras de su línea («{c}») "
                  "dicen {u}: se reconoce como {u}.").format(c=L["letters"], u=names)
    return f"{tip}\n{why}"


class LayerInfoMixin:
    """Panel izquierdo «Leyenda» del diálogo de capas (ver el docstring del módulo)."""

    def _build_info_panel(self, legend_sources=None, legend_cache=None):
        t = _theme.tokens()
        self.info = LayerInfoPanel()
        self.info.includeChanged.connect(self._on_letters_toggled)
        self.info.focusRequested.connect(self._focus_lines)
        self.info_box = CollapsiblePanel(_tr("Leyenda"))
        self.info_box.setObjectName("layerCard")
        self.info_box.setStyleSheet(f"QFrame#layerCard {{ background:{t.surface}; border:1px solid {t.border};"
                                    " border-radius:8px; }")
        self.info_box.body_layout.addWidget(NaturalHeightScroll(self.info), 1)
        self.info_box.setMinimumWidth(INFO_MIN_W)
        self.info_box.toggled.connect(self._on_info_toggled)
        self.split.insertWidget(0, self.info_box)
        self.split.setStretchFactor(0, 0); self.split.setStretchFactor(1, 1); self.split.setStretchFactor(2, 0)
        self._hl_items: list = []
        self._drawings = None                 # (trazo, lo visible) de las capas de utilidad (para resaltar)
        self._legend_worker = None
        self.info.visible_layers = self._visible_layers      # la leyenda del estándar: solo lo que se ve
        self.info.set_layers(self._layers_raw, self._letters_off)
        self._legend_cache = legend_cache if legend_cache is not None else {}
        sources = [s for s in (legend_sources or []) if s.get("data") or s.get("path")]
        key = _sources_key(sources)
        if not sources:
            self.info.set_legend([])
        elif key in self._legend_cache:
            self.info.set_legend(self._legend_cache[key])
        else:
            cache = self._legend_cache
            parent = self.parent() if isinstance(self.parent(), QtCore.QObject) else None
            worker = LegendWorker(sources, parent or self)
            worker.done.connect(lambda res, c=cache, k=key: c.__setitem__(k, res))
            worker.done.connect(self._on_legend)
            worker.finished.connect(worker.deleteLater)
            self._legend_worker = worker
            worker.start()
        self._auto_collapse_info()

    # ── decisiones y datos ──
    def letters_off(self) -> list:
        """Capas que el usuario decidió NO reconocer por las letras de su línea."""
        return sorted(self._letters_off)

    def _on_letters_toggled(self, name: str, used: bool):
        (self._letters_off.discard if used else self._letters_off.add)(name)
        hidden = set(self.hidden_names())
        open_groups = {k for k, g in self._groups.items() if g.isExpanded()}
        self._layers = [dict(L, on=L["name"] not in hidden)
                        for L in pdf_layers.without_letters(self._layers_raw, self._letters_off)]
        self._fill_list()
        for k in open_groups:
            if k in self._groups:
                self._groups[k].setExpanded(True)
        self._refresh_recog_checks()

    def _on_legend(self, results):
        self._legend_worker = None
        self.info.set_legend(results)
        self._auto_collapse_info()

    def _auto_collapse_info(self):
        """Sin capas por letras ni leyenda en el PDF, el panel se pliega: la hoja gana sitio."""
        empty = (not any(L.get("letter_utilities") for L in self._layers_raw) and self.info._legend == []
                 and not self.info.standard_groups())
        if empty and not self.info_box.collapsed:
            self.info_box.set_collapsed(True)

    def _info_reload(self):
        """Cambió la hoja (◀ ▶): tarjetas y leyenda con las capas de la nueva."""
        self._clear_focus()
        self._drawings = None
        self.info.set_layers(self._layers_raw, self._letters_off)

    def _stop_legend(self):
        worker = self._legend_worker
        if worker is not None:
            try:
                worker.done.disconnect(self._on_legend)   # sigue llenando la caché si no terminó
            except (RuntimeError, TypeError):
                pass
            if worker.parent() is self:                   # sin ventana principal: esperarlo
                worker.requestInterruption()
                worker.wait(5000)
        self._legend_worker = None

    # ── resaltar en la hoja ──
    def _all_drawings(self):
        """(trazo, lo que se ve de él) de las capas de utilidad y por letras, con TODAS las
        capas encendidas y recortado como lo toma el reconocimiento
        (`leyenda_estandar.trazos_visibles`). Una vez por hoja."""
        if self._drawings is None:
            pdf_layers.set_hidden(self._doc, ())
            try:
                self._drawings = leyenda_trazos.trazos_visibles(self._page, le.capas_de_utilidad(self._layers_raw))
            finally:
                pdf_layers.set_hidden(self._doc, self.hidden_names())
        return self._drawings

    def _visible_layers(self) -> set:
        """Capas con algo visible en la hoja (lo recortado por la vista no cuenta)."""
        return {d.get("layer") or "" for d, _shown in self._all_drawings()}

    def _layer_of(self, eff: dict, name: str):
        """La capa (con la decisión «Usar») o, si no está en la lista del PDF, una por nombre."""
        L = eff.get(name)
        if L is None and name not in eff:
            L = eff[name] = le.capa_sin_lista(name)
        return L

    def _remove_highlight(self):
        sc = self.view.scene()
        for it in self._hl_items:
            sc.removeItem(it)
        self._hl_items = []

    def _clear_focus(self):
        self._remove_highlight()
        self.info.clear_focus()

    def _escape(self) -> bool:
        """Esc (la ventana no se cierra: `NoEscapeClose`) quita el resaltado de la leyenda."""
        if not self._hl_items:
            return False
        self._clear_focus()
        return True

    def _focus_lines(self, spec):
        """Resalta lo ACTIVO en el panel izquierdo; None = quitar el resaltado. `spec` =
        {"specs": [...], "label": [...]} (todo lo marcado, junto: 3.er pedido 2026-10-07,
        «activar más de una utilidad») o uno solo:
          · {"layers": [capa]} (tarjeta por letras): sus líneas con halo y, en línea fina,
            el resto de las líneas de su utilidad que se reconocerán;
          · {"codes": [...], "raw": letras}: fila de la leyenda del PDF;
          · {"utility": U[, "layers": [...], "role": rol], "label": texto}: leyenda por
            utilidad — toda la utilidad (sus capas visibles) o esas capas."""
        self._remove_highlight()
        if not spec or self._pix_item is None:
            self.info.set_focus_status("")
            return
        if self._drawings is None:
            with busy(self.view, _tr("Leyendo las líneas de la hoja…")):
                self._all_drawings()
        strong, soft, what = self._union_sets(spec)
        self.info.set_focus_status(_tr("Resaltado: {what}").format(what=what))
        if not strong:
            return                                  # lo marcado no tiene líneas visibles en esta hoja
        sc = self.view.scene()
        veil = QtWidgets.QGraphicsRectItem(self._pix_item.sceneBoundingRect())
        bg = QtGui.QColor(255, 255, 255, DIM_ALPHA)
        veil.setBrush(bg); veil.setPen(QtCore.Qt.NoPen); veil.setZValue(5)
        sc.addItem(veil)
        self._hl_items.append(veil)
        z = self._render_zoom()
        m = self._page.rotation_matrix
        box = QtCore.QRectF()
        for groups, styles in ((soft, ((1.4, 230, 6),)), (strong, ((7.0, 90, 6), (2.2, 255, 7)))):
            for util, drawings in groups.items():
                color = QtGui.QColor(layer_qcolor(util or "OTRAS"))
                if color.lightness() > 200:                 # drenaje blanco: que se vea sobre el velo
                    color = QtGui.QColor(90, 90, 90)
                whole = QtGui.QPainterPath()
                for d in drawings:
                    whole.addPath(_qpath(d, m, z))
                for width, alpha, zv in styles:
                    pen = QtGui.QPen(QtGui.QColor(color.red(), color.green(), color.blue(), alpha), width)
                    pen.setCosmetic(True); pen.setCapStyle(QtCore.Qt.RoundCap); pen.setJoinStyle(QtCore.Qt.RoundJoin)
                    item = QtWidgets.QGraphicsPathItem(whole)
                    item.setPen(pen); item.setBrush(QtCore.Qt.NoBrush); item.setZValue(zv)
                    sc.addItem(item)
                    self._hl_items.append(item)
                if groups is strong:
                    box = box.united(whole.boundingRect())
        pad = max(box.width(), box.height()) * 0.08 + 30
        self.view.fitInView(box.adjusted(-pad, -pad, pad, pad), QtCore.Qt.KeepAspectRatio)

    def _union_sets(self, spec):
        """(fuertes, finos, texto) de todo lo activo junto: cada trazo una vez, lo fuerte
        manda sobre lo fino; el texto, lo activo en corto + cuántas capas."""
        specs = spec["specs"] if "specs" in spec else [spec]
        strong, soft, whats, seen = defaultdict(list), defaultdict(list), [], set()
        for sp in specs:
            st, so, w = self._focus_sets(sp)
            whats.append(w)
            for u, ds in st.items():
                for d in ds:
                    if id(d) not in seen:
                        seen.add(id(d))
                        strong[u].append(d)
            for u, ds in so.items():
                soft[u].extend(ds)
        thin, done = defaultdict(list), set(seen)
        for u, ds in soft.items():
            for d in ds:
                if id(d) not in done:
                    done.add(id(d))
                    thin[u].append(d)
        if len(specs) == 1:
            return strong, thin, whats[0]
        labels = [x for x in (spec.get("label") or whats) if x]
        short = (" · ".join(labels) if len(labels) <= 3 else
                 _tr("{capas} y {n} más").format(capas=" · ".join(labels[:3]), n=len(labels) - 3))
        n = len({d.get("layer") for ds in strong.values() for d in ds})
        return strong, thin, _tr("{what} · {n} capas").format(what=short, n=n)

    def _focus_sets(self, spec):
        """(fuertes, finos, texto): trazos de `get_drawings` por utilidad a resaltar."""
        if "utility" in spec:
            return self._utility_sets(spec)
        strong, soft = defaultdict(list), defaultdict(list)
        by_name = {L["name"]: L for L in self._layers_raw}
        codes = set(spec.get("codes") or ())
        names = spec.get("layers") or [n for n, L in by_name.items() if codes & set(L.get("read_codes") or ())]
        raw = spec.get("raw") or ""
        if raw and not spec.get("layers"):          # fila de la leyenda: su variante («G» / «g»)
            exact = [n for n in names if any((by_name[n].get("letter_raw") or {}).get(c) == raw for c in codes)]
            names = exact or names
        want = {letters_mod.code_utility(c) for c in codes} - {None}
        mine = set()
        for d, shown in self._all_drawings():
            L = by_name.get(d.get("layer") or "")
            if L is None or L["name"] not in names:
                continue
            paths = L.get("letter_paths") or {}
            if paths:
                util = paths.get(letters_mod.path_key(d))
                if util is None or (want and util not in want):
                    continue
            else:
                util = (next(iter(want)) if want else
                        (L.get("letter_utilities") or [L.get("utility")])[0])
            strong[util].append(shown)
            mine.add(id(d))
        if codes:
            return strong, soft, "«{c}»".format(c=raw or ", ".join(sorted(codes)))
        # tarjeta: el resto de las líneas de su(s) utilidad(es), las que se reconocerán
        eff = {L["name"]: L for L in self._layers}
        hidden = set(self.hidden_names())
        for d, shown in self._all_drawings():
            L = self._layer_of(eff, d.get("layer") or "")
            if id(d) in mine or L["name"] in hidden:
                continue
            for util in strong:
                if le.es_trazo_de(L, util, d) == le.LINE:
                    soft[util].append(shown)
                    break
        utils = ", ".join(_tr(_utility_label(u)) for u in strong)
        shorts = ", ".join(pdf_layers.short_name(n) for n in names)
        what = (_tr("{capa} con halo; en línea fina, el resto de {u}").format(capa=shorts, u=utils)
                if soft else shorts)
        return strong, soft, what

    def _utility_sets(self, spec):
        """«Leyenda de esta hoja»: toda la utilidad —lo que se reconocerá: líneas y
        estructuras de las capas visibles, sin las aéreas— o las capas de una fila."""
        strong = defaultdict(list)
        util, role = spec["utility"], spec.get("role")
        roles = {role} if role else {le.LINE, le.STRUCTURE}
        names = set(spec.get("layers") or ())
        hidden = set(self.hidden_names())
        names = (names - hidden) or names           # una capa oculta no se reconoce (salvo que sean todas)
        eff = {L["name"]: L for L in self._layers}
        used = set()
        for d, shown in self._all_drawings():
            L = self._layer_of(eff, d.get("layer") or "")
            if L["name"] not in names if names else L["name"] in hidden:
                continue
            if le.es_trazo_de(L, util, d) not in roles:
                continue
            strong[util].append(shown)
            used.add(L["name"])
        label = spec.get("label") or _tr(_utility_label(util))
        what = label if names else _tr("{what} · {n} capas").format(what=label, n=len(used))
        return strong, {}, what

    def _render_zoom(self) -> float:
        rect = self._page.rect
        pm = self._pix_item.pixmap()
        return pm.width() / max(rect.width, 1e-6) if pm.width() else 3.0

    # ── tres columnas ──
    @staticmethod
    def _info_width(total: int) -> int:
        return max(INFO_MIN_W, min(320, int(total * 0.2)))

    def _apply_three_columns(self, side_w: int):
        w = self.split.width() or self.width()
        left = CollapsiblePanel.STRIP_W if self.info_box.collapsed else self._info_width(w)
        self.split.setSizes([left, max(200, w - left - side_w), side_w])

    def _on_info_toggled(self, collapsed: bool):
        """Plegar «Leyenda» le da su ancho a la hoja; desplegar lo recupera."""
        sizes = self.split.sizes()
        if collapsed:
            self._info_w = sizes[0]
            sizes[1] += max(0, sizes[0] - CollapsiblePanel.STRIP_W)
            sizes[0] = CollapsiblePanel.STRIP_W
        else:
            self.info_box.setMinimumWidth(INFO_MIN_W)
            want = getattr(self, "_info_w", 0) or self._info_width(sum(sizes))
            sizes[1] = max(200, sizes[1] - (want - sizes[0]))
            sizes[0] = want
        self.split.setSizes(sizes)
