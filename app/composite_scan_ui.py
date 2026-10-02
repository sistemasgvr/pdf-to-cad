"""composite_scan_ui.py — herramientas de «Hoja compuesta» para escaneos.

Mezcla (`ScanToolsMixin`) de `CompositeDialog`: arma el grupo de guías de la
barra única del panel 3 y atiende sus acciones. Rediseño pedido por el usuario
(2026-10-02): una sola fila, sin botones repetidos, y herramientas precisas.

    Regla ▾   Transportador │ Medir   Enderezar │ Fundir bordes

  - Regla ▾: botón dividido. Clic = mostrar/ocultar; ▾ = bloquear, girar 90°,
    traer a la vista y sus medidas (antes eran dos botones).
  - Transportador: imán a 0°/90°, Ctrl fino, Shift 15°, doble clic = 0°.
  - Medir: dos clics → pies y rumbo; si caen en una pieza, «Calibrar escala…»
    corrige la escala de su hoja con una distancia conocida.
  - Enderezar: dos clics sobre una línea → la pieza gira al eje más cercano
    (horizontal o vertical, sin casilla «Vertical») alrededor del medio de la
    línea, que no se mueve.
  - Fundir bordes: las piezas se combinan en modo oscurecer (vista y PDF): el
    papel de una pieza no tapa la tinta de la otra, así que se superponen un
    poco y la costura no deja corte ni franja blanca.

Las indicaciones de cada herramienta y el resultado de la medida van en la
línea de estado bajo la hoja (`lbl_status`), no en filas de texto encima.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtWidgets

import composite as C
import composite_scan as CS
from i18n import t as _tr
from icons import icon as _icon
import theme as _theme


def _split_tool(btn: QtWidgets.QToolButton) -> QtWidgets.QMenu:
    """Convierte un botón conmutable en botón dividido con menú de opciones."""
    menu = QtWidgets.QMenu(btn)
    menu.setToolTipsVisible(True)
    btn.setMenu(menu)
    btn.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
    return menu


class ScanToolsMixin:
    """Requiere de la clase: `self.view` (CompositeView), `self.comp`,
    `self.lbl_status`, `self.btn_calibrate`, `_sync_piece_widgets`,
    `_refresh_summary`, `_refresh_scale_combo`, y los helpers `_tool`,
    `_spin`, `_field_action`, `_check_action` que recibe `build_scan_tools`."""

    # ── barra ───────────────────────────────────────────────────────────
    def build_scan_tools(self, bar, tool, spin, field_action, check_action):
        view = self.view
        self.btn_rule = tool("mdi:ruler", _tr("Regla"), _tr(
            "Regla graduada en pies sobre la hoja. Su borde inferior es la guía para alinear; "
            "el punto verde del extremo la gira (imán a 0° y 90°)."), checkable=True)
        rmenu = _split_tool(self.btn_rule)
        self.ruler_lock = check_action(rmenu, _tr("Bloquear regla"),
            _tr("Dejar la regla fija y permitir mover las hojas por debajo"),
            checked=view.alignment_ruler.locked)
        self.ruler_lock.setIcon(_icon("mdi:lock-outline"))
        self.ruler_lock.toggled.connect(lambda on: view.alignment_ruler.configure(locked=on))
        rmenu.addAction(_icon("mdi:rotate-left"), _tr("Girar 90°"), self._ruler_turn)
        rmenu.addAction(_icon("mdi:crosshairs-gps"), _tr("Traer a la vista"), self._ruler_to_view)
        rmenu.addSeparator()
        self.ruler_fields = {}
        for key, label, lo, hi in (("length", _tr("Largo"), 10, 1000000),
                ("width", _tr("Ancho"), 5, 1000000), ("x", "X", -1000000, 1000000),
                ("y", "Y", -1000000, 1000000), ("angle", _tr("Ángulo"), -360, 360)):
            field = spin("", "°" if key == "angle" else " pt", lo, hi, 2, 1)
            self.ruler_fields[key] = field
            field.valueChanged.connect(lambda value, key=key: self._configure_ruler(key, value))
            field_action(rmenu, label, field)
        rmenu.aboutToShow.connect(self._sync_ruler_fields)
        self.btn_rule.toggled.connect(self._on_rule_toggled)
        self.btn_rule.setChecked(view.alignment_ruler.isVisible())
        bar.add(self.btn_rule, compact=True)

        self.btn_protractor = tool("mdi:angle-acute", _tr("Transportador"), _tr(
            "Grados sobre la pieza elegida. Arrastra el punto verde para girarla: se imanta "
            "a 0°/90°; Ctrl = ajuste fino; Shift = pasos de 15°; doble clic = volver a 0°."),
            checkable=True)
        self.btn_protractor.toggled.connect(self._on_protractor_toggled)
        bar.add(self.btn_protractor, compact=True)
        bar.add_separator()

        self.btn_measure = tool("mdi:tape-measure", _tr("Medir"), _tr(
            "Clic en dos puntos: distancia en pies y rumbo. Shift = horizontal/vertical. "
            "Con los dos puntos en una pieza puedes calibrar la escala de su hoja."),
            checkable=True)
        self.btn_straighten = tool("mdi:set-square", _tr("Enderezar"), _tr(
            "Clic en dos puntos de una línea que debería ir horizontal o vertical: la pieza "
            "gira hasta dejarla derecha."), checkable=True)
        self.btn_measure.toggled.connect(lambda on: self._set_tool("measure", on))
        self.btn_straighten.toggled.connect(lambda on: self._set_tool("straighten", on))
        bar.add(self.btn_measure, compact=True)
        bar.add(self.btn_straighten, compact=True)
        bar.add_separator()

        self.btn_blend = tool("mdi:vector-combine", _tr("Fundir bordes"), _tr(
            "Donde dos piezas se superponen se ve la tinta de ambas: el papel de una no tapa "
            "las líneas de la otra. Superpón un poco las piezas y la unión no deja corte ni "
            "franja blanca. También se aplica al PDF que pasa al editor."), checkable=True)
        self.btn_blend.setChecked(bool(self.comp.seam_blend))
        self.btn_blend.toggled.connect(self._on_blend_toggled)
        bar.add(self.btn_blend, compact=True)

        view.measure.measured.connect(self._on_measured)
        view.measure.cleared.connect(self._on_measure_cleared)
        view.measure.straighten.connect(self._on_straighten)
        view.measure.exited.connect(lambda: self._set_tool(None, False))
        view.protractorAngleChanged.connect(self._on_protractor_angle)
        view.rotateRequested.connect(self._nudge_rotation)
        view.alignment_ruler.changed.connect(self._sync_rule_button)
        self._flash_timer = QtCore.QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_flash)
        self._flash = ""

    def build_scan_status(self, row: QtWidgets.QHBoxLayout):
        """«Calibrar escala…» junto a la línea de estado (solo tras medir en una pieza)."""
        self.btn_calibrate = QtWidgets.QPushButton(_icon("mdi:tape-measure", color=_theme.tokens().soft_text),
                                                   _tr("Calibrar escala…"))
        self.btn_calibrate.setProperty("soft", True)
        self.btn_calibrate.setToolTip(_tr("Escribe cuánto mide en realidad lo que mediste: la "
                                          "escala de esa hoja se corrige con esa distancia."))
        self.btn_calibrate.setAutoDefault(False)
        self.btn_calibrate.clicked.connect(self._calibrate)
        self.btn_calibrate.hide()
        row.addWidget(self.btn_calibrate)

    # ── línea de estado ────────────────────────────────────────────────
    def scan_status_text(self) -> str:
        if self._flash:
            return self._flash
        mode = self.view.measure.mode
        result = self.view.measure.result
        if mode == "measure":
            if result is not None:
                return _tr("Medida: {m}").format(m=self.view.measure.label(result[1], result[2]))
            return _tr("Medir: clic en dos puntos · Shift = horizontal/vertical · Esc = salir")
        if mode == "straighten":
            return _tr("Enderezar: clic en dos puntos de una línea que debe quedar horizontal o vertical")
        has = self.view.selected_index() >= 0
        if self.btn_protractor.isChecked():
            return (_tr("Transportador: arrastra el punto verde · imán a 0°/90° · Ctrl = fino · "
                        "Shift = 15° · doble clic = 0°") if has else
                    _tr("Transportador: elige una pieza para ver sus grados"))
        if has:
            return _tr("Flechas = mover · + / − = girar 0.1° · Ctrl = ajuste fino · Shift = paso grande")
        if self.btn_rule.isChecked():
            return _tr("Regla: arrástrala hasta una línea; su borde inferior es la guía · "
                       "▾ Bloquear para mover las hojas por debajo")
        return ""

    def _flash_status(self, text: str):
        self._flash = text
        self._flash_timer.start(6000)
        self._refresh_status()

    def _clear_flash(self):
        self._flash = ""
        self._refresh_status()

    # ── regla ───────────────────────────────────────────────────────────
    def _on_rule_toggled(self, on: bool):
        self.view.show_alignment_ruler(on)
        self._refresh_status()

    def _sync_rule_button(self):
        r = self.view.alignment_ruler
        self.ruler_lock.blockSignals(True)
        self.ruler_lock.setChecked(r.locked)
        self.ruler_lock.blockSignals(False)

    def _ruler_turn(self):
        r = self.view.alignment_ruler
        r.configure(angle=CS.nearest_axis(r.angle() + 90.0))

    def _ruler_to_view(self):
        """La regla horizontal en el centro de lo que se ve (si quedó fuera)."""
        r = self.view.alignment_ruler
        vis = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        r.configure(length=max(10.0, vis.width() * 0.6), width=max(5.0, vis.height() * 0.06), angle=0)
        r.setPos(vis.center().x() - r.length / 2, vis.center().y())
        if not self.btn_rule.isChecked():
            self.btn_rule.setChecked(True)

    def _configure_ruler(self, key, value):
        r = self.view.alignment_ruler
        if key in ("x", "y"):
            r.setPos(value if key == "x" else r.x(), value if key == "y" else r.y())
        else:
            r.configure(**{key: value})

    def _sync_ruler_fields(self):
        r = self.view.alignment_ruler
        for key, field in self.ruler_fields.items():
            field.blockSignals(True)
            field.setValue({"x": r.x(), "y": r.y(), "length": r.length,
                "width": r.width, "angle": r.angle()}[key])
            field.blockSignals(False)

    # ── giro de la pieza elegida ───────────────────────────────────────
    def _turn_piece(self, index: int, rotation: float, pivot=None):
        """Gira la pieza a `rotation` (antihorario) sin mover `pivot` (su centro
        si no se indica): el transportador y «Enderezar» no la desplazan."""
        p = self.comp.pieces[index]
        CS.rotate_piece(p, self.view.page_size(p), self.comp.target_scale(), rotation, pivot)
        self.view.refresh_piece(index)
        self._sync_piece_widgets(index)
        self._refresh_summary()

    def _on_protractor_toggled(self, on: bool):
        self.view.show_protractor(on)
        self._refresh_status()

    def _on_protractor_angle(self, value):
        index = self.view.selected_index()
        if index >= 0:
            self._turn_piece(index, value)

    def _nudge_rotation(self, delta: float):
        index = self.view.selected_index()
        if index >= 0:
            p = self.comp.pieces[index]
            self._turn_piece(index, round(p.rotation + delta, 6))

    def _reset_rotation(self):
        """Ajustes ▾ «Girar a 0°»: al eje más cercano (respeta un giro de 90°)."""
        index = self.view.selected_index()
        if index >= 0:
            self._turn_piece(index, CS.nearest_axis(self.comp.pieces[index].rotation))

    # ── medir / enderezar ──────────────────────────────────────────────
    def _set_tool(self, name, on: bool):
        """Medir y Enderezar se excluyen; Esc o un segundo clic en el botón sale."""
        if on:
            other = self.btn_straighten if name == "measure" else self.btn_measure
            other.blockSignals(True); other.setChecked(False); other.blockSignals(False)
            self.view.measure.set_mode(name)
            self.view.setFocus()
        elif self.view.measure.mode in (name, None) or name is None:
            for b in (self.btn_measure, self.btn_straighten):
                b.blockSignals(True); b.setChecked(False); b.blockSignals(False)
            self.view.measure.set_mode(None)
        self._flash = ""
        self._refresh_status()

    def _on_measured(self, index, a, b):
        self.btn_calibrate.setVisible(index >= 0)
        self._refresh_status()

    def _on_measure_cleared(self):
        self.btn_calibrate.hide()
        self._refresh_status()

    def _on_straighten(self, index, a, b):
        correction = C.ruler_correction(a, b, None)
        if correction is None or not 0 <= index < len(self.comp.pieces):
            return
        p = self.comp.pieces[index]
        pivot = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)   # la línea no se mueve
        self._turn_piece(index, round(p.rotation + correction, 6), pivot)
        self.view.select(index)
        self._set_tool(None, False)
        self._flash_status(_tr("✔ Pieza {n} enderezada: {a:+.2f}°").format(n=index + 1, a=correction))

    def _calibrate(self):
        result = self.view.measure.result
        if result is None or result[0] < 0:
            return
        index, a, b = result
        measured = math.hypot(b[0] - a[0], b[1] - a[1]) * self.comp.target_scale()
        real, ok = QtWidgets.QInputDialog.getDouble(
            self, _tr("Calibrar escala"),
            _tr("Medida en el plano: {m:.2f} ft. ¿Cuánto mide en realidad (pies)?").format(m=measured),
            round(measured, 2), 0.01, 10_000_000.0, 2)
        if not ok:
            return
        piece = self.comp.pieces[index]
        new = CS.calibrated_scale(piece.src_scale, measured, real)
        if new is None:
            return
        self.apply_page_scale(piece.source, piece.page, new, pivot=(index, a))
        self._flash_status(_tr("✔ Escala de la hoja corregida: {s}").format(
            s='1" = {v:g}\''.format(v=round(new * 72.0, 3))))

    def apply_page_scale(self, source: int, page: int, scale: float, pivot=None):
        """Nueva escala (pies/pt) para TODAS las piezas de esa hoja (un escaneo
        tiene una sola escala). Si todas las piezas quedan con la misma escala,
        la hoja compuesta la adopta y nada se mueve; si no, la escala de la hoja
        compuesta se conserva y cada pieza calibrada cambia de tamaño sin mover
        su centro (la medida, sin mover su primer punto)."""
        comp = self.comp
        old_target = comp.target_scale()
        targets = [i for i, p in enumerate(comp.pieces) if p.source == source and p.page == page]
        others = {p.src_scale for i, p in enumerate(comp.pieces) if i not in targets}
        if all(abs(s - scale) < 1e-12 for s in others):
            for i in targets:
                comp.pieces[i].src_scale = scale
            comp.scale_ft_per_pt = None
        else:
            comp.scale_ft_per_pt = old_target
            for i in targets:
                p = comp.pieces[i]
                at = pivot[1] if pivot and pivot[0] == i else None
                CS.scale_piece(p, self.view.page_size(p), old_target, scale, at)
        self._scale_cache[(source, page)] = scale
        if (source, page) == (self._cur_source, self._cur_page):
            self.spn_src_scale.blockSignals(True)
            self.spn_src_scale.setValue(scale * 72.0)
            self.spn_src_scale.blockSignals(False)
        self._refresh_scale_combo()
        self.view.refresh_all()
        idx = self.view.selected_index()
        if idx >= 0:
            self._sync_piece_widgets(idx)
        self._refresh_summary()

    # ── fundir bordes ───────────────────────────────────────────────────
    def _on_blend_toggled(self, on: bool):
        self.view.set_blend(on)
        self._flash_status(_tr("Fundir bordes activado: superpón un poco las piezas en la unión.")
                           if on else _tr("Fundir bordes desactivado: cada pieza tapa a la de abajo."))
