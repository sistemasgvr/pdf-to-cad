"""Clics en el lienzo, selección, snap y edición/movimiento con el ratón.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class ClicsMixin:
    # ─────────────────────────── clics ───────────────────────────
    def on_click(self, x, y, button):
        if self.canvas.pixmap_item is None: return
        if button == QtCore.Qt.RightButton:
            if self.mode == "pipe": self.finish_pipe()
            elif self.mode == "erase": self.finish_erase()
            elif self.mode == "centerline": self.finish_centerline()
            elif self.mode == "move": self._delete_vertex(x, y)
            elif self.mode == "idle": self._canvas_context_menu(x, y)
            return
        # Left-click sobre una marca de conflicto (círculo amarillo con !):
        # abre el diálogo de aprobación para conectar con válvula. Tiene
        # prioridad sobre cualquier otro modo — el usuario no debe estar
        # esperando resolver un conflicto y que el click empiece a dibujar.
        if button == QtCore.Qt.LeftButton and self.mode != "pipe":
            if self._try_click_conflict(x, y):
                return
        if self.mode == "pipe":
            self._push(); self.cur_pts.append(self._pipe_snap_and_ask(x, y)); self._update_ui(); self._redraw()
        elif self.mode == "erase":
            self._erase_pts.append((x, y)); self._update_ui(); self._redraw()
        elif self.mode == "centerline":
            self._push(); self._cl_pts.append(self._snap(x, y)); self._update_ui(); self._redraw()
        elif self.mode == "text":
            if self._editor is not None: return   # el clic confirma el texto abierto (no abre otro)
            self._new_free_text(x, y)
        elif self.mode == "leader1":
            self._pending["arrow"] = self._snap(x, y); self.mode = "leader2"; self._update_ui()
        elif self.mode == "leader2":
            hx, hy = self._pending["arrow"]; o = self.orient_combo.currentData()
            if o == "d":                                 # diagonal: 2º clic = inicio del landing (bisagra)
                self._pending["landing"] = self._snap(x, y); self.mode = "leader3"; self._update_ui(); return
            tail = (x, hy) if o == "h" else (hx, y)      # h/v: 2º clic = final del cuerpo, recto al eje
            self._add_simple_leader((hx, hy), tail, o); return
        elif self.mode == "leader3":                         # Leader diagonal: 3er clic = final del cuerpo
            self._add_simple_leader(self._pending["arrow"], (x, y), "d",
                                    landing=self._pending.get("landing")); return
        elif self.mode == "insert_bz":
            self._do_insert_manhole(x, y)
        elif self.mode == "idle":
            self._pick(x, y)

    def _add_simple_leader(self, head, tail, orient, landing=None):
        """Coloca un Leader simple (solo flecha, sin texto) y queda listo para el siguiente.
        orient 'h'/'v' → 2 clics (cabeza→final del cuerpo, recto al eje).
        orient 'd'     → 3 clics (cabeza → inicio del landing/bisagra → final del cuerpo)."""
        self._push()
        self.leaders.append({"text": "", "orient": orient, "simple": True,
                             "arrow": head, "tp": tail if tail else head, "landing": landing,
                             "font": self.font_combo.currentFont().family(),
                             "size_ft": self.size_spin.value(), "bold": self.chk_bold.isChecked()})
        self._pending = {"arrow": None, "simple": True}; self.mode = "leader1"
        self._refresh_lists(); self._update_ui(); self._redraw()
        self._info(_tr("Leader colocado. Clic en la cabeza de flecha del siguiente (Esc para salir)."))

    def on_dblclick(self, x, y):
        if self.mode not in ("idle", "move"): return
        thr = 14.0 / max(1e-6, self.canvas.transform().m11())
        for i, ld in enumerate(self.leaders):
            if not (ld.get("arrow") and ld.get("tp")): continue
            geo = self._leader_geo(ld); lx, ly = geo["label_pos"]; H = geo["H"]
            lines = ld["text"].split("\n"); tw = max((len(s) for s in lines), default=1) * H * 0.55; th = len(lines) * H
            hit_text = (lx - 8 <= x <= lx + tw + 8 and ly - 8 <= y <= ly + th + 8)
            if hit_text or math.hypot(ld["tp"][0] - x, ld["tp"][1] - y) < thr:
                self._edit_leader_text(i); return
        for i, tm in enumerate(self.text_marks):
            if self._text_hit(tm, x, y):
                self._edit_text_mark(i); return

    def _text_hit(self, tm, x, y):
        h = self._px_for_ft(tm["size_ft"]) if "size_ft" in tm else tm.get("h", 16)
        lines = tm["text"].split("\n")
        w = max((len(s) for s in lines), default=1) * h * 0.55; th = len(lines) * h
        px, py = tm["pos"]; return px - 6 <= x <= px + w + 6 and py - 6 <= y <= py + th + 6

    def _pick(self, x, y):
        thr = 10.0 / max(1e-6, self.canvas.transform().m11())
        bz_thr = 18.0 / max(1e-6, self.canvas.transform().m11())
        curve_thr = 22.0 / max(1e-6, self.canvas.transform().m11())
        best_bz, bd_bz = -1, bz_thr
        for i, s in enumerate(self.structures):
            if s.get("world") or s.get("hidden"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            d = math.hypot(x - sx, y - sy)
            local_thr = curve_thr if s.get("curve") else bz_thr
            if d < local_thr and d < bd_bz: bd_bz, best_bz = d, i
        # Hit-test extra sobre el ARCO REAL de cada elemento curvo. Sin esto
        # el usuario tiene que clickear justo en el vértice esquina (chico);
        # con esto puede hacer clic en cualquier parte del arco visible.
        arc_thr = thr * 1.5
        for i, s in enumerate(self.structures):
            if not s.get("curve") or s.get("world") or s.get("hidden"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            pipe = self._pipe_at_vertex(sx, sy)
            info = self._curve_arc_info(s, pipe) if pipe else None
            if info is None: continue
            arc_pts = self._arc_polyline(info, n_per_90=12)
            for a, b in zip(arc_pts, arc_pts[1:]):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < arc_thr and d < bd_bz:
                    bd_bz, best_bz = d, i
        if best_bz >= 0:
            self._no_center = True
            if self.structures[best_bz].get("curve"):
                self._show_tab(TAB_CURVE); self.curve_list.setCurrentRow(self._curve_rows.index(best_bz))
            else:
                self._show_tab(TAB_BZ); self.bz_list.setCurrentRow(self._bz_rows.index(best_bz))
            self._no_center = False; return
        for i, tm in enumerate(self.text_marks):        # textos primero (blancos pequeños)
            if self._text_hit(tm, x, y):
                self._no_center = True; self._show_tab(TAB_TEXT); self.txt_marks_list.setCurrentRow(i)
                self._no_center = False; return
        for i, ld in enumerate(self.leaders):           # leaders: por la línea o el texto
            if not (ld.get("arrow") and ld.get("tp")): continue
            geo = self._leader_geo(ld); hit = False
            for s in geo["segs"]:
                for a, b in zip(s, s[1:]):
                    if G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1]) < thr: hit = True; break
                if hit: break
            lx, ly = geo["label_pos"]; H = geo["H"]
            tw = max((len(t) for t in ld["text"].split("\n")), default=1) * H * 0.6; tt = ld["text"].count("\n") + 1
            if not hit and lx - 8 <= x <= lx + tw + 8 and ly - 8 <= y <= ly + tt * H + 8: hit = True
            if hit:
                self._select_leader(i); return
        best_cl, bd_cl = -1, thr
        for i, c in enumerate(self.ref_centerlines):
            pts = c.get("pts") or []
            for a, b in zip(pts, pts[1:]):
                d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
                if d < bd_cl: bd_cl, best_cl = d, i
        if best_cl >= 0:
            self._no_center = True; self._show_tab(TAB_CL); self.cl_list.setCurrentRow(best_cl)
            self._no_center = False; return
        best = self._pipe_at(x, y)
        if best >= 0 and QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier:
            self._toggle_pipe_selection(best); return
        if best >= 0:
            self._no_center = True; self._show_tab(TAB_PIPE); self.pipe_list.clearSelection(); self.pipe_list.setCurrentRow(best)
            self._no_center = False
            self._scroll_pipe_list_to(best)

    def _scroll_pipe_list_to(self, row):
        """Lleva la lista «Utilidades» hasta la fila `row` (centrada). Diferido: el
        cambio de pestaña y el panel de propiedades se acomodan en el mismo ciclo
        y un scroll inmediato quedaba sin efecto (la lista no bajaba a la utilidad
        elegida en el lienzo)."""
        def _go():
            it = self.pipe_list.item(row) if 0 <= row < self.pipe_list.count() else None
            if it is not None:
                self.pipe_list.scrollToItem(it, QtWidgets.QAbstractItemView.PositionAtCenter)
        _go()
        QtCore.QTimer.singleShot(0, _go)

    def _snap(self, x, y):
        if not self.snap: return (x, y)
        return G.snap_point(self.gray, x, y, self.snap_r)

    def _pipe_soft_snap(self, x, y, layer=None, exclude=None, skip_structs=()):
        """Snap suave a utilidades EXISTENTES del mismo tipo (capa) mientras se
        dibuja una nueva. Busca dentro de un radio en pixels de pantalla el
        candidato más cercano y devuelve un dict:
            {"pt": (x, y), "kind": "endpoint"|"vertex"|"segment",
             "pipe_idx": int, "port": int}
        `port` es 0 para start, len(pts)-1 para end (endpoints), o el índice
        del vértice interno (vertex), o el índice del segmento inicio (segment).
        Devuelve None si no hay nada cerca.

        Sólo compara contra pipes cuya capa == `layer` (o self.active_layer()
        si no se pasa). Radio de snap = 12 px de pantalla, convertidos a
        unidades de escena según el zoom actual.

        Además se engancha al CONTORNO de los SÓLIDOS (de cualquier utilidad):
        kind "solid", `pipe_idx` None y `port` = índice de la estructura; sus
        esquinas mandan como un vértice. `exclude` = (pipe_idx, vi) del vértice
        que se está arrastrando (ni él ni sus dos tramos cuentan) y
        `skip_structs` = estructuras que se mueven con él."""
        lay = layer or self.active_layer()
        m11 = max(1e-6, self.canvas.transform().m11())
        tol = 12.0 / m11
        best = None; best_d2 = tol * tol
        ex_pi, ex_vi = exclude if exclude else (None, None)
        for pi, p in enumerate(self.pipes):
            if p.get("layer") != lay: continue
            pts = p.get("pts") or []
            n = len(pts)
            if n < 2: continue
            # 1) Vértices (endpoints + intermedios).
            for vi, (vx, vy) in enumerate(pts):
                if pi == ex_pi and vi == ex_vi: continue
                d2 = (vx - x) ** 2 + (vy - y) ** 2
                if d2 < best_d2:
                    kind = "endpoint" if (vi == 0 or vi == n - 1) else "vertex"
                    best = {"pt": (vx, vy), "kind": kind, "pipe_idx": pi, "port": vi}
                    best_d2 = d2
            # 2) Proyección perpendicular sobre cada segmento.
            for si in range(n - 1):
                if pi == ex_pi and si in (ex_vi - 1, ex_vi): continue   # tramos del vértice arrastrado
                ax, ay = pts[si]; bx, by = pts[si + 1]
                dx, dy = bx - ax, by - ay
                seg_len2 = dx * dx + dy * dy
                if seg_len2 < 1e-9: continue
                t = ((x - ax) * dx + (y - ay) * dy) / seg_len2
                if t <= 0 or t >= 1: continue      # los extremos ya se cubren arriba
                px = ax + t * dx; py = ay + t * dy
                d2 = (px - x) ** 2 + (py - y) ** 2
                # Los VÉRTICES mandan sobre la proyección al tramo: junto a un
                # vértice, la perpendicular a un segmento oblicuo cae un pelo
                # más cerca y le ganaba, así que el punto se deslizaba unas
                # décimas sobre el tramo en vez de pegarse al vértice — y las
                # utilidades no empalmaban exactamente donde el usuario veía
                # el marcador. Un hit de vértice solo se cede si el tramo está
                # claramente más cerca.
                if best is not None and best["kind"] in ("endpoint", "vertex"):
                    if d2 >= best_d2 * PRIORIDAD_VERTICE: continue
                if d2 < best_d2:
                    best = {"pt": (px, py), "kind": "segment", "pipe_idx": pi, "port": si}
                    best_d2 = d2
        # 3) Contorno de los SÓLIDOS: esquinas (como un vértice) y el borde.
        salta = {id(st) for st in skip_structs or ()}
        for k, st in enumerate(self.structures):
            if not st.get("solid") or id(st) in salta: continue
            poly = [tuple(q) for q in (st.get("outline") or [])]
            if len(poly) < 3: continue
            for cx, cy in poly:
                d2 = (cx - x) ** 2 + (cy - y) ** 2
                if best is not None and best["kind"] in ("endpoint", "vertex") and d2 >= best_d2: continue
                if d2 < best_d2:
                    best = {"pt": (cx, cy), "kind": "solid", "pipe_idx": None, "port": k, "corner": True}
                    best_d2 = d2
            for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
                dx, dy = bx - ax, by - ay
                seg_len2 = dx * dx + dy * dy
                if seg_len2 < 1e-9: continue
                t = ((x - ax) * dx + (y - ay) * dy) / seg_len2
                if t <= 0 or t >= 1: continue
                px = ax + t * dx; py = ay + t * dy
                d2 = (px - x) ** 2 + (py - y) ** 2
                # Igual que con los tramos: un vértice (o una esquina) cercano manda.
                if best is not None and (best["kind"] in ("endpoint", "vertex") or best.get("corner")):
                    if d2 >= best_d2 * PRIORIDAD_VERTICE: continue
                if d2 < best_d2:
                    best = {"pt": (px, py), "kind": "solid", "pipe_idx": None, "port": k}
                    best_d2 = d2
        return best

    def _endpoint_drag(self):
        """(pipe_idx, vi) si se está arrastrando el vértice INICIAL o FINAL de la
        utilidad seleccionada (modo Mover); None si no. Ese extremo se engancha
        con el mismo snap suave que al dibujar."""
        vi = getattr(self, "_drag_vertex", None)
        if getattr(self, "_move_kind", None) != "pipe" or vi is None \
                or not (0 <= self.sel_pipe < len(self.pipes)):
            return None
        n = len(self.pipes[self.sel_pipe].get("pts") or [])
        return (self.sel_pipe, vi) if n >= 2 and vi in (0, n - 1) else None

    def _drag_snap(self, x, y):
        """Snap del extremo arrastrado: devuelve (x, y, hit)."""
        ex = self._endpoint_drag()
        if ex is None: return x, y, None
        hit = self._pipe_soft_snap(x, y, layer=self.pipes[ex[0]].get("layer"), exclude=ex,
                                   skip_structs=getattr(self, "_move_structs", None) or ())
        if hit is None: return x, y, None
        return hit["pt"][0], hit["pt"][1], hit

    def _pipe_snap_and_ask(self, x, y):
        """Aplica el snap suave para el modo Dibujar. Si el snap cae en el
        EXTREMO de una utilidad existente del mismo tipo y es el PRIMER click
        de la nueva utilidad, pregunta si el usuario quiere unirla como parte
        de esa utilidad (extenderla) o crear una nueva independiente.

        Devuelve (x, y) del punto a usar. Si el usuario eligió "unir", además
        deja `_extending`/`_ext_pipe`/`_ext_at` armados como si hubiera venido
        del comando F, para que `finish_pipe` haga el append correcto."""
        hit = self._pipe_soft_snap(x, y)
        if hit is None:
            return self._snap(x, y)
        sx, sy = hit["pt"]
        # Sólo pregunta si es el primer click (cur_pts vacío) y el snap es a
        # un EXTREMO (unir a mitad de segmento no tiene sentido en polilíneas).
        first_click = not self.cur_pts and not self._extending
        if first_click and hit["kind"] == "endpoint":
            resp = QtWidgets.QMessageBox.question(
                self, _tr("Unir a utilidad existente"),
                _tr("El punto donde estás dibujando coincide con el extremo de otra "
                    "utilidad del mismo tipo.\n\n"
                    "¿Quieres UNIRLA como parte de esa utilidad (misma polilínea, "
                    "una sola red)?\n\n"
                    "Sí = extiende la utilidad existente.\n"
                    "No = crea una utilidad nueva que la toca (juntura automática al importar)."),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if resp == QtWidgets.QMessageBox.Yes:
                pi = hit["pipe_idx"]; port = hit["port"]
                pep = self.pipes[pi]
                self._extending = True
                self._ext_pipe = pi
                self._ext_layer = pep.get("layer", "")
                self._ext_at = "start" if port == 0 else "end"
        return (sx, sy)

    # ─────────────────────────── editar / mover ───────────────────────────
    def _current_kind(self):
        ti = self._current_tab()
        if ti == TAB_PIPE and 0 <= self.sel_pipe < len(self.pipes): return "pipe"
        if ti == TAB_LEADER and 0 <= self.sel_leader < len(self.leaders) and self.leaders[self.sel_leader].get("simple"): return "leader"
        if ti == TAB_TEXT and 0 <= self.sel_text < len(self.text_marks): return "text"
        if ti == TAB_REGION and 0 <= self.sel_region < len(self.erase_regions): return "region"
        return None

    def enter_move(self):
        kind = self._current_kind()
        # Ctrl+T con un Leader simple seleccionado: asegura la pestaña Leaders y entra a editar sus vértices
        if not kind and 0 <= self.sel_leader < len(self.leaders) and self.leaders[self.sel_leader].get("simple"):
            self._select_leader(self.sel_leader, center=True); kind = "leader"
        if kind == "leader":
            self.set_mode("move"); self._info(_tr("Editar Leader: arrastra un vértice (posición/longitud) o el trazo para mover. Enter/Esc termina."))
        elif kind:
            self.set_mode("move"); self._info(_tr("Arrastra para mover · clic en vértice extiende (F) · clic derecho elimina"))
        else:
            self._info(_tr("Selecciona primero una utilidad, Leader, texto o zona"))

    def _thr(self): return 12.0 / max(1e-6, self.canvas.transform().m11())

    def _segments(self, pts, closed):
        segs = list(zip(range(len(pts) - 1), pts, pts[1:]))
        if closed and len(pts) >= 3: segs.append((len(pts) - 1, pts[-1], pts[0]))
        return segs

    def begin_move(self, x, y):
        kind = self._current_kind()
        if not kind: return
        self._push(); self._moved = False; self._move_kind = kind
        self._move_structs = []                          # estructuras que acompañan al arrastre
        self._press_xy = (x, y); self._last_xy = (x, y); thr = self._thr()
        if kind == "text":
            self._move0 = (x, y); self._drag_vertex = None; self._edit_pts = None; return
        if kind == "leader":
            ld = self.leaders[self.sel_leader]; self._edit_leader = ld
            pts = [tuple(ld["arrow"])]
            if ld.get("landing"): pts.append(tuple(ld["landing"]))
            pts.append(tuple(ld["tp"]))
            self._edit_pts = pts; self._edit_closed = False
            vi, vd = -1, thr
            for i, (px, py) in enumerate(pts):
                d = math.hypot(px - x, py - y)
                if d < vd: vd, vi = d, i
            self._drag_vertex = vi if vi >= 0 else None       # vértice cercano → arrastra; si no, mueve todo
            self._move0 = None if vi >= 0 else (x, y); return
        pts = self.pipes[self.sel_pipe]["pts"] if kind == "pipe" else self.erase_regions[self.sel_region]["pts"]
        if not pts: return                              # tramo importado (world): no editable en el lienzo
        self._edit_pts = pts; self._edit_closed = (kind == "region")
        vi, vd = -1, thr
        for i, (px, py) in enumerate(pts):
            d = math.hypot(px - x, py - y)
            if d < vd: vd, vi = d, i
        if vi >= 0:
            self._drag_vertex = vi; self._move0 = None
            if kind == "pipe":                          # el buzón/caja del vértice se mueve con él
                self._move_structs = model_ops.structures_at_vertex(self.pipes, self.structures, self.sel_pipe, vi)
            return
        si, sd = -1, thr
        for idx, a, b in self._segments(pts, self._edit_closed):
            d = G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1])
            if d < sd: sd, si = d, idx
        if si >= 0:
            pts.insert(si + 1, (x, y)); self._drag_vertex = si + 1; self._move0 = None; self._moved = True
            if kind == "pipe":
                p = self.pipes[self.sel_pipe]; ov = p.get("vertex_inv")
                if ov:                          # reindexar: todo lo que estaba después del corte sube uno
                    p["vertex_inv"] = {(k + 1 if k >= si + 1 else k): v for k, v in ov.items()}
                self._rebuild_seg_inv_table(p)
            self._refresh_lists(); return
        self._drag_vertex = None; self._move0 = (x, y)
        if kind == "pipe":                              # mover la utilidad entera: sus buzones propios también
            vistos = set()
            for i in range(len(pts)):
                for st in model_ops.structures_at_vertex(self.pipes, self.structures, self.sel_pipe, i):
                    compartida = any(math.hypot(st["x"] - qx, st["y"] - qy) <= model_ops._TOL
                                     for pj, p in enumerate(self.pipes) if pj != self.sel_pipe
                                     for qx, qy in (p.get("pts") or []))
                    if id(st) not in vistos and not compartida:     # el nudo con otra utilidad se queda
                        vistos.add(id(st)); self._move_structs.append(st)

    def do_move(self, x, y):
        self._moved = True; self._last_xy = (x, y)
        if self._move_kind == "text" and 0 <= self.sel_text < len(self.text_marks):
            if self._move0:
                dx, dy = x - self._move0[0], y - self._move0[1]; self._move0 = (x, y)
                px, py = self.text_marks[self.sel_text]["pos"]
                self.text_marks[self.sel_text]["pos"] = (px + dx, py + dy); self._redraw()
            return
        if self._move_kind == "leader":
            pts = self._edit_pts
            if pts is None: return
            if self._drag_vertex is not None:
                pts[self._drag_vertex] = (x, y)               # mueve un vértice (posición/longitud)
            elif self._move0 is not None:
                dx, dy = x - self._move0[0], y - self._move0[1]; self._move0 = (x, y)
                for i in range(len(pts)): pts[i] = (pts[i][0] + dx, pts[i][1] + dy)
            else:
                return
            self._sync_leader(); self._redraw(); return
        pts = self._edit_pts
        if pts is None: return
        if self._drag_vertex is not None:
            if self._move_kind == "pipe":                # extremo: mismo snap suave que al dibujar
                x, y, _ = self._drag_snap(x, y)
            ox, oy = pts[self._drag_vertex]
            pts[self._drag_vertex] = (x, y)
            for st in getattr(self, "_move_structs", None) or []:
                model_ops.translate_structure(st, x - ox, y - oy)
            self._redraw(); return
        if self._move0 is not None:
            dx, dy = x - self._move0[0], y - self._move0[1]; self._move0 = (x, y)
            for i in range(len(pts)): pts[i] = (pts[i][0] + dx, pts[i][1] + dy)
            for st in getattr(self, "_move_structs", None) or []:
                model_ops.translate_structure(st, dx, dy)
            self._redraw()

    def end_move(self):
        # clic (casi sin arrastrar) sobre un vértice de una tubería → extender
        dist = math.hypot(self._last_xy[0] - self._press_xy[0], self._last_xy[1] - self._press_xy[1]) \
            if (self._last_xy and self._press_xy) else 0
        if (self._move_kind == "pipe" and self._drag_vertex is not None and dist < 6
                and 0 <= self.sel_pipe < len(self.pipes)):
            self._move0 = None; self._move_kind = None
            self._start_extension(self.sel_pipe, self._drag_vertex); self._drag_vertex = None; return
        movidos = bool(getattr(self, "_move_structs", None)) and self._moved
        self._move0 = None; self._drag_vertex = None; self._move_kind = None; self._edit_leader = None
        self._move_structs = []
        if movidos:
            self._refresh_lists(); self._redraw()       # lista de buzones y conexiones al día

    def _sync_leader(self):
        """Vuelca los vértices editados (self._edit_pts) al leader (arrow / landing / tp)."""
        ld = self._edit_leader; pts = self._edit_pts
        if not ld or not pts: return
        ld["arrow"] = pts[0]
        if ld.get("landing"): ld["landing"] = pts[1]; ld["tp"] = pts[2]
        else: ld["tp"] = pts[-1]

    def _start_extension(self, pi, vi):
        # Sin ventana emergente: la casilla 'continuar la misma utilidad' decide.
        pts = self.pipes[pi]["pts"]; vpos = tuple(pts[vi]); is_end = (vi == 0 or vi == len(pts) - 1)
        same = self.chk_ext_same.isChecked() and is_end
        self._extending = True; self._ext_layer = self.pipes[pi]["layer"]; self.cur_pts = [vpos]
        if same:
            self._ext_pipe = pi; self._ext_at = "start" if vi == 0 else "end"
            self._info(_tr("Continuando la MISMA utilidad: clic para agregar puntos, Enter finaliza."))
        else:
            self._ext_pipe = None; self._ext_at = None
            if self.chk_ext_same.isChecked() and not is_end:
                self._info(_tr("Solo desde un extremo se continúa; se creará una utilidad NUEVA. Clic para agregar, Enter finaliza."))
            else:
                self._info(_tr("Utilidad NUEVA (rama en F): clic para agregar puntos, Enter finaliza."))
        self.set_mode("pipe")

    def _delete_vertex(self, x, y):
        kind = self._current_kind()
        if kind not in ("pipe", "region"): return
        pts = self.pipes[self.sel_pipe]["pts"] if kind == "pipe" else self.erase_regions[self.sel_region]["pts"]
        floor = 3 if kind == "region" else 2
        if len(pts) <= floor: self._info(_tr("Necesita al menos {n} puntos").format(n=floor)); return
        thr = self._thr(); vi, vd = -1, thr
        for i, (px, py) in enumerate(pts):
            d = math.hypot(px - x, py - y)
            if d < vd: vd, vi = d, i
        if vi >= 0:
            self._push(); pts.pop(vi)
            if kind == "pipe":
                p = self.pipes[self.sel_pipe]; ov = p.get("vertex_inv")
                if ov:                          # reindexar: el vértice vi ya no existe, los de más allá bajan uno
                    p["vertex_inv"] = {(k - 1 if k > vi else k): v for k, v in ov.items() if k != vi}
                self._rebuild_seg_inv_table(p)
            self._refresh_lists(); self._redraw(); self._info(_tr("Vértice eliminado"))
