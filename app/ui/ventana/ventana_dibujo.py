"""Dibujo del lienzo: utilidades, conexiones cruzadas, estructuras y formas.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
import contextlib
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from ui.comun import marcas_lienzo as ML
from ui.comun import etiquetas_tramo as ET


class DibujoMixin:
    # ─────────────────────────── dibujo ───────────────────────────
    @contextlib.contextmanager
    def _redibujo_diferido(self):
        """Dentro, `_redraw` no hace nada (al abrir un proyecto, `set_mode` redibujaba y enseguida
        se redibujaba otra vez); quien lo usa redibuja UNA vez al salir."""
        previo = getattr(self, "_diferir_redibujo", False)
        self._diferir_redibujo = True
        try:
            yield
        finally:
            self._diferir_redibujo = previo

    def _redraw(self):
        if getattr(self, "_diferir_redibujo", False):
            return
        # Lo que depende SOLO del modelo (cruces, choques, accesorios, normativas, curvas) se
        # reusa mientras su firma no cambie (`nucleo/memo_modelo`): elegir, cambiar de pestaña
        # o de modo ya no lo recalcula. Y las cotas por vértice de cada utilidad, UNA vez por
        # redibujo (`model_ops.memo_cotas`). Durante el redibujo nada cambia una utilidad.
        from nucleo import memo_modelo
        if getattr(self, "_memo_redibujo", None) is None:
            self._memo_redibujo = memo_modelo.Memo()
        self._memo_redibujo.usar(self._firma_modelo())
        # Modelo grande recién cambiado: los cálculos van a un hilo y este redibujo es PROVISIONAL
        # (`calculo_fondo`, 2026-10-19); al terminar el hilo se redibuja con sus resultados.
        self._provisional = self._calculo_en_fondo()
        self._indice_redibujo = None                   # índice de tramos de ESTE redibujo
        self._en_redibujo = True
        try:
            with model_ops.memo_cotas():
                self._redraw_todo()
        finally:
            self._en_redibujo = False
            self._marcas_vigentes = False
        if self._provisional:
            self._lanzar_calculo()

    def _firma_modelo(self):
        """Todo lo que leen los cálculos que se reusan entre redibujos (`_memo`)."""
        from nucleo import memo_modelo
        from traduccion import i18n_core
        return memo_modelo.firma(self.pipes, self.structures, getattr(self, "cross_connections", None),
                                 getattr(self, "normas_aprobados", None), getattr(self, "normas_cat", None),
                                 getattr(self, "duct_banks", None), self.scale, self.zoom,
                                 getattr(i18n_core, "_current_lang", None))

    def _firma_marcas(self):
        """Lo que decide las marcas de tamaño fijo: el modelo (la firma del redibujo), la escala, el idioma
        (ya en la firma) y qué avisos se muestran."""
        m = getattr(self, "_memo_redibujo", None)
        ver = tuple(bool(a.isChecked()) for a in (getattr(self, "chk_show_conflicts", None),
                                                  getattr(self, "act_show_acc", None),
                                                  getattr(self, "act_show_normas", None)) if a is not None)
        return (getattr(m, "firma", None), ver)

    def _reusar_marca(self, clave):
        """La marca `clave` del redibujo anterior (`capa_marcas.GrupoMarcas.reusar`) o None."""
        grupo = getattr(self, "_marcas", None)
        return grupo.reusar(clave) if grupo is not None and grupo.scene is self.canvas.scene() else None

    def _guardar_marca(self, clave, it):
        grupo = getattr(self, "_marcas", None)
        if grupo is not None and grupo.scene is self.canvas.scene():
            grupo.guardar(clave, it)
        return it

    def _marca(self, it):
        """Pone una marca de tamaño fijo en pantalla en su capa (o en la escena, fuera de un redibujo)."""
        grupo = getattr(self, "_marcas", None)
        if grupo is not None and grupo.scene is self.canvas.scene():
            return grupo.agregar(it)
        self.canvas.scene().addItem(it)
        return it

    def _memo(self, clave, fn, copiar=True):
        """`fn()` reusado entre redibujos con el mismo modelo (fuera de un redibujo: siempre `fn()`)."""
        m = getattr(self, "_memo_redibujo", None)
        if m is None or not getattr(self, "_en_redibujo", False):
            return fn()
        return m.obtener(clave, fn, copiar)

    def _lineas_de_utilidad(self, i, pts):
        """Segmentos y caja de la utilidad i para `CapaLineas`; se reusan mientras su polilínea tenga los
        mismos puntos (2026-10-19: antes solo si era el MISMO objeto; al editar una utilidad se rehacían
        las 16 761)."""
        from ui.comun.capa_lineas import lineas_de
        cache = getattr(self, "_lineas_cache", None)
        if cache is None:
            cache = self._lineas_cache = {}
        hecho = cache.get(i)
        if hecho is None or (hecho[0] is not pts and hecho[0] != pts):
            hecho = cache[i] = (pts, *lineas_de(pts))   # (mismos puntos por VALOR = mismos segmentos)
        return hecho[1], hecho[2]

    def _colores_utilidades(self):
        """El color de cada capa que se usa (si cambia, la capa de líneas se rehace)."""
        return tuple(sorted((c, layer_qcolor(c).rgba()) for c in {p.get("layer") for p in self.pipes
                                                                     if p.get("pts")} if c is not None))

    def _pluma_utilidad(self, color, ancho):
        plumas = getattr(self, "_plumas_utilidad", None)
        if plumas is None:
            plumas = self._plumas_utilidad = {}
        k = (color.rgba(), ancho)
        if k not in plumas:
            pen = QtGui.QPen(color, ancho); pen.setCosmetic(True)
            plumas[k] = pen
        return plumas[k]

    def _redraw_todo(self):
        sc = self.canvas.scene()
        guardadas = set()
        # Marcas: dependen SOLO del modelo (firma), la escala, el idioma y qué avisos se muestran. Si nada
        # de eso cambió (elegir una utilidad, cambiar de modo…), las MISMAS capas siguen en la escena con
        # su imagen y su despeje; quien dibuja marcas mira `_marcas_vigentes` (2026-10-17).
        previo = getattr(self, "_marcas", None)
        firma_m = self._firma_marcas()
        self._marcas_vigentes = bool(previo is not None and firma_m[0] is not None
                                     and getattr(previo, "firma", None) == firma_m and previo.vivo(sc))
        if (getattr(self, "_provisional", False) and not self._marcas_vigentes and previo is not None
                and previo.vivo(sc)):
            self._marcas_vigentes = True                # mientras calcula el hilo, las marcas de antes a la vista
        if self._marcas_vigentes:
            guardadas |= {id(c) for c in previo.capas.values()}
        # Capa de las utilidades: con el MISMO modelo y los mismos colores sigue en la escena (2026-10-19,
        # 16 761 utilidades: Esc, elegir o cambiar de modo la rehacían entera); solo cambia la pluma de las
        # que se eligen o se sueltan.
        capa_prev = getattr(self, "_capa_lineas", None)
        clave_capa = (getattr(getattr(self, "_memo_redibujo", None), "firma", None), self._colores_utilidades())
        try:                                            # (vaciar la escena borra la capa en C++)
            viva = capa_prev is not None and capa_prev[1].scene() is sc
        except RuntimeError:
            viva = False
        reuso_capa = bool(viva and clave_capa[0] is not None and capa_prev[0] == clave_capa
                          and self.canvas.pixmap_item is not None)
        if reuso_capa:
            guardadas.add(id(capa_prev[1]))
        for it in self._overlay:
            if id(it) in guardadas:
                continue
            try:
                if it.scene() is sc: sc.removeItem(it)   # las marcas de las capas no están en la escena
            except (RuntimeError, ValueError): pass
        self._overlay = []
        # Marcas de tamaño fijo en pantalla (cruces, alertas, accesorios, avisos, C-n): las pintan
        # capas, una por Z (`ui/comun/capa_marcas`); con decenas de miles el lienzo se trababa.
        from ui.comun.capa_marcas import GrupoMarcas
        if self._marcas_vigentes:
            self._overlay += list(previo.capas.values()) + previo.todas()
        else:
            self._marcas = GrupoMarcas(sc, self.canvas.transform().m11(), self._overlay, previo=previo)
            # provisional (calculo_fondo): este grupo queda SIN marcas; sin firma, el redibujo con los
            # resultados del hilo no lo toma por vigente
            self._marcas.firma = None if getattr(self, "_provisional", False) else firma_m
        self._trazo_al_redibujar()                      # anillo y línea elástica del dibujo (ventana_trazo)
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
        ocupados = []                                   # etiquetas T1, T2… ya puestas (no se solapan)
        # Todas las utilidades en UNA capa de la escena (`ui/comun/capa_lineas`, 2026-10-18): antes un
        # ítem por segmento (~27 mil con 16 761 utilidades). Mismo orden, plumas y segmentos.
        from ui.comun.capa_lineas import CapaLineas
        elegidas = {i for i in ({self.sel_pipe} | (multi if len(multi) > 1 else set()))
                    if 0 <= i < len(self.pipes) and self.pipes[i].get("pts")}
        if reuso_capa:
            capa, con_tramos = capa_prev[1], capa_prev[3]
            for i in capa_prev[2] ^ elegidas:            # las que cambian de grosor, en su mismo lugar
                capa.cambiar_pluma(i, self._pluma_utilidad(layer_qcolor(self.pipes[i]["layer"]),
                                                           4.0 if i in elegidas else 2.0))
            indices = sorted(elegidas | con_tramos)       # lo demás del bucle solo toca a éstas
        else:
            capa, con_tramos = CapaLineas(Z_MARK), set()
            sc.addItem(capa)
            indices = range(len(self.pipes))
        self._overlay.append(capa)
        for i in indices:
            p = self.pipes[i]
            if not p.get("pts"): continue               # tramos importados (world): no se dibujan
            sel = (i == self.sel_pipe) or (len(multi) > 1 and i in multi)
            # Dibujo la polilínea del pipe con arcos REALES sustituyendo cada
            # esquina que tenga un elemento curvo — mismo radio y tangencia
            # que el plugin usará en Civil 3D.
            if not reuso_capa:
                pts = self._memo(("dibujo", i), lambda p=p: self._pipe_display_pts(p), copiar=False)
                if pts:
                    capa.agregar(*self._lineas_de_utilidad(i, pts),
                                 self._pluma_utilidad(layer_qcolor(p["layer"]), 4.0 if sel else 2.0), clave=i)
                if p.get("seg_edit_enabled") and len(p["pts"]) >= 3:
                    con_tramos.add(i)
            if sel and self.mode == "move": self._handles(p["pts"])
            elif i == self.sel_pipe:
                self._vertices_libres(p)                # eléctrico/telecom: vértices que pueden ser curva
            if sel and 0 <= self.sel_seg_idx < len(p["pts"]) - 1:
                a, b = p["pts"][self.sel_seg_idx], p["pts"][self.sel_seg_idx + 1]
                pen_hi = QtGui.QPen(QtGui.QColor(255, 50, 220), 6.0); pen_hi.setCosmetic(True)
                it = sc.addLine(a[0], a[1], b[0], b[1], pen_hi)
                it.setZValue(Z_HANDLE + 1); self._overlay.append(it)
                dot_pen = QtGui.QPen(QtGui.QColor(20, 20, 20), 1.4); dot_pen.setCosmetic(True)
                for (vx, vy) in (a, b):
                    self._overlay.append(ML.agregar(sc, vx, vy, 7, dot_pen, QtGui.QColor(255, 50, 220), Z_HANDLE + 1))
            # Etiquetas T1, T2… encima de cada tramo cuando el pipe tiene
            # activada la edición por tramo. Se dibujan aunque el pipe no
            # esté seleccionado, así el usuario ve la numeración en todo
            # momento. Solo visual — NO se exportan al DXF (dxf_export lee
            # self.pipes, no la escena Qt).
            if p.get("seg_edit_enabled") and len(p["pts"]) >= 3:
                tramos = [(f"T{si + 1}", p["pts"][si], p["pts"][si + 1]) for si in range(len(p["pts"]) - 1)]
                for texto, mx, my, dx, dy, px in ET.ubicar(tramos, ocupados, evitar=p["pts"]):
                    it = ET.EtiquetaTramo(texto, layer_qcolor(p["layer"]), px, dx, dy)
                    it.setPos(mx, my); it.setZValue(Z_MARK + 2); sc.addItem(it); self._overlay.append(it)
        if not reuso_capa:
            capa.cerrar()                               # su caja, ya con todas las utilidades
        self._capa_lineas = (clave_capa, capa, elegidas, con_tramos)
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
        # Hoja compuesta: minimapa y marcas de agua de cada hoja (`ventana_hojas`).
        self._dibujar_hojas()
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
        from nucleo import normas_aprobacion
        normas_aprobacion.reindexar(getattr(self, "normas_aprobados", None) or [], deleted_idx)
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
        return model_ops.z_en_tramo(self.pipes[pipe_idx], seg_idx, x, y)

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
        sc = self.canvas.scene()
        # Precomputa color por buzón: mira los pipes NO importados y toma el layer
        # del primero cuyo vértice coincida (dist² ≤ tol²). Vértices por celdas
        # (`indice_plano`): antes cada buzón recorría todas las utilidades.
        vert, indice = self._calcular_vertices_buzones()    # ventana_calculo

        def _color_for(s):
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: return QtGui.QColor(200, 200, 200)
            if s.get("world") or s.get("net") == "pressure":
                # Para presión (sin vértice de pipe dibujado) o buzones importados,
                # gris claro (no hay línea de referencia visible).
                pass
            cerca = indice.en_radio(sx, sy, 14.0)
            if cerca:                                # el primero en orden: la primera utilidad
                return layer_qcolor(self.pipes[vert[cerca[0]][2]]["layer"])
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
                        self._overlay.append(ML.agregar(sc, q[0], q[1], 3, use_pen, arc_col, Z_MARK + 1,
                                                        tope_px=ML.TOPE_PX / 2))
            # Radio fijo en el plano, con tope en pantalla (de cerca no tapa los tramos cortos).
            self._overlay.append(ML.agregar(sc, mx, my, r_use, use_pen, brush, Z_MARK + 1,
                                            tope_px=ML.TOPE_PX * r_use / R))
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
            self._overlay.append(ML.agregar(sc, vx, vy, 5, pen, QtGui.QColor(255, 180, 40), Z_HANDLE,
                                            tope_px=ML.TOPE_ASA_PX, cuadrada=True))

    def _poly(self, pts, color, width, dots=False, z=Z_MARK, dash=False):
        sc = self.canvas.scene(); pen = QtGui.QPen(color, width); pen.setCosmetic(True)
        if dash: pen.setStyle(QtCore.Qt.DashLine)
        for a, b in zip(pts, pts[1:]):
            it = sc.addLine(a[0], a[1], b[0], b[1], pen); it.setZValue(z); self._overlay.append(it)
        if dots:
            for (x, y) in pts:
                self._overlay.append(ML.agregar(sc, x, y, 3, pen, color, z, tope_px=ML.TOPE_PX / 2))

    def _arrow(self, a, b, color):
        ang = math.atan2(a[1] - b[1], a[0] - b[0]); L = self.leader_hpx * 0.8
        p1 = (a[0] - L * math.cos(ang - 0.4), a[1] - L * math.sin(ang - 0.4))
        p2 = (a[0] - L * math.cos(ang + 0.4), a[1] - L * math.sin(ang + 0.4))
        poly = QtGui.QPolygonF([QtCore.QPointF(*a), QtCore.QPointF(*p1), QtCore.QPointF(*p2)])
        it = self.canvas.scene().addPolygon(poly, QtGui.QPen(color), QtGui.QBrush(color)); it.setZValue(Z_MARK); self._overlay.append(it)
