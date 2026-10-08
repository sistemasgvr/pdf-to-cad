"""composite_dialog.py — «Componer hoja de trabajo».

Paso del asistente que reemplaza a «Organizar hojas». Tres PESTAÑAS, cada una a
ventana completa (pedido del usuario 2026-10-03: en tres columnas a cada vista le
quedaba poco sitio), en el orden en que se usan:

  Origen          PDF (se pueden agregar más) y galería de hojas con miniaturas
                  grandes (`composite_source_page`). Las capas se eligen en el paso
                  siguiente («Capas de la hoja»), ya sobre la hoja compuesta.
  Área a tomar    la hoja elegida, con ‹ › para pasar de hoja sin volver a Origen;
                  se marca un rectángulo y se «toma».
  Hoja compuesta  las piezas; se arrastran con imán, se giran, se corrige su
                  escala; los extremos de línea se marcan y los PUENTES que los
                  unirán se dibujan en verde.

La hoja ELEGIDA es la hoja compuesta (pedido del usuario 2026-10-05: elegía la hoja,
pulsaba «Siguiente» y la hoja compuesta quedaba vacía): mientras ésta sea una sola hoja
entera (o esté vacía), elegir otra hoja (clic o flechas en «Origen», ‹ › en «Área a
tomar») la reemplaza, y la pieza queda EN EDICIÓN: un área marcada sobre su hoja la
recorta al momento y «Hoja completa» la vuelve a la hoja entera. Con trabajo de verdad
(un área, varias piezas) elegir otra hoja solo la muestra: se agrega con «Tomar área»,
«Hoja completa» o Ctrl+clic en «Origen», y con una sola pieza el aviso ofrece «Usar
solo esta hoja».

Navegación: las pestañas siempre son clicables (se puede volver a cualquiera) y el
pie lleva «‹ Atrás» / «Siguiente ›» además de «Continuar». Antes de continuar se
revisa lo que falta (`composite_checks`): sin piezas no se puede; un área marcada
sin tomar o una hoja a la vista que no está en la hoja compuesta se avisan en el pie
y se preguntan al continuar. Esc no cierra la ventana (`NoEscapeClose`).

Todo lo geométrico vive en `composite.py`; aquí solo hay Qt.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from hoja import composite as C
from hoja import composite_checks as CK
import vector_pipeline as VP
from ui.asistente.composite_view import CompositeView, _qpixmap
from ui.asistente.composite_source_page import SourcePageMixin
from ui.asistente.composite_tabs import WorkTabs, BADGE_COUNT, BADGE_WARN
from ui.asistente.pdf_view_quality import ViewportSharpener
from traduccion.i18n import t as _tr
from ui.comun.icons import icon as _icon
from ui.asistente.sheet_crop_dialog import _CropView
from ui.asistente.scan_crop_view import ScanCropView
from ui.asistente.composite_scan_ui import ScanToolsMixin
from ui.asistente.composite_choice import ChosenSheetMixin
from ui.asistente.tool_strip import ToolStrip
from ui.comun.busy import busy
from ui.comun.widgets import maximize_on_show
from ui.asistente.wizard_widgets import NoEscapeClose, StepBar, wizard_header, wizard_footer
from ui.comun import theme as _theme

_ICON = QtCore.QSize(20, 20)
_BTN_H = 38            # alto de TODOS los botones del compositor (= QPushButton del tema)
TAB_SOURCE, TAB_AREA, TAB_SHEET = CK.TAB_SOURCE, CK.TAB_AREA, CK.TAB_SHEET


def _scale_label(ft_per_pt: float) -> str:
    return '1" = {v:g}\''.format(v=round(ft_per_pt * 72.0, 3))


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


def _banner(color: str) -> tuple[QtWidgets.QFrame, QtWidgets.QLabel]:
    """Aviso en línea (borde izquierdo de color + icono + texto)."""
    t = _theme.tokens()
    box = QtWidgets.QFrame()
    box.setObjectName("compBanner")
    box.setStyleSheet(
        f"QFrame#compBanner {{ background:{t.surface_alt}; border:1px solid {color}; "
        f"border-left:4px solid {color}; border-radius:4px; }}"
        f"QFrame#compBanner QLabel {{ background:transparent; border:none; }}")
    row = QtWidgets.QHBoxLayout(box)
    row.setContentsMargins(10, 6, 10, 6); row.setSpacing(8)
    ic = QtWidgets.QLabel()
    ic.setPixmap(_icon("mdi:alert-outline", color=color).pixmap(_ICON))
    row.addWidget(ic, 0, QtCore.Qt.AlignTop)
    lbl = QtWidgets.QLabel()
    lbl.setWordWrap(True)
    row.addWidget(lbl, 1)
    box.hide()
    return box, lbl


class CompositeDialog(NoEscapeClose, ChosenSheetMixin, SourcePageMixin, ScanToolsMixin, QtWidgets.QDialog):
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
        self._editing = -1            # pieza cuya área se edita en «Área a tomar» (-1 = nueva pieza)
        self._syncing_crop = False
        self._sel_dirty = False       # el usuario marcó un área que aún no tomó
        self._fitted: set = set()     # pestañas cuya vista ya se encuadró al mostrarse
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
        start = self._start_tab()          # antes de que la hoja a la vista entre sola
        self._fill_sources()
        self.view.rebuild()
        self._refresh_scale_combo()
        self._refresh_summary()
        if self._simple():
            self._choose_page()            # la hoja a la vista ya es la hoja compuesta
        self._go_tab(start)

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

    def _start_tab(self) -> int:
        """Pestaña con que se abre: sin piezas, a elegir la hoja; con la hoja entera
        que pone el editor, a marcar el área sobre ella; con piezas acomodadas, a
        la hoja compuesta."""
        if not self.comp.pieces:
            return TAB_SOURCE
        if self.comp.is_single_full_page():
            return TAB_AREA
        return TAB_SHEET

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)
        self.steps = StepBar(0)            # 1 Componer hoja › 2 Capas de la hoja › 3 Vista previa
        root.addWidget(wizard_header(self.steps))
        if self.comp.manual:
            self.steps.hide()
        self.tabs = WorkTabs([("mdi:file-document-outline", _tr("Origen")),
                              ("mdi:vector-rectangle", _tr("Área a tomar")),
                              ("mdi:vector-combine", _tr("Hoja compuesta"))])
        self.tabs.tabs[TAB_SOURCE].setToolTip(_tr("Elegir el PDF y la hoja"))
        self.tabs.tabs[TAB_AREA].setToolTip(_tr("Marcar el área de la hoja y tomarla"))
        self.tabs.tabs[TAB_SHEET].setToolTip(_tr("Acomodar las piezas tomadas"))
        self.tabs.currentChanged.connect(self._go_tab)
        root.addWidget(self.tabs)

        t = _theme.tokens()
        self.stack = QtWidgets.QStackedWidget()
        self.stack.setObjectName("compPanel")
        self.stack.setStyleSheet(f"QStackedWidget#compPanel {{ background:{t.surface}; "
                                 f"border:1px solid {t.border}; border-radius:8px; }}")
        self.pages = [self._build_source_page(_tool, _BTN_H), self._build_area_page(), self._build_composite_page()]
        for page in self.pages:
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)

        self.btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn_cancel.setProperty("secondary", True)
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_back = QtWidgets.QPushButton(_icon("mdi:chevron-left"), _tr("Atrás"))
        self.btn_back.setProperty("secondary", True)
        self.btn_back.setAutoDefault(False)
        self.btn_back.clicked.connect(lambda: self._go_tab(self.tabs.current() - 1))
        self.btn_next = QtWidgets.QPushButton(_tr("Siguiente"))
        self.btn_next.setIcon(_icon("mdi:chevron-right", color=t.soft_text))
        self.btn_next.setLayoutDirection(QtCore.Qt.RightToLeft)      # la flecha a la derecha
        self.btn_next.setProperty("soft", True)
        self.btn_next.setAutoDefault(False)
        self.btn_next.clicked.connect(self._on_next)
        self.btn_ok = QtWidgets.QPushButton(_tr("Continuar"))
        if self.comp.manual:
            self.btn_ok.setText(_tr("Importar hoja al editor"))
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        # qué falta para continuar (o «✔ Lista»); el enlace lleva a la pestaña que lo arregla
        self.lbl_check = QtWidgets.QLabel()
        self.lbl_check.setTextFormat(QtCore.Qt.RichText)
        self.lbl_check.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse
                                               | QtCore.Qt.LinksAccessibleByKeyboard)
        self.lbl_check.linkActivated.connect(self._on_check_link)
        footer = wizard_footer([self.lbl_check], _tr("Rueda = zoom · botón central = desplazar"),
                               [self.btn_cancel, self.btn_back, self.btn_next, self.btn_ok])
        root.addWidget(footer)
        for seq, step in ((QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_PageDown), 1),
                          (QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_PageUp), -1)):
            QtGui.QShortcut(seq, self, lambda s=step: self._go_tab(self.tabs.current() + s))
        self._on_piece_selected(-1)
        sc = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self.view, self._delete)
        sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)   # no borrar piezas al editar un número

    # ── navegación entre pestañas ───────────────────────────────────────
    def _go_tab(self, index: int):
        index = max(0, min(TAB_SHEET, int(index)))
        self.tabs.set_current(index, emit=False)
        self.stack.setCurrentIndex(index)
        self.btn_back.setVisible(index > TAB_SOURCE)
        self.btn_next.setVisible(index < TAB_SHEET)
        if index == TAB_SOURCE:
            self.btn_next.setText(_tr("Siguiente: Área a tomar"))
            if self.lst_pages.currentItem() is not None:
                self.lst_pages.scrollToItem(self.lst_pages.currentItem())
        elif index == TAB_AREA:
            self.btn_next.setText(_tr("Siguiente: Hoja compuesta"))
        # la primera vez que se muestra cada vista se encuadra (oculta, su tamaño era otro)
        if index not in self._fitted:
            self._fitted.add(index)
            if index == TAB_AREA:
                QtCore.QTimer.singleShot(0, lambda: self.crop.fitInView(self.crop._page_rect, QtCore.Qt.KeepAspectRatio)
                                         if self.crop._page_rect is not None else None)
            elif index == TAB_SHEET:
                QtCore.QTimer.singleShot(0, self.view.fit_all)
        self._refresh_checks()

    def changeEvent(self, event):
        super().changeEvent(event)
        # maximize_on_show maximiza DESPUÉS del primer show: la vista ya encuadrada
        # quedaba chica en un rincón. Se vuelve a encuadrar una vez, ya maximizada.
        if (event.type() == QtCore.QEvent.WindowStateChange and self.isMaximized()
                and not getattr(self, "_refit_done", False) and hasattr(self, "tabs")):
            self._refit_done = True
            self._fitted = set()
            QtCore.QTimer.singleShot(0, lambda: self._go_tab(self.tabs.current()))

    def _on_next(self):
        """«Siguiente ›». Al salir de «Área a tomar» con un área marcada sin
        tomar, se pregunta antes (el error típico: marcar y no pulsar «Tomar»)."""
        cur = self.tabs.current()
        if cur == TAB_AREA and self._area_untaken():
            choice = self._ask_untaken_area()
            if choice == "back":
                return
            if choice == "take":
                self._take(full=False)
        self._go_tab(cur + 1)

    def _on_check_link(self, href: str):
        if href == "pick":
            self._choose_page()
        elif href == "take":
            self._go_tab(TAB_AREA)
            self._take(full=not self._has_area())
        elif href.startswith("tab:"):
            self._go_tab(int(href[4:]))

    # ── qué falta para continuar ────────────────────────────────────────
    def _area_untaken(self) -> bool:
        return self._sel_dirty and self._editing < 0 and self._has_area()

    def _checks(self) -> List[CK.Check]:
        return CK.checks(len(self.comp.pieces),
                         self._cur_page + 1 if self._area_untaken() else None,
                         self._cur_page + 1 if self._page_pending() else None)

    def _refresh_checks(self):
        """Pie: lo que falta (con enlace a donde se arregla) o «✔ Lista»;
        «Continuar» solo sin errores; insignias de las pestañas."""
        if not hasattr(self, "lbl_check"):
            return
        t = _theme.tokens()
        found = self._checks()
        ok = CK.ready(found)
        self.btn_ok.setEnabled(ok)
        n = len(self.comp.pieces)
        self.tabs.set_badge(TAB_SHEET, str(n), BADGE_COUNT)
        self.tabs.set_badge(TAB_AREA, "!" if any(c.tab == TAB_AREA and c.level == CK.WARN for c in found) else None,
                            BADGE_WARN)
        if not found:
            # con una sola pieza, qué se usará (la hoja elegida, entera o un área)
            if n == 1:
                p = self.comp.pieces[0]
                ready = (_tr("✔ Lista para continuar: hoja {n} completa") if self._is_full(p) else
                         _tr("✔ Lista para continuar: área de la hoja {n}")).format(n=p.page + 1)
            else:
                ready = _tr("✔ Lista para continuar: {n} pieza(s)").format(n=n)
            html = f"<span style='color:{t.success}; font-weight:bold'>{ready}</span>"
            self.lbl_check.setText(html)
            self.lbl_check.setToolTip("")
            return
        first = found[0]
        text = _tr(first.text).format(n=first.page)
        if first.code == "untaken_area":
            link, label = "take", _tr("Tomarla")
        elif first.code == "pending_page":
            link, label = "take", _tr("Tomar la hoja {n}").format(n=first.page)
        elif first.code == "no_pieces":
            link, label = "pick", _tr("Usar la hoja {n}").format(n=self._cur_page + 1)
        else:
            link, label = f"tab:{first.tab}", _tr("Ir")
        more = f"  <span style='color:{t.text_muted}'>(+{len(found) - 1})</span>" if len(found) > 1 else ""
        # lo que falta para seguir NO es un error (es el paso siguiente): tono neutro;
        # lo que quedó a medias (área marcada, hoja sin tomar), en ámbar con ⚠
        head = (f"<span style='color:{t.text}'>→ {text}</span>" if first.level == CK.ERROR else
                f"<span style='color:{t.selection}; font-weight:bold'>⚠ {text}</span>")
        self.lbl_check.setText(f"{head} <a href='{link}' style='color:{t.accent}'>{label}</a>{more}")
        self.lbl_check.setToolTip("\n".join(_tr(c.text).format(n=c.page) for c in found))

    # ── pestaña «Área a tomar» ──────────────────────────────────────────
    def _build_area_page(self) -> QtWidgets.QWidget:
        t = _theme.tokens()
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        # hoja a la vista y ‹ › para pasar de hoja sin volver a «Origen»
        nav = QtWidgets.QHBoxLayout(); nav.setSpacing(8)
        self.btn_prev_page = _tool("mdi:chevron-left", _tr("Hoja anterior"), icon_only=True)
        self.btn_prev_page.clicked.connect(lambda: self._step_page(-1))
        nav.addWidget(self.btn_prev_page)
        self.lbl_page = QtWidgets.QLabel()
        f = self.lbl_page.font(); f.setBold(True); f.setPointSize(f.pointSize() + 2); self.lbl_page.setFont(f)
        nav.addWidget(self.lbl_page)
        self.btn_next_page = _tool("mdi:chevron-right", _tr("Hoja siguiente"), icon_only=True)
        self.btn_next_page.clicked.connect(lambda: self._step_page(1))
        nav.addWidget(self.btn_next_page)
        self.lbl_page_info = QtWidgets.QLabel()
        self.lbl_page_info.setStyleSheet(f"color:{t.text_muted};")
        self.lbl_page_info.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        nav.addWidget(self.lbl_page_info, 1)
        self.btn_all_pages = _tool("mdi:grid", _tr("Ver todas las hojas"), _tr("Volver a «Origen» para elegir otra hoja"))
        self.btn_all_pages.clicked.connect(lambda: self._go_tab(TAB_SOURCE))
        nav.addWidget(self.btn_all_pages)
        lay.addLayout(nav)
        self.lbl_mode = QtWidgets.QLabel(_tr("Arrastra un rectángulo sobre el plano; esquinas y lados se ajustan."))
        self.lbl_mode.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
        self.lbl_mode.setWordWrap(True)
        lay.addWidget(self.lbl_mode)
        # Hoja «aplanada»: sus vectores no están en ninguna capa (apagar capas no
        # la cambia y el reconocimiento por capas no encuentra nada en ella).
        self.nolayers_box, self.lbl_nolayers = _banner(t.danger)
        lay.addWidget(self.nolayers_box)
        # Aviso «esta hoja aún no está en la hoja compuesta» (reporte del usuario
        # 2026-09-30: al volver a componer elegía otra hoja en la lista, no la
        # tomaba y al continuar seguía saliendo solo la anterior).
        self.pending_box, self.lbl_pending = _banner(t.selection)
        # con UNA pieza de otra hoja: cambiarla por ésta (con varias se perdería el armado)
        self.btn_pending_use = QtWidgets.QPushButton(_tr("Usar solo esta hoja"))
        self.btn_pending_use.setProperty("soft", True)
        self.btn_pending_use.setAutoDefault(False)
        self.btn_pending_use.setToolTip(_tr("Quitar lo tomado y usar solo la hoja que estás viendo"))
        self.btn_pending_use.clicked.connect(self._use_only_this_sheet)
        self.pending_box.layout().addWidget(self.btn_pending_use, 0, QtCore.Qt.AlignVCenter)
        lay.addWidget(self.pending_box)
        self.crop = ScanCropView() if self.comp.manual else _CropView()
        self.crop.selectionChanged.connect(self._on_selection_changed)
        self.crop.dragFinished.connect(self._on_crop_drag_done)
        # La hoja se muestra a 72 dpi; al hacer zoom, la parte visible se
        # re-renderiza nítida encima (z=1: bajo las guías y el rectángulo).
        self._crop_sharp = ViewportSharpener(self.crop, lambda: self.docs[self._cur_source][self._cur_page], z=1)
        lay.addWidget(self.crop, 1)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8)
        # Una acción principal («Tomar área»), una secundaria y las opciones del
        # rectángulo plegadas en un menú (antes eran cinco botones en fila).
        self.btn_take = QtWidgets.QPushButton(_icon("mdi:plus", color=t.text_on_accent), _tr("Tomar área"))
        self.btn_take.setIconSize(_ICON)
        self.btn_take.setMinimumHeight(_BTN_H)
        self.btn_take.setAutoDefault(False)
        self.btn_take.setToolTip(_tr("Agregar el rectángulo marcado como una pieza nueva de la hoja compuesta"))
        self.btn_take.clicked.connect(lambda: self._take(full=False))
        self.btn_take_full = QtWidgets.QPushButton(
            _icon("mdi:file-document-outline", color=t.soft_text), _tr("Hoja completa"))
        self.btn_take_full.setProperty("soft", True)      # con color: se confundía con el fondo
        self.btn_take_full.setIconSize(_ICON)
        self.btn_take_full.setMinimumHeight(_BTN_H)
        self.btn_take_full.setAutoDefault(False)
        self.btn_take_full.setToolTip(_tr("Agregar la hoja entera como una pieza"))
        self.btn_take_full.clicked.connect(lambda: self._take(full=True))
        self.btn_new = QtWidgets.QPushButton(_icon("mdi:plus", color=t.text_on_accent), _tr("Nueva pieza"))
        self.btn_new.setIconSize(_ICON)
        self.btn_new.setMinimumHeight(_BTN_H)
        self.btn_new.setAutoDefault(False)
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
        self.lbl_area.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
        row.addWidget(self.lbl_area)
        # la escala es de la hoja que se toma: va junto a «Tomar»
        row.addWidget(QtWidgets.QLabel(_tr("Escala de la hoja")))
        self.spn_src_scale = _spin('1" = ', "'", 0.1, 100000.0)
        self.spn_src_scale.setToolTip(_tr("Escala leída del texto de la hoja; corrígela si no es la del plano."))
        if self.comp.manual:
            self.spn_src_scale.setToolTip(_tr("Indica la escala real del plano escaneado; las medidas de la regla y del editor dependen de ella."))
        self.spn_src_scale.valueChanged.connect(self._on_src_scale_edited)
        row.addWidget(self.spn_src_scale)
        lay.addLayout(row)
        # Confirmación al tomar, con el paso siguiente a mano (la hoja compuesta
        # está en otra pestaña: hay que decir que la pieza ya se agregó). Se apaga sola.
        self.taken_box = QtWidgets.QFrame()
        self.taken_box.setObjectName("takenBox")
        self.taken_box.setStyleSheet(f"QFrame#takenBox {{ background:{t.success}; border-radius:4px; }}"
                                     f"QFrame#takenBox QLabel {{ color:{t.text_on_accent}; font-weight:bold; "
                                     f"background:transparent; }}")
        trow = QtWidgets.QHBoxLayout(self.taken_box)
        trow.setContentsMargins(10, 4, 6, 4); trow.setSpacing(8)
        self.lbl_taken = QtWidgets.QLabel()
        self.lbl_taken.setWordWrap(True)
        trow.addWidget(self.lbl_taken, 1)
        self.btn_see_sheet = QtWidgets.QPushButton(_tr("Ver hoja compuesta"))
        self.btn_see_sheet.setIcon(_icon("mdi:chevron-right"))
        self.btn_see_sheet.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.btn_see_sheet.setProperty("secondary", True)
        self.btn_see_sheet.setAutoDefault(False)
        self.btn_see_sheet.clicked.connect(lambda: self._go_tab(TAB_SHEET))
        trow.addWidget(self.btn_see_sheet)
        self.taken_box.hide()
        lay.addWidget(self.taken_box)
        self._taken_timer = QtCore.QTimer(self)
        self._taken_timer.setSingleShot(True)
        self._taken_timer.timeout.connect(self.taken_box.hide)
        return page

    def _step_page(self, step: int):
        row = self.lst_pages.currentRow() + step
        if 0 <= row < self.lst_pages.count():
            self.lst_pages.picking = True
            try:
                self.lst_pages.setCurrentRow(row)
            finally:
                self.lst_pages.picking = False
            self._choose_page()                # ‹ › = elegir la hoja, como un clic en «Origen»

    def _refresh_page_nav(self):
        """«Hoja 21 de 50» + PDF y si ya está tomada; ‹ › al borde se apagan."""
        if not hasattr(self, "lbl_page"):
            return
        total = self.docs[self._cur_source].page_count
        self.lbl_page.setText(_tr("Hoja {n} de {total}").format(n=self._cur_page + 1, total=total))
        info = self.sources[self._cur_source]["name"]
        taken = self._pieces_on_page(self._cur_source, self._cur_page)
        if taken:
            info += "  ·  " + _tr("✔ ya está en la hoja compuesta")
        self.lbl_page_info.setText(info)
        self.lbl_page_info.setToolTip(self.sources[self._cur_source]["name"])
        self.btn_prev_page.setEnabled(self._cur_page > 0)
        self.btn_next_page.setEnabled(self._cur_page < total - 1)
        self._refresh_source_selection()

    def _notify_taken(self, piece: "C.Piece", idx: int):
        """Muestra unos segundos «✔ Área tomada como pieza N» en «Área a tomar»."""
        self.lbl_taken.setText(_tr("✔ Área tomada como pieza {n} ({label}). Ya está en la hoja compuesta "
                                   "({total} pieza(s)).").format(n=idx + 1, label=piece.label,
                                                                 total=len(self.comp.pieces)))
        self.taken_box.show()
        self._taken_timer.start(8000)

    # ── pestaña «Hoja compuesta» ────────────────────────────────────────
    def _build_composite_page(self) -> QtWidgets.QWidget:
        t = _theme.tokens()
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        self.lbl_sheet_hint = QtWidgets.QLabel(_tr(
            "Acomoda las piezas arrastrándolas: el imán alinea los extremos de las líneas y los "
            "puentes (verde) los unen. Cada pieza conserva sus vectores, capas, textos y medidas."))
        if self.comp.manual:
            self.lbl_sheet_hint.setText(_tr("Usa la regla para enderezar cada pieza y pásala al editor para "
                                            "dibujar las utilidades a mano."))
        self.lbl_sheet_hint.setWordWrap(True)
        self.lbl_sheet_hint.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
        lay.addWidget(self.lbl_sheet_hint)
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
        # la pieza elegida ya está cargada en «Área a tomar»: este botón lleva allí
        self.btn_edit_area = _tool("mdi:vector-rectangle", _tr("Editar área"),
                                   _tr("Ajustar en «Área a tomar» el recorte de la pieza seleccionada"))
        self.btn_edit_area.clicked.connect(lambda: self._go_tab(TAB_AREA))
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
        for w in (self.btn_edit_area, self.btn_ccw, self.btn_cw, self.btn_piece_opts, self.btn_del):
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
        self.lbl_status.setStyleSheet(f"color:{t.text}; font-size:12px;")
        self.lbl_status.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        srow.addWidget(self.lbl_status, 1)
        if self.comp.manual:
            self.build_scan_status(srow)
        self.lbl_summary = QtWidgets.QLabel()
        self.lbl_summary.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
        srow.addWidget(self.lbl_summary)
        self.lbl_bridges = QtWidgets.QLabel()
        self.lbl_bridges.setStyleSheet(f"color:{t.success}; font-weight:bold;")
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
        return page

    # ── hojas ───────────────────────────────────────────────────────────
    def _on_pieces_changed(self):
        """Tras tomar o quitar piezas: marcas de la lista y aviso de hoja sin tomar."""
        for i in range(self.lst_pages.count()):
            self._label_page_item(self.lst_pages.item(i), i)
        self._refresh_pending()

    def _page_pending(self) -> bool:
        """¿La hoja a la vista en «Área a tomar» falta en la hoja compuesta? Solo
        cuenta con piezas ya tomadas (sin ninguna, «Continuar» ni se habilita)."""
        return (bool(self.comp.pieces) and self._editing < 0
                and not self._pieces_on_page(self._cur_source, self._cur_page))

    def _refresh_pending(self):
        pending = self._page_pending()
        single = pending and len(self.comp.pieces) == 1
        if single:
            q = self.comp.pieces[0]
            where = (_tr("Hoja {n}").format(n=q.page + 1) if q.source == self._cur_source else
                     _tr("{pdf} · hoja {n}").format(pdf=self.sources[q.source]["name"], n=q.page + 1))
            self.lbl_pending.setText(_tr(
                "La hoja {n} aún no está en la hoja compuesta (que usa: {donde}). Para sumarla, marca un "
                "área y pulsa «Tomar área», o pulsa «Hoja completa».").format(n=self._cur_page + 1, donde=where))
        elif pending:
            self.lbl_pending.setText(_tr(
                "La hoja {n} aún no está en la hoja compuesta: marca un área y pulsa «Tomar área», "
                "o pulsa «Hoja completa».").format(n=self._cur_page + 1))
        self.btn_pending_use.setVisible(single)
        self.pending_box.setVisible(pending)
        self._refresh_page_nav()
        self._refresh_checks()

    def _guides(self, source: int, page: int) -> dict:
        key = (source, page)
        if key not in self._guide_cache:
            try:
                self._guide_cache[key] = C.guide_lines(self.docs[source][page])
            except Exception:
                self._guide_cache[key] = {"x": [], "y": []}
        return self._guide_cache[key]

    def _detected_scale(self, source: int, page: int) -> float:
        key = (source, page)
        if key not in self._scale_cache:
            try:
                self._scale_cache[key] = float(VP.detect_scale(self.docs[source][page]))
            except Exception:
                self._scale_cache[key] = 20 / 72.0
        return self._scale_cache[key]

    def _on_page_changed(self, row: int):
        if row < 0:
            return
        self._cur_page = row
        if self.comp.manual or self._uses_layers(self._cur_source, row):
            self.nolayers_box.hide()
        else:
            self.lbl_nolayers.setText(_tr("Hoja {n} sin capas: sus vectores no están en ninguna capa del "
                                          "PDF. Apagar capas no la cambia y el reconocimiento de "
                                          "utilidades por capa no encontrará nada aquí.").format(n=row + 1))
            self.nolayers_box.show()
        # cambiar de hoja a mano = empezar una pieza nueva; salvo si el usuario ELIGE la hoja
        # y la hoja compuesta es solo la elegida: `_choose_page` la cambia enseguida (si no,
        # el aviso «no está en la hoja compuesta» asomaba bajo «Cargando hoja…»)
        if self._editing >= 0 and not self._syncing_crop and not (self.lst_pages.picking and self._simple()):
            self.view.select(-1)
        with busy(self.crop, _tr("Cargando hoja {n}…").format(n=row + 1),
                  _tr("Líneas generales y escala de la hoja")):
            self._render_current_page(first=True)
            scale = self._detected_scale(self._cur_source, row)
        self.spn_src_scale.blockSignals(True)
        self.spn_src_scale.setValue(scale * 72.0)
        self.spn_src_scale.blockSignals(False)
        self.taken_box.hide()
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
            self._sel_dirty = False
            self.crop.set_selection(None)
            QtCore.QTimer.singleShot(0, lambda: self.crop.fitInView(rect, QtCore.Qt.KeepAspectRatio))

    def _on_selection_changed(self, rect):
        ok = rect is not None and rect.width() >= C.MIN_PIECE_PT and rect.height() >= C.MIN_PIECE_PT
        self.btn_take.setEnabled(ok)
        self.lbl_area.setText(_tr("{w:.0f} × {h:.0f} pt").format(w=rect.width(), h=rect.height()) if ok else "")
        if self._editing >= 0 and ok and not self._syncing_crop:
            self._crop_timer.start()
        if not self._syncing_crop and self._editing < 0:
            self._sel_dirty = ok
            if ok:
                self.taken_box.hide()
        self._refresh_checks()

    def _current_clip(self, full: bool = False):
        """(clip normalizado, covers) del rectángulo de «Área a tomar». Con «Sin
        línea de borde» activo el clip pasa por el centro de la línea de borde y
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
        """Modo edición: el rectángulo de «Área a tomar» ES el área de la pieza seleccionada."""
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
        self._refresh_area_mode()
        self._on_pieces_changed()

    def _on_trim_toggled(self, _on: bool):
        if self._editing >= 0:
            self._crop_timer.start()

    def _show_piece_in_area_panel(self, idx: int):
        """Lleva «Área a tomar» al PDF/hoja de la pieza y dibuja su área para editarla."""
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
            # la hoja entera se ve sin tinte (solo borde y asas: `_CropView._fill_for`)
            self.crop.set_selection(QtCore.QRectF(x0 * full.width(), y0 * full.height(),
                                                  (x1 - x0) * full.width(), (y1 - y0) * full.height()))
            if self.comp.manual and p.polygon:
                self.crop.set_polygon([QtCore.QPointF(x * full.width(), y * full.height()) for x, y in p.polygon])
            self.spn_src_scale.blockSignals(True)          # la escala es la de ESTA pieza
            self.spn_src_scale.setValue(p.src_scale * 72.0)
            self.spn_src_scale.blockSignals(False)
        finally:
            self._syncing_crop = False
        self._sel_dirty = False
        self._refresh_area_mode()

    def _leave_edit_mode(self):
        self._sel_dirty = False
        self._refresh_area_mode()

    # ── piezas ──────────────────────────────────────────────────────────
    def _take(self, full: bool):
        if self._editing_here():
            self._set_piece_area(self._editing, full)
            return
        with busy(self.view, _tr("Agregando la pieza…"),
                  _tr("Bordes, extremos de línea y uniones con las vecinas")):
            self._take_area(full)

    def _take_area(self, full: bool):
        if self._editing_here():             # la hoja ya tiene su pieza en edición: actualizarla
            self._set_piece_area(self._editing, full)
            return
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
        self._sel_dirty = False
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
        for w in (self.btn_ccw, self.btn_cw, self.spn_angle, self.spn_piece_scale, self.btn_del,
                  self.btn_edit_area):
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
        self._refresh_status()
        w, h, _, _ = C.sheet_geometry(self.comp, self.view.page_size)
        self.lbl_summary.setText(_tr("{n} pieza(s) · hoja compuesta {w:.0f} × {h:.0f} pt · {s}").format(
            n=n, w=w, h=h, s=_scale_label(self.comp.target_scale())))
        self._refresh_checks()

    def _refresh_status(self):
        """Línea de estado bajo la hoja: qué hacer con la herramienta activa."""
        if not hasattr(self, "lbl_status"):
            return
        text = self.scan_status_text() if self.comp.manual else ""
        if not text and self.comp.pieces and self.view.selected_index() < 0:
            text = _tr("Haz clic en una pieza para girarla, ajustarla o quitarla.")
        elif not text and not self.comp.pieces:
            text = _tr("Aún no hay piezas: toma un área en «Área a tomar».")
        self.lbl_status.setText(text)
        self.lbl_status.setToolTip(text)

    # ── cierre ──────────────────────────────────────────────────────────
    def accept(self):
        if self._crop_timer.isActive():
            self._crop_timer.stop()
            self._apply_crop_edit()
        if not self.comp.pieces:
            if not self._area_untaken():
                self._go_tab(TAB_AREA)        # «Continuar» viene apagado; por si acaso
                return
            self._take(full=False)            # solo hay un área marcada: tomarla es lo único útil
        elif self._page_pending():
            # la pregunta de la hoja sin tomar ya ofrece agregar el área marcada
            if not self._resolve_pending_page():
                return
        elif self._area_untaken():
            choice = self._ask_untaken_area()
            if choice == "back":
                self._go_tab(TAB_AREA)
                return
            if choice == "take":
                self._take(full=False)
        super().accept()

    def _has_area(self) -> bool:
        sel = self.crop._selection
        return sel is not None and sel.width() >= C.MIN_PIECE_PT and sel.height() >= C.MIN_PIECE_PT

    def _ask_untaken_area(self) -> str:
        """'take' | 'skip' | 'back': hay un área marcada que no se tomó."""
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(_tr("Área sin tomar"))
        box.setText(_tr("Marcaste un área en la hoja {n} pero no la tomaste.").format(n=self._cur_page + 1))
        box.setInformativeText(_tr("Si no la tomas, no estará en la hoja compuesta."))
        b_take = box.addButton(_tr("Tomar el área"), QtWidgets.QMessageBox.AcceptRole)
        b_skip = box.addButton(_tr("Seguir sin tomarla"), QtWidgets.QMessageBox.DestructiveRole)
        b_back = box.addButton(_tr("Volver"), QtWidgets.QMessageBox.RejectRole)
        for b in (b_skip, b_back):
            b.setProperty("secondary", True)
            b.style().unpolish(b); b.style().polish(b)
        box.setDefaultButton(b_take)
        box.setEscapeButton(b_back)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_take:
            return "take"
        if clicked is b_skip:
            return "skip"
        return "back"

    def _resolve_pending_page(self) -> bool:
        """«Continuar» con una hoja a la vista que NO está en la hoja compuesta:
        se pregunta antes de seguir solo con lo ya tomado. False = quedarse."""
        choice = self._ask_pending_page()
        if choice == "back":
            self._go_tab(TAB_AREA)
            return False
        if choice == "replace":
            self._use_only_this_sheet()
        elif choice == "add":
            self._take(full=not self._has_area())
        return True

    def _ask_pending_page(self) -> str:
        """'add' | 'replace' | 'skip' | 'back'. «Usar solo esta hoja» solo con UNA
        pieza (no se pierde trabajo de piezas acomodadas)."""
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
        if len(self.comp.pieces) == 1:
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
