"""recognition_geom_indice.py — índices por celdas para `recognition_geom.resolve_nodes` (PURO).

Reporte del usuario 2026-11-20 (monitor): reconocer el drenaje de la compuesta de 36 mapas de Phoenix tardaba ~4–5 min,
217 s en `resolve_nodes`, que compara cada punta con TODAS las corridas o TODAS las otras puntas (132 millones de
`_dist`). Con ~13 mil corridas eso crece al cuadrado. Aquí:

  · `IndiceCorridas.candidatos(p, margen)` = las corridas cuyo recuadro, agrandado `margen` (+ su `desvio`), contiene p;
  · `IndicePuntos.vecinos(p, r)` = los puntos a ≤ r en x y en y (un cuadrado: contiene al círculo de radio r);
  · `IndicePuntos.cerca_de_segmento(a, b, r)` = los puntos del recuadro del segmento agrandado r.

Siempre un SUPERCONJUNTO de lo que el bucle original aceptaría (la prueba exacta la sigue haciendo el bucle) y en
ORDEN ASCENDENTE de índice (el mismo orden del `for` original: mismos desempates). `IndiceCorridas.poner` actualiza
una corrida cuando un bucle mueve su punta o agrega una nueva.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

_EPS = 1e-6


class IndiceCorridas:
    def __init__(self, runs, celda: float, desvio: Optional[Callable] = None):
        self.celda = max(float(celda), 1.0)
        self._desvio = desvio
        self._cajas: Dict[int, Tuple[float, float, float, float]] = {}
        self._celdas: Dict[Tuple[int, int], Set[int]] = defaultdict(set)
        self._suyas: Dict[int, List[Tuple[int, int]]] = {}
        self._siempre: Set[int] = set()          # corridas que no se pueden acotar (desvío infinito)
        for j, r in enumerate(runs):
            self.poner(j, r)

    def _rango(self, x0, y0, x1, y1):
        c = self.celda
        return (math.floor(x0 / c), math.floor(y0 / c), math.floor(x1 / c), math.floor(y1 / c))

    def poner(self, j: int, r) -> None:
        """(Re)ubica la corrida `j` con su geometría de ahora (a, mid, b)."""
        for k in self._suyas.pop(j, ()):
            self._celdas[k].discard(j)
        self._siempre.discard(j)
        self._cajas.pop(j, None)
        extra = self._desvio(r) if self._desvio is not None else 0.0
        if not math.isfinite(extra):
            self._siempre.add(j)
            return
        pts = [r.a] + list(r.mid) + [r.b]
        x0 = min(p[0] for p in pts) - extra; x1 = max(p[0] for p in pts) + extra
        y0 = min(p[1] for p in pts) - extra; y1 = max(p[1] for p in pts) + extra
        self._cajas[j] = (x0, y0, x1, y1)
        cx0, cy0, cx1, cy1 = self._rango(x0, y0, x1, y1)
        mias = []
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                self._celdas[(cx, cy)].add(j)
                mias.append((cx, cy))
        self._suyas[j] = mias

    def candidatos(self, p, margen: float) -> List[int]:
        m = margen + _EPS
        cx0, cy0, cx1, cy1 = self._rango(p[0] - m, p[1] - m, p[0] + m, p[1] + m)
        vistos: Set[int] = set(self._siempre)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                c = self._celdas.get((cx, cy))
                if c:
                    vistos |= c
        out = []
        for j in vistos:
            caja = self._cajas.get(j)
            if caja is None:                        # (las de `_siempre`)
                out.append(j)
                continue
            x0, y0, x1, y1 = caja
            if x0 - m <= p[0] <= x1 + m and y0 - m <= p[1] <= y1 + m:
                out.append(j)
        out.sort()
        return out


class IndicePuntos:
    def __init__(self, puntos: Sequence, celda: float):
        self.celda = max(float(celda), 1.0)
        self.pts = list(puntos)
        self._celdas: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        c = self.celda
        for i, p in enumerate(self.pts):
            self._celdas[(math.floor(p[0] / c), math.floor(p[1] / c))].append(i)

    def _en_caja(self, x0, y0, x1, y1) -> List[int]:
        c = self.celda
        out = []
        for cx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for cy in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for i in self._celdas.get((cx, cy), ()):
                    p = self.pts[i]
                    if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                        out.append(i)
        out.sort()
        return out

    def vecinos(self, p, r: float) -> List[int]:
        m = r + _EPS
        return self._en_caja(p[0] - m, p[1] - m, p[0] + m, p[1] + m)

    def cerca_de_segmento(self, a, b, r: float) -> List[int]:
        m = r + _EPS
        return self._en_caja(min(a[0], b[0]) - m, min(a[1], b[1]) - m, max(a[0], b[0]) + m, max(a[1], b[1]) + m)
