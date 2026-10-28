"""ventana_pasos.py — volver atrás en el asistente sin rehacer lo ya hecho (`PasosVivosMixin`).

Pedido del usuario (2026-10-28): con la hoja compuesta ya armada, ir a «Capas de la hoja» y volver
a «Componer hoja» redibujaba todo; lo mismo entre «Capas» y la vista previa. «Si yo avancé y quiero
retroceder, no es necesario recargar todo… solo si hubo algún cambio».

Cada paso deja su ventana VIVA (oculta) en `Main._pasos_vivos` («comp», «capas», «vista») y se
vuelve a mostrar tal cual si lo que recibe es lo mismo que dejó (`composite_dialog.compose_sheet`,
`layer_dialog.choose_sheet_layers`, `recognition_dialog.show_recognition_preview` con `vivo=`).
Además, en el mismo asistente:
  · aceptar el compositor con la MISMA hoja compuesta que ya se armó no la vuelve a armar ni a
    dibujar (`_paso_compuesta`);
  · aceptar «Capas» con la misma hoja y las mismas capas no la vuelve a cargar (`_paso_hoja`);
  · el reconocimiento ya tenía su caché (`recognition_cache`).
Cualquier cambio cambia la firma: entonces sí se rehace, como siempre. Se sueltan al abrir otro
PDF o proyecto, al cerrar, al importar y al cancelar el asistente.
"""
from __future__ import annotations

from hoja import pdf_layers
from reconocimiento import recognition_cache


class PasosVivosMixin:
    def _pasos(self) -> dict:
        return self.__dict__.setdefault("_pasos_vivos", {})

    def _soltar_pasos(self):
        """Cierra las ventanas del asistente que esperaban y olvida lo hecho en él."""
        vivos = self.__dict__.pop("_pasos_vivos", None) or {}
        for dlg in vivos.values():
            soltar = getattr(dlg, "soltar_vivo", None)
            try:
                if soltar is not None:
                    soltar()
                dlg.deleteLater()
            except RuntimeError:
                pass
        self._paso_compuesta = None
        self._paso_hoja = None

    def _cargar_hoja_si_cambio(self, page_idx):
        """Carga la hoja en el editor salvo que ya esté, tal cual, por este mismo asistente."""
        firma = self._firma_hoja(page_idx)
        if firma is None or firma != getattr(self, "_paso_hoja", None):
            self._load_sheet_busy(page_idx)
            self._paso_hoja = self._firma_hoja(page_idx)

    def _empezar_asistente(self):
        """Un asistente nuevo (abrir PDF, «Componer hoja» desde el editor, agregar utilidad): lo que
        se armó en el anterior no cuenta como hecho (el editor pudo cambiar desde entonces). Las
        ventanas vivas sí sirven: se reusan solo si reciben lo mismo que dejaron."""
        self._paso_compuesta = None
        self._paso_hoja = None

    def _firma_compuesta(self, comp, sources, hidden_by_source):
        """La hoja compuesta tal como se arma (sin lo que es solo vista)."""
        return (recognition_cache.composition_signature(comp), self._src_fingerprints(sources),
                recognition_cache.freeze({str(k): sorted(v) for k, v in (hidden_by_source or {}).items() if v}))

    def _firma_hoja(self, page_idx):
        """La hoja cargada en el editor: documento, hoja, capas apagadas y escala."""
        doc = self.__dict__.get("doc")
        item = self.canvas.pixmap_item
        if doc is None or doc.is_closed or item is None:
            return None
        return (id(doc), self.__dict__.get("work_pdf_path"), int(page_idx),
                tuple(sorted(pdf_layers.hidden_layers(doc))), self.__dict__.get("_scale_override"),
                item.pixmap().cacheKey())
