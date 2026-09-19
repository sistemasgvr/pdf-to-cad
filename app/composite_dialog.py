"""composite_dialog.py — «Componer hoja de trabajo».

Paso del asistente que reemplaza a «Organizar hojas». Tres paneles, de
izquierda a derecha, en el orden en que se usan:

  1 · Origen        PDF (se pueden agregar más), hojas con miniatura y escala
                    de la hoja. Las capas se eligen en el paso siguiente
                    («Capas de la hoja»), ya sobre la hoja compuesta.
  2 · Área a tomar  la hoja elegida; se marca un rectángulo y se «toma».
  3 · Hoja compuesta las piezas; se arrastran con imán, se giran, se corrige su
                    escala; los extremos de línea se marcan y los PUENTES que
                    los unirán se dibujan en verde.

Todo lo geométrico vive en `composite.py`; aquí solo hay Qt.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

import composite as C
import pdf_layers
import vector_pipeline as VP
from composite_view import CompositeView, _qpixmap
from pdf_view_quality import ViewportSharpener
from i18n import t as _tr
from icons import icon as _icon
from sheet_crop_dialog import _CropView
from ui_common import DOWNLOADS
from widgets import CollapsiblePanel, maximize_on_show
import theme as _theme

_SETTINGS = ("PDFCAD", "AsistenteC3D")

_THUMB_W = 150
_ICON = QtCore.QSize(20, 20)


def _scale_label(ft_per_pt: float) -> str:
    return '1" = {v:g}\''.format(v=round(ft_per_pt * 72.0, 3))


def _panel(title: str) -> tuple[CollapsiblePanel, QtWidgets.QVBoxLayout]:
    """Panel plegable con marco, márgenes y cabecera uniforme (número · nombre)."""
    box = CollapsiblePanel(title)
    box.setObjectName("compPanel")
    t = _theme.tokens()
    box.setStyleSheet(f"QFrame#compPanel {{ background:{t.surface}; border:1px solid {t.border}; border-radius:8px; }}")
    return box, box.body_layout


def _tool(icon_name: str, text: str, tip: str = "", checkable: bool = False,
          icon_only: bool = False) -> QtWidgets.QToolButton:
    """Botón de herramienta uniforme. `icon_only`: solo icono (el texto queda
    en el tooltip) para no gastar espacio en acciones evidentes."""
    btn = QtWidgets.QToolButton()
    btn.setIcon(_icon(icon_name)); btn.setIconSize(_ICON)
    btn.setText(text); btn.setToolTip(tip or text)
    btn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if icon_only
                           else QtCore.Qt.ToolButtonTextBesideIcon)
    btn.setCheckable(checkable)
    btn.setAutoRaise(False)
    btn.setMinimumHeight(32)
    if icon_only:
        btn.setFixedSize(34, 32)
    return btn


def _spin(prefix: str = "", suffix: str = "", lo: float = 0.0, hi: float = 100.0,
          decimals: int = 2, step: float = 1.0) -> QtWidgets.QDoubleSpinBox:
    sp = QtWidgets.QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setDecimals(decimals); sp.setSingleStep(step)
    sp.setPrefix(prefix); sp.setSuffix(suffix)
    sp.setMinimumHeight(30)
    return sp


class CompositeDialog(QtWidgets.QDialog):
    def __init__(self, parent, sources: List[dict], comp: Optional[C.Composite],
                 hidden_by_source: Optional[Dict[str, List[str]]], current_page: int = 0):
        super().__init__(parent)
        self.sources = [dict(s) for s in sources]
        self.hidden_by_source = {k: list(v) for k, v in (hidden_by_source or {}).items()}
        self.comp = C.Composite.from_dict(comp.to_dict()) if comp else C.Composite()
        self.docs: List[fitz.Document] = []
        for i, s in enumerate(self.sources):
            doc = fitz.open(stream=s["data"], filetype="pdf")
            pdf_layers.set_hidden(doc, self.hidden_by_source.get(str(i), ()))
            self.docs.append(doc)
        self._scale_cache: Dict[tuple, float] = {}
        self._thumb_cache: Dict[tuple, QtGui.QIcon] = {}
        self._guide_cache: Dict[tuple, dict] = {}
        self._cur_source = 0
        self._cur_page = current_page
        self._page_item = None
        self._syncing_widgets = False
        self._editing = -1            # pieza cuya área se edita en el panel 2 (-1 = nueva pieza)
        self._syncing_crop = False
        self._crop_timer = QtCore.QTimer(self)
        self._crop_timer.setSingleShot(True)
        self._crop_timer.setInterval(200)
        self._crop_timer.timeout.connect(self._apply_crop_edit)

        self.setWindowTitle(_tr("Componer hoja de trabajo"))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMinimizeButtonHint
                            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1500, 880)
        maximize_on_show(self)
        self._build_ui()
        self._fill_sources()
        self.view.rebuild()
        self._refresh_scale_combo()
        self._refresh_summary()
        QtCore.QTimer.singleShot(0, self.view.fit_all)

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        tokens = _theme.tokens()
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)
        self.intro = QtWidgets.QLabel(_tr(
            "Elige el PDF y la hoja, marca el área del plano que necesitas y tómala a la hoja "
            "compuesta. Acomoda las piezas arrastrándolas: el imán alinea los extremos de las líneas "
            "y los puentes (verde) los unen. Cada pieza conserva sus vectores, capas, textos y medidas."))
        self.intro.setWordWrap(True)
        self.intro.setStyleSheet(f"color:{tokens.text_muted};")
        root.addWidget(self.intro)
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        # tirador invisible: solo separación entre paneles (sigue siendo arrastrable)
        split.setStyleSheet("QSplitter::handle { background: transparent; border: none; }")
        root.addWidget(split, 1)
        self.split = split
        self.panels = [self._build_source_panel(), self._build_area_panel(), self._build_composite_panel()]
        for i, panel in enumerate(self.panels):
            split.addWidget(panel)
            panel.toggled.connect(lambda on, i=i: self._on_panel_toggled(i, on))
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 3); split.setStretchFactor(2, 4)
        self._sizes_before: Dict[int, int] = {}
        self._apply_initial_sizes()

        foot = QtWidgets.QHBoxLayout()
        hint = QtWidgets.QLabel(_tr("Rueda = zoom · botón central = desplazar · Supr quita la pieza seleccionada"))
        hint.setStyleSheet(f"color:{tokens.text_muted}; font-size:12px;")
        hint.setWordWrap(True)
        foot.addWidget(hint, 1)
        self.btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn_cancel.setMinimumSize(120, 34)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QtWidgets.QPushButton(_icon("mdi:check"), _tr("Continuar"))
        self.btn_ok.setMinimumSize(140, 34)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        foot.addWidget(self.btn_cancel); foot.addWidget(self.btn_ok)
        root.addLayout(foot)
        self._on_piece_selected(-1)
        sc = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self.view, self._delete)
        sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)   # no borrar piezas al editar un número

    # ── responsivo: tamaños iniciales, plegado, pantallas pequeñas ─────────
    def _apply_initial_sizes(self):
        """Ancho inicial de los paneles proporcional a la ventana (recordado entre
        sesiones si el usuario lo movió)."""
        w = max(900, self.width())
        st = QtCore.QSettings(*_SETTINGS)
        saved = st.value("compositor/splitter")
        if isinstance(saved, (list, tuple)) and len(saved) == 3:
            try:
                sizes = [int(v) for v in saved]
                if sum(sizes) > 0:
                    total = sum(sizes)
                    self.split.setSizes([int(v * w / total) for v in sizes])
                    return
            except (TypeError, ValueError):
                pass
        left = max(240, min(330, int(w * 0.22)))
        rest = w - left
        self.split.setSizes([left, int(rest * 0.44), rest - int(rest * 0.44)])

    def _on_panel_toggled(self, index: int, collapsed: bool):
        sizes = self.split.sizes()
        if collapsed:
            self._sizes_before[index] = sizes[index]
            freed = max(0, sizes[index] - CollapsiblePanel.STRIP_W)
            sizes[index] = CollapsiblePanel.STRIP_W
            others = [i for i in range(len(sizes)) if i != index and not self.panels[i].collapsed]
            for i in others:
                sizes[i] += freed // max(1, len(others))
        else:
            want = self._sizes_before.pop(index, max(260, int(sum(sizes) * 0.3)))
            others = [i for i in range(len(sizes)) if i != index and not self.panels[i].collapsed]
            take = want - sizes[index]
            for i in others:
                sizes[i] = max(120, sizes[i] - take // max(1, len(others)))
            sizes[index] = want
        self.split.setSizes(sizes)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # en ventanas estrechas el texto de ayuda se esconde para ganar alto
        self.intro.setVisible(self.width() >= 1250 and self.height() >= 700)

    def _build_source_panel(self) -> QtWidgets.QWidget:
        box, lay = _panel(_tr("1 · Origen"))
        lay.addWidget(QtWidgets.QLabel(_tr("PDF")))
        row = QtWidgets.QHBoxLayout(); row.setSpacing(6)
        self.cmb_source = QtWidgets.QComboBox()
        self.cmb_source.setMinimumHeight(30)
        self.cmb_source.currentIndexChanged.connect(self._on_source_changed)
        row.addWidget(self.cmb_source, 1)
        btn_add = _tool("mdi:file-plus-outline", _tr("Agregar PDF…"), _tr("Agregar otro PDF"), icon_only=True)
        btn_add.clicked.connect(self._add_pdf)
        row.addWidget(btn_add)
        lay.addLayout(row)

        lay.addWidget(QtWidgets.QLabel(_tr("Hojas")))
        self.lst_pages = QtWidgets.QListWidget()
        self.lst_pages.setIconSize(QtCore.QSize(_THUMB_W, int(_THUMB_W * 0.75)))
        self.lst_pages.setMinimumWidth(120)
        self.lst_pages.setSpacing(3)
        self.lst_pages.currentRowChanged.connect(self._on_page_changed)
        lay.addWidget(self.lst_pages, 1)

        form = QtWidgets.QFormLayout(); form.setContentsMargins(0, 0, 0, 0)
        self.spn_src_scale = _spin('1" = ', "'", 0.1, 100000.0)
        self.spn_src_scale.setToolTip(_tr("Escala leída del texto de la hoja; corrígela si no es la del plano."))
        form.addRow(_tr("Escala de la hoja"), self.spn_src_scale)
        lay.addLayout(form)

        return box

    def _build_area_panel(self) -> QtWidgets.QWidget:
        box, lay = _panel(_tr("2 · Área a tomar"))
        self.lbl_mode = QtWidgets.QLabel(_tr("Arrastra un rectángulo sobre el plano; esquinas y lados se ajustan."))
        self.lbl_mode.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        self.lbl_mode.setWordWrap(True)
        lay.addWidget(self.lbl_mode)
        self.crop = _CropView()
        self.crop.selectionChanged.connect(self._on_selection_changed)
        # La hoja se muestra a 72 dpi; al hacer zoom, la parte visible se
        # re-renderiza nítida encima (z=1: bajo las guías y el rectángulo).
        self._crop_sharp = ViewportSharpener(self.crop, lambda: self.docs[self._cur_source][self._cur_page], z=1)
        lay.addWidget(self.crop, 1)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8)
        self.btn_take = QtWidgets.QPushButton(_icon("mdi:arrow-right-bold"), _tr("Tomar área"))
        self.btn_take.setMinimumHeight(34)
        self.btn_take.clicked.connect(lambda: self._take(full=False))
        self.btn_take_full = QtWidgets.QPushButton(_tr("Tomar hoja completa"))
        self.btn_take_full.setMinimumHeight(34)
        self.btn_take_full.clicked.connect(lambda: self._take(full=True))
        self.btn_new = QtWidgets.QPushButton(_icon("mdi:plus"), _tr("Nueva pieza"))
        self.btn_new.setMinimumHeight(34)
        self.btn_new.setToolTip(_tr("Dejar de editar la pieza seleccionada y marcar un área nueva"))
        self.btn_new.clicked.connect(lambda: self.view.select(-1))
        self.btn_new.hide()
        row.addWidget(self.btn_take); row.addWidget(self.btn_take_full); row.addWidget(self.btn_new)
        self.btn_area_snap = _tool("mdi:magnet", _tr("Imán a líneas"),
                                   _tr("Al arrastrar el rectángulo, sus lados saltan a las líneas generales de la "
                                       "hoja (match lines, marcos, bordes largos), que se resaltan en celeste"),
                                   checkable=True)
        self.btn_area_snap.setChecked(True)
        self.btn_area_snap.toggled.connect(lambda on: setattr(self.crop, "snap_enabled", bool(on)))
        row.addWidget(self.btn_area_snap)
        self.btn_trim = _tool("mdi:border-none-variant", _tr("Sin línea de borde"),
                              _tr("Recortar el área por dentro de la línea larga que corra pegada a cada lado "
                                  "(match line, marco de la vista), sea de la capa que sea, para que no aparezca "
                                  "en la hoja compuesta"), checkable=True)
        self.btn_trim.setChecked(True)
        self.btn_trim.toggled.connect(self._on_trim_toggled)
        row.addWidget(self.btn_trim)
        row.addStretch(1)
        self.lbl_area = QtWidgets.QLabel()
        self.lbl_area.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        row.addWidget(self.lbl_area)
        lay.addLayout(row)
        return box

    def _build_composite_panel(self) -> QtWidgets.QWidget:
        box, lay = _panel(_tr("3 · Hoja compuesta"))
        # Barra de herramientas: pieza seleccionada | vista
        bar = QtWidgets.QHBoxLayout(); bar.setSpacing(6)
        self.btn_ccw = _tool("mdi:rotate-left", _tr("Girar 90° antihorario"), icon_only=True)
        self.btn_ccw.clicked.connect(lambda: self._rotate(90))
        self.btn_cw = _tool("mdi:rotate-right", _tr("Girar 90° horario"), icon_only=True)
        self.btn_cw.clicked.connect(lambda: self._rotate(-90))
        bar.addWidget(self.btn_ccw); bar.addWidget(self.btn_cw)
        bar.addWidget(QtWidgets.QLabel(_tr("Ángulo")))
        self.spn_angle = _spin("", "°", -360.0, 360.0, 2, 0.5)
        self.spn_angle.setToolTip(_tr("Ángulo fino de la pieza (antihorario)"))
        self.spn_angle.valueChanged.connect(self._on_angle_edited)
        bar.addWidget(self.spn_angle)
        bar.addWidget(QtWidgets.QLabel(_tr("Escala pieza")))
        self.spn_piece_scale = _spin('1" = ', "'", 0.1, 100000.0)
        self.spn_piece_scale.setToolTip(_tr("Escala de la hoja de origen de esta pieza"))
        self.spn_piece_scale.valueChanged.connect(self._on_piece_scale_edited)
        bar.addWidget(self.spn_piece_scale)
        self.btn_del = _tool("mdi:trash-can-outline", _tr("Quitar la pieza seleccionada (Supr)"), icon_only=True)
        self.btn_del.clicked.connect(self._delete)
        bar.addWidget(self.btn_del)
        bar.addStretch(1)
        btn_fit = _tool("mdi:fit-to-screen-outline", _tr("Ajustar la vista a todas las piezas"), icon_only=True)
        btn_fit.clicked.connect(self.view_fit)
        bar.addWidget(btn_fit)
        lay.addLayout(bar)

        self.view = CompositeView(self.comp, self.docs)
        self.view.pieceMoved.connect(lambda _i: self._refresh_summary())
        self.view.selectionChangedIdx.connect(self._on_piece_selected)
        self.view.bridgesChanged.connect(self._on_bridges_changed)
        lay.addWidget(self.view, 1)

        # Ayudas de unión | escala de la hoja
        aid = QtWidgets.QHBoxLayout(); aid.setSpacing(6)
        self.btn_magnet = _tool("mdi:magnet", _tr("Imán"),
                                _tr("Al arrastrar, los extremos de las líneas se pegan (o se alinean) con los de la pieza vecina"),
                                checkable=True)
        self.btn_magnet.setChecked(True)
        self.btn_magnet.toggled.connect(lambda on: setattr(self.view, "magnet_enabled", bool(on)))
        aid.addWidget(self.btn_magnet)
        self.btn_anchors = _tool("mdi:circle-medium", _tr("Extremos"),
                                 _tr("Mostrar los extremos de línea en el borde de cada pieza"), checkable=True)
        self.btn_anchors.setChecked(True)
        self.btn_anchors.toggled.connect(self._toggle_anchors)
        aid.addWidget(self.btn_anchors)
        self.btn_bridges = _tool("mdi:link-variant", _tr("Puentes"),
                                 _tr("Unir con un trazo vectorial (misma capa) cada extremo con el que tiene enfrente en la pieza vecina"),
                                 checkable=True)
        self.btn_bridges.setChecked(bool(self.comp.bridges))
        self.btn_bridges.toggled.connect(self._toggle_bridges)
        aid.addWidget(self.btn_bridges)
        aid.addWidget(QtWidgets.QLabel(_tr("hueco máx.")))
        self.spn_gap = _spin("", " pt", 1.0, 2000.0, 0, 10.0)
        self.spn_gap.setValue(float(self.comp.bridge_max_pt))
        self.spn_gap.setToolTip(_tr("Separación máxima entre dos extremos para unirlos con un puente"))
        self.spn_gap.valueChanged.connect(self._on_gap_edited)
        aid.addWidget(self.spn_gap)
        self.lbl_bridges = QtWidgets.QLabel()
        aid.addWidget(self.lbl_bridges)
        aid.addStretch(1)
        lay.addLayout(aid)
        # resumen + escala de la hoja en una segunda línea (menos ancho mínimo)
        srow = QtWidgets.QHBoxLayout(); srow.setSpacing(6)
        self.lbl_summary = QtWidgets.QLabel()
        self.lbl_summary.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        srow.addWidget(self.lbl_summary, 1)
        srow.addWidget(QtWidgets.QLabel(_tr("Escala de la hoja")))
        self.cmb_scale = QtWidgets.QComboBox()
        self.cmb_scale.setMinimumHeight(30)
        self.cmb_scale.setToolTip(_tr("Escala única de la hoja compuesta; cada pieza se ajusta a ella"))
        self.cmb_scale.currentIndexChanged.connect(self._on_target_scale_changed)
        srow.addWidget(self.cmb_scale)
        lay.addLayout(srow)
        return box

    # ── PDFs y hojas ────────────────────────────────────────────────────
    def _fill_sources(self):
        self.cmb_source.blockSignals(True)
        self.cmb_source.clear()
        for i, s in enumerate(self.sources):
            self.cmb_source.addItem(_tr("{name}  ({n} hojas)").format(name=s["name"], n=self.docs[i].page_count))
        self.cmb_source.setCurrentIndex(self._cur_source)
        self.cmb_source.blockSignals(False)
        self._fill_pages()

    def _fill_pages(self):
        doc = self.docs[self._cur_source]
        self.lst_pages.blockSignals(True)
        self.lst_pages.clear()
        for i in range(doc.page_count):
            self.lst_pages.addItem(QtWidgets.QListWidgetItem(
                self._thumb(self._cur_source, i), _tr("Hoja {n}").format(n=i + 1)))
        row = self._cur_page if 0 <= self._cur_page < doc.page_count else 0
        self.lst_pages.setCurrentRow(row)
        self.lst_pages.blockSignals(False)
        self._on_page_changed(row)

    def _thumb(self, source: int, page: int) -> QtGui.QIcon:
        key = (source, page)
        if key not in self._thumb_cache:
            pg = self.docs[source][page]
            z = _THUMB_W / max(pg.rect.width, 1.0)
            self._thumb_cache[key] = QtGui.QIcon(_qpixmap(pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)))
        return self._thumb_cache[key]

    def _guides(self, source: int, page: int) -> dict:
        key = (source, page)
        if key not in self._guide_cache:
            try:
                self._guide_cache[key] = C.guide_lines(self.docs[source][page])
            except Exception:
                self._guide_cache[key] = {"x": [], "y": []}
        return self._guide_cache[key]

    def _invalidate_source_renders(self, source: int):
        for key in [k for k in self._thumb_cache if k[0] == source]:
            self._thumb_cache.pop(key, None)

    def _detected_scale(self, source: int, page: int) -> float:
        key = (source, page)
        if key not in self._scale_cache:
            try:
                self._scale_cache[key] = float(VP.detect_scale(self.docs[source][page]))
            except Exception:
                self._scale_cache[key] = 20 / 72.0
        return self._scale_cache[key]

    def _on_source_changed(self, idx: int):
        if idx < 0:
            return
        self._cur_source = idx
        self._cur_page = 0
        self._fill_pages()

    def _on_page_changed(self, row: int):
        if row < 0:
            return
        self._cur_page = row
        if self._editing >= 0 and not self._syncing_crop:
            self.view.select(-1)          # cambiar de hoja a mano = empezar una pieza nueva
        self._render_current_page(first=True)
        self.spn_src_scale.blockSignals(True)
        self.spn_src_scale.setValue(self._detected_scale(self._cur_source, row) * 72.0)
        self.spn_src_scale.blockSignals(False)

    def _render_current_page(self, first: bool = False):
        page = self.docs[self._cur_source][self._cur_page]
        pm = _qpixmap(page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False))
        if self._page_item is None:
            self._page_item = self.crop.scene().addPixmap(pm)
            self._page_item.setZValue(0)
        else:
            self._page_item.setPixmap(pm)
        rect = QtCore.QRectF(0, 0, pm.width(), pm.height())
        self.crop.set_page(rect)
        self.crop.setSceneRect(rect)
        self._crop_sharp.invalidate()
        self.crop.set_guides(self._guides(self._cur_source, self._cur_page))
        if first:
            self.crop.set_selection(None)
            QtCore.QTimer.singleShot(0, lambda: self.crop.fitInView(rect, QtCore.Qt.KeepAspectRatio))

    def _on_selection_changed(self, rect):
        ok = rect is not None and rect.width() >= C.MIN_PIECE_PT and rect.height() >= C.MIN_PIECE_PT
        self.btn_take.setEnabled(ok)
        self.lbl_area.setText(_tr("{w:.0f} × {h:.0f} pt").format(w=rect.width(), h=rect.height()) if ok else "")
        if self._editing >= 0 and ok and not self._syncing_crop:
            self._crop_timer.start()

    def _current_clip(self, full: bool = False):
        """(clip normalizado, covers) del rectángulo del panel 2. Con «Sin línea
        de borde» activo el clip pasa por el centro de la línea de borde y
        `covers` trae la franja blanca que la tapa por lado."""
        if full:
            clip = [0.0, 0.0, 1.0, 1.0]
        else:
            sel = self.crop._selection
            if sel is None:
                return None
            full_r = self.crop._page_rect
            clip = C.normalize_clip([sel.left() / full_r.width(), sel.top() / full_r.height(),
                                     sel.right() / full_r.width(), sel.bottom() / full_r.height()])
        covers = {}
        if self.btn_trim.isChecked():
            clip, covers = C.trim_border(self.docs[self._cur_source][self._cur_page], clip)
        return clip, covers

    def _apply_crop_edit(self):
        """Modo edición: el rectángulo del panel 2 ES el área de la pieza seleccionada."""
        idx = self._editing
        if not 0 <= idx < len(self.comp.pieces):
            return
        res = self._current_clip()
        if res is None:
            return
        clip, covers = res
        piece = self.comp.pieces[idx]
        if piece.source != self._cur_source or piece.page != self._cur_page:
            return
        if [round(v, 9) for v in clip] == [round(v, 9) for v in piece.clip] and covers == piece.covers:
            return
        piece.clip = clip
        piece.covers = covers
        self.view.refresh_piece(idx, rerender=True)
        self.view.refresh_overlay()
        self._refresh_summary()

    def _on_trim_toggled(self, _on: bool):
        if self._editing >= 0:
            self._crop_timer.start()

    def _show_piece_in_area_panel(self, idx: int):
        """Lleva el panel 2 al PDF/hoja de la pieza y dibuja su área para editarla."""
        p = self.comp.pieces[idx]
        self._syncing_crop = True
        try:
            if self._cur_source != p.source:
                self._cur_source = p.source
                self._cur_page = p.page
                self.cmb_source.blockSignals(True); self.cmb_source.setCurrentIndex(p.source); self.cmb_source.blockSignals(False)
                self._fill_pages()
            elif self._cur_page != p.page:
                self.lst_pages.setCurrentRow(p.page)      # dispara _on_page_changed
            full = self.crop._page_rect
            x0, y0, x1, y1 = p.clip
            self.crop.set_selection(QtCore.QRectF(x0 * full.width(), y0 * full.height(),
                                                  (x1 - x0) * full.width(), (y1 - y0) * full.height()))
        finally:
            self._syncing_crop = False
        self.lbl_mode.setText(_tr("Editando el área de la pieza {n} ({name}). Ajusta el rectángulo; "
                                  "la pieza se actualiza sola.").format(n=idx + 1, name=p.label or ""))
        self.btn_take.hide(); self.btn_take_full.hide(); self.btn_new.show()

    def _leave_edit_mode(self):
        self.lbl_mode.setText(_tr("Arrastra un rectángulo sobre el plano; esquinas y lados se ajustan."))
        self.btn_new.hide(); self.btn_take.show(); self.btn_take_full.show()

    def _add_pdf(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr("Agregar PDF"), DOWNLOADS, "PDF (*.pdf)")
        if not path:
            return
        try:
            with open(path, "rb") as fp:
                data = fp.read()
            doc = fitz.open(stream=data, filetype="pdf")
            if doc.page_count < 1:
                raise ValueError(_tr("El PDF no tiene hojas."))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, _tr("Agregar PDF"),
                                          _tr("No se pudo abrir el PDF:\n\n{e}").format(e=exc))
            return
        self.sources.append({"name": os.path.basename(path), "data": data, "path": path})
        self.docs.append(doc)
        self._cur_source = len(self.sources) - 1
        self._cur_page = 0
        self._fill_sources()

    # ── piezas ──────────────────────────────────────────────────────────
    def _take(self, full: bool):
        res = self._current_clip(full)
        if res is None:
            return
        clip, covers = res
        src_scale = self.spn_src_scale.value() / 72.0
        piece = C.Piece(self._cur_source, self._cur_page, clip, src_scale=src_scale,
                        label=f"{self.sources[self._cur_source]['name']} · {self._cur_page + 1}",
                        covers=covers)
        bb = C.bounds(self.comp, self.view.page_size)
        if bb is not None:
            piece.x, piece.y = bb[2] + 24.0, bb[1]
        self.comp.pieces.append(piece)
        self._refresh_scale_combo()
        self.view.rebuild(keep_selection=len(self.comp.pieces) - 1)
        self.view.fit_all()
        self._refresh_summary()

    def _delete(self):
        idx = self.view.selected_index()
        if idx < 0:
            return
        del self.comp.pieces[idx]
        self._refresh_scale_combo()
        self.view.rebuild()
        self._refresh_summary()
        self._on_piece_selected(-1)

    def _rotate(self, delta: float):
        idx = self.view.selected_index()
        if idx < 0:
            return
        p = self.comp.pieces[idx]
        p.rotation = (p.rotation + delta) % 360.0
        self.view.refresh_piece(idx)
        self._sync_piece_widgets(idx)
        self._refresh_summary()

    def _on_angle_edited(self, value: float):
        idx = self.view.selected_index()
        if idx < 0 or self._syncing_widgets:
            return
        self.comp.pieces[idx].rotation = float(value) % 360.0
        self.view.refresh_piece(idx)
        self._refresh_summary()

    def _on_piece_scale_edited(self, value: float):
        idx = self.view.selected_index()
        if idx < 0 or self._syncing_widgets:
            return
        self.comp.pieces[idx].src_scale = float(value) / 72.0
        self._refresh_scale_combo()
        self.view.refresh_all()
        self._refresh_summary()

    def _sync_piece_widgets(self, idx: int):
        self._syncing_widgets = True
        try:
            if idx >= 0:
                p = self.comp.pieces[idx]
                ang = p.rotation if p.rotation <= 180.0 else p.rotation - 360.0
                self.spn_angle.setValue(ang)
                self.spn_piece_scale.setValue(p.src_scale * 72.0)
        finally:
            self._syncing_widgets = False

    def _on_piece_selected(self, idx: int):
        has = idx >= 0
        for w in (self.btn_ccw, self.btn_cw, self.spn_angle, self.spn_piece_scale, self.btn_del):
            w.setEnabled(has)
        if has:
            self._sync_piece_widgets(idx)
            if idx != self._editing:
                self._editing = idx
                self._show_piece_in_area_panel(idx)
        elif self._editing >= 0:
            self._editing = -1
            self._crop_timer.stop()
            self._leave_edit_mode()

    # ── ayudas de unión ─────────────────────────────────────────────────
    def _toggle_anchors(self, on: bool):
        self.view.show_anchors = bool(on)
        self.view.refresh_overlay()

    def _toggle_bridges(self, on: bool):
        self.comp.bridges = bool(on)
        self.spn_gap.setEnabled(bool(on))
        self.view.refresh_overlay()

    def _on_gap_edited(self, value: float):
        self.comp.bridge_max_pt = float(value)
        self.view.refresh_overlay()

    def _on_bridges_changed(self, n: int):
        self.lbl_bridges.setText(_tr("{n} puentes").format(n=n) if self.comp.bridges else "")

    def view_fit(self):
        self.view.fit_all()

    # ── escala de la hoja ───────────────────────────────────────────────
    def _refresh_scale_combo(self):
        scales = []
        for p in self.comp.pieces:
            if not any(abs(p.src_scale - s) < 1e-9 for s in scales):
                scales.append(p.src_scale)
        cur = self.comp.target_scale()
        self.cmb_scale.blockSignals(True)
        self.cmb_scale.clear()
        for s in scales:
            self.cmb_scale.addItem(_scale_label(s), s)
        for i, s in enumerate(scales):
            if abs(s - cur) < 1e-9:
                self.cmb_scale.setCurrentIndex(i)
                break
        self.cmb_scale.setEnabled(len(scales) > 1)
        self.cmb_scale.blockSignals(False)

    def _on_target_scale_changed(self, idx: int):
        if idx < 0:
            return
        self.comp.scale_ft_per_pt = float(self.cmb_scale.itemData(idx))
        self.view.refresh_all()
        self._refresh_summary()

    def _refresh_summary(self):
        n = len(self.comp.pieces)
        self.btn_ok.setEnabled(n > 0)
        w, h, _, _ = C.sheet_geometry(self.comp, self.view.page_size)
        self.lbl_summary.setText(_tr("{n} pieza(s) · hoja compuesta {w:.0f} × {h:.0f} pt · {s}").format(
            n=n, w=w, h=h, s=_scale_label(self.comp.target_scale())))

    # ── cierre ──────────────────────────────────────────────────────────
    def result_tuple(self):
        return self.comp, self.sources, self.hidden_by_source

    def done(self, result):
        if not any(p.collapsed for p in self.panels):
            QtCore.QSettings(*_SETTINGS).setValue("compositor/splitter", [int(v) for v in self.split.sizes()])
        super().done(result)

    def close_docs(self):
        for d in self.docs:
            try:
                d.close()
            except Exception:
                pass
        self.docs = []


def compose_sheet(parent, sources: List[dict], comp: Optional[C.Composite],
                  hidden_by_source: Optional[Dict[str, List[str]]], current_page: int = 0):
    """Abre el compositor. Devuelve ``(composite, sources, hidden_by_source)`` o
    None si se cancela. `sources` son dicts ``{name, data(bytes), path?}``."""
    dlg = CompositeDialog(parent, sources, comp, hidden_by_source, current_page)
    try:
        if dlg.exec() != QtWidgets.QDialog.Accepted:   # showEvent lo maximiza al aparecer
            return None
        return dlg.result_tuple()
    finally:
        dlg.close_docs()
