"""Conflictos del dibujo con NÚMERO (PURO: sin Qt).

Junta en una sola lista los cruces a la misma cota que el plugin no une y todas las
alertas rojas del lienzo (5+ tuberías en un punto, escalones de cota, tramos cortos
entre codos, codos de retorno, uniones con pendiente, conexiones verticales con
pendiente, redes distintas que chocan, cruces sin conexión) y les da un número C-1,
C-2… en orden de LECTURA del plano (de arriba abajo y de izquierda a derecha). El mismo
número se ve en el lienzo, en la Vista 3D, en la Tabla de datos y en su Excel.

Al cambiar el dibujo o las cotas los conflictos se recalculan: el número es el del
estado actual (un conflicto resuelto desaparece y los demás se renumeran).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from traduccion.i18n_core import N_

TITULOS = {
    "cruce": N_("Cruce a la misma cota"),
    "exceso": N_("5 o más tuberías en un punto"),
    "escalon": N_("Escalón de cota"),
    "codos": N_("Tramo muy corto entre codos"),
    "retorno": N_("Codo de retorno"),
    "pendiente": N_("Unión con pendiente"),
    "inclinada": N_("Conexión vertical con pendiente"),
    "redes": N_("Choque entre redes distintas"),
    "choque": N_("Cruce sin conexión"),
}
FILA_PX = 8.0           # puntos a menos de esto en vertical van en la misma «fila» de lectura


@dataclass
class Conflicto:
    id: str                                  # «C-1»
    clave: str                               # TITULOS
    x: float                                 # lugar en el lienzo (px)
    y: float
    mensaje: str = ""
    pipes: list = field(default_factory=list)       # índices de las utilidades
    cotas: list = field(default_factory=list)       # cotas (ft) en el punto, una por utilidad (o vacío)

    @property
    def titulo(self):
        return TITULOS.get(self.clave, self.clave)

    @property
    def diferencia(self):
        """Diferencia de cota entre las dos utilidades (ft), o None."""
        z = [c for c in self.cotas if c is not None]
        return abs(z[0] - z[1]) if len(z) >= 2 else None


MISMO_PX = 1.5          # el mismo conflicto visto por varios pares de tramos (cruce en un vértice)


def _sin_repetidos(items):
    """Un cruce en un VÉRTICE lo ven varios pares de tramos de las mismas dos utilidades: es UN
    conflicto (antes salían C-10…C-13 en el mismo punto)."""
    out = []
    for c in items:
        clave = (c["clave"], frozenset(i for i in c.get("pipes") or [] if i is not None))
        if any((o["clave"], frozenset(i for i in o.get("pipes") or [] if i is not None)) == clave
               and (float(o["x"]) - float(c["x"])) ** 2 + (float(o["y"]) - float(c["y"])) ** 2 <= MISMO_PX ** 2
               for o in out):
            continue
        out.append(c)
    return out


def numerar(items):
    """[Conflicto] con su número. `items` = [{clave, x, y, mensaje, pipes, cotas}]."""
    filas, actual = [], []
    for c in sorted(_sin_repetidos(items), key=lambda c: (float(c["y"]), float(c["x"]))):
        if actual and float(c["y"]) - float(actual[0]["y"]) > FILA_PX:      # otra fila de lectura
            filas.append(actual); actual = []
        actual.append(c)
    if actual:
        filas.append(actual)
    orden = [c for fila in filas for c in sorted(fila, key=lambda c: (float(c["x"]), c["clave"]))]
    return [Conflicto(f"C-{n}", c["clave"], float(c["x"]), float(c["y"]), c.get("mensaje", ""),
                      [int(i) for i in c.get("pipes") or [] if i is not None],
                      [None if z is None else float(z) for z in c.get("cotas") or []])
            for n, c in enumerate(orden, 1)]


def agrupar(conflictos, tol):
    """Los conflictos en el MISMO lugar (≤ tol px) juntos, para una sola etiqueta «C-10 · C-13»
    (si no, una tapa a la otra). Devuelve [[Conflicto, …]] en el orden de numeración."""
    grupos = []
    for c in conflictos or []:
        g = next((g for g in grupos if (g[0].x - c.x) ** 2 + (g[0].y - c.y) ** 2 <= tol * tol), None)
        if g is None:
            grupos.append([c])
        else:
            g.append(c)
    return grupos


def en_punto(conflictos, x, y, tol):
    """Conflictos a ≤ tol (px) del punto."""
    return [c for c in conflictos or [] if (c.x - x) ** 2 + (c.y - y) ** 2 <= tol * tol]
