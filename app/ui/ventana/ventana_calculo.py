"""Lo que el redibujo CALCULA del modelo, separado de lo que DIBUJA (2026-10-19, pedido del usuario: con
16 761 utilidades editar trababa la ventana ~8 s). Son los MISMOS cálculos, con las MISMAS claves de `_memo`,
que antes estaban dentro de `_draw_pipe_conflicts`, `_draw_accesorios` y `_draw_structures` (movidos tal cual).
Así los puede correr también `calculo_fondo.Calculo` sobre una COPIA del modelo, en otro hilo: el mismo código
da el mismo resultado, y la ventana lo retoma del memo como si lo hubiera calculado ella.

Regla: aquí solo se lee el modelo (`pipes`, `structures`, `cross_connections`, `normas_cat`,
`normas_aprobados`, `duct_banks`, `scale`, `zoom`) y se escriben resultados; nada de la escena ni de widgets.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class CalculoPlanoMixin:
    def _calcular_cruces(self):
        """Cruces de presión, juntas, redes distintas, escalones, codos, retornos y choques. Deja los
        `_*_hits` en la ventana y devuelve (filas de las marcas de cruce, n_conf, n_sug, n_ap)."""
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
        # Puntos donde se juntan más tramos de los que el plugin une con un
        # accesorio (5+): ahí Civil 3D no dibujará ninguna pieza. Se marcan con
        # un triángulo rojo propio y se omiten los círculos de cruce de ese
        # punto, que solo se apilaban sin decir lo importante.
        tol_junta = 0.5 / self.scale * self.zoom if self.scale else 3.0   # 0.5 ft, como el plugin
        self._exceso_hits = self._memo(("juntas", tol_junta), lambda: model_ops.junturas_excedidas(
            self.pipes, self._pipe_z_at, tol_junta))
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

        # Solo los pares de tramos cuyos recuadros se tocan (`indice_plano.pares_tramos`, pedido
        # 2026-10-16: con cientos de utilidades comparar todos contra todos trababa cada redibujo),
        # en el MISMO orden de siempre: mismos cruces, misma numeración.
        from nucleo.indice_plano import pares_tramos

        def _cruces():                             # solo geometría: se reusa mientras el modelo no cambie
            out = []
            for a, b in pares_tramos([(sg[2], sg[3]) for sg in segs]):
                if segs[a][0] == segs[b][0]:
                    continue
                cp = _seg_inter(segs[a][2], segs[a][3], segs[b][2], segs[b][3])
                if cp is not None:
                    out.append((a, b, cp))
            return out
        # La clasificación de cada cruce (cotas, estado y texto del globo) depende SOLO del modelo:
        # se reusa entre redibujos (con miles de cruces se rehacía en cada uno, 2026-10-17).
        def _clasificar():
            n_conf = n_sug = n_ap = 0
            filas = []                              # (x, y, estado, globo) de cada marca de cruce
            for a, b, cp in self._memo(("cruces_presion",), _cruces, copiar=False):
                ia, ka, a1, a2, la = segs[a]
                ib, kb, b1, b2, lb = segs[b]
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
                    filas.append((cx, cy, estado, tooltip_bloque(union)))
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
                filas.append((cx, cy, estado, tooltip_bloque(f"{tip}\n{pair}{z_desc}")))
            return (self._conflict_hits, self._pendiente_hits, self._redes_hits, filas, n_conf, n_sug, n_ap)
        (self._conflict_hits, self._pendiente_hits, self._redes_hits, filas,
         n_conf, n_sug, n_ap) = self._memo(("clasificar_cruces", tol_junta), _clasificar)
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0
        self._escalon_hits = self._memo(("escalones",), lambda: model_ops.escalones_en_vertices(
            self.pipes, self._pipe_z_at))
        self._codos_hits = self._memo(("codos", ft_px), lambda: model_ops.tramos_cortos_entre_codos(
            self.pipes, ft_px)) if ft_px else []
        self._retorno_hits = self._memo(("retorno", ft_px), lambda: model_ops.codos_de_retorno(
            self.pipes, ft_px)) if ft_px else []
        self._choque_hits = self._memo(("choques", tol_junta), lambda: model_ops.choques_sin_conexion(
            self.pipes, self._pipe_z_at, tol_junta, self.structures))
        return filas, n_conf, n_sug, n_ap

    def _calcular_accesorios(self, ft_px):
        """Accesorios, avisos de normativa (ya marcados con sus aprobaciones) y ángulos fuera de paso."""
        from nucleo import accesorios as _acc
        # Se reusan mientras el modelo no cambie (`_memo`, ventana_dibujo): copias, que
        # `marcar` escribe la aprobación en cada aviso.
        accs = self._memo(("accesorios", ft_px), lambda: _acc.accesorios(self.pipes, self._pipe_z_at, ft_px))
        con_db = {i for db in getattr(self, "duct_banks", []) or [] for i in db.assigned()}
        # + el diámetro que el plano no dijo con certeza (`diametro_plano`, 2026-10-22): mismos avisos
        from nucleo import diametro_plano
        normas = self._memo(("normas", ft_px), lambda: normas_validar.validar(
            self.normas_cat, self.pipes, accs, ft_px, con_db, self.structures,
            getattr(self, "cross_connections", None) or ()) + diametro_plano.avisos(self.pipes))
        # Ángulos en pasos de 0.25°: se validan pero NO se muestran (pedido del usuario 2026-10-16:
        # el dibujo a mano ya los deja en el paso; no van a los avisos ni al plano).
        from nucleo import angulos
        fuera = self._memo(("angulos", ft_px), lambda: angulos.avisos(self.pipes, ft_px))
        normas_aprobacion.marcar(normas, self.pipes, getattr(self, "normas_aprobados", []))
        return accs, normas, fuera

    def _preparar_etiquetas(self, accs, normas, ft_px):
        """Textos y globos de las etiquetas de accesorios: solo del modelo, se reusan entre redibujos."""
        from ui.comun import accesorios_view
        tol = 0.5 / ft_px
        return self._memo(("etiquetas_accesorios", ft_px), lambda: accesorios_view.preparar(
            accs, normas, tol), copiar=False)

    def _calcular_vertices_buzones(self):
        """Vértices de las utilidades (para el color de cada buzón) y su índice por celdas."""
        from nucleo.indice_plano import IndicePuntos

        def _vertices():                           # solo del modelo: se reusa entre redibujos (solo lectura)
            vert = [(vx, vy, pi) for pi, p in enumerate(self.pipes)
                    if not p.get("world") and p.get("pts") for (vx, vy) in p["pts"]]
            return vert, IndicePuntos([(v[0], v[1]) for v in vert], 14.0)
        return self._memo(("vertices_buzones",), _vertices, copiar=False)
