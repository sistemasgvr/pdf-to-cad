"""Estilo de la superficie importada en la Vista 3D (pedido del usuario 2026-11-14: «para no tener solo una vista»).

El visor (`visor3d.Visor3D`) tiene `estilo_superficie` (`visor3d_shaders.ESTILOS_SUPERFICIE`: relieve, cotas, malla),
`curvas_nivel` y `intervalo_curvas` (ft; 0 = automático, `mallas3d.intervalo_curvas`). Aquí: sus uniformes y la
leyenda que se pinta encima del modelo (franjas de cota del estilo «cotas» y el intervalo de las curvas). Solo
cambia CÓMO se pinta: la escena (geometría, colores guardados) es la misma.
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui

from nucleo import mallas3d as M
from traduccion.i18n import t as _tr
from ui.comun import visor3d_shaders as SH

MARGEN_PX = 14
ANCHO_BARRA_PX = 14


def rango(escena):
    """(z mínima, z máxima) de la superficie, relativas al origen de la escena, o None si no hay superficie."""
    if escena is None or not getattr(escena, "con_superficie", False):
        return None
    cache = getattr(escena, "_pdfcad_rango_sup", None)
    if cache is not None:
        return cache or None
    suelo = getattr(escena, "suelo", None)
    r = ()
    if suelo is not None and len(suelo):
        m = suelo[:, 14] < -0.5
        if np.any(m):
            z = suelo[m, 2]
            r = (float(z.min()), float(z.max()))
    try:
        escena._pdfcad_rango_sup = r
    except AttributeError:
        pass
    return r or None


def intervalo(visor):
    """Intervalo de las curvas de nivel (ft) que usa el visor."""
    elegido = float(getattr(visor, "intervalo_curvas", 0.0) or 0.0)
    if elegido > 0:
        return elegido
    r = rango(visor.escena)
    return M.intervalo_curvas(*r) if r else 1.0


def uniformes(visor, p):
    """Los uniformes del estilo (programa de triángulos y de instancias: los dos usan el mismo FRAG)."""
    estilo = getattr(visor, "estilo_superficie", "relieve")
    k = SH.ESTILOS_SUPERFICIE.index(estilo) if estilo in SH.ESTILOS_SUPERFICIE else 0
    p.setUniformValue1f("uEstiloSup", float(k))
    p.setUniformValue1f("uCurvas", 1.0 if getattr(visor, "curvas_nivel", False) else 0.0)
    p.setUniformValue1f("uIntervalo", float(intervalo(visor)))
    escena = visor.escena
    p.setUniformValue1f("uZBase", float(escena.origen[2]) if escena is not None else 0.0)
    r = rango(escena) or (0.0, 1.0)
    p.setUniformValue("uRangoZ", QtCore.QPointF(r[0], r[1]))


def _texto_ft(v):
    return f"{v:,.2f} ft".replace(",", " ")


def dibujar_leyenda(visor, pintor, oscuro):
    """Abajo a la izquierda, solo con la superficie a la vista: franjas de cota («cotas») y/o el intervalo de las
    curvas de nivel."""
    escena = visor.escena
    r = rango(escena)
    if r is None or not getattr(visor, "ver_suelo", True):
        return
    estilo = getattr(visor, "estilo_superficie", "relieve")
    curvas = getattr(visor, "curvas_nivel", False)
    if estilo != "cotas" and not curvas:
        return
    z0, z1 = r[0] + escena.origen[2], r[1] + escena.origen[2]
    fuente = QtGui.QFont(pintor.font())
    fuente.setPixelSize(11)
    pintor.setFont(fuente)
    fm = QtGui.QFontMetrics(fuente)
    tinta = QtGui.QColor(235, 238, 245) if oscuro else QtGui.QColor(30, 34, 42)
    fondo = QtGui.QColor(20, 24, 30, 170) if oscuro else QtGui.QColor(255, 255, 255, 200)
    lineas = []
    n = SH.BANDAS_COTA
    alto_franja = 14
    ancho = 0
    if estilo == "cotas":
        etiquetas = [_texto_ft(z0 + (z1 - z0) * (i + 1) / n) for i in range(n)]
        ancho = ANCHO_BARRA_PX + 8 + max(fm.horizontalAdvance(e) for e in etiquetas + [_texto_ft(z0)])
    if curvas:
        lineas.append(_tr("Curvas de nivel cada {d} ft").format(d=f"{intervalo(visor):g}"))
    alto = (n * alto_franja + fm.height() + 6 if estilo == "cotas" else 0) + len(lineas) * (fm.height() + 2)
    ancho = max([ancho] + [fm.horizontalAdvance(t) for t in lineas]) + 16
    x0 = MARGEN_PX
    y0 = visor.height() - MARGEN_PX - alto - 12
    pintor.save()
    pintor.setRenderHint(QtGui.QPainter.Antialiasing)
    pintor.setPen(QtCore.Qt.NoPen)
    pintor.setBrush(fondo)
    pintor.drawRoundedRect(QtCore.QRectF(x0, y0, ancho, alto + 12), 8, 8)
    x, y = x0 + 8, y0 + 6
    pintor.setPen(tinta)
    if estilo == "cotas":
        pintor.drawText(QtCore.QPointF(x, y + fm.ascent()), _tr("Cota"))
        y += fm.height() + 6
        for i in range(n):                                       # de arriba (lo más alto) a abajo
            k = n - 1 - i
            rgb = SH.arcoiris((k + 0.5) / n)
            pintor.fillRect(QtCore.QRectF(x, y + i * alto_franja, ANCHO_BARRA_PX, alto_franja),
                            QtGui.QColor.fromRgbF(*rgb))
            if i % 2 == 0 or i == n - 1:
                pintor.drawText(QtCore.QPointF(x + ANCHO_BARRA_PX + 6, y + i * alto_franja + fm.ascent() - 2),
                                _texto_ft(z0 + (z1 - z0) * (k + 1) / n))
        y += n * alto_franja
    for t in lineas:
        pintor.drawText(QtCore.QPointF(x, y + fm.ascent()), t)
        y += fm.height() + 2
    pintor.restore()
