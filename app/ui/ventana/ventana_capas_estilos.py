"""«Capas y estilos…» del panel «Reconocer»: todo lo de «Capas de la hoja» (ver, resaltar y elegir capas o estilos,
asignar estilos en hojas sin capas, roles, letras, leyenda, escala) como vista del CENTRO de la ventana (plan
2026-11-16, «reconocimiento desde el editor», Tarea 8).

  · `abrir_capas_estilos(parte)` arma el diálogo de siempre en modo editor (`layer_dialog_editor`) sobre la hoja del
    editor, abierto en la utilidad de la fila, y lo incrusta en el centro (`incrustar_vista`/`mostrar_vista`, como
    Normativas); sin la ventana a la vista, se abre como diálogo. Con la interpretación de la hoja no relee la hoja.
  · «Aplicar» = `_aplicar_capas_elegidas` (lo MISMO que hace el asistente con lo elegido en «Capas de la hoja»), la
    imagen del plano con las capas nuevas SIN recargar la hoja (lo dibujado queda) y las filas al día: bloqueadas o
    desbloqueadas (`reconocer_estado.de_interpretacion`, las reconocidas se conservan) y las reconocidas cuyas capas,
    roles, letras o escala cambiaron, «desactualizadas» (`marcar_cambios` con la firma de cada parte).
  · Cancelar o cerrar: nada cambia (el diálogo repone las capas del documento).
"""
from PySide6 import QtCore, QtWidgets

from nucleo import reconocer_estado as RE
from traduccion.i18n import t as _tr


class CapasEstilosMixin:
    _capas_estilos_dlg = None

    def abrir_capas_estilos(self, parte=None):
        """«Capas y estilos…» (de una fila: `parte`; general: None)."""
        dlg = self._capas_estilos_dlg
        if dlg is not None:                                     # ya abierta: a la vista, en esa utilidad
            dlg.enfocar_parte(parte)
            if not self.mostrar_vista(dlg):
                dlg.raise_()
            return
        if not getattr(self, "doc", None) or self.canvas.pixmap_item is None:
            self.informar(_tr("Capas y estilos"), _tr("Abre primero un PDF vectorial."))
            return
        from ui.asistente import layer_dialog_editor as LE
        from ui.comun import fondo_trabajo
        # la hoja que se reconoce: con una utilidad agregada, la de su PDF (no la combinada: ventana_interpretar)
        doc, hoja, propio = self._doc_de_lectura()
        if doc is None:
            self.informar(_tr("Capas y estilos"), _tr("No se pudo armar la hoja de la utilidad agregada."))
            return
        try:
            dlg = LE.dialogo_editor(
                self, doc, hoja, interp=self._interpretacion_vigente(),
                en_proceso=fondo_trabajo.conviene(self.composite), layout=self._layout_minimapa(),
                recognition_utilities=self._recognition_utilities, letters_off=self._letters_off,
                roles_by_utility=self._roles_de_la_hoja(self.page_idx), scale_ft_per_pt=self._scale_editable(),
                legend_sources=self._legend_sources(), legend_cache=self._legend_cache)
        except Exception:
            if propio:
                doc.close()
            raise
        if dlg is None:
            if propio:
                doc.close()
            self.informar(_tr("Capas y estilos"), _tr("La hoja no tiene capas ni estilos de trazo que elegir."))
            return
        dlg._doc_propio = doc if propio else None
        dlg.enfocar_parte(parte)
        self._capas_estilos_dlg = dlg
        dlg.finished.connect(lambda codigo, d=dlg: self._capas_estilos_cerrada(d, codigo))
        if self.incrustar_vista(dlg):
            self.mostrar_vista(dlg)
        else:
            dlg.exec()

    def _interpretacion_vigente(self):
        """La interpretación de la hoja si es de ESTA lectura (sin firma: la de la hoja a la vista)."""
        interp = getattr(self, "_interpretacion", None)
        if not interp:
            return None
        firma = interp.get("firma")
        return interp if not firma or firma == self._firma_lectura() else None

    def _capas_estilos_cerrada(self, dlg, codigo):
        if self._capas_estilos_dlg is dlg:
            self._capas_estilos_dlg = None
        centro = getattr(self, "centro", None)
        if centro is not None and centro.indexOf(dlg) >= 0:
            centro.removeWidget(dlg)
        if hasattr(self, "mostrar_plano"):
            self.mostrar_plano()                                # de vuelta al plano, siempre
        if codigo == QtWidgets.QDialog.Accepted:
            from ui.asistente import layer_dialog_editor as LE
            self._capas_estilos_aplicar(LE.resultado(dlg))
        dlg.soltar_vivo()
        propio = getattr(dlg, "_doc_propio", None)       # la hoja de la utilidad agregada, abierta solo para esto
        if propio is not None:
            dlg.destroyed.connect(lambda *_a, d=propio: d.close())
        QtCore.QTimer.singleShot(0, dlg.deleteLater)

    def _capas_estilos_aplicar(self, chosen):
        """Lo elegido en «Capas y estilos…» a la ventana y a las filas del panel."""
        from hoja import pdf_layers
        antes = (sorted(self.hidden_ocgs or ()), self._scale_override)
        if len(chosen) > 5 and chosen[5] and not self._confirmar_escala(chosen[5]):
            chosen = tuple(chosen[:5]) + (None,) + tuple(chosen[6:])        # la escala de antes queda
        if getattr(self, "_rec_hoja", None) is not None:   # la hoja del PDF agregado: la del editor no cambia
            chosen = (chosen[0], self.page_idx) + tuple(chosen[2:])
        self._aplicar_capas_elegidas(chosen, utilidades=False)
        if sorted(self.hidden_ocgs or ()) != antes[0]:
            pdf_layers.set_hidden(self.doc, list(self.hidden_ocgs))
            self._imagen_con_capas()
        if self._scale_override != antes[1] and self._scale_override:
            self.scale = float(self._scale_override)
            if hasattr(self, "_refresh_scale_label"):
                self._refresh_scale_label()
        self._dirty = True
        e = self._rec_estado()
        interp = self._interpretacion_vigente()
        if interp:
            if e.firma_hoja is None:              # la misma hoja: lo reconocido se conserva
                e.firma_hoja = self._firma_lectura()
            RE.de_interpretacion(e, interp, e.firma_hoja, hidden=self.hidden_ocgs,
                                 roles_by_utility=self._roles_de_la_hoja(self.page_idx))
        RE.marcar_cambios(e, {p: self._firma_parte_actual(p) for p in RE.PARTES})
        self._refrescar_panel_reconocer()

    def _confirmar_escala(self, ft_per_pt) -> bool:
        """¿Cambiar la escala de la hoja? Con utilidades en el editor los largos dibujados cambian: se pregunta y por
        defecto queda la de antes (sin la ventana a la vista, también)."""
        actual = float(self.scale or 0.0)
        if not self.pipes or abs(float(ft_per_pt) - actual) <= 1e-12 * max(1.0, abs(actual)):
            return True
        if not self.isVisible():
            return False
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(_tr("Cambiar la escala"))
        box.setText(_tr("¿Cambiar la escala de la hoja? Ya hay utilidades en el plano."))
        box.setInformativeText(_tr("Con otra escala cambian los largos y las medidas en pies de lo que ya está "
                                   "dibujado."))
        b_si = box.addButton(_tr("Cambiar la escala"), QtWidgets.QMessageBox.DestructiveRole)
        b_no = box.addButton(_tr("Dejar la escala de antes"), QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(b_no)
        box.exec()
        return box.clickedButton() is b_si

    def _imagen_con_capas(self):
        """La imagen del plano con las capas de ahora, sin recargar la hoja (lo dibujado y el deshacer quedan)."""
        qimg, gris, escala, _ancho, _alto = self._fondo_de(self.doc[self.page_idx])
        self.gray = gris
        self.canvas.cambiar_imagen(qimg, escala)
        if self.canvas.nitidez is not None:
            self.canvas.nitidez.fijar(self.canvas.pixmap_item)

    def _aplicar_capas_elegidas(self, chosen, utilidades=True):
        """Lo elegido en «Capas de la hoja» (`choose_sheet_layers(include_roles=True)`) a la ventana: capas ocultas
        (también en los PDF de origen), utilidades (asistente), letras, roles por utilidad y escala calibrada. Lo usan
        el asistente y «Capas y estilos…». Devuelve la hoja elegida."""
        hidden, page_idx, utils, letters_off = chosen[:4]
        if utilidades:
            self._recognition_utilities = utils
        self._letters_off = set(letters_off)
        if self.composite is not None and self.composite.is_single_full_page():
            self.composite.pieces[0].page = page_idx
        self.hidden_ocgs = list(hidden)
        compuesta_al_dia = (getattr(self, "_paso_compuesta", None) is not None and self._paso_compuesta
                            == self._firma_compuesta(self.composite, self.src_pdfs, self.hidden_ocgs_by_source))
        self._sync_hidden_to_sources(hidden)
        if compuesta_al_dia:
            # la hoja ya armada tiene ahora estas capas apagadas: volver al compositor sin
            # cambiarla sigue sin rearmarla
            self._paso_compuesta = self._firma_compuesta(self.composite, self.src_pdfs, self.hidden_ocgs_by_source)
        # Los roles (qué capas son líneas / bóvedas) se asignan solos por
        # nombre y se muestran en el preview; «Ajustar capas…» los cambia.
        self._layer_roles_by_utility = chosen[4] if len(chosen) > 4 else {}
        self._layer_roles_hoja = self._clave_hoja(page_idx)
        if len(chosen) > 5 and chosen[5]:
            self._calibrated_scale(chosen[5])          # «Escala» de «Capas de la hoja»
        return page_idx
