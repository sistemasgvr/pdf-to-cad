"""«Agregar utilidad desde otro PDF…» — todas las utilidades en la MISMA hoja del editor.

Pedido del usuario 2026-10-23: los mapas llegan en un PDF por utilidad (Phoenix: dos de agua,
dos de alcantarillado, dos de drenaje). Con una utilidad ya importada, desde el editor se
elige el PDF de la siguiente, se pasa por el mismo flujo que al abrir un PDF (2026-10-26: «Componer
hoja» con las hojas ubicadas ya marcadas) y queda junto a la anterior, en su lugar; su plano y sus
utilidades se encienden y apagan en «Capas».

Cómo: la hoja de la utilidad nueva se arma CALCADA sobre la del editor (`hoja.hoja_calcada`,
en el proceso trabajador): cada hoja del PDF nuevo se ubica sobre su pieza del editor por el
mapa base que comparten, con la misma área y el mismo `marco`, así lo que se reconoce en ella
cae en las coordenadas del editor sin mover nada.

Flujo desde el editor (plan 2026-11-16, Tarea 9): al aceptar «Componer hoja» la hoja del editor pasa a
ser las piezas de antes + las nuevas (fundidas) y solo cambia la imagen de fondo
(`canvas.cambiar_imagen`): lo dibujado, el deshacer y la georreferencia no se tocan. Se INTERPRETA
solo la hoja calcada (la del PDF nuevo: en mapas sin capas los estilos de los dos PDF se mezclarían en
la combinada) y sus filas aparecen en el panel «Reconocer»; cada ▶ reconoce en ESA hoja
(`Main._rec_hoja`, `ventana_interpretar`) y lo reconocido entra encima de lo que hay. Nada se reconoce
solo. Mientras el compositor está abierto corre el respaldo del editor (`respaldo_editor`): cancelar
lo deja como estaba. `self._agregando` = el modo (None fuera de él).

2026-11-18 (pedido del usuario, la 3.ª utilidad tardaba minutos antes de mostrar nada): el compositor se
abre AL INSTANTE con las hojas del PDF nuevo y la búsqueda de dónde cae cada una corre en segundo plano
(`agregar_busqueda`, `composite_agregar`: estado por hoja y «Marcar las N»). Al continuar se ubica solo lo
marcado que falte (`_agregando_recolocar`).
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from nucleo import reconocer_estado as RE


class AgregarUtilidadMixin:
    # ─────────────────────────── entrada ───────────────────────────
    def agregar_utilidad(self):
        """Herramientas → «Agregar utilidad desde otro PDF…»."""
        titulo = _tr("Agregar utilidad")
        if not self.doc or not self.src_pdfs or self.canvas.pixmap_item is None or getattr(self, "blank_canvas", False):
            self.informar(titulo, _tr(
                "Abre primero el PDF de una utilidad e impórtala: la nueva se agrega sobre esa hoja."))
            return
        if self.composite is not None and self.composite.manual:
            self.informar(titulo, _tr(
                "La hoja del editor es un PDF imagen/escaneo: no tiene un mapa base vectorial con el que "
                "ubicar otra utilidad."))
            return
        faltan = RE.faltan_para_agregar(getattr(self, "reconocer_estado", None))
        if faltan:
            self.informar(titulo, _tr(
                "Antes de agregar otra utilidad reconoce todo lo de esta hoja (panel Reconocer → «Reconocer "
                "todo»). Falta: {faltan}.").format(faltan=", ".join(_tr(RE.ETIQUETAS[x]) for x in faltan)))
            return
        while True:
            rutas = self._elegir_pdfs_utilidad()
            if not rutas:
                return
            hecho = self._agregar_desde(rutas, titulo)
            if hecho != "otro":
                return

    def _agregar_desde(self, rutas, titulo):
        """Ubica y agrega los PDF elegidos. → "otro" si el usuario quiere elegir otro PDF."""
        nuevas = []
        for ruta in rutas:
            try:
                with open(ruta, "rb") as fp:
                    nuevas.append({"name": os.path.basename(ruta), "data": fp.read(), "path": ruta})
            except OSError as exc:
                QtWidgets.QMessageBox.warning(self, titulo, _tr("No se pudo leer el PDF:\n\n{e}").format(e=exc))
                return
        from ui.ventana.agregar_busqueda import BusquedaAgregar
        editor = self._composicion_del_editor()
        busq = BusquedaAgregar(editor.to_dict(), [e["data"] for e in self.src_pdfs], nuevas, float(self.scale),
                               [e.get("name", "") for e in self.src_pdfs], parent=self)
        busq.iniciar()
        self._info(_tr("Elige las hojas de «{pdf}» que agregar: mientras tanto se busca dónde cae cada una sobre "
                       "la hoja del editor.").format(pdf=", ".join(e["name"] for e in nuevas)))
        hecho = self._empezar_agregado(editor, nuevas, busq)
        if not hecho and busq.terminada and not busq.cancelada and not busq.error and not busq.ubicadas():
            return self._sin_coincidencias(nuevas)      # canceló tras ver que ninguna hoja cae ahí
        return None

    def _sin_coincidencias(self, nuevas):
        """Ninguna hoja del PDF elegido cae sobre la hoja del editor. No es un error del programa: lo más
        común es que el PDF sea de OTRA zona (p. ej. «…_North» con la hoja del editor «…_South»). Se dice
        así, sin alarma, y se ofrece elegir otro PDF. → "otro" o None."""
        texto = _tr("«{pdf}» no dibuja la zona de la hoja del editor.").format(
            pdf=", ".join(e["name"] for e in nuevas))
        detalle = _tr(
            "Revisé cada hoja buscando el mismo mapa base (calles, lotes) que tiene la hoja del editor, "
            "también si está dibujado de otra manera o como imagen, y ninguna cae sobre ella. Lo más común "
            "es que sea el PDF de otra zona (por ejemplo «North» en vez de «South»). El editor no cambió.")
        if not self.isVisible():                   # (sin la ventana en pantalla: el aviso de siempre)
            self.informar(_tr("Agregar utilidad"), texto + "\n\n" + detalle)
            return None
        caja = QtWidgets.QMessageBox(self)
        caja.setIcon(QtWidgets.QMessageBox.Information)
        caja.setWindowTitle(_tr("Agregar utilidad"))
        caja.setText(texto)
        caja.setInformativeText(detalle)
        otro = caja.addButton(_tr("Elegir otro PDF…"), QtWidgets.QMessageBox.AcceptRole)
        caja.addButton(_tr("Cerrar"), QtWidgets.QMessageBox.RejectRole)
        caja.setDefaultButton(otro)
        caja.exec()
        return "otro" if caja.clickedButton() is otro else None

    def _elegir_pdfs_utilidad(self):
        """Los PDF de la utilidad nueva (uno o varios). Si la hoja del editor viene de varios PDF
        y se eligió uno solo, ofrece los de la misma utilidad de la carpeta («…_South»)."""
        from hoja import composicion_hermanos
        carpeta = next((os.path.dirname(e["path"]) for e in self.src_pdfs
                        if e.get("path") and os.path.isdir(os.path.dirname(e["path"]))), DOWNLOADS)
        rutas, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, _tr("Agregar utilidad: elige su PDF"), carpeta, "PDF (*.pdf)")
        rutas = list(rutas or [])
        n_base = self._pdfs_del_plano_base()
        if len(rutas) == 1 and n_base > 1:
            ya = [e.get("path") or "" for e in self.src_pdfs]
            mas = [p for p in composicion_hermanos.candidatos(rutas[0], ya)][:n_base - 1]
            if mas and self._preguntar_hermanos(rutas[0], mas, n_base):
                rutas += mas
        return rutas

    def _pdfs_del_plano_base(self) -> int:
        """Cuántos PDF forman el plano de la hoja del editor (el primero: con utilidades ya agregadas,
        `src_pdfs` trae también los de cada una)."""
        comp = self.composite
        if comp is None or not comp.pieces:
            return len(self.src_pdfs)
        g0 = min(int(p.grupo) for p in comp.pieces)
        return len({int(p.source) for p in comp.pieces if int(p.grupo) == g0})

    def _preguntar_hermanos(self, elegido, mas, n_base) -> bool:
        """La hoja del editor junta varios PDF (p. ej. North y South) y se eligió uno solo: en la carpeta
        hay otro(s) de la misma utilidad. Se explica qué se encontró y qué pasa con cada respuesta."""
        lista = "\n".join("   • " + os.path.basename(p) for p in mas)
        texto = (_tr("Encontré otro PDF de la misma utilidad en la carpeta.") if len(mas) == 1 else
                 _tr("Encontré otros {n} PDF de la misma utilidad en la carpeta.").format(n=len(mas)))
        detalle = _tr(
            "Elegiste «{pdf}», pero la hoja del editor está armada con {n} PDF (por ejemplo North y South). "
            "Es probable que la utilidad también continúe en:\n\n{lista}\n\n"
            "Si lo incluyes, se buscan las hojas de todos y la utilidad puede cubrir toda la hoja del editor. "
            "Si no, solo se agrega la zona que dibuja el PDF que elegiste.").format(
                pdf=os.path.basename(elegido), n=n_base, lista=lista)
        if not self.isVisible():                          # (sin la ventana en pantalla: la pregunta de siempre)
            r = QtWidgets.QMessageBox.question(self, _tr("Agregar utilidad"), texto + "\n\n" + detalle,
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.Yes)
            return r == QtWidgets.QMessageBox.Yes
        caja = QtWidgets.QMessageBox(self)
        caja.setIcon(QtWidgets.QMessageBox.Question)
        caja.setWindowTitle(_tr("Agregar utilidad"))
        caja.setText(texto)
        caja.setInformativeText(detalle)
        si = caja.addButton(_tr("Incluirlo también") if len(mas) == 1 else _tr("Incluirlos también"),
                            QtWidgets.QMessageBox.AcceptRole)
        caja.addButton(_tr("Solo el que elegí"), QtWidgets.QMessageBox.RejectRole)
        caja.setDefaultButton(si)
        caja.exec()
        return caja.clickedButton() is si

    def _composicion_del_editor(self):
        """La composición de la hoja del editor (una hoja suelta = una pieza entera)."""
        if self.composite is not None and self.composite.pieces:
            return composite_mod.Composite.from_dict(self.composite.to_dict())
        return composite_mod.Composite([composite_mod.Piece(0, int(self.page_idx), [0.0, 0.0, 1.0, 1.0],
                                                            src_scale=float(self.scale))])

    def _calcar_en_fondo(self, editor, nuevas, fuentes_editor, nombres_editor, escala, solo=None, ocupado=None):
        """`hoja_calcada.calcar_trabajo` de las hojas `solo` en el proceso trabajador, con «Cancelar». → dict o
        None. (Al continuar el compositor con hojas marcadas que la búsqueda de fondo aún no ubicó.)"""
        from ui.comun import proceso
        t = proceso.Tarea("hoja.hoja_calcada:calcar_trabajo",
                          (editor.to_dict(), list(fuentes_editor), [e["data"] for e in nuevas],
                           [e["name"] for e in nuevas], float(escala), list(nombres_editor)),
                          dict(solo=[list(k) for k in solo] if solo is not None else None,
                               ocupado=[list(r) for r in (ocupado or ())]))
        out = {}
        lazo = QtCore.QEventLoop()
        ov = _busy_mod.overlay_for(self)

        def etapa(a):
            if a and a[0] == "detalle" and ov.active:
                ov.step(detail=_busy_mod.detalle_de(a[1], a[2], a[3]),
                        done=a[2] if a[3] else None, total=a[3] if a[3] else None, pump=False)
        t.avance.connect(etapa)
        t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
        ov.begin(_tr("Ubicando las hojas elegidas sobre la hoja del editor…"),
                 _tr("Buscando en cada hoja el mismo mapa base (lotes, calles)"), cancel=t.cancelar)
        try:
            proceso.trabajador("principal").enviar(t)
            if not t.hecha:
                lazo.exec()
        finally:
            ov.end()
        err = out.get("e", "")
        if err == "cancelado":
            self._info(_tr("Se dejó de ubicar las hojas elegidas — vuelves a «Componer hoja»."))
            return None
        if err:
            QtWidgets.QMessageBox.warning(self, _tr("Agregar utilidad"), _tr(
                "No se pudo ubicar el PDF sobre la hoja del editor:\n\n{e}").format(
                    e=_tr("La hoja necesita más memoria de la que hay libre en el equipo.") if err == "memoria" else err))
            return None
        return out.get("r")

    def _empezar_agregado(self, editor, nuevas, busqueda) -> bool:
        """Respaldo del editor y «Componer hoja» con las hojas del PDF nuevo, AL INSTANTE: dónde cae cada
        una lo va diciendo `busqueda` (en segundo plano). Al aceptar, cada hoja va a su lugar
        (`_agregando_recolocar`), la hoja se arma y queda junto a la del editor (`_agregado_compuesto`).
        → True si se agregó."""
        from hoja import hoja_calcada
        docs = [fitz.open(stream=e["data"], filetype="pdf") for e in self.src_pdfs]
        try:
            marco = hoja_calcada.marco_de(
                editor, lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height))
        finally:
            for d in docs:
                d.close()
        # SIEMPRE con respaldo (aunque el editor no tenga líneas): cancelar vuelve a SU hoja
        self._empezar_asistente()
        self._soltar_respaldo()
        self._respaldo = respaldo_editor.tomar(self)
        en_editor = list(dict.fromkeys(p.get("layer") for p in self.pipes if p.get("layer")))
        self._agregando = dict(
            editor=editor.to_dict(), marco=list(marco), n_editor=len(self.src_pdfs), escala=float(self.scale),
            busqueda=busqueda, nombres=[e["name"] for e in nuevas], utilidades_editor=en_editor)
        self.src_pdfs = nuevas
        self.composite = None                  # nada elegido: el usuario marca (o «Marcar las N»)
        self.hidden_ocgs_by_source = {}
        self._layer_roles_by_utility = {}
        self._layer_roles_hoja = None
        self._letters_off = set()
        # «agregar OTRA utilidad»: las que ya están en el editor no se marcan (se pueden marcar)
        self._recognition_utilities = tuple(u for u in _recognition.SUPPORTED_UTILITIES if u not in en_editor)             or _recognition.DEFAULT_UTILITIES
        if not self._wizard_sheet_flow(0):
            self._cancelar_asistente(_tr("Agregar utilidad cancelado — el editor queda como estaba."))
            return False
        return True

    def _parar_busqueda_agregar(self):
        """Fuera del modo «agregar»: la búsqueda de fondo ya no sirve."""
        ag = getattr(self, "_agregando", None)
        b = ag.get("busqueda") if isinstance(ag, dict) else None
        if b is not None:
            b.cancelar()

    # ─────────────────────────── en el asistente ───────────────────────────
    def _agregando_recolocar(self, comp, sources):
        """Tras «Componer hoja» en este modo: cada hoja marcada va al lugar que da su mapa base sobre la hoja
        del editor. Lo que la búsqueda de fondo ya ubicó entra con sus piezas calcadas (su área, en su lugar; una
        hoja marcada entera toma esas piezas, sin el cajetín); lo marcado que aún no se ubicó se busca AHORA,
        solo eso. Las hojas que no caen sobre la hoja del editor se quitan con aviso. → hoja, o None (vuelve
        al compositor; el aviso ya se dio)."""
        from hoja import hoja_calcada
        ag = self._agregando
        b = ag["busqueda"]
        escala = float(ag["escala"])
        docs = [fitz.open(stream=e["data"], filetype="pdf") for e in sources]
        try:
            tam = lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height)  # noqa: E731
            pedidas = list(dict.fromkeys((int(p.source), int(p.page)) for p in comp.pieces))
            falta = [k for k in pedidas if k not in b.m]
            completa = b.terminada and not b.cancelada and not b.error
            if falta and not completa:
                b.cancelar()                                  # lo que no se marcó ya no hace falta buscarlo
                ocupado = [tuple(composite_mod.piece_rect(q, tam(q), escala))
                           for k in pedidas if k in b.piezas
                           for q in (composite_mod.Piece.from_dict(d) for d in b.piezas[k])]
                res = self._calcar_en_fondo(composite_mod.Composite.from_dict(ag["editor"]), sources,
                                            b.fuentes_editor, b.nombres_editor, escala, solo=falta, ocupado=ocupado)
                if res is None:
                    return None
                ub = {(int(u["fuente"]), int(u["hoja"])): u["m"] for u in res.get("ubicaciones") or ()}
                for d in (res.get("comp") or {}).get("pieces") or ():
                    k = (int(d["source"]), int(d["page"]))
                    if k in ub:
                        b.poner(k[0], k[1], d, ub[k])
            quedan, quitadas = [], []
            for k in pedidas:
                mias = [p for p in comp.pieces if (int(p.source), int(p.page)) == k]
                if k not in b.m:
                    quitadas += mias
                    continue
                cal = [composite_mod.Piece.from_dict(d) for d in b.piezas.get(k, ())]
                if cal and all(self._pieza_entera(p) or any(self._misma_area(p, q) for q in cal) for p in mias):
                    quedan += cal                             # su área calcada (sin el cajetín), en su lugar
                else:
                    quedan += [hoja_calcada.colocar(composite_mod.Piece.from_dict(p.to_dict()), tam(p), b.m[k],
                                                    escala) for p in mias]
        finally:
            for d in docs:
                d.close()
        if quitadas:
            self.informar(_tr("Agregar utilidad"), _tr(
                "{n} hoja(s) no coinciden con ninguna hoja del editor (su mapa base no está en la hoja) y "
                "no se usan: {lista}.").format(n=len({(p.source, p.page) for p in quitadas}), lista=", ".join(
                    sorted({f"{sources[p.source]['name']} · {p.page + 1}" for p in quitadas}))))
        if not quedan:
            if not quitadas:
                self.informar(_tr("Agregar utilidad"), _tr("Ninguna de las hojas elegidas coincide con la hoja del editor."))
            return None
        nuevo = composite_mod.Composite.from_dict(comp.to_dict())
        nuevo.pieces = quedan
        nuevo.scale_ft_per_pt = escala
        nuevo.marco = [float(v) for v in ag["marco"]]
        return nuevo

    @staticmethod
    def _pieza_entera(p) -> bool:
        return not p.polygon and composite_mod.normalize_clip(p.clip) == [0.0, 0.0, 1.0, 1.0]

    @staticmethod
    def _misma_area(a, b) -> bool:
        ca, cb = composite_mod.normalize_clip(a.clip), composite_mod.normalize_clip(b.clip)
        return list(a.polygon or []) == list(b.polygon or []) and max(abs(x - y) for x, y in zip(ca, cb)) <= 1e-6

    def _agregado_compuesto(self):
        """Tras «Componer hoja» en este modo (la hoja calcada ya es la hoja de trabajo): el editor como estaba, su
        hoja pasa a ser la combinada (solo cambia la imagen de fondo) y se interpreta la hoja calcada para el panel
        «Reconocer». → True, o False si la hoja combinada no se pudo armar (el editor queda como estaba)."""
        import hashlib
        ag = self._agregando
        nuevas, calco, ocultas = self.src_pdfs, self.composite, self.hidden_ocgs_by_source
        ruta, tmp, hoja = self.work_pdf_path, self._tmp_composite, int(self.page_idx)
        firma = hashlib.sha1(repr(("agregado", recognition_cache.composition_signature(calco),
                                   recognition_cache.freeze(self._src_fingerprints(nuevas)), hoja,
                                   tuple(sorted(self.hidden_ocgs or ())))).encode("utf-8")).hexdigest()
        self._tmp_composite = None                        # la hoja calcada queda para interpretar y reconocer
        if self.doc is not None:
            self.doc.close()                              # (se lee en el trabajador, desde su archivo)
            self.doc = None
        r, self._respaldo = self._respaldo, None
        # El editor se redibuja una vez, al final. Mientras la hoja combinada se arma en el proceso la ventana
        # atiende eventos: la copia automática espera (`_importando`) a que tenga su hoja nueva.
        previo, self._importando = getattr(self, "_importando", False), True
        try:
            with self._redibujo_diferido():
                fallo = self._combinar_hojas(r, ag, nuevas, calco, ocultas, [])
        finally:
            self._importando = previo
        if fallo is not None:
            if tmp and os.path.isfile(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            QtWidgets.QMessageBox.warning(self, _tr("Agregar utilidad"),
                _tr("No se pudo armar la hoja con las dos utilidades:\n\n{e}").format(e=fallo))
            self._reponer_respaldo(_tr("Agregar utilidad cancelado — el editor queda como estaba."))
            return False
        self._soltar_respaldo()
        self._rec_guardar_plano()                         # el plano de antes conserva su panel (ventana_reconocer_planos)
        self.reconocer_estado = RE.nuevo()                # …y el nuevo empieza con el suyo
        self._interpretacion, self._resultados_partes, self._cache_partes = None, {}, None
        self._soltar_rec_hoja()
        self._rec_hoja = dict(ruta=ruta, hoja=hoja, firma=firma, tmp=tmp, desde=len(self.src_pdfs) - len(nuevas),
                              grupo=max(p.grupo for p in self.composite.pieces))
        self._dirty = True
        self._info(_tr("«{pdf}» quedó junto a la hoja del editor. Reconoce su utilidad desde el panel "
                       "Reconocer.").format(pdf=", ".join(e["name"] for e in nuevas)))
        self._interpretar_hoja()
        return True

    def _agregado_utilidad(self, ov, utilidad):
        """Una utilidad reconocida en la hoja agregada: nombra su plano de fondo (`ventana_planos`)."""
        comp = self.composite
        if comp is None:
            return
        nombres = dict(comp.utilidades_grupo or {})
        lista = list(nombres.get(ov["grupo"]) or [])
        if utilidad not in lista:
            lista.append(utilidad)
        nombres[ov["grupo"]] = lista
        comp.utilidades_grupo = nombres

    def _combinar_hojas(self, r, ag, nuevas, calco, ocultas, utilidades=()):
        """El editor como estaba (respaldo `r`) y su hoja pasa a ser la combinada: sus piezas + las
        nuevas. → None, o la excepción si la hoja combinada no se pudo armar."""
        from hoja import hoja_calcada
        respaldo_editor.reponer(self, r)                  # hoja, modelo, deshacer… de antes
        self._respaldo = respaldo_editor.tomar(self)      # por si la hoja combinada falla
        editor = composite_mod.Composite.from_dict(ag["editor"])
        n_editor = len(self.src_pdfs)
        comb = hoja_calcada.combinar(editor, calco, n_editor, ag["marco"], ag["escala"])
        # el nombre de cada plano de fondo (`ventana_planos`): las utilidades que trae cada grupo
        nombres = dict(editor.utilidades_grupo or {})
        nombres.setdefault(0, list(ag.get("utilidades_editor") or ()))
        nombres[max(p.grupo for p in comb.pieces)] = list(utilidades)
        comb.utilidades_grupo = {g: v for g, v in nombres.items() if v}
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
        self._soltar_planos()                             # la hoja nueva se ve con todos sus planos
        self.canvas.cambiar_imagen(qimg, escala)
        if self.canvas.nitidez is not None:
            self.canvas.nitidez.fijar(self.canvas.pixmap_item)   # teselas de la hoja NUEVA
        self._update_page_label(); self._refresh_scale_label()
        self._refresh_lists(); self._update_ui(); self._redraw()
