"""👁 y «Para verificar» del panel «Reconocer» (plan 2026-11-16, «reconocimiento desde el editor», Tarea 7).

  · 👁 de una utilidad abre la vista previa de siempre (`recognition_dialog`, `editor=True`: sin pasos ni «Atrás»,
    botón «Importar») con el resultado de esa parte. Si no hay uno en la caché de la hoja, antes se reconoce (el mismo
    trabajo del ▶, pero SIN importar ni tocar la fila). «Importar» entra por el mismo camino del ▶ (`_rec_aplicar`:
    importar_parte + tras_reconocer + la pregunta de reemplazar); «Ajustar capas…» pide los roles de ESA utilidad y
    vuelve a reconocer; «Tramos unidos/sueltos» queda en la fila (`unir_tramos`) y cambia su firma.
  · Válvulas, diámetros y rótulos no tienen vista previa propia: su 👁 muestra en el panel sus «Para verificar».
  · Los «Para verificar» de cada fila (`Fila.verificar`, con `visto` = ✔ revisado) se recorren desde el panel: clic =
    ir a su lugar del plano (como `_go_to` de la vista previa) y marcarlo.
"""
from __future__ import annotations

import copy

from PySide6 import QtCore

from nucleo import reconocer_estado as RE
from reconocimiento import recognition_cache
from traduccion.i18n import t as _tr

_HECHAS = ("reconocida", "desactualizada")


class ReconocerVistaMixin:
    # ── 👁 ───────────────────────────────────────────────────────────────
    def ver_parte(self, parte):
        """Vista previa de la fila `parte` (utilidades) o sus «Para verificar» (las demás)."""
        from ui.comun.panel_reconocer import texto_motivo
        parte = str(parte).strip().upper()
        estado = self._rec_estado()
        fila = estado.filas.get(parte)
        if fila is None:
            return
        if parte not in RE.UTILIDADES:
            p = getattr(self, "panel_reconocer", None)
            if p is None or not fila.verificar:
                self._aviso_reconocer(_tr("No hay nada por verificar en esta fila."))
                return
            p.abrir_verificar(parte)
            return
        if self._rec_actual is not None:
            self._aviso_reconocer(_tr(RE.M_RECONOCIENDO))
            return
        ok, clave, datos = RE.puede(estado, parte)
        if not ok:
            self._aviso_reconocer(texto_motivo(clave, datos))
            return
        firma, fp = self._firma_lectura(), self._firma_parte_actual(parte)
        guardado = self._rec_cache().get(self._rec_clave(parte, firma, fp))
        if guardado is not None:
            self._ver_resultado(parte, copy.deepcopy(guardado[0]), firma)
        else:
            self.reconocer_parte(parte, importar=False, ver=True)

    def _ver_resultado(self, parte, res, firma):
        from ui.asistente import recognition_dialog as RD
        if self._rec_actual is not None or firma != self._firma_lectura():
            return                                       # otro ▶, u otra hoja / otras capas desde que se pidió
        results = [r for r in (res or []) if r is not None]
        item = self.canvas.pixmap_item
        if not results or item is None or item.pixmap().isNull():
            self._aviso_reconocer(_tr("No hay nada que mostrar de esta parte."))
            return
        fila = self._rec_estado().filas[parte]
        if any(bool(getattr(r, "join_routes", True)) != bool(fila.unir_tramos) for r in results):
            recognition_cache.set_join_routes(results, bool(fila.unir_tramos))
        extra = {"fondo": {"escala": self.canvas.fondo_escala, "tam": self.canvas.tam_hoja(),
                           "zoom": self.zoom, "pagina": self._pagina_fondo}}
        accion = RD.show_recognition_preview(
            self, lambda: item.pixmap().toImage(), results,
            page_count=self.doc.page_count if self.doc else None, hojas=self._hojas_px(), editor=True, **extra)
        unir = all(bool(getattr(r, "join_routes", True)) for r in results)
        if unir != bool(fila.unir_tramos):               # «Tramos unidos/sueltos» de la vista: queda en la fila
            fila.unir_tramos = unir
        fp = self._firma_parte_actual(parte)
        self._rec_cache().put(self._rec_clave(parte, firma, fp), [copy.deepcopy(results)])
        if accion == RD.PREVIEW_IMPORT:
            reemplazar = False
            if fila.estado in _HECHAS:
                r = self._preguntar_reemplazo(parte)
                if r is None:
                    self._refrescar_panel_reconocer()
                    return
                reemplazar = r == "reemplazar"
            self._rec_aplicar(parte, results, reemplazar, firma, fp)
        elif accion == RD.PREVIEW_ADJUST_LAYERS:
            self._ajustar_y_ver(parte)
        else:
            self._refrescar_panel_reconocer()

    # ── «Ajustar capas…» de una utilidad ──────────────────────────────────
    def ajustar_capas_parte(self, parte):
        """Roles a mano de las capas de UNA utilidad (sin elegir cuál); la fila reconocida queda «desactualizada»."""
        parte = str(parte).strip().upper()
        if parte not in RE.UTILIDADES or not getattr(self, "doc", None):
            return
        if self._ajustar_roles_de(parte, self.page_idx):
            RE.marcar_cambios(self._rec_estado(), {parte: self._firma_parte_actual(parte)})
        self._refrescar_panel_reconocer()

    def _ajustar_y_ver(self, parte):
        """«Ajustar capas…» de la vista previa: pide los roles y vuelve a mostrarla (reconociendo de nuevo si cambió)."""
        self.ajustar_capas_parte(parte)
        QtCore.QTimer.singleShot(0, self, lambda p=parte: self.ver_parte(p))

    # ── «Para verificar» guardados ─────────────────────────────────────────
    def ir_a_por_verificar(self):
        """Muestra u oculta, en el panel, la lista de los «Para verificar» guardados de todas las filas."""
        p = getattr(self, "panel_reconocer", None)
        if p is not None:
            p.abrir_verificar(None, alternar=True)

    def _verificar_item(self, parte, i):
        f = self._rec_estado().filas.get(parte)
        if f is None or not (0 <= i < len(f.verificar)):
            return None
        return f.verificar[i]

    def _verificar_ir(self, parte, i):
        """Clic en un «Para verificar» del panel: el plano va a su lugar (marcado un momento) y queda revisado."""
        v = self._verificar_item(parte, i)
        if v is None:
            return
        r = v.get("rect")
        if r:
            cx, cy = (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0
            self.canvas.centerOn(cx, cy)
            self._marcar_lugar(cx, cy)
        if not v.get("visto"):
            v["visto"] = True
            p = getattr(self, "panel_reconocer", None)
            if p is not None:
                p._llenar_verificar()

    def _verificar_visto(self, parte, i, on):
        v = self._verificar_item(parte, i)
        if v is not None:
            v["visto"] = bool(on)
