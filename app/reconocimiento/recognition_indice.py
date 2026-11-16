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
        cortos, largos = [], []
        for i, sg in enumerate(tramos):
            for j, (a, b) in enumerate(sg):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L <= c:
                    # tramo corto: las celdas de su caja ± alcance (cubren el corredor)
                    cortos.append((i, j, a[0], a[1], b[0], b[1]))
                else:
                    # tramo largo: puntos cada ≤ media celda, cada uno con las celdas a ≤ r
                    largos.append((i, j, a[0], a[1], b[0], b[1], max(1, int(math.ceil(L / paso)))))
        if cortos or largos:
            self._repartir(cortos, largos, r)

    def _repartir(self, cortos, largos, r) -> None:
        """Las celdas de cada tramo, todas juntas con numpy y con las MISMAS cuentas que de a uno (mín./máx.,
        ± alcance o ± r, punto k/n del tramo, ÷ celda, piso: numpy las hace en coma flotante igual que Python;
        un tramo largo cuenta una vez por celda aunque varios de sus puntos caigan en ella). En la compuesta de
        Southwest (36 mil tramos, el índice se arma ~30 veces) de a uno costaba ~10 s. El orden dentro de cada
        celda no importa: `cerca` ordena."""
        import numpy as np
        al, c = self.alcance, self.celda
        partes = []
        if cortos:
            t = np.array(cortos, dtype=np.float64)
            partes.append(_cajas(np.floor((np.minimum(t[:, 2], t[:, 4]) - al) / c),
                                 np.floor((np.maximum(t[:, 2], t[:, 4]) + al) / c),
                                 np.floor((np.minimum(t[:, 3], t[:, 5]) - al) / c),
                                 np.floor((np.maximum(t[:, 3], t[:, 5]) + al) / c), t[:, 0], t[:, 1]))
        if largos:
            t = np.array(largos, dtype=np.float64)
            n = t[:, 6].astype(np.int64)
            fila = np.repeat(np.arange(len(t)), n + 1)
            k = (np.arange(int((n + 1).sum())) - np.repeat(np.cumsum(n + 1) - (n + 1), n + 1)).astype(np.float64)
            nf = t[fila, 6]
            x = t[fila, 2] + (t[fila, 4] - t[fila, 2]) * k / nf
            y = t[fila, 3] + (t[fila, 5] - t[fila, 3]) * k / nf
            partes.append(_cajas(np.floor((x - r) / c), np.floor((x + r) / c), np.floor((y - r) / c),
                                 np.floor((y + r) / c), t[fila, 0], t[fila, 1]))
        cx, cy, ii, jj = (np.concatenate([q[m] for q in partes]) for m in range(4))
        orden = np.lexsort((jj, ii, cy, cx))
        cx, cy, ii, jj = cx[orden], cy[orden], ii[orden], jj[orden]
        otra = np.ones(len(cx), dtype=bool)                  # sin repetir (tramo, celda)
        otra[1:] = (cx[1:] != cx[:-1]) | (cy[1:] != cy[:-1]) | (ii[1:] != ii[:-1]) | (jj[1:] != jj[:-1])
        cx, cy, ii, jj = cx[otra], cy[otra], ii[otra], jj[otra]
        cortes = np.flatnonzero((cx[1:] != cx[:-1]) | (cy[1:] != cy[:-1])) + 1
        ini = np.concatenate(([0], cortes))
        fin = cortes.tolist() + [len(cx)]
        pares = list(zip(ii.tolist(), jj.tolist()))
        self._celdas = dict(zip(zip(cx[ini].tolist(), cy[ini].tolist()),
                                [pares[a:b] for a, b in zip(ini.tolist(), fin)]))

    def cerca(self, p: Pt) -> List[Tuple[int, int]]:
        """(polilínea, tramo) que pueden estar a ≤ `alcance` de p, en orden."""
        got = self._celdas.get((int(math.floor(p[0] / self.celda)), int(math.floor(p[1] / self.celda))))
        return sorted(got) if got else []


def _cajas(x0, x1, y0, y1, ii, jj):
    """(celda x, celda y, polilínea, tramo) de cada celda de cada caja [x0..x1] × [y0..y1] (pisos ya calculados)."""
    import numpy as np
    x0, x1, y0, y1 = (v.astype(np.int64) for v in (x0, x1, y0, y1))
    ny = y1 - y0 + 1
    cuantas = (x1 - x0 + 1) * ny
    fila = np.repeat(np.arange(len(x0)), cuantas)
    k = np.arange(int(cuantas.sum())) - np.repeat(np.cumsum(cuantas) - cuantas, cuantas)
    return (x0[fila] + k // ny[fila], y0[fila] + k % ny[fila], ii.astype(np.int64)[fila], jj.astype(np.int64)[fila])


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
