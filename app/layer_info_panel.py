"""layer_info_panel.py — Panel IZQUIERDO del paso «Capas de la hoja».

Pedido del usuario 2026-10-05: «poner información de qué capas se reconocieron por el
texto y no por el nombre de la capa… algo corto… que el usuario tome la decisión de
incluirlas o no», y «una leyenda de capas de acuerdo al documento, para que conozca
cada una de esas capas». Dos secciones:

  · «Por las letras de su línea (N)»: una tarjeta por capa que va a su utilidad por
    las LETRAS de su linetype (`recognition.letter_uses`): utilidad y letras, la capa,
    por qué (su nombre no dice la utilidad / dice otra / línea por línea) y qué dice
    la leyenda del PDF de esas letras. La casilla «Usar» decide (`includeChanged`):
    desmarcada, la capa vuelve a su grupo por nombre y no se reconoce por sus letras.
  · «Leyenda de esta hoja» (`layer_std_legend`, pedidos del usuario 2026-10-07): POR
    UTILIDAD, cada tipo de línea que hay en la hoja con la descripción de la leyenda
    del propio PDF (`pdf_legend`, leída en otro hilo: `LegendWorker`, ~4 s por PDF) o,
    si no trae (DU06), la del estándar BOE; y debajo, plegada, la «Leyenda completa del
    PDF» (en negrita las filas que hay en esta hoja; clic = sus líneas).
Lo que se ve en la hoja se ELIGE con casillas y clics que se SUMAN (3.er pedido, 2026-10-07:
«activar más de una utilidad» y saber cuál está activa): las de la leyenda por utilidad,
las tarjetas por letras y las filas de la leyenda completa; otro clic quita esa. Todo lo
activo se resalta junto (`focusRequested({"specs": [...], "label": …})`), queda marcado
aquí con el color de su utilidad y arriba dice «Resaltado: …» con «Ver todo» (lo quita todo).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr
from layer_std_legend import (StandardLegend, TIP_PDF_MAX_W, accent, active_qss, img_html, pdf_sample,
                              tooltip_html)
from recognition_summary_view import utility_swatch
from ui_common import layer_qcolor
import leyenda_estandar as le
import pdf_layers
import recognition
import recognition_letters as letters_mod
import theme as _theme

SAMPLE_H = 22            # alto de la muestra de una fila de leyenda (px)
SAMPLE_W = 132           # …y ancho máximo


class LegendWorker(QtCore.QThread):
    """Lee la leyenda de cada PDF de origen en segundo plano. `done(list)`: por PDF
    {"name", "rows": [pdf_legend.LegendRow], "images": {hoja: (png, (x0, y0, x1, y1))}}."""
    done = QtCore.Signal(object)

    def __init__(self, sources, parent=None):
        super().__init__(parent)
        self._sources = list(sources or [])

    def run(self):
        import fitz
        import pdf_legend
        out = []
        stop = self.isInterruptionRequested
        for src in self._sources:
            if stop():
                break
            try:
                doc = (fitz.open(stream=src["data"], filetype="pdf") if src.get("data")
                       else fitz.open(src["path"]))
            except Exception:
                continue
            try:
                rows = pdf_legend.document_legend(doc, stop)
                images = {}
                for page in sorted({r.page for r in rows}):
                    mine = [r.sample for r in rows if r.page == page]
                    region = (min(s[0] for s in mine) - 2, min(s[1] for s in mine) - 2,
                              max(s[2] for s in mine) + 2, max(s[3] for s in mine) + 2)
                    pix = doc[page].get_pixmap(matrix=fitz.Matrix(3, 3), clip=fitz.Rect(*region), alpha=False)
                    images[page] = (pix.tobytes("png"), region)
                out.append({"name": src.get("name", ""), "rows": rows, "images": images})
            except Exception:
                continue
            finally:
                doc.close()
        self.done.emit(out)


def _utility_name(key: str) -> str:
    return _tr(recognition.utility_label(key))


def _muted(text: str, size: int = 12, italic: bool = False) -> QtWidgets.QLabel:
    t = _theme.tokens()
    lbl = QtWidgets.QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{t.text_muted}; font-size:{size}px; background:transparent;"
                      + (" font-style:italic;" if italic else ""))
    return lbl


def _card_qss(active: bool) -> str:
    t = _theme.tokens()
    base = (f"background:{t.surface_alt}; border:1px solid {t.border_soft};" if active
            else f"background:transparent; border:1px dashed {t.border};")
    return (f"#infoCard {{ {base} border-radius:6px; }}"
            f" #infoCard:hover {{ border:1px solid {t.text_muted}; }}"
            " #infoCard QLabel { background:transparent; border:none; }")


class _LetterCard(QtWidgets.QFrame):
    """Una capa reconocida por sus letras: «Usar» + utilidad, letras, capa y leyenda."""
    toggled = QtCore.Signal(str, bool)
    activated = QtCore.Signal(str)

    def __init__(self, layer: dict, used: bool):
        super().__init__()
        self.name = layer["name"]
        self.utility = (layer.get("letter_utilities") or [layer.get("utility")])[0]
        self.highlighted = False
        self.setObjectName("infoCard")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(_tr("Clic: ver sus líneas en la hoja (otro clic, ver todo)."))
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(8)
        self.chk = QtWidgets.QCheckBox()
        self.chk.setChecked(used)
        self.chk.setToolTip(_tr("Usar: reconocer esta capa por las letras de su línea"))
        self.chk.toggled.connect(lambda on: (self._restyle(), self.toggled.emit(self.name, on)))
        lay.addWidget(self.chk, 0, QtCore.Qt.AlignTop)
        col = QtWidgets.QVBoxLayout(); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(2)
        head = QtWidgets.QHBoxLayout(); head.setSpacing(6)
        codes = layer.get("letter_codes") or {}
        for u in layer.get("letter_utilities") or ():
            sw = QtWidgets.QLabel(); sw.setPixmap(utility_swatch(layer_qcolor(u), 12))
            head.addWidget(sw, 0)
            lb = QtWidgets.QLabel("{u} «{c}»".format(u=_utility_name(u), c=codes.get(u, layer.get("letters", ""))))
            f = lb.font(); f.setBold(True); lb.setFont(f)
            head.addWidget(lb, 0)
        head.addStretch(1)
        col.addLayout(head)
        if layer.get("name_utility"):
            why = _tr("su nombre dice {u}").format(u=_utility_name(layer["name_utility"]))
        elif len(layer.get("letter_utilities") or ()) > 1:
            why = _tr("línea por línea")
        else:
            why = _tr("su nombre no dice la utilidad")
        col.addWidget(_muted("{capa} · {por}".format(capa=layer.get("short") or self.name, por=why)))
        self.lbl_legend = _muted("", 11, italic=True)
        self.lbl_legend.hide()
        col.addWidget(self.lbl_legend)
        lay.addLayout(col, 1)
        self._restyle()

    def set_legend_text(self, text: str):
        self.lbl_legend.setText(text)
        self.lbl_legend.setVisible(bool(text))

    def _restyle(self):
        if self.highlighted:
            self.setStyleSheet(active_qss("infoCard", accent(self.utility)))
        else:
            self.setStyleSheet(_card_qss(self.chk.isChecked()))

    def set_highlighted(self, on: bool):
        """Activa en la hoja (sus líneas con halo): marco del color de su utilidad."""
        self.highlighted = on
        self._restyle()

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.activated.emit(self.name)
            return
        super().mouseReleaseEvent(e)


class _LegendRowWidget(QtWidgets.QFrame):
    """Fila de la leyenda del PDF: muestra de la línea + descripción (+ utilidad)."""
    activated = QtCore.Signal(int)             # índice de la fila en la leyenda

    def __init__(self, row, pixmap: Optional[QtGui.QPixmap], in_sheet: bool, index: int):
        super().__init__()
        t = _theme.tokens()
        self.index = index
        self.setObjectName("infoCard")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4); lay.setSpacing(2)
        top = QtWidgets.QHBoxLayout(); top.setSpacing(6)
        if pixmap is not None and not pixmap.isNull():
            img = QtWidgets.QLabel()
            img.setPixmap(pixmap.scaled(SAMPLE_W, SAMPLE_H, QtCore.Qt.KeepAspectRatio,
                                        QtCore.Qt.SmoothTransformation))
            img.setStyleSheet("background:white; border-radius:3px; padding:1px;")
            top.addWidget(img, 0)
        if row.utility and not row.overhead:
            sw = QtWidgets.QLabel(); sw.setPixmap(utility_swatch(layer_qcolor(row.utility), 10))
            sw.setToolTip(_utility_name(row.utility))
            top.addWidget(sw, 0)
        top.addStretch(1)
        lay.addLayout(top)
        desc = QtWidgets.QLabel(row.text)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{t.text if in_sheet else t.text_muted}; font-size:11px;"
                           + (" font-weight:bold;" if in_sheet else ""))
        lay.addWidget(desc)
        self.clickable = in_sheet
        self.utility = row.utility
        if self.clickable:
            self.setCursor(QtCore.Qt.PointingHandCursor)
        # tooltip con la muestra del PDF en GRANDE (la de la fila es una miniatura)
        tip = row.text + ("\n" + _tr("Clic: ver estas líneas en la hoja (otro clic, ver todo).")
                          if self.clickable else "")
        self.setToolTip(tooltip_html([img_html(pixmap, TIP_PDF_MAX_W)], tip))
        self.set_highlighted(False)

    def set_highlighted(self, on: bool):
        if on:
            self.setStyleSheet(active_qss("infoCard", accent(self.utility or "OTRAS")))
        else:
            self.setStyleSheet(_card_qss(True) if self.clickable else
                               "#infoCard { background:transparent; border:none; }")

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and self.clickable:
            self.activated.emit(self.index)
            return
        super().mouseReleaseEvent(e)


def legend_texts(rows, code: str, raw: str = "", limit: int = 2) -> List[str]:
    """Qué dice la leyenda del PDF de un código, en pocas palabras: las filas con ese
    código —con la MISMA caja de letra si alguna la tiene («g» existente / «G»
    propuesta)— de la primera hoja de leyenda, sin las variantes abandonadas («…
    ABANDONED», «TO BE ABANDONED»: el linetype es el mismo con «/» o «//»)."""
    cands = [(src, r) for src, r in rows if r.code == code and not r.overhead]
    if raw:
        exact = [(s, r) for s, r in cands if letters_mod.raw_core(r.raw) == raw]
        cands = exact or cands
    if not cands:
        return []
    first = (cands[0][0].get("name"), cands[0][1].page)
    mine = [r for s, r in cands if (s.get("name"), r.page) == first]
    base = [r for r in mine if "ABANDON" not in r.text.upper()] or mine
    out: List[str] = []
    for r in base:
        if r.text not in out:
            out.append(r.text)
    return out[:limit]


def _clear(layout):
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.hide()                               # hasta que se borre no debe verse encima
            w.deleteLater()


class LayerInfoPanel(QtWidgets.QWidget):
    """Contenido del panel izquierdo. `includeChanged(capa, usar)`: el usuario decidió;
    `focusRequested(dict | None)`: {"layers": [...]} o {"codes": [...]} a resaltar."""
    includeChanged = QtCore.Signal(str, bool)
    focusRequested = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self._layers: List[dict] = []
        self._off: set = set()
        self._legend = None                  # lista de LegendWorker.done, o None mientras se lee
        self._show_all = False
        self._extra: Dict[tuple, dict] = {}      # activos fuera de las casillas: tarjetas y filas del PDF
        self._pdf_rows: Dict[int, _LegendRowWidget] = {}
        self._cards: Dict[str, _LetterCard] = {}
        # () -> capas con algo VISIBLE en la hoja (lo pone el diálogo); None = todas
        self.visible_layers = None
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 4, 0); root.setSpacing(8)
        # ── qué se está resaltando en la hoja (solo mientras hay algo) ──
        self.focus_bar = QtWidgets.QFrame()
        self.focus_bar.setObjectName("focusBar")
        t = _theme.tokens()
        self.focus_bar.setStyleSheet(f"#focusBar {{ background:{t.surface_alt}; border:1px solid {t.border};"
                                     " border-radius:6px; } #focusBar QLabel { background:transparent; }")
        fb = QtWidgets.QHBoxLayout(self.focus_bar); fb.setContentsMargins(8, 4, 4, 4); fb.setSpacing(6)
        self.lbl_focus = QtWidgets.QLabel()
        self.lbl_focus.setWordWrap(True)
        self.lbl_focus.setStyleSheet("font-size:11px;")
        fb.addWidget(self.lbl_focus, 1)
        self.btn_focus_off = QtWidgets.QToolButton()
        self.btn_focus_off.setText(_tr("Ver todo"))
        self.btn_focus_off.setAutoRaise(True)
        self.btn_focus_off.clicked.connect(self._unfocus)
        fb.addWidget(self.btn_focus_off, 0, QtCore.Qt.AlignTop)
        self.focus_bar.hide()
        root.addWidget(self.focus_bar)
        # ── por las letras ──
        self.sec_letters = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(self.sec_letters); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(6)
        self.lbl_letters = QtWidgets.QLabel()
        f = self.lbl_letters.font(); f.setBold(True); self.lbl_letters.setFont(f)
        sl.addWidget(self.lbl_letters)
        sl.addWidget(_muted(_tr("Su nombre no dice la utilidad; las letras de su línea sí. "
                                "Desmarca las que no quieras usar.")))
        self.cards_box = QtWidgets.QVBoxLayout(); self.cards_box.setSpacing(6)
        sl.addLayout(self.cards_box)
        root.addWidget(self.sec_letters)
        # ── leyenda de esta hoja, por utilidad ──
        lbl = QtWidgets.QLabel(_tr("Leyenda de esta hoja"))
        f = lbl.font(); f.setBold(True); lbl.setFont(f)
        root.addWidget(lbl)
        self.lbl_legend = _muted(_tr("Buscando la leyenda en el PDF…"))
        self.lbl_legend.setToolTip(_tr("Cada utilidad con los tipos de línea que hay en esta hoja. Marca una "
                                       "o varias (casilla o clic) para verlas juntas en la hoja: lo "
                                       "marcado se ve con halo y aquí con el color de su utilidad."))
        root.addWidget(self.lbl_legend)
        self.std = StandardLegend()
        self.std.changed.connect(self._emit_focus)
        root.addWidget(self.std)
        # ── la leyenda completa del PDF, plegada ──
        self.btn_all = QtWidgets.QToolButton()
        self.btn_all.setAutoRaise(True)
        self.btn_all.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btn_all.clicked.connect(self._toggle_all)
        self.btn_all.hide()
        root.addWidget(self.btn_all)
        self.legend_box = QtWidgets.QVBoxLayout(); self.legend_box.setSpacing(4)
        root.addLayout(self.legend_box)
        self._rows: list = []
        root.addStretch(1)

    # ── datos ──
    def set_layers(self, layers: List[dict], off) -> None:
        """Capas de la hoja (`pdf_layers.page_layers`) y las que el usuario apagó."""
        self._layers = list(layers or [])
        self._off = set(off or ())
        self._extra = {}
        _clear(self.cards_box)
        self._cards = {}
        mine = [L for L in self._layers if L.get("letter_utilities")]
        for L in mine:
            card = _LetterCard(L, L["name"] not in self._off)
            card.toggled.connect(self._on_card_toggled)
            card.activated.connect(lambda name: self._request(
                ("layer", name), {"layers": [name], "label": pdf_layers.short_name(name)}))
            self.cards_box.addWidget(card)
            self._cards[L["name"]] = card
        self.lbl_letters.setText(_tr("Por las letras de su línea ({n})").format(n=len(mine)))
        self.sec_letters.setVisible(bool(mine))
        self._fill_legend()

    def set_legend(self, results) -> None:
        """Resultado de `LegendWorker` (lista por PDF de origen)."""
        self._legend = list(results or [])
        self._fill_legend()
        if self.active():
            self._emit_focus()                      # las filas pueden haberse rearmado con la leyenda

    def clear_focus(self):
        """Nada activo (sin avisar: lo llama el diálogo al quitar el resaltado)."""
        self.std.clear()
        self._extra = {}
        self._restyle_extra()
        self.set_focus_status("")

    def set_focus_status(self, text: str) -> None:
        """Qué se resalta en la hoja («Resaltado: …»); vacío = nada (se oculta)."""
        self.lbl_focus.setText(text)
        self.focus_bar.setVisible(bool(text))

    def standard_groups(self) -> list:
        """Utilidades de la «Leyenda de esta hoja» (`leyenda_estandar.Grupo`)."""
        return self.std.groups

    # ── interno ──
    def _unfocus(self):
        """«Ver todo»: desmarca todo y quita el resaltado."""
        self.clear_focus()
        self.focusRequested.emit(None)

    def active(self) -> List[dict]:
        """Lo que se resalta ahora: casillas de la leyenda + tarjetas + filas del PDF."""
        return self.std.active_specs() + list(self._extra.values())

    def _emit_focus(self):
        specs = self.active()
        if not specs:
            self.focusRequested.emit(None)
            return
        labels = self.std.summary() + [sp.get("label") or "" for sp in self._extra.values()]
        self.focusRequested.emit({"specs": specs, "label": [x for x in labels if x]})

    def _restyle_extra(self):
        for name, card in self._cards.items():
            card.set_highlighted(("layer", name) in self._extra)
        for i, w in self._pdf_rows.items():
            w.set_highlighted(("pdf", i) in self._extra)

    def _on_card_toggled(self, name: str, used: bool):
        (self._off.discard if used else self._off.add)(name)
        self.includeChanged.emit(name, used)
        self._fill_legend()                         # la capa cambia de utilidad (o vuelve a su nombre)
        if self.active():
            self._emit_focus()                      # lo activo puede haber cambiado de líneas

    def _std_layers(self) -> List[dict]:
        """Capas para la leyenda del estándar: con la decisión «Usar» y solo las que se ven."""
        layers = pdf_layers.without_letters(self._layers, self._off)
        vis = self.visible_layers() if self.visible_layers is not None else None
        if vis is None:
            return layers
        known = {L["name"] for L in layers}
        # + las capas con trazos que no están en la lista del PDF (el reconocimiento las toma)
        return [L for L in layers if L["name"] in vis] + [le.capa_sin_lista(n) for n in sorted(vis - known)]

    def _on_pdf_row(self, i: int):
        """Fila de la leyenda completa del PDF → las líneas de la hoja que describe."""
        filas = self.std.filas_de_pdf(i)
        if not filas:
            return
        capas = list(dict.fromkeys(n for f in filas for n in f.capas))
        self._request(("pdf", i), {"utility": filas[0].utilidad, "layers": capas, "role": filas[0].rol,
                                   "label": self._rows[i][1].text})

    def _request(self, key, spec):
        """Tarjeta o fila del PDF: se SUMA a lo activo; otro clic la quita."""
        if key in self._extra:
            del self._extra[key]
        else:
            self._extra[key] = spec
        self._restyle_extra()
        self._emit_focus()

    def _toggle_all(self):
        self._show_all = not self._show_all
        self._fill_legend()

    def _fill_legend(self):
        _clear(self.legend_box)
        self._pdf_rows = {}
        rows = [(src, r) for src in (self._legend or []) for r in src["rows"]]
        if rows != self._rows:                      # otra leyenda: sus filas activas ya no valen
            self._extra = {k: v for k, v in self._extra.items() if k[0] != "pdf"}
        self._rows = rows
        crops: Dict[tuple, QtGui.QPixmap] = {}
        self.std.set_layers(self._std_layers(), pdf=rows)
        pages = sorted({r.page + 1 for _s, r in rows})
        where = (_tr("hoja {n}").format(n=pages[0]) if len(pages) == 1 else
                 _tr("hojas {n}").format(n=", ".join(str(p) for p in pages[:4])))
        if not self.std.groups:
            self.lbl_legend.setText(_tr("Esta hoja no tiene líneas de utilidades."))
        elif self._legend is None:
            self.lbl_legend.setText(_tr("Según el estándar BOE (buscando la leyenda en el PDF…)."))
        elif rows:
            self.lbl_legend.setText(_tr("Según la leyenda del PDF ({donde}).").format(donde=where))
        else:
            self.lbl_legend.setText(_tr("Según el estándar BOE: el PDF no trae leyenda."))
        # la leyenda completa del PDF, plegada (en negrita, lo que hay en esta hoja)
        self.btn_all.setVisible(bool(rows))
        self.btn_all.setArrowType(QtCore.Qt.DownArrow if self._show_all else QtCore.Qt.RightArrow)
        self.btn_all.setText(_tr("Leyenda completa del PDF ({n})").format(n=len(rows)))
        if self._show_all:
            here = self.std.matched()
            for i, (src, row) in enumerate(rows):
                w = _LegendRowWidget(row, self._crop(src, row, crops), i in here, i)
                w.activated.connect(self._on_pdf_row)
                self.legend_box.addWidget(w)
                self._pdf_rows[i] = w
        self._restyle_extra()
        for L in self._layers:
            card = self._cards.get(L["name"])
            if card is None:
                continue
            raw = L.get("letter_raw") or {}
            mine = [c for label in (L.get("letter_codes") or {}).values() for c in label.split(" · ")]
            texts = [t for c in dict.fromkeys(mine) for t in legend_texts(rows, c, raw.get(c, ""))]
            card.set_legend_text(_tr("Leyenda: {d}").format(d=" · ".join(texts)) if texts else "")

    @staticmethod
    def _crop(src, row, cache) -> Optional[QtGui.QPixmap]:
        return pdf_sample(src, row, cache)
