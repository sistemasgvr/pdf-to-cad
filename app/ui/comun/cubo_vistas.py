"""Cubo de vistas de la Vista 3D (como el ViewCube de Civil 3D), en la esquina superior
derecha: un cubo con el nombre de cada cara y, debajo, un anillo con los puntos
cardinales. Se dibuja con QPainter ENCIMA del 3D (proyección ortográfica con la misma
orientación que la cámara).

  • Clic en una cara → esa vista (SUPERIOR = planta con el norte arriba).
  • Clic en N / E / S / O → mirar desde ese punto cardinal (misma inclinación).
  • Arrastrar sobre el cubo o el anillo → orbitar.
  • La cara (o la letra) bajo el ratón se resalta.

Ejes del dibujo: +X = este, +Y = norte, +Z = arriba (como el visor).
"""
from __future__ import annotations

import math

import numpy as np
from PySide6 import QtCore, QtGui

from traduccion.i18n import t as _tr

LADO_PX = 34            # medio lado del cubo en pantalla
MARGEN_PX = 18
R_ANILLO = 1.85         # radio del anillo (en medios lados del cubo)
Z_ANILLO = -1.15

# (clave, texto, normal, esquinas TL, TR, BR, BL vistas desde afuera con el texto derecho)
CARAS = (
    ("superior", "SUPERIOR", (0, 0, 1), ((-1, 1, 1), (1, 1, 1), (1, -1, 1), (-1, -1, 1))),
    ("inferior", "INFERIOR", (0, 0, -1), ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1))),
    ("frontal", "FRONTAL", (0, -1, 0), ((-1, -1, 1), (1, -1, 1), (1, -1, -1), (-1, -1, -1))),
    ("posterior", "POSTERIOR", (0, 1, 0), ((1, 1, 1), (-1, 1, 1), (-1, 1, -1), (1, 1, -1))),
    ("derecha", "DERECHA", (1, 0, 0), ((1, -1, 1), (1, 1, 1), (1, 1, -1), (1, -1, -1))),
    ("izquierda", "IZQUIERDA", (-1, 0, 0), ((-1, 1, 1), (-1, -1, 1), (-1, -1, -1), (-1, 1, -1))),
)
# (yaw, pitch) de cada cara: la cámara mira la cara desde afuera
VISTA_CARA = {"superior": (-90.0, 89.5), "inferior": (-90.0, -89.5), "frontal": (-90.0, 0.0),
              "posterior": (90.0, 0.0), "derecha": (0.0, 0.0), "izquierda": (180.0, 0.0)}
# (clave, texto, dirección) de los puntos cardinales; yaw = mirar DESDE ese lado
CARDINALES = (("N", "N", (0, 1)), ("E", "E", (1, 0)), ("S", "S", (0, -1)), ("O", "O", (-1, 0)))
YAW_CARDINAL = {"N": 90.0, "E": 0.0, "S": -90.0, "O": 180.0}


class CuboVistas:
    def __init__(self):
        self.sobre = None               # ("cara", clave) | ("cardinal", clave) | ("anillo", None) | None
        self._caras = []                # [(clave, QPolygonF)] visibles, la de adelante al final
        self._letras = []               # [(clave, QPointF, delante)]
        self._centro = QtCore.QPointF()
        self._anillo = None             # QPolygonF del anillo

    # ── proyección ──
    @staticmethod
    def _base(cam):
        der, arriba = cam.ejes()
        adelante = cam.objetivo - cam.ojo()
        return np.asarray(der), np.asarray(arriba), adelante / np.linalg.norm(adelante)

    def _proy(self, p, base):
        der, arriba, _ad = base
        p = np.asarray(p, float)
        return QtCore.QPointF(self._centro.x() + float(np.dot(p, der)) * LADO_PX,
                              self._centro.y() - float(np.dot(p, arriba)) * LADO_PX)

    def rect(self, ancho):
        """Zona del widget que ocupa el cubo (para saber si el ratón está encima)."""
        lado = int(LADO_PX * (R_ANILLO + 0.9) * 2)
        return QtCore.QRect(ancho - lado - MARGEN_PX + 10, MARGEN_PX - 10, lado, lado)

    # ── dibujo ──
    def dibujar(self, painter, ancho, cam, oscuro=True):
        r = self.rect(ancho)
        self._centro = QtCore.QPointF(r.center())
        base = self._base(cam)
        _der, _arr, adelante = base
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        texto = QtGui.QColor(235, 235, 235) if oscuro else QtGui.QColor(40, 40, 40)
        resalte = QtGui.QColor(70, 140, 255)

        # anillo con los puntos cardinales
        pts = [self._proy((R_ANILLO * math.cos(a), R_ANILLO * math.sin(a), Z_ANILLO), base)
               for a in np.linspace(0, 2 * math.pi, 64, endpoint=False)]
        self._anillo = QtGui.QPolygonF(pts)
        banda = QtGui.QColor(95, 95, 95, 200) if oscuro else QtGui.QColor(150, 150, 150, 200)
        if self.sobre and self.sobre[0] in ("anillo", "cardinal"):
            banda = QtGui.QColor(resalte.red(), resalte.green(), resalte.blue(), 200)
        painter.setPen(QtGui.QPen(banda, 7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPolygon(self._anillo)
        f = painter.font(); f.setBold(True); f.setPointSizeF(8.5); painter.setFont(f)
        self._letras = []
        for clave, letra, (dx, dy) in CARDINALES:
            p3 = (dx * R_ANILLO, dy * R_ANILLO, Z_ANILLO)
            delante = float(np.dot(p3, adelante)) < 0          # entre el cubo y la cámara
            self._letras.append((clave, self._proy(p3, base), delante, letra))
        estilo = (texto, resalte, oscuro)
        for le in self._letras:                                 # las de atrás quedan tapadas por el cubo
            if not le[2]:
                self._letra(painter, le, estilo)

        # caras visibles, de atrás hacia adelante
        visibles = []
        for clave, nombre, normal, esq in CARAS:
            if float(np.dot(normal, adelante)) < -1e-3:          # mira hacia la cámara
                prof = float(np.dot(np.mean(esq, axis=0), adelante))
                visibles.append((prof, clave, nombre, normal, esq))
        visibles.sort(reverse=True)
        self._caras = []
        f.setPointSizeF(6.5); painter.setFont(f)
        for _prof, clave, nombre, normal, esq in visibles:
            poli = QtGui.QPolygonF([self._proy(p, base) for p in esq])
            self._caras.append((clave, poli))
            luz = 0.78 + 0.22 * abs(float(np.dot(normal, adelante)))
            gris = int(225 * luz) if oscuro else int(245 * luz)
            relleno = resalte if self.sobre == ("cara", clave) else QtGui.QColor(gris, gris, gris)
            painter.setPen(QtGui.QPen(QtGui.QColor(90, 90, 90), 1))
            painter.setBrush(relleno)
            painter.drawPolygon(poli)
            # texto sobre la cara, deformado con ella (como el ViewCube)
            ancho_t = 100.0
            fuente = QtGui.QPolygonF([QtCore.QPointF(0, 0), QtCore.QPointF(ancho_t, 0),
                                      QtCore.QPointF(ancho_t, ancho_t), QtCore.QPointF(0, ancho_t)])
            tr = QtGui.QTransform()
            if QtGui.QTransform.quadToQuad(fuente, poli, tr) and abs(float(np.dot(normal, adelante))) > 0.25:
                painter.save()
                painter.setTransform(tr, True)
                ft = painter.font(); ft.setPointSizeF(15)
                ancho_txt = QtGui.QFontMetricsF(ft).horizontalAdvance(_tr(nombre))
                if ancho_txt > ancho_t * 0.86:              # «IZQUIERDA», «POSTERIOR»: que entren
                    ft.setPointSizeF(15 * ancho_t * 0.86 / ancho_txt)
                painter.setFont(ft)
                painter.setPen(QtGui.QColor(255, 255, 255) if self.sobre == ("cara", clave) else QtGui.QColor(50, 50, 50))
                painter.drawText(QtCore.QRectF(0, 0, ancho_t, ancho_t), QtCore.Qt.AlignCenter, _tr(nombre))
                painter.restore()
        f.setPointSizeF(8.5); painter.setFont(f)
        for le in self._letras:                                 # las de adelante, encima del cubo
            if le[2]:
                self._letra(painter, le, estilo)
        painter.restore()

    def _letra(self, painter, letra, estilo):
        clave, q, _delante, texto_letra = letra
        texto, resalte, oscuro = estilo
        caja = QtCore.QRectF(q.x() - 8, q.y() - 8, 16, 16)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(resalte if self.sobre == ("cardinal", clave) else
                         (QtGui.QColor(30, 30, 30, 230) if oscuro else QtGui.QColor(245, 245, 245, 235)))
        painter.drawEllipse(caja)
        painter.setPen(QtGui.QColor(255, 255, 255) if self.sobre == ("cardinal", clave) else texto)
        painter.drawText(caja, QtCore.Qt.AlignCenter, _tr(texto_letra))

    # ── ratón ──
    def que_hay(self, pos):
        """Lo que hay bajo `pos` (QPointF): ("cara", clave), ("cardinal", clave),
        ("anillo", None) o None."""
        def letra(delante):
            for clave, q, adelante, _t in self._letras:
                if adelante == delante and (q.x() - pos.x()) ** 2 + (q.y() - pos.y()) ** 2 <= 10 ** 2:
                    return ("cardinal", clave)
            return None
        if letra(True):                                  # adelante del cubo: gana la letra
            return letra(True)
        for clave, poli in reversed(self._caras):
            if poli.containsPoint(pos, QtCore.Qt.OddEvenFill):
                return ("cara", clave)
        if letra(False):                                 # detrás, solo donde no la tapa el cubo
            return letra(False)
        if self._anillo is not None and len(self._anillo):
            d = min(math.hypot(p.x() - pos.x(), p.y() - pos.y()) for p in self._anillo)
            if d <= 7:
                return ("anillo", None)
        return None

    @staticmethod
    def vista_de(objeto, pitch_actual):
        """(yaw, pitch) al hacer clic en `objeto`, o None."""
        if not objeto:
            return None
        tipo, clave = objeto
        if tipo == "cara":
            return VISTA_CARA[clave]
        if tipo == "cardinal":
            return YAW_CARDINAL[clave], pitch_actual
        return None
