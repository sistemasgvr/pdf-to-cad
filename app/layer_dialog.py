"""layer_dialog.py — Paso «Capas de la hoja» del asistente de reconocimiento.

Se muestra DESPUÉS de elegir la hoja y ANTES de reconocer/dibujar la vista
previa. Izquierda: la hoja renderizada (zoom con rueda, pan con botón central).
Derecha: todas las capas OCG del PDF (como Okular), con conteo de trazos en
esa hoja y una casilla para mostrar/ocultar cada una. Cada cambio re-renderiza
la hoja en vivo.

Al aceptar, la visibilidad queda aplicada en el ``fitz.Document`` de la ventana
principal (``pdf_layers.set_hidden``): el lienzo se carga ya sin esas capas y el
reconocimiento las ignora. Al cancelar se restaura la visibilidad previa.

Toda la lógica de datos (listar capas, apagar/encender) vive en
``pdf_layers.py`` (puro, testeable). Aquí solo va la UI.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import fitz

from i18n import t as _tr
import pdf_layers
import theme as _theme
from widgets import ZoomPanView

# Zoom del render PDF (matriz PyMuPDF). El lienzo principal usa ~3.5; aquí
# 3.0 da nitidez al acercar con la rueda sin ralentizar demasiado el
# re-render al marcar/desmarcar capas (~0.3–0.5 s en hojas 36×24").
_PREVIEW_ZOOM = 3.0
# Espera tras el último clic en una casilla antes de re-renderizar (ms).
_RERENDER_DELAY_MS = 150


class SheetLayersDialog(QtWidgets.QDialog):
    """Mostrar/ocultar capas OCG de una hoja con vista previa en vivo."""

    def __init__(self, parent, doc: fitz.Document, page_index: int, layers=None):
        super().__init__(parent)
        self._doc = doc
        self._page_index = page_index
        self._page = doc[page_index]
        self._initial_hidden = pdf_layers.hidden_layers(doc)
        # `layers` permite reutilizar el listado ya calculado por quien nos llama.
        self._layers = layers if layers is not None else pdf_layers.page_layers(doc, page_index)
        self._pix_item = None

        self.setWindowTitle(_tr("Capas de la hoja {n}").format(n=page_index + 1))
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint)
        self.resize(1200, 760)

        root = QtWidgets.QHBoxLayout(self)
        self.view = ZoomPanView()
        root.addWidget(self.view, 1)

        panel = QtWidgets.QVBoxLayout()
        panel.setSpacing(8)
        root.addLayout(panel, 0)

        intro = QtWidgets.QLabel(_tr(
            "Marca las capas que quieres ver. Las capas ocultas no se dibujan "
            "en el lienzo ni se usan en el reconocimiento."))
        intro.setWordWrap(True)
        intro.setMinimumWidth(340)
        panel.addWidget(intro)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(_tr("Buscar capa…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        panel.addWidget(self.search)

        self.lst = QtWidgets.QListWidget()
        self.lst.setMinimumWidth(340)
        self.lst.setAlternatingRowColors(True)
        f = self.lst.font(); f.setPointSize(f.pointSize() + 1); self.lst.setFont(f)
        for L in self._layers:
            it = QtWidgets.QListWidgetItem(f"{L['short']}  ({L['path_count']})")
            it.setToolTip(L["name"])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if L["on"] else QtCore.Qt.Unchecked)
            it.setData(QtCore.Qt.UserRole, L["name"])
            self.lst.addItem(it)
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

        self._update_count()
        self._render(first=True)

    # ── estado ──────────────────────────────────────────────────────────────
    def hidden_names(self) -> list[str]:
        """Nombres completos de las capas desmarcadas (en el orden de la lista)."""
        out = []
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.checkState() != QtCore.Qt.Checked:
                out.append(it.data(QtCore.Qt.UserRole))
        return out

    def _update_count(self):
        total = self.lst.count()
        visible = total - len(self.hidden_names())
        self.lbl_count.setText(_tr("Visibles: {v} de {t} capas").format(v=visible, t=total))

    def _on_item_changed(self, _item):
        self._update_count()
        self._timer.start()

    def _set_all(self, on: bool):
        # Solo las filas visibles en el filtro (así "Ocultar todas" con un filtro
        # escrito actúa sobre lo que el usuario está viendo).
        self.lst.blockSignals(True)
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if not it.isHidden():
                it.setCheckState(QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)
        self.lst.blockSignals(False)
        self._update_count()
        self._timer.start()

    def _apply_filter(self, text: str):
        q = (text or "").strip().upper()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            it.setHidden(bool(q) and q not in it.text().upper()
                         and q not in str(it.data(QtCore.Qt.UserRole)).upper())

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
        if first:
            self.view.fitInView(self._pix_item, QtCore.Qt.KeepAspectRatio)

    # ── cierre ──────────────────────────────────────────────────────────────
    def accept(self):
        self._timer.stop()
        pdf_layers.set_hidden(self._doc, self.hidden_names())
        super().accept()

    def reject(self):
        self._timer.stop()
        pdf_layers.set_hidden(self._doc, self._initial_hidden)   # deshacer cambios
        super().reject()


def choose_sheet_layers(parent, doc, page_index: int) -> list[str] | None:
    """Abre el diálogo. Devuelve la lista de capas ocultas (puede ser vacía) si
    el usuario continúa, o None si cancela (visibilidad restaurada)."""
    layers = pdf_layers.page_layers(doc, page_index)
    if not layers:
        # Hoja sin capas OCG (PDF aplanado): no hay nada que elegir.
        return []
    dlg = SheetLayersDialog(parent, doc, page_index, layers=layers)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    return dlg.hidden_names()
