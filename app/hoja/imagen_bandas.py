"""Varias bandas «en caja» PEGADAS de una red en imagen → una línea por banda (PURO: numpy + cv2, sin Qt).

Pedido del usuario (2026-11-19, Phoenix «QS SD_Indian School», «60" RCP» junto a «30" RGRCP»): dos o tres tuberías
anchas dibujadas a cuadros (bloque macizo, hueco blanco, bloque…) una pegada a la otra. Sus contornos de 1 px y las
esquinas de los bloques de una banda con los de la vecina las unen en grupitos de 2–3 bloques; el esqueleto de cada
grupito salía en trocitos torcidos. Una banda SOLA no pasa por aquí (la rellena `imagen_huecos.rellenar`).

`bandas(mask, escala)` → (líneas, franja tomada de la máscara o None):

  1. La máscara se ABRE (`ABRIR_PX`: quita lo de 1–2 px de grueso, contornos y esquinas que se tocan) y sus piezas
     COMPACTAS (lado largo ≤ `COMPACTO_K` × corto, corto ≥ `BLOQUE_MIN_PT`, caja ≤ `BLOQUE_MAX_PT`) son los bloques.
  2. Los bloques se juntan en grupos por cercanía (≤ `VECINO_K` × su lado mayor). En cada grupo, cada bloque se
     encadena con el siguiente de su MISMA banda: en la dirección de su lado largo, sin apartarse de costado, a un paso
     de bloque y del mismo tamaño (`_filas_del_grupo`); la banda vecina queda a un ancho de costado.
  3. Solo las bandas que van JUNTO a otra paralela del mismo tamaño y tocándola (sus bloques son de la misma
     componente de la máscara original; `_de_costado`) se toman: cada una es UNA línea por los centros de sus bloques,
     de la punta del primero a la del último, y su franja (`QUITAR_K` × ancho) sale de la máscara. Una banda sola, dos
     sueltas en paralelo o un ramal en «T» no se toman: siguen como antes.

Determinista: todo en el orden de los bloques.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

ABRIR_PX = 3          # apertura que quita contornos de 1–2 px
COMPACTO_K = 3.0      # bloque: lado largo ≤ esto × corto …
BLOQUE_MAX_PT = 15.0  # … y su caja ≤ esto (los de Phoenix SD: ~5 × 3 pt)
BLOQUE_MIN_PT = 1.5   # … y lado corto ≥ esto (pt): las bandas de Phoenix SD miden ~3.1; una raya cortada de rejilla, <1
VECINO_K = 2.5        # bloques del mismo grupo: centros a ≤ esto × su lado mayor
FILA_MIN = 3          # bloques mínimos de una banda
LATERAL_K = 0.4       # bloque siguiente de la misma banda: de costado ≤ esto × su lado corto …
GIRO_DEG = 15.0       # … en la dirección de su lado largo (± esto) …
PASO_K = 2.6          # … a ≤ esto × su largo (el hueco blanco entre bloques mide un bloque) …
TAM_TOL = 0.3         # … y del mismo tamaño (± esto)
COSTADO_K = 2.5       # dos bandas pegadas: centros a ≤ esto × ancho de bloque de costado
QUITAR_K = 1.3        # franja de la máscara que se lleva cada banda tomada (× su ancho)
RUIDO_PX = 12


def _bloques(mask: np.ndarray, minimo: float, maximo: float):
    """Bloques de la máscara abierta (`ABRIR_PX`): [(cx, cy, largo, corto, ang)] de las piezas COMPACTAS (lado largo ≤
    `COMPACTO_K` × corto, corto ≥ `minimo` px, caja ≤ `maximo` px). Las demás (líneas macizas, buzones) no son bloques."""
    op = cv2.morphologyEx(mask.view(np.uint8), cv2.MORPH_OPEN, np.ones((ABRIR_PX, ABRIR_PX), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(op, connectivity=8)
    out = []
    for i in range(1, n):
        bx, by, bw, bh, ba = (int(v) for v in st[i])
        if ba < RUIDO_PX or max(bw, bh) > maximo or min(bw, bh) < minimo:
            continue
        ys, xs = np.nonzero(lab[by:by + bh, bx:bx + bw] == i)
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(np.column_stack([xs + bx, ys + by]).astype(np.float32))
        rw, rh = rw + 1.0, rh + 1.0
        if max(rw, rh) <= COMPACTO_K * min(rw, rh) and min(rw, rh) >= minimo:
            out.append((float(cx), float(cy), rw, rh, ang))
    return out


def _grupos(c: np.ndarray, r: np.ndarray) -> list[list[int]]:
    n = len(c)
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    celda = float(max(r.max(), 1.0) * VECINO_K)
    celdas: dict = {}
    for i, (x, y) in enumerate(c):
        celdas.setdefault((int(x // celda), int(y // celda)), []).append(i)
    for i, (x, y) in enumerate(c):
        cx, cy = int(x // celda), int(y // celda)
        for j in (j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in celdas.get((cx + dx, cy + dy), ())):
            if j > i and math.dist(c[i], c[j]) <= VECINO_K * max(r[i], r[j]):
                padre[raiz(j)] = raiz(i)
    g: dict = {}
    for i in range(n):
        g.setdefault(raiz(i), []).append(i)
    return [sorted(v) for v in g.values()]


def _ancho_en(b, n) -> float:
    """Extensión del bloque (rectángulo girado) a lo largo de la dirección unitaria `n`."""
    a = math.radians(b[4])
    ex = np.array([math.cos(a), math.sin(a)]) * b[2]
    ey = np.array([-math.sin(a), math.cos(a)]) * b[3]
    return abs(float(ex @ n)) + abs(float(ey @ n))


def _filas_del_grupo(bl, idx):
    """Bandas del grupo: cada bloque se encadena con los de su MISMA banda, que siguen en la dirección de su lado largo
    (± `GIRO_DEG`), sin apartarse de costado más de `LATERAL_K` × su lado corto, a ≤ `PASO_K` × su largo y del mismo
    tamaño (± `TAM_TOL`). Las bandas vecinas quedan a un ancho de costado: no se encadenan."""
    padre = {i: i for i in idx}

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    cos = math.cos(math.radians(GIRO_DEG))
    celda = PASO_K * max(max(bl[i][2], bl[i][3]) for i in idx)
    celdas: dict = {}
    for i in idx:
        celdas.setdefault((int(bl[i][0] // celda), int(bl[i][1] // celda)), []).append(i)
    for i in idx:
        cx, cy, rw, rh, ang = bl[i]
        largo, corto = (rw, rh) if rw >= rh else (rh, rw)
        a = math.radians(ang if rw >= rh else ang + 90.0)
        d = np.array([math.cos(a), math.sin(a)])
        gx, gy = int(cx // celda), int(cy // celda)
        for j in sorted(j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in celdas.get((gx + dx, gy + dy), ())):
            if j <= i:
                continue
            v = np.array(bl[j][:2]) - np.array((cx, cy))
            L = float(np.hypot(*v))
            lj, cj = max(bl[j][2], bl[j][3]), min(bl[j][2], bl[j][3])
            if (0 < L <= PASO_K * largo and abs(float(v @ d)) >= cos * L
                    and abs(v[0] * d[1] - v[1] * d[0]) <= LATERAL_K * corto
                    and abs(lj - largo) <= TAM_TOL * largo and abs(cj - corto) <= TAM_TOL * corto):
                padre[raiz(j)] = raiz(i)
    filas: dict = {}
    for i in idx:
        filas.setdefault(raiz(i), []).append(i)
    out = []
    for f in filas.values():
        if len(f) < FILA_MIN:
            continue
        c = np.array([bl[i][:2] for i in f])
        u = np.linalg.svd(c - c.mean(axis=0))[2][0]
        out.append((sorted(f, key=lambda i: float(np.dot(bl[i][:2], u))), u))
    return out


def _de_costado(bl, fa, fb) -> bool:
    """Dos bandas una JUNTO a la otra: paralelas (± `GIRO_DEG`), con bloques del mismo tamaño (± `TAM_TOL`; una banda
    junto a los restos de una rejilla, no), a entre ½ y `COSTADO_K` anchos de bloque de costado y solapadas a lo largo
    (dos tramos de la misma banda, uno tras otro, no)."""
    (ia, u), (ib, v) = fa, fb
    if abs(float(u @ v)) < math.cos(math.radians(GIRO_DEG)):
        return False
    n = np.array([-u[1], u[0]])
    wa = float(np.median([_ancho_en(bl[i], n) for i in ia]))
    wb = float(np.median([_ancho_en(bl[i], n) for i in ib]))
    la = float(np.median([_ancho_en(bl[i], u) for i in ia]))
    lb = float(np.median([_ancho_en(bl[i], u) for i in ib]))
    if abs(wa - wb) > TAM_TOL * max(wa, wb) or abs(la - lb) > TAM_TOL * max(la, lb):
        return False                                  # bandas del mismo dibujo: bloques del mismo tamaño
    w = 0.5 * (wa + wb)
    ca = np.array([bl[i][:2] for i in ia])
    cb = np.array([bl[i][:2] for i in ib])
    lado = abs(float((cb.mean(axis=0) - ca.mean(axis=0)) @ n))
    a0, a1 = float((ca @ u).min()), float((ca @ u).max())
    b0, b1 = float((cb @ u).min()), float((cb @ u).max())
    return 0.5 * w <= lado <= COSTADO_K * w and min(a1, b1) > max(a0, b0)


def bandas(mask: np.ndarray, escala: float):
    """(líneas [(puntos, grosor_px)], máscara de lo que tomaron o None) de las bandas pegadas de la máscara de un
    color (`escala` = px/pt). Una banda que no está pegada a otra no se toma (sigue como antes)."""
    mask = np.ascontiguousarray(mask, dtype=bool)
    bl = _bloques(mask, BLOQUE_MIN_PT * escala, BLOQUE_MAX_PT * escala)
    if len(bl) < 2 * FILA_MIN:
        return [], None
    _n, lab0 = cv2.connectedComponents(mask.view(np.uint8), connectivity=8)
    de = [int(lab0[min(max(int(round(b[1])), 0), mask.shape[0] - 1), min(max(int(round(b[0])), 0), mask.shape[1] - 1)])
          for b in bl]
    del lab0
    c = np.array([b[:2] for b in bl])
    r = np.array([max(b[2], b[3]) for b in bl])
    lineas, quitar = [], None
    for idx in _grupos(c, r):
        if len(idx) < 2 * FILA_MIN:
            continue
        filas = _filas_del_grupo(bl, idx)
        fila_de = {i: k for k, (f, _u) in enumerate(filas) for i in f}
        por_comp: dict = {}
        for i in fila_de:
            if de[i]:
                por_comp.setdefault(de[i], set()).add(fila_de[i])
        usar = sorted({k for v in por_comp.values() for a in v for b in v if a < b
                       and _de_costado(bl, filas[a], filas[b]) for k in (a, b)})
        for k in usar:               # una banda sola, bandas que no se tocan o un ramal en «T» no llegan aquí
            f, u = filas[k]
            pts = [tuple(map(float, bl[i][:2])) for i in f]
            la, lb = _ancho_en(bl[f[0]], u) / 2, _ancho_en(bl[f[-1]], u) / 2
            pts[0] = (pts[0][0] - u[0] * la, pts[0][1] - u[1] * la)
            pts[-1] = (pts[-1][0] + u[0] * lb, pts[-1][1] + u[1] * lb)
            g = float(np.median([_ancho_en(bl[i], np.array([-u[1], u[0]])) for i in f]))
            lineas.append((pts, g))
            if quitar is None:
                quitar = np.zeros(mask.shape, np.uint8)
            cv2.polylines(quitar, [np.round(np.array(pts)).astype(np.int32)], False, 1,
                          thickness=int(math.ceil(g * QUITAR_K)) + 2)
    if quitar is None:
        return lineas, None
    return lineas, (quitar > 0) & mask
