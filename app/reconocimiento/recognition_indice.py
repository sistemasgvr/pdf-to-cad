"""recognition_indice.py — índice espacial de tramos (PURO): «¿qué tramos pasan cerca de este punto?».

Pedido del usuario (2026-10-14): reconocer una hoja compuesta de 36 mapas tardaba 11 min
(una hoja sola, ~5 s): varios pasos medían cada punto contra TODOS los tramos de la hoja, y
eso crece al cuadrado con su tamaño. `IndiceTramos` reparte los tramos en celdas (por su
CORREDOR, no por su caja: un tramo largo en diagonal no llena cientos de celdas) y
`cerca(p)` da solo los que pueden estar a ≤ `alcance` de p, EN EL ORDEN ORIGINAL
(polilínea, tramo): quien recorra esa lista con la misma regla de desempate («el primero
más cercano») obtiene exactamente lo mismo que recorriendo todos.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

Pt = Tuple[float, float]


class IndiceTramos:
    def __init__(self, tramos: Sequence[Sequence[Tuple[Pt, Pt]]], alcance: float, celda: float = 0.0):
        """`tramos[i]` = los tramos (a, b) de la polilínea i; `alcance` = distancia máxima que
        se va a preguntar."""
        self.alcance = float(alcance)
        self.celda = float(celda) if celda > 0 else max(4.0 * self.alcance, 8.0)
        c = self.celda
        paso = c / 2.0
        r = self.alcance + paso / 2.0 + 1e-9
        self._celdas: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        al = self.alcance
        celdas = self._celdas
        for i, sg in enumerate(tramos):
            for j, (a, b) in enumerate(sg):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L <= c:
                    # tramo corto (casi todos): las celdas de su caja ± alcance (cubren el corredor)
                    for cx in range(int(math.floor((min(a[0], b[0]) - al) / c)), int(math.floor((max(a[0], b[0]) + al) / c)) + 1):
                        for cy in range(int(math.floor((min(a[1], b[1]) - al) / c)), int(math.floor((max(a[1], b[1]) + al) / c)) + 1):
                            celdas.setdefault((cx, cy), []).append((i, j))
                    continue
                n = max(1, int(math.ceil(L / paso)))
                vistas = set()
                for k in range(n + 1):
                    x = a[0] + (b[0] - a[0]) * k / n
                    y = a[1] + (b[1] - a[1]) * k / n
                    for cx in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
                        for cy in range(int(math.floor((y - r) / c)), int(math.floor((y + r) / c)) + 1):
                            if (cx, cy) not in vistas:
                                vistas.add((cx, cy))
                                self._celdas.setdefault((cx, cy), []).append((i, j))

    def cerca(self, p: Pt) -> List[Tuple[int, int]]:
        """(polilínea, tramo) que pueden estar a ≤ `alcance` de p, en orden."""
        got = self._celdas.get((int(math.floor(p[0] / self.celda)), int(math.floor(p[1] / self.celda))))
        return sorted(got) if got else []


class IndicePuntos:
    """Puntos por celdas: `cerca(p)` da los índices de los que pueden estar a ≤ `alcance`
    de p (superconjunto exacto; en orden creciente)."""

    def __init__(self, pts: Sequence[Pt], alcance: float):
        self.celda = max(float(alcance), 1e-6)
        self._celdas: Dict[Tuple[int, int], List[int]] = {}
        for i, q in enumerate(pts):
            self._celdas.setdefault((int(math.floor(q[0] / self.celda)), int(math.floor(q[1] / self.celda))),
                                    []).append(i)

    def cerca(self, p: Pt) -> List[int]:
        cx, cy = int(math.floor(p[0] / self.celda)), int(math.floor(p[1] / self.celda))
        out: List[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out.extend(self._celdas.get((cx + dx, cy + dy), ()))
        return sorted(out)

    def en_caja(self, x0: float, y0: float, x1: float, y1: float) -> List[int]:
        """Índices de los puntos que pueden caer en la caja (superconjunto; en orden)."""
        c = self.celda
        out: List[int] = []
        for cx in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
            for cy in range(int(math.floor(y0 / c)), int(math.floor(y1 / c)) + 1):
                out.extend(self._celdas.get((cx, cy), ()))
        return sorted(out)


class IndiceCajas:
    """Cajas (x0, y0, x1, y1) por celdas: `cerca(p)` = las que, agrandadas `margen`, pueden
    contener p; `tocan(caja)` = las que pueden tocar otra caja (superconjuntos; en orden)."""

    def __init__(self, cajas: Sequence, margen: float = 0.0, celda: float = 0.0):
        validas = [b for b in cajas if b is not None]
        lado = max([max(b[2] - b[0], b[3] - b[1]) for b in validas] + [1.0])
        self.celda = float(celda) if celda > 0 else max(lado + 2.0 * margen, 1e-6)
        self.margen = float(margen)
        self._celdas: Dict[Tuple[int, int], List[int]] = {}
        c, m = self.celda, self.margen
        for i, b in enumerate(cajas):
            if b is None:
                continue
            for cx in range(int(math.floor((b[0] - m) / c)), int(math.floor((b[2] + m) / c)) + 1):
                for cy in range(int(math.floor((b[1] - m) / c)), int(math.floor((b[3] + m) / c)) + 1):
                    self._celdas.setdefault((cx, cy), []).append(i)

    def cerca(self, p: Pt) -> List[int]:
        got = self._celdas.get((int(math.floor(p[0] / self.celda)), int(math.floor(p[1] / self.celda))))
        return sorted(got) if got else []

    def tocan(self, b) -> List[int]:
        c = self.celda
        out = set()
        for cx in range(int(math.floor(b[0] / c)), int(math.floor(b[2] / c)) + 1):
            for cy in range(int(math.floor(b[1] / c)), int(math.floor(b[3] / c)) + 1):
                out.update(self._celdas.get((cx, cy), ()))
        return sorted(out)


def lineas_cerca(indice: "IndiceTramos", p: Pt) -> List[int]:
    """Polilíneas (no tramos) con algún tramo a ≤ alcance de p, en orden."""
    return sorted({i for i, _j in indice.cerca(p)})
