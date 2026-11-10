"""composite_mixto.py — compositor ÚNICO: piezas vectoriales y escaneadas en la misma hoja (2026-11-09).

Pedido del usuario: «componer entre vectorial y escaneo». Antes el modo era de TODA la hoja compuesta
(`Composite.manual`, elegido por el botón con que se abría el compositor). Ahora, en el compositor de PDF
vectoriales (`comp.manual` False), cada pieza decide por su hoja de origen (`hoja/pieza_escaneo.es_escaneo`):

  - pieza vectorial: lo de siempre (imán, match lines, puentes) y después Capas → reconocimiento;
  - pieza escaneada: regla, transportador, medir y enderezar en la barra (`ScanToolsMixin`, ocultos mientras
    no haya ninguna), gira sobre su centro, el imán no la mueve y el reconocimiento no ve nada en ella
    (es una imagen: se dibuja a mano en el editor);
  - TODAS escaneadas: al continuar se pregunta; «Dibujar a mano» devuelve la hoja con `manual=True` y sigue
    el camino del compositor de escaneos de siempre (al editor, sin Capas).

Sin ninguna pieza escaneada nada cambia: ni la barra (el grupo queda oculto), ni el imán, ni lo que se
devuelve. El compositor de escaneos (`manual=True`, al abrir un PDF imagen) tampoco cambia.
"""
from __future__ import annotations

from PySide6 import QtWidgets

from hoja import pieza_escaneo as PE
from traduccion.i18n import t as _tr


class MixtoMixin:
    """Requiere: `self.comp`, `self.docs`, `self.view`, `self.grupo_escaneo` (de `build_scan_tools`)."""

    def _es_escaneo_hoja(self, source: int, page: int) -> bool:
        cache = self.__dict__.setdefault("_escaneo_cache", {})
        key = (source, page)
        if key not in cache:
            try:
                cache[key] = PE.es_escaneo(self.docs[source][page])
            except Exception:                           # noqa: BLE001 — ante la duda, vectorial
                cache[key] = False
        return cache[key]

    def _es_escaneo_pieza(self, index: int) -> bool:
        if self.comp.manual or not 0 <= index < len(self.comp.pieces):
            return False
        p = self.comp.pieces[index]
        return self._es_escaneo_hoja(p.source, p.page)

    def _hay_escaneo(self) -> bool:
        return any(self._es_escaneo_pieza(i) for i in range(len(self.comp.pieces)))

    def _todo_escaneo(self) -> bool:
        return bool(self.comp.pieces) and all(self._es_escaneo_pieza(i) for i in range(len(self.comp.pieces)))

    def _guias_escaneo(self) -> bool:
        """¿Están a la vista regla, transportador, medir y enderezar?"""
        return self.comp.manual or self._hay_escaneo()

    def _sync_mixto(self):
        """Muestra u oculta las guías del escaneo según las piezas (solo en el compositor vectorial)."""
        if self.comp.manual or not hasattr(self, "grupo_escaneo"):
            return
        ver = self._hay_escaneo()
        for w in self.grupo_escaneo:
            if w.isHidden() == ver:
                w.setVisible(ver)
        if not ver:
            if self.view.measure.mode is not None:
                self._set_tool(None, False)
            for b in (self.btn_rule, self.btn_protractor):
                if b.isChecked():
                    b.setChecked(False)

    def _decidir_todo_escaneo(self) -> str:
        """Al continuar con TODAS las piezas escaneadas: 'mano' | 'reconocer' | 'back'. Sin ellas: 'reconocer'."""
        self._a_mano = False
        if self.comp.manual or not self._todo_escaneo():
            return "reconocer"
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(_tr("Hoja escaneada"))
        box.setText(_tr("Todas las piezas de la hoja compuesta son imágenes o escaneos."))
        box.setInformativeText(_tr("No tienen líneas que reconocer: lo normal es pasarla al editor y dibujar "
                                   "las utilidades a mano."))
        b_mano = box.addButton(_tr("Dibujar a mano"), QtWidgets.QMessageBox.AcceptRole)
        b_rec = box.addButton(_tr("Reconocer de todos modos"), QtWidgets.QMessageBox.DestructiveRole)
        b_back = box.addButton(_tr("Volver"), QtWidgets.QMessageBox.RejectRole)
        for b in (b_rec, b_back):
            b.setProperty("secondary", True)
            b.style().unpolish(b); b.style().polish(b)
        box.setDefaultButton(b_mano)
        box.setEscapeButton(b_back)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_mano:
            self._a_mano = True
            return "mano"
        if clicked is b_rec:
            return "reconocer"
        return "back"

    def _resultado_mixto(self, comp):
        """La hoja que se devuelve: con «Dibujar a mano», en modo escaneo (como el compositor de escaneos)."""
        if getattr(self, "_a_mano", False):
            comp.manual = True
            comp.bridges = False
        return comp
