"""Resumen por zona de las marcas del lienzo con la vista alejada (pedido del usuario 2026-11-14: un proyecto con
29 000 utilidades y ~88 000 marcas —conflictos, observaciones, avisos, accesorios— tardaba ~0.4–0.6 s en cada paso
de desplazar, de zoom o de mover el ratón: casi todo era pintar marcas que de lejos no se pueden leer).

Como los mapas: si en lo que se ve hay más de `UMBRAL` marcas, en lugar de cada una se pinta UN globo por zona
(celdas de `CELDA_PX` de pantalla, fijas al plano: desplazar no las cambia) con cuántas hay, del color de lo más
grave de esa zona; el globo (tooltip) dice cuántas de cada clase y un clic acerca a esa zona. Al acercarse (menos de
`UMBRAL` a la vista) vuelven las marcas de siempre, idénticas. Las marcas, sus listas y los cálculos NO cambian:
solo qué se pinta.

Cada marca dice su clase con `clase(item, CLASE)`; las que no la dicen (el círculo rojo de un conflicto, que ya
cuenta su etiqueta C-n) no se cuentan en los globos.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6 import QtCore, QtGui

from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

UMBRAL = 2500                     # marcas a la vista a partir de las que se resume
CELDA_PX = 84.0                   # lado de cada zona, en px de pantalla
RESUMIR = True                    # (las pruebas de «se ve igual» lo apagan)

# clase → (orden de gravedad, color, nombre en singular/plural). El globo toma el color de la más grave.
ACCESORIO, CRUCE, AVISO, OBSERVACION, CONFLICTO = 1, 2, 3, 4, 5
CLASES = {
    ACCESORIO: ("#64748b", N_("{n} accesorio(s)")),
    CRUCE: ("#2563eb", N_("{n} cruce(s) a distinta cota")),
    AVISO: ("#d97706", N_("{n} aviso(s)")),
    OBSERVACION: ("#ea580c", N_("{n} observación(es)")),
    CONFLICTO: ("#dc2626", N_("{n} conflicto(s)")),
}
N_CLASES = max(CLASES) + 1


def clase(item, cual, cuantos=1):
    """Anota la clase de la marca para el resumen por zona y por cuántos cuenta (una etiqueta «C-3 · C-4» = 2; una
    insignia con tres avisos = 3). Devuelve `item`."""
    try:
        item._pdfcad_clase = int(cual)
        item._pdfcad_peso = max(1, int(cuantos))
    except AttributeError:
        pass
    return item


def _corto(n):
    return str(n) if n < 1000 else (f"{n / 1000:.1f}k" if n < 10000 else f"{n // 1000}k")


class Zonas:
    """Los globos de una escala: centro (escena), total, clase más grave y cuántas de cada clase."""

    def __init__(self, xs, ys, clases, lado, pesos=None):
        self.lado = lado
        self.n = 0
        if not len(xs):
            self.x = self.y = np.zeros(0)
            self.total = self.grave = np.zeros(0, dtype=int)
            self.por_clase = np.zeros((0, N_CLASES), dtype=int)
            return
        ci, cj = np.floor(xs / lado).astype(np.int64), np.floor(ys / lado).astype(np.int64)
        clave = (ci - ci.min()) * (int(cj.max() - cj.min()) + 1) + (cj - cj.min())
        _u, inv = np.unique(clave, return_inverse=True)
        n = int(inv.max()) + 1
        self.n = n
        pesos = np.ones(len(xs), dtype=int) if pesos is None else np.asarray(pesos, dtype=int)
        marcas = np.bincount(inv, minlength=n)
        self.total = np.bincount(inv, weights=pesos, minlength=n).astype(int)
        mx = np.bincount(inv, weights=xs, minlength=n) / marcas
        my = np.bincount(inv, weights=ys, minlength=n) / marcas
        # a medio camino entre el centro de la zona y el de sus marcas: fiel al lugar y sin encimarse con la vecina
        cx = (np.bincount(inv, weights=ci, minlength=n) / marcas + 0.5) * lado
        cy = (np.bincount(inv, weights=cj, minlength=n) / marcas + 0.5) * lado
        self.x, self.y = (mx + cx) / 2.0, (my + cy) / 2.0
        self.por_clase = np.zeros((n, N_CLASES), dtype=int)
        np.add.at(self.por_clase, (inv, clases), pesos)
        self.grave = np.zeros(n, dtype=int)
        np.maximum.at(self.grave, inv, clases)

    def texto(self, k):
        partes = [_tr(CLASES[c][1]).format(n=int(self.por_clase[k, c]))
                  for c in sorted(CLASES, reverse=True) if self.por_clase[k, c]]
        return "\n".join(partes + [_tr("Clic o acércate para verlos uno por uno.")])


class ResumenMixin:
    """Para `GrupoMarcas`: cuándo se resume y los globos de cada escala."""

    def _vista_y_region(self, widget):
        vista = self._vista_de(self.scene, widget)
        if vista is None:
            return None, None, None
        W = vista.viewportTransform()
        return vista, W, vista.mapToScene(vista.viewport().rect()).boundingRect()

    def _version(self):
        return tuple((id(c), len(c.marcas), id(c._ocultas)) for c in self.capas.values())

    def en_resumen(self, widget=None) -> bool:
        """¿Se pinta el resumen por zona en lugar de las marcas? Una decisión por vista (la misma para todas las
        capas y para los repintados parciales)."""
        if not RESUMIR or self.cargando:
            return False
        vista, W, vis = self._vista_y_region(widget)
        if vista is None or not getattr(vista, "resumen_marcas", False):
            return False                                  # solo el lienzo del editor (no las capturas del informe)
        clave = (W.m11(), W.m12(), W.m21(), W.m22(), W.dx(), W.dy(), vis.width(), vis.height(), self._version())
        e = getattr(self, "_res_estado", None)
        if e is None or e[0] != clave:
            n = 0
            for c in self.capas.values():
                if c.marcas:
                    n += len(c.cerca(vis))
                    if n > UMBRAL:
                        break
            e = self._res_estado = (clave, n > UMBRAL)
        return e[1]

    def zonas(self, escala) -> Zonas:
        """Los globos a esa escala (px de pantalla por px del plano), de TODAS las marcas con clase."""
        clave = (round(escala, 9), self._version())
        z = getattr(self, "_res_zonas", None)
        if z is None or z[0] != clave:
            xs, ys, cl, ps = [], [], [], []
            for c in self.capas.values():
                if not c.marcas:
                    continue
                x, y = c._puntos()
                k = np.asarray(c.clases, dtype=int)
                m = k > 0
                if c._ocultas is not None and len(c._ocultas) == len(m):
                    m &= ~c._ocultas
                xs.append(x[m]); ys.append(y[m]); cl.append(k[m]); ps.append(np.asarray(c.pesos, dtype=int)[m])
            if xs:
                xs, ys, cl, ps = np.concatenate(xs), np.concatenate(ys), np.concatenate(cl), np.concatenate(ps)
            else:
                xs = ys = np.zeros(0); cl = ps = np.zeros(0, dtype=int)
            z = self._res_zonas = (clave, Zonas(xs, ys, cl, CELDA_PX / max(escala, 1e-9), ps))
        return z[1]

    def zona_en(self, punto, widget=None):
        """(zonas, índice) del globo bajo `punto` (escena) si se está resumiendo; si no, None."""
        if not self.en_resumen(widget):
            return None
        _vista, W, _vis = self._vista_y_region(widget)
        escala = max(math.hypot(W.m11(), W.m12()), 1e-9)
        z = self.zonas(escala)
        if not z.n:
            return None
        d2 = (z.x - punto.x()) ** 2 + (z.y - punto.y()) ** 2
        k = int(np.argmin(d2))
        r = (radio_px(int(z.total[k])) + 3.0) / escala
        return (z, k) if d2[k] <= r * r else None

    def pintar_resumen(self, painter, rect, widget=None):
        """Los globos de las zonas que tocan `rect` (escena). Lo llama el lienzo en `drawForeground` (encima de
        todo); si no se está resumiendo, no pinta nada."""
        if not self.en_resumen(widget):
            return
        W = QtGui.QTransform(painter.worldTransform())
        escala = max(math.hypot(W.m11(), W.m12()), 1e-9)
        z = self.zonas(escala)
        if not z.n:
            return
        m = 40.0 / escala
        r = QtCore.QRectF(rect).adjusted(-m, -m, m, m)
        idx = np.flatnonzero((z.x >= r.left()) & (z.x <= r.right()) & (z.y >= r.top()) & (z.y <= r.bottom()))
        if not len(idx):
            return
        vx = W.m11() * z.x[idx] + W.m21() * z.y[idx] + W.dx()
        vy = W.m12() * z.x[idx] + W.m22() * z.y[idx] + W.dy()
        painter.save()
        try:
            painter.setWorldTransform(QtGui.QTransform())
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            f = QtGui.QFont(painter.font())
            f.setPixelSize(11)
            f.setBold(True)
            painter.setFont(f)
            borde = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5)
            blanco = QtGui.QPen(QtGui.QColor(255, 255, 255))
            colores = {c: QtGui.QColor(v[0]) for c, v in CLASES.items()}
            for k, x, y in zip(idx.tolist(), vx.tolist(), vy.tolist()):
                n = int(z.total[k])
                rad = radio_px(n)
                painter.setPen(borde)
                painter.setBrush(colores.get(int(z.grave[k]), colores[ACCESORIO]))
                painter.drawEllipse(QtCore.QPointF(x, y), rad, rad)
                painter.setPen(blanco)
                painter.drawText(QtCore.QRectF(x - rad, y - rad, 2 * rad, 2 * rad), QtCore.Qt.AlignCenter, _corto(n))
        finally:
            painter.restore()


def radio_px(n):
    return 11.0 + 2.6 * min(len(_corto(n)), 4)
