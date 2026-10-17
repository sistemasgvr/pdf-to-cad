"""Índices espaciales del plano (PURO: sin Qt): MISMOS resultados, sin comparar todo con todo.

Pedido del usuario 2026-10-16 («sobre todo cuando se hace de forma masiva»): con 400
utilidades cada redibujo del lienzo tardaba ~20 s, casi todo en comparar CADA tramo con
TODOS los demás (cruces, choques) y cada punto con todos (juntas, avisos, color de los
buzones). Aquí las celdas solo proponen los candidatos que PUEDEN cumplir; quien llama hace
la MISMA prueba de siempre, en el MISMO orden (los índices salen ordenados), así el
resultado no cambia ni en el orden ni en el «el primero gana».

  · `pares_tramos(segs)`: pares (a, b), a < b, cuyos recuadros —agrandados por la
    tolerancia de los cruces (t, u ∈ [−1e-6, 1 + 1e-6]) y un margen de redondeo— se tocan.
    Un par fuera de la lista no tiene cruce: ningún punto de cruce cae fuera de los dos
    recuadros agrandados.
  · `IndicePuntos(puntos, celda)`: los puntos a ≤ r (misma cuenta dx² + dy² ≤ r²) de un
    lugar, en el orden original.
  · `IndiceUtilidades(pipes)`: las utilidades con algún tramo a ≤ r de un punto (ratón).
"""
from __future__ import annotations

import math

MARGEN_PX = 1e-3          # redondeo de la coma flotante en coordenadas de miles de px
TOL_PARAM = 1e-6          # la de `_inter` / `_seg_inter`


def _caja(p1, p2):
    L = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    m = TOL_PARAM * L + TOL_PARAM + MARGEN_PX
    return (min(p1[0], p2[0]) - m, min(p1[1], p2[1]) - m, max(p1[0], p2[0]) + m, max(p1[1], p2[1]) + m)


def pares_tramos(segs):
    """[(a, b)] ordenados (a < b) de los tramos `segs` = [(p1, p2)] cuyos recuadros se tocan."""
    n = len(segs)
    if n < 2:
        return []
    cajas = [_caja(p1, p2) for p1, p2 in segs]
    lados = sorted(max(c[2] - c[0], c[3] - c[1]) for c in cajas)
    celda = max(lados[len(lados) // 2], 1.0)             # el tramo típico ocupa 1–4 celdas
    celdas = {}
    for i, (x0, y0, x1, y1) in enumerate(cajas):
        for cx in range(math.floor(x0 / celda), math.floor(x1 / celda) + 1):
            for cy in range(math.floor(y0 / celda), math.floor(y1 / celda) + 1):
                celdas.setdefault((cx, cy), []).append(i)
    pares = set()
    for lista in celdas.values():
        if len(lista) < 2:
            continue
        for u in range(len(lista)):
            a = lista[u]
            ca = cajas[a]
            for b in lista[u + 1:]:
                cb = cajas[b]
                if ca[0] <= cb[2] and cb[0] <= ca[2] and ca[1] <= cb[3] and cb[1] <= ca[3]:
                    pares.add((a, b) if a < b else (b, a))
    return sorted(pares)


class IndiceUtilidades:
    """Las utilidades que tienen ALGÚN tramo cerca de un punto (para el ratón: hover, imán,
    clic). `cerca(x, y, r)` = índices ordenados de las utilidades con un tramo cuyo recuadro,
    agrandado r, contiene el punto: toda utilidad con un tramo o vértice a ≤ r está. Quien
    llama recorre SOLO esas, en el mismo orden y con la misma cuenta: mismo resultado.

    `vigente(pipes)` dice si el índice sigue sirviendo: compara la geometría (cada punto),
    así un cambio hecho sin redibujar no deja un índice viejo."""

    def __init__(self, pipes, firma=None):
        self.firma = _firma(pipes) if firma is None else firma
        cajas = []
        for i, pts in enumerate(self.firma):
            for a, b in zip(pts, pts[1:]):
                cajas.append((i,) + _caja(a, b))
        self.cajas = cajas
        lados = sorted(max(c[3] - c[1], c[4] - c[2]) for c in cajas) or [1.0]
        self.celda = max(lados[len(lados) // 2], 1.0)
        self.celdas = {}
        c = self.celda
        for k, (_i, x0, y0, x1, y1) in enumerate(cajas):
            for cx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
                for cy in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                    self.celdas.setdefault((cx, cy), []).append(k)

    def vigente(self, pipes):
        return _firma(pipes) == self.firma


    def cerca(self, x, y, r):
        c = self.celda
        r = r + MARGEN_PX
        out = set()
        for cx in range(math.floor((x - r) / c), math.floor((x + r) / c) + 1):
            for cy in range(math.floor((y - r) / c), math.floor((y + r) / c) + 1):
                for k in self.celdas.get((cx, cy), ()):
                    i, x0, y0, x1, y1 = self.cajas[k]
                    if x0 - r <= x <= x1 + r and y0 - r <= y <= y1 + r:
                        out.add(i)
        return sorted(out)


def utilidades_cerca(cache, pipes, x, y, r):
    """Índices (en orden) de las utilidades a revisar para el punto: las de algún tramo a
    ≤ r según el índice de `cache` (dict que guarda quien llama). Mientras la geometría
    cambia en cada llamada (arrastrando un vértice) no vale la pena armarlo: se devuelven
    TODAS, como antes; con la misma geometría dos veces seguidas se arma y se usa."""
    ix = cache.get("indice")
    if ix is not None and ix.vigente(pipes):
        return ix.cerca(x, y, r)
    firma = _firma(pipes)
    if cache.get("firma") == firma:
        cache["indice"] = ix = IndiceUtilidades(pipes, firma)
        return ix.cerca(x, y, r)
    cache["indice"] = None
    cache["firma"] = firma
    return range(len(pipes))

def _firma(pipes):
    """La geometría de las utilidades como tuplas (se compara punto por punto; un punto que
    ya es tupla —inmutable— se toma tal cual: 400 utilidades ≈ 0.3 ms)."""
    return [tuple(map(tuple, p.get("pts") or ())) for p in pipes]


class IndicePuntos:
    """Puntos por celdas de `celda` px; `en_radio` = los índices a ≤ r, en orden."""

    def __init__(self, puntos, celda):
        self.puntos = [(float(x), float(y)) for x, y in puntos]
        self.celda = max(float(celda), 1e-6)
        self.celdas = {}
        for i, (x, y) in enumerate(self.puntos):
            self.celdas.setdefault((math.floor(x / self.celda), math.floor(y / self.celda)), []).append(i)

    def en_caja(self, x, y, r):
        """Índices (ordenados) de los puntos con |dx| ≤ r y |dy| ≤ r (candidatos)."""
        c = self.celda
        out = []
        for cx in range(math.floor((x - r) / c), math.floor((x + r) / c) + 1):
            for cy in range(math.floor((y - r) / c), math.floor((y + r) / c) + 1):
                for i in self.celdas.get((cx, cy), ()):
                    px, py = self.puntos[i]
                    if abs(px - x) <= r and abs(py - y) <= r:
                        out.append(i)
        out.sort()
        return out

    def en_radio(self, x, y, r):
        """Índices (ordenados) de los puntos con (px − x)² + (py − y)² ≤ r²."""
        r2 = r * r
        return [i for i in self.en_caja(x, y, r)
                if (self.puntos[i][0] - x) ** 2 + (self.puntos[i][1] - y) ** 2 <= r2]
