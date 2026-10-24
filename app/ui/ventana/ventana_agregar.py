"""«Agregar utilidad desde otro PDF…» — todas las utilidades en la MISMA hoja del editor.

Pedido del usuario 2026-10-23: los mapas llegan en un PDF por utilidad (Phoenix: dos de agua,
dos de alcantarillado, dos de drenaje). Con una utilidad ya importada, desde el editor se
elige el PDF de la siguiente, se pasa por el mismo flujo (Capas de la hoja → vista previa) y
al importar queda junto a la anterior, en su lugar.

Cómo: la hoja de la utilidad nueva se arma CALCADA sobre la del editor (`hoja.hoja_calcada`,
en el proceso trabajador): cada hoja del PDF nuevo se ubica sobre su pieza del editor por el
mapa base que comparten, con la misma área y el mismo `marco`, así lo que se reconoce en ella
cae en las coordenadas del editor sin mover nada. Al importar, la hoja del editor pasa a ser
las piezas de antes + las nuevas (fundidas) y solo cambia la imagen de fondo
(`canvas.cambiar_imagen`): lo dibujado, el deshacer y la georreferencia no se tocan.

Todo el asistente corre con el respaldo del editor (`respaldo_editor`): cualquier salida sin
importar lo deja como estaba. `self._agregando` = el modo (None fuera de él).
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class AgregarUtilidadMixin:
    # ─────────────────────────── entrada ───────────────────────────
    def agregar_utilidad(self):
        """Herramientas → «Agregar utilidad desde otro PDF…»."""
        titulo = _tr("Agregar utilidad")
        if not self.doc or not self.src_pdfs or self.canvas.pixmap_item is None or getattr(self, "blank_canvas", False):
            QtWidgets.QMessageBox.information(self, titulo, _tr(
                "Abre primero el PDF de una utilidad e impórtala: la nueva se agrega sobre esa hoja."))
            return
        if self.composite is not None and self.composite.manual:
            QtWidgets.QMessageBox.information(self, titulo, _tr(
                "La hoja del editor es un PDF imagen/escaneo: no tiene un mapa base vectorial con el que "
                "ubicar otra utilidad."))
            return
        rutas = self._elegir_pdfs_utilidad()
        if not rutas:
            return
        nuevas = []
        for ruta in rutas:
            try:
                with open(ruta, "rb") as fp:
                    nuevas.append({"name": os.path.basename(ruta), "data": fp.read(), "path": ruta})
            except OSError as exc:
                QtWidgets.QMessageBox.warning(self, titulo, _tr("No se pudo leer el PDF:\n\n{e}").format(e=exc))
                return
        editor = self._composicion_del_editor()
        res = self._calcar_en_fondo(editor, nuevas)
        if res is None:
            return                                           # cancelado o error ya avisado
        if not res.get("comp"):
            QtWidgets.QMessageBox.information(self, titulo, _tr(
                "Ninguna hoja de «{pdf}» dibuja el mismo lugar que la hoja del editor (su mapa base de lotes y "
                "calles no coincide con el de la hoja), así que no se puede ubicar sobre ella.").format(
                    pdf=", ".join(e["name"] for e in nuevas)))
            return
        self._empezar_agregado(editor, nuevas, res)

    def _elegir_pdfs_utilidad(self):
        """Los PDF de la utilidad nueva (uno o varios). Si la hoja del editor viene de varios PDF
        y se eligió uno solo, ofrece los de la misma utilidad de la carpeta («…_South»)."""
        from hoja import composicion_hermanos
        carpeta = next((os.path.dirname(e["path"]) for e in self.src_pdfs
                        if e.get("path") and os.path.isdir(os.path.dirname(e["path"]))), DOWNLOADS)
        rutas, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, _tr("Agregar utilidad: elige su PDF"), carpeta, "PDF (*.pdf)")
        rutas = list(rutas or [])
        if len(rutas) == 1 and len(self.src_pdfs) > 1:
            ya = [e.get("path") or "" for e in self.src_pdfs]
            mas = [p for p in composicion_hermanos.candidatos(rutas[0], ya)][:len(self.src_pdfs) - 1]
            if mas:
                r = QtWidgets.QMessageBox.question(
                    self, _tr("Agregar utilidad"),
                    _tr("La hoja del editor viene de {n} PDF. ¿Agregar también estos de la misma utilidad?\n\n{lista}").format(
                        n=len(self.src_pdfs), lista="\n".join("· " + os.path.basename(p) for p in mas)),
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes)
                if r == QtWidgets.QMessageBox.Yes:
                    rutas += mas
        return rutas

    def _composicion_del_editor(self):
        """La composición de la hoja del editor (una hoja suelta = una pieza entera)."""
        if self.composite is not None and self.composite.pieces:
            return composite_mod.Composite.from_dict(self.composite.to_dict())
        return composite_mod.Composite([composite_mod.Piece(0, int(self.page_idx), [0.0, 0.0, 1.0, 1.0],
                                                            src_scale=float(self.scale))])

    def _calcar_en_fondo(self, editor, nuevas):
        """`hoja_calcada.calcar_trabajo` en el proceso trabajador, con «Cancelar». → dict o None."""
        from ui.comun import proceso
        t = proceso.Tarea("hoja.hoja_calcada:calcar_trabajo",
                          (editor.to_dict(), [e["data"] for e in self.src_pdfs], [e["data"] for e in nuevas],
                           [e["name"] for e in nuevas], float(self.scale),
                           [e.get("name", "") for e in self.src_pdfs]))
        out = {}
        lazo = QtCore.QEventLoop()
        ov = _busy_mod.overlay_for(self)

        def etapa(a):
            if a and a[0] == "detalle" and ov.active:
                ov.step(detail=_busy_mod.detalle_de(a[1], a[2], a[3]),
                        done=a[2] if a[3] else None, total=a[3] if a[3] else None, pump=False)
        t.avance.connect(etapa)
        t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
        ov.begin(_tr("Ubicando «{pdf}» sobre la hoja del editor…").format(pdf=nuevas[0]["name"]),
                 _tr("Buscando en cada hoja el mismo mapa base (lotes, calles)"), cancel=t.cancelar)
        try:
            proceso.trabajador("principal").enviar(t)
            if not t.hecha:
                lazo.exec()
        finally:
            ov.end()
        err = out.get("e", "")
        if err == "cancelado":
            self._info(_tr("Agregar utilidad cancelado — el editor queda como estaba."))
            return None
        if err:
            QtWidgets.QMessageBox.warning(self, _tr("Agregar utilidad"), _tr(
                "No se pudo ubicar el PDF sobre la hoja del editor:\n\n{e}").format(
                    e=_tr("La hoja necesita más memoria de la que hay libre en el equipo.") if err == "memoria" else err))
            return None
        return out.get("r")

    def _empezar_agregado(self, editor, nuevas, res):
        """Respaldo del editor, la hoja calcada como hoja de trabajo y el asistente desde «Capas»."""
        from hoja import hoja_calcada
        calco = composite_mod.Composite.from_dict(res["comp"])
        docs = [fitz.open(stream=e["data"], filetype="pdf") for e in self.src_pdfs]
        try:
            marco = hoja_calcada.marco_de(
                editor, lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height))
        finally:
            for d in docs:
                d.close()
        # SIEMPRE con respaldo (aunque el editor no tenga líneas): cancelar vuelve a SU hoja
        self._soltar_respaldo()
        self._respaldo = respaldo_editor.tomar(self)
        en_editor = {p.get("layer") for p in self.pipes}
        self._agregando = dict(
            editor=editor.to_dict(), marco=list(marco), n_editor=len(self.src_pdfs), escala=float(self.scale),
            ubicaciones=list(res.get("ubicaciones") or []), sin_pareja=list(res.get("sin_pareja") or []),
            nombres=[e["name"] for e in nuevas])
        self.src_pdfs = nuevas
        self.composite = calco
        self.hidden_ocgs_by_source = {}
        self._layer_roles_by_utility = {}
        self._layer_roles_hoja = None
        self._letters_off = set()
        self._recog_ready = False
        # «agregar OTRA utilidad»: las que ya están en el editor no se marcan (se pueden marcar)
        self._recognition_utilities = tuple(u for u in _recognition.SUPPORTED_UTILITIES if u not in en_editor) \
            or _recognition.DEFAULT_UTILITIES
        try:
            self._apply_composite()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, _tr("Agregar utilidad"),
                _tr("No se pudo armar la hoja compuesta:\n\n{e}").format(e=exc))
            self._cancelar_asistente(_tr("Agregar utilidad cancelado — el editor queda como estaba."))
            return
        n, total = len(calco.pieces), len(editor.pieces)
        self._info(_tr("{n} de {t} hojas de la hoja del editor ubicadas en «{pdf}» por su mapa base.").format(
            n=n, t=total, pdf=", ".join(e["name"] for e in nuevas)))
        if not self._wizard_sheet_flow(self.page_idx, start_step=1):
            self._cancelar_asistente(_tr("Agregar utilidad cancelado — el editor queda como estaba."))

    # ─────────────────────────── en el asistente ───────────────────────────
    def _agregando_recolocar(self, comp, sources):
        """Tras «Componer hoja» en este modo: cada pieza vuelve al lugar de su hoja sobre la del
        editor (el usuario elige hojas y áreas; el lugar lo pone el mapa base). → hoja o None."""
        from hoja import hoja_calcada
        ag = self._agregando
        docs = [fitz.open(stream=e["data"], filetype="pdf") for e in sources]
        try:
            ubic = [hoja_calcada.Ubicacion.from_dict(u) for u in ag["ubicaciones"]]
            nuevo, quitadas = hoja_calcada.recolocar(
                comp, ubic, ag["marco"], ag["escala"],
                lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height))
        finally:
            for d in docs:
                d.close()
        if quitadas:
            QtWidgets.QMessageBox.information(self, _tr("Agregar utilidad"), _tr(
                "{n} hoja(s) no coinciden con ninguna hoja del editor (su mapa base no está en la hoja) y "
                "no se usan: {lista}.").format(n=len(quitadas), lista=", ".join(
                    sorted({f"{sources[p.source]['name']} · {p.page + 1}" for p in quitadas}))))
        if not nuevo.pieces:
            return None
        return nuevo

    def _importar_agregando(self, results):
        """«Importar» en este modo: el editor como estaba, su hoja pasa a ser la combinada (solo
        cambia la imagen de fondo) y lo reconocido entra ENCIMA de lo que hay."""
        ag, self._agregando = self._agregando, None
        nuevas, calco, ocultas = self.src_pdfs, self.composite, self.hidden_ocgs_by_source
        r, self._respaldo = self._respaldo, None
        # El editor se redibuja con lo importado, no antes al reponerlo ni al cambiar su hoja (12 + 12
        # mapas: ~1.5 s menos de ventana quieta). Mientras la hoja combinada se arma en el proceso la
        # ventana atiende eventos: la copia automática espera (`_importando`) a que tenga su hoja nueva.
        previo, self._importando = getattr(self, "_importando", False), True
        try:
            with self._redibujo_diferido():
                fallo = self._combinar_hojas(r, ag, nuevas, calco, ocultas)
        finally:
            self._importando = previo
        if fallo is not None:
            QtWidgets.QMessageBox.warning(self, _tr("Agregar utilidad"),
                _tr("No se pudo armar la hoja con las dos utilidades:\n\n{e}").format(e=fallo))
            self._reponer_respaldo(_tr("Agregar utilidad cancelado — el editor queda como estaba."))
            return False
        self._origen_desde_fuente = len(self.src_pdfs) - len(nuevas)   # datos extendidos: la pieza NUEVA
        try:
            with _busy_mod.busy(self, _tr("Importando al editor…")):
                imported = self._import_recognized_pipes(results)
        finally:
            self._origen_desde_fuente = None
        if not imported:
            self._reponer_respaldo(_tr("No hay tramos reconocidos para importar — el editor queda como estaba."))
            return False
        self._soltar_respaldo()
        self._dirty = True
        _busy_mod.toast(self, "✔ " + _tr("Utilidad agregada a la hoja del editor"))
        return True

    def _combinar_hojas(self, r, ag, nuevas, calco, ocultas):
        """El editor como estaba (respaldo `r`) y su hoja pasa a ser la combinada: sus piezas + las
        nuevas. → None, o la excepción si la hoja combinada no se pudo armar."""
        from hoja import hoja_calcada
        respaldo_editor.reponer(self, r)                  # hoja, modelo, deshacer… de antes
        self._respaldo = respaldo_editor.tomar(self)      # por si la hoja combinada falla
        editor = composite_mod.Composite.from_dict(ag["editor"])
        n_editor = len(self.src_pdfs)
        comb = hoja_calcada.combinar(editor, calco, n_editor, ag["marco"], ag["escala"])
        self.src_pdfs = list(self.src_pdfs) + list(nuevas)
        self.composite = comb
        hidden = {k: list(v) for k, v in (self.hidden_ocgs_by_source or {}).items()}
        hidden.update({str(int(k) + n_editor): list(v) for k, v in (ocultas or {}).items()})
        self.hidden_ocgs_by_source = hidden
        try:
            self._poner_hoja_combinada(comb)
        except Exception as exc:
            return exc
        return None

    def _poner_hoja_combinada(self, comp):
        """Materializa `comp` (mismo marco = mismo tamaño y coordenadas que la hoja del editor) y
        cambia SOLO la imagen de fondo: lo dibujado encima, el deshacer y la vista quedan."""
        from hoja import pdf_layers as _pdf_layers
        tam = self.canvas.tam_hoja()
        self._cleanup_tmp_composite()                     # el temporal de antes lo guarda el respaldo
        self.doc = None                                   # (el respaldo lo cierra al soltarlo)
        with _busy_mod.busy(self, _tr("Armando la hoja con las dos utilidades…"),
                            _tr("{n} piezas · vectores, capas y textos intactos").format(n=len(comp.pieces))):
            self._build_composite_doc(comp, _pdf_layers)
            page = self.doc[self.page_idx]
            qimg, gray, escala, ancho, alto = self._fondo_de(page)     # en el proceso trabajador
        if tam is not None and (abs(ancho - tam[0]) > 1.0 or abs(alto - tam[1]) > 1.0):
            raise RuntimeError(_tr("La hoja combinada no mide lo mismo que la del editor."))
        self.scale = float(self._scale_override)
        self.rot = page.rotation; mbx = page.mediabox; self.W, self.H = mbx.width, mbx.height
        self.derot = page.derotation_matrix
        self.pageH_px = alto
        self.leader_hpx = max(14.0, min(LEADER_TEXT_FT / self.scale * self.zoom, self.pageH_px * 0.05))
        self.gray = gray
        self._close_editor()
        self.canvas.cambiar_imagen(qimg, escala)
        if self.canvas.nitidez is not None:
            self.canvas.nitidez.fijar(self.canvas.pixmap_item)   # teselas de la hoja NUEVA
        self._update_page_label(); self._refresh_scale_label()
        self._refresh_lists(); self._update_ui(); self._redraw()
