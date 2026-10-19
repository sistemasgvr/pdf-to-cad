"""composite_choice.py — «la hoja elegida» del compositor (mezcla de `CompositeDialog`).

Pedido del usuario 2026-10-05: elegía la hoja en «Origen», pulsaba «Siguiente» y la
hoja compuesta quedaba vacía («le doy continuar y no seleccioné nada»). Pedido
2026-10-16: elegía la hoja 1, luego la 2, y la 2 REEMPLAZABA a la 1. Pedido
2026-10-19 («para evitar problemas y confusiones»): una CASILLA por hoja en «Origen»;
las marcadas son la hoja compuesta. Ahora:

  · Al abrir sin nada, la hoja a la vista ya está marcada (`_choose_provisional`): así
    «Continuar» nunca lleva a «vacío». Nada la cambia sola: el texto de arriba dice que
    vino marcada (`_provisional` = cómo quedó, solo para ese texto) y se desmarca a mano.
  · La casilla de una hoja (`_toggle_page`; también Espacio / Enter / Ctrl+clic) la
    SUMA entera a la hoja compuesta, además de las que ya están, y la deja a la vista en
    edición (`_use_page`), o la QUITA (`_remove_page`; si tenía un área tomada, pregunta).
    Una casilla solo cambia SU hoja.
  · Clic en la miniatura, flechas o ‹ › en «Área a tomar» solo MUESTRAN la hoja; si ya
    está en la hoja compuesta queda en edición (`_select_page_piece`); si no, el aviso
    ofrece «Hoja completa» o, con una pieza, «Usar solo esta hoja»
    (`_use_only_this_sheet`). «Tomar área de esta hoja» y el enlace del pie la suman
    (`_pick_page`).
  · La pieza de la hoja a la vista queda EN EDICIÓN: un área marcada sobre su hoja (o
    sus esquinas movidas) la recorta al momento (la maquinaria de siempre:
    `_apply_crop_edit`) y «Hoja completa» la vuelve a la hoja entera
    (`_set_piece_area`). La hoja entera se ve sin tinte, solo borde y asas (teñirla
    toda de naranja confundía); el texto de arriba dice qué está pasando
    (`_refresh_area_mode`).

Mezcla de `CompositeDialog`, como `composite_source_page`. Requiere de la clase: `self.comp`,
`self.view`, `self.crop`, `self.docs`, `self.sources`, `self._cur_source`,
`self._cur_page`, `self._editing`, `self._provisional`, `self._crop_timer`,
`self._syncing_crop`, `self._syncing_widgets`, botones `btn_take`/`btn_take_full`/
`btn_new`, `lbl_mode`, `spn_src_scale` y los métodos `_detected_scale`,
`_refresh_scale_combo`, `_refresh_summary`, `_on_pieces_changed`, `_on_piece_selected`,
`_pieces_on_page`, `_take`, `_apply_crop_edit`, `_area_untaken`, `_has_area`,
`_show_piece_in_area_panel` y `lst_pages`.
"""
from __future__ import annotations

from PySide6 import QtWidgets

from hoja import composite as C
from traduccion.i18n import t as _tr


class ChosenSheetMixin:
    def _simple(self) -> bool:
        """¿La hoja compuesta es solo «la hoja elegida»? (vacía o UNA hoja entera)"""
        return not self.comp.pieces or self.comp.is_single_full_page()

    @staticmethod
    def _is_full(p: "C.Piece") -> bool:
        return not p.polygon and C.normalize_clip(p.clip) == [0.0, 0.0, 1.0, 1.0]

    def _provisional_now(self) -> bool:
        """¿La hoja compuesta es la hoja que puso el compositor, tal cual (nadie la eligió,
        recortó, giró ni movió)? Entonces «Origen» dice que vino marcada sola."""
        return (self._provisional is not None and self.comp.is_single_full_page()
                and self.comp.pieces[0].to_dict() == self._provisional)

    def _choose_provisional(self):
        """La hoja a la vista pasa a ser la hoja compuesta sin que el usuario la eligiera
        (al abrir sin nada): su casilla viene marcada."""
        self._choose_page()
        self._provisional = self.comp.pieces[0].to_dict() if self.comp.is_single_full_page() else None
        self._refresh_source_selection()         # el texto de arriba dice que se puede cambiar

    def _editing_here(self) -> bool:
        """¿«Área a tomar» edita la pieza de la hoja que se ve?"""
        idx = self._editing
        return (0 <= idx < len(self.comp.pieces)
                and (self.comp.pieces[idx].source, self.comp.pieces[idx].page) == (self._cur_source, self._cur_page))

    def _choose_page(self, _row: int = -1):
        """La hoja a la vista pasa a ser LA hoja compuesta, entera y EN EDICIÓN (un área
        marcada la recorta). Solo mientras la hoja compuesta sea vacía o una hoja entera:
        al abrir, la primera hoja marcada, o «Usar solo esta hoja». Con trabajo de verdad
        (un área, varias piezas) no se toca nada."""
        if not self._simple() or not self.docs:
            return
        src, page = self._cur_source, self._cur_page
        if self.comp.pieces:
            p = self.comp.pieces[0]
            if (p.source, p.page) == (src, page):
                if self.view.selected_index() != 0:
                    self.view.select(0)
                return
            p.source, p.page = src, page
            p.clip, p.covers, p.polygon = [0.0, 0.0, 1.0, 1.0], {}, []
            p.x = p.y = p.rotation = 0.0
        else:
            p = C.Piece(src, page, [0.0, 0.0, 1.0, 1.0])
            self.comp.pieces.append(p)
        p.src_scale = self._detected_scale(src, page)
        p.label = f"{self.sources[src]['name']} · {page + 1}"
        self.comp.scale_ft_per_pt = None         # la escala es la de la hoja elegida
        self._editing = -1                       # que la selección la vuelva a cargar
        self._refresh_scale_combo()
        self.view.rebuild(keep_selection=0)
        self._refresh_summary()
        self._on_pieces_changed()

    def _pick_page(self, _row: int = -1):
        """«Tomar área de esta hoja» o el enlace «Usar la hoja N» del pie: la hoja a la
        vista se SUMA a la hoja compuesta, entera y en edición, además de las que ya
        están (pedido del usuario 2026-10-16: la 2 reemplazaba a la 1); su casilla queda
        marcada. Si ya está, se elige su pieza."""
        if not self.docs:
            return
        self._provisional = None
        if self._pieces_on_page(self._cur_source, self._cur_page):
            self._select_page_piece()
        elif not self.comp.pieces:
            self._choose_page()
        else:
            self._take(full=True)
        self._refresh_source_selection()

    def _select_page_piece(self):
        """La hoja a la vista ya está en la hoja compuesta: su pieza queda en edición
        («Área a tomar» la recorta). Si no está, nada."""
        mine = [i for i, p in enumerate(self.comp.pieces)
                if (p.source, p.page) == (self._cur_source, self._cur_page)]
        if mine and self.view.selected_index() not in mine:
            self.view.select(mine[0])

    def _view_page(self, _row: int = -1):
        """Clic en la miniatura de una hoja: solo VERLA (pedido 2026-10-19: mirar y
        elegir eran lo mismo); si está en la hoja compuesta, su pieza queda en edición."""
        self._select_page_piece()
        self._refresh_source_selection()

    def _toggle_page(self, row: int):
        """Casilla de la hoja `row` del PDF a la vista (clic en ella, Espacio, Enter o
        Ctrl+clic): marcada = está en la hoja compuesta. Solo cambia ESA hoja."""
        if not self.docs or not 0 <= row < self.docs[self._cur_source].page_count:
            return
        if self._pieces_on_page(self._cur_source, row):
            self._remove_page(row)
        else:
            self._use_page(row)

    def _use_page(self, row: int):
        """Marcar la casilla: la hoja se SUMA entera y queda a la vista, en edición (un
        área marcada en «Área a tomar» la recorta)."""
        if row != self._cur_page:
            self.lst_pages.setCurrentRow(row)        # verla (dispara _on_page_changed)
        self._pick_page()

    def _remove_page(self, row: int = -1):
        """Desmarcar la casilla de la hoja `row` (por defecto la que está a la vista):
        salen sus piezas. Si tenía un área tomada (pieza recortada), se pregunta antes:
        es trabajo que se pierde con un clic."""
        src, page = self._cur_source, (self._cur_page if row < 0 else row)
        mine = [p for p in self.comp.pieces if (p.source, p.page) == (src, page)]
        if not mine:
            return
        if any(not self._is_full(p) for p in mine) and not self._confirm_remove_page(page):
            return                                   # la casilla sigue marcada
        self._provisional = None
        self.comp.pieces[:] = [p for p in self.comp.pieces if (p.source, p.page) != (src, page)]
        self._refresh_scale_combo()
        self.view.rebuild()
        self._refresh_summary()
        self._on_piece_selected(-1)
        self._select_page_piece()                    # la hoja a la vista, si sigue, en edición
        self._on_pieces_changed()

    def _confirm_remove_page(self, page: int) -> bool:
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(_tr("Desmarcar la hoja"))
        box.setText(_tr("La hoja {n} tiene un área tomada.").format(n=page + 1))
        box.setInformativeText(_tr("Si la desmarcas, sale de la hoja compuesta y se pierde esa área."))
        b_yes = box.addButton(_tr("Desmarcarla"), QtWidgets.QMessageBox.DestructiveRole)
        b_back = box.addButton(_tr("Volver"), QtWidgets.QMessageBox.RejectRole)
        b_back.setProperty("secondary", True)
        for b in box.buttons():
            b.style().unpolish(b); b.style().polish(b)
        box.setDefaultButton(b_back)
        box.setEscapeButton(b_back)
        box.exec()
        return box.clickedButton() is b_yes

    def _use_only_this_sheet(self):
        """La hoja compuesta pasa a ser SOLO la hoja a la vista (con el área marcada,
        si la hay). Lo ofrecen el aviso de hoja sin tomar y «Continuar», con una pieza."""
        had_area = self._area_untaken()
        self._provisional = None
        self.comp.pieces.clear()
        self.comp.scale_ft_per_pt = None         # la escala pasa a ser la de la hoja nueva
        self._editing = -1
        if had_area:
            self._take(full=False)
        else:
            self._choose_page()

    def _set_piece_area(self, idx: int, full: bool):
        """«Tomar» sobre la pieza que se edita: «Hoja completa» la vuelve a la hoja
        entera; un área marcada la recorta (igual que al ajustar el rectángulo)."""
        self._crop_timer.stop()
        if not full:
            self._apply_crop_edit()
            return
        p = self.comp.pieces[idx]
        if self._is_full(p) and not p.covers:
            return
        self._provisional = None
        p.clip, p.covers, p.polygon = [0.0, 0.0, 1.0, 1.0], {}, []
        self._syncing_crop = True
        try:
            self.crop.set_selection(self.crop._page_rect)      # la hoja entera, sin tinte
        finally:
            self._syncing_crop = False
        self.view.refresh_piece(idx, rerender=True)
        self.view.refresh_overlay()
        self._refresh_summary()
        self._refresh_area_mode()
        self._on_pieces_changed()

    def _on_crop_drag_done(self):
        """Un clic suelto (sin área) mientras se edita una pieza: vuelve a mostrar la
        suya (antes el rectángulo desaparecía y la pieza seguía con su área)."""
        if self._editing_here() and not self._has_area():
            self._show_piece_in_area_panel(self._editing)

    def _on_src_scale_edited(self, value: float):
        """La escala junto a «Tomar» es la de la pieza de esta hoja si se edita."""
        if not self._editing_here() or self._syncing_widgets:
            return
        self.comp.pieces[self._editing].src_scale = float(value) / 72.0
        if len(self.comp.pieces) == 1:
            self.comp.scale_ft_per_pt = None
        self._refresh_scale_combo()
        self.view.refresh_all()
        self._refresh_summary()

    def _refresh_area_mode(self):
        """Texto y botones de «Área a tomar» según lo que hace el rectángulo: recortar
        la pieza de esta hoja (entera o con un área) o marcar una pieza nueva."""
        idx = self._editing
        manual = self.comp.manual
        if not 0 <= idx < len(self.comp.pieces):
            self.lbl_mode.setText(_tr("Arrastra un área y mueve cada esquina para seguir el borde inclinado del plano.")
                                  if manual else
                                  _tr("Arrastra un rectángulo sobre el plano; esquinas y lados se ajustan."))
            self.btn_take_full.setToolTip(_tr("Agregar la hoja entera como una pieza"))
            self.btn_new.hide(); self.btn_take.show(); self.btn_take_full.show()
            return
        p = self.comp.pieces[idx]
        full = self._is_full(p)
        if full:
            text = _tr("La hoja {n} entera está en la hoja compuesta. Si solo necesitas una parte, "
                       "arrastra un área sobre el plano o mueve las esquinas: la hoja compuesta se "
                       "actualiza sola.").format(n=p.page + 1)
        elif len(self.comp.pieces) == 1:
            text = _tr("La hoja compuesta usa el área marcada de la hoja {n}. Ajústala, o pulsa «Hoja "
                       "completa» para volver a usar toda la hoja.").format(n=p.page + 1)
        elif manual:
            text = _tr("Ajusta las cuatro esquinas; la pieza seleccionada se actualiza sola.")
        else:
            text = _tr("Editando el área de la pieza {n} ({name}). Ajusta el rectángulo; "
                       "la pieza se actualiza sola.").format(n=idx + 1, name=p.label or "")
        self.lbl_mode.setText(text)
        self.btn_take_full.setToolTip(_tr("Volver a usar la hoja entera en esta pieza"))
        self.btn_take.hide()
        self.btn_take_full.setVisible(not full)
        # «Nueva pieza» (otra área de esta hoja) no cuando la hoja elegida está entera:
        # ahí basta con marcar el área
        self.btn_new.setVisible(not (full and len(self.comp.pieces) == 1))
