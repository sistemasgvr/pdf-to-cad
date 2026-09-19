"""layer_dialog.py — Paso «Capas de la hoja» del asistente de reconocimiento.

Se muestra DESPUÉS de elegir la hoja y ANTES de reconocer/dibujar la vista
previa. Izquierda: la hoja renderizada (zoom con rueda, pan con botón central).
Derecha:
  · navegador «◀ Hoja N / M ▶» para cambiar de hoja sin salir del diálogo
    (las capas marcadas se conservan: la visibilidad es del documento);
  · panel «Utilidades» (Agua, Alcantarillado, Drenaje, Gas, Eléctrico,
    Telefonía, Otras — las mismas que el desplegable «Tipo de utilidad» de la
    app, cada una con su color): son FILTROS de la lista, no encienden ni
    apagan capas;
  · la lista de capas OCG agrupada por utilidad (cabecera de color por grupo),
    con conteo de trazos en esa hoja y casilla para mostrar/ocultar.
Cada cambio de casilla re-renderiza la hoja en vivo.

Al aceptar, la visibilidad queda aplicada en el ``fitz.Document`` de la ventana
principal (``pdf_layers.set_hidden``): el lienzo se carga ya sin esas capas y el
reconocimiento las ignora. Al cancelar se restaura la visibilidad previa.

Toda la lógica de datos (listar capas, apagar/encender, utilidad por nombre)
vive en ``pdf_layers.py`` (puro, testeable). Aquí solo va la UI.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import fitz

from i18n import t as _tr
import pdf_layers
import theme as _theme
from ui_common import aci_qcolor, layer_qcolor, swatch_icon
from widgets import ZoomPanView, MiniMap, maximize_on_show, side_panel_width

# Zoom del render PDF (matriz PyMuPDF). El lienzo principal usa ~3.5; aquí
# 3.0 da nitidez al acercar con la rueda sin ralentizar demasiado el
# re-render al marcar/desmarcar capas (~0.3–0.5 s en hojas 36×24").
_PREVIEW_ZOOM = 3.0
# Espera tras el último clic en una casilla antes de re-renderizar (ms).
_RERENDER_DELAY_MS = 150
# Ancho del panel derecho (utilidades + lista); la vista previa toma el resto.
_PANEL_WIDTH = 420
# Roles de datos de las filas de la lista.
_ROLE_NAME = QtCore.Qt.UserRole            # nombre completo de la capa (None en cabeceras)
_ROLE_UTILITY = QtCore.Qt.UserRole + 1     # clave de utilidad de la fila


def utility_qcolor(key: str) -> QtGui.QColor:
    """Color de una utilidad: el de su capa de salida (igual que en la app);
    «Otras» en gris."""
    if key == pdf_layers.UTILITY_OTHER:
        return aci_qcolor(8)
    return layer_qcolor(key)


class SheetLayersDialog(QtWidgets.QDialog):
    """Mostrar/ocultar capas OCG de una hoja con vista previa en vivo."""

    def __init__(self, parent, doc: fitz.Document, page_index: int, layers=None, layout=None):
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
        self._util_checks: dict[str, QtWidgets.QCheckBox] = {}

        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1240, 780)
        maximize_on_show(self)

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)   # margen uniforme alrededor de vista y panel
        self.view = ZoomPanView()
        # Minimapa (esquina inferior izquierda): esquema de la hoja mostrada con
        # el recuadro de lo visible; clic/arrastre centra la vista.
        self.minimap = MiniMap(self.view)

        # Vista | panel derecho, con divisor arrastrable: el panel arranca con un
        # ancho acorde a la ventana (nunca más del 32 %) y el usuario lo ajusta.
        self.split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(10)
        # tirador fino y transparente: solo separación (sigue siendo arrastrable)
        self.split.setStyleSheet("QSplitter::handle { background: transparent; border: none; }")
        self.split.addWidget(self.view)
        side = QtWidgets.QWidget()
        side.setMinimumWidth(300)
        panel = QtWidgets.QVBoxLayout(side)
        panel.setContentsMargins(10, 0, 0, 0)   # aire entre el divisor y los controles
        panel.setSpacing(8)
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

        intro = QtWidgets.QLabel(_tr(
            "Marca las capas que quieres ver. Las capas ocultas no se dibujan "
            "en el lienzo ni se usan en el reconocimiento."))
        intro.setWordWrap(True)
        panel.addWidget(intro)

        # ── filtro por utilidad (solo filtra la lista) ──
        grp = QtWidgets.QGroupBox(_tr("Utilidades"))
        gl = QtWidgets.QGridLayout(grp)
        gl.setHorizontalSpacing(14)
        gl.setVerticalSpacing(4)
        self.chk_all = QtWidgets.QCheckBox(_tr("Todas"))
        self.chk_all.setTristate(False)
        self.chk_all.setChecked(True)
        self.chk_all.toggled.connect(self._on_all_toggled)
        gl.addWidget(self.chk_all, 0, 0, 1, 2)
        for k, (key, label) in enumerate(pdf_layers.UTILITIES):
            cb = QtWidgets.QCheckBox(_tr(label))
            cb.setIcon(swatch_icon(utility_qcolor(key)))
            cb.setChecked(True)
            cb.toggled.connect(self._on_utility_toggled)
            self._util_checks[key] = cb
            gl.addWidget(cb, 1 + k // 2, k % 2)
        panel.addWidget(grp)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(_tr("Buscar capa…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        panel.addWidget(self.search)

        self.lst = QtWidgets.QListWidget()
        self.lst.setAlternatingRowColors(True)
        f = self.lst.font(); f.setPointSize(f.pointSize() + 1); self.lst.setFont(f)
        self.lst.itemChanged.connect(self._on_item_changed)
        panel.addWidget(self.lst, 1)

        row = QtWidgets.QHBoxLayout()
        self.btn_all = QtWidgets.QPushButton(_tr("Mostrar todas"))
        self.btn_none = QtWidgets.QPushButton(_tr("Ocultar todas"))
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        row.addWidget(self.btn_all); row.addWidget(self.btn_none)
        panel.addLayout(row)

        self.lbl_count = QtWidgets.QLabel()
        panel.addWidget(self.lbl_count)

        hint = QtWidgets.QLabel(_tr("Rueda = zoom · botón central = desplazar"))
        hint.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
        panel.addWidget(hint)

        bb = QtWidgets.QDialogButtonBox()
        self.btn_ok = bb.addButton(_tr("Continuar"), QtWidgets.QDialogButtonBox.AcceptRole)
        btn_cancel = bb.addButton(QtWidgets.QDialogButtonBox.Cancel)
        btn_cancel.setText(_tr("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        panel.addWidget(bb)
        self.btn_ok.setDefault(True)

        # Re-render diferido: varios clics seguidos → un solo render.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_RERENDER_DELAY_MS)
        self._timer.timeout.connect(self._render)

        self._fit_pending = True
        self._fill_list()
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

    # ── lista ───────────────────────────────────────────────────────────────
    def _fill_list(self):
        """Rellena la lista agrupada por utilidad (cabecera de color + capas)."""
        self.lst.blockSignals(True)
        self.lst.clear()
        by_util: dict[str, list[dict]] = {}
        for L in self._layers:
            by_util.setdefault(L["utility"], []).append(L)
        for key, label in pdf_layers.UTILITIES:
            group = by_util.get(key, [])
            cb = self._util_checks[key]
            cb.setText(f"{_tr(label)}  ({len(group)})")
            cb.setEnabled(bool(group))
            if not group:
                continue
            color = utility_qcolor(key)
            hdr = QtWidgets.QListWidgetItem(swatch_icon(color, 12), f"{_tr(label)} — {len(group)}")
            hdr.setFlags(QtCore.Qt.ItemIsEnabled)        # ni marcable ni seleccionable; icono a color
            hf = hdr.font(); hf.setBold(True); hdr.setFont(hf)
            hdr.setForeground(color)
            hdr.setData(_ROLE_NAME, None)
            hdr.setData(_ROLE_UTILITY, key)
            self.lst.addItem(hdr)
            for L in group:
                it = QtWidgets.QListWidgetItem(f"{L['short']}  ({L['path_count']})")
                it.setToolTip(L["name"])
                it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
                it.setCheckState(QtCore.Qt.Checked if L["on"] else QtCore.Qt.Unchecked)
                it.setData(_ROLE_NAME, L["name"])
                it.setData(_ROLE_UTILITY, key)
                self.lst.addItem(it)
        self.lst.blockSignals(False)
        self._apply_filter()
        self._update_count()

    def _layer_items(self):
        """Filas de capa (sin cabeceras)."""
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.data(_ROLE_NAME) is not None:
                yield it

    # ── estado ──────────────────────────────────────────────────────────────
    def hidden_names(self) -> list[str]:
        """Nombres completos de las capas desmarcadas (en el orden de la lista)."""
        return [it.data(_ROLE_NAME) for it in self._layer_items()
                if it.checkState() != QtCore.Qt.Checked]

    def page_index(self) -> int:
        """Hoja mostrada al cerrar (puede cambiar con ◀ ▶)."""
        return self._page_index

    def _update_count(self):
        total = sum(1 for _ in self._layer_items())
        visible = total - len(self.hidden_names())
        self.lbl_count.setText(_tr("Visibles: {v} de {t} capas").format(v=visible, t=total))

    def _on_item_changed(self, _item):
        self._update_count()
        self._timer.start()

    def _set_all(self, on: bool):
        # Solo las filas visibles en el filtro (así "Ocultar todas" con un filtro
        # escrito o una utilidad desmarcada actúa sobre lo que el usuario ve).
        self.lst.blockSignals(True)
        for it in self._layer_items():
            if not it.isHidden():
                it.setCheckState(QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)
        self.lst.blockSignals(False)
        self._update_count()
        self._timer.start()

    # ── filtro (utilidades + búsqueda) ──────────────────────────────────────
    def _on_all_toggled(self, on: bool):
        for cb in self._util_checks.values():
            cb.blockSignals(True); cb.setChecked(on); cb.blockSignals(False)
        self._apply_filter()

    def _on_utility_toggled(self, _on: bool):
        # «Todas» refleja el estado conjunto sin disparar su propio handler.
        enabled = [cb for cb in self._util_checks.values() if cb.isEnabled()]
        self.chk_all.blockSignals(True)
        self.chk_all.setChecked(all(cb.isChecked() for cb in enabled))
        self.chk_all.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self, _text=None):
        q = (self.search.text() or "").strip().upper()
        shown_utils = {k for k, cb in self._util_checks.items() if cb.isChecked()}
        visible_by_util: dict[str, int] = {}
        for it in self._layer_items():
            key = it.data(_ROLE_UTILITY)
            hide = key not in shown_utils or (
                bool(q) and q not in it.text().upper()
                and q not in str(it.data(_ROLE_NAME)).upper())
            it.setHidden(hide)
            if not hide:
                visible_by_util[key] = visible_by_util.get(key, 0) + 1
        # Cabeceras: solo si su grupo tiene alguna fila visible.
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.data(_ROLE_NAME) is None:
                it.setHidden(visible_by_util.get(it.data(_ROLE_UTILITY), 0) == 0)

    # ── hojas ───────────────────────────────────────────────────────────────
    def _update_sheet_widgets(self):
        n, total = self._page_index + 1, self._doc.page_count
        self.setWindowTitle(_tr("Capas de la hoja {n}").format(n=n))
        self.lbl_sheet.setText(_tr("Hoja {n} / {total}").format(n=n, total=total))
        self.btn_prev.setEnabled(self._page_index > 0)
        self.btn_next.setEnabled(self._page_index < total - 1)

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
        self._fill_list()
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
    def accept(self):
        self._timer.stop()
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        super().accept()

    def reject(self):
        self._timer.stop()
        pdf_layers.set_hidden(self._doc, self._initial_hidden)   # deshacer cambios
        super().reject()


def choose_sheet_layers(parent, doc, page_index: int, layout=None) -> tuple[list[str], int] | None:
    """Abre el diálogo. Devuelve ``(capas_ocultas, indice_de_hoja)`` si el
    usuario continúa (la hoja puede haber cambiado con ◀ ▶; la lista puede ser
    vacía), o None si cancela (visibilidad restaurada). `layout`: disposición
    de las hojas de la página compuesta para el minimapa (ver composite.piece_layout)."""
    layers = pdf_layers.page_layers(doc, page_index)
    if not layers:
        # Hoja sin capas OCG (PDF aplanado): no hay nada que elegir.
        return [], page_index
    dlg = SheetLayersDialog(parent, doc, page_index, layers=layers, layout=layout)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return dlg.hidden_names(), dlg.page_index()
