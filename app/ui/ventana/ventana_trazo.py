"""Dibujar y editar utilidades con ángulos en pasos de 0.25° (pedidos 2026-10-15/16).

A mano alzada la línea nunca sale del todo recta y cada quiebre chico se volvía un vértice
con su accesorio; y en el lienzo no puede haber ángulos como 45.684°. Al dibujar, cada tramo
(`nucleo.trazo_asistido`) cuenta desde el anterior (el quiebre es múltiplo de 0.25°); el
primero, desde la utilidad donde empieza (la unión) o desde los ejes de la hoja. Si el cursor
pasa a ≤ `IMAN_PX` de seguir recto, girar 45°/90°… o de los ejes de la hoja, la línea va ahí;
si no, hacia el imán a la tinta (o el cursor), en el paso. Al llegar EXACTO al extremo o
vértice de otra utilidad, el punto anterior (si no está unido a nada) se corre unas décimas
por su recta para que el último quiebre también quede en el paso; sobre un tramo, el punto
cae en el cruce de la dirección en el paso con él.

La utilidad se «estira» en tiempo real del último punto al cursor (línea a trazos con el
rumbo, el giro —el ángulo del quiebre/codo que se crea— con ✓/⚠ y el largo). En «Editar/
mover» el vértice arrastrado queda donde sus ángulos siguen el paso y lleva la misma
etiqueta. Clase mezcla de `Main`.

(El 2026-10-16 se quitó el anillo «Asistir / Libre / Finalizar / Cancelar»: siempre se
dibuja en el paso de 0.25° y se termina con Enter, doble clic o clic derecho.)
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from nucleo import angulos as ANG
from nucleo import trazo_asistido as TA

IMAN_PX = 8.0            # px de PANTALLA: el cursor a esta distancia de un imán va al imán
DESLIZ_PX = 8.0          # lo más que se corre el punto anterior para llegar exacto (px de pantalla)
CRUCE_PX = 24.0          # el cruce con el tramo enganchado, a esta distancia del cursor
_VERDE = QtGui.QColor(40, 170, 80)
_AMBAR = QtGui.QColor(230, 160, 20)


def _num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _giro(a, v, b):
    """Deflexión (0–180°) en v del recorrido a → v → b."""
    return abs((TA.rumbo(v, b) - TA.rumbo(a, v) + 180.0) % 360.0 - 180.0)


class TrazoMixin:
    # ─────────────────────────── clics ───────────────────────────
    def _clic_dibujo(self, x, y):
        """Clic izquierdo en modo «Dibujar utilidad»."""
        hit = self._pipe_soft_snap(x, y)
        if not self.cur_pts:
            self._push(); self.cur_pts.append(self._pipe_snap_and_ask(x, y))
            self._trazo_base0 = self._base_de_hit(hit)
            self._trazo_fijos = {tuple(self.cur_pts[0])} if hit is not None else set()
            self._update_ui(); self._redraw()
            return
        raw = (x, y) if hit is not None else self._snap(x, y)
        pt, enganche, p0n = self._resolver_trazo(x, y, hit, raw)
        p0 = p0n or tuple(self.cur_pts[-1])
        if math.hypot(pt[0] - p0[0], pt[1] - p0[1]) < 1e-6:
            return                                      # mismo punto: no agrega un tramo de largo cero
        self._push()
        if p0n is not None:
            self.cur_pts[-1] = p0n
        self.cur_pts.append(pt)
        if enganche is not None:
            self._trazo_fijos = set(getattr(self, "_trazo_fijos", set())) | {tuple(pt)}
        self._update_ui(); self._redraw()

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
        self._trazo_al_iniciar_extension(pi, vi)

    def _trazo_al_iniciar_extension(self, pi=None, vi=None):
        """Extender desde un vértice (F): los ángulos cuentan desde la utilidad de la que sale."""
        self._trazo_fijos = {tuple(self.cur_pts[0])} if self.cur_pts else set()
        self._trazo_base0 = 0.0
        if pi is not None and 0 <= pi < len(self.pipes):
            self._trazo_base0 = self._base_de_hit({"kind": "vertex", "pipe_idx": pi, "port": vi})

    # ─────────────────────────── geometría ───────────────────────────
    def _escala_vista(self):
        return max(1e-6, self.canvas.transform().m11())

    def _tramo_de_hit(self, hit):
        """(a, b) del tramo o borde de sólido al que se engancha `hit`, o None."""
        try:
            if hit["kind"] == "segment":
                pts = self.pipes[hit["pipe_idx"]]["pts"]; si = hit["port"]
                return tuple(pts[si]), tuple(pts[si + 1])
            if hit["kind"] in ("endpoint", "vertex"):
                pts = self.pipes[hit["pipe_idx"]]["pts"]; vi = hit["port"]
                return (tuple(pts[vi]), tuple(pts[vi + 1])) if vi < len(pts) - 1 else (tuple(pts[vi - 1]), tuple(pts[vi]))
            if hit["kind"] == "solid":
                poly = [tuple(q) for q in (self.structures[hit["port"]].get("outline") or [])]
                hx, hy = hit["pt"]
                return min(zip(poly, poly[1:] + poly[:1]),
                           key=lambda ab: G.pt_seg_dist(hx, hy, ab[0][0], ab[0][1], ab[1][0], ab[1][1]))
        except (IndexError, KeyError, TypeError, ValueError):
            pass
        return None

    def _base_de_hit(self, hit):
        """Rumbo desde el que cuentan los ángulos de una utilidad que empieza en `hit`."""
        ab = self._tramo_de_hit(hit) if hit else None
        if ab is None or ab[0] == ab[1]:
            return 0.0
        return TA.rumbo(*ab)

    def _trazo_base(self):
        if len(self.cur_pts) >= 2 and tuple(self.cur_pts[-2]) != tuple(self.cur_pts[-1]):
            return TA.rumbo(self.cur_pts[-2], self.cur_pts[-1])
        return float(getattr(self, "_trazo_base0", 0.0) or 0.0)

    def _resolver_trazo(self, x, y, hit, raw=None):
        """(punto, enganche a mostrar, punto anterior corrido o None) para el cursor en (x, y).
        Sin puntos: el enganche o el cursor. Si no: extremo/vértice/esquina de otra utilidad =
        exacto (y el anterior se corre para quedar en el paso); sobre un tramo, el cruce de la
        dirección en el paso con él; si no, un imán o la dirección en el paso hacia `raw`."""
        if not self.cur_pts:
            return (tuple(hit["pt"]) if hit else (x, y)), hit, None
        p0 = tuple(self.cur_pts[-1])
        base = self._trazo_base()
        esc = self._escala_vista()
        if hit and (hit.get("kind") in ("endpoint", "vertex") or hit.get("corner")):
            T = tuple(hit["pt"])
            p0n = None
            if p0 not in (getattr(self, "_trazo_fijos", None) or set()) and T != p0:
                prev = tuple(self.cur_pts[-2]) if len(self.cur_pts) >= 2 else None
                p0n = TA.deslizar_inicio(prev, p0, T, base)
                if p0n is not None and math.hypot(p0n[0] - p0[0], p0n[1] - p0[1]) > DESLIZ_PX / esc:
                    p0n = None
            return T, hit, p0n
        imanes = TA.imanes(base, TA.en_paso(base))
        q, ang = TA.restringir(p0, (x, y), base, imanes, IMAN_PX / esc)
        if raw is not None and tuple(raw) != (x, y) and ang not in imanes:
            q, ang = TA.restringir(p0, raw, base)       # sin imán: hacia la tinta, en el paso
        if hit:
            ab = self._tramo_de_hit(hit)
            c = TA.cruce_rayo(p0, TA.unitario(ang), *ab) if ab else None
            if c is not None and math.hypot(c[0] - x, c[1] - y) <= CRUCE_PX / esc:
                return c, dict(hit, pt=c), None
        return q, None, None

    def _arrastre_en_paso(self, pts, k, x, y):
        """Editar/mover: el vértice arrastrado queda donde sus ángulos siguen el paso de 0.25°."""
        return TA.arrastre_en_paso(pts, k, (x, y), CRUCE_PX / self._escala_vista())

    # ─────────────────────────── etiquetas junto al cursor ───────────────────────────
    def _trazo_borrar(self):
        sc = self.canvas.scene()
        for it in getattr(self, "_trazo_items", None) or []:
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        self._trazo_items = []

    def _etiqueta(self, x, y, texto, ok, color):
        """Recuadro oscuro con `texto` junto a (x, y); borde verde (✓), ámbar (⚠) o del color dado."""
        sc = self.canvas.scene()
        caja = QtWidgets.QGraphicsRectItem()
        caja.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        caja.setPos(x, y); caja.setZValue(Z_MARK + 21)
        t = QtWidgets.QGraphicsSimpleTextItem(caja)
        t.setText(texto)
        t.setBrush(QtGui.QColor(255, 255, 255))
        t.setPos(16, 12)
        caja.setRect(t.mapRectToParent(t.boundingRect()).adjusted(-5, -3, 5, 3))
        caja.setBrush(QtGui.QColor(20, 26, 40, 215))
        caja.setPen(QtGui.QPen(color if ok is None else (_VERDE if ok else _AMBAR), 1.4))
        sc.addItem(caja)
        self._trazo_items.append(caja)

    def _ft(self, a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        return L * (self.scale / self.zoom) if self.scale and self.zoom else 0.0

    def _trazo_actualizar(self, x, y, hit):
        """Dibuja la utilidad «estirándose» del último punto al cursor (o al punto en el paso)."""
        self._trazo_borrar()
        if self.mode != "pipe" or not self.cur_pts or self.canvas.pixmap_item is None:
            return
        try:
            pt, _, p0n = self._resolver_trazo(x, y, hit)
            p0 = p0n or tuple(self.cur_pts[-1])
            sc = self.canvas.scene()
            col = QtGui.QColor(layer_qcolor(self._ext_layer or self.active_layer()))
            pen = QtGui.QPen(col, 2.0, QtCore.Qt.DashLine); pen.setCosmetic(True)
            linea = sc.addLine(p0[0], p0[1], pt[0], pt[1], pen); linea.setZValue(Z_MARK + 5)
            self._trazo_items = [linea]
            if math.hypot(pt[0] - p0[0], pt[1] - p0[1]) < 1e-6:
                return
            ang, ft = TA.rumbo_deg(p0, pt), self._ft(p0, pt)
            prev = tuple(self.cur_pts[-2]) if len(self.cur_pts) >= 2 else None
            if prev is not None and prev != p0:       # el giro = el ángulo del quiebre/codo que se crea
                g = _giro(prev, p0, pt)
                ok = not ANG.fuera_de_paso(g)
                txt = _tr("{a}° · giro {g}° {v} · {l} ft").format(a=_num(ang), g=_num(g), v="✓" if ok else "⚠",
                                                                  l=f"{ft:,.2f}")
            else:
                ok, txt = None, _tr("{a}° · {l} ft").format(a=_num(ang), l=f"{ft:,.2f}")
            self._etiqueta(pt[0], pt[1], txt, ok, col)
        except Exception:
            self._trazo_borrar()

    def _etiqueta_arrastre(self, pts, k):
        """Editar/mover: junto al vértice arrastrado, su giro (o el del vecino si es una punta)
        con ✓/⚠ y el largo de sus tramos. ⚠ si algún ángulo que cambia queda fuera del paso."""
        self._trazo_borrar()
        try:
            pts = [tuple(q) for q in pts]
            n = len(pts)
            if n < 2 or not (0 <= k < n):
                return
            giros = [(j, _giro(pts[j - 1], pts[j], pts[j + 1])) for j in (k - 1, k, k + 1)
                     if 0 < j < n - 1 and pts[j] not in (pts[j - 1], pts[j + 1])]
            ok = all(not ANG.fuera_de_paso(g) for _j, g in giros if g > ANG.TOL_DEG)
            v = "✓" if ok else "⚠"
            largos = [f"{self._ft(pts[j], pts[j + 1]):,.2f}" for j in (k - 1, k) if 0 <= j < n - 1]
            propio = next((g for j, g in giros if j == k), None)
            vecino = next((g for j, g in giros if j != k), None)
            if propio is not None:
                txt = _tr("giro {g}° {v} · {l1} / {l2} ft").format(g=_num(propio), v=v, l1=largos[0], l2=largos[1])
            elif vecino is not None:
                txt = _tr("giro {g}° {v} · {l} ft").format(g=_num(vecino), v=v, l=largos[0])
            else:
                ok, txt = None, _tr("{a}° · {l} ft").format(a=_num(TA.rumbo_deg(pts[0], pts[1])), l=largos[0])
            col = QtGui.QColor(layer_qcolor(self.pipes[self.sel_pipe].get("layer"))) \
                if 0 <= self.sel_pipe < len(self.pipes) else QtGui.QColor(255, 255, 255)
            self._etiqueta(pts[k][0], pts[k][1], txt, ok, col)
        except Exception:
            self._trazo_borrar()

    def _trazo_al_redibujar(self):
        """Lo llama `_redraw`: borra la línea elástica (se rehace al mover el ratón)."""
        self._trazo_borrar()
