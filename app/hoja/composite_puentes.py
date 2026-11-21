"""composite_puentes.py — anclajes y puentes de la hoja compuesta SIN comparar todos contra todos (PURO).

Monitor 2026-11-21 (Agregar utilidad, 32 mapas de drenaje sobre la hoja del editor): al marcar las hojas la
ventana quedaba «No responde» ~20 s y cada materialización pasaba ~17 s en «Buscando las líneas que cruzan cada
costura…». Causas medidas:

  · `find_bridges` probaba CADA par de anclajes de toda la hoja (1 679 anclajes = 1.4 millones de pares) y en
    cada par pedía dos veces el nombre corto de la capa (`pdf_layers.short_name`);
  · `edge_anchors` volvía a calcular los anclajes de cada pieza cada vez que se abría «Componer hoja» o se
    materializaba (la misma hoja, el mismo recorte).

Aquí, con el MISMO resultado:

  · `claves_de_capa`: el nombre corto de cada capa, una vez por nombre distinto;
  · `candidatos`: los pares que pasan la prueba de puente, buscados por CELDAS. Un par que pasa tiene su hueco
    `along` ∈ [−perp, máx] y su desvío lateral ≤ perp, así que la distancia entre los dos extremos es a lo sumo
    hypot(máx, perp) / |u| (u = dirección del primero): con celdas de ese lado basta mirar las 3 × 3 vecinas. La
    prueba de cada par es la de siempre, con las mismas cuentas; los pares se ordenan después por (costo, i, j),
    así que el orden en que se encuentran no importa. Con datos raros (no finitos, direcciones no unitarias) se
    prueban todos los pares, como antes;
  · `hay_vecino`: «¿algún anclaje ya guardado está a ≤ radio?» de `_merge_anchors`, por celdas (la respuesta es
    la misma: solo importa si existe);
  · memoria de anclajes por documento (huella sha1 de sus bytes, la de `composite_renders.marcar`), hoja, giro,
    capas encendidas y TODOS los parámetros: un documento sin huella no la usa.

`TODOS_CON_TODOS = True` vuelve al recorrido de antes (para comparar en las pruebas).
"""
from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TODOS_CON_TODOS = False
MAX_MEMORIA = 4096                     # entradas (hoja + recorte); cada una son decenas o cientos de anclajes

_U_MIN, _U_MAX = 0.5, 2.0              # direcciones fuera de esto (no vienen de `edge_anchors`): todos los pares
_COORD_MAX = 1e12
_CELDAS_MAX = 1e8                      # |x| / celda: con más, el redondeo de la división podría saltar una celda


# ─────────────────────────── claves de capa ───────────────────────────
def claves_de_capa(capas: Iterable[str]) -> List[str]:
    """`short_name(capa).casefold()` de cada una, calculado una vez por nombre distinto."""
    from hoja.pdf_layers import short_name

    memo: Dict[str, str] = {}
    out = []
    for c in capas:
        k = memo.get(c)
        if k is None:
            k = memo[c] = short_name(c).casefold()
        out.append(k)
    return out


# ─────────────────────────── pares de puente ───────────────────────────
def _todos(items, claves, max_gap: float, perp_tol: float, cos: float) -> List[Tuple[float, int, int]]:
    """El recorrido de siempre: cada par (i < j)."""
    cands: List[Tuple[float, int, int]] = []
    for i, (pi, a) in enumerate(items):
        ka = claves[i]
        for j in range(i + 1, len(items)):
            pj, b = items[j]
            if pi == pj:
                continue
            if ka != claves[j]:
                continue
            if a.ux * b.ux + a.uy * b.uy > -cos:
                continue
            vx, vy = b.x - a.x, b.y - a.y
            along = vx * a.ux + vy * a.uy
            if along < -perp_tol or along > max_gap:
                continue
            lateral = abs(vx * a.uy - vy * a.ux)
            if lateral > perp_tol:
                continue
            cands.append((along + lateral, i, j))
    return cands


def _aptos(items) -> Optional[Tuple[float, float]]:
    """(|u| mínimo, |coordenada| máxima) si todos los anclajes son «normales» (finitos, dirección casi
    unitaria); None si no."""
    umin, cmax = math.inf, 0.0
    for _pi, a in items:
        x, y, ux, uy = a.x, a.y, a.ux, a.uy
        if not (abs(x) < _COORD_MAX and abs(y) < _COORD_MAX):      # (también descarta NaN)
            return None
        n = math.hypot(ux, uy)
        if not (_U_MIN <= n <= _U_MAX):
            return None
        if n < umin:
            umin = n
        cmax = max(cmax, abs(x), abs(y))
    return umin, cmax


def candidatos(items: Sequence[tuple], claves: Sequence[str], max_gap: float, perp_tol: float,
               cos: float) -> List[Tuple[float, int, int]]:
    """Los (costo, i, j), i < j, de los pares de `items` [(pieza, Anchor)] que pasan la prueba de puente de
    `composite.find_bridges` (mismo conjunto que probar todos; quien llama los ordena)."""
    if TODOS_CON_TODOS or len(items) < 64:
        return _todos(items, claves, max_gap, perp_tol, cos)
    apto = _aptos(items)
    if apto is None or not (math.isfinite(max_gap) and math.isfinite(perp_tol)):
        return _todos(items, claves, max_gap, perp_tol, cos)
    umin, cmax = apto
    # |v|·|u_a| = hypot(along, lateral) ≤ hypot(máx(max_gap, perp), perp) para todo par que pasa
    alcance = math.hypot(max(abs(max_gap), abs(perp_tol)), abs(perp_tol)) / umin
    celda = alcance * (1.0 + 1e-6) + 1e-6
    if cmax / celda > _CELDAS_MAX:                  # celdas enormes en número: el redondeo de x / celda no alcanza
        return _todos(items, claves, max_gap, perp_tol, cos)
    rejilla: Dict[tuple, List[int]] = {}
    pos = []
    for i, (_pi, a) in enumerate(items):
        cx, cy = math.floor(a.x / celda), math.floor(a.y / celda)
        pos.append((cx, cy))
        rejilla.setdefault((claves[i], cx, cy), []).append(i)      # índices en orden creciente
    cands: List[Tuple[float, int, int]] = []
    for i, (pi, a) in enumerate(items):
        ka = claves[i]
        cx, cy = pos[i]
        aux, auy, ax, ay = a.ux, a.uy, a.x, a.y
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                lista = rejilla.get((ka, gx, gy))
                if not lista:
                    continue
                for j in lista:
                    if j <= i:
                        continue
                    pj, b = items[j]
                    if pi == pj:
                        continue
                    if aux * b.ux + auy * b.uy > -cos:
                        continue
                    vx, vy = b.x - ax, b.y - ay
                    along = vx * aux + vy * auy
                    if along < -perp_tol or along > max_gap:
                        continue
                    lateral = abs(vx * auy - vy * aux)
                    if lateral > perp_tol:
                        continue
                    cands.append((along + lateral, i, j))
    return cands


# ─────────────────────────── fusión de anclajes ───────────────────────────
class Fusion:
    """Los anclajes ya guardados por `_merge_anchors`, por (capa, celda): `hay_vecino(an)` = ¿alguno a
    ≤ radio en x e y, misma capa y dirección parecida (producto > 0.9)? — la condición de siempre."""

    def __init__(self, radio: float):
        self.radio = radio
        self.celda = radio * (1.0 + 1e-6) + 1e-9
        self.rejilla: Dict[tuple, list] = {}

    def _c(self, v: float) -> int:
        return math.floor(v / self.celda)

    def hay_vecino(self, an) -> bool:
        r = self.radio
        cx, cy = self._c(an.x), self._c(an.y)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for u in self.rejilla.get((an.layer, gx, gy), ()):
                    if (abs(an.x - u.x) <= r and abs(an.y - u.y) <= r
                            and an.ux * u.ux + an.uy * u.uy > 0.9):
                        return True
        return False

    def poner(self, an) -> None:
        self.rejilla.setdefault((an.layer, self._c(an.x), self._c(an.y)), []).append(an)


def fusion_apta(anchors, radio: float) -> bool:
    """¿Se puede buscar por celdas? (coordenadas finitas y no tan grandes frente al radio)."""
    if not (math.isfinite(radio) and radio > 0):
        return False
    tope = _CELDAS_MAX * radio
    return all(abs(a.x) < tope and abs(a.y) < tope for a in anchors)


# ─────────────────────────── memoria de anclajes ───────────────────────────
_MEMORIA: "OrderedDict[tuple, list]" = OrderedDict()
_CANDADO = threading.Lock()


def marcar(doc, data) -> None:
    """Huella del documento (sha1 de sus bytes), la misma que pone `composite_renders.marcar`."""
    if getattr(doc, "_pdfcad_huella", None):
        return
    try:
        doc._pdfcad_huella = hashlib.sha1(data).hexdigest()
    except Exception:                                       # noqa: BLE001 — sin huella, sin memoria
        pass


def clave(page, clip, max_paths, tol, insets, polygon) -> Optional[tuple]:
    """Todo lo que decide los anclajes de `edge_anchors`; None si el documento no tiene huella."""
    doc = page.parent
    h = getattr(doc, "_pdfcad_huella", None)
    if not h:
        return None
    try:
        capas = tuple(bool(c.get("on")) for c in doc.layer_ui_configs())
    except Exception:                                       # noqa: BLE001
        return None
    try:
        return (h, int(page.number), int(page.rotation), capas,
                tuple(float(v) for v in clip), int(max_paths), float(tol),
                tuple(sorted((str(k), float(v)) for k, v in (insets or {}).items())),
                tuple(tuple(float(c) for c in pt) for pt in (polygon or ())))
    except (TypeError, ValueError):
        return None


def _copia(lista, Anchor) -> list:
    return [Anchor(a.x, a.y, a.ux, a.uy, a.layer, a.color, a.width, a.dash_len, a.on_edge, a.inset)
            for a in lista]


def buscar(k, Anchor) -> Optional[list]:
    if k is None:
        return None
    with _CANDADO:
        hit = _MEMORIA.get(k)
        if hit is None:
            return None
        _MEMORIA.move_to_end(k)
    return _copia(hit, Anchor)


def guardar(k, anclajes, Anchor) -> None:
    if k is None:
        return
    copia = _copia(anclajes, Anchor)
    with _CANDADO:
        _MEMORIA[k] = copia
        _MEMORIA.move_to_end(k)
        while len(_MEMORIA) > MAX_MEMORIA:
            _MEMORIA.popitem(last=False)


def soltar() -> None:
    with _CANDADO:
        _MEMORIA.clear()
