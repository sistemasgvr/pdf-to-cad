"""ventana_georef_auto.py — georreferencia AUTOMÁTICA al componer una hoja (2026-11-18).

Las piezas que dicen dónde están (hoy: el cuarto de sección de los mapas de Phoenix, confirmado por la sección PLSS
del cajetín; ver `geo/auto/`) dan la georreferencia sin clics. Se calcula en el trabajador «georef» (leer cada
hoja cuesta) y, al volver, solo se aplica si la hoja sigue siendo la misma y el proyecto todavía no tiene
georreferencia: la hecha a mano manda siempre. Con error alto queda DUDOSA: se avisa y no se aplica sola.
"""
from __future__ import annotations

import json
import os

from geo import georef as georef_mod
from traduccion.i18n import t

TRABAJADOR = "georef"


class GeorefAutoMixin:
    _georef_auto_tarea = None
    _georef_auto_dudosa = None      # el último resultado dudoso (dict), para «Aplicar igual»
    _georef_auto_ultimo = None      # el último resultado calculado (dict o None), para las pruebas
    _georef_auto_error = ""

    def _georef_auto_firma(self):
        comp = getattr(self, "composite", None)
        return json.dumps(comp.to_dict() if comp is not None else None, sort_keys=True, default=str), \
            len(getattr(self, "src_pdfs", None) or [])

    def _georef_automatica(self):
        """Lanza el cálculo tras componer. Nada si ya hay georreferencia o no hay PDF de origen."""
        if os.environ.get("PDFCAD_GEOREF_AUTO", "1") == "0":
            return
        if self.georef.active() or not getattr(self, "src_pdfs", None):
            return
        from ui.comun import proceso
        if self._georef_auto_tarea is not None:
            self._georef_auto_tarea.cancelar()
        self._georef_auto_dudosa = None
        firma = self._georef_auto_firma()
        comp = getattr(self, "composite", None)
        tarea = proceso.Tarea("geo.auto.ajuste:trabajo",
                              (comp.to_dict() if comp is not None else None,
                               [e["data"] for e in self.src_pdfs], float(self.zoom)))
        tarea.terminado.connect(lambda res, err, f=firma, tk=tarea: self._georef_auto_listo(res, err, f, tk))
        self._georef_auto_tarea = tarea
        proceso.trabajador(TRABAJADOR).enviar(tarea)

    def _georef_auto_listo(self, res, err, firma, tarea):
        if tarea is not self._georef_auto_tarea:
            return                                   # una tarea vieja (se compuso otra hoja)
        self._georef_auto_tarea = None
        self._georef_auto_ultimo = res
        self._georef_auto_error = err or ""
        if err or not res:
            return                                   # ninguna pieza dice dónde está: nada cambia
        if self.georef.active() or firma != self._georef_auto_firma():
            return                                   # el usuario georreferenció o cambió la hoja mientras tanto
        celdas = self._georef_auto_celdas(res)
        if res.get("aceptada"):
            self.aplicar_georef_auto(res)
            self.aviso_breve(t("Georreferenciada sola por cuarto de sección"),
                             t("{celdas} · error {e} ft").format(celdas=celdas, e="%.1f" % res["rms_ft"]),
                             (t("Deshacer"), self.undo))
            return
        self._georef_auto_dudosa = res
        self.aviso_breve(t("No se georreferenció sola"),
                         t("Las hojas no coinciden con sus cuadros ({celdas}): error {e} ft. Revisa la composición.")
                         .format(celdas=celdas, e="%.0f" % res["rms_ft"]),
                         (t("Aplicar igual"), lambda r=res: self.aplicar_georef_auto(r)), "aviso")

    @staticmethod
    def _georef_auto_celdas(res) -> str:
        et = sorted(set(res.get("etiquetas") or []))
        if len(et) <= 3:
            return ", ".join(et)
        return "%s … %s (%d)" % (et[0], et[-1], len(et))

    def aplicar_georef_auto(self, res):
        """La georreferencia del resultado, con un paso de deshacer (Ctrl+Z la quita)."""
        self._push()
        self.georef = georef_mod.Georef(res["matrix"], res["epsg"], "similarity", res["rms_ft"],
                                        res["puntos"], res.get("cs_code") or "")
        self._georef_auto_dudosa = None
        self._update_geo_status()
        self._redraw()

    def _georef_auto_esperar(self, ms: int = 300_000) -> bool:
        """Espera el cálculo en curso (pruebas). → terminó."""
        from PySide6 import QtCore
        tarea = self._georef_auto_tarea
        if tarea is None:
            return True
        lazo = QtCore.QEventLoop()
        tarea.terminado.connect(lambda *_a: QtCore.QTimer.singleShot(0, lazo.quit))
        QtCore.QTimer.singleShot(ms, lazo.quit)
        if self._georef_auto_tarea is not None:
            lazo.exec()
        return self._georef_auto_tarea is None
