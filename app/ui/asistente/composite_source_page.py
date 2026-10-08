"""composite_source_page.py — pestaña «Origen» del compositor (mezcla de `CompositeDialog`).

Antes era la columna izquierda, angosta, con miniaturas de 150 px en una lista
(pedido del usuario 2026-10-03: «me queda poco espacio para seleccionar y
visualizar las hojas»). Ahora es una pestaña a ventana completa: el PDF (se pueden
agregar más) y una GALERÍA de hojas con miniaturas grandes; cada hoja dice si está en
la hoja compuesta («✔ Hoja completa» / «✔ Área tomada») o si es una hoja «sin capas».
Clic (o flechas) = ELEGIRLA: mientras la hoja compuesta sea una sola hoja entera, la
elegida pasa a serlo (pedido del usuario 2026-10-05: elegía la hoja, pulsaba
«Siguiente» y la hoja compuesta quedaba vacía); Ctrl+clic = agregarla entera además
de las que ya están; doble clic o «Tomar área de esta hoja» = ir a «Área a tomar».

Las funciones de PDFs, hojas y miniaturas se movieron TAL CUAL desde
composite_dialog (mismos nombres: `lst_pages` sigue siendo la hoja actual).
Requiere de la clase: `self.docs`, `self.sources`, `self.comp`, `self._cur_source`,
`self._cur_page`, `self._thumb_cache`, `self._layers_cache`, `self._thumb_queue`,
`self._thumb_timer`, `_on_page_changed`, `_choose_page`, `_add_sheet`, `_simple`,
`_is_full`, `_go_tab` y `_refresh_pending`.
"""
from __future__ import annotations

import os

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from hoja import pdf_layers as PL
from ui.asistente.composite_view import _qpixmap
from traduccion.i18n import t as _tr
from ui.comun.icons import icon as _icon
from ui.comun.ui_common import DOWNLOADS
from ui.comun.busy import busy
from ui.comun import theme as _theme

THUMB_W = 220          # ancho de la miniatura en la galería (antes 150 en una lista angosta)


class PageGallery(QtWidgets.QListWidget):
    """Galería de hojas que distingue lo que hace el USUARIO de los cambios por
    código (sincronizar la hoja de una pieza, pruebas): `picked(fila)` al elegir
    una hoja con el ratón o el teclado; `added(fila)` con Ctrl+clic."""
    picked = QtCore.Signal(int)
    added = QtCore.Signal(int)
    picking = False         # un gesto del usuario está cambiando la hoja (antes de `picked`)

    def mousePressEvent(self, e):
        item = self.itemAt(e.position().toPoint()) if e.button() == QtCore.Qt.LeftButton else None
        if item is not None and e.modifiers() & QtCore.Qt.ControlModifier:
            self.setCurrentItem(item)           # se muestra (Área a tomar) y se agrega
            self.added.emit(self.row(item))
            e.accept()
            return
        self.picking = item is not None
        try:
            super().mousePressEvent(e)
        finally:
            self.picking = False
        if item is not None:
            self.picked.emit(self.row(item))

    def keyPressEvent(self, e):
        before = self.currentRow()
        self.picking = True
        try:
            super().keyPressEvent(e)
        finally:
            self.picking = False
        if self.currentRow() >= 0 and self.currentRow() != before:
            self.picked.emit(self.currentRow())


class SourcePageMixin:
    # ── UI ──────────────────────────────────────────────────────────────
    def _build_source_page(self, tool, btn_h: int) -> QtWidgets.QWidget:
        t = _theme.tokens()
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(10)
        self.lbl_source_hint = QtWidgets.QLabel()
        self.lbl_source_hint.setWordWrap(True)
        self.lbl_source_hint.setStyleSheet(f"color:{t.text_muted};")
        lay.addWidget(self.lbl_source_hint)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8)
        row.addWidget(QtWidgets.QLabel(_tr("PDF")))
        self.cmb_source = QtWidgets.QComboBox()
        self.cmb_source.setMinimumHeight(30)
        self.cmb_source.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.cmb_source.currentIndexChanged.connect(self._on_source_changed)
        row.addWidget(self.cmb_source, 1)
        btn_add = tool("mdi:file-plus-outline", _tr("Agregar PDF…"), _tr("Agregar otro PDF"))
        btn_add.clicked.connect(self._add_pdf)
        row.addWidget(btn_add)
        lay.addLayout(row)

        self.lst_pages = PageGallery()
        self.lst_pages.setViewMode(QtWidgets.QListView.IconMode)
        self.lst_pages.setIconSize(QtCore.QSize(THUMB_W, int(THUMB_W * 0.72)))
        self.lst_pages.setGridSize(QtCore.QSize(THUMB_W + 28, int(THUMB_W * 0.72) + 58))
        self.lst_pages.setResizeMode(QtWidgets.QListView.Adjust)
        self.lst_pages.setMovement(QtWidgets.QListView.Static)
        self.lst_pages.setWrapping(True)
        self.lst_pages.setWordWrap(True)
        self.lst_pages.setSpacing(8)
        self.lst_pages.setUniformItemSizes(True)
        self.lst_pages.currentRowChanged.connect(self._on_page_changed)
        self.lst_pages.picked.connect(self._choose_page)
        self.lst_pages.added.connect(self._add_sheet)
        self.lst_pages.itemDoubleClicked.connect(lambda _it: self._go_tab(1))
        lay.addWidget(self.lst_pages, 1)

        bottom = QtWidgets.QHBoxLayout(); bottom.setSpacing(10)
        self.lbl_source_sel = QtWidgets.QLabel()
        self.lbl_source_sel.setStyleSheet(f"color:{t.text};")
        bottom.addWidget(self.lbl_source_sel, 1)
        self.btn_go_area = QtWidgets.QPushButton(_icon("mdi:vector-rectangle", color=t.text_on_accent),
                                                 _tr("Tomar área de esta hoja"))
        self.btn_go_area.setMinimumHeight(btn_h)
        self.btn_go_area.setAutoDefault(False)
        self.btn_go_area.setToolTip(_tr("Ir a «Área a tomar» con la hoja elegida"))
        self.btn_go_area.clicked.connect(lambda: (self._choose_page(), self._go_tab(1)))
        bottom.addWidget(self.btn_go_area)
        lay.addLayout(bottom)
        return page

    def _refresh_source_selection(self):
        """Pie de la galería: qué hoja está elegida y si ya está en la hoja compuesta;
        arriba, qué hace un clic (depende de si la hoja compuesta es una sola hoja)."""
        if not hasattr(self, "lbl_source_sel"):
            return
        if self._simple():
            hint = _tr("Haz clic en la hoja del plano: esa hoja pasa a la hoja compuesta. Si solo "
                       "necesitas una parte, márcala en «Área a tomar» (doble clic). Ctrl+clic agrega "
                       "otra hoja.")
        else:
            hint = _tr("La hoja compuesta ya está armada: un clic solo muestra la hoja. Para "
                       "agregarla, toma su área en «Área a tomar» (doble clic) o usa Ctrl+clic para "
                       "agregarla entera.")
        self.lbl_source_hint.setText(hint)
        n = self._cur_page + 1
        taken = self._pieces_on_page(self._cur_source, self._cur_page)
        text = _tr("Elegida: hoja {n} de {total}").format(n=n, total=self.docs[self._cur_source].page_count)
        if taken:
            text += "  ·  " + _tr("✔ ya está en la hoja compuesta")
        self.lbl_source_sel.setText(text)

    # ── PDFs y hojas (movido tal cual de composite_dialog) ─────────────
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
            # alto para DOS líneas («Hoja 26» + «✔ Área tomada»): con tamaños uniformes
            # todas toman el de la primera hoja (una línea) y la marca quedaba «Hoja 26…»
            item.setSizeHint(QtCore.QSize(THUMB_W + 20, int(THUMB_W * 0.72) + 46))
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
        """Texto de una hoja de la lista: «sin capas» (hoja aplanada) y, en negrita,
        cómo está en la hoja compuesta («✔ Hoja completa», «✔ Área tomada»)."""
        mine = [p for p in self.comp.pieces if p.source == self._cur_source and p.page == page]
        taken = len(mine)
        flat = not self._uses_layers(self._cur_source, page)
        text = (_tr("Hoja {n} · sin capas") if flat else _tr("Hoja {n}")).format(n=page + 1)
        tips = []
        if taken:
            text += "\n" + (_tr("✔ {n} piezas").format(n=taken) if taken > 1 else
                            _tr("✔ Hoja completa") if self._is_full(mine[0]) else _tr("✔ Área tomada"))
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

    def _thumb_placeholder(self, page) -> QtGui.QIcon:
        """Recuadro del tamaño de la miniatura mientras se renderiza."""
        w = THUMB_W
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
            z = THUMB_W / max(pg.rect.width, 1.0)
            self._thumb_cache[key] = QtGui.QIcon(_qpixmap(pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)))
        return self._thumb_cache[key]

    def _invalidate_source_renders(self, source: int):
        for key in [k for k in self._thumb_cache if k[0] == source]:
            self._thumb_cache.pop(key, None)

    def _on_source_changed(self, idx: int):
        if idx < 0:
            return
        self._cur_source = idx
        self._cur_page = 0
        self._fill_pages()

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
