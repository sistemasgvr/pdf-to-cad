"""Borrar zona, centerlines, leaders y texto libre.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class MarcasMixin:
    # ─────────────────────────── borrar zona ───────────────────────────
    def finish_erase(self):
        if len(self._erase_pts) < 3: return
        self._push(); poly = self._erase_pts[:]; self.erase_regions.append({"pts": poly, "enabled": True})
        # Las zonas de borrado SOLO tapan la geometría del PDF base al exportar
        # (ver dxf_export.apply_erase, que corre antes de agregar utilidades).
        # NO eliminan pipes/leaders/textos del usuario que caigan dentro — eso
        # se hace explícito con el borrado individual del panel.
        self._erase_pts = []; self.set_mode("idle"); self._refresh_lists()
        self._info(_tr("Zona agregada: al exportar tapa la geometría base del plano dentro de ella (no toca tus utilidades)."))

    def finish_centerline(self):
        if len(self._cl_pts) < 2: return
        self._push()
        used = {c.get("cod", "") for c in self.ref_centerlines if c.get("cod")}
        n = 1
        while f"CL-{n}" in used: n += 1
        self.ref_centerlines.append({"cod": f"CL-{n}", "pts": self._cl_pts[:]})
        self._cl_pts = []; self.set_mode("idle"); self._refresh_lists()
        self._info(_tr("Centerline agregado — solo referencia para calzar la georreferenciación, no es una utilidad."))

    def start_leader(self, simple=True):
        """Entra al modo de colocación de Leader (solo flecha, sin texto). La
        orientación se lee de `orient_combo` AL MOMENTO del clic final para que
        el usuario pueda cambiarla dentro del modo. `simple` se mantiene solo
        por retrocompat de callers antiguos; siempre es True ahora."""
        self._pending = {"arrow": None, "simple": True}
        self._open_section("leader")
        self.set_mode("leader1")
        if self.orient_combo.currentData() == "d":
            self._info(_tr("Leader diagonal: cabeza → inicio del landing (bisagra) → final del cuerpo. Enter/Esc para salir."))
        else:
            self._info(_tr("Leader: cabeza de flecha → final del cuerpo. Enter/Esc para salir."))

    def _edit_leader_text(self, idx):
        ld = self.leaders[idx]; tp = ld["tp"]
        if ld.get("simple"):                                 # el Leader simple no tiene texto que editar
            self._info(_tr("El Leader simple no lleva texto.")); return
        def commit(val):
            self._close_editor()
            if val.strip(): self._push(); ld["text"] = val.rstrip("\n"); self._refresh_lists()
            self._redraw()
        self._open_editor(tp[0], tp[1] - self.leader_hpx, ld["text"], commit)

    def _leader_geo(self, ld):
        # Geometría del Multileader (pura) en model_ops; se le pasa la conversión
        # pies→px de la ventana (depende de escala/zoom).
        return model_ops.leader_geo(ld, self._px_for_ft)

    # ─────────────────────────── texto libre ───────────────────────────
    def _new_free_text(self, x, y):
        def commit(val):
            self._close_editor()
            if val.strip():
                self._push()
                self.text_marks.append({"pos": (x, y), "text": val.rstrip("\n"),
                                        "size_ft": self.size_spin.value(), "font": self.font_combo.currentFont().family(),
                                        "bold": self.chk_bold.isChecked(), "rot": self.rot_spin.value() % 360, "free": True})
                self._refresh_lists()
            self._redraw()
        self._open_editor(x, y, "", commit)

    def _edit_text_mark(self, idx):
        tm = self.text_marks[idx]
        def commit(val):
            self._close_editor()
            if val.strip(): self._push(); tm["text"] = val.rstrip("\n"); self._refresh_lists()
            self._redraw()
        self._open_editor(tm["pos"][0], tm["pos"][1], tm["text"], commit)

    def _open_editor(self, x, y, initial, on_commit, w=220):
        # Caja flotante hija del viewport (no escala con el zoom y recibe el teclado
        # de forma fiable: Enter aplica, Ctrl+Shift+Enter salta de línea, clic fuera aplica).
        self._close_editor()
        ed = InlineEdit(initial); ed.setParent(self.canvas.viewport())
        ed.setFixedWidth(w); ed.setFixedHeight(64)
        vp = self.canvas.mapFromScene(QtCore.QPointF(x, y))
        ed.move(vp); ed.show(); ed.raise_()
        ed.committed.connect(on_commit); self._editor = ed
        ed.setFocus(QtCore.Qt.OtherFocusReason); ed.selectAll()

    def _close_editor(self):
        if self._editor:
            ed = self._editor; self._editor = None
            try: ed.hide(); ed.deleteLater()
            except Exception: pass
