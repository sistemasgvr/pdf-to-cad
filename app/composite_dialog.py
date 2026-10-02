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
import pdf_layers as PL
import vector_pipeline as VP
from composite_view import CompositeView, _qpixmap
from pdf_view_quality import ViewportSharpener
from i18n import t as _tr
from icons import icon as _icon
from sheet_crop_dialog import _CropView
from scan_crop_view import ScanCropView
from composite_scan_ui import ScanToolsMixin
from tool_strip import ToolStrip
from ui_common import DOWNLOADS
from busy import busy
from widgets import CollapsiblePanel, maximize_on_show, GripSplitter
from wizard_widgets import StepBar, wizard_header, wizard_footer
import theme as _theme

_SETTINGS = ("PDFCAD", "AsistenteC3D")

_THUMB_W = 150
_ICON = QtCore.QSize(20, 20)
_BTN_H = 38            # alto de TODOS los botones del compositor (= QPushButton del tema)
_SIDE_MIN, _SIDE_MAX = 240, 460   # ancho del panel «Origen» (no crece al plegar los otros)


def _settings() -> QtCore.QSettings:
    """Preferencias del compositor (ancho de los paneles). Aparte para que las
    pruebas no escriban en la configuración real del usuario."""
    return QtCore.QSettings(*_SETTINGS)


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
    btn.setMinimumHeight(_BTN_H)
    if icon_only:
        btn.setFixedSize(_BTN_H, _BTN_H)
    if checkable:
        # Estado activo bien visible (fondo verde del tema + icono claro): el
        # usuario no distinguía si «Imán a líneas» / «Sin línea de borde» estaban
        # activos con el resalte sutil de QToolButton.
        btn.setProperty("toggleTool", True)
        on_icon = _icon(icon_name, color=_theme.tokens().text_on_accent)
        off_icon = btn.icon()
        btn.toggled.connect(lambda on, b=btn: b.setIcon(on_icon if on else off_icon))
    return btn


def _options_button(icon_name: str, text: str, tip: str) -> tuple[QtWidgets.QPushButton, QtWidgets.QMenu]:
    """Botón «▾» que agrupa opciones poco usadas en un menú (casillas y campos):
    el usuario ve una sola acción en vez de una fila de conmutadores. Es un
    QPushButton (mismo alto que «Hoja completa») en violeta (`options` del
    tema): antes, un QToolButton más bajo y del color del fondo, no se notaba."""
    btn = QtWidgets.QPushButton(_icon(icon_name, color=_theme.tokens().options_text), text)
    btn.setProperty("options", True)
    btn.setIconSize(_ICON)
    btn.setToolTip(tip)
    btn.setAutoDefault(False)          # Enter no abre el menú: sigue siendo «Continuar»
    btn.setMinimumHeight(_BTN_H)
    menu = QtWidgets.QMenu(btn)
    menu.setToolTipsVisible(True)
    btn.setMenu(menu)
    return btn, menu


def _check_action(menu: QtWidgets.QMenu, text: str, tip: str, checked: bool = True) -> QtGui.QAction:
    act = menu.addAction(text)
    act.setCheckable(True); act.setChecked(checked); act.setToolTip(tip)
    return act


def _field_action(menu: QtWidgets.QMenu, label: str, field: QtWidgets.QWidget) -> QtWidgets.QWidgetAction:
    """Campo (número, etc.) con su etiqueta dentro de un menú."""
    w = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(w); row.setContentsMargins(12, 4, 12, 4); row.setSpacing(8)
    row.addWidget(QtWidgets.QLabel(label), 1); row.addWidget(field)
    act = QtWidgets.QWidgetAction(menu)
    act.setDefaultWidget(w)
    menu.addAction(act)
    return act


def _spin(prefix: str = "", suffix: str = "", lo: float = 0.0, hi: float = 100.0,
          decimals: int = 2, step: float = 1.0) -> QtWidgets.QDoubleSpinBox:
    sp = QtWidgets.QDoubleSpinBox()
    sp.setRange(lo, hi); sp.setDecimals(decimals); sp.setSingleStep(step)
    sp.setPrefix(prefix); sp.setSuffix(suffix)
    sp.setMinimumHeight(30)
    return sp


class CompositeDialog(ScanToolsMixin, QtWidgets.QDialog):
    def __init__(self, parent, sources: List[dict], comp: Optional[C.Composite],
                 hidden_by_source: Optional[Dict[str, List[str]]], current_page: int = 0, manual: bool = False):
        super().__init__(parent)
        self.sources = [dict(s) for s in sources]
        # `hidden_by_source` es la selección de capas de la hoja YA COMPUESTA
        # (paso «Capas de la hoja», después de este diálogo): aquí solo se
        # conserva para devolverla sin tocar. El compositor sirve para MIRAR y
        # recortar el plano de cada PDF origen, así que muestra siempre TODAS
        # las capas — si se aplicara la ocultación de una composición anterior,
        # una hoja cuyo contenido está solo en una capa ya oculta parecía no
        # tener nada que tomar (usuario: «la página 3 no me muestra capas»).
        self.hidden_by_source = {k: list(v) for k, v in (hidden_by_source or {}).items()}
        self.comp = C.Composite.from_dict(comp.to_dict()) if comp else C.Composite()
        self.comp.manual = manual or self.comp.manual
        if self.comp.manual:
            self.comp.bridges = False
        self.docs: List[fitz.Document] = []
        for i, s in enumerate(self.sources):
            doc = fitz.open(stream=s["data"], filetype="pdf")
            self.docs.append(doc)
        self._scale_cache: Dict[tuple, float] = {}
        self._thumb_cache: Dict[tuple, QtGui.QIcon] = {}
        self._guide_cache: Dict[tuple, dict] = {}
        self._layers_cache: Dict[tuple, bool] = {}   # (pdf, hoja) → ¿dibuja dentro de capas?
        self._cur_source, self._cur_page = self._start_position(current_page)
        self._page_item = None
        self._syncing_widgets = False
        self._editing = -1            # pieza cuya área se edita en el panel 2 (-1 = nueva pieza)
        self._syncing_crop = False
        self._crop_timer = QtCore.QTimer(self)
        self._crop_timer.setSingleShot(True)
        self._crop_timer.setInterval(200)
        self._crop_timer.timeout.connect(self._apply_crop_edit)
        self._thumb_queue: List[tuple] = []
        self._thumb_timer = QtCore.QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(0)
        self._thumb_timer.timeout.connect(self._next_thumb)

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

    def _start_position(self, current_page: int) -> tuple[int, int]:
        """PDF y hoja con que se abre: donde el usuario estaba trabajando, no el
        primer PDF. Una sola hoja entera (sin materializar) → su PDF y la hoja
        del editor (◀ ▶ la cambian); si no, la última vista del compositor
        (`Composite.last_view`); si no, la de la última pieza tomada."""
        n = len(self.docs)

        def valid(src, page):
            return 0 <= src < n and 0 <= page < self.docs[src].page_count
        pieces = self.comp.pieces
        if self.comp.is_single_full_page() and valid(pieces[0].source, current_page):
            return pieces[0].source, current_page
        lv = self.comp.last_view
        if lv is not None and valid(lv[0], lv[1]):
            return int(lv[0]), int(lv[1])
        if pieces and valid(pieces[-1].source, pieces[-1].page):
            return pieces[-1].source, pieces[-1].page
        return 0, current_page if valid(0, current_page) else 0

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        tokens = _theme.tokens()
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)
        self.steps = StepBar(0)            # 1 Componer hoja › 2 Capas de la hoja › 3 Vista previa
        root.addWidget(wizard_header(self.steps))
        if self.comp.manual:
            self.steps.hide()
        self.intro = QtWidgets.QLabel(_tr(
            "Elige el PDF y la hoja, marca el área del plano que necesitas y tómala a la hoja "
            "compuesta. Acomoda las piezas arrastrándolas: el imán alinea los extremos de las líneas "
            "y los puentes (verde) los unen. Cada pieza conserva sus vectores, capas, textos y medidas."))
        self.intro.setWordWrap(True)
        self.intro.setStyleSheet(f"color:{tokens.text_muted};")
        root.addWidget(self.intro)
        if self.comp.manual:
            self.intro.setText(_tr("PDF imagen/escaneo: selecciona la hoja, ajusta las cuatro esquinas del área y compón la hoja. Usa la regla para enderezar cada pieza y pásala al editor para dibujar las utilidades a mano."))
        split = GripSplitter(QtCore.Qt.Horizontal)   # tirador visible y arrastrable
        root.addWidget(split, 1)
        self.split = split
        self.panels = [self._build_source_panel(), self._build_area_panel(), self._build_composite_panel()]
        for i, panel in enumerate(self.panels):
            split.addWidget(panel)
            panel.toggled.connect(lambda on, i=i: self._on_panel_toggled(i, on))
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 3); split.setStretchFactor(2, 4)
        self._sizes_before: Dict[int, int] = {}
        self._side_w, self._flex_ratio = self._size_prefs()
        self._sizes_auto = True           # False en cuanto el usuario mueve un divisor o pliega
        split.splitterMoved.connect(lambda *_: setattr(self, "_sizes_auto", False))
        self._apply_initial_sizes()
        self._update_collapse_rules()

        self.btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn_cancel.setProperty("secondary", True)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QtWidgets.QPushButton(_tr("Continuar"))
        if self.comp.manual:
            self.btn_ok.setText(_tr("Importar hoja al editor"))
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        root.addWidget(wizard_footer(
            [], _tr("Rueda = zoom · botón central = desplazar · Supr quita la pieza seleccionada"),
            [self.btn_cancel, self.btn_ok]))
        self._on_piece_selected(-1)
        sc = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self.view, self._delete)
        sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)   # no borrar piezas al editar un número

    # ── responsivo: tamaños iniciales, plegado, pantallas pequeñas ─────────
    def _size_prefs(self) -> tuple[Optional[int], float]:
        """(ancho de «Origen» en px o None, proporción Área / (Área + Hoja
        compuesta)), recordados entre sesiones si el usuario movió los divisores."""
        saved = _settings().value("compositor/splitter")
        if isinstance(saved, (list, tuple)) and len(saved) == 3:
            try:
                sizes = [int(v) for v in saved]
                if sizes[0] > 0 and sizes[1] > 0 and sizes[2] > 0:
                    return max(_SIDE_MIN, min(_SIDE_MAX, sizes[0])), sizes[1] / float(sizes[1] + sizes[2])
            except (TypeError, ValueError):
                pass
        return None, 0.44

    def _apply_initial_sizes(self, real: bool = False):
        """Ancho inicial: «Origen» con ancho PROPIO en px (no escala con la
        ventana) y el resto repartido entre «Área a tomar» y «Hoja compuesta».
        `resizeEvent` lo repite con el ancho REAL (al mostrarse y maximizarse)
        hasta que el usuario mueva un divisor o pliegue un panel: `setSizes`
        reparte la diferencia con el ancho real en proporción a cada tamaño, y
        «Origen» crecía con la ventana (330 → 470 px)."""
        sp = self.split
        # `real`: el layout ya le dio al divisor su ancho (en resizeEvent, también
        # el primero, que llega al mostrarse antes de que el divisor sea visible)
        total = sp.width() if real else max(900, self.width() - 32)
        avail = max(0, total - sp.handleWidth() * (sp.count() - 1))
        if self._side_w is None:
            self._side_w = max(_SIDE_MIN, min(330, int(avail * 0.22)))
        rest = max(0, avail - self._side_w)
        sp.setSizes([self._side_w, int(rest * self._flex_ratio), rest - int(rest * self._flex_ratio)])

    # «Origen» (0) es la barra lateral: conserva su ancho. El sitio que se libera
    # o se pide al plegar/desplegar lo ponen «Área a tomar» (1) y «Hoja
    # compuesta» (2). Antes se repartía también con «Origen», que crecía hasta
    # compartir media ventana con la hoja compuesta (reporte del usuario 2026-09-30).
    _FLEX = (1, 2)

    def _flex_open(self, exclude: int = -1) -> List[int]:
        return [i for i in self._FLEX if i != exclude and not self.panels[i].collapsed]

    def _on_panel_toggled(self, index: int, collapsed: bool):
        self._sizes_auto = False
        sizes = self.split.sizes()
        others = self._flex_open(exclude=index) or \
            [i for i in range(len(sizes)) if i != index and not self.panels[i].collapsed]
        if collapsed:
            self._sizes_before[index] = sizes[index]
            freed = max(0, sizes[index] - CollapsiblePanel.STRIP_W)
            sizes[index] = CollapsiblePanel.STRIP_W
            for k, i in enumerate(others):
                sizes[i] += freed // len(others) + (freed % len(others) if k == 0 else 0)
        else:
            want = self._sizes_before.pop(index, max(260, int(sum(sizes) * 0.3)))
            take = want - sizes[index]
            for i in others:
                sizes[i] = max(120, sizes[i] - take // max(1, len(others)))
            sizes[index] = want
        self.split.setSizes(sizes)
        self._update_collapse_rules()

    def _update_collapse_rules(self):
        """Siempre queda abierto «Área a tomar» u «Hoja compuesta»: el último de
        los dos no se puede plegar («Origen» solo, estirado a toda la ventana,
        no sirve de nada). «Origen» se puede plegar siempre."""
        flex_open = self._flex_open()
        for i, p in enumerate(self.panels):
            p.set_collapse_allowed(i not in self._FLEX or p.collapsed or len(flex_open) > 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # en ventanas estrechas el texto de ayuda se esconde para ganar alto
        self.intro.setVisible(self.width() >= 1250 and self.height() >= 700)
        if getattr(self, "_sizes_auto", False):
            self._apply_initial_sizes(real=True)

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
        # Hoja «aplanada»: sus vectores no están en ninguna capa (apagar capas no
        # la cambia y el reconocimiento por capas no encuentra nada en ella).
        t = _theme.tokens()
        self.lbl_nolayers = QtWidgets.QLabel()
        self.lbl_nolayers.setWordWrap(True)
        self.lbl_nolayers.setStyleSheet(
            f"border:1px solid {t.danger}; border-left:4px solid {t.danger}; color:{t.text}; "
            f"padding:6px 8px; border-radius:4px; font-size:12px;")
        self.lbl_nolayers.hide()
        lay.addWidget(self.lbl_nolayers)

        form = QtWidgets.QFormLayout(); form.setContentsMargins(0, 0, 0, 0)
        self.spn_src_scale = _spin('1" = ', "'", 0.1, 100000.0)
        self.spn_src_scale.setToolTip(_tr("Escala leída del texto de la hoja; corrígela si no es la del plano."))
        if self.comp.manual:
            self.spn_src_scale.setToolTip(_tr("Indica la escala real del plano escaneado; las medidas de la regla y del editor dependen de ella."))
        form.addRow(_tr("Escala de la hoja"), self.spn_src_scale)
        lay.addLayout(form)

        return box

    def _build_area_panel(self) -> QtWidgets.QWidget:
        box, lay = _panel(_tr("2 · Área a tomar"))
        self.lbl_mode = QtWidgets.QLabel(_tr("Arrastra un rectángulo sobre el plano; esquinas y lados se ajustan."))
        self.lbl_mode.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        self.lbl_mode.setWordWrap(True)
        lay.addWidget(self.lbl_mode)
        # Aviso «esta hoja aún no está en la hoja compuesta» (reporte del usuario
        # 2026-09-30: al volver a componer elegía otra hoja en la lista, no la
        # tomaba y al continuar seguía saliendo solo la anterior).
        t = _theme.tokens()
        self.pending_box = QtWidgets.QFrame()
        self.pending_box.setObjectName("pendingBox")
        self.pending_box.setStyleSheet(
            f"QFrame#pendingBox {{ background:{t.surface_alt}; border:1px solid {t.selection}; "
            f"border-left:4px solid {t.selection}; border-radius:4px; }}"
            f"QFrame#pendingBox QLabel {{ background:transparent; border:none; }}")
        prow = QtWidgets.QHBoxLayout(self.pending_box)
        prow.setContentsMargins(10, 6, 10, 6); prow.setSpacing(8)
        warn = QtWidgets.QLabel()
        warn.setPixmap(_icon("mdi:alert-outline", color=t.selection).pixmap(_ICON))
        prow.addWidget(warn, 0, QtCore.Qt.AlignTop)
        self.lbl_pending = QtWidgets.QLabel()
        self.lbl_pending.setWordWrap(True)
        prow.addWidget(self.lbl_pending, 1)
        self.pending_box.hide()
        lay.addWidget(self.pending_box)
        self.crop = ScanCropView() if self.comp.manual else _CropView()
        self.crop.selectionChanged.connect(self._on_selection_changed)
        # La hoja se muestra a 72 dpi; al hacer zoom, la parte visible se
        # re-renderiza nítida encima (z=1: bajo las guías y el rectángulo).
        self._crop_sharp = ViewportSharpener(self.crop, lambda: self.docs[self._cur_source][self._cur_page], z=1)
        lay.addWidget(self.crop, 1)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8)
        # Una acción principal («Tomar área»), una secundaria y las opciones del
        # rectángulo plegadas en un menú (antes eran cinco botones en fila).
        self.btn_take = QtWidgets.QPushButton(_icon("mdi:plus", color=_theme.tokens().text_on_accent),
                                              _tr("Tomar área"))
        self.btn_take.setIconSize(_ICON)
        self.btn_take.setMinimumHeight(_BTN_H)
        self.btn_take.setToolTip(_tr("Agregar el rectángulo marcado como una pieza nueva de la hoja compuesta"))
        self.btn_take.clicked.connect(lambda: self._take(full=False))
        self.btn_take_full = QtWidgets.QPushButton(
            _icon("mdi:file-document-outline", color=_theme.tokens().soft_text), _tr("Hoja completa"))
        self.btn_take_full.setProperty("soft", True)      # con color: se confundía con el fondo
        self.btn_take_full.setIconSize(_ICON)
        self.btn_take_full.setMinimumHeight(_BTN_H)
        self.btn_take_full.setToolTip(_tr("Agregar la hoja entera como una pieza"))
        self.btn_take_full.clicked.connect(lambda: self._take(full=True))
        self.btn_new = QtWidgets.QPushButton(_icon("mdi:plus", color=_theme.tokens().text_on_accent),
                                             _tr("Nueva pieza"))
        self.btn_new.setIconSize(_ICON)
        self.btn_new.setMinimumHeight(_BTN_H)
        self.btn_new.setToolTip(_tr("Dejar de editar la pieza seleccionada y marcar un área nueva"))
        self.btn_new.clicked.connect(lambda: self.view.select(-1))
        self.btn_new.hide()
        row.addWidget(self.btn_take); row.addWidget(self.btn_take_full); row.addWidget(self.btn_new)
        self.btn_area_opts, menu = _options_button(
            "mdi:tune-vertical", _tr("Opciones"), _tr("Cómo se ajusta el rectángulo al plano"))
        self.btn_area_snap = _check_action(
            menu, _tr("Imán a líneas"),
            _tr("Al arrastrar el rectángulo, sus lados saltan a las líneas generales de la "
                "hoja (match lines, marcos, bordes largos), que se resaltan en celeste"))
        self.btn_area_snap.toggled.connect(lambda on: setattr(self.crop, "snap_enabled", bool(on)))
        self.btn_trim = _check_action(
            menu, _tr("Sin línea de borde"),
            _tr("Recortar el área por dentro de la línea larga que corra pegada a cada lado "
                "(match line, marco de la vista), sea de la capa que sea, para que no aparezca "
                "en la hoja compuesta"))
        self.btn_trim.toggled.connect(self._on_trim_toggled)
        if self.comp.manual:
            self.btn_trim.setChecked(False)
            self.btn_trim.setEnabled(False)
            self.btn_area_snap.setChecked(False)
            self.btn_area_snap.setEnabled(False)
            self.lbl_mode.setText(_tr("Arrastra un área y mueve cada esquina para seguir el borde inclinado del plano."))
        row.addWidget(self.btn_area_opts)
        row.addStretch(1)
        self.lbl_area = QtWidgets.QLabel()
        self.lbl_area.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        row.addWidget(self.lbl_area)
        lay.addLayout(row)
        # Aviso de confirmación al tomar (el usuario puede tener el panel 3
        # plegado y no ver que la pieza ya se agregó). Se apaga solo.
        self.lbl_taken = QtWidgets.QLabel()
        self.lbl_taken.setWordWrap(True)
        self.lbl_taken.setStyleSheet(
            f"background:{t.success}; color:{t.text_on_accent}; font-weight:bold; "
            f"padding:6px 10px; border-radius:4px;")
        self.lbl_taken.hide()
        lay.addWidget(self.lbl_taken)
        self._taken_timer = QtCore.QTimer(self)
        self._taken_timer.setSingleShot(True)
        self._taken_timer.timeout.connect(self.lbl_taken.hide)
        return box

    def _notify_taken(self, piece: "C.Piece", idx: int):
        """Muestra unos segundos «✔ Área tomada como pieza N» en el panel 2."""
        self.lbl_taken.setText(_tr("✔ Área tomada como pieza {n} ({label}). Ya está en la hoja compuesta "
                                   "({total} pieza(s)).").format(n=idx + 1, label=piece.label,
                                                                 total=len(self.comp.pieces)))
        self.lbl_taken.show()
        self._taken_timer.start(5000)

    def _build_composite_panel(self) -> QtWidgets.QWidget:
        box, lay = _panel(_tr("3 · Hoja compuesta"))
        self.view = CompositeView(self.comp, self.docs)
        # UNA sola barra (pedido del usuario 2026-10-02: dos filas de botones y
        # una de texto «abrumaban»): a la izquierda las guías del escaneo, que
        # no cambian de sitio; a la derecha las acciones de la pieza elegida,
        # que solo aparecen con una pieza seleccionada; al final, ajustar vista.
        # Con poco ancho los botones quedan en solo icono (`ToolStrip`).
        bar = ToolStrip()
        self.tool_bar = bar
        if self.comp.manual:
            self.build_scan_tools(bar, _tool, _spin, _field_action, _check_action)
        bar.add_stretch()
        self.piece_tools = QtWidgets.QWidget()
        pt = QtWidgets.QHBoxLayout(self.piece_tools); pt.setContentsMargins(0, 0, 0, 0); pt.setSpacing(6)
        self.btn_ccw = _tool("mdi:rotate-left", _tr("Girar 90° antihorario"), icon_only=True)
        self.btn_ccw.clicked.connect(lambda: self._rotate(90))
        self.btn_cw = _tool("mdi:rotate-right", _tr("Girar 90° horario"), icon_only=True)
        self.btn_cw.clicked.connect(lambda: self._rotate(-90))
        self.btn_del = _tool("mdi:trash-can-outline", _tr("Quitar la pieza seleccionada (Supr)"), icon_only=True)
        self.btn_del.clicked.connect(self._delete)
        self.btn_piece_opts, pmenu = _options_button(
            "mdi:tune-vertical", _tr("Ajustes"), _tr("Ángulo fino y escala de la pieza seleccionada"))
        self.spn_angle = _spin("", "°", -360.0, 360.0, 2, 0.5)
        self.spn_angle.setToolTip(_tr("Ángulo fino de la pieza (antihorario)"))
        self.spn_angle.valueChanged.connect(self._on_angle_edited)
        _field_action(pmenu, _tr("Ángulo"), self.spn_angle)
        self.spn_piece_scale = _spin('1" = ', "'", 0.1, 100000.0)
        self.spn_piece_scale.setToolTip(_tr("Escala de la hoja de origen de esta pieza"))
        self.spn_piece_scale.valueChanged.connect(self._on_piece_scale_edited)
        _field_action(pmenu, _tr("Escala pieza"), self.spn_piece_scale)
        if self.comp.manual:
            pmenu.addSeparator()
            pmenu.addAction(_icon("mdi:rotate-left"), _tr("Girar a 0°"), self._reset_rotation)
        for w in (self.btn_ccw, self.btn_cw, self.btn_piece_opts, self.btn_del):
            pt.addWidget(w)
        bar.add(self.piece_tools)
        self.piece_tools.hide()
        bar.add_separator()
        btn_fit = _tool("mdi:fit-to-screen-outline", _tr("Ajustar la vista a todas las piezas"), icon_only=True)
        btn_fit.clicked.connect(self.view_fit)
        bar.add(btn_fit)
        lay.addWidget(bar)

        self.view.pieceMoved.connect(lambda _i: self._refresh_summary())
        self.view.selectionChangedIdx.connect(self._on_piece_selected)
        self.view.bridgesChanged.connect(self._on_bridges_changed)
        lay.addWidget(self.view, 1)

        # Abajo, la línea de estado: indicación de la herramienta activa o el
        # resultado de la medida (+ «Calibrar escala…») | resumen | uniones (menú)
        # | escala de la hoja (solo si hay varias).
        srow = QtWidgets.QHBoxLayout(); srow.setSpacing(8)
        self.lbl_status = QtWidgets.QLabel()
        self.lbl_status.setStyleSheet(f"color:{_theme.tokens().text}; font-size:12px;")
        self.lbl_status.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        srow.addWidget(self.lbl_status, 1)
        if self.comp.manual:
            self.build_scan_status(srow)
        self.lbl_summary = QtWidgets.QLabel()
        self.lbl_summary.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        srow.addWidget(self.lbl_summary)
        self.lbl_bridges = QtWidgets.QLabel()
        self.lbl_bridges.setStyleSheet(f"color:{_theme.tokens().success}; font-weight:bold;")
        srow.addWidget(self.lbl_bridges)
        self.btn_join_opts, jmenu = _options_button(
            "mdi:link-variant", _tr("Uniones"), _tr("Cómo se unen las piezas vecinas"))
        self.btn_magnet = _check_action(
            jmenu, _tr("Imán"),
            _tr("Al arrastrar, los extremos de las líneas se pegan (o se alinean) con los de la pieza vecina"))
        self.btn_magnet.toggled.connect(lambda on: setattr(self.view, "magnet_enabled", bool(on)))
        self.btn_anchors = _check_action(jmenu, _tr("Extremos"),
                                         _tr("Mostrar los extremos de línea en el borde de cada pieza"))
        self.btn_anchors.toggled.connect(self._toggle_anchors)
        self.btn_bridges = _check_action(
            jmenu, _tr("Puentes"),
            _tr("Unir con un trazo vectorial (misma capa) cada extremo con el que tiene enfrente en la pieza vecina"),
            checked=bool(self.comp.bridges))
        self.btn_bridges.toggled.connect(self._toggle_bridges)
        self.spn_gap = _spin("", " pt", 1.0, 2000.0, 0, 10.0)
        self.spn_gap.setValue(float(self.comp.bridge_max_pt))
        self.spn_gap.setToolTip(_tr("Separación máxima entre dos extremos para unirlos con un puente"))
        self.spn_gap.setEnabled(bool(self.comp.bridges))
        self.spn_gap.valueChanged.connect(self._on_gap_edited)
        _field_action(jmenu, _tr("hueco máx."), self.spn_gap)
        srow.addWidget(self.btn_join_opts)
        if self.comp.manual:
            self.btn_join_opts.hide()
            self.view.magnet_enabled = False
        self.lbl_target_scale = QtWidgets.QLabel(_tr("Escala de la hoja"))
        srow.addWidget(self.lbl_target_scale)
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
        # Miniaturas de a una tras mostrar la lista (antes se renderizaban todas
        # aquí: ~1.5 s con 19 hojas y el compositor tardaba en abrir).
        self._thumb_queue = []
        for i in range(doc.page_count):
            key = (self._cur_source, i)
            icon = self._thumb_cache.get(key) or self._thumb_placeholder(doc[i])
            if key not in self._thumb_cache:
                self._thumb_queue.append(key)
            item = QtWidgets.QListWidgetItem(icon, "")
            self._label_page_item(item, i)
            self.lst_pages.addItem(item)
        row = self._cur_page if 0 <= self._cur_page < doc.page_count else 0
        self.lst_pages.setCurrentRow(row)
        self.lst_pages.blockSignals(False)
        self._on_page_changed(row)
        if self._thumb_queue:
            self._thumb_timer.start()

    def _pieces_on_page(self, source: int, page: int) -> int:
        return sum(1 for p in self.comp.pieces if p.source == source and p.page == page)

    def _label_page_item(self, item: QtWidgets.QListWidgetItem, page: int):
        """Texto de una hoja de la lista: «sin capas» (hoja aplanada) y «✔ Tomada»
        en negrita si ya está en la hoja compuesta (así se ve cuáles entran)."""
        taken = self._pieces_on_page(self._cur_source, page)
        flat = not self._uses_layers(self._cur_source, page)
        text = (_tr("Hoja {n} · sin capas") if flat else _tr("Hoja {n}")).format(n=page + 1)
        tips = []
        if taken:
            text += "\n" + (_tr("✔ Tomada") if taken == 1 else
                            _tr("✔ Tomada ({n} piezas)").format(n=taken))
            tips.append(_tr("Esta hoja ya está en la hoja compuesta."))
        if flat:
            tips.append(_tr("Esta hoja no interactúa con las capas: sus vectores no están en "
                            "ninguna capa del PDF (hoja aplanada). Apagar capas no la cambia y el "
                            "reconocimiento por capas no encontrará utilidades en ella."))
        item.setText(text)
        item.setToolTip("\n\n".join(tips))
        font = item.font(); font.setBold(bool(taken)); item.setFont(font)
        if flat:
            item.setForeground(QtGui.QColor(_theme.tokens().text_muted))
        else:
            item.setData(QtCore.Qt.ForegroundRole, None)

    def _on_pieces_changed(self):
        """Tras tomar o quitar piezas: marcas de la lista y aviso de hoja sin tomar."""
        for i in range(self.lst_pages.count()):
            self._label_page_item(self.lst_pages.item(i), i)
        self._refresh_pending()

    def _page_pending(self) -> bool:
        """¿La hoja a la vista en el panel 2 falta en la hoja compuesta? Solo
        cuenta con piezas ya tomadas (sin ninguna, «Continuar» ni se habilita)."""
        return (bool(self.comp.pieces) and self._editing < 0
                and not self._pieces_on_page(self._cur_source, self._cur_page))

    def _refresh_pending(self):
        pending = self._page_pending()
        if pending:
            self.lbl_pending.setText(_tr(
                "La hoja {n} aún no está en la hoja compuesta: marca un área y pulsa «Tomar área», "
                "o pulsa «Hoja completa».").format(n=self._cur_page + 1))
        self.pending_box.setVisible(pending)

    def _thumb_placeholder(self, page) -> QtGui.QIcon:
        """Recuadro del tamaño de la miniatura mientras se renderiza."""
        w = _THUMB_W
        h = max(1, int(round(w * page.rect.height / max(page.rect.width, 1.0))))
        key = ("placeholder", h)
        if key not in self._thumb_cache:
            t = _theme.tokens()
            pm = QtGui.QPixmap(w, h)
            pm.fill(QtGui.QColor(t.surface_alt))
            p = QtGui.QPainter(pm)
            p.setPen(QtGui.QColor(t.border)); p.drawRect(0, 0, w - 1, h - 1)
            p.end()
            self._thumb_cache[key] = QtGui.QIcon(pm)
        return self._thumb_cache[key]

    def _next_thumb(self):
        """Renderiza UNA miniatura pendiente (la UI sigue respondiendo entre una y otra)."""
        while self._thumb_queue:
            source, page = self._thumb_queue.pop(0)
            if source != self._cur_source or not self.docs:
                continue                      # se cambió de PDF: esa lista ya no está
            item = self.lst_pages.item(page)
            if item is not None:
                item.setIcon(self._thumb(source, page))
            break
        if self._thumb_queue:
            self._thumb_timer.start()

    def _uses_layers(self, source: int, page: int) -> bool:
        key = (source, page)
        if key not in self._layers_cache:
            try:
                self._layers_cache[key] = PL.page_uses_layers(self.docs[source], page)
            except Exception:
                self._layers_cache[key] = True
        return self._layers_cache[key]

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
        if self.comp.manual or self._uses_layers(self._cur_source, row):
            self.lbl_nolayers.hide()
        else:
            self.lbl_nolayers.setText(_tr("Hoja {n} sin capas: sus vectores no están en ninguna capa del "
                                          "PDF. Apagar capas no la cambia y el reconocimiento de "
                                          "utilidades por capa no encontrará nada aquí.").format(n=row + 1))
            self.lbl_nolayers.show()
        if self._editing >= 0 and not self._syncing_crop:
            self.view.select(-1)          # cambiar de hoja a mano = empezar una pieza nueva
        with busy(self.crop, _tr("Cargando hoja {n}…").format(n=row + 1),
                  _tr("Líneas generales y escala de la hoja")):
            self._render_current_page(first=True)
            scale = self._detected_scale(self._cur_source, row)
        self.spn_src_scale.blockSignals(True)
        self.spn_src_scale.setValue(scale * 72.0)
        self.spn_src_scale.blockSignals(False)
        self._refresh_pending()

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
        if self.btn_trim.isChecked() and not self.comp.manual:
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
        polygon = self.crop.normalized_polygon() if self.comp.manual else []
        if [round(v, 9) for v in clip] == [round(v, 9) for v in piece.clip] and covers == piece.covers and polygon == piece.polygon:
            return
        piece.clip = clip
        piece.covers = covers
        piece.polygon = polygon
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
            if self.comp.manual and p.polygon:
                self.crop.set_polygon([QtCore.QPointF(x * full.width(), y * full.height()) for x, y in p.polygon])
        finally:
            self._syncing_crop = False
        self.lbl_mode.setText(_tr("Editando el área de la pieza {n} ({name}). Ajusta el rectángulo; "
                                  "la pieza se actualiza sola.").format(n=idx + 1, name=p.label or ""))
        if self.comp.manual:
            self.lbl_mode.setText(_tr("Ajusta las cuatro esquinas; la pieza seleccionada se actualiza sola."))
        self.btn_take.hide(); self.btn_take_full.hide(); self.btn_new.show()

    def _leave_edit_mode(self):
        self.lbl_mode.setText(_tr("Arrastra un rectángulo sobre el plano; esquinas y lados se ajustan."))
        if self.comp.manual:
            self.lbl_mode.setText(_tr("Arrastra un área y mueve cada esquina para seguir el borde inclinado del plano."))
        self.btn_new.hide(); self.btn_take.show(); self.btn_take_full.show()

    def _add_pdf(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr("Agregar PDF"), DOWNLOADS, "PDF (*.pdf)")
        if not path:
            return
        with busy(self, _tr("Abriendo PDF…"), os.path.basename(path)):
            self._open_extra_pdf(path)

    def _open_extra_pdf(self, path: str):
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
        with busy(self.view, _tr("Agregando la pieza…"),
                  _tr("Bordes, extremos de línea y uniones con las vecinas")):
            self._take_area(full)

    def _take_area(self, full: bool):
        res = self._current_clip(full)
        if res is None:
            return
        clip, covers = res
        src_scale = self.spn_src_scale.value() / 72.0
        piece = C.Piece(self._cur_source, self._cur_page, clip, src_scale=src_scale,
                        label=f"{self.sources[self._cur_source]['name']} · {self._cur_page + 1}",
                        covers=covers)
        if self.comp.manual and not full:
            piece.polygon = self.crop.normalized_polygon()
        bb = C.bounds(self.comp, self.view.page_size)
        if bb is not None:
            piece.x, piece.y = bb[2] + 24.0, bb[1]
        self.comp.pieces.append(piece)
        self._refresh_scale_combo()
        self.view.rebuild(keep_selection=len(self.comp.pieces) - 1)
        self.view.fit_all()
        self._refresh_summary()
        self._on_pieces_changed()
        self._notify_taken(piece, len(self.comp.pieces) - 1)
        self.view.warm_seams_now()        # las match lines ya, bajo la misma capa de carga

    def _delete(self):
        idx = self.view.selected_index()
        if idx < 0:
            return
        del self.comp.pieces[idx]
        self._refresh_scale_combo()
        self.view.rebuild()
        self._refresh_summary()
        self._on_piece_selected(-1)
        self._on_pieces_changed()

    def _rotate(self, delta: float):
        idx = self.view.selected_index()
        if idx < 0:
            return
        p = self.comp.pieces[idx]
        if self.comp.manual:              # escaneo: gira sobre su centro, no se corre
            self._turn_piece(idx, round(p.rotation + delta, 6))
            return
        p.rotation = (p.rotation + delta) % 360.0
        self.view.refresh_piece(idx)
        self._sync_piece_widgets(idx)
        self._refresh_summary()

    def _on_angle_edited(self, value: float):
        idx = self.view.selected_index()
        if idx < 0 or self._syncing_widgets:
            return
        if self.comp.manual:
            self._turn_piece(idx, float(value))
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
        self.piece_tools.setVisible(has)
        self._refresh_status()
        if has:
            self._sync_piece_widgets(idx)
            if idx != self._editing:
                self._editing = idx
                self._show_piece_in_area_panel(idx)
        elif self._editing >= 0:
            self._editing = -1
            self._crop_timer.stop()
            self._leave_edit_mode()
        self._refresh_pending()

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
        # con una sola escala no hay nada que elegir: ya va en el resumen
        self.cmb_scale.setVisible(len(scales) > 1)
        self.lbl_target_scale.setVisible(len(scales) > 1)
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
        self._refresh_status()
        w, h, _, _ = C.sheet_geometry(self.comp, self.view.page_size)
        self.lbl_summary.setText(_tr("{n} pieza(s) · hoja compuesta {w:.0f} × {h:.0f} pt · {s}").format(
            n=n, w=w, h=h, s=_scale_label(self.comp.target_scale())))

    def _refresh_status(self):
        """Línea de estado bajo la hoja: qué hacer con la herramienta activa."""
        if not hasattr(self, "lbl_status"):
            return
        text = self.scan_status_text() if self.comp.manual else ""
        if not text and self.comp.pieces and self.view.selected_index() < 0:
            text = _tr("Haz clic en una pieza para girarla, ajustarla o quitarla.")
        self.lbl_status.setText(text)
        self.lbl_status.setToolTip(text)

    # ── cierre ──────────────────────────────────────────────────────────
    def accept(self):
        if self._crop_timer.isActive():
            self._crop_timer.stop()
            self._apply_crop_edit()
        if self._page_pending() and not self._resolve_pending_page():
            return
        super().accept()

    def _has_area(self) -> bool:
        sel = self.crop._selection
        return sel is not None and sel.width() >= C.MIN_PIECE_PT and sel.height() >= C.MIN_PIECE_PT

    def _resolve_pending_page(self) -> bool:
        """«Continuar» con una hoja a la vista que NO está en la hoja compuesta:
        se pregunta antes de seguir solo con lo ya tomado. False = quedarse."""
        choice = self._ask_pending_page()
        if choice == "back":
            return False
        if choice == "replace":
            self.comp.pieces.clear()
            self.comp.scale_ft_per_pt = None      # la escala pasa a ser la de la hoja nueva
        if choice in ("add", "replace"):
            self._take(full=not self._has_area())
        return True

    def _ask_pending_page(self) -> str:
        """'add' | 'replace' | 'skip' | 'back'. «Usar solo esta hoja» solo con una
        única hoja entera (no se pierde trabajo de piezas acomodadas)."""
        n = self._cur_page + 1
        area = self._has_area()
        multi = len({p.source for p in self.comp.pieces} | {self._cur_source}) > 1
        names: List[str] = []
        for p in self.comp.pieces:
            s = (_tr("{pdf} · hoja {n}").format(pdf=self.sources[p.source]["name"], n=p.page + 1)
                 if multi else _tr("Hoja {n}").format(n=p.page + 1))
            if s not in names:
                names.append(s)
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle(_tr("Hoja sin tomar"))
        box.setText(_tr("La hoja {n} que estás viendo aún no está en la hoja compuesta.").format(n=n))
        box.setInformativeText(_tr("Si continúas así, solo se usará lo que ya tomaste: {taken}.").format(
            taken=", ".join(names)))
        b_add = box.addButton(_tr("Agregar el área marcada") if area else
                              _tr("Agregar la hoja {n} completa").format(n=n), QtWidgets.QMessageBox.AcceptRole)
        b_rep = None
        if self.comp.is_single_full_page():
            b_rep = box.addButton(_tr("Usar solo el área marcada") if area else
                                  _tr("Usar solo la hoja {n}").format(n=n), QtWidgets.QMessageBox.AcceptRole)
            b_rep.setProperty("soft", True)
        b_skip = box.addButton(_tr("Continuar sin ella"), QtWidgets.QMessageBox.DestructiveRole)
        b_back = box.addButton(_tr("Volver"), QtWidgets.QMessageBox.RejectRole)
        for b in (b_skip, b_back):
            b.setProperty("secondary", True)
        for b in box.buttons():            # la propiedad llegó después del estilo: re-aplicarlo
            b.style().unpolish(b); b.style().polish(b)
        box.setDefaultButton(b_add)
        box.setEscapeButton(b_back)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_add:
            return "add"
        if b_rep is not None and clicked is b_rep:
            return "replace"
        if clicked is b_skip:
            return "skip"
        return "back"

    def result_tuple(self):
        self.comp.last_view = [int(self._cur_source), int(self._cur_page)]
        return self.comp, self.sources, self.hidden_by_source

    def done(self, result):
        if not any(p.collapsed for p in self.panels):
            _settings().setValue("compositor/splitter", [int(v) for v in self.split.sizes()])
        super().done(result)

    def close_docs(self):
        self._thumb_timer.stop()
        self._thumb_queue = []
        for d in self.docs:
            try:
                d.close()
            except Exception:
                pass
        self.docs = []


def compose_sheet(parent, sources: List[dict], comp: Optional[C.Composite],
                  hidden_by_source: Optional[Dict[str, List[str]]], current_page: int = 0, manual: bool = False):
    """Abre el compositor. Devuelve ``(composite, sources, hidden_by_source)`` o
    None si se cancela. `sources` son dicts ``{name, data(bytes), path?}``."""
    with busy(parent, _tr("Abriendo «Componer hoja»…"),
              _tr("Preparando las hojas del PDF")):
        dlg = CompositeDialog(parent, sources, comp, hidden_by_source, current_page, manual=manual)
    try:
        if dlg.exec() != QtWidgets.QDialog.Accepted:   # showEvent lo maximiza al aparecer
            return None
        return dlg.result_tuple()
    finally:
        dlg.close_docs()
