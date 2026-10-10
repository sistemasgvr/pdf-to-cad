"""Edición en bloque, copiar/pegar propiedades y «Revisar y limpiar el dibujo».

Pedido del usuario 2026-10-08 (cliente ferroviario: mapea lo existente, no diseña;
automatizar el modelado): poner familia y diámetro a muchas utilidades del MISMO tipo
de una vez o copiarlos de una a otras (`nucleo.edicion_bloque`), y limpiar antes de
exportar lo que en Civil 3D sale como basura (`nucleo.limpieza`). Clase mezcla de
`Main` (app_window.py), como las demás ventana_*.py.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from nucleo import edicion_bloque, limpieza


class EdicionBloqueMixin:
    # ─────────────────────────── edición en bloque ───────────────────────────
    def _catalogo_para(self, capa):
        """([(id, texto)] familias del catálogo de Civil 3D para ese tipo de utilidad,
        tamanos_de(fid)) — los mismos que el panel de propiedades."""
        from catalogo import civil_catalog as _cc
        from nucleo.model import network_kind
        red = network_kind(capa or "")
        year = self.civil_year
        if not year or red not in ("gravity", "pressure", "conduit"):
            return [], lambda _fid: []
        fams = _cc.pressure_pipes(year) if red == "pressure" else _cc.imperial_pipes(year)

        def tamanos(fid):
            if not fid:
                return []
            return _cc.pressure_pipe_sizes(year, fid) if red == "pressure" else _cc.pipe_sizes(year, fid)
        return [(f["id"], f"{f['pretty']}  [{f['subfolder']}]") for f in fams], tamanos

    def _items_combo(self, cb):
        return [(cb.itemText(i), cb.itemData(i)) for i in range(cb.count())]

    def _mismo_tipo_o_avisar(self, filas, titulo):
        tipos = edicion_bloque.tipos(self.pipes, filas)
        if len(tipos) <= 1:
            return True
        QtWidgets.QMessageBox.information(self, titulo, _tr(
            "Las utilidades seleccionadas son de tipos distintos ({tipos}). Esto se hace solo con "
            "utilidades del mismo tipo: clic derecho → «Seleccionar todas las de tipo …».").format(
                tipos=", ".join(self._tipo(c) for c in tipos)))
        return False

    def editar_en_bloque(self):
        """Familia, tamaño (diámetro), tipo de tubería, material y estado de varias
        utilidades del mismo tipo a la vez."""
        titulo = _tr("Editar en bloque")
        filas = self._selected_pipe_rows()
        if len(filas) < 2:
            QtWidgets.QMessageBox.information(self, titulo, _tr(
                "Selecciona dos o más utilidades del mismo tipo: Ctrl+clic en la lista «Utilidades» o sobre "
                "ellas en el lienzo, o clic derecho → «Seleccionar todas las de tipo …»."))
            return
        if self._mismo_tipo_o_avisar(filas, titulo):
            self._editar_filas(filas, titulo)

    def copiar_propiedades(self):
        """Guarda las propiedades de la utilidad actual para pegarlas en otras."""
        if not (0 <= self.sel_pipe < len(self.pipes)):
            self._info(_tr("Selecciona la utilidad de la que quieres copiar las propiedades."))
            return
        p = self.pipes[self.sel_pipe]
        self._props_copiadas = (p.get("layer") or "", edicion_bloque.valores_de(p), self.sel_pipe + 1)
        self._info(_tr("Propiedades de la utilidad #{n} copiadas: selecciona otras de tipo «{tipo}» y "
                       "elige «Pegar propiedades».").format(n=self.sel_pipe + 1, tipo=self._tipo(p.get("layer"))))

    def pegar_propiedades(self):
        """Pega las propiedades copiadas en las utilidades seleccionadas del MISMO tipo."""
        titulo = _tr("Pegar propiedades")
        copia = getattr(self, "_props_copiadas", None)
        if not copia:
            QtWidgets.QMessageBox.information(self, titulo, _tr(
                "Primero copia las propiedades de una utilidad: clic derecho sobre ella → «Copiar propiedades»."))
            return
        capa, valores, num = copia
        filas = self._selected_pipe_rows()
        destino = [r for r in filas if self.pipes[r].get("layer") == capa]
        if not destino:
            QtWidgets.QMessageBox.information(self, titulo, _tr(
                "Las propiedades copiadas son de una utilidad de tipo «{tipo}»: solo se pegan en utilidades "
                "de ese tipo.").format(tipo=self._tipo(capa)))
            return
        self._editar_filas(destino, _tr("Pegar propiedades de la utilidad #{n}").format(n=num),
                           inicial=valores, saltadas=len(filas) - len(destino))

    def copiar_de_la_primera(self):
        """Selección múltiple: las propiedades de la PRIMERA seleccionada pasan a las demás."""
        filas = self._selected_pipe_rows()
        titulo = _tr("Copiar propiedades")
        if len(filas) < 2 or not self._mismo_tipo_o_avisar(filas, titulo):
            return
        base = next((r for r in getattr(self, "_orden_sel", []) if r in filas), filas[0])
        resto = [r for r in filas if r != base]
        self._editar_filas(resto, _tr("Copiar propiedades de la utilidad #{n}").format(n=base + 1),
                           inicial=edicion_bloque.valores_de(self.pipes[base]))

    def _editar_filas(self, filas, titulo, inicial=None, saltadas=0):
        from ui.dialogos.edicion_bloque_dialog import EdicionBloqueDialog
        capa = self.pipes[filas[0]].get("layer") or ""
        familias, tamanos = self._catalogo_para(capa)
        con_db = [r for r in filas if self._duct_bank_for_pipe(r) is not None]
        dlg = EdicionBloqueDialog(
            self, titulo, len(filas), self._tipo(capa), familias, tamanos,
            edicion_bloque.familia_comun(self.pipes, filas),
            self._items_combo(self.prop_material), self._items_combo(self.prop_nettype),
            inicial=inicial, datos=(inicial or {}).get("datos"), con_bancoducto=len(con_db), saltadas=saltadas,
            tipos=normas_catalogo.tipos_de(self.normas_cat, capa), con_amperaje=(capa == "ELECTRICO"))
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        cambios = dlg.cambios()
        if not cambios:
            return
        self._push()
        n = edicion_bloque.aplicar(self.pipes, filas, cambios, sin_familia=con_db)
        self._refresh_lists()
        self._reselect_pipes(filas)
        if 0 <= self.sel_pipe < len(self.pipes):
            self._no_center = True
            try:
                self._sel_pipe(self.sel_pipe)          # el panel muestra los valores nuevos
            finally:
                self._no_center = False
        self._redraw()
        self._info(_tr("Se actualizaron {n} de {total} utilidades.").format(n=n, total=len(filas)))

    # ─────────────────────────── revisar y limpiar ───────────────────────────
    def _protegidas_limpieza(self):
        """Utilidades con bancoducto o conexión vertical: nunca se borran solas."""
        out = {i for db in getattr(self, "duct_banks", []) or [] for i in db.assigned()}
        for c in getattr(self, "cross_connections", None) or []:
            for k in ("pipe_a", "pipe_b"):
                try:
                    out.add(int(c.get(k, -1)))
                except (TypeError, ValueError):
                    pass
        return out

    def _ir_a_lugar(self, x, y, fila):
        """Lleva el lienzo a (x, y) con zoom cercano y selecciona la utilidad."""
        if 0 <= fila < len(self.pipes):
            self._no_center = True
            try:
                self._show_tab(TAB_PIPE)
                self.pipe_list.clearSelection()
                self.pipe_list.setCurrentRow(fila)
            finally:
                self._no_center = False
        r = 60.0
        self.canvas.fitInView(QtCore.QRectF(x - r, y - r, 2 * r, 2 * r), QtCore.Qt.KeepAspectRatio)
        self.canvas.centerOn(x, y)
        self._redraw()

    def revisar_dibujo(self, exportando=False):
        """Herramientas → «Revisar y limpiar el dibujo…» y, antes de exportar, solo si
        hay algo que arreglar. Devuelve False si el usuario cancela la exportación."""
        from ui.dialogos.limpieza_dialog import LimpiezaDialog
        titulo = _tr("Revisar y limpiar el dibujo")
        ft = (self.scale / self.zoom) if self.scale and self.zoom else 0.0
        if not self.pipes or ft <= 0:
            if not exportando:
                QtWidgets.QMessageBox.information(self, titulo, _tr(
                    "No hay utilidades dibujadas (o falta la escala de la hoja)."))
            return True
        protegidas = self._protegidas_limpieza()
        # Al exportar, los tramos diminutos no se preguntan: el DXF los corrige solo
        # (dxf_export._sin_tramos_diminutos). Solo lo que cambia el dibujo de verdad.
        tipos = ("punta", "corta", "duplicada") if exportando else limpieza.TIPOS
        previa = limpieza.limpiar(copy.deepcopy(self.pipes), copy.deepcopy(self.structures), ft,
                                  tipos=tipos, protegidas=protegidas)
        if exportando and not previa.arreglos:
            return True
        if not previa.cambios:
            QtWidgets.QMessageBox.information(self, titulo, _tr("Todo en orden: no hay nada que limpiar."))
            return True
        dlg = LimpiezaDialog(self, previa, lambda i: f"#{i + 1} {self._etq(self.pipes[i])}",
                             self._ir_a_lugar, exportando=exportando)
        dlg.exec()
        if dlg.accion == "cancelar":
            return not exportando
        if dlg.accion == "arreglar":
            self._push()
            hecho = limpieza.limpiar(self.pipes, self.structures, ft, tipos=dlg.tipos(), protegidas=protegidas)
            if hecho.borrar:
                self._delete_pipes(hecho.borrar)
            self._refresh_lists()
            self._redraw()
            self._info(_tr("Dibujo limpio: {n} arreglo(s).").format(n=len(hecho.arreglos)))
        return True
