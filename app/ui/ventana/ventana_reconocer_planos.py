"""El panel «Reconocer» con VARIOS planos (hoja con utilidades agregadas desde otros PDF).

Reporte del usuario 2026-11-17: tras «Agregar utilidad desde otro PDF» (agua + alcantarillado de Indian School) el
panel solo tenía las filas de la hoja agregada; las del plano anterior (agua) se perdían: había UN estado del panel
y la interpretación de la hoja nueva lo reemplazaba.

Ahora cada plano (grupo de la hoja, `hoja_calcada.grupos`; los mismos de «Capas ▾») guarda su estado: filas,
interpretación, roles y resultados de sus ▶ (`_rec_planos`, {grupo: foto}). El activo vive en los atributos de
siempre (`reconocer_estado`, `_interpretacion`, `_layer_roles_by_utility`, `_resultados_partes`, `_rec_hoja`), así
el ▶, «Capas y estilos…», el 👁 e interpretar no cambian. El panel muestra un selector de plano si hay más de uno;
elegir otro guarda el activo y repone el otro (sin foto: se interpreta). Cada plano se lee y se reconoce en SU hoja
(`hoja_calcada.solo_grupos`, mismo `marco`: mismas coordenadas que la hoja del editor; `_rearmar_rec_hoja`).
"""
from __future__ import annotations

import hashlib

from nucleo import reconocer_estado as RE
from traduccion.i18n import t as _tr


class PlanosReconocerMixin:
    _rec_planos = None               # {grupo: foto} de los planos que NO están activos

    # ── qué plano ────────────────────────────────────────────────────────
    def _rec_grupo(self) -> int:
        ov = getattr(self, "_rec_hoja", None)
        return int(ov.get("grupo") or 0) if ov else 0

    def rec_planos(self):
        """[(grupo, nombre)] de los planos de la hoja, o [] con un solo plano."""
        gs = self._grupos_planos() if hasattr(self, "_grupos_planos") else []
        return [(int(g), self._nombre_plano(g)) for g in gs] if len(gs) > 1 else []

    # ── fotos ────────────────────────────────────────────────────────────
    def _rec_foto(self) -> dict:
        ov = getattr(self, "_rec_hoja", None)
        hoja = {k: ov.get(k) for k in ("hoja", "firma", "desde", "grupo")} if ov else None
        return dict(estado=self.reconocer_estado, interpretacion=getattr(self, "_interpretacion", None),
                    roles=dict(getattr(self, "_layer_roles_by_utility", None) or {}),
                    resultados=getattr(self, "_resultados_partes", None), cache=getattr(self, "_cache_partes", None),
                    hoja=hoja)

    def _rec_guardar_plano(self, grupo=None):
        """Guarda el plano activo (o lo que hay ahora, como el plano `grupo`). Siempre un dict NUEVO
        (`respaldo_editor` lo guarda por referencia)."""
        g = self._rec_grupo() if grupo is None else int(grupo)
        planos = dict(self._rec_planos or {})
        planos[g] = self._rec_foto()
        self._rec_planos = planos

    def _rec_hoja_de_grupo(self, g, firma=None) -> dict:
        """`_rec_hoja` de un plano: su hoja se arma con el primer uso (`_rearmar_rec_hoja`)."""
        from hoja import hoja_calcada
        from reconocimiento import recognition_cache
        comp = self.composite
        piezas = [p for p in comp.pieces if int(p.grupo) == int(g)] if comp is not None else []
        if firma is None:
            sub = hoja_calcada.solo_grupos(comp, [g]) if comp is not None else None
            datos = ("plano", int(g), recognition_cache.composition_signature(sub) if sub is not None else None,
                     recognition_cache.freeze(self._src_fingerprints(self.src_pdfs)) if self.src_pdfs else None)
            firma = hashlib.sha1(repr(datos).encode("utf-8")).hexdigest()
        return {"ruta": None, "tmp": None, "hoja": 0, "firma": str(firma),
                "desde": min((int(p.source) for p in piezas), default=0), "grupo": int(g)}

    def rec_cambiar_plano(self, g):
        """El panel pasa al plano `g`: guarda el activo y repone `g` (o lo interpreta si nunca se leyó)."""
        g = int(g)
        if g == self._rec_grupo():
            return
        if getattr(self, "_rec_actual", None) is not None or getattr(self, "_interp_tarea", None) is not None:
            self._info(_tr("Espera a que termine lo que se está reconociendo o interpretando para cambiar de plano."))
            self._refrescar_panel_reconocer()
            return
        self._rec_guardar_plano()
        planos = dict(self._rec_planos or {})
        foto = planos.pop(g, None)
        self._rec_planos = planos
        self._soltar_rec_hoja()
        if foto is None:
            self._rec_hoja = self._rec_hoja_de_grupo(g)
            self.reconocer_estado = RE.nuevo()
            self._interpretacion = None
            self._resultados_partes, self._cache_partes = {}, None
            self._layer_roles_by_utility = {}
            self._layer_roles_hoja = None
        else:
            hoja = foto.get("hoja")
            if hoja and int(hoja.get("grupo", g)) == g and hoja.get("firma"):
                self._rec_hoja = dict(hoja, ruta=None, tmp=None)
            else:                                        # el plano de antes de agregar: la hoja del editor de entonces
                e = foto.get("estado")
                self._rec_hoja = self._rec_hoja_de_grupo(g, getattr(e, "firma_hoja", None))
            self.reconocer_estado = foto.get("estado") or RE.nuevo()
            self._interpretacion = foto.get("interpretacion")
            self._resultados_partes = foto.get("resultados") or {}
            self._cache_partes = foto.get("cache")
            self._layer_roles_by_utility = dict(foto.get("roles") or {})
            # los roles son de ESTE plano tal cual (`_roles_de_la_hoja` no les quita lo de la leyenda)
            self._layer_roles_hoja = self._clave_hoja(self.page_idx) if foto.get("roles") else None
        self._reconocer_ultimo = None
        self._refrescar_panel_reconocer()
        self._info(_tr("Panel Reconocer: plano {p}.").format(p=self._nombre_plano(g)))
        if self._interpretacion is None:
            self._interpretar_hoja()

    def _rec_soltar_planos(self):
        self._rec_planos = {}
