"""Conflictos entre tuberías (alertas del lienzo) y sus mensajes.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class ConflictosMixin:
    def _draw_pipe_conflicts(self):
        """Detecta y dibuja marcas en los cruces geométricos entre segmentos
        de tuberías. Se distinguen tres estados (colores distintos):

        - ROJO «!»  = CONFLICTO físico real (dos tuberías con la MISMA cota
          en el punto de cruce → chocan). Requiere corregir la geometría o
          alguna cota. NO se ofrece conexión.
        - AZUL «↕»  = SUGERENCIA de conexión: cotas distintas (una pasa por
          encima/debajo de la otra sin chocar). Se puede aprobar con click
          para que el plugin dibuje una vertical + válvula uniéndolas.
        - VERDE «✓» = Sugerencia ya APROBADA por el usuario.

        Tolerancia de "misma cota": 0.10 ft (~1.2 pulgadas). Si a alguna de
        las dos le falta la cota, se trata como conflicto (no se puede
        confirmar que estén a alturas distintas)."""
        # Saneamos antes de dibujar por si el usuario borró/movió una pipe
        # y quedaron cruces fantasma en cross_connections.
        self._prune_stale_cross_connections()
        # Toggle del usuario en la barra inferior: si está apagado, no dibujar
        # nada, limpiar hits (para que un click no active nada) y quitar el
        # contador de la barra de estado. El resto de la app sigue igual —
        # los cross_connections aprobados se conservan (afectan el DXF).
        if hasattr(self, "chk_show_conflicts") and not self.chk_show_conflicts.isChecked():
            self._conflict_hits = []
            self._exceso_hits = []
            self._escalon_hits = []
            self._codos_hits = []
            self._retorno_hits = []
            self._pendiente_hits = []
            self._inclinada_hits = []
            self._redes_hits = []
            self._choque_hits = []
            if hasattr(self, "lbl_info"):
                # Deja el texto de info normal (sin el contador de cruces)
                pass
            return
        sc = self.canvas.scene()

        def _seg_inter(p1, p2, p3, p4):
            # Acepta intersecciones en los extremos también: si dos utilidades
            # se TOCAN (un extremo cae sobre el otro segmento o los extremos
            # coinciden) también cuenta como cruce físico.
            x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-9: return None
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
            u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
            eps = 1e-6
            if not (-eps <= t <= 1 + eps and -eps <= u <= 1 + eps): return None
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

        # Solo redes a PRESIÓN (agua, gas): conflictos, sugerencias/aprobaciones
        # de vertical y «redes distintas» no aplican a gravedad (drenaje,
        # alcantarillado: lo resuelve el buzón) ni a conduit (eléctrico, telecom).
        # Regla del usuario 2026-09-28. Las alertas rojas ya eran solo de presión.
        from nucleo.model import network_kind as _nk
        segs = []
        for i, p in enumerate(self.pipes):
            lay = p.get("layer", "")
            if _nk(lay) != "pressure":
                continue
            pts = p.get("pts") or []
            for k in range(len(pts) - 1):
                segs.append((i, k, pts[k], pts[k + 1], lay))

        # Cada hit lleva su "estado" ya clasificado.
        self._conflict_hits = []
        self._pendiente_hits = []   # extremo con extremo sin altura para vertical (▲ rojo)
        approvals = {(int(c["pipe_a"]), int(c["pipe_b"]), round(float(c["x"]), 3), round(float(c["y"]), 3))
                      for c in (getattr(self, "cross_connections", None) or [])}
        Z_TOL = 0.10        # ft — misma cota si |za - zb| <= Z_TOL
        R_PX = 7.0
        red_col   = QtGui.QColor(180, 20, 20)
        blue_col  = QtGui.QColor(30, 90, 220)
        green_col = QtGui.QColor(30, 160, 60)
        yellow_br = QtGui.QBrush(QtGui.QColor(255, 235, 60))
        cyan_br   = QtGui.QBrush(QtGui.QColor(180, 220, 255))
        greenbr   = QtGui.QBrush(QtGui.QColor(180, 240, 200))
        ign = QtWidgets.QGraphicsItem.ItemIgnoresTransformations
        n_conf = n_sug = n_ap = 0

        # Puntos donde se juntan más tramos de los que el plugin une con un
        # accesorio (5+): ahí Civil 3D no dibujará ninguna pieza. Se marcan con
        # un triángulo rojo propio y se omiten los círculos de cruce de ese
        # punto, que solo se apilaban sin decir lo importante.
        tol_junta = 0.5 / self.scale * self.zoom if self.scale else 3.0   # 0.5 ft, como el plugin
        self._exceso_hits = model_ops.junturas_excedidas(self.pipes, self._pipe_z_at, tol_junta)
        tol_omitir2 = (tol_junta * 2.0) ** 2

        def _en_exceso(x, y):
            return any((e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol_omitir2 for e in self._exceso_hits)

        # Redes distintas que chocan (misma cota): el plugin nunca las une, así
        # que en vez del círculo de conflicto van con la alerta roja. Un mismo
        # punto puede salir de varios pares de tramos: se reporta una sola vez.
        self._redes_hits = []

        def _registrar_redes(x, y, red_a, red_b):
            if any((e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol_omitir2 for e in self._redes_hits):
                return
            self._redes_hits.append({"x": x, "y": y, "a": red_a, "b": red_b})

        for a in range(len(segs)):
            ia, ka, a1, a2, la = segs[a]
            for b in range(a + 1, len(segs)):
                ib, kb, b1, b2, lb = segs[b]
                if ia == ib: continue
                cp = _seg_inter(a1, a2, b1, b2)
                if cp is None: continue
                cx, cy = cp
                if _en_exceso(cx, cy): continue
                za = self._pipe_z_at(ia, ka, cx, cy)
                zb = self._pipe_z_at(ib, kb, cx, cy)
                aprobado = ((min(ia, ib), max(ia, ib), round(cx, 3), round(cy, 3)) in approvals)
                # Clasificación del cruce.
                same_layer = (la == lb)
                if za is None or zb is None:
                    estado = "conflicto"       # sin cotas → tratar como conflicto
                elif abs(za - zb) <= Z_TOL:
                    estado = "conflicto"       # misma cota → chocan
                elif not same_layer:
                    continue                   # distinta utilidad + distinta cota → normal, no marcar
                else:
                    estado = "aprobado" if aprobado else "sugerencia"
                    # Extremo con extremo sin altura para la vertical: no hay nada
                    # que aprobar, el plugin los une con pendiente (ver mensaje).
                    tol_u = 0.5 / self.scale * self.zoom if self.scale else 3.0
                    sin_esp = model_ops.union_con_pendiente(
                        self.pipes[ia], self.pipes[ib], (cx, cy), za, zb, tol_u,
                        self.scale / self.zoom if self.scale and self.zoom else 0.0)
                    if sin_esp:
                        tol2_u = tol_u * tol_u
                        if not any((e["x"] - cx) ** 2 + (e["y"] - cy) ** 2 <= tol2_u
                                   for e in self._pendiente_hits):
                            self._pendiente_hits.append({"x": cx, "y": cy, "ia": ia, "ib": ib, "r": sin_esp})
                        continue
                if estado == "conflicto" and za is not None and zb is not None and not same_layer:
                    # Utilidades distintas (agua × drenaje…) nunca se unen. La MISMA
                    # utilidad con nombres de red distintos sí: el plugin las junta
                    # en una sola red (ver model_ops.red_civil_de_union).
                    red_a, red_b = model_ops.red_de(self.pipes[ia]), model_ops.red_de(self.pipes[ib])
                    _registrar_redes(cx, cy, self._etq(self.pipes[ia]), self._etq(self.pipes[ib]))
                    continue
                self._conflict_hits.append((cx, cy, ia, ib, ka, kb, za, zb, estado))
                if estado == "conflicto":  n_conf += 1
                elif estado == "aprobado": n_ap += 1
                else:                       n_sug += 1
                # Dibujo según estado.
                if estado == "conflicto":
                    pen = QtGui.QPen(red_col, 2.0); pen.setCosmetic(True)
                    brush = yellow_br; text = "!"; text_col = red_col
                elif estado == "aprobado":
                    pen = QtGui.QPen(green_col, 2.0); pen.setCosmetic(True)
                    brush = greenbr; text = "✓"; text_col = green_col
                else:  # sugerencia
                    pen = QtGui.QPen(blue_col, 2.0); pen.setCosmetic(True)
                    brush = cyan_br; text = "↕"; text_col = blue_col
                circ = sc.addEllipse(-R_PX, -R_PX, R_PX * 2, R_PX * 2, pen, brush)
                circ.setPos(cx, cy); circ.setFlag(ign)
                circ.setZValue(Z_HANDLE + 5); self._overlay.append(circ)
                t = sc.addText(text); t.setDefaultTextColor(text_col)
                f = t.font(); f.setPixelSize(11); f.setBold(True); t.setFont(f)
                t.document().setDocumentMargin(0)
                br = t.boundingRect()
                t.setPos(cx, cy); t.setFlag(ign)
                t.setTransform(QtGui.QTransform().translate(-br.width() / 2, -br.height() / 2))
                t.setZValue(Z_HANDLE + 6); self._overlay.append(t)
                # Tooltip por estado.
                z_desc = ""
                if za is not None and zb is not None:
                    z_desc = (f"\nZ «{self._etq(self.pipes[ia])}» = {za:.2f} ft   |   "
                              f"Z «{self._etq(self.pipes[ib])}» = {zb:.2f} ft (Δ = {abs(za - zb):.2f} ft)")
                elif za is not None or zb is not None:
                    z_desc = "\n" + _tr("(a una de las dos le falta la cota — no se puede confirmar Δ)")
                else:
                    z_desc = "\n" + _tr("(sin cotas en ninguna — no se puede confirmar Δ)")
                union = self._union_civil(ia, ib, cx, cy, za, zb)
                if union:
                    circ.setToolTip(tooltip_bloque(union))
                    continue
                if estado == "conflicto":
                    tip = "⚠ " + _tr("CONFLICTO — cruce con la misma cota (las tuberías chocan). "
                                     "Revisa la geometría o las cotas.")
                elif estado == "aprobado":
                    tip = "✓ " + _tr("Conexión vertical aprobada — al importar se dibuja una tubería "
                                     "vertical uniendo las dos cotas.")
                else:
                    tip = "↕ " + _tr("Sugerencia — cotas distintas, pasan una por encima de la otra. "
                                     "Click para conectarlas con una tubería vertical.")
                ea, eb = self._etq(self.pipes[ia]), self._etq(self.pipes[ib])
                pair = (_tr("Dos tramos de «{capa}»").format(capa=ea) if ea == eb
                        else f"«{ea}» × «{eb}»")
                circ.setToolTip(tooltip_bloque(f"{tip}\n{pair}{z_desc}"))

        # Triángulo rojo con «!» blanco: algo que Civil 3D NO dibujará como está
        # en la app. El mensaje (tooltip y clic) dice qué pasa y cómo quedará.
        R_TRI = 10.0
        tri = QtGui.QPolygonF([QtCore.QPointF(0, -R_TRI),
                               QtCore.QPointF(R_TRI * 0.95, R_TRI * 0.75),
                               QtCore.QPointF(-R_TRI * 0.95, R_TRI * 0.75)])

        def _alerta_roja(x, y, mensaje):
            pen = QtGui.QPen(QtGui.QColor(120, 0, 0), 1.5); pen.setCosmetic(True)
            it = sc.addPolygon(tri, pen, QtGui.QBrush(QtGui.QColor(215, 25, 25)))
            it.setPos(x, y); it.setFlag(ign)
            it.setZValue(Z_HANDLE + 7); self._overlay.append(it)
            t = sc.addText("!"); t.setDefaultTextColor(QtGui.QColor(255, 255, 255))
            f = t.font(); f.setPixelSize(12); f.setBold(True); t.setFont(f)
            t.document().setDocumentMargin(0)
            br = t.boundingRect()
            t.setPos(x, y); t.setFlag(ign)
            t.setTransform(QtGui.QTransform().translate(-br.width() / 2, -br.height() / 2 + 2))
            t.setZValue(Z_HANDLE + 8); self._overlay.append(t)
            it.setToolTip(tooltip_bloque(mensaje))

        for e in self._exceso_hits:
            _alerta_roja(e["x"], e["y"], self._msg_exceso(e))
        self._escalon_hits = model_ops.escalones_en_vertices(self.pipes, self._pipe_z_at)
        for e in self._escalon_hits:
            _alerta_roja(e["x"], e["y"], self._msg_escalon(e))
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0
        self._codos_hits = model_ops.tramos_cortos_entre_codos(self.pipes, ft_px) if ft_px else []
        for e in self._codos_hits:
            _alerta_roja(e["x"], e["y"], self._msg_codos(e))
        self._retorno_hits = model_ops.codos_de_retorno(self.pipes, ft_px) if ft_px else []
        for e in self._retorno_hits:
            _alerta_roja(e["x"], e["y"], self._msg_retorno(e))
        for e in self._pendiente_hits:
            _alerta_roja(e["x"], e["y"], self._msg_sin_espacio(e["ia"], e["ib"], e["r"]))
        # Conexión vertical aprobada en un quiebre sin desnivel para dos codos:
        # el plugin la resuelve con Wye inclinada + pendiente en la tubería.
        self._inclinada_hits = []
        tol_v = 0.5 / self.scale * self.zoom if self.scale else 3.0
        for (hx, hy, ia, ib, _ka, _kb, za, zb, est) in self._conflict_hits:
            if est != "aprobado" or any((e["x"] - hx) ** 2 + (e["y"] - hy) ** 2 <= tol_v * tol_v
                                        for e in self._inclinada_hits):
                continue
            r = model_ops.conexion_vertical_inclinada(self.pipes[ia], self.pipes[ib], (hx, hy), za, zb, tol_v)
            if r:
                e = {"x": hx, "y": hy, "dz": r["dz"], "min": r["min"],
                     "capa": self._etq(r["termina"])}
                self._inclinada_hits.append(e)
                _alerta_roja(hx, hy, self._msg_inclinada(e))
        for e in self._redes_hits:
            _alerta_roja(e["x"], e["y"], self._msg_redes(e))
        # Cruce completo a la misma cota sin conexión con al menos una tubería
        # que NO es a presión (drenaje, alcantarillado, eléctrico, telecom): el
        # resto de señales es solo de presión, pero un choque se avisa siempre.
        self._choque_hits = model_ops.choques_sin_conexion(
            self.pipes, self._pipe_z_at, tol_junta, self.structures)
        for e in self._choque_hits:
            _alerta_roja(e["x"], e["y"], self._msg_choque(e))

        if hasattr(self, "lbl_info"):
            partes = []
            if self._exceso_hits:
                partes.append("▲ " + _tr("{n} punto(s) con 5+ tuberías").format(n=len(self._exceso_hits)))
            if self._escalon_hits:
                partes.append("▲ " + _tr("{n} escalón(es) de cota").format(n=len(self._escalon_hits)))
            if self._inclinada_hits:
                partes.append("▲ " + _tr("{n} conexión(es) vertical(es) con pendiente").format(
                    n=len(self._inclinada_hits)))
            if self._pendiente_hits:
                partes.append("▲ " + _tr("{n} unión(es) con pendiente").format(n=len(self._pendiente_hits)))
            if self._retorno_hits:
                partes.append("▲ " + _tr("{n} codo(s) de retorno").format(n=len(self._retorno_hits)))
            if self._codos_hits:
                partes.append("▲ " + _tr("{n} tramo(s) muy corto(s) entre codos").format(n=len(self._codos_hits)))
            if self._redes_hits:
                partes.append("▲ " + _tr("{n} choque(s) entre redes distintas").format(n=len(self._redes_hits)))
            if self._choque_hits:
                partes.append("▲ " + _tr("{n} cruce(s) a la misma cota sin conexión").format(
                    n=len(self._choque_hits)))
            if n_conf > 0: partes.append("⚠ " + _tr("{n} conflicto(s)").format(n=n_conf))
            if n_sug > 0:  partes.append("↕ " + _tr("{n} sugerencia(s)").format(n=n_sug))
            if n_ap > 0:   partes.append("✓ " + _tr("{n} aprobada(s)").format(n=n_ap))
            if partes: self.lbl_info.setText(" · ".join(partes))

    @staticmethod
    def _msg_exceso(e):
        return _tr("Hay {n} tuberías en el mismo punto, no se dibujará ningún accesorio "
                   "en Civil 3D, por favor corrija el dibujo.").format(n=e["n"])

    @staticmethod
    def _msg_redes(e):
        return _tr("«{a}» y «{b}» se cruzan a la misma cota, pero son redes distintas.\n\n"
                   "En Civil 3D no se conectarán: las tuberías quedarán chocando.").format(
            a=e["a"], b=e["b"])

    def _msg_choque(self, e):
        return _tr("«{a}» y «{b}» se cruzan a la misma cota ({za:.2f} / {zb:.2f} ft) y no "
                   "se conectan: en Civil 3D quedarán chocando.\n\n"
                   "Corrige el dibujo o cambia la cota de una de las dos.").format(
            a=self._etq(self.pipes[e["ia"]]), b=self._etq(self.pipes[e["ib"]]),
            za=e["za"], zb=e["zb"])

    def _union_civil(self, ia, ib, cx, cy, za, zb):
        """Mensaje corto de lo que hará Civil 3D cuando dos tuberías de la MISMA
        utilidad a presión se tocan a la misma cota: no es un choque, el plugin
        las une con un accesorio sólido. None si no es ese caso."""
        from nucleo.model import network_kind
        pa, pb = self.pipes[ia], self.pipes[ib]
        la = pa.get("layer", "")
        if (za is None or zb is None or abs(za - zb) > 0.10 or la != pb.get("layer", "")
                or network_kind(la) != "pressure"):
            return None
        tol = 0.5 / self.scale * self.zoom if self.scale else 3.0      # 0.5 ft, como el plugin
        # El plugin une donde una tubería TERMINA sobre la otra o donde las dos
        # comparten un vértice. Un cruce en X a mitad de tramo no se une: choca.
        def _cerca(q):
            return (q[0] - cx) ** 2 + (q[1] - cy) ** 2 <= tol * tol
        pts_a, pts_b = pa.get("pts") or [], pb.get("pts") or []
        termina = any(_cerca(q) for q in (pts_a[:1] + pts_a[-1:] + pts_b[:1] + pts_b[-1:]))
        vertice_comun = any(map(_cerca, pts_a)) and any(map(_cerca, pts_b))
        if not (termina or vertice_comun):
            return None
        polis = [p.get("pts") or [] for p in self.pipes if p.get("layer", "") == la]
        tipo = model_ops.accesorio_en_punto(polis, (cx, cy), tol)
        nombres = {"codo": N_("un codo sólido"), "tee": N_("una Tee sólida"), "wye": N_("una Wye sólida"),
                   "cruz": N_("una cruz sólida"), "recto": N_("un codo sólido")}
        if tipo not in nombres:
            return None
        red = model_ops.red_civil_de_union(self.pipes, ia, ib)
        accesorio = _tr(nombres[tipo])
        try:
            d_a, d_b = float(pa.get("diam") or 0), float(pb.get("diam") or 0)
        except (TypeError, ValueError):
            d_a = d_b = 0.0
        if tipo == "codo" and d_a > 0 and d_b > 0 and abs(d_a - d_b) > 1e-6:
            # Como el plugin: codo del diámetro mayor + reducción excéntrica.
            mayor, menor = max(d_a, d_b), min(d_a, d_b)
            accesorio = _tr("un codo sólido de {d1:g}\" con reducción {d1:g}×{d2:g}\"").format(d1=mayor, d2=menor)
        elif tipo == "recto" and d_a > 0 and d_b > 0 and abs(d_a - d_b) > 1e-6:
            accesorio = _tr("una reducción {d1:g}×{d2:g}\"").format(d1=max(d_a, d_b), d2=min(d_a, d_b))
        msg = _tr("Se unen aquí a {z:.2f} ft.\n\nEn Civil 3D: {accesorio} en la red «{red}».").format(
            z=(za + zb) / 2.0, accesorio=accesorio, red=red)   # ≤0.10 ft: el plugin promedia
        na, nb = model_ops.red_de(pa), model_ops.red_de(pb)
        if na != nb:
            msg += "\n" + _tr("Tienen nombres de red distintos («{a}» / «{b}»): las dos quedan en «{red}».").format(
                a=na, b=nb, red=red)
        return msg

    @staticmethod
    def _tipo(capa):
        """Nombre visible (traducido) del tipo de utilidad de una capa interna:
        «AGUA» → «Agua» / «Water». La capa es un código interno: nunca se muestra."""
        tipo = next((_tr(lbl) for lbl, lay in TIPOS if lay == capa), capa or "?")
        return tipo.split(" (")[0]

    @staticmethod
    def _etq(p):
        """Cómo se nombra una utilidad en los mensajes: «Agua - Linea Norte»
        (tipo traducido + nombre de red si lo tiene), o solo «Agua»."""
        tipo = ConflictosMixin._tipo(p.get("layer", "?"))
        nombre = (p.get("name") or "").strip()
        return f"{tipo} - {nombre}" if nombre else tipo

    @staticmethod
    def _msg_inclinada(e):
        return _tr("Desnivel de {dz:.2f} ft: es muy poco para bajar con dos codos "
                   "(mínimo {minimo:.2f} ft).\n\n"
                   "En Civil 3D se pondrá una Wye con el ramal inclinado y la tubería "
                   "«{capa}» se modificará para que llegue con pendiente.").format(
            dz=e["dz"], minimo=e["min"], capa=e["capa"])

    def _msg_sin_espacio(self, ia, ib, r):
        """Sugerencia de vertical sin altura suficiente (extremo con extremo):
        qué hará Civil 3D en su lugar. Ver model_ops.union_con_pendiente."""
        cabecera = "⚠ " + _tr("No hay espacio para una tubería vertical: la diferencia de altura es de "
                              "{dz:.2f} ft y hacen falta al menos {minimo:.2f} ft.").format(dz=r["dz"], minimo=r["min"])
        union = _tr(N_("se unirán con un codo") if r["codo"] else N_("se unirán en línea recta"))
        if r["iguales"]:
            cuerpo = _tr("En Civil 3D: las dos tuberías miden lo mismo, así que las dos tendrán una "
                         "pendiente hasta un punto medio ({z:.2f} ft) y {union}.").format(z=r["z_union"], union=union)
        else:
            i_larga = ia if r["larga"] == "a" else ib
            tramo = r["tramo_a"] if r["larga"] == "a" else r["tramo_b"]
            cuerpo = _tr("En Civil 3D: la tubería más larga («{nombre}», tramo T{t}) tendrá una pendiente "
                         "para llegar a la más corta y {union}.").format(
                nombre=self._etq(self.pipes[i_larga]), t=tramo, union=union)
        return cabecera + "\n\n" + cuerpo

    @staticmethod
    def _msg_retorno(e):
        return _tr("Giro de {giro:.0f}° muy cerrado: el codo necesita {necesita:.2f} ft de tubería "
                   "y el tramo T{t} solo tiene {largo:.2f} ft.\n\n"
                   "En Civil 3D se pondrá un codo de retorno (curva en U) en el vértice y el tramo "
                   "T{t} se correrá {lateral:.2f} ft hacia el costado para no montarse sobre el otro "
                   "tubo.").format(giro=e["giro"], necesita=e["necesita_ft"], t=e["tramo"],
                                   largo=e["largo_ft"], lateral=e["lateral_ft"])

    @staticmethod
    def _msg_codos(e):
        return _tr("El tramo T{t} mide {largo:.2f} ft: es muy corto para dos codos "
                   "(mínimo {minimo:.2f} ft).\n\n"
                   "En Civil 3D se reemplazará por un solo codo.").format(
            t=e["tramo"], largo=e["largo_ft"], minimo=e["min_ft"])

    @staticmethod
    def _msg_escalon(e):
        return _tr("En este vértice hay un escalón: el tramo T{a} llega a {za:.2f} ft "
                   "y el T{b} sale a {zb:.2f} ft.\n\n"
                   "En Civil 3D los dos se unirán a {zc:.2f} ft (el promedio).").format(
            a=e["llega"], b=e["sale"], za=e["z_llega"], zb=e["z_sale"], zc=e["z_civil"])

    def _try_click_conflict(self, x, y):
        """Si el click está sobre una marca de cruce, abre el diálogo
        correspondiente. Devuelve True si consumió el click."""
        m11 = max(1e-6, self.canvas.transform().m11())
        tol = 10.0 / m11
        tol2 = tol * tol
        for e in getattr(self, "_exceso_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Demasiadas tuberías en un punto"),
                                              self._msg_exceso(e))
                return True
        for e in getattr(self, "_inclinada_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Conexión vertical con pendiente"),
                                              self._msg_inclinada(e))
                return True
        for e in getattr(self, "_pendiente_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Sin espacio para tubería vertical"),
                                              self._msg_sin_espacio(e["ia"], e["ib"], e["r"]))
                return True
        for e in getattr(self, "_retorno_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Codo de retorno"), self._msg_retorno(e))
                return True
        for e in getattr(self, "_codos_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Tramo muy corto entre codos"), self._msg_codos(e))
                return True
        for e in getattr(self, "_escalon_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Escalón de cota"), self._msg_escalon(e))
                return True
        for e in getattr(self, "_redes_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Redes distintas a la misma cota"),
                                              self._msg_redes(e))
                return True
        for e in getattr(self, "_choque_hits", None) or []:
            if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol2:
                QtWidgets.QMessageBox.warning(self, _tr("Tuberías que chocan"), self._msg_choque(e))
                return True
        hits = getattr(self, "_conflict_hits", None) or []
        if not hits: return False
        for h in hits:
            cx, cy = h[0], h[1]
            if (cx - x) ** 2 + (cy - y) ** 2 <= tol2:
                self._open_conflict_dialog(h)
                return True
        return False

    def _open_conflict_dialog(self, hit):
        """Según el estado del cruce:
          - "conflicto"  → sólo muestra info, no ofrece conectar.
          - "sugerencia" → pregunta si aprobar conexión vertical + válvula.
          - "aprobado"   → pregunta si retirar la aprobación."""
        cx, cy, ia, ib, ka, kb, za, zb, estado = hit
        la = self._etq(self.pipes[ia])
        lb = self._etq(self.pipes[ib])
        if not hasattr(self, "cross_connections") or self.cross_connections is None:
            self.cross_connections = []
        z_info = ""
        if za is not None and zb is not None:
            z_info = "\n\n" + _tr("Cotas en el punto de cruce:\n  • «{la}»: {za} ft\n  • «{lb}»: {zb} ft"
                         "\n  • Diferencia: {dz} ft").format(
                la=la, lb=lb, za=f"{za:.2f}", zb=f"{zb:.2f}", dz=f"{abs(za - zb):.2f}")
        else:
            z_info = "\n\n" + _tr("(⚠ falta cota en al menos una de las dos utilidades — pon cotas para "
                         "poder decidir si es conflicto o sugerencia de unión)")

        union = self._union_civil(ia, ib, cx, cy, za, zb) if estado == "conflicto" else None
        if union:
            QtWidgets.QMessageBox.information(self, _tr("Unión en Civil 3D"), union)
            return
        if estado == "conflicto":
            QtWidgets.QMessageBox.warning(
                self, _tr("Conflicto físico"),
                _tr("⚠ CONFLICTO entre «{la}» y «{lb}» — están a la MISMA cota en el cruce y chocan "
                    "geométricamente.{cotas}\n\nNo se ofrece conexión automática aquí: hay que corregir "
                    "la geometría del plano o ajustar la cota de alguna de las dos tuberías.").format(
                    la=la, lb=lb, cotas=z_info))
            return

        if estado == "aprobado":
            # Retirar aprobación.
            idx = next((i for i, c in enumerate(self.cross_connections)
                        if min(int(c["pipe_a"]), int(c["pipe_b"])) == min(ia, ib)
                        and max(int(c["pipe_a"]), int(c["pipe_b"])) == max(ia, ib)
                        and round(float(c["x"]), 3) == round(cx, 3)
                        and round(float(c["y"]), 3) == round(cy, 3)), None)
            resp = QtWidgets.QMessageBox.question(
                self, _tr("Conexión vertical ya aprobada"),
                _tr("Este cruce entre «{la}» y «{lb}» ya está marcado para conectarse con una tubería "
                    "vertical al importar.{cotas}\n\n¿Deseas RETIRAR la aprobación?").format(
                    la=la, lb=lb, cotas=z_info),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if resp == QtWidgets.QMessageBox.Yes and idx is not None:
                self.cross_connections.pop(idx)
                self._push(); self._redraw()
            return

        # sugerencia → ofrecer conectar.
        resp = QtWidgets.QMessageBox.question(
            self, _tr("Sugerencia de conexión vertical"),
            _tr("Las utilidades «{la}» y «{lb}» se cruzan pero están a cotas distintas — no chocan, "
                "una pasa por encima de la otra.{cotas}\n\n¿Quieres conectarlas con una tubería "
                "vertical al importar en Civil 3D?\n\nSí = se dibuja un tramo vertical uniendo "
                "ambas cotas.\nNo = se dejan como están (no se conectan).").format(
                la=la, lb=lb, cotas=z_info),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if resp == QtWidgets.QMessageBox.Yes:
            self.cross_connections.append({
                "x": float(cx), "y": float(cy),
                "pipe_a": int(ia), "pipe_b": int(ib),
                "z_a": (None if za is None else float(za)),
                "z_b": (None if zb is None else float(zb)),
                "valve": True,
            })
            self._push(); self._redraw()
