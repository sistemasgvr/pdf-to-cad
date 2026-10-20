"""Para `capa_marcas`: la IMAGEN de una capa para la vista actual (`CacheVistaMixin`, de `_Capa`) y el
DESPEJE de rótulos —nivel de detalle— de un redibujo (`DespejeMixin`, de `GrupoMarcas`)."""
from __future__ import annotations

import math

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun.despeje_rotulos import despejar

CACHE_MIN = 300                   # capas con al menos tantas marcas guardan su imagen de la vista
DESPEJAR = True                   # nivel de detalle: rótulos que se tapan → solo uno
MARGEN_REGION = 0.5               # el despeje cubre la vista + este tanto por lado (desplazar no lo rehace)


CACHE_MAX_PIEZAS = 24              # imágenes guardadas por capa (las más recientes)
CACHE_MAX_MB = 96                 # y no más que esto por capa


class CacheVistaMixin:
    def _con_cache(self, painter, W, S, inv_d, clip, widget, visibles, m):
        """IMAGEN de la capa para la vista actual (2026-10-17: a vista entera la cruz del cursor cruzaba
        ~16 mil marcas en cada movimiento): con la vista quieta, repintar = copiar de la imagen (mismos
        píxeles: se arma con el mismo dibujo, alineado al mismo píxel físico). Se arma al pintar la vista
        entera o al repetirse la misma vista. True = ya pintó.

        PIEZAS (2026-10-19, AGUA 2 con el zoom alejado: cada paso al DESPLAZAR rehacía la imagen entera de
        la capa, ~125 ms): las imágenes ya armadas con la MISMA escala y despeje se reusan si la vista se
        corrió un número ENTERO de píxeles físicos (cada marca cae corrida exactamente esos píxeles, con la
        misma fase de subpíxel: el mismo dibujo); solo se arma lo que falta (la franja que entra)."""
        if len(self.marcas) < CACHE_MIN:
            return False
        vista = self.grupo._vista_de(self.grupo.scene, widget)
        if vista is None or S.type().value > QtGui.QTransform.TxScale.value or S.m11() <= 0:
            return False
        vp = QtCore.QRectF(vista.viewport().rect())
        dev = S.mapRect(vp)
        X0, Y0 = math.floor(dev.left()), math.floor(dev.top())
        X1, Y1 = math.ceil(dev.right()), math.ceil(dev.bottom())
        ax, ay = S.m11(), S.m22()
        clase = (W.m11(), W.m12(), W.m21(), W.m22(), ax, ay, id(self.grupo._despeje))
        T = (ax * W.dx() + S.dx(), ay * W.dy() + S.dy())      # traslación escena → píxel físico
        clave = clase + (W.dx(), W.dy(), S.dx(), S.dy(), X0, Y0, X1, Y1)
        piezas = [p for p in (self._cache or []) if p[0] == clase]   # otra escala/despeje: no sirven
        falta = QtGui.QRegion(X0, Y0, X1 - X0, Y1 - Y0)
        usar = []
        for pz in reversed(piezas):                      # las más recientes primero
            _cl, Tp, Xp, Yp, img = pz
            kx, ky = T[0] - Tp[0], T[1] - Tp[1]
            if abs(kx - round(kx)) > 1e-7 or abs(ky - round(ky)) > 1e-7:
                continue                                 # corrida en fracción de píxel: otro dibujo
            caja = QtGui.QRegion(Xp + round(kx), Yp + round(ky), img.width(), img.height())
            parte = falta.intersected(caja)
            if not parte.isEmpty():
                usar.append((pz, round(kx), round(ky), parte))
                falta = falta.subtracted(caja)
            if falta.isEmpty():
                break
        if not falta.isEmpty():
            entera = clip is None or clip.boundingRect().contains(QtCore.QRect(X0 + 1, Y0 + 1, X1 - X0 - 2, Y1 - Y0 - 2))
            if not (entera or self._ultima == clave):
                self._ultima = clave
                return False
            for r in falta:                              # solo lo que falta, en rectángulos que no se tocan
                img = self._armar_cache(painter, W, S, QtCore.QRectF((r.left() - S.dx()) / ax,
                                                                      (r.top() - S.dy()) / ay,
                                                                      r.width() / ax, r.height() / ay),
                                        r.left(), r.top(), r.left() + r.width(), r.top() + r.height(),
                                        widget, visibles, m)
                pz = (clase, T, r.left(), r.top(), img)
                piezas.append(pz)
                usar.append((pz, 0, 0, QtGui.QRegion(r)))
            self._cache = self._recortar_piezas(piezas)
        else:
            self._cache = piezas
        self._ultima = clave
        painter.save()
        painter.setWorldTransform(QtGui.QTransform())
        for (_cl, _Tp, Xp, Yp, img), kx, ky, parte in usar:
            ox, oy = Xp + kx, Yp + ky                     # dónde cae la imagen ahora (px físicos)
            for r in parte:
                painter.drawImage(QtCore.QRectF((r.left() - S.dx()) / ax, (r.top() - S.dy()) / ay,
                                                r.width() / ax, r.height() / ay),
                                  img, QtCore.QRectF(r.left() - ox, r.top() - oy, r.width(), r.height()))
        painter.restore()
        return True

    @staticmethod
    def _recortar_piezas(piezas):
        """Las más recientes, a lo sumo `CACHE_MAX_PIEZAS` y `CACHE_MAX_MB`."""
        out, total = [], 0
        for pz in reversed(piezas):
            total += pz[4].sizeInBytes()
            if len(out) >= CACHE_MAX_PIEZAS or total > CACHE_MAX_MB * 1024 * 1024:
                break
            out.append(pz)
        return out[::-1]

    def _armar_cache(self, painter, W, S, vp, X0, Y0, X1, Y1, widget, visibles, m):
        ax, ay = S.m11(), S.m22()
        img = QtGui.QImage(max(1, X1 - X0), max(1, Y1 - Y0), QtGui.QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(ax)
        img.fill(QtCore.Qt.transparent)
        inv_w, _ok = W.inverted()
        escena = inv_w.mapRect(vp).adjusted(-m, -m, m, m)
        vx, vy, indices = self._en_vista(W, self.cerca(escena), [vp])
        if len(indices):
            p = QtGui.QPainter(img)
            p.setRenderHints(painter.renderHints())
            try:
                # px de la vista → píxel de la imagen = el MISMO píxel físico de la ventana − (X0, Y0)
                base = QtGui.QTransform.fromTranslate((S.dx() - X0) / ax, (S.dy() - Y0) / ay)
                self._pintar_marcas(p, indices, vx, vy, widget, visibles, base, S)
            finally:
                p.end()
        return img


class DespejeMixin:
    @staticmethod
    def _vista_de(scene, widget):
        vista = widget.parent() if widget is not None else None
        if not isinstance(vista, QtWidgets.QGraphicsView):
            vistas = scene.views()
            vista = vistas[0] if vistas else None
        return vista

    def rotulos_visibles(self, capa, widget):
        """Para cada marca de `capa`, si su rótulo se dibuja (array booleano), o None si la capa no tiene
        rótulos / no hay despeje. Una vez por escala y región de la vista (ver `despeje_rotulos`)."""
        if not DESPEJAR or not capa.con_rotulos:
            return None
        vista = self._vista_de(self.scene, widget)
        if vista is None:
            return None
        W = vista.viewportTransform()
        clave = (W.m11(), W.m12(), W.m21(), W.m22())
        vis = vista.mapToScene(vista.viewport().rect()).boundingRect()
        d = self._despeje
        if d is None or d[0] != clave or not d[1].contains(vis):
            mx, my = vis.width() * MARGEN_REGION, vis.height() * MARGEN_REGION
            region = vis.adjusted(-mx, -my, mx, my)
            d = self._despeje = (clave, region, self._despejar(W, region))
        return d[2].get(id(capa))

    def _despejar(self, W, region):
        """Voraz por prioridad (Z más alta, luego orden de llegada) sobre los rótulos con su punto en
        `region` (escena); cajas en px de pantalla SIN la traslación (no dependen del desplazamiento)."""
        orden, cajas = [], []
        for z in sorted(self.capas, reverse=True):
            capa = self.capas[z]
            if not capa.con_rotulos:
                continue
            xs, ys = capa._puntos()
            rots = capa._np_rots
            idx = np.flatnonzero(~np.isnan(rots[:, 0]) & (xs >= region.left()) & (xs <= region.right())
                                 & (ys >= region.top()) & (ys <= region.bottom()))
            if not len(idx):
                continue
            px = W.m11() * xs[idx] + W.m21() * ys[idx]
            py = W.m12() * xs[idx] + W.m22() * ys[idx]
            r = rots[idx]
            cajas.append(np.column_stack([px + r[:, 0], py + r[:, 1], px + r[:, 2], py + r[:, 3]]))
            orden.append((capa, idx))
        out = {}
        if not orden:
            return out
        puestos = despejar(np.vstack(cajas))
        k = 0
        for capa, idx in orden:
            vis = np.ones(len(capa.marcas), dtype=bool)
            vis[idx] = puestos[k:k + len(idx)]
            k += len(idx)
            out[id(capa)] = vis
        return out
