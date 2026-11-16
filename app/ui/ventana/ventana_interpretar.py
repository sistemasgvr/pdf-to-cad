"""INTERPRETAR la hoja del editor en segundo plano y llenar el panel «Reconocer» (plan 2026-11-16, «reconocimiento
desde el editor», Tarea 9).

Abrir un PDF = componer la hoja → el editor, al instante. Ya no hay paso «Capas de la hoja» ni vista previa
obligatoria: `_interpretar_hoja` manda `hoja.interpretar_trabajo:interpretar` al trabajador «reconocer»
(`proceso.RETENEDOR`: la lectura de la hoja queda ahí para los ▶ que siguen) y la ventana sigue libre; una tarjeta
chica abajo a la derecha (`tarjeta_avance`, sin velo, con «Cancelar») muestra la etapa. Al terminar:

  · `Main._interpretacion` = lo leído (capas, leyenda, estilos sugeridos, letras, símbolos, rótulos, escala, firma);
  · los roles iniciales de la hoja = los que dejaba «Capas de la hoja» al continuar sin tocar nada
    (`roles_iniciales`: en una hoja sin capas, lo que asigna la leyenda del mapa o los estilos sugeridos), así las
    mismas utilidades que antes quedan listas para el ▶;
  · `reconocer_estado = de_interpretacion(...)`; el riel ya está en la página «Reconocer» (se pasa al empezar).

Lo que llega tarde (otra hoja, otro PDF, cerrar: `_soltar_reconocer` sube `_recog_generation`) se descarta. Si
falla, las filas quedan «Sin interpretar» con el botón «Interpretar la hoja» y un aviso en la barra de estado.
"""
from __future__ import annotations

from nucleo import reconocer_estado as RE
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

OBJETIVO = "hoja.interpretar_trabajo:interpretar"
PAGINA_RECONOCER = 4                       # `ventana_shell.RIEL`: «Reconocer»
M_INTERPRETANDO = N_("Interpretando la hoja…")


def _borrar(ruta) -> bool:
    """Borra `ruta` → True si ya no existe."""
    import os
    try:
        if os.path.isfile(ruta):
            os.remove(ruta)
    except OSError:
        return False
    return True


class InterpretarMixin:
    _interpretacion = None          # lo que devolvió `interpretar_trabajo` (firma incluida)
    _interp_tarea = None            # la Tarea en curso (o None)
    _interp_tarjeta = None          # `tarjeta_avance.CapaTarjetas` de la interpretación
    _reconocer_escaneo = False      # hoja escaneada: el panel dice que no hay nada que reconocer
    _rec_hoja = None                # «Agregar utilidad»: {ruta, hoja, firma, desde, tmp, grupo} (ventana_agregar)

    # ── API ──────────────────────────────────────────────────────────────
    def interpretando(self) -> bool:
        return self._interp_tarea is not None

    def _interpretar_hoja(self):
        """Interpreta la hoja del editor en el trabajador y llena el panel al terminar (la ventana no espera)."""
        from ui.comun import proceso
        if self._interp_tarea is not None:
            self._info(_tr(M_INTERPRETANDO))
            return
        if not getattr(self, "doc", None) or self.canvas.pixmap_item is None or self._reconocer_escaneo:
            return
        ruta, hoja = self._rec_ruta_hoja()
        if not ruta:
            return
        from hoja import pdf_layers
        firma = self._firma_hoja_actual()
        ov = self._rec_hoja
        ons = () if ov is not None else pdf_layers.encendidas(self.doc)
        ocultos = () if ov is not None else sorted(getattr(self.doc, "_pdf_style_hidden", None) or ())
        t = proceso.Tarea(OBJETIVO, args=(ruta, int(hoja), ons, ocultos, firma),
                          kwargs={"escala": float(self.scale) if self.scale else None})
        gen = getattr(self, "_recog_generation", 0)
        self._interp_tarea = t
        self._interp_abrir_tarjeta()
        self._refrescar_panel_reconocer()
        self._interp_a_la_vista()
        t.avance.connect(lambda a, t=t: self._interp_avance(t, a))
        t.terminado.connect(lambda r, e, t=t, gen=gen, firma=firma: self._interp_terminado(t, gen, firma, r, e))
        try:
            proceso.trabajador(proceso.RETENEDOR).enviar(t)
        except Exception:
            import traceback
            self._interp_terminado(t, gen, firma, None, traceback.format_exc())

    def cancelar_interpretacion(self, aviso=True):
        t, self._interp_tarea = self._interp_tarea, None
        self._interp_cerrar_tarjeta()
        if t is not None and not t.hecha:
            t.cancelar()
        self._refrescar_panel_reconocer()
        if aviso and t is not None:
            self._info(_tr("Interpretación cancelada: pulsa «Interpretar la hoja» en el panel Reconocer para "
                           "volver a leerla."))

    # ── dónde se lee ─────────────────────────────────────────────────────
    def _rec_ruta_hoja(self):
        """(PDF, hoja) que se interpreta y se reconoce: la hoja del editor, o la hoja de la utilidad agregada."""
        ov = self._rec_hoja
        if ov is not None:
            if not ov.get("ruta"):
                self._rearmar_rec_hoja(ov)
            return ov.get("ruta"), int(ov["hoja"])
        return self.work_pdf_path or self.pdf_path, int(self.page_idx)

    def _rearmar_rec_hoja(self, ov):
        """Proyecto reabierto con una utilidad agregada (`hoja_agregada` del .digproj): su hoja = las piezas de su
        grupo con el mismo `marco` (mismas coordenadas: `hoja_calcada.solo_grupos`, como los «Planos» de «Capas»),
        armada otra vez en el trabajador. Sin ella el ▶ leería la hoja combinada y mezclaría los dos PDF."""
        import os
        import tempfile
        from hoja import hoja_calcada
        from ui.comun import proceso
        comp = self.composite
        grupo = int(ov.get("grupo") or 0)
        if comp is None or not self.src_pdfs or not any(int(p.grupo) == grupo for p in comp.pieces):
            return
        sub = hoja_calcada.solo_grupos(comp, [grupo])
        res, err = proceso.ejecutar(
            "hoja.composite_trabajo:materializar", sub.to_dict(), [e["data"] for e in self.src_pdfs],
            {k: list(v) for k, v in (self.hidden_ocgs_by_source or {}).items()},
            [e.get("name", "") for e in self.src_pdfs])
        if err or not res:
            return
        fd, ruta = tempfile.mkstemp(prefix="pdfcad_agregada", suffix=".pdf")
        with os.fdopen(fd, "wb") as fp:
            fp.write(res[0])
        ov["ruta"], ov["tmp"], ov["hoja"] = ruta, ruta, 0

    def _rec_hoja_de_proyecto(self, d):
        """`hoja_agregada` guardada → `_rec_hoja` sin archivo (se arma con el primer uso)."""
        if not isinstance(d, dict) or not d.get("firma"):
            return None
        try:
            return {"ruta": None, "tmp": None, "hoja": int(d.get("hoja") or 0), "firma": str(d["firma"]),
                    "desde": int(d.get("desde") or 0), "grupo": int(d.get("grupo") or 0)}
        except (TypeError, ValueError):
            return None

    def _doc_de_lectura(self):
        """(documento, hoja, propio) de la hoja que se reconoce: la del editor o, con una utilidad agregada, la suya
        (abierta aparte: `propio` = quien lo pide lo cierra). (None, 0, False) si no se puede armar."""
        if self._rec_hoja is None:
            return self.doc, int(self.page_idx), False
        ruta, hoja = self._rec_ruta_hoja()
        if not ruta:
            return None, 0, False
        import fitz
        return fitz.open(ruta), int(hoja), True

    def _soltar_rec_hoja(self):
        """Suelta la hoja de la utilidad agregada y borra su temporal. El trabajador «reconocer» puede tenerlo
        abierto (lectura retenida; en Windows no se borra un archivo abierto): se suelta su lectura y se borra al
        terminar eso."""
        ov, self._rec_hoja = self._rec_hoja, None
        tmp = (ov or {}).get("tmp")
        if not tmp or _borrar(tmp):
            return
        from ui.comun import proceso
        t = proceso.soltar_lectura(proceso.RETENEDOR)
        if t is not None:
            t.terminado.connect(lambda *_a, tmp=tmp: _borrar(tmp))

    # ── trabajo ──────────────────────────────────────────────────────────
    def _interp_vigente(self, t, gen):
        return self._interp_tarea is t and getattr(self, "_recog_generation", 0) == gen

    def _interp_avance(self, t, a):
        if self._interp_tarea is not t or not a or a[0] != "detalle":
            return
        tarjeta = self._interp_tarjeta
        if tarjeta is not None:
            from ui.comun import busy
            tarjeta.step(detail=busy.detalle_de(a[1], a[2], a[3]), done=a[2] if a[3] else None,
                         total=a[3] if a[3] else None)

    def _interp_terminado(self, t, gen, firma, res, err):
        if not self._interp_vigente(t, gen):
            return                                       # cancelada, o de otra hoja / otro PDF
        self._interp_tarea = None
        self._interp_cerrar_tarjeta()
        if err == "cancelado":
            self._refrescar_panel_reconocer()
            return
        if err or not isinstance(res, dict):
            self._interp_fallo(err or _tr("La interpretación no devolvió nada."))
            return
        try:
            self._interp_aplicar(res, firma)
        except Exception:
            import traceback
            self._interp_fallo(traceback.format_exc())

    def _interp_aplicar(self, res, firma):
        from ui.asistente import roles_iniciales as RI
        from ui.asistente.layer_sugeridos import textos_de_fuentes
        self._interpretacion = res
        hoja = int(self.page_idx)
        if self.doc is not None and self._rec_hoja is None and res.get("leyenda") is not None:
            # la leyenda leída queda en el documento: «Capas y estilos…» no la vuelve a leer
            self.doc.__dict__.setdefault("_pdfcad_leyenda_mapa", {}).setdefault(hoja, res["leyenda"])
        roles = RI.roles_iniciales(res.get("layers"), res.get("leyenda"), res.get("sugeridos"),
                                   base_roles=self._roles_de_la_hoja(hoja),
                                   textos_fuentes=lambda: textos_de_fuentes(self._legend_sources()))
        self._layer_roles_by_utility = roles
        self._layer_roles_hoja = self._clave_hoja(hoja)
        self.reconocer_estado = RE.de_interpretacion(self._rec_estado(), res, firma, hidden=self.hidden_ocgs,
                                                     roles_by_utility=self._roles_de_la_hoja(hoja))
        self._refrescar_panel_reconocer()
        n = sum(1 for f in self.reconocer_estado.filas.values() if f.estado == "pendiente")
        self._info(_tr("Hoja interpretada: {n} filas listas para reconocer en el panel Reconocer.").format(n=n))

    def _interp_fallo(self, err):
        from nucleo import diagnostico
        if err == "memoria":
            texto = _tr("La hoja necesita más memoria de la que hay libre en el equipo.")
        else:
            diagnostico.registrar(err, "Interpretar la hoja")
            texto = diagnostico.resumen(err)
        self._refrescar_panel_reconocer()
        self._info(_tr("No se pudo interpretar la hoja: {e}. Pulsa «Interpretar la hoja» en el panel Reconocer "
                       "para intentarlo otra vez.").format(e=texto))

    # ── proyecto guardado (Tarea 10) ─────────────────────────────────────
    def _reconocer_de_proyecto(self, rec):
        """Al abrir un .digproj: las filas y la interpretación liviana que se guardaron (`project_io.
        reconocer_de_model`), sin interpretar nada. Proyecto viejo: lo ya importado «reconocida» y el panel ofrece
        «Interpretar la hoja». La lectura de la hoja se rehace sola con el primer ▶."""
        rec = rec or {}
        self._soltar_rec_hoja()
        self._rec_hoja = self._rec_hoja_de_proyecto(rec.get("hoja_agregada"))
        self._interpretacion = rec.get("interpretacion")
        roles = rec.get("roles")
        self._layer_roles_by_utility = dict(roles or {})          # los de la hoja guardada (o ninguno)
        self._layer_roles_hoja = self._clave_hoja(self.page_idx) if roles else None
        # sin PDF (hoja en blanco) no hay nada que reconocer: lo dibujado no es «reconocido»
        self.reconocer_estado = (rec.get("estado") if getattr(self, "doc", None) is not None else None) or RE.nuevo()
        comp = getattr(self, "composite", None)
        self._reconocer_escaneo = bool(comp is not None and comp.manual)
        interp = self._interpretacion or {}
        if self.doc is not None and self._rec_hoja is None and interp.get("leyenda") is not None:
            # como `_interp_aplicar`: «Capas y estilos…» no vuelve a leer la leyenda
            self.doc.__dict__.setdefault("_pdfcad_leyenda_mapa", {}).setdefault(int(self.page_idx), interp["leyenda"])
        self._refrescar_panel_reconocer()

    # ── interfaz ─────────────────────────────────────────────────────────
    def _interp_a_la_vista(self):
        """El riel en «Reconocer» al empezar (el panel dice «Interpretando la hoja…» y se llena solo al terminar);
        sin abrir el panel si se oculta solo: no tapa el plano."""
        pila = getattr(self, "paneles_riel", None)
        if pila is None:
            return
        pila.setCurrentIndex(PAGINA_RECONOCER)
        self._pagina_riel = PAGINA_RECONOCER
        for k, b in getattr(self, "_riel_btn", ()) or ():
            b.setChecked(k == PAGINA_RECONOCER)
        if hasattr(self, "_titulo_panel_izq"):
            self._titulo_panel_izq()

    def _interp_abrir_tarjeta(self):
        from ui.comun.tarjeta_avance import CapaTarjetas
        self._interp_cerrar_tarjeta()
        tarjeta = CapaTarjetas(self, cancel=self.cancelar_interpretacion)
        tarjeta.begin(_tr(M_INTERPRETANDO), _tr("Capas, letras, leyenda, estilos, símbolos y rótulos · en "
                                                 "segundo plano"))
        self._interp_tarjeta = tarjeta

    def _interp_cerrar_tarjeta(self):
        tarjeta, self._interp_tarjeta = self._interp_tarjeta, None
        if tarjeta is not None:
            tarjeta.end()
