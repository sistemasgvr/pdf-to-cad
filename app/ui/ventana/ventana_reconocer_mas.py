"""«Reconocer más capas…» — reconocer otras capas de la hoja del editor SIN perder lo hecho.

Pedido del usuario 2026-11-12 (recomendación 1 de la revisión): una vez importadas las tuberías por
capas y avanzado el lienzo, «Componer hoja…» volvía a cargar la hoja y lo importado reemplazaba todo.
Aquí el asistente arranca en «Capas de la hoja» sobre la MISMA hoja (sin volver a armarla) y al importar
el editor vuelve a como estaba (`respaldo_editor`) y lo reconocido entra ENCIMA, sin las líneas que ya
están dibujadas (`nucleo.reconocer_mas`). Cualquier salida sin importar deja el editor como estaba.
`self._reconociendo_mas` = el modo (None fuera de él).
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)

TOL_REPETIDA_FT = 0.5          # una línea nueva a ≤ esto de una del editor (toda ella) ya está dibujada


class ReconocerMasMixin:
    def reconocer_mas_capas(self):
        """Herramientas → «Reconocer más capas de esta hoja…»."""
        titulo = _tr("Reconocer más capas")
        if (not self.doc or not self.src_pdfs or self.canvas.pixmap_item is None
                or getattr(self, "blank_canvas", False)):
            self.informar(titulo, _tr("Abre primero un PDF vectorial con capas."))
            return
        if self.composite is not None and self.composite.manual:
            self.informar(titulo, _tr(
                "La hoja del editor es un PDF imagen/escaneo: no tiene capas que reconocer."))
            return
        self._empezar_asistente()
        # la hoja del editor ya está armada y cargada: el asistente no la vuelve a armar ni a dibujar
        self._paso_compuesta = self._firma_compuesta(self.composite, self.src_pdfs, self.hidden_ocgs_by_source)
        self._paso_hoja = self._firma_hoja(self.page_idx)
        self._soltar_respaldo()
        self._respaldo = respaldo_editor.tomar(self)      # SIEMPRE: cancelar vuelve a como estaba
        en_editor = list(dict.fromkeys(p.get("layer") for p in self.pipes if p.get("layer")))
        self._reconociendo_mas = dict(hoja=self._hoja_reconocer_mas(), pagina=self.page_idx)
        # las utilidades que ya están en el editor no se marcan (se pueden marcar)
        self._recognition_utilities = tuple(
            u for u in _recognition.SUPPORTED_UTILITIES if u not in en_editor) or _recognition.DEFAULT_UTILITIES
        self._recog_ready = False
        if not self._wizard_sheet_flow(self.page_idx, start_step=1):
            self._cancelar_asistente(_tr("Reconocimiento cancelado — el editor queda como estaba."))

    def _hoja_reconocer_mas(self):
        """La hoja del editor sin las capas apagadas: si cambia (otra composición), lo reconocido
        ya no cae en las coordenadas de lo dibujado."""
        return (recognition_cache.composition_signature(self.composite), self._src_fingerprints(self.src_pdfs))

    def _importar_mas(self, results):
        """«Importar» en este modo: el editor como estaba (hoja, capas, modelo, deshacer) y lo
        reconocido ENCIMA, sin las líneas que ya están dibujadas."""
        from hoja import pdf_layers as _pdf_layers
        modo, self._reconociendo_mas = self._reconociendo_mas, None
        page = results[0].page_index if results else None
        if modo["hoja"] != self._hoja_reconocer_mas() or page != modo["pagina"]:
            self.informar(_tr("Reconocer más capas"), _tr(
                "Se cambió la hoja durante el asistente: lo reconocido no corresponde a la hoja del "
                "editor. Para trabajar sobre otra hoja usa «Componer hoja de trabajo…»."))
            self._reponer_respaldo(_tr("Reconocimiento cancelado — el editor queda como estaba."))
            return False
        r, self._respaldo = self._respaldo, None
        respaldo_editor.reponer(self, r)                  # hoja, modelo, deshacer… de antes
        if self.doc is not None:                          # las capas del PDF, como estaban en el editor
            _pdf_layers.set_hidden(self.doc, list(self.hidden_ocgs or []))
        self._respaldo = respaldo_editor.tomar(self)      # por si no hay nada que importar
        fpp = self.scale / self.zoom if self.scale and self.zoom else 0.0
        self._tol_repetidas = max(2.0, TOL_REPETIDA_FT / fpp) if fpp else 2.0
        self._repetidas_quitadas = 0
        try:
            with _busy_mod.busy(self, _tr("Importando al editor…")):
                imported = self._import_recognized_pipes(results)
        finally:
            self._tol_repetidas = None
        if not imported:
            self._reponer_respaldo(_tr("No hay tramos nuevos para importar — el editor queda como estaba."))
            return False
        self._soltar_respaldo()
        utils = [u for u in dict.fromkeys(getattr(x, "utility", None) for x in results) if u]
        self.capas_apagadas = {c for c in self.capas_apagadas if "/" not in c or c.split("/")[0] not in utils}
        if self.capas_apagadas & set(utils):               # lo reconocido se ve («Capas»)
            self.capas_apagadas -= set(utils)
            self._aplicar_capas()
        self._dirty = True
        if self._repetidas_quitadas:
            self._info(self.lbl_info.text() + " " + _tr(
                "Ya dibujadas en el editor (no se repiten): {n}.").format(n=self._repetidas_quitadas))
        _busy_mod.toast(self, "✔ " + _tr("Capas agregadas a lo que ya había en el editor"))
        return True

    def _sin_repetidas(self, pipes):
        """En «Reconocer más capas»: quita las líneas nuevas que ya están dibujadas."""
        tol = getattr(self, "_tol_repetidas", None)
        if not tol:
            return pipes
        from nucleo import reconocer_mas
        quedan, n = reconocer_mas.quitar_repetidas(self.pipes, pipes, tol)
        self._repetidas_quitadas = getattr(self, "_repetidas_quitadas", 0) + n
        return quedan
