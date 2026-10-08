"""Dibujo del lienzo: utilidades, conexiones cruzadas, estructuras y formas.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class DibujoMixin:
    # ─────────────────────────── dibujo ───────────────────────────
    def _redraw(self):
        sc = self.canvas.scene()
        for it in self._overlay:
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        self._overlay = []
        if self.canvas.pixmap_item is None: return
        # zonas de borrado — DETRÁS de todo (solo tapan el PDF)
        if self._erase_pts:
            self._poly(self._erase_pts, QtGui.QColor(255, 220, 0), 1.8, dots=True, z=Z_MARK)
        # Fondo detrás del PDF (blanco/negro) — solo cambia el ASPECTO VISUAL de
        # las zonas borradas en el lienzo principal. Al exportar/importar la zona
        # sigue tratándose exactamente igual (nada de esto toca los datos).
        bg = self.canvas.pdf_bg_color
        bg_dark = bg.value() < 128
        fill_full = QtGui.QColor(bg)                       # opaco (misma tinta que el fondo)
        fill_sel = QtGui.QColor(bg); fill_sel.setAlpha(128)   # semitransparente al seleccionar
        for i, rg in enumerate(self.erase_regions):
            qp = QtGui.QPolygonF([QtCore.QPointF(px, py) for (px, py) in rg["pts"]])
            enabled = rg.get("enabled", True); sel = (i == self.sel_region)
            if not enabled:
                pen = QtGui.QPen(QtGui.QColor(150, 150, 150), 1.2, QtCore.Qt.DashLine); brush = QtGui.QBrush(QtGui.QColor(200, 200, 200, 30))
            elif sel:
                # Solo al seleccionar se dibuja borde (rojo) para verla; el resto sin borde.
                pen = QtGui.QPen(QtGui.QColor(255, 40, 40), 2.0); brush = QtGui.QBrush(fill_sel)
            else:
                pen = QtGui.QPen(QtCore.Qt.NoPen); brush = QtGui.QBrush(fill_full)
            pen.setCosmetic(True); it = sc.addPolygon(qp, pen, brush); it.setZValue(Z_ERASE); self._overlay.append(it)
            if sel and self.mode == "move": self._handles(rg["pts"])
        # utilidades (con selección múltiple se resaltan todas las seleccionadas)
        multi = set(self._selected_pipe_rows()) if hasattr(self, "pipe_list") else set()
        for i, p in enumerate(self.pipes):
            if not p.get("pts"): continue               # tramos importados (world): no se dibujan
            sel = (i == self.sel_pipe) or (len(multi) > 1 and i in multi)
            # Dibujo la polilínea del pipe con arcos REALES sustituyendo cada
            # esquina que tenga un elemento curvo — mismo radio y tangencia
            # que el plugin usará en Civil 3D.
            self._poly(self._pipe_display_pts(p), layer_qcolor(p["layer"]),
                       4.0 if sel else 2.0, z=Z_MARK)
            if sel and self.mode == "move": self._handles(p["pts"])
            if sel and 0 <= self.sel_seg_idx < len(p["pts"]) - 1:
                a, b = p["pts"][self.sel_seg_idx], p["pts"][self.sel_seg_idx + 1]
                pen_hi = QtGui.QPen(QtGui.QColor(255, 50, 220), 6.0); pen_hi.setCosmetic(True)
                it = sc.addLine(a[0], a[1], b[0], b[1], pen_hi)
                it.setZValue(Z_HANDLE + 1); self._overlay.append(it)
                dot_pen = QtGui.QPen(QtGui.QColor(20, 20, 20), 1.4); dot_pen.setCosmetic(True)
                for (vx, vy) in (a, b):
                    it2 = sc.addEllipse(vx - 7, vy - 7, 14, 14, dot_pen, QtGui.QBrush(QtGui.QColor(255, 50, 220)))
                    it2.setZValue(Z_HANDLE + 1); self._overlay.append(it2)
            # Etiquetas T1, T2… encima de cada tramo cuando el pipe tiene
            # activada la edición por tramo. Se dibujan aunque el pipe no
            # esté seleccionado, así el usuario ve la numeración en todo
            # momento. Solo visual — NO se exportan al DXF (dxf_export lee
            # self.pipes, no la escena Qt).
            if p.get("seg_edit_enabled") and len(p["pts"]) >= 3:
                for si in range(len(p["pts"]) - 1):
                    (x1, y1), (x2, y2) = p["pts"][si], p["pts"][si + 1]
                    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    self._seg_label(sc, f"T{si + 1}", mx, my,
                                    layer_qcolor(p["layer"]))
        self._poly(self.cur_pts, layer_qcolor(self._ext_layer or self.active_layer()), 2.0, dots=True, z=Z_MARK)
        # centerlines de referencia (para georreferenciar) — magenta punteado,
        # bien distinto de las utilidades para no confundirlos a simple vista.
        cl_color = QtGui.QColor(255, 60, 220)
        for i, c in enumerate(self.ref_centerlines):
            sel = (i == self.sel_cl)
            self._poly(c.get("pts") or [], cl_color, 7.0 if sel else 2.0, z=Z_MARK, dash=True)
        self._poly(self._cl_pts, cl_color, 2.0, dots=True, z=Z_MARK, dash=True)
        # leaders
        anno = aci_qcolor(8)
        for i, ld in enumerate(self.leaders):
            if not (ld.get("arrow") and ld.get("tp")): continue
            col = QtGui.QColor(120, 220, 120) if i == self.sel_leader else anno
            geo = self._leader_geo(ld)
            for s in geo["segs"]: self._poly(s, col, 1.6, z=Z_MARK)
            self._arrow(ld["arrow"], geo["segs"][0][1], col)   # punta orientada a lo largo de la línea
            if i == self.sel_leader and self.mode == "move" and ld.get("simple"):
                self._handles(geo["segs"][0])                  # vértices editables (cabeza / bisagra / final)
            if ld["text"]:                                     # Leader simple no lleva texto
                t = sc.addText(ld["text"]); t.setDefaultTextColor(col); t.document().setDocumentMargin(0)
                f = t.font(); f.setPixelSize(int(geo["H"])); t.setFont(f)
                if geo["rot"]: t.setRotation(geo["rot"])
                t.setPos(geo["label_pos"][0], geo["label_pos"][1]); t.setZValue(Z_MARK); self._overlay.append(t)
        # buzones — círculo relleno con el color del pipe al que pertenecen.
        # Se dibuja por encima de las utilidades (mismo z que MARK). Si show_bz_labels
        # está activo, el código se dibuja al lado con una fuente pequeña blanca.
        self._draw_structures()
        # Marcas de conflicto: pares de segmentos que se cruzan geométricamente
        # (dos utilidades pasando una por encima de la otra sin ser juntura).
        self._draw_pipe_conflicts()
        # Accesorios de presión (codo/Tee/Wye/cruz) con su ángulo + normativas.
        self._draw_accesorios()
        # textos
        for i, tm in enumerate(self.text_marks):
            t = sc.addText(tm["text"]); t.setDefaultTextColor(QtGui.QColor(120, 220, 120)); t.document().setDocumentMargin(0)
            hpx = self._px_for_ft(tm["size_ft"]) if "size_ft" in tm else tm.get("h", 16)
            f = t.font(); f.setPixelSize(max(6, int(hpx)))
            if tm.get("font"): f.setFamily(tm["font"])
            f.setBold(bool(tm.get("bold"))); t.setFont(f)
            t.setPos(tm["pos"][0], tm["pos"][1])
            if tm.get("rot"): t.setRotation(-tm["rot"])       # rot en grados CCW; Qt gira en sentido horario
            t.setZValue(Z_MARK); self._overlay.append(t)
            if i == self.sel_text and self._current_tab() == TAB_TEXT:
                br = t.boundingRect(); pen = QtGui.QPen(QtGui.QColor(255, 180, 40)); pen.setCosmetic(True)
                rit = sc.addRect(tm["pos"][0], tm["pos"][1], br.width(), br.height(), pen); rit.setZValue(Z_MARK); self._overlay.append(rit)

    def _reindex_cross_connections_on_pipe_delete(self, deleted_idx):
        """Al borrar una utilidad se corren TODOS los índices posteriores:
        pipe #k con k > deleted_idx pasa a ser k-1. Actualizamos las
        conexiones aprobadas (`cross_connections`) para reflejar eso:
          - Se DESCARTA la que referencia a la pipe borrada (queda huérfana).
          - En las demás, si pipe_a > deleted_idx se le resta 1 (idem pipe_b)."""
        if not getattr(self, "cross_connections", None): return
        nuevas = []
        for c in self.cross_connections:
            a, b = int(c.get("pipe_a", -1)), int(c.get("pipe_b", -1))
            if a == deleted_idx or b == deleted_idx: continue
            if a > deleted_idx: a -= 1
            if b > deleted_idx: b -= 1
            c["pipe_a"] = a; c["pipe_b"] = b
            nuevas.append(c)
        self.cross_connections = nuevas

    def _prune_stale_cross_connections(self):
        """Filtro defensivo: quita conexiones aprobadas que ya no tienen
        sentido geométrico (la pipe referenciada ya no existe o los segmentos
        de las dos tuberías ya no se cruzan cerca del punto guardado). Se
        corre antes de exportar y antes de dibujar, para que nunca se cuele
        al DXF un cruce fantasma que quedó del historial. Devuelve cuántas
        conexiones se descartaron."""
        conns = getattr(self, "cross_connections", None) or []
        if not conns: return 0
        # Tolerancia en pixeles del lienzo (mismo criterio que _draw).
        # Como aquí no dependemos del zoom, usamos una tolerancia fija amplia
        # (~5 unidades del lienzo, suficiente porque el punto se guardó en
        # las mismas coords).
        TOL = 6.0
        keep = []
        for c in conns:
            try:
                a = int(c["pipe_a"]); b = int(c["pipe_b"])
                cx = float(c["x"]); cy = float(c["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= a < len(self.pipes) and 0 <= b < len(self.pipes)):
                continue
            if a == b:
                continue
            # Solo redes a presión: una aprobación vieja entre tuberías de
            # gravedad/conduit ya no se ve en el lienzo; no debe llegar al DXF.
            if (self._pipe_net_kind(self.pipes[a]) != "pressure"
                    or self._pipe_net_kind(self.pipes[b]) != "pressure"):
                continue
            pa = self.pipes[a].get("pts") or []
            pb = self.pipes[b].get("pts") or []
            if len(pa) < 2 or len(pb) < 2:
                continue
            # ¿Existe algún par de segmentos (uno de A, otro de B) que se
            # crucen en el interior cerca de (cx, cy)?
            hallado = False
            for i in range(len(pa) - 1):
                a1, a2 = pa[i], pa[i + 1]
                for j in range(len(pb) - 1):
                    b1, b2 = pb[j], pb[j + 1]
                    cp = self._seg_inter_pts(a1, a2, b1, b2)
                    if cp is None: continue
                    if (cp[0] - cx) ** 2 + (cp[1] - cy) ** 2 <= TOL * TOL:
                        hallado = True
                        break
                if hallado: break
            if hallado:
                keep.append(c)
        removed = len(conns) - len(keep)
        if removed > 0:
            self.cross_connections = keep
        return removed

    @staticmethod
    def _seg_inter_pts(p1, p2, p3, p4):
        """Intersección de dos segmentos (incluyendo extremos), o None.
        Acepta t/u en [0, 1] con pequeña tolerancia, para que también cuenten
        cruces donde un extremo de un segmento cae sobre el otro o donde los
        extremos coinciden — el usuario ve ese contacto físico como cruce
        aunque no sea intersección estrictamente interior."""
        x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-9: return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
        eps = 1e-6
        if not (-eps <= t <= 1 + eps and -eps <= u <= 1 + eps): return None
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    def _pipe_z_at(self, pipe_idx, seg_idx, x, y):
        """Devuelve la cota Z interpolada de la tubería `pipe_idx` en el punto
        (x, y) que se sabe que cae en el segmento `seg_idx` (entre pts[seg_idx]
        y pts[seg_idx+1]). Usa las cotas por vértice (VertexInv/VertexInvIn)
        con el mismo criterio que `interp_vertex_z`. Cuando la pipe no tiene
        `inv_start`/`inv_end` (típico de tuberías recién dibujadas), asume Z=0
        — mismo valor que muestra el spinbox de la UI por defecto."""
        if not (0 <= pipe_idx < len(self.pipes)): return None
        p = self.pipes[pipe_idx]
        pts = p.get("pts") or []
        if seg_idx < 0 or seg_idx >= len(pts) - 1: return None
        n = len(pts)
        zs = p.get("inv_start"); ze = p.get("inv_end")
        # None → 0.0 (coincide con el valor por defecto que ve el usuario).
        if zs is None: zs = 0.0 if ze is None else ze
        if ze is None: ze = zs
        zs = float(zs); ze = float(ze)
        # Cotas por tramo: el modelo usa DOS diccionarios independientes
        # —vertex_inv_out (cota de SALIDA de cada vértice = "Inicio" del tramo
        # que sale) y vertex_inv_in (cota de ENTRADA = "Fin" del tramo que
        # llega)—. Antes esto leía el `vertex_inv` viejo (un solo dict), que
        # `migrate_vertex_inv` YA elimina con pop → quedaba siempre {} y la
        # detección de conflictos ignoraba las ediciones de la tabla "Cotas por
        # tramo" (solo reaccionaba a inv_start/inv_end). Ahora se replica EXACTO
        # el criterio de _rebuild_seg_inv_table para que el cruce se reclasifique
        # igual que lo muestra la tabla.
        def _norm(d): return {int(k): float(v) for k, v in (d or {}).items()}
        ov_out = _norm(p.get("vertex_inv_out"))
        ov_in  = _norm(p.get("vertex_inv_in"))
        if not ov_out and not ov_in:
            # Pipe aún sin migrar (no pasó por la tabla): usa el dict viejo.
            viejo = _norm(p.get("vertex_inv"))
            ov_out = dict(viejo); ov_in = dict(viejo)
        auto_out = model_ops.interp_vertex_z(pts, zs, ze, ov_out)
        auto_in  = model_ops.interp_vertex_z(pts, zs, ze, ov_in)
        v0, v1 = seg_idx, seg_idx + 1
        # z al INICIO del segmento = cota de salida del vértice v0.
        z0 = zs if v0 == 0 else ov_out.get(v0, auto_out[v0])
        # z al FIN del segmento = cota de entrada del vértice v1.
        z1 = ze if v1 == n - 1 else ov_in.get(v1, auto_in[v1])
        # Interpolación lineal a lo largo del segmento.
        a = pts[seg_idx]; b = pts[seg_idx + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-9: return z0
        t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / seg_len2))
        return z0 + (z1 - z0) * t

    def _on_toggle_show_conflicts(self, on):
        """Toggle del checkbox de la barra inferior 'Mostrar cruces/conflictos':
        redibuja el lienzo para que las marcas aparezcan/desaparezcan de inmediato.
        Preferencia persistida en QSettings (Configuración → app), reconstruida
        al iniciar la app."""
        try:
            s = QtCore.QSettings("pdf-to-cad", "app")
            s.setValue("show_conflicts_v2", bool(on))
        except Exception: pass
        self._redraw()

    def _draw_structures(self):
        """Dibuja cada buzón como un círculo relleno con el color del pipe al que
        pertenece (mismo vértice). Si show_bz_labels está activo, escribe el código
        del buzón al lado del círculo."""
        if not self.structures: return
        sc = self.canvas.scene(); tol2 = 14.0 ** 2
        # Precomputa color por buzón: mira los pipes NO importados y toma el layer
        # del primero cuyo vértice coincida (dist² ≤ tol²).
        def _color_for(s):
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: return QtGui.QColor(200, 200, 200)
            if s.get("world") or s.get("net") == "pressure":
                # Para presión (sin vértice de pipe dibujado) o buzones importados,
                # gris claro (no hay línea de referencia visible).
                pass
            for p in self.pipes:
                if p.get("world") or not p.get("pts"): continue
                for (vx, vy) in p["pts"]:
                    if (vx - sx) ** 2 + (vy - sy) ** 2 <= tol2:
                        return layer_qcolor(p["layer"])
            if s.get("standalone"):
                return layer_qcolor(s.get("utility") or "ELECTRICO")
            return QtGui.QColor(180, 180, 180)     # buzón sin pipe cercano (raro)
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.2); pen.setCosmetic(True)
        pen_sel = QtGui.QPen(QtGui.QColor(255, 220, 40), 2.5); pen_sel.setCosmetic(True)
        R = 6.0                                     # radio en px (independiente del zoom por _cosmetic pen)
        for i, s in enumerate(self.structures):
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if s.get("world"): continue             # los importados (Excel) están en coord mundo, no lienzo
            if s.get("hidden"): continue             # ocultado por el usuario — sigue en la lista, no en el lienzo
            is_curve = bool(s.get("curve"))
            col = QtGui.QColor(190, 90, 220) if is_curve else _color_for(s); brush = QtGui.QBrush(col)
            selected = i == getattr(self, "sel_curve" if is_curve else "sel_bz", -1)
            use_pen = pen_sel if selected else pen
            r_use = R + 1.5 if selected else R
            # El arco real ya se dibuja como parte de la polilínea del pipe
            # (ver _pipe_display_pts). Para el marcador de la curva, lo
            # colocamos EN el arco (punto medio) — así queda visualmente
            # pegado a la geometría y no "volando" en la esquina teórica,
            # que puede estar lejos del arco cuando el radio es grande.
            # Si la curva está seleccionada, además repintamos el arco encima
            # en amarillo grueso para que sea inequívoco cuál está activa.
            mx, my = sx, sy   # fallback si no hay pipe / geometría inválida
            if is_curve:
                pipe = self._pipe_at_vertex(sx, sy)
                # Arco REAL con el radio explícito (o el auto = 6 × diámetro). La
                # matemática (tangencias, centro, discretización, cap por doble
                # curva) vive en _curve_arc_info + _arc_polyline: envuelve al
                # model_ops.fillet_geo (base pura) añadiéndole el cap 0.48 si el
                # vecino también es curva y el auto-radio. El pipe (ver
                # _pipe_display_pts) ya dibuja este mismo arco integrado en su
                # polilínea; aquí sólo pintamos:
                #   · el marcador (pegado al arco, no volando en la esquina),
                #   · el resalte amarillo cuando la curva está seleccionada,
                #   · los puntos de tangencia (con línea discontinua si el
                #     radio pedido no entró y el plugin lo va a recortar).
                info = self._curve_arc_info(s, pipe) if pipe else None
                if info is not None:
                    arc_pts = self._arc_polyline(info, n_per_90=24)
                    if arc_pts:
                        mx, my = arc_pts[len(arc_pts) // 2]
                    clamped = bool(info.get("clamped"))
                    if selected:
                        hi_col = QtGui.QColor(255, 220, 40)
                        hi_pen = QtGui.QPen(hi_col, 6.0); hi_pen.setCosmetic(True)
                        hi_pen.setCapStyle(QtCore.Qt.RoundCap)
                        if clamped: hi_pen.setStyle(QtCore.Qt.DashLine)
                        path = QtGui.QPainterPath()
                        path.moveTo(*arc_pts[0])
                        for (ax, ay) in arc_pts[1:]:
                            path.lineTo(ax, ay)
                        it = sc.addPath(path, hi_pen)
                        it.setZValue(Z_MARK + 1); self._overlay.append(it)
                        arc_col = hi_col
                    else:
                        arc_col = col
                    # Puntos de tangencia — muestran dónde arranca/termina el arco
                    # sobre cada recta vecina (útil para saber si el radio "cabe").
                    for q in (info["p1"], info["p2"]):
                        it = sc.addEllipse(q[0] - 3, q[1] - 3, 6, 6, use_pen, QtGui.QBrush(arc_col))
                        it.setZValue(Z_MARK + 1); self._overlay.append(it)
            it = sc.addEllipse(mx - r_use, my - r_use, 2 * r_use, 2 * r_use, use_pen, brush)
            it.setZValue(Z_MARK + 1); self._overlay.append(it)
            # Bóveda reconocida (feature de reconocimiento del PDF, dev_santos_v2):
            # su contorno real a escala, con el color de la línea y la medida al
            # seleccionarla.
            outline = s.get("outline")
            if outline and len(outline) >= 3:
                poly = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in outline])
                open_pen = QtGui.QPen(QtGui.QColor(255, 220, 40) if selected else col, 2 if selected else 1.5)
                open_pen.setCosmetic(True)
                fill = QtGui.QColor(col); fill.setAlpha(45)
                it = sc.addPolygon(poly, open_pen, QtGui.QBrush(fill)); it.setZValue(Z_MARK); self._overlay.append(it)
                if selected and s.get("width_ft") and s.get("length_ft"):
                    t = sc.addText(f"{s['width_ft']:.1f} × {s['length_ft']:.1f} ft")
                    t.setDefaultTextColor(QtGui.QColor(255, 220, 40))
                    t.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
                    t.setPos(max(x for x, _ in outline) + 4, min(y for _, y in outline))
                    t.setZValue(Z_MARK + 2); self._overlay.append(t)
            if self.show_bz_labels and s.get("cod"):
                t = sc.addText(s["cod"]); t.setDefaultTextColor(QtGui.QColor(180, 180, 180))
                t.document().setDocumentMargin(0)
                f = t.font(); f.setPixelSize(11); f.setBold(True); t.setFont(f)
                # Etiqueta también sigue el marcador (mx, my) — así queda
                # junto a la curva y no en la esquina teórica.
                t.setPos(mx + R + 2, my - R - 2); t.setZValue(Z_MARK + 1); self._overlay.append(t)

    def _handles(self, pts):
        sc = self.canvas.scene(); pen = QtGui.QPen(QtGui.QColor(255, 255, 255)); pen.setCosmetic(True)
        for (vx, vy) in pts:
            it = sc.addRect(vx - 5, vy - 5, 10, 10, pen, QtGui.QBrush(QtGui.QColor(255, 180, 40)))
            it.setZValue(Z_HANDLE); self._overlay.append(it)

    def _seg_label(self, sc, text, cx, cy, color, px=24, halo=5.0):
        """Etiqueta de tramo ("T1", "T2"…) centrada sobre el punto (cx, cy):
        relleno del COLOR DE LA LÍNEA con CONTORNO NEGRO GRUESO, al doble del
        tamaño que tenía antes (24px vs 12px).

        Se dibuja en DOS CAPAS porque un QGraphicsTextItem no admite contorno,
        y un solo QGraphicsPathItem con pen+brush tampoco sirve: Qt traza el
        pen DESPUÉS de rellenar y centrado sobre el borde del glifo, así que un
        pen grueso se come el relleno y la etiqueta sale casi negra (verificado
        renderizando las variantes). Con dos capas —silueta negra engordada
        detrás, relleno de color encima— el contorno es grueso de verdad y el
        color queda limpio.

        Escala con el zoom, igual que las etiquetas de buzón de
        _draw_structures — misma convención en todo el lienzo.
        """
        font = QtGui.QFont(); font.setPixelSize(px); font.setBold(True)
        path = QtGui.QPainterPath()
        path.addText(0.0, 0.0, font, text)            # baseline en (0,0)
        w = QtGui.QFontMetricsF(font).horizontalAdvance(text)
        x, y = cx - w / 2.0, cy - 8.0                 # centrado y por encima
        halo_pen = QtGui.QPen(QtGui.QColor(0, 0, 0), halo)
        halo_pen.setJoinStyle(QtCore.Qt.RoundJoin); halo_pen.setCapStyle(QtCore.Qt.RoundCap)
        for pen, brush in ((halo_pen, QtGui.QBrush(QtGui.QColor(0, 0, 0))),
                           (QtGui.QPen(QtCore.Qt.NoPen), QtGui.QBrush(color))):
            it = sc.addPath(path, pen, brush)
            it.setPos(x, y); it.setZValue(Z_MARK + 2); self._overlay.append(it)

    def _poly(self, pts, color, width, dots=False, z=Z_MARK, dash=False):
        sc = self.canvas.scene(); pen = QtGui.QPen(color, width); pen.setCosmetic(True)
        if dash: pen.setStyle(QtCore.Qt.DashLine)
        for a, b in zip(pts, pts[1:]):
            it = sc.addLine(a[0], a[1], b[0], b[1], pen); it.setZValue(z); self._overlay.append(it)
        if dots:
            for (x, y) in pts:
                it = sc.addEllipse(x - 3, y - 3, 6, 6, pen, QtGui.QBrush(color)); it.setZValue(z); self._overlay.append(it)

    def _arrow(self, a, b, color):
        ang = math.atan2(a[1] - b[1], a[0] - b[0]); L = self.leader_hpx * 0.8
        p1 = (a[0] - L * math.cos(ang - 0.4), a[1] - L * math.sin(ang - 0.4))
        p2 = (a[0] - L * math.cos(ang + 0.4), a[1] - L * math.sin(ang + 0.4))
        poly = QtGui.QPolygonF([QtCore.QPointF(*a), QtCore.QPointF(*p1), QtCore.QPointF(*p2)])
        it = self.canvas.scene().addPolygon(poly, QtGui.QPen(color), QtGui.QBrush(color)); it.setZValue(Z_MARK); self._overlay.append(it)
