"""Conflictos del dibujo con NÚMERO (PURO: sin Qt).

Junta en una sola lista los cruces a la misma cota que el plugin no une y todas las
alertas rojas del lienzo (5+ tuberías en un punto, escalones de cota, tramos cortos
entre codos, codos de retorno, uniones con pendiente, conexiones verticales con
pendiente, redes distintas que chocan, cruces sin conexión) y les da un número C-1,
C-2… en orden de LECTURA del plano (de arriba abajo y de izquierda a derecha). El mismo
número se ve en el lienzo, en la Vista 3D, en la Tabla de datos y en su Excel.

Los números son FIJOS (pedido del usuario 2026-10-29: resolver uno con el asistente renumeraba
todos y el usuario se perdía): con un `Registro`, cada conflicto conserva el número que tuvo la
primera vez (mismo tipo, mismas utilidades y cerca del mismo lugar); uno resuelto queda en el
registro como «resuelto» con su número (si vuelve —Ctrl+Z—, vuelve con él) y uno nuevo toma el
siguiente número libre. Sin registro (o vacío) se numera en orden de lectura, como siempre.
"""
from __future__ import annotations

import math
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
    conflicto (antes salían C-10…C-13 en el mismo punto). «¿Ya está?» mira solo los de las celdas vecinas de
    `MISMO_PX` (uno a ≤ `MISMO_PX` está a lo sumo una celda más allá): con 26 mil cruces de una hoja compuesta era
    todos contra todos, 3.5 s en cada redibujo (2026-11-15)."""
    out = []
    celdas = {}
    for c in items:
        clave = (c["clave"], frozenset(i for i in c.get("pipes") or [] if i is not None))
        x, y = float(c["x"]), float(c["y"])
        if not (math.isfinite(x) and math.isfinite(y)):      # (nunca está a ≤ MISMO_PX de otro)
            out.append(c)
            continue
        cx, cy = math.floor(x / MISMO_PX), math.floor(y / MISMO_PX)
        if any(k == clave and (ox - x) ** 2 + (oy - y) ** 2 <= MISMO_PX ** 2
               for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k, ox, oy in celdas.get((cx + dx, cy + dy), ())):
            continue
        out.append(c)
        celdas.setdefault((cx, cy), []).append((clave, x, y))
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


SIGUE_PX = 40.0         # un conflicto que se corrió hasta esto (otra cota, el dibujo retocado) es el mismo


class Registro:
    """Números ya dados: [{n, clave, pipes (frozenset), x, y, resuelto}] y el siguiente libre."""

    def __init__(self):
        self.entradas = []
        self.siguiente = 1

    def resueltos(self):
        return [e for e in self.entradas if e["resuelto"]]

    def a_dict(self):
        return {"siguiente": self.siguiente,
                "entradas": [dict(e, pipes=sorted(e["pipes"])) for e in self.entradas]}

    @classmethod
    def de_dict(cls, d):
        r = cls()
        if isinstance(d, dict):
            try:
                r.entradas = [dict(e, n=int(e["n"]), pipes=frozenset(int(i) for i in e.get("pipes") or []),
                                   x=float(e["x"]), y=float(e["y"]), resuelto=bool(e.get("resuelto")))
                              for e in d.get("entradas") or []]
                r.siguiente = max([int(d.get("siguiente") or 1)] + [e["n"] + 1 for e in r.entradas])
            except (KeyError, TypeError, ValueError):
                return cls()
        return r


def numerar_fijo(items, registro):
    """Como `numerar`, pero con los números de `registro` (y lo pone al día). Devuelve los conflictos
    vigentes ordenados por número."""
    if not registro.entradas:
        out = numerar(items)
        registro.entradas = [dict(n=int(c.id[2:]), clave=c.clave, pipes=frozenset(c.pipes), x=c.x, y=c.y,
                                  resuelto=False) for c in out]
        registro.siguiente = len(out) + 1
        return out
    libres = list(registro.entradas)
    usados = set()
    nuevos = []
    out = []
    # (los del registro por celdas de SIGUE_PX: uno a ≤ SIGUE_PX está a lo sumo una celda más allá; los
    # candidatos son un conjunto y gana el de menor (distancia, número): el orden de búsqueda no importa)
    celdas = {}
    for e in libres:
        if math.isfinite(e["x"]) and math.isfinite(e["y"]):
            celdas.setdefault((math.floor(e["x"] / SIGUE_PX), math.floor(e["y"] / SIGUE_PX)), []).append(e)
    for c in numerar(items):                                  # en orden de lectura: los nuevos, también
        pipes = frozenset(c.pipes)
        if math.isfinite(c.x) and math.isfinite(c.y):
            kx, ky = math.floor(c.x / SIGUE_PX), math.floor(c.y / SIGUE_PX)
            cerca = [e for dx in (-1, 0, 1) for dy in (-1, 0, 1) for e in celdas.get((kx + dx, ky + dy), ())]
        else:
            cerca = []
        cand = [e for e in cerca if id(e) not in usados and e["clave"] == c.clave and e["pipes"] == pipes
                and (e["x"] - c.x) ** 2 + (e["y"] - c.y) ** 2 <= SIGUE_PX ** 2]
        if not cand:
            nuevos.append(c)
            continue
        e = min(cand, key=lambda e: ((e["x"] - c.x) ** 2 + (e["y"] - c.y) ** 2, e["n"]))
        usados.add(id(e))
        e.update(x=c.x, y=c.y, resuelto=False)
        c.id = f"C-{e['n']}"
        out.append(c)
    for e in registro.entradas:
        if id(e) not in usados:
            e["resuelto"] = True
    for c in nuevos:
        n = registro.siguiente
        registro.siguiente += 1
        registro.entradas.append(dict(n=n, clave=c.clave, pipes=frozenset(c.pipes), x=c.x, y=c.y, resuelto=False))
        c.id = f"C-{n}"
        out.append(c)
    return sorted(out, key=lambda c: int(c.id[2:]))


def agrupar(conflictos, tol):
    """Los conflictos en el MISMO lugar (≤ tol px) juntos, para una sola etiqueta «C-10 · C-13»
    (si no, una tapa a la otra). Devuelve [[Conflicto, …]] en el orden de numeración. Cada uno va al PRIMER grupo
    cuyo primero está a ≤ tol: se buscan en las celdas vecinas (de lado tol) y gana el de menor índice."""
    grupos = []
    if not tol or tol <= 0 or not math.isfinite(tol):
        for c in conflictos or []:
            g = next((g for g in grupos if (g[0].x - c.x) ** 2 + (g[0].y - c.y) ** 2 <= tol * tol), None)
            if g is None:
                grupos.append([c])
            else:
                g.append(c)
        return grupos
    celdas = {}                                       # (un primero sin coordenada finita no recibe a nadie)
    for c in conflictos or []:
        if math.isfinite(c.x) and math.isfinite(c.y):
            kx, ky = math.floor(c.x / tol), math.floor(c.y / tol)
            dentro = [k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in celdas.get((kx + dx, ky + dy), ())
                      if (grupos[k][0].x - c.x) ** 2 + (grupos[k][0].y - c.y) ** 2 <= tol * tol]
        else:
            kx = ky = None
            dentro = []
        if dentro:
            grupos[min(dentro)].append(c)
        else:
            if kx is not None:
                celdas.setdefault((kx, ky), []).append(len(grupos))
            grupos.append([c])
    return grupos


def en_punto(conflictos, x, y, tol):
    """Conflictos a ≤ tol (px) del punto."""
    return [c for c in conflictos or [] if (c.x - x) ** 2 + (c.y - y) ** 2 <= tol * tol]
