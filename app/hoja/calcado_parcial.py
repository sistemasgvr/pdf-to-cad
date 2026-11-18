"""calcado_parcial.py — hojas de otra utilidad que NO coinciden una a una con las del editor.

Pedido del usuario 2026-11-17 («Agregar utilidad desde otro PDF»): la cuadrícula del PDF nuevo
puede no ser la del editor (una hoja nueva cae mitad y mitad sobre dos hojas del editor, o solo
cubre una parte). `hoja_calcada.calcar` resuelve primero el caso de siempre (misma cuadrícula: la
hoja nueva cubre entera una pieza del editor); lo que queda sin cubrir se arma aquí con las hojas
nuevas YA ubicadas (similaridad hoja nueva → hoja compuesta del editor):

  · cada hoja nueva aporta su ÁREA ÚTIL (el recuadro del mapa o, sin él, lo que coincide con el
    mapa base del editor) llevada a la hoja compuesta;
  · si dos hojas nuevas se solapan, el solape se parte por la mitad (cada punto de la hoja del
    editor lo dibuja UNA sola hoja nueva: si no, la red saldría dos veces);
  · ese rectángulo se recorta a cada pieza del editor SIN cubrir (nada fuera de la hoja del editor
    ni encima de lo que ya cubrió el caso de siempre) y los trozos de una misma hoja nueva que
    forman un rectángulo se juntan en una sola pieza.

Solo mapas al norte (sin giro entre las hojas; un giro < 0.5° se toma por su caja). PURO.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Rect = Tuple[float, float, float, float]

MIN_LADO_PT = 6.0          # un trozo más angosto que esto (en la hoja compuesta) no se agrega
JUNTAR_TOL_PT = 0.01       # dos trozos se juntan si sus lados coinciden a esto


@dataclass
class HojaUbicada:
    """Una hoja nueva ubicada: `m` = similaridad (a, b, tx, ty) hoja visible → hoja compuesta."""
    fuente: int
    hoja: int
    m: Tuple[float, float, float, float]
    util: Rect                       # área útil en pt de SU hoja visible
    votos: int = 0
    rms: float = 0.0
    celda: Tuple[int, ...] = ()      # piezas del editor de SU celda (mapas en cuadrícula), o ()


def _mapa(m, x, y):
    a, b, tx, ty = m
    return a * x - b * y + tx, b * x + a * y + ty


def _inversa(m, X, Y):
    a, b, tx, ty = m
    qx, qy = X - tx, Y - ty
    n = a * a + b * b
    return (a * qx + b * qy) / n, (-b * qx + a * qy) / n


def caja(m, r: Rect) -> Rect:
    """La caja de `r` (hoja de origen) llevada por `m` a la hoja compuesta."""
    pts = [_mapa(m, x, y) for x, y in ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3]))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def interseccion(a: Rect, b: Rect) -> Optional[Rect]:
    r = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return r if r[2] > r[0] and r[3] > r[1] else None


def area(r: Optional[Rect]) -> float:
    return 0.0 if r is None else (r[2] - r[0]) * (r[3] - r[1])


def partir_solapes(cajas: List[Rect]) -> List[Rect]:
    """Cada solape entre dos cajas se parte por la mitad, por el eje en que es más angosto
    (dos hojas lado a lado → corte vertical; una sobre otra → horizontal). Una caja contenida
    entera en otra no se toca aquí (la deja fuera `repartir`, por orden)."""
    out = [list(c) for c in cajas]
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            a, b = out[i], out[j]
            r = interseccion(tuple(a), tuple(b))
            if r is None:
                continue
            ancho, alto = r[2] - r[0], r[3] - r[1]
            if ancho <= alto:                               # una al lado de la otra
                if (a[0] + a[2]) <= (b[0] + b[2]):          # a a la izquierda
                    if a[2] >= b[2] or b[0] <= a[0]:
                        continue                            # contenida a lo ancho: no se parte
                    mid = (r[0] + r[2]) / 2.0
                    a[2], b[0] = mid, mid
                else:
                    if b[2] >= a[2] or a[0] <= b[0]:
                        continue
                    mid = (r[0] + r[2]) / 2.0
                    b[2], a[0] = mid, mid
            else:                                           # una sobre la otra
                if (a[1] + a[3]) <= (b[1] + b[3]):
                    if a[3] >= b[3] or b[1] <= a[1]:
                        continue
                    mid = (r[1] + r[3]) / 2.0
                    a[3], b[1] = mid, mid
                else:
                    if b[3] >= a[3] or a[1] <= b[1]:
                        continue
                    mid = (r[1] + r[3]) / 2.0
                    b[3], a[1] = mid, mid
    return [tuple(c) for c in out]


def _restar(r: Rect, quita: Rect) -> List[Rect]:
    """`r` sin `quita`, en hasta 4 rectángulos (franjas arriba/abajo y lados)."""
    q = interseccion(r, quita)
    if q is None:
        return [r]
    out = []
    if q[1] > r[1]:
        out.append((r[0], r[1], r[2], q[1]))
    if q[3] < r[3]:
        out.append((r[0], q[3], r[2], r[3]))
    if q[0] > r[0]:
        out.append((r[0], q[1], q[0], q[3]))
    if q[2] < r[2]:
        out.append((q[2], q[1], r[2], q[3]))
    return out


def _juntar(trozos: List[Rect]) -> List[Rect]:
    """Trozos de una misma hoja que juntos forman un rectángulo → uno solo (sin costura)."""
    t = list(trozos)
    cambio = True
    while cambio:
        cambio = False
        for i in range(len(t)):
            for j in range(i + 1, len(t)):
                a, b = t[i], t[j]
                tol = JUNTAR_TOL_PT
                misma_fila = abs(a[1] - b[1]) <= tol and abs(a[3] - b[3]) <= tol
                misma_col = abs(a[0] - b[0]) <= tol and abs(a[2] - b[2]) <= tol
                u = None
                if misma_fila and (abs(a[2] - b[0]) <= tol or abs(b[2] - a[0]) <= tol):
                    u = (min(a[0], b[0]), a[1], max(a[2], b[2]), a[3])
                elif misma_col and (abs(a[3] - b[1]) <= tol or abs(b[3] - a[1]) <= tol):
                    u = (a[0], min(a[1], b[1]), a[2], max(a[3], b[3]))
                if u is not None:
                    t[i] = u
                    del t[j]
                    cambio = True
                    break
            if cambio:
                break
    return t


def repartir(hojas: Sequence[HojaUbicada], libres: Sequence[Rect],
             ocupado: Sequence[Rect] = ()) -> List[Tuple[HojaUbicada, Rect, List[int]]]:
    """Qué rectángulo de la hoja compuesta dibuja cada hoja nueva. `libres` = las cajas de las
    piezas del editor SIN cubrir; `ocupado` = lo que ya cubrió el caso de siempre. → [(hoja,
    rectángulo en la hoja compuesta, índices de `libres` que toca)], sin solapes entre sí. Las
    hojas con más votos van primero (una hoja contenida entera en otra se queda sin nada)."""
    orden = sorted(range(len(hojas)), key=lambda i: -hojas[i].votos)
    cajas = partir_solapes([caja(hojas[i].m, hojas[i].util) for i in orden])
    tomado: List[Rect] = list(ocupado)
    out: List[Tuple[HojaUbicada, Rect, List[int]]] = []
    for i, c in zip(orden, cajas):
        trozos: List[Tuple[Rect, int]] = []
        for k, lib in enumerate(libres):
            r = interseccion(c, lib)
            if r is None:
                continue
            partes = [r]
            for t in tomado:
                partes = [p for q in partes for p in _restar(q, t)]
            trozos += [(p, k) for p in partes
                       if p[2] - p[0] >= MIN_LADO_PT and p[3] - p[1] >= MIN_LADO_PT]
        if not trozos:
            continue
        for r in _juntar([p for p, _k in trozos]):
            ks = sorted({k for p, k in trozos if interseccion(p, r) is not None})
            out.append((hojas[i], r, ks))
            tomado.append(r)
    return out


def repartir_celdas(hojas: Sequence[HojaUbicada], cajas_celda: Sequence[Rect], libres: Sequence[Rect],
                    ocupado: Sequence[Rect] = ()):
    """Hojas que saben su celda (mapas en cuadrícula): cada una dibuja el cuadro de SU celda (`cajas_celda`,
    la caja de las piezas del editor de esa celda), entero y en UNA pieza, salvo lo ya ocupado. → (reparto
    como `repartir`, lo ocupado después)."""
    orden = sorted(range(len(hojas)), key=lambda i: -hojas[i].votos)
    tomado: List[Rect] = list(ocupado)
    out: List[Tuple[HojaUbicada, Rect, List[int]]] = []
    for i in orden:
        hu = hojas[i]
        r = interseccion(caja(hu.m, hu.util), tuple(cajas_celda[i]))
        if r is None:
            continue
        partes = [r]
        for t in tomado:
            partes = [p for q in partes for p in _restar(q, t)]
        partes = [p for p in partes if p[2] - p[0] >= MIN_LADO_PT and p[3] - p[1] >= MIN_LADO_PT]
        for p in _juntar(partes):
            ks = [k for k, lib in enumerate(libres) if interseccion(p, tuple(lib)) is not None]
            if ks:
                out.append((hu, p, ks))
                tomado.append(p)
    return out, tomado


def clip_en_hoja(h: HojaUbicada, r: Rect, size: Tuple[float, float]) -> List[float]:
    """El rectángulo `r` (hoja compuesta) como clip normalizado de la hoja nueva."""
    pts = [_inversa(h.m, x, y) for x, y in ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3]))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, hh = size
    return [max(0.0, min(xs) / w), max(0.0, min(ys) / hh), min(1.0, max(xs) / w), min(1.0, max(ys) / hh)]


def por_hoja(reparto) -> Dict[Tuple[int, int], List[Rect]]:
    out: Dict[Tuple[int, int], List[Rect]] = {}
    for h, r, _k in reparto:
        out.setdefault((h.fuente, h.hoja), []).append(r)
    return out
