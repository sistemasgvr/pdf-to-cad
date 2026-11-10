"""Lo que se pinta del perfil (mezcla de `VistaPerfil`): rejilla, terreno, tubería, válvulas, cruces, fila de
tramos, callouts, alertas, marcas A/B y título. Movido tal cual de `perfil_vista` (2026-11-08)."""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui

from nucleo import valvulas as VV
from nucleo import perfil_textos as T
from traduccion.i18n import t
from ui.comun.perfil_vista_base import CAJA_PX_MIN, HUECO, LETRA_PT, RADIO_NODO, VALVULA_MIN_PX


class DibujoPerfilMixin:
    def _marcas_alerta(self):
        """[(centro, alertas)] de cada marca «!» (una por estación, bajo la tubería). La usan el dibujo y el globo."""
        if not self.alertas or not self.p or not self.p.pasos:
            return []
        grupos = {}
        for a in self.alertas:
            grupos.setdefault(round(self.X(a.e) / 14), []).append(a)
        out = []
        for _k, lst in grupos.items():
            a = lst[0]
            ps = self.p.pasos[a.paso] if a.paso >= 0 else min(self.p.pasos, key=lambda q: min(abs(q.e0 - a.e), abs(q.e1 - a.e)))
            f = max(0.0, min(1.0, (a.e - ps.e0) / max(ps.e1 - ps.e0, 1e-6)))
            z = ps.z0 + (ps.z1 - ps.z0) * f
            out.append((QtCore.QPointF(self.X(a.e), self.Z(z) + 16), lst))
        return out

    def _alertas(self, pt, tk):
        """Tramos con alerta con borde rojo, nodos con anillo rojo y una marca «!» donde va cada una."""
        if not self.alertas:
            return
        rojo = QtGui.QColor(tk.danger)
        ambar = QtGui.QColor(tk.warning)
        hechos = set()
        for a in self.alertas:
            col = rojo if a.nivel == "ERROR" else ambar
            if a.paso >= 0 and a.nodo < 0 and a.cruce < 0 and ("p", a.paso) not in hechos:
                hechos.add(("p", a.paso))
                ps = self.p.pasos[a.paso]
                z0, z1 = self._z_paso(a.paso)
                pen = QtGui.QPen(col, 2.5)
                pt.setPen(pen)
                pt.setBrush(QtCore.Qt.NoBrush)
                pt.drawPolygon(QtGui.QPolygonF([
                    QtCore.QPointF(self.X(ps.e0), self.Z(z0) + 3), QtCore.QPointF(self.X(ps.e1), self.Z(z1) + 3),
                    QtCore.QPointF(self.X(ps.e1), self.Z(z1 + ps.alto_ft) - 3),
                    QtCore.QPointF(self.X(ps.e0), self.Z(z0 + ps.alto_ft) - 3)]))
            if a.nodo >= 0 and ("n", a.nodo) not in hechos:
                hechos.add(("n", a.nodo))
                pt.setPen(QtGui.QPen(col, 2.5))
                pt.setBrush(QtCore.Qt.NoBrush)
                pt.drawEllipse(QtCore.QPointF(self.X(self.p.nodos[a.nodo].e), self.Z(self._z_nodo(a.nodo))),
                               RADIO_NODO + 5, RADIO_NODO + 5)
        # una marca «!» por estación (bajo la tubería), con el número si hay varias
        for c, lst in self._marcas_alerta():
            col = rojo if any(x.nivel == "ERROR" for x in lst) else ambar
            pt.setPen(QtCore.Qt.NoPen)
            pt.setBrush(col)
            pt.drawEllipse(c, 8, 8)
            pt.setPen(QtGui.QColor("#ffffff" if col == rojo else "#1a1a1a"))
            pt.setFont(self._fuente(True))
            pt.drawText(QtCore.QRectF(c.x() - 8, c.y() - 8, 16, 16), QtCore.Qt.AlignCenter,
                        "!" if len(lst) == 1 else str(len(lst)))
            pt.setFont(self._fuente())

    def _vacio(self, pt, tk):
        """Estado vacío que guía: flecha hacia el plano (arriba) y qué hacer."""
        r = QtCore.QRectF(self.rect())
        c = r.center()
        col = QtGui.QColor(tk.text_muted)
        pt.setPen(QtGui.QPen(col, 2))
        a, b = QtCore.QPointF(c.x(), c.y() - 18), QtCore.QPointF(c.x(), c.y() - 58)
        pt.drawLine(a, b)
        pt.setBrush(col)
        pt.drawPolygon(QtGui.QPolygonF([b, QtCore.QPointF(b.x() - 7, b.y() + 10),
                                        QtCore.QPointF(b.x() + 7, b.y() + 10)]))
        pt.setFont(self._fuente(True, LETRA_PT + 3))
        pt.setPen(QtGui.QColor(tk.text))
        pt.drawText(QtCore.QRectF(r.left(), c.y() - 10, r.width(), 24), QtCore.Qt.AlignCenter,
                    t("Haz clic en una utilidad del plano"))
        pt.setFont(self._fuente(False, LETRA_PT + 1))
        pt.setPen(col)
        pt.drawText(QtCore.QRectF(r.left() + 20, c.y() + 18, r.width() - 40, 40),
                    QtCore.Qt.AlignHCenter | QtCore.Qt.TextWordWrap,
                    self.aviso_vacio or t("Se arma solo el perfil de su tramo, siguiendo la red de frente en cada unión."))

    def _cursor(self, pt, tk, g):
        """La estación señalada en el plano: línea vertical y punto sobre la tubería."""
        e = self._cursor_e
        if e is None or not (self.p.e_ini <= e <= self.p.e_fin):
            return
        x = self.X(e)
        col = QtGui.QColor(tk.accent)
        pt.setPen(QtGui.QPen(col, 1, QtCore.Qt.DashLine))
        pt.drawLine(QtCore.QPointF(x, g["marco"].top() + g["alto_fila"]), QtCore.QPointF(x, g["marco"].bottom()))
        ps = next((q for q in self.p.pasos if q.e0 <= e <= q.e1), None)
        if ps is not None:
            f = (e - ps.e0) / max(ps.e1 - ps.e0, 1e-6)
            z = ps.z0 + (ps.z1 - ps.z0) * f + ps.alto_ft / 2
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.text_on_accent), 1.5))
            pt.setBrush(col)
            pt.drawEllipse(QtCore.QPointF(x, self.Z(z)), 4.5, 4.5)
            pt.setPen(QtGui.QColor(tk.text))
            pt.drawText(QtCore.QPointF(x + 6, self.Z(z) - 8), T.estacion(e))

    def _rejilla(self, pt, tk, g):
        marco, fm = g["marco"], g["fm"]
        vis = marco.intersected(g["vista"])            # lo que se ve del marco: ahí se anclan los rótulos
        cm, cmen, em, emen = self.p.intervalos
        menor, mayor = QtGui.QColor(tk.grid_line_minor), QtGui.QColor(tk.grid_line_major)
        texto = QtGui.QColor(tk.text_muted)
        z_bot, z_top = self.z_de(vis.bottom()), self.z_de(vis.top())
        z = math.floor(z_bot / cmen) * cmen
        while z <= z_top + 1e-9:
            y = self.Z(z)
            if vis.top() <= y <= vis.bottom():
                es_mayor = abs(z / cm - round(z / cm)) < 1e-6
                pt.setPen(QtGui.QPen(mayor if es_mayor else menor, 1))
                pt.drawLine(QtCore.QPointF(vis.left(), y), QtCore.QPointF(vis.right(), y))
                if es_mayor:
                    pt.setPen(texto)
                    s = f"{z:g}"
                    pt.drawText(QtCore.QPointF(vis.left() - fm.horizontalAdvance(s) - 6, y + fm.ascent() / 3), s)
                    pt.drawText(QtCore.QPointF(vis.right() + 6, y + fm.ascent() / 3), s)
            z += cmen
        e_izq, e_der = self.e_de(vis.left()), self.e_de(vis.right())
        y_est = vis.bottom() + fm.height() + 2
        e = math.ceil(e_izq / em) * em
        etiquetas = [(T.estacion(e_izq, 0), vis.left())]
        while e <= e_der + 1e-9:
            x = self.X(e)
            pt.setPen(QtGui.QPen(mayor, 1))
            pt.drawLine(QtCore.QPointF(x, vis.top()), QtCore.QPointF(x, vis.bottom()))
            etiquetas.append((T.estacion(e, 0), x))
            e += em
        etiquetas.append((T.estacion(e_der, 0), vis.right()))
        pt.setPen(texto)
        fin = -1e9
        for k, (s, x) in enumerate(etiquetas):         # sin encimarse (gana la de la rejilla)
            w = fm.horizontalAdvance(s)
            x0 = x - w / 2
            if x0 < fin + 4 and 0 < k < len(etiquetas) - 1:
                continue
            if x0 < fin + 4:
                continue
            pt.drawText(QtCore.QPointF(x0, y_est), s)
            fin = x0 + w
        s = T.TITULO_ESTACION
        pt.drawText(QtCore.QPointF(vis.center().x() - fm.horizontalAdvance(s) / 2, y_est + fm.height() + 4), s)
        for x, ang in ((vis.left() - 52, -90), (vis.right() + 52, 90)):
            pt.save()
            pt.translate(x, vis.center().y())
            pt.rotate(ang)
            s = T.TITULO_ELEVACION
            pt.drawText(QtCore.QPointF(-fm.horizontalAdvance(s) / 2, fm.ascent() / 2), s)
            pt.restore()

    def _terreno(self, pt, tk):
        ter = self.p.terreno
        if len(ter) < 2:
            return
        pen = QtGui.QPen(QtGui.QColor(tk.text_muted), 1.3, QtCore.Qt.DashLine)
        pt.setPen(pen)
        pts = [QtCore.QPointF(self.X(e), self.Z(z)) for e, z in ter]
        pt.drawPolyline(QtGui.QPolygonF(pts))
        pt.drawText(pts[0] + QtCore.QPointF(4, -4), T.TEXTO_RASANTE)

    def _tuberia(self, pt, tk):
        p = self.p
        base = QtGui.QColor(self.color)
        relleno = QtGui.QColor(base)
        relleno.setAlpha(60)
        for i, ps in enumerate(p.pasos):
            z0, z1 = self._z_paso(i)
            a0, a1 = QtCore.QPointF(self.X(ps.e0), self.Z(z0)), QtCore.QPointF(self.X(ps.e1), self.Z(z1))
            c0 = QtCore.QPointF(self.X(ps.e0), self.Z(z0 + ps.alto_ft))
            c1 = QtCore.QPointF(self.X(ps.e1), self.Z(z1 + ps.alto_ft))
            sel = i == self._sel_paso
            pt.setPen(QtCore.Qt.NoPen)
            pt.setBrush(QtGui.QColor(tk.accent if sel else relleno))
            pt.drawPolygon(QtGui.QPolygonF([a0, a1, c1, c0]))
            pen = QtGui.QPen(base, 2.0 if sel else 1.4)
            if ps.ab:
                pen.setStyle(QtCore.Qt.DashLine)
            pt.setPen(pen)
            pt.drawLine(a0, a1)
            pt.drawLine(c0, c1)
        for k, n in enumerate(p.nodos):
            x = self.X(n.e)
            z = self._z_nodo(k)
            if n.tipo == "estructura":
                g = self._geo
                w = max(8.0, 4.0 * g["kx"] * self._zoom)
                arriba = n.rim if n.rim is not None else z + 5.0
                r = QtCore.QRectF(x - w / 2, self.Z(arriba), w, self.Z(z - 0.5) - self.Z(arriba))
                pt.setPen(QtGui.QPen(QtGui.QColor(tk.text), 1.2))
                pt.setBrush(QtGui.QColor(tk.surface))
                pt.drawRect(r)
            elif n.tipo == "extremo":
                ps = p.pasos[min(k, len(p.pasos) - 1)]
                pt.setPen(QtGui.QPen(base, 1.4))
                pt.drawLine(QtCore.QPointF(x, self.Z(z)), QtCore.QPointF(x, self.Z(z + ps.alto_ft)))
            if n.editable:
                elegido = k in (self._sel_nodo, self._hover) or (self._arrastre and self._arrastre[0] == k)
                pt.setPen(QtGui.QPen(QtGui.QColor(tk.text_on_accent if elegido else tk.text), 1))
                pt.setBrush(QtGui.QColor(tk.accent if elegido else tk.surface))
                pt.drawEllipse(QtCore.QPointF(x, self.Z(z)), RADIO_NODO, RADIO_NODO)
        self._valvulas(pt, tk)
        if self._arrastre:
            k, z = self._arrastre
            s = T.cota(z)
            pt.setPen(QtGui.QColor(tk.text))
            pt.drawText(QtCore.QPointF(self.X(p.nodos[k].e) + 8, self.Z(z) - 8), s)

    def _marcas_ab(self, pt, tk, marco):
        """«A» (verde) en el inicio y «B» (roja) en el fin, abajo del marco: las mismas banderas que en el plano."""
        p = self.p
        f = self._fuente(negrita=True)
        pt.setFont(f)
        r = 9.0
        for letra, e, color in (("A", p.e_ini, tk.success), ("B", p.e_fin, tk.danger)):
            x = min(max(self.X(e), marco.left() + r + 2), marco.right() - r - 2)
            c = QtCore.QPointF(x, marco.bottom() - r - 3)
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.surface), 1.5))
            pt.setBrush(QtGui.QColor(color))
            pt.drawEllipse(c, r, r)
            pt.setPen(QtGui.QColor(tk.text_on_accent))
            pt.drawText(QtCore.QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), QtCore.Qt.AlignCenter, letra)
        pt.setFont(self._fuente())

    def _z_valvula(self, v):
        """Solera del recorrido en la válvula (sigue al arrastre de un nodo de su paso)."""
        ps = self.p.pasos[v.paso]
        z0, z1 = self._z_paso(v.paso)
        t = (v.e - ps.e0) / max(ps.e1 - ps.e0, 1e-9)
        return z0 + (z1 - z0) * t

    def _valvulas(self, pt, tk):
        """Cada válvula como en un plano de perfil: el «moño» a lo largo de la tubería (su largo real, mínimo
        `VALVULA_MIN_PX`) y el vástago hacia arriba."""
        for v in getattr(self.p, "valvulas", ()):
            z = self._z_valvula(v)
            x = self.X(v.e)
            medio = max(VALVULA_MIN_PX / 2.0, v.largo_ft / 2.0 * self._geo["kx"] * self._zoom)
            y0, y1 = self.Z(z), self.Z(z + v.alto_ft)
            if y0 - y1 < VALVULA_MIN_PX:              # tubería muy fina en pantalla: un moño visible
                yc = (y0 + y1) / 2.0
                y0, y1 = yc + VALVULA_MIN_PX / 2.0, yc - VALVULA_MIN_PX / 2.0
            yc = (y0 + y1) / 2.0
            relleno = QtGui.QColor(self.color)
            relleno.setAlpha(170)
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.text), 1.2))
            pt.setBrush(relleno)
            pt.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x - medio, y0), QtCore.QPointF(x, yc),
                                            QtCore.QPointF(x - medio, y1)]))
            pt.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x + medio, y0), QtCore.QPointF(x, yc),
                                            QtCore.QPointF(x + medio, y1)]))
            alto = (y0 - y1) * 0.8
            pt.drawLine(QtCore.QPointF(x, yc), QtCore.QPointF(x, y1 - alto))
            pt.drawLine(QtCore.QPointF(x - medio * 0.6, y1 - alto), QtCore.QPointF(x + medio * 0.6, y1 - alto))
            if v.z_caja is not None:                  # caja de la válvula: de la corona a la superficie
                yt = self.Z(z + (v.z_caja - v.z_solera))      # sigue al arrastre de su paso
                ancho = max(CAJA_PX_MIN, VV.CAJA_DIAM_IN / 12.0 / 2.0 * self._geo["kx"] * self._zoom)
                pt.setBrush(QtCore.Qt.NoBrush)
                pt.drawRect(QtCore.QRectF(x - ancho, yt, 2 * ancho, y1 - yt))
                pt.drawLine(QtCore.QPointF(x - ancho * 1.8, yt), QtCore.QPointF(x + ancho * 1.8, yt))

    def _cruces(self, pt, tk):
        p = self.p
        fm = self._geo["fm"]
        for c in p.cruces:
            col = QtGui.QColor(self.color_de(c.pipe))
            cx, cz = self.X(c.e), self.Z(c.z_solera + c.alto_ft / 2)
            rx = max(3.0, c.alto_ft / 2 * self._geo["kx"] * self._zoom)
            rz = max(3.0, c.alto_ft / 2 * self._geo["kz"] * self._zoom)
            pt.setPen(QtGui.QPen(col, 1.5))
            relleno = QtGui.QColor(col)
            relleno.setAlpha(50)
            pt.setBrush(relleno)
            pt.drawEllipse(QtCore.QPointF(cx, cz), rx, rz)
            # claro entre paredes
            ps = next((q for q in p.pasos if q.e0 <= c.e <= q.e1), None)
            if ps is not None:
                t_ = (c.e - ps.e0) / max(ps.e1 - ps.e0, 1e-6)
                z_run = ps.z0 + (ps.z1 - ps.z0) * t_
                if c.encima:
                    y0, y1 = self.Z(z_run + ps.alto_ft), self.Z(c.z_solera)
                else:
                    y0, y1 = self.Z(z_run), self.Z(c.z_solera + c.alto_ft)
                mal = any(a.cruce == p.cruces.index(c) for a in self.alertas)
                pt.setPen(QtGui.QPen(QtGui.QColor(tk.danger if mal else tk.text), 1.5 if mal else 1))
                xd = cx + rx + 6
                pt.drawLine(QtCore.QPointF(xd, y0), QtCore.QPointF(xd, y1))
                for y in (y0, y1):
                    pt.drawLine(QtCore.QPointF(xd - 3, y), QtCore.QPointF(xd + 3, y))
                pt.drawText(QtCore.QPointF(xd + 4, (y0 + y1) / 2 + fm.ascent() / 2), T.cota(c.claro))

    def _fila(self, pt, tk, g):
        p, fm, marco = self.p, g["fm"], g["marco"]
        if not p.celdas:
            return
        alto = g["alto_fila"]
        base = marco.top() + alto
        pt.setPen(QtGui.QPen(QtGui.QColor(tk.grid_line_major), 1))
        pt.drawLine(QtCore.QPointF(marco.left(), base), QtCore.QPointF(marco.right(), base))
        texto = QtGui.QColor(tk.text)
        for c in p.celdas:
            x0, x1 = self.X(c.e0), self.X(c.e1)
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.text_muted), 1))
            for e in (c.e0, c.e1):
                x = self.X(e)
                k = min(range(len(p.pasos)), key=lambda i: min(abs(p.pasos[i].e0 - e), abs(p.pasos[i].e1 - e)))
                ps = p.pasos[k]
                z = (self._z_paso(k)[0] if abs(ps.e0 - e) <= abs(ps.e1 - e) else self._z_paso(k)[1]) + ps.alto_ft
                pt.drawLine(QtCore.QPointF(x, marco.top()), QtCore.QPointF(x, self.Z(z)))
            pt.setPen(texto)
            y = marco.top() + HUECO + fm.ascent()
            for s in c.lineas:
                ancho = fm.horizontalAdvance(s)
                if ancho <= (x1 - x0) - 4:
                    pt.drawText(QtCore.QPointF((x0 + x1) / 2 - ancho / 2, y), s)
                y += fm.lineSpacing()

    def _callouts(self, pt, tk, g):
        p, fm, marco = self.p, g["fm"], g["marco"]
        tope_arr = marco.top() + g["alto_fila"] + HUECO
        bloques = []                                   # (x deseada, lineas, arriba, punto ancla, nodo | -1)
        self._zonas = []
        for k, n in enumerate(p.nodos):
            if not n.lineas:
                continue
            z = n.z_ancla + (self._z_nodo(k) - (p.pasos[k].z0 if k < len(p.pasos) else p.pasos[k - 1].z1))
            bloques.append((self.X(n.e), list(n.lineas), n.arriba, QtCore.QPointF(self.X(n.e), self.Z(z)), k))
        for c in p.cruces:
            z = c.z_solera + (c.alto_ft if c.encima else 0.0)
            bloques.append((self.X(c.e), list(c.lineas), c.encima,
                            QtCore.QPointF(self.X(c.e), self.Z(z)), -1))
        for v in getattr(p, "valvulas", ()):           # válvulas: rótulo arriba, a la corona
            bloques.append((self.X(v.e), list(v.lineas), True,
                            QtCore.QPointF(self.X(v.e), self.Z(self._z_valvula(v) + v.alto_ft)), -1))
        texto = QtGui.QColor(tk.text)
        paredes = sorted({self.X(c.e0) for c in p.celdas} | {self.X(c.e1) for c in p.celdas})
        for arriba in (True, False):
            fin_prev = -1e9
            for x, lineas, _a, ancla, nodo in sorted((b for b in bloques if b[2] == arriba), key=lambda b: b[0]):
                ancho, largo = self._bloque(lineas, fm)
                izq = max(x - ancho / 2, fin_prev + HUECO)
                if arriba:                            # sin cruzar una vertical de la fila de tramos
                    for xv in paredes:
                        if izq - 2 < xv < izq + ancho + 2:
                            izq = xv + 3 if x >= xv else xv - ancho - 3
                    izq = max(izq, fin_prev + HUECO)
                fin_prev = izq + ancho
                if arriba:
                    pie = tope_arr + largo                # el bloque se apoya hacia abajo desde la fila
                else:
                    pie = marco.bottom() - HUECO
                # texto vertical: se lee de abajo arriba (el de una T/Y/cruz con ramal, como enlace)
                enlace = nodo in self.con_ramal
                pt.setPen(QtGui.QColor(tk.accent) if enlace else texto)
                if enlace:
                    self._zonas.append((QtCore.QRectF(izq, pie - largo, ancho, largo), nodo))
                pt.save()
                pt.translate(izq, pie)
                pt.rotate(-90)
                y = fm.ascent()
                for s in lineas:
                    pt.drawText(QtCore.QPointF(0, y), s)
                    y += fm.lineSpacing()
                pt.restore()
                # cola bajo la 1.ª línea + leader con flecha hasta el ancla
                xc = izq + fm.lineSpacing() + 1
                pt.setPen(QtGui.QPen(texto, 1))
                pt.drawLine(QtCore.QPointF(xc, pie), QtCore.QPointF(xc, pie - largo))
                desde = QtCore.QPointF(xc, pie if arriba else pie - largo)
                pt.drawLine(desde, ancla)
                self._flecha(pt, desde, ancla, texto)

    def ramal_en(self, pos):
        """Nodo del rótulo-enlace bajo el ratón (T/Y/cruz con ramal) o -1."""
        for r, k in self._zonas:
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return k
        return -1

    def _flecha(self, pt, a, b, color):
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        L = 7
        p1 = QtCore.QPointF(b.x() - L * math.cos(ang - 0.35), b.y() - L * math.sin(ang - 0.35))
        p2 = QtCore.QPointF(b.x() - L * math.cos(ang + 0.35), b.y() - L * math.sin(ang + 0.35))
        pt.setPen(QtCore.Qt.NoPen)
        pt.setBrush(color)
        pt.drawPolygon(QtGui.QPolygonF([b, p1, p2]))

    def _titulo(self, pt, tk, g):
        marco = g["marco"]
        pt.setPen(QtGui.QColor(tk.text))
        f = self._fuente(True, LETRA_PT + 2)
        pt.setFont(f)
        fm = QtGui.QFontMetricsF(f)
        vis = marco.intersected(g["vista"])
        y = vis.bottom() + 2 * g["fm"].height() + 10 + fm.ascent()
        pt.drawText(QtCore.QPointF(vis.left(), y), self.p.titulo[0])
        pt.setFont(self._fuente())
        pt.drawText(QtCore.QPointF(vis.left(), y + g["fm"].lineSpacing() + 2), self.p.titulo[1])
