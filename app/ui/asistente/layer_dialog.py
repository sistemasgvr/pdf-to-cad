"""layer_dialog.py — Paso «Capas de la hoja» del asistente de reconocimiento.

Se muestra DESPUÉS de componer la hoja y ANTES de reconocer/dibujar la vista
previa. Izquierda: la hoja renderizada (zoom con rueda, pan con botón central,
minimapa). Derecha, de arriba abajo:
  · (cabecera a todo el ancho) barra de pasos «1 Componer hoja › 2 Capas de la
    hoja › 3 Vista previa»: el paso 1 es clicable y vuelve al compositor;
  · «◀ Hoja N / M ▶» para
    cambiar de hoja sin salir (las capas marcadas se conservan: la visibilidad
    es del documento);
  · tarjeta «Reconocer» (`layer_dialog_recog`): qué utilidades se reconocen — «Todas»
    + una casilla por utilidad con su color (sin ninguna marcada, o con una marcada y
    todas sus capas ocultas, no se puede continuar);
  · tarjeta «Capas del plano»: árbol por utilidad (Agua, Alcantarillado,
    Drenaje, Gas, Eléctrico, Telecom, Otras — las del desplegable «Tipo de
    utilidad» de la app). La casilla del GRUPO enciende/apaga todas las capas
    de esa utilidad en la hoja (al volver a encenderla cada capa recupera el
    estado que tenía); desplegándolo se marca capa por capa. Una capa con líneas
    de VARIAS utilidades (por sus letras: `G-XREF` con «—T—» y «—W—») sale en el
    grupo de cada una, con las dos filas sincronizadas (`pdf_layers.layer_groups`).
    Buscador y «Mostrar / Ocultar todas» sobre lo filtrado.
  · (pie a todo el ancho) «Opacidad» del PDF — el mismo desplegable del
    editor —, ayuda y Cancelar | Continuar.
Cada cambio re-renderiza la hoja en vivo.

Al aceptar, la visibilidad queda aplicada en el ``fitz.Document`` de la ventana
principal (``pdf_layers.set_hidden``): el lienzo se carga ya sin esas capas y el
reconocimiento las ignora. Al cancelar (o volver a componer) se restaura la
visibilidad previa.

Toda la lógica de datos (listar capas, apagar/encender, utilidad por nombre)
vive en ``pdf_layers.py`` (puro, testeable). Aquí solo va la UI.
"""
from __future__ import annotations

import time

from PySide6 import QtCore, QtGui, QtWidgets

import fitz

from ui.comun.busy import busy, detalle_de
from ui.comun import fondo_pdf, fondo_trabajo
from ui.asistente import capas_previas

from traduccion.i18n import t as _tr
from ui.comun.icons import icon as _icon
from hoja import pdf_layers
from reconocimiento import recognition
from ui.comun import theme as _theme
from ui.comun.ui_common import swatch_icon
from ui.comun.widgets import ZoomPanView, MiniMap, etiquetas_cortas, maximize_on_show, side_panel_width, GripSplitter
from ui.asistente.layer_dialog_info import LayerInfoMixin, layer_tooltip as _layer_tooltip
from ui.asistente.layer_dialog_recog import (RecogCardMixin, card as _card, utility_qcolor,  # noqa: F401
                                             _UTILITY_RECOG_LABEL)
from ui.asistente.wizard_widgets import NoEscapeClose, StepBar, OpacityButton, wizard_header, wizard_footer
from ui.asistente.layer_assignments import LayerAssignmentsMixin
from ui.asistente.layer_dialog_scale import ScaleCalibrationMixin

# Zoom del render PDF (matriz PyMuPDF). El lienzo principal usa ~3.5; aquí
# 3.0 da nitidez al acercar con la rueda sin ralentizar demasiado el
# re-render al marcar/desmarcar capas (~0.3–0.5 s en hojas 36×24").
_PREVIEW_ZOOM = 3.0
# Espera tras el último clic en una casilla antes de re-renderizar (ms).
_RERENDER_DELAY_MS = 150
# Un re-render más lento que esto muestra «Actualizando la vista…» en el
# siguiente (en hojas rápidas la capa solo parpadearía).
_SLOW_RENDER_S = 0.25
# Ancho del panel derecho; la vista previa toma el resto (era 440: pedido del usuario
# 2026-10-09, más angosto; «Reconocer» en dos columnas necesita ~325 px).
_PANEL_WIDTH = 350
# Roles de datos de las filas del árbol.
_ROLE_NAME = QtCore.Qt.UserRole            # nombre completo de la capa (None en grupos)
_ROLE_UTILITY = QtCore.Qt.UserRole + 1     # clave de utilidad de la fila

# `choose_sheet_layers` devuelve esto si el usuario pulsa «◀ Componer hoja».
LAYERS_BACK = "back"


class SheetLayersDialog(ScaleCalibrationMixin, LayerAssignmentsMixin, LayerInfoMixin, RecogCardMixin,
                        NoEscapeClose, QtWidgets.QDialog):
    """Mostrar/ocultar capas OCG de una hoja con vista previa en vivo; a la izquierda,
    las capas que se toman por las LETRAS de su línea y la leyenda del PDF
    (`layer_dialog_info`). Esc no la cierra (`NoEscapeClose`): quita el resaltado."""

    def __init__(self, parent, doc: fitz.Document, page_index: int, layers=None, layout=None,
                 recognition_utilities=None, can_go_back: bool = False, letters_off=None,
                 legend_sources=None, legend_cache=None, roles_by_utility=None,
                 scale_ft_per_pt=None, previa=None, en_proceso=False):
        super().__init__(parent)
        self._doc = doc
        self._page_index = page_index
        # hoja compuesta grande: lo pesado ya se leyó en el proceso trabajador (`capas_previas`)
        # y las imágenes de la hoja se dibujan allí (`fondo_trabajo`); la ventana no se traba
        self._previa = previa
        self._previa_img = (((previa.hoja, previa.encendidas), previa.imagen)
                            if previa is not None and previa.imagen is not None else None)
        self._en_proceso = bool(en_proceso)
        self._render_estado = None         # (hoja, capas encendidas) de la imagen a la vista
        # Disposición de las hojas que forman esta página (hoja compuesta):
        # [((x0, y0, x1, y1) en pt, etiqueta), …]. Alimenta el minimapa esquemático.
        self._layout = layout
        self._page = doc[page_index]
        self._initial_hidden = pdf_layers.hidden_layers(doc)
        # `layers` permite reutilizar el listado ya calculado por quien nos llama.
        self._layers_raw = layers if layers is not None else pdf_layers.page_layers(doc, page_index)
        # capas que el usuario decidió NO tomar por las letras de su línea (panel izquierdo)
        self._letters_off = set(letters_off or ())
        self._init_assignments(roles_by_utility)
        self._layers = self._effective_layers()
        self._pix_item = None
        self._slow_render = False          # el último render tardó: el próximo avisa
        self._groups: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._items_by_name: dict[str, list] = {}   # capa → sus filas (una por grupo si es compartida)
        # estado por capa de una utilidad apagada, para reponerlo al encenderla
        self._util_memory: dict[str, dict[str, bool]] = {}
        self._syncing = False
        self.went_back = False
        t = _theme.tokens()

        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1240, 780)
        maximize_on_show(self)

        # Cabecera (pasos, a todo el ancho) · vista | panel · pie (opacidad y botones)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)   # margen uniforme alrededor de vista y panel
        root.setSpacing(10)
        self.steps = StepBar(1, back_enabled=can_go_back)
        self.steps.stepClicked.connect(lambda _i: self._go_back())
        root.addWidget(wizard_header(self.steps))
        self.view = ZoomPanView()
        from ui.asistente.layer_style_pick import StylePicker
        self._style_picker = StylePicker(self)
        # Minimapa (esquina inferior izquierda): esquema de la hoja mostrada con
        # el recuadro de lo visible; clic/arrastre centra la vista.
        self.minimap = MiniMap(self.view)
        # hoja enorme (hoja compuesta de muchas piezas): imagen reducida + recorte nítido
        self._nitidez = fondo_pdf.Nitidez(self.view, lambda: _PREVIEW_ZOOM, lambda: self._page)

        # Vista | panel derecho, con divisor arrastrable: el panel arranca con un
        # ancho acorde a la ventana (nunca más del 32 %) y el usuario lo ajusta.
        self.split = GripSplitter(QtCore.Qt.Horizontal)   # tirador visible y arrastrable
        self.split.addWidget(self.view)
        side = QtWidgets.QWidget()
        side.setMinimumWidth(320)
        panel = QtWidgets.QVBoxLayout(side)
        panel.setContentsMargins(0, 0, 10, 0)   # aire entre los controles y el divisor (2.0.0: a la izquierda)
        panel.setSpacing(10)
        self.split.addWidget(side)
        self.split.setStretchFactor(0, 1); self.split.setStretchFactor(1, 0)
        root.addWidget(self.split, 1)
        self._side = side

        # ── navegador de hojas ──
        nav = QtWidgets.QHBoxLayout()
        self.btn_prev = QtWidgets.QToolButton()
        self.btn_prev.setText("◀")
        self.btn_prev.setToolTip(_tr("Hoja anterior"))
        self.btn_prev.clicked.connect(lambda: self._go_sheet(self._page_index - 1))
        self.btn_next = QtWidgets.QToolButton()
        self.btn_next.setText("▶")
        self.btn_next.setToolTip(_tr("Hoja siguiente"))
        self.btn_next.clicked.connect(lambda: self._go_sheet(self._page_index + 1))
        self.lbl_sheet = QtWidgets.QLabel()
        self.lbl_sheet.setAlignment(QtCore.Qt.AlignCenter)
        f = self.lbl_sheet.font(); f.setBold(True); f.setPointSize(f.pointSize() + 2)
        self.lbl_sheet.setFont(f)
        for b in (self.btn_prev, self.btn_next):
            b.setFixedSize(44, 32)
            bf = b.font(); bf.setPointSize(bf.pointSize() + 3); b.setFont(bf)
        # 2.0.0 (como el prototipo): «◀ Hoja N / M ▶» flota sobre la hoja (arriba: abajo va el minimapa)
        from ui.asistente.wizard_widgets import flotar, pastilla
        for b in (self.btn_prev, self.btn_next):
            b.setFixedSize(32, 28)
        f = self.lbl_sheet.font(); f.setPointSize(f.pointSize() - 2); self.lbl_sheet.setFont(f)
        self.lbl_sheet.setMinimumWidth(110)
        self.pastilla_hoja = pastilla([self.btn_prev, self.lbl_sheet, self.btn_next])
        flotar(self.view, self.pastilla_hoja, "arriba")

        # ── tarjeta «Reconocer»: qué utilidades se leen del plano (`layer_dialog_recog`) ──
        self._build_recog_card(panel, recognition_utilities)

        # ── tarjeta «Capas del plano»: árbol por utilidad ──
        box, lay, head = _card(_tr("Capas del plano"))
        self.btn_all = QtWidgets.QToolButton()
        self.btn_all.setIcon(_icon("mdi:eye-outline")); self.btn_all.setToolTip(_tr("Mostrar todas"))
        self.btn_none = QtWidgets.QToolButton()
        self.btn_none.setIcon(_icon("mdi:eye-off-outline")); self.btn_none.setToolTip(_tr("Ocultar todas"))
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        head.addWidget(self.btn_all); head.addWidget(self.btn_none)
        hint = QtWidgets.QLabel(_tr("Pulsa una línea del PDF para identificar y resaltar su capa. "
                                   "Casilla = mostrar · interruptor = reconocer · ▸ = capa por capa"))
        if any(L.get("source") == "style" for L in self._layers):
            hint.setText(_tr("Clic en una capa para resaltarla y asignar su utilidad y rol abajo. "
                             "También puedes pulsar una línea del PDF para seleccionar su estilo. "
                             "Las casillas excluyen estilos del reconocimiento; el PDF conserva "
                             "su imagen. Calibra la escala antes de importar."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
        lay.addWidget(hint)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(_tr("Buscar capa…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        # 2.0.0 (prototipo «faltante»): 2.ª columna = el interruptor «Reconocer» de cada utilidad, en su
        # misma fila (refleja la casilla de siempre de la tarjeta «Reconocer»)
        self.tree.setColumnCount(2)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
        self.tree.header().resizeSection(1, 48)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        f = self.tree.font(); f.setPointSize(f.pointSize() + 1); self.tree.setFont(f)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.currentItemChanged.connect(self._focus_style)
        # Tras Esc se puede volver a resaltar pulsando la misma fila actual.
        self.tree.itemClicked.connect(
            lambda item, column: self._focus_style(item, column) if not self._hl_items else None)
        lay.addWidget(self.tree, 1)
        self._build_assignment_controls(lay)
        self.lbl_count = QtWidgets.QLabel()
        self.lbl_count.setStyleSheet(f"color:{t.text_muted};")
        lay.addWidget(self.lbl_count)
        panel.addWidget(box, 1)

        # ── pie a todo el ancho: opacidad · ayuda · Cancelar | Continuar ──
        # (volver a «Componer hoja» es el paso 1 de la cabecera: un solo sitio)
        self.opacity = OpacityButton(lambda: self._pix_item)
        btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        btn_cancel.setProperty("secondary", True)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QtWidgets.QPushButton(_tr("Continuar"))
        self.btn_ok.clicked.connect(self.accept)
        self.btn_ok.setDefault(True)
        root.addWidget(wizard_footer([self.opacity] + self._build_scale_control(scale_ft_per_pt),
                                     _tr("Rueda = zoom · botón central = desplazar"),
                                     [btn_cancel, self.btn_ok]))

        # Re-render diferido: varios clics seguidos → un solo render.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_RERENDER_DELAY_MS)
        self._timer.timeout.connect(self._render_live)

        # ── izquierda: «Leyenda» (capas por sus letras + leyenda del PDF) ──
        self._build_info_panel(legend_sources, legend_cache)

        self._fit_pending = True
        self._fill_list()
        self._refresh_recog_checks()
        self._update_sheet_widgets()
        self._render(first=True)

    def showEvent(self, e):
        super().showEvent(e)
        # El primer fitInView ocurre antes de que la vista tenga su tamaño real:
        # se repite al mostrar para que la hoja entre completa.
        if self._fit_pending and self._pix_item is not None:
            self._fit_pending = False
            # con el diálogo como contexto: si se borra antes, no se llama (llamado sobre un diálogo ya
            # borrado, el error tumbaba PySide 6.11 en el siguiente filtro de eventos)
            QtCore.QTimer.singleShot(0, self, self._apply_side_width)   # primero los anchos: la hoja entra en SU columna
            QtCore.QTimer.singleShot(0, self, self._fit_view)

    def _apply_side_width(self):
        w = self.width()
        self._apply_three_columns(side_panel_width(w, _PANEL_WIDTH))

    def _fit_view(self):
        if self._pix_item is not None:
            self.view.resetTransform()
            self.view.fitInView(self._pix_item, QtCore.Qt.KeepAspectRatio)
            self._view_auto = True          # hoja entera: sigue a la ventana (`_follow_window`)

    # ── árbol ───────────────────────────────────────────────────────────────
    def _fill_list(self):
        """Rellena el árbol: un grupo por utilidad (con su color) y sus capas."""
        self._syncing = True
        # clear() emite currentItemChanged(None, anterior). No ejecutar slots
        # que consulten filas mientras Qt las está destruyendo.
        blocker = QtCore.QSignalBlocker(self.tree)
        self.tree.clear()
        self._groups.clear()
        self._interruptores_arbol = {}
        self._items_by_name = {}
        by_util: dict[str, list[dict]] = {}
        for L in self._layers:
            for key in pdf_layers.layer_groups(L):      # compartida: en el grupo de cada utilidad
                by_util.setdefault(key, []).append(L)
        for key, label in pdf_layers.UTILITIES:
            group = by_util.get(key, [])
            if not group:
                continue
            color = utility_qcolor(key)
            hdr = QtWidgets.QTreeWidgetItem([_tr(label)])
            hdr.setIcon(0, swatch_icon(color, 14))
            hdr.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            hf = hdr.font(0); hf.setBold(True); hdr.setFont(0, hf)
            hdr.setData(0, _ROLE_NAME, None)
            hdr.setData(0, _ROLE_UTILITY, key)
            self.tree.addTopLevelItem(hdr)
            self._groups[key] = hdr
            self._poner_interruptor(hdr, key)
            for L in group:
                shared = [u for u in pdf_layers.layer_groups(L) if u != key]
                code = (L.get("letter_codes") or {}).get(key) if shared else L.get("letters")
                text = f"{L['short']}  ({L['path_count']})"
                if code:
                    text += f"  «{code}»"               # en su grupo por las letras de su línea
                if L.get("legend"):                     # mapa sin capas: lo que dice su leyenda
                    text += "  — " + ", ".join(L["legend"][:3]) + ("…" if len(L["legend"]) > 3 else "")
                it = QtWidgets.QTreeWidgetItem([text])
                tip = _layer_tooltip(L)
                if shared:
                    it.setIcon(0, _icon("mdi:link-variant", color=_theme.tokens().text_muted))
                    tip += "\n" + _tr("Es UNA sola capa del PDF: también está en {u}. Ocultarla oculta "
                                      "sus líneas de todas las utilidades; para ver solo las de una, "
                                      "márcala en la «Leyenda».").format(
                        u=", ".join(_tr(dict(pdf_layers.UTILITIES).get(u, u)) for u in shared))
                it.setToolTip(0, tip)
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable
                            | QtCore.Qt.ItemIsSelectable)
                it.setCheckState(0, QtCore.Qt.Checked if L["on"] else QtCore.Qt.Unchecked)
                it.setData(0, _ROLE_NAME, L["name"])
                it.setData(0, _ROLE_UTILITY, key)
                hdr.addChild(it)
                self._items_by_name.setdefault(L["name"], []).append(it)
            hdr.setExpanded(False)          # plegados: se ve la hoja por utilidades de un vistazo
        self._syncing = False
        del blocker
        if hasattr(self, "assignment_utility"):
            self._assignment_selection_changed(None)
        for key in self._groups:
            self._refresh_group(key)
        self._apply_filter()
        self._update_count()
        if hasattr(self, "_recog_checks"):
            self._sync_recog_all()

    def _poner_interruptor(self, hdr, key):
        """Interruptor «Reconocer» de la utilidad en su fila del árbol (= su casilla de «Reconocer»)."""
        cb = getattr(self, "_recog_checks", {}).get(key)
        if cb is None:
            return
        from ui.comun.rediseno import Interruptor
        sw = Interruptor(cb.isChecked(), _tr("Reconocer {u}").format(u=_tr(dict(pdf_layers.UTILITIES).get(key, key))))
        sw.setEnabled(cb.isEnabled())
        sw.toggled.connect(lambda on, c=cb: c.isChecked() != on and c.setChecked(on))
        caja = QtWidgets.QWidget()
        cl = QtWidgets.QHBoxLayout(caja)
        cl.setContentsMargins(0, 0, 6, 0)
        cl.addStretch(1)
        cl.addWidget(sw)
        self.tree.setItemWidget(hdr, 1, caja)
        self._interruptores_arbol[key] = sw

    def _focus_style(self, item, _column=0):
        if item is None or self._syncing:
            return
        name = item.data(0, _ROLE_NAME)
        if name:
            spec = {"layers": [name], "identificar": True}
            layer = next((L for L in self._layers if L["name"] == name), {})
            if layer.get("letter_paths"):
                spec["path_utility"] = item.data(0, _ROLE_UTILITY)
            self._focus_lines(spec)

    def _layer_items(self):
        """Filas de capa (sin grupos), en el orden del árbol."""
        for i in range(self.tree.topLevelItemCount()):
            grp = self.tree.topLevelItem(i)
            for j in range(grp.childCount()):
                yield grp.child(j)

    def group_item(self, key: str):
        return self._groups.get(key)

    def _refresh_group(self, key: str):
        """Casilla del grupo (todas / algunas / ninguna) y su conteo visibles/total."""
        grp = self._groups.get(key)
        if grp is None:
            return
        n = grp.childCount()
        on = sum(1 for j in range(n) if grp.child(j).checkState(0) == QtCore.Qt.Checked)
        label = dict(pdf_layers.UTILITIES).get(key, key)
        self._syncing = True
        grp.setCheckState(0, QtCore.Qt.Checked if on == n else
                          QtCore.Qt.Unchecked if on == 0 else QtCore.Qt.PartiallyChecked)
        grp.setText(0, f"{_tr(label)}   {on}/{n}" if 0 < on < n else f"{_tr(label)}   {n}")
        self._syncing = False

    # ── estado ──────────────────────────────────────────────────────────────
    def hidden_names(self) -> list[str]:
        """Nombres completos de las capas desmarcadas (en el orden del árbol; una
        capa compartida, una vez)."""
        return list(dict.fromkeys(it.data(0, _ROLE_NAME) for it in self._layer_items()
                                  if it.checkState(0) != QtCore.Qt.Checked))

    def page_index(self) -> int:
        """Hoja mostrada al cerrar (puede cambiar con ◀ ▶)."""
        return self._page_index

    # ── capas ───────────────────────────────────────────────────────────────
    def _update_count(self):
        total = len(self._items_by_name)
        visible = total - len(self.hidden_names())
        self.lbl_count.setText(_tr("Visibles: {v} de {t} capas").format(v=visible, t=total))

    def _sync_twins(self, items) -> set:
        """Las otras filas de una capa COMPARTIDA (está en dos grupos) toman el estado de
        la que cambió; devuelve los grupos que tocó."""
        touched = set()
        prev, self._syncing = self._syncing, True
        for it in items:
            for twin in self._items_by_name.get(it.data(0, _ROLE_NAME), ()):
                if twin is not it and twin.checkState(0) != it.checkState(0):
                    twin.setCheckState(0, it.checkState(0))
                    touched.add(twin.data(0, _ROLE_UTILITY))
        self._syncing = prev
        return touched

    def _on_item_changed(self, item, _col=0):
        if self._syncing:
            return
        key = item.data(0, _ROLE_UTILITY)
        if item.data(0, _ROLE_NAME) is None:           # casilla del grupo = toda la utilidad
            grp = self._groups[key]
            self._set_utility_visible(key, item.checkState(0) != QtCore.Qt.Unchecked)
            touched = self._sync_twins([grp.child(j) for j in range(grp.childCount())])
        else:
            self._util_memory.pop(key, None)            # el usuario eligió capa por capa
            touched = self._sync_twins([item])
        for k in {key} | touched:
            self._refresh_group(k)
        self._update_count()
        self._sync_recog_all()
        self._timer.start()

    def set_utility_visible(self, key: str, on: bool):
        """Enciende/apaga la utilidad `key` (lo mismo que su casilla de grupo)."""
        grp = self._groups.get(key)
        if grp is not None:
            grp.setCheckState(0, QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)

    def _set_utility_visible(self, key: str, on: bool):
        """Apaga (o repone) en la hoja todas las capas de la utilidad `key`.
        Al apagar se recuerda el estado de cada capa; al encender se repone
        (una capa que ya estaba oculta a mano sigue oculta)."""
        grp = self._groups.get(key)
        if grp is None:
            return
        items = [grp.child(j) for j in range(grp.childCount())]
        self._syncing = True
        if not on:
            self._util_memory[key] = {it.data(0, _ROLE_NAME): it.checkState(0) == QtCore.Qt.Checked
                                      for it in items}
            for it in items:
                it.setCheckState(0, QtCore.Qt.Unchecked)
        else:
            mem = self._util_memory.pop(key, {})
            if mem and not any(mem.values()):
                mem = {}                                 # estaba todo apagado: encender = todo
            for it in items:
                it.setCheckState(0, QtCore.Qt.Checked if mem.get(it.data(0, _ROLE_NAME), True)
                                 else QtCore.Qt.Unchecked)
        self._syncing = False

    def _set_all(self, on: bool):
        # Solo las filas visibles en el buscador (así «Ocultar todas» con un filtro
        # escrito actúa sobre lo que el usuario ve).
        self._syncing = True
        shown = [it for it in self._layer_items() if not it.isHidden()]
        for it in shown:
            it.setCheckState(0, QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)
        self._syncing = False
        self._sync_twins(shown)
        self._util_memory.clear()
        for key in self._groups:
            self._refresh_group(key)
        self._update_count()
        self._sync_recog_all()
        self._timer.start()

    def _apply_filter(self, _text=None):
        q = (self.search.text() or "").strip().upper()
        for key, grp in self._groups.items():
            shown = 0
            for j in range(grp.childCount()):
                it = grp.child(j)
                hide = bool(q) and q not in it.text(0).upper() and q not in str(it.data(0, _ROLE_NAME)).upper()
                it.setHidden(hide)
                shown += not hide
            grp.setHidden(shown == 0)
            if q:
                grp.setExpanded(shown > 0)               # con búsqueda, se ven los resultados

    # ── hojas ───────────────────────────────────────────────────────────────
    def _update_sheet_widgets(self):
        n, total = self._page_index + 1, self._doc.page_count
        self.setWindowTitle(_tr("Capas de la hoja {n}").format(n=n))
        self.lbl_sheet.setText(_tr("Hoja {n} / {total}").format(n=n, total=total))
        self.btn_prev.setEnabled(self._page_index > 0)
        self.btn_next.setEnabled(self._page_index < total - 1)
        for w in (self.btn_prev, self.btn_next, self.lbl_sheet):
            w.setVisible(total > 1)          # hoja compuesta = una sola página: sin navegador

    def _go_sheet(self, idx: int):
        if not (0 <= idx < self._doc.page_count) or idx == self._page_index:
            return
        self._timer.stop()
        with busy(self, _tr("Cargando hoja {n}…").format(n=idx + 1),
                  _tr("Leyendo sus capas")):
            self._load_sheet(idx)

    def _load_sheet(self, idx: int):
        # La visibilidad es del documento: lo marcado hasta ahora se conserva y
        # `page_layers` lo lee de ahí; solo cambian los conteos de trazos.
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        self._page_index = idx
        self._page = self._doc[idx]
        self._layers_raw = pdf_layers.page_layers(self._doc, idx)
        self._legend_for_new_sheet()          # mapa con leyenda: la de ESTA hoja decide sus estilos
        self._layers = self._effective_layers()
        # El buscador es solo de VISTA: no debe seguir puesto al cambiar de hoja,
        # o la nueva podía verse vacía aunque sí tuviera capas (usuario: «página
        # 3 parece no tener capas, pero sí tiene»). Lo OCULTO en el documento
        # (`hidden_names()`, ya aplicado arriba) sí se conserva entre hojas.
        self._util_memory.clear()
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self._fill_list()
        self._refresh_recog_checks()
        self._update_sheet_widgets()
        self._info_reload()
        self._render(first=True)

    # ── render ──────────────────────────────────────────────────────────────
    def _render_live(self):
        """Re-render tras marcar/desmarcar capas; si la hoja es lenta, con aviso
        sobre la vista (el panel queda a la vista, la hoja se atenúa)."""
        if self._slow_render and self.isVisible():
            with busy(self.view, _tr("Actualizando la vista…")):
                self._render()
        else:
            self._render()

    def _imagen(self, z: float, estado):
        """(QImage, escala, ancho, alto) de la hoja a `z` con las capas de `estado`: la que trajo
        la lectura previa, dibujada en el proceso (hoja compuesta) o aquí, como siempre."""
        previa, self._previa_img = getattr(self, "_previa_img", None), None
        if previa is not None and previa[0] == estado:
            return previa[1]
        if self._en_proceso:
            # todo el diálogo tapado mientras espera: sin otro clic a medias (la ventana sigue viva)
            self._dibujando = True
            try:
                with busy(self, _tr("Actualizando la vista…")):
                    r = fondo_trabajo.en_proceso(self._doc, self._page_index, z, grises=False)
            finally:
                self._dibujando = False
            if r is not None:
                return r[0], r[2], r[3], r[4]
        qimg, _g, escala, ancho, alto = fondo_trabajo.aqui(self._page, z, grises=False)
        return qimg, escala, ancho, alto

    def _render(self, first: bool = False):
        if getattr(self, "_dibujando", False):    # otro dibujo espera al proceso: después de él
            self._timer.start()
            return
        t0 = time.perf_counter()
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        estado = (self._page_index, pdf_layers.encendidas(self._doc))
        if not first and self._pix_item is not None and estado == self._render_estado:
            return              # las mismas capas encendidas: la misma imagen (mapa sin capas: siempre)
        z = _PREVIEW_ZOOM
        # la hoja entera a zoom 3; si es enorme, reducida con las MISMAS coordenadas
        qimg, escala, ancho, alto = self._imagen(z, estado)
        self._render_estado = estado
        pm = QtGui.QPixmap.fromImage(qimg)
        sc = self.view.scene()
        rect = (QtCore.QRectF(pm.rect()) if escala >= 1.0
                else QtCore.QRectF(0, 0, ancho, alto))
        if self._pix_item is None or fondo_pdf.escala_de(self._pix_item) != escala:
            self._nitidez.soltar()
            if self._pix_item is not None:
                sc.removeItem(self._pix_item)
            self._pix_item = fondo_pdf.nuevo_item(pm, escala)
            sc.addItem(self._pix_item)
            self.view.setSceneRect(rect)
            self._nitidez.fijar(self._pix_item)
        else:
            self._pix_item.setPixmap(pm)   # conserva zoom/pan del usuario
            self.view.setSceneRect(rect)
            self._nitidez.invalidar()      # capas cambiadas: el recorte nítido ya no sirve
        self.opacity.sync()
        if self._layout:
            # esquema de la organización (número y posición de cada hoja), sin dibujo
            # cada hoja con su código corto («17-10», «North 3»; el nombre completo al pasar el
            # ratón) y el esquema se acerca con la vista: en una tira de 36 hojas se lee la de enfrente
            labels = [label for _r, label in self._layout]
            self.minimap.set_layout(
                [(QtCore.QRectF(x0 * z, y0 * z, (x1 - x0) * z, (y1 - y0) * z), corta, label)
                 for ((x0, y0, x1, y1), label), corta in zip(self._layout, etiquetas_cortas(labels))],
                rect, sync_zoom=True)
        else:
            self.minimap.set_thumbnail(pm, rect)   # refleja las capas visibles
        if first:
            self._fit_view()
        self._slow_render = time.perf_counter() - t0 > _SLOW_RENDER_S

    # ── cierre ──────────────────────────────────────────────────────────────
    def _go_back(self):
        """Paso «1 Componer hoja» de la cabecera: deshace la visibilidad (como
        Cancelar) y avisa al llamador de que vuelva al compositor."""
        self.went_back = True
        self.reject()

    def accept(self):
        self._timer.stop()
        self._stop_legend()
        self._stop_calibration()
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        super().accept()

    def reject(self):
        self._timer.stop()
        self._stop_legend()
        self._stop_calibration()
        pdf_layers.set_hidden(self._doc, self._initial_hidden)   # deshacer cambios
        super().reject()

    # ── seguir vivo entre pasos del asistente (pedido del usuario 2026-10-28) ──
    def sirve_para(self, doc, page_index, recognition_utilities, letters_off, roles_by_utility,
                   scale_ft_per_pt, layout, en_proceso) -> bool:
        """¿Recibe lo mismo que dejó al continuar? (mismo documento abierto y hoja, las capas que
        dejó apagadas, mismas utilidades, letras, roles y escala)."""
        if doc is not self._doc or doc.is_closed or page_index != self._page_index:
            return False
        escala = self.scale_ft_per_pt() or getattr(self, "_escala_entrada", None)
        mismo_num = lambda a, b: (a is None and b is None) or (  # noqa: E731
            a is not None and b is not None and abs(float(a) - float(b)) <= 1e-12 * max(1.0, abs(float(a))))
        # al volver al compositor las capas del documento se repusieron; las del diálogo (lo que el
        # usuario dejó marcado) se vuelven a aplicar en `reabrir`
        return ((self.went_back or set(pdf_layers.hidden_layers(doc)) == set(self.hidden_names()))
                and tuple(recognition.normalize_utilities(recognition_utilities)) == tuple(self.recognition_utilities())
                and set(letters_off or ()) == set(self.letters_off())
                and (roles_by_utility or {}) == (self.roles_by_utility() or {})
                and mismo_num(scale_ft_per_pt, escala)
                and layout == self._layout and bool(en_proceso) == self._en_proceso)

    def reabrir(self):
        """Se vuelve a mostrar tal cual: Cancelar / volver deshacen desde AHORA, y la leyenda que
        quedó leyéndose al continuar se termina de poner."""
        volvio, self.went_back = self.went_back, False
        self._initial_hidden = pdf_layers.hidden_layers(self._doc)
        if volvio:
            pdf_layers.set_hidden(self._doc, self.hidden_names())   # lo marcado antes de volver
        self._reanudar_leyenda()

    def soltar_vivo(self):
        self._timer.stop()
        self._stop_legend()


def choose_sheet_layers(parent, doc, page_index: int, layout=None, recognition_utilities=None,
                        can_go_back: bool = False, letters_off=None, legend_sources=None,
                        legend_cache=None, roles_by_utility=None, include_roles=False,
                        scale_ft_per_pt=None, en_proceso=False, vivo=None):
    """Devuelve ``(capas_ocultas, indice_de_hoja, utilidades, letras_no)`` si el usuario
    continúa; con ``include_roles`` añade los roles por utilidad (quinto valor) y la escala
    calibrada en pies/pt (sexto; None si no se tocó: el botón «Escala» solo sale si se
    da `scale_ft_per_pt`, la escala actual).
    La hoja puede haber cambiado con ◀ ▶; la lista puede ser vacía.
    `LAYERS_BACK` si pulsa el paso «1 Componer hoja» de la cabecera (solo con
    `can_go_back`), o None si
    cancela (visibilidad restaurada en ambos casos). `layout`: disposición de las
    hojas de la página compuesta para el minimapa (ver composite.piece_layout).
    `letters_off`: capas que NO se toman por las letras de su línea (las devuelve
    actualizadas como `letras_no`); `legend_sources`: PDFs de origen
    ([{name, data|path}]) cuya leyenda se muestra; `legend_cache`: dict de la ventana
    principal donde queda la leyenda ya leída. `en_proceso` (hoja compuesta de varias piezas): lo
    pesado se lee y la hoja se dibuja en el proceso trabajador (`capas_previas`), mismos resultados.
    `vivo` (dict de la ventana, `ventana_pasos`): al continuar o volver al compositor el diálogo
    queda ahí, oculto; si se vuelve a pedir con lo mismo que dejó, se muestra TAL CUAL (sin leer
    las capas ni dibujar la hoja otra vez). Cancelar lo suelta."""
    dlg = vivo.pop("capas", None) if vivo is not None else None
    if dlg is not None and not dlg.sirve_para(doc, page_index, recognition_utilities, letters_off,
                                              roles_by_utility, scale_ft_per_pt, layout, en_proceso):
        dlg.soltar_vivo()
        dlg.deleteLater()
        dlg = None
    if dlg is not None:
        dlg.reabrir()
        return _resultado_capas(dlg, dlg.exec(), vivo, include_roles)
    with busy(parent, _tr("Leyendo las capas de la hoja…"),
              _tr("Contando los trazos de cada capa")) as ov:
        previa = None
        if en_proceso:
            previa = capas_previas.leer(doc, page_index, _PREVIEW_ZOOM, al_avanzar=lambda a: (
                ov.step(detail=detalle_de(a[1], a[2], a[3]), pump=False)
                if a and a[0] == "detalle" and ov.active else None))
        layers = previa.layers if previa is not None else pdf_layers.page_layers(doc, page_index)
        if not layers:
            # Hoja sin vectores (solo imagen: escaneo): no hay nada que elegir. Una hoja
            # vectorial sin capas OCG trae capas por estilo (`pdf_styles`).
            result = ([], page_index, recognition.normalize_utilities(recognition_utilities), sorted(letters_off or ()))
            return result + (roles_by_utility or {}, None) if include_roles else result
        dlg = SheetLayersDialog(parent, doc, page_index, layers=layers, layout=layout,
                                recognition_utilities=recognition_utilities, can_go_back=can_go_back,
                                letters_off=letters_off, legend_sources=legend_sources,
                                legend_cache=legend_cache, roles_by_utility=roles_by_utility,
                                scale_ft_per_pt=scale_ft_per_pt, previa=previa, en_proceso=en_proceso)
        dlg._escala_entrada = scale_ft_per_pt
    return _resultado_capas(dlg, dlg.exec(), vivo, include_roles)


def _resultado_capas(dlg, codigo, vivo, include_roles):
    if codigo != QtWidgets.QDialog.Accepted:
        if dlg.went_back and vivo is not None:
            vivo["capas"] = dlg            # vuelve al compositor: al regresar se muestra igual
        elif vivo is not None:
            dlg.soltar_vivo()
            dlg.deleteLater()
        return LAYERS_BACK if dlg.went_back else None
    if vivo is not None:
        vivo["capas"] = dlg
    result = (dlg.hidden_names(), dlg.page_index(), dlg.recognition_utilities(), dlg.letters_off())
    return result + (dlg.roles_by_utility(), dlg.scale_ft_per_pt()) if include_roles else result
