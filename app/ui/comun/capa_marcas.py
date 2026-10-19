"""Marcas del lienzo de tamaño fijo en pantalla pintadas por CAPAS (pedido del usuario 2026-10-16).

Con un mapa de agua con sus acometidas (16 761 utilidades) el lienzo tenía ~80 mil ítems: marcas de
cruce, alertas, etiquetas de accesorios, avisos y conflictos C-n. Cada redibujo los sacaba y metía en
la escena uno por uno y cada repintado (mover el ratón, la cruz del cursor, el zoom) los volvía a
recorrer: segundos por movimiento.

Aquí cada marca sigue siendo EL MISMO ítem de Qt de antes (círculo, texto, `EtiquetaAccesorio`…, con
`ItemIgnoresTransformations`, su posición, su transformación, su Z y su tooltip), pero NO entra en la
escena: la guarda la capa de su Z (`GrupoMarcas.agregar`), que es UN ítem de la escena y la pinta con
su propio `paint`, igual que Qt pinta un ítem que ignora el zoom (punto de la escena llevado a la
pantalla + su transformación), en el mismo orden (Z y orden de llegada). Solo pinta las marcas que
caen en lo que hay que repintar (búsqueda vectorizada sobre los puntos). El tooltip es el de la marca
de más arriba bajo el cursor cuya forma lo contiene (como `QGraphicsScene.helpEvent`).

SELLOS (2026-10-17, segundo reporte: a vista completa ~54 mil marcas visibles = ~8 s por paso de zoom;
lo que hacen los visores de mapas): la marca que trae una clave de ASPECTO (`sello(item, clave)`: todo
lo que define cómo se ve, sin el punto ni el tooltip) se dibuja UNA vez en una imagen a la resolución
de la pantalla y en cada repintado solo se COPIA en su lugar, alineada al píxel físico (idéntica salvo
el suavizado de bordes de una fracción de píxel). Las marcas sin clave se pintan como antes.

NIVEL DE DETALLE (2026-10-17, como Google Maps o Civil 3D): las partes que son RÓTULO (`sello(...,
rotulo=True)` o el 5.º valor de cada parte: la pastilla y el texto de un accesorio, el C-n) se despejan
con `despeje_rotulos.despejar` —de los que se tapan en pantalla, solo el de más prioridad: Z más alta y
luego orden de llegada—; los puntos (rombo, círculo de cruce, triángulo, insignia) siempre. Se decide UNA
vez por escala y región de la vista (`GrupoMarcas.rotulos_visibles`), así el repintado parcial (la cruz)
ve lo mismo. Un rótulo oculto no da tooltip (sí su punto).

Reuso: quien arma una marca puede pedir con `reusar(clave)` la MISMA del redibujo anterior (clave =
todo lo que define su aspecto: tipo, punto, estado, texto); solo le renueva el tooltip. Así un
redibujo sin cambios del modelo (elegir una utilidad, cambiar de modo) no rehace miles de ítems.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun.capa_marcas_sellos import (FASES, _caja_local, _caja_rotulo, _hacer_sello, _pintar,  # noqa: F401
                                        sello)
from ui.comun.capa_marcas_vista import CacheVistaMixin, DespejeMixin

ESCALA_MIN = 0.3                  # la del lienzo (`canvas._ZOOM_MIN`): para el margen de la caja
MAX_MB = 192                      # memoria de los sellos (se vacían todos al pasarse)


class _Capa(CacheVistaMixin, QtWidgets.QGraphicsItem):
    def __init__(self, grupo, z, escala):
        super().__init__()
        self.grupo = grupo
        self.marcas = []
        self.ids = []                                    # aspecto de cada marca: nº, -1 sin clave, None sin ver
        self._xs, self._ys = [], []
        self._cajas = []                                 # caja de cada marca en px de pantalla
        self._rots = []                                  # caja de su RÓTULO (o NaN): nivel de detalle
        self.con_rotulos = False
        self._cache = None                               # (clave de la vista, imagen) — `_con_cache`
        self._ultima = None                              # clave de la vista del último repintado
        self._np = None                                  # (xs, ys) en numpy, al primer uso
        self.ext = 0.0                                   # mayor extensión en px de pantalla
        self.escala = max(min(escala, ESCALA_MIN), 1e-6)
        self._caja = QtCore.QRectF()
        self.setZValue(z)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemUsesExtendedStyleOption)

    def agregar(self, it):
        xy = getattr(it, "_pdfcad_xy", None)             # marca reusada: su punto no cambia (clave)
        if xy is None:
            p = it.pos()
            xy = (p.x(), p.y())
            try:
                it._pdfcad_xy = xy
            except AttributeError:
                pass
        x, y = xy
        caja = _caja_local(it)
        self.marcas.append(it)
        self.ids.append(None)
        self._xs.append(x)
        self._ys.append(y)
        self._cajas.append(caja)
        rot = _caja_rotulo(it)
        self._rots.append(rot if rot is not None else (math.nan,) * 4)
        if rot is not None:
            self.con_rotulos = True
        self._np = None
        l, t, r, b = caja
        ext = max(-l, l, -t, t, -r, r, -b, b) + 2.0
        if ext > self.ext:
            self.ext = ext
        if len(self.marcas) == 1:
            self._lim = [x, x, y, y]
        else:
            lim = self._lim
            if x < lim[0]: lim[0] = x
            if x > lim[1]: lim[1] = x
            if y < lim[2]: lim[2] = y
            if y > lim[3]: lim[3] = y
        # Caja = puntos + la extensión mayor (en px de la escena al zoom mínimo); se avisa a la escena
        # solo cuando CRECE (avisar en cada una de decenas de miles de marcas pesaba).
        m = self.ext / self.escala
        x0, x1, y0, y1 = self._lim
        caja_q = QtCore.QRectF(x0 - m, y0 - m, x1 - x0 + 2 * m, y1 - y0 + 2 * m)
        if caja_q != self._caja:
            self.prepareGeometryChange()
            self._caja = caja_q

    def boundingRect(self):
        return self._caja

    def _puntos(self):
        if self._np is None:
            self._np = (np.asarray(self._xs, dtype=float), np.asarray(self._ys, dtype=float))
            self._np_cajas = np.asarray(self._cajas, dtype=float).reshape(-1, 4)
            self._np_rots = np.asarray(self._rots, dtype=float).reshape(-1, 4)
        return self._np

    def cerca(self, *rects):
        """Índices ordenados (orden de llegada) de las marcas cuyo punto cae en alguno de `rects`
        (escena, bordes incluidos como `QRectF.contains`)."""
        xs, ys = self._puntos()
        dentro = None
        for r in rects:
            if r.width() == 0 or r.height() == 0:
                continue
            r = r.normalized()
            m = (xs >= r.left()) & (xs <= r.right()) & (ys >= r.top()) & (ys <= r.bottom())
            dentro = m if dentro is None else (dentro | m)
        return np.flatnonzero(dentro) if dentro is not None else np.zeros(0, dtype=int)

    def paint(self, painter, opcion, widget=None):
        W = QtGui.QTransform(painter.worldTransform())
        escala = max(math.hypot(W.m11(), W.m12()), 1e-9)
        m = self.ext / escala
        # Lo que de verdad hay que repintar: con la cruz del cursor son dos franjas finas, no toda
        # la vista (Qt no lo deja como recorte del pintor sino del sistema). OJO: el recorte del
        # sistema va en px FÍSICOS de la ventana (desplazamiento de la vista en la ventana y escala
        # de pantalla, p. ej. 125 %): se lleva con `deviceTransform`, no con `worldTransform` (con
        # ésta se descartaban marcas que sí estaban bajo la cruz y se «borraban», 2026-10-17).
        D = QtGui.QTransform(painter.deviceTransform())  # copia (la de Qt es del estado del pintor)
        clip = None
        motor = painter.paintEngine()
        if motor is not None and not motor.systemClip().isEmpty():
            clip = motor.systemClip()
        if painter.hasClipping():
            c = D.map(painter.clipRegion())
            clip = c if clip is None else clip.intersected(c)
        inv_d, ok_d = D.inverted()
        inv_w, ok_w = W.inverted()
        visibles = self.grupo.rotulos_visibles(self, widget)
        painter.save()                                   # px de la vista → px físicos, EXACTA (inv_w·D trae
        painter.setWorldTransform(QtGui.QTransform())    # ruido de coma flotante que cambia empates de fase)
        S = QtGui.QTransform(painter.deviceTransform())
        painter.restore()
        if ok_d and ok_w and self._con_cache(painter, W, S, inv_d, clip, widget, visibles, m):
            return
        zona = opcion.exposedRect.adjusted(-m, -m, m, m)
        if clip is None or not ok_d:
            indices = self.cerca(zona)
        else:                                            # solo cerca de cada rectángulo a repintar
            indices = self.cerca(*[inv_d.mapRect(QtCore.QRectF(r)).adjusted(-m, -m, m, m).intersected(zona)
                                   for r in clip])
        vx, vy, indices = self._en_vista(W, indices, None if clip is None or not ok_d else
                                         [(inv_d * W).mapRect(QtCore.QRectF(r)) for r in clip])
        if not len(indices):
            return
        painter.save()
        try:                                             # el estado del pintor SIEMPRE se repone
            self._pintar_marcas(painter, indices, vx, vy, widget, visibles)
        finally:
            painter.restore()

    def _en_vista(self, W, indices, rects_vista):
        """Punto de cada marca en px de la vista y, con `rects_vista`, solo las que tocan alguno (descarte
        EXACTO por la caja de cada marca: el margen `m` es el de la marca más grande y con la cruz a vista
        completa dejaba ~40 mil marcas para repintar dos franjas finas)."""
        xs, ys = self._puntos()
        sx, sy = xs[indices], ys[indices]
        vx = W.m11() * sx + W.m21() * sy + W.dx()
        vy = W.m12() * sx + W.m22() * sy + W.dy()
        if not W.isAffine():
            w = W.m13() * sx + W.m23() * sy + W.m33()
            vx, vy = vx / w, vy / w
        if rects_vista is not None and len(indices):
            cajas = self._np_cajas[indices]
            x0, x1, y0, y1 = vx + cajas[:, 0], vx + cajas[:, 2], vy + cajas[:, 1], vy + cajas[:, 3]
            toca = np.zeros(len(indices), dtype=bool)
            for q in rects_vista:
                toca |= (x0 <= q.right() + 2) & (x1 >= q.left() - 2) & (y0 <= q.bottom() + 2) & (y1 >= q.top() - 2)
            indices, vx, vy = indices[toca], vx[toca], vy[toca]
        return vx, vy, indices

    def _pintar_marcas(self, painter, indices, vx, vy, widget, visibles=None, base=None, S=None):
        """`base`/`S` (imagen de la vista, `CacheVistaMixin`): el pintor dibuja corrido por `base`, pero el
        píxel y la fase de cada marca salen de `S` = la transformación REAL de la ventana (si no, un empate
        de redondeo podía caer distinto que al pintar directo)."""
        base = base if base is not None else QtGui.QTransform()
        painter.setWorldTransform(base)
        if S is None:
            S = QtGui.QTransform(painter.deviceTransform())  # px de la vista → px físicos
        ax, bx, ay, by = S.m11(), S.dx(), S.m22(), S.dy()
        # Escala REAL vista → píxeles (no la del dispositivo: al renderizar a una imagen, `device()`
        # puede ser la vista con otra escala). Sin escala uniforme ni giro: como siempre.
        alinear = S.type().value <= QtGui.QTransform.TxScale.value and ax > 0 and abs(ax - ay) < 1e-9
        dpr = ax
        # Píxel físico donde cae cada punto y su fase de subpíxel en pasos de 1/fases: el sello de esa
        # fase es el mismo dibujo que con el punto ahí (lo que resta, ≤ 1/(2·fases) px, no se ve).
        px, py = vx * ax + bx, vy * ay + by
        ix, iy = np.floor(px), np.floor(py)
        fx, fy = px - ix, py - iy
        hints = painter.renderHints()
        op = QtWidgets.QStyleOptionGraphicsItem()
        marcas, ids, grupo = self.marcas, self.ids, self.grupo
        guardados = grupo.sellos_a(dpr)
        dibujar = painter.drawPixmap
        punto = QtCore.QPointF
        rotulos = []                                     # como en los mapas: encima de los puntos
        for k, x, y, i0, j0, a0, b0 in zip(indices.tolist(), vx.tolist(), vy.tolist(), ix.tolist(), iy.tolist(),
                                          fx.tolist(), fy.tolist()):
            it = marcas[k]
            if not it.isVisible():
                continue
            partes = ids[k]
            if partes is None:
                partes = ids[k] = grupo.ids_de(it)
            if not partes or not alinear:                # sin clave de aspecto: como siempre
                _pintar(painter, it, it.transform() * QtGui.QTransform.fromTranslate(x, y) * base, op, widget)
                continue
            oculto = visibles is not None and not visibles[k]
            for n, fases, parte, rot in partes:
                if rot and oculto:                       # nivel de detalle: rótulo tapado
                    continue
                a, b = round(a0 * fases), round(b0 * fases)
                i, j = i0 + (a == fases), j0 + (b == fases)
                a, b = a % fases, b % fases
                s = guardados.get((n, a, b))
                if s is None:
                    s = grupo.nuevo_sello(guardados, (n, a, b), it, parte, dpr, a / fases, b / fases, hints, widget)
                if rot:
                    rotulos.append((punto((i + s.ox - bx) / ax, (j + s.oy - by) / ay), s.pm))
                else:
                    dibujar(punto((i + s.ox - bx) / ax, (j + s.oy - by) / ay), s.pm)
        for q, pm in rotulos:
            dibujar(q, pm)

    def hoverMoveEvent(self, ev):
        self.setToolTip(self.grupo.tooltip_en(ev.scenePos(), ev.widget()))

    def hoverLeaveEvent(self, ev):
        self.setToolTip("")


class GrupoMarcas(DespejeMixin):
    """Las capas de un redibujo: una por Z. `agregar(item)` en lugar de `scene.addItem(item)`."""

    def __init__(self, scene, escala, nuevas=None, previo=None):
        self.scene = scene
        self.escala = escala
        self.capas = {}
        self.nuevas = nuevas                              # lista donde dejar cada capa creada (overlay)
        self._viejas = previo._guardadas if previo is not None and previo.scene is scene else {}
        self._guardadas = {}
        viejo = previo is not None and previo._bytes <= MAX_MB * 1024 * 1024
        self._ids = previo._ids if viejo else {}          # clave de aspecto → nº
        self._ficha = previo._ficha if viejo else object()  # identifica ese `_ids` (las marcas lo guardan)
        self._sellos = previo._sellos if viejo else {}    # dpr → {(nº, fase x, fase y): _Sello}
        self._bytes = previo._bytes if viejo else 0
        self._despeje = None                              # (clave de escala, región, {capa: visibles})
        self.firma = None                                 # la pone la ventana: si no cambia, se reusa todo

    def vivo(self, scene):
        """Sus capas siguen en `scene` (vaciar la escena —otra hoja, abrir— las borra)."""
        try:
            return self.scene is scene and all(c.scene() is scene for c in self.capas.values())
        except RuntimeError:
            return False

    def todas(self):
        """Las marcas de todas las capas (lo que la ventana guarda en `_overlay`)."""
        return [m for c in self.capas.values() for m in c.marcas]

    def reusar(self, clave):
        """La marca de `clave` del redibujo anterior (ya configurada), o None."""
        lista = self._viejas.get(clave)
        if not lista:
            return None
        it = lista.pop()
        self._guardadas.setdefault(clave, []).append(it)
        return it

    def guardar(self, clave, it):
        """Recuerda la marca recién armada para el próximo redibujo; devuelve `it`."""
        self._guardadas.setdefault(clave, []).append(it)
        return it

    def agregar(self, it):
        z = it.zValue()
        capa = self.capas.get(z)
        if capa is None:
            capa = self.capas[z] = _Capa(self, z, self.escala)
            self.scene.addItem(capa)
            if self.nuevas is not None:
                self.nuevas.append(capa)
        capa.agregar(it)
        return it

    def ids_de(self, it):
        """Partes del aspecto de `it` como ((nº, fases, (rect, pintar), rótulo), …), o () sin clave."""
        guardado = getattr(it, "_pdfcad_ids", None)      # marca reusada: ya calculado con estos `_ids`
        if guardado is not None and guardado[0] is self._ficha:
            return guardado[1]
        partes = getattr(it, "_pdfcad_sello", None)
        if not partes:
            return ()
        out = []
        for clave, fases, rect, pintar, rot in partes:
            n = self._ids.get(clave)
            if n is None:
                n = self._ids[clave] = len(self._ids)
            out.append((n, max(1, int(fases)), (rect, pintar), bool(rot)))
        out = tuple(out)
        try:
            it._pdfcad_ids = (self._ficha, out)
        except AttributeError:
            pass
        return out

    def sellos_a(self, dpr):
        """Sellos ya dibujados a esa escala de pantalla."""
        return self._sellos.setdefault(dpr, {})

    def nuevo_sello(self, guardados, clave, it, parte, dpr, fx, fy, hints, widget):
        s, nbytes = _hacer_sello(it, parte, dpr, fx, fy, hints, widget)
        guardados[clave] = s
        self._bytes += nbytes
        return s

    def tooltip_en(self, punto, widget):
        """Tooltip de la marca de más arriba bajo `punto` (escena) cuya forma lo contiene."""
        vista = self._vista_de(self.scene, widget)
        if vista is None:
            return ""
        W = vista.viewportTransform()
        cursor = W.map(punto)
        escala = max(math.hypot(W.m11(), W.m12()), 1e-9)
        for z in sorted(self.capas, reverse=True):
            capa = self.capas[z]
            m = capa.ext / escala
            visibles = self.rotulos_visibles(capa, widget)
            for k in reversed(capa.cerca(QtCore.QRectF(punto.x() - m, punto.y() - m, 2 * m, 2 * m)).tolist()):
                it = capa.marcas[k]
                if not it.isVisible() or not it.toolTip():
                    continue
                d = W.map(it.pos())
                inv, ok = (it.transform() * QtGui.QTransform.fromTranslate(d.x(), d.y())).inverted()
                if not ok:
                    continue
                local = inv.map(cursor)
                if visibles is not None and not visibles[k]:
                    # rótulo oculto: solo cuentan sus partes que NO son rótulo (el punto)
                    if any(rect is not None and not rot and QtCore.QRectF(rect).contains(local)
                           for _c, _f, rect, _p, rot in getattr(it, "_pdfcad_sello", None) or ()):
                        return it.toolTip()
                    continue
                if it.contains(local) or any(h.contains(h.mapFromParent(local)) for h in it.childItems()):
                    return it.toolTip()
        return ""
