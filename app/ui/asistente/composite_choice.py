"""composite_choice.py — «la hoja elegida» del compositor (mezcla de `CompositeDialog`).

Pedido del usuario 2026-10-05: elegía la hoja en «Origen», pulsaba «Siguiente» y la
hoja compuesta quedaba vacía («le doy continuar y no seleccioné nada»). Ahora:

  · Mientras la hoja compuesta sea solo «la hoja elegida» (vacía o UNA hoja entera,
    `_simple`), elegir una hoja —clic o flechas en «Origen», ‹ › en «Área a tomar»,
    la hoja con que se abre— la pone como hoja compuesta, entera (`_choose_page`).
  · Esa pieza queda EN EDICIÓN: un área marcada sobre su hoja (o sus esquinas
    movidas) la recorta al momento (la maquinaria de siempre: `_apply_crop_edit`) y
    «Hoja completa» la vuelve a la hoja entera (`_set_piece_area`). La hoja entera se
    ve sin tinte, solo borde y asas (teñirla toda de naranja confundía); el texto de
    arriba dice qué está pasando (`_refresh_area_mode`).
  · Con trabajo de verdad (un área tomada, varias piezas) elegir otra hoja solo la
    muestra: se agrega con «Tomar área», «Hoja completa» o Ctrl+clic en «Origen»
    (`_add_sheet`); con una sola pieza, el aviso ofrece «Usar solo esta hoja»
    (`_use_only_this_sheet`).

Mezcla de `CompositeDialog`, como `composite_source_page`. Requiere de la clase: `self.comp`,
`self.view`, `self.crop`, `self.docs`, `self.sources`, `self._cur_source`,
`self._cur_page`, `self._editing`, `self._crop_timer`, `self._syncing_crop`,
`self._syncing_widgets`, botones `btn_take`/`btn_take_full`/`btn_new`, `lbl_mode`,
`spn_src_scale` y los métodos `_detected_scale`, `_refresh_scale_combo`,
`_refresh_summary`, `_on_pieces_changed`, `_pieces_on_page`, `_take`,
`_apply_crop_edit`, `_area_untaken`, `_has_area` y `_show_piece_in_area_panel`.
"""
from __future__ import annotations

from hoja import composite as C
from traduccion.i18n import t as _tr


class ChosenSheetMixin:
    def _simple(self) -> bool:
        """¿La hoja compuesta es solo «la hoja elegida»? (vacía o UNA hoja entera)"""
        return not self.comp.pieces or self.comp.is_single_full_page()

    @staticmethod
    def _is_full(p: "C.Piece") -> bool:
        return not p.polygon and C.normalize_clip(p.clip) == [0.0, 0.0, 1.0, 1.0]

    def _editing_here(self) -> bool:
        """¿«Área a tomar» edita la pieza de la hoja que se ve?"""
        idx = self._editing
        return (0 <= idx < len(self.comp.pieces)
                and (self.comp.pieces[idx].source, self.comp.pieces[idx].page) == (self._cur_source, self._cur_page))

    def _choose_page(self, _row: int = -1):
        """El usuario ELIGIÓ la hoja a la vista (clic o flechas en «Origen», ‹ › en «Área
        a tomar»). Mientras la hoja compuesta sea solo la hoja elegida, esa hoja pasa a
        ser la hoja compuesta, entera y EN EDICIÓN (un área marcada la recorta). Con
        trabajo de verdad (un área, varias piezas) no se toca nada."""
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

    def _add_sheet(self, _row: int = -1):
        """Ctrl+clic en «Origen»: la hoja se AGREGA entera, además de lo ya tomado."""
        if not self.comp.pieces:
            self._choose_page()
        elif not self._pieces_on_page(self._cur_source, self._cur_page):
            self._take(full=True)

    def _use_only_this_sheet(self):
        """La hoja compuesta pasa a ser SOLO la hoja a la vista (con el área marcada,
        si la hay). Lo ofrecen el aviso de hoja sin tomar y «Continuar», con una pieza."""
        had_area = self._area_untaken()
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
