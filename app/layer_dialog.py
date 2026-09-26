"""layer_dialog.py — Paso «Capas de la hoja» del asistente de reconocimiento.

Se muestra DESPUÉS de componer la hoja y ANTES de reconocer/dibujar la vista
previa. Izquierda: la hoja renderizada (zoom con rueda, pan con botón central,
minimapa). Derecha, de arriba abajo:
  · (cabecera a todo el ancho) barra de pasos «1 Componer hoja › 2 Capas de la
    hoja › 3 Vista previa»: el paso 1 es clicable y vuelve al compositor;
  · «◀ Hoja N / M ▶» para
    cambiar de hoja sin salir (las capas marcadas se conservan: la visibilidad
    es del documento);
  · tarjeta «Reconocer»: qué utilidades se reconocen — «Todas» + una casilla
    por utilidad con su color (sin ninguna marcada no se puede continuar);
  · tarjeta «Capas del plano»: árbol por utilidad (Agua, Alcantarillado,
    Drenaje, Gas, Eléctrico, Telecom, Otras — las del desplegable «Tipo de
    utilidad» de la app). La casilla del GRUPO enciende/apaga todas las capas
    de esa utilidad en la hoja (al volver a encenderla cada capa recupera el
    estado que tenía); desplegándolo se marca capa por capa. Buscador y
    «Mostrar / Ocultar todas» sobre lo filtrado.
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

from PySide6 import QtCore, QtGui, QtWidgets

import fitz

from i18n import t as _tr
from icons import icon as _icon
import pdf_layers
import recognition
import theme as _theme
from ui_common import aci_qcolor, layer_qcolor, swatch_icon
from widgets import ZoomPanView, MiniMap, maximize_on_show, side_panel_width, GripSplitter
from wizard_widgets import StepBar, OpacityButton, wizard_header, wizard_footer

# Zoom del render PDF (matriz PyMuPDF). El lienzo principal usa ~3.5; aquí
# 3.0 da nitidez al acercar con la rueda sin ralentizar demasiado el
# re-render al marcar/desmarcar capas (~0.3–0.5 s en hojas 36×24").
_PREVIEW_ZOOM = 3.0
# Espera tras el último clic en una casilla antes de re-renderizar (ms).
_RERENDER_DELAY_MS = 150
# Ancho del panel derecho; la vista previa toma el resto.
_PANEL_WIDTH = 440
# Roles de datos de las filas del árbol.
_ROLE_NAME = QtCore.Qt.UserRole            # nombre completo de la capa (None en grupos)
_ROLE_UTILITY = QtCore.Qt.UserRole + 1     # clave de utilidad de la fila

# `choose_sheet_layers` devuelve esto si el usuario pulsa «◀ Componer hoja».
LAYERS_BACK = "back"

# Etiqueta corta de cada utilidad reconocible (recognition.SUPPORTED_UTILITIES)
# para sus casillas de «Reconocer».
_UTILITY_RECOG_LABEL = dict(recognition.UTILITY_LABELS)


def utility_qcolor(key: str) -> QtGui.QColor:
    """Color de una utilidad: el de su capa de salida (igual que en la app);
    «Otras» en gris."""
    if key == pdf_layers.UTILITY_OTHER:
        return aci_qcolor(8)
    return layer_qcolor(key)


def _card(title: str) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout, QtWidgets.QHBoxLayout]:
    """Tarjeta con título (y un hueco a la derecha del título para acciones)."""
    t = _theme.tokens()
    box = QtWidgets.QFrame()
    box.setObjectName("layerCard")
    box.setStyleSheet(f"QFrame#layerCard {{ background:{t.surface}; border:1px solid {t.border};"
                      " border-radius:8px; }")
    lay = QtWidgets.QVBoxLayout(box)
    lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(8)
    head = QtWidgets.QHBoxLayout(); head.setSpacing(8)
    lbl = QtWidgets.QLabel(title)
    f = lbl.font(); f.setBold(True); f.setPointSize(f.pointSize() + 1); lbl.setFont(f)
    head.addWidget(lbl, 1)
    lay.addLayout(head)
    return box, lay, head


class SheetLayersDialog(QtWidgets.QDialog):
    """Mostrar/ocultar capas OCG de una hoja con vista previa en vivo."""

    def __init__(self, parent, doc: fitz.Document, page_index: int, layers=None, layout=None,
                 recognition_utilities=None, can_go_back: bool = False):
        super().__init__(parent)
        self._doc = doc
        self._page_index = page_index
        # Disposición de las hojas que forman esta página (hoja compuesta):
        # [((x0, y0, x1, y1) en pt, etiqueta), …]. Alimenta el minimapa esquemático.
        self._layout = layout
        self._page = doc[page_index]
        self._initial_hidden = pdf_layers.hidden_layers(doc)
        # `layers` permite reutilizar el listado ya calculado por quien nos llama.
        self._layers = layers if layers is not None else pdf_layers.page_layers(doc, page_index)
        self._pix_item = None
        self._groups: dict[str, QtWidgets.QTreeWidgetItem] = {}
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
        # Minimapa (esquina inferior izquierda): esquema de la hoja mostrada con
        # el recuadro de lo visible; clic/arrastre centra la vista.
        self.minimap = MiniMap(self.view)

        # Vista | panel derecho, con divisor arrastrable: el panel arranca con un
        # ancho acorde a la ventana (nunca más del 32 %) y el usuario lo ajusta.
        self.split = GripSplitter(QtCore.Qt.Horizontal)   # tirador visible y arrastrable
        self.split.addWidget(self.view)
        side = QtWidgets.QWidget()
        side.setMinimumWidth(320)
        panel = QtWidgets.QVBoxLayout(side)
        panel.setContentsMargins(10, 0, 0, 0)   # aire entre el divisor y los controles
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
        nav.addWidget(self.btn_prev); nav.addWidget(self.lbl_sheet, 1); nav.addWidget(self.btn_next)
        panel.addLayout(nav)

        # ── tarjeta «Reconocer»: qué utilidades se leen del plano ──
        card, lay, head = _card(_tr("Reconocer"))
        self.chk_recog_all = QtWidgets.QCheckBox(_tr("Todas"))
        self.chk_recog_all.setToolTip(_tr("Marcar o desmarcar todas las utilidades que tiene la hoja"))
        self.chk_recog_all.clicked.connect(self._on_recog_all_clicked)
        head.addWidget(self.chk_recog_all)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10); grid.setVerticalSpacing(6)
        self._recog_checks: dict[str, QtWidgets.QCheckBox] = {}
        selected = recognition.normalize_utilities(recognition_utilities)
        for n, key in enumerate(recognition.SUPPORTED_UTILITIES):
            cb = QtWidgets.QCheckBox(_tr(_UTILITY_RECOG_LABEL.get(key, key)))
            cb.setIcon(swatch_icon(utility_qcolor(key)))
            cb.setChecked(key in selected)
            cb.toggled.connect(self._on_recog_utility_toggled)
            self._recog_checks[key] = cb
            # 2 columnas: con 3 los nombres se cortaban en un panel estrecho
            grid.addWidget(cb, n // 2, n % 2)
        for c in range(2):
            grid.setColumnStretch(c, 1)
        lay.addLayout(grid)
        self.lbl_recog_warn = QtWidgets.QLabel(_tr("Marca al menos una utilidad para reconocer."))
        self.lbl_recog_warn.setStyleSheet(f"color:{t.danger}; font-weight:bold;")
        self.lbl_recog_warn.hide()
        lay.addWidget(self.lbl_recog_warn)
        panel.addWidget(card)

        # ── tarjeta «Capas del plano»: árbol por utilidad ──
        card, lay, head = _card(_tr("Capas del plano"))
        self.btn_all = QtWidgets.QToolButton()
        self.btn_all.setIcon(_icon("mdi:eye-outline")); self.btn_all.setToolTip(_tr("Mostrar todas"))
        self.btn_none = QtWidgets.QToolButton()
        self.btn_none.setIcon(_icon("mdi:eye-off-outline")); self.btn_none.setToolTip(_tr("Ocultar todas"))
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        head.addWidget(self.btn_all); head.addWidget(self.btn_none)
        hint = QtWidgets.QLabel(_tr("Casilla = toda la utilidad · ▸ = capa por capa"))
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
        self.tree.setColumnCount(1)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        f = self.tree.font(); f.setPointSize(f.pointSize() + 1); self.tree.setFont(f)
        self.tree.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.tree, 1)
        self.lbl_count = QtWidgets.QLabel()
        self.lbl_count.setStyleSheet(f"color:{t.text_muted};")
        lay.addWidget(self.lbl_count)
        panel.addWidget(card, 1)

        # ── pie a todo el ancho: opacidad · ayuda · Cancelar | Continuar ──
        # (volver a «Componer hoja» es el paso 1 de la cabecera: un solo sitio)
        self.opacity = OpacityButton(lambda: self._pix_item)
        btn_cancel = QtWidgets.QPushButton(_tr("Cancelar"))
        btn_cancel.setProperty("secondary", True)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QtWidgets.QPushButton(_tr("Continuar"))
        self.btn_ok.clicked.connect(self.accept)
        self.btn_ok.setDefault(True)
        root.addWidget(wizard_footer([self.opacity], _tr("Rueda = zoom · botón central = desplazar"),
                                     [btn_cancel, self.btn_ok]))

        # Re-render diferido: varios clics seguidos → un solo render.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_RERENDER_DELAY_MS)
        self._timer.timeout.connect(self._render)

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
            QtCore.QTimer.singleShot(0, self._fit_view)
            QtCore.QTimer.singleShot(0, self._apply_side_width)

    def _apply_side_width(self):
        w = self.width()
        side_w = side_panel_width(w, _PANEL_WIDTH)
        self.split.setSizes([max(200, w - side_w), side_w])

    def _fit_view(self):
        if self._pix_item is not None:
            self.view.resetTransform()
            self.view.fitInView(self._pix_item, QtCore.Qt.KeepAspectRatio)

    # ── árbol ───────────────────────────────────────────────────────────────
    def _fill_list(self):
        """Rellena el árbol: un grupo por utilidad (con su color) y sus capas."""
        self._syncing = True
        self.tree.clear()
        self._groups.clear()
        by_util: dict[str, list[dict]] = {}
        for L in self._layers:
            by_util.setdefault(L["utility"], []).append(L)
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
            for L in group:
                it = QtWidgets.QTreeWidgetItem([f"{L['short']}  ({L['path_count']})"])
                it.setToolTip(0, L["name"])
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
                it.setCheckState(0, QtCore.Qt.Checked if L["on"] else QtCore.Qt.Unchecked)
                it.setData(0, _ROLE_NAME, L["name"])
                it.setData(0, _ROLE_UTILITY, key)
                hdr.addChild(it)
            hdr.setExpanded(False)          # plegados: se ve la hoja por utilidades de un vistazo
        self._syncing = False
        for key in self._groups:
            self._refresh_group(key)
        self._apply_filter()
        self._update_count()

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
        """Nombres completos de las capas desmarcadas (en el orden del árbol)."""
        return [it.data(0, _ROLE_NAME) for it in self._layer_items()
                if it.checkState(0) != QtCore.Qt.Checked]

    def page_index(self) -> int:
        """Hoja mostrada al cerrar (puede cambiar con ◀ ▶)."""
        return self._page_index

    def recognition_utilities(self) -> tuple[str, ...]:
        chosen = tuple(key for key in recognition.SUPPORTED_UTILITIES
                       if self._recog_checks[key].isChecked())
        return recognition.normalize_utilities(chosen)

    # ── «Reconocer» ─────────────────────────────────────────────────────────
    def _refresh_recog_checks(self):
        """Solo se marcan las utilidades que la hoja tiene; «Todas» refleja el
        conjunto; sin ninguna marcada no se puede continuar."""
        available = {layer.get("utility") for layer in self._layers
                     if int(layer.get("path_count") or 0) > 0}
        for key, cb in self._recog_checks.items():
            has = key in available
            cb.setEnabled(has)
            cb.setToolTip("" if has else _tr("Esta hoja no tiene capas de {u}").format(
                u=_tr(_UTILITY_RECOG_LABEL.get(key, key))))
        self._sync_recog_all()

    def _enabled_recog(self):
        return [cb for cb in self._recog_checks.values() if cb.isEnabled()]

    def _sync_recog_all(self):
        enabled = self._enabled_recog()
        n_on = sum(1 for cb in enabled if cb.isChecked())
        self.chk_recog_all.blockSignals(True)
        self.chk_recog_all.setTristate(0 < n_on < len(enabled))
        self.chk_recog_all.setCheckState(
            QtCore.Qt.Checked if enabled and n_on == len(enabled) else
            QtCore.Qt.PartiallyChecked if n_on else QtCore.Qt.Unchecked)
        self.chk_recog_all.setEnabled(bool(enabled))
        self.chk_recog_all.blockSignals(False)
        ok = n_on > 0 or not enabled          # hoja sin utilidades: se puede seguir (avisa el preview)
        self.lbl_recog_warn.setVisible(not ok)
        self.btn_ok.setEnabled(ok)

    def _on_recog_all_clicked(self, _checked=False):
        enabled = self._enabled_recog()
        target = not all(cb.isChecked() for cb in enabled)
        for cb in enabled:
            cb.blockSignals(True); cb.setChecked(target); cb.blockSignals(False)
        self._sync_recog_all()

    def _on_recog_utility_toggled(self, _on: bool):
        self._sync_recog_all()

    # ── capas ───────────────────────────────────────────────────────────────
    def _update_count(self):
        total = sum(1 for _ in self._layer_items())
        visible = total - len(self.hidden_names())
        self.lbl_count.setText(_tr("Visibles: {v} de {t} capas").format(v=visible, t=total))

    def _on_item_changed(self, item, _col=0):
        if self._syncing:
            return
        key = item.data(0, _ROLE_UTILITY)
        if item.data(0, _ROLE_NAME) is None:           # casilla del grupo = toda la utilidad
            self._set_utility_visible(key, item.checkState(0) != QtCore.Qt.Unchecked)
        else:
            self._util_memory.pop(key, None)            # el usuario eligió capa por capa
        self._refresh_group(key)
        self._update_count()
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
        for it in self._layer_items():
            if not it.isHidden():
                it.setCheckState(0, QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)
        self._syncing = False
        self._util_memory.clear()
        for key in self._groups:
            self._refresh_group(key)
        self._update_count()
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
        # La visibilidad es del documento: lo marcado hasta ahora se conserva y
        # `page_layers` lo lee de ahí; solo cambian los conteos de trazos.
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        self._page_index = idx
        self._page = self._doc[idx]
        self._layers = pdf_layers.page_layers(self._doc, idx)
        # El buscador es solo de VISTA: no debe seguir puesto al cambiar de hoja,
        # o la nueva podía verse vacía aunque sí tuviera capas (usuario: «página
        # 3 parece no tener capas, pero sí tiene»). Lo OCULTO en el documento
        # (`hidden_names()`, ya aplicado arriba) sí se conserva entre hojas.
        self._util_memory.clear()
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self._fill_list()
        self._refresh_recog_checks()
        self._update_sheet_widgets()
        self._render(first=True)

    # ── render ──────────────────────────────────────────────────────────────
    def _render(self, first: bool = False):
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        z = _PREVIEW_ZOOM
        pix = self._page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        qimg = QtGui.QImage(bytes(pix.samples), pix.width, pix.height,
                            pix.stride, QtGui.QImage.Format_RGB888).copy()
        pm = QtGui.QPixmap.fromImage(qimg)
        sc = self.view.scene()
        if self._pix_item is None:
            self._pix_item = sc.addPixmap(pm)
            self.view.setSceneRect(QtCore.QRectF(pm.rect()))
        else:
            self._pix_item.setPixmap(pm)   # conserva zoom/pan del usuario
            self.view.setSceneRect(QtCore.QRectF(pm.rect()))
        self.opacity.sync()
        if self._layout:
            # esquema de la organización (número y posición de cada hoja), sin dibujo
            self.minimap.set_layout(
                [(QtCore.QRectF(x0 * z, y0 * z, (x1 - x0) * z, (y1 - y0) * z), label)
                 for (x0, y0, x1, y1), label in self._layout], QtCore.QRectF(pm.rect()))
        else:
            self.minimap.set_thumbnail(pm, QtCore.QRectF(pm.rect()))   # refleja las capas visibles
        if first:
            self._fit_view()

    # ── cierre ──────────────────────────────────────────────────────────────
    def _go_back(self):
        """Paso «1 Componer hoja» de la cabecera: deshace la visibilidad (como
        Cancelar) y avisa al llamador de que vuelva al compositor."""
        self.went_back = True
        self.reject()

    def accept(self):
        self._timer.stop()
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        super().accept()

    def reject(self):
        self._timer.stop()
        pdf_layers.set_hidden(self._doc, self._initial_hidden)   # deshacer cambios
        super().reject()


def choose_sheet_layers(parent, doc, page_index: int, layout=None, recognition_utilities=None,
                        can_go_back: bool = False):
    """Devuelve ``(capas_ocultas, indice_de_hoja, utilidades)`` si el usuario
    continúa (la hoja puede haber cambiado con ◀ ▶; la lista puede ser vacía),
    `LAYERS_BACK` si pulsa el paso «1 Componer hoja» de la cabecera (solo con
    `can_go_back`), o None si
    cancela (visibilidad restaurada en ambos casos). `layout`: disposición de las
    hojas de la página compuesta para el minimapa (ver composite.piece_layout)."""
    layers = pdf_layers.page_layers(doc, page_index)
    if not layers:
        # Hoja sin capas OCG (PDF aplanado): no hay nada que elegir.
        return [], page_index, recognition.normalize_utilities(recognition_utilities)
    dlg = SheetLayersDialog(parent, doc, page_index, layers=layers, layout=layout,
                            recognition_utilities=recognition_utilities, can_go_back=can_go_back)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return LAYERS_BACK if dlg.went_back else None
    return dlg.hidden_names(), dlg.page_index(), dlg.recognition_utilities()
