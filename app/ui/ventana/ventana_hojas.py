"""ventana_hojas.py — saber en qué hoja estás, en una hoja compuesta (pedido del usuario 2026-10-14).

Con 36 mapas importados al editor no había cómo ubicarse. Dos ayudas, cada una con su casilla en
Ver (se recuerdan en QSettings):

  · MINIMAPA de las hojas abajo a la izquierda del lienzo (el mismo `widgets.MiniMap` del
    compositor: código corto de cada hoja, la de enfrente resaltada, se acerca con la vista,
    clic = ir, doble clic = todas);
  · MARCAS DE AGUA: el borde de cada hoja a trazos y su código grande y tenue, ENCIMA del PDF y
    DEBAJO de todo lo demás. No cortan ni tapan nada, no se eligen con el ratón y no van al DXF
    (son ítems del lienzo, como las demás marcas de dibujo: `_redraw` las rehace).

El esquema sale de `_composite_layout` (pt de la hoja compuesta: px = pt × zoom), con la etiqueta
de la pieza si la trae (composición sugerida: «17-10»); en un proyecto reabierto se calcula de la
composición y los PDF de origen.
"""
from __future__ import annotations

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from nucleo.model import Z_PDF
from traduccion.i18n import bind as _bind, t as _tr
from ui.comun.widgets import MiniMap, etiquetas_cortas

Z_MARCA_HOJA = Z_PDF + 0.5        # encima del plano (y de su recorte nítido), debajo de lo dibujado
_AJUSTES = ("pdf-to-cad", "app")


def _pref(clave: str, defecto: bool = True) -> bool:
    try:
        return bool(QtCore.QSettings(*_AJUSTES).value(clave, defecto, type=bool))
    except Exception:
        return defecto


class HojasEditorMixin:
    # ── imagen de la hoja ─────────────────────────────────────────────────
    def _fondo_de(self, page):
        """(QImage, grises, escala, ancho, alto) de la hoja a `self.zoom`. Hoja compuesta de varias
        piezas: dibujada en el proceso trabajador (`fondo_trabajo`, mismos píxeles: la ventana no se
        traba ~10 s con 36 + 36 mapas); si no, o si eso falla, aquí como siempre."""
        from ui.comun import busy, fondo_trabajo
        if fondo_trabajo.conviene(getattr(self, "composite", None)):
            ov = busy.overlay_for(self)
            with busy.busy(self, ov.text() or _tr("Cargando hoja…"), _tr("Dibujando la hoja en pantalla…")):
                r = fondo_trabajo.en_proceso(page.parent, page.number, self.zoom, al_avanzar=lambda a: (
                    ov.step(detail=busy.detalle_de(a[1], a[2], a[3]), pump=False)
                    if a and a[0] == "detalle" and ov.active else None))
            if r is not None:
                return r
        return fondo_trabajo.aqui(page, self.zoom)

    # ── menú Ver ──────────────────────────────────────────────────────────
    def _acciones_hojas(self, menu):
        self.act_minimapa_hojas = _bind(QtGui.QAction(self), "setText", "Minimapa de las hojas")
        self.act_minimapa_hojas.setCheckable(True)
        self.act_minimapa_hojas.setChecked(_pref("minimapa_hojas"))
        _bind(self.act_minimapa_hojas, "setToolTip",
              "En una hoja compuesta, el esquema de sus hojas abajo a la izquierda: clic = ir a esa hoja.")
        self.act_marcas_hojas = _bind(QtGui.QAction(self), "setText", "Marcas de las hojas")
        self.act_marcas_hojas.setCheckable(True)
        self.act_marcas_hojas.setChecked(_pref("marcas_hojas"))
        _bind(self.act_marcas_hojas, "setToolTip",
              "En una hoja compuesta, el borde y el código de cada hoja, tenues, sobre el plano. "
              "No se exportan ni tapan nada.")
        for act, clave in ((self.act_minimapa_hojas, "minimapa_hojas"), (self.act_marcas_hojas, "marcas_hojas")):
            act.toggled.connect(lambda on, clave=clave: self._on_toggle_hojas(clave, on))
            menu.addAction(act)

    def _on_toggle_hojas(self, clave, on):
        try:
            QtCore.QSettings(*_AJUSTES).setValue(clave, bool(on))
        except Exception:
            pass
        self._redraw()

    # ── esquema de las hojas ──────────────────────────────────────────────
    def _layout_minimapa(self):
        """Esquema de hojas [(x0, y0, x1, y1) pt, etiqueta] para los minimapas (Capas de la hoja,
        vista previa, editor) y las marcas: el de `_composite_layout` con la etiqueta de la pieza
        si la trae. Solo para mostrar: `_composite_layout` sigue siendo el dato de xdata."""
        lay = getattr(self, "_composite_layout", None)
        comp = getattr(self, "composite", None)
        if not lay and comp is not None and len(comp.pieces) >= 2 and getattr(self, "src_pdfs", None):
            lay = self._calcular_layout(comp)
        if not lay or comp is None or len(comp.pieces) != len(lay):
            return lay
        # las hojas de una utilidad agregada (`grupo`) caen ENCIMA de las del editor: no se repiten.
        # Con solo algunos planos a la vista (ventana_planos), las del primero de ellos.
        vista = getattr(self, "_vista_fondo", None)
        g = min(vista) if vista else 0
        return [(rect, p.label or label) for (rect, label), p in zip(lay, comp.pieces) if int(p.grupo) == g]

    def _calcular_layout(self, comp):
        """Proyecto reabierto: el esquema con los tamaños de las hojas de origen."""
        from hoja import composite as composite_mod
        try:
            docs = [fitz.open(stream=e["data"], filetype="pdf") for e in self.src_pdfs]
            try:
                sizes = lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height)  # noqa: E731
                lay = composite_mod.piece_layout(comp, sizes, [e.get("name", "") for e in self.src_pdfs])
            finally:
                for d in docs:
                    d.close()
        except Exception:
            return None
        self._composite_layout = lay
        return lay

    def _hojas_px(self):
        """[(QRectF px del lienzo, etiqueta corta, etiqueta completa)] o [] si no es compuesta."""
        lay = self._layout_minimapa() if self.canvas.pixmap_item is not None else None
        if not lay or len(lay) < 2:
            return []
        z = self.zoom or 1.0
        labels = [label for _r, label in lay]
        return [(QtCore.QRectF(x0 * z, y0 * z, (x1 - x0) * z, (y1 - y0) * z), corta, label)
                for ((x0, y0, x1, y1), label), corta in zip(lay, etiquetas_cortas(labels))]

    # ── al redibujar ──────────────────────────────────────────────────────
    def _dibujar_hojas(self):
        """Minimapa, marcas de agua y el botón «Capas» (lo llama `_redraw` al final)."""
        self._sync_boton_capas()
        hojas = self._hojas_px()
        self._minimapa_editor(hojas)
        if hojas and getattr(self, "act_marcas_hojas", None) is not None and self.act_marcas_hojas.isChecked():
            self._overlay += marcas_de_agua(self.canvas.scene(), hojas)

    def _minimapa_editor(self, hojas):
        mm = getattr(self, "_mm_editor", None)
        ver = (hojas and getattr(self, "act_minimapa_hojas", None) is not None
               and self.act_minimapa_hojas.isChecked())
        if not ver:
            if mm is not None:
                mm.hide()
            self._mm_firma = None
            return
        if mm is None:
            mm = self._mm_editor = MiniMap(self.canvas, sync_zoom=True)
            # en el editor se trabaja sobre el lienzo: el minimapa, más chico que en el asistente
            mm.LAYOUT_W_FRAC, mm.LAYOUT_H_FRAC = 0.24, 0.2
            mm.LAYOUT_MAX_W, mm.LAYOUT_MAX_H = 340, 190
        firma = tuple((r.x(), r.y(), r.width(), r.height(), c) for r, c, _l in hojas)
        if firma != getattr(self, "_mm_firma", None) or not mm.isVisible():
            sr = self.canvas.sceneRect()
            mm.set_layout(hojas, sr, sync_zoom=True)
            self._mm_firma = firma


def marcas_de_agua(scene, hojas) -> list:
    """El borde a trazos y el código de cada hoja, tenues (ver el docstring del módulo)."""
    items = []
    pen = QtGui.QPen(QtGui.QColor(105, 110, 150, 110), 1.2, QtCore.Qt.DashLine)
    pen.setCosmetic(True)
    tinta = QtGui.QColor(105, 110, 150, 60)
    for rect, corta, _label in hojas:
        caja = scene.addRect(rect, pen, QtGui.QBrush(QtCore.Qt.NoBrush))
        texto = QtWidgets.QGraphicsSimpleTextItem(corta)
        f = texto.font()
        f.setPixelSize(max(12, int(min(rect.width(), rect.height()) * 0.09)))
        f.setBold(True)
        texto.setFont(f)
        texto.setBrush(QtGui.QBrush(tinta))
        texto.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        br = texto.boundingRect()
        texto.setPos(rect.center().x() - br.width() / 2.0, rect.center().y() - br.height() / 2.0)
        scene.addItem(texto)
        for it in (caja, texto):
            it.setZValue(Z_MARCA_HOJA)
            it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            it.setAcceptHoverEvents(False)
            items.append(it)
    return items
