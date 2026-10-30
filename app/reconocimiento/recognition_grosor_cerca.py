"""Los rótulos con diámetro que hay JUNTO a una línea cuyo diámetro el plano no dijo con certeza (PURO).

Pedido del usuario 2026-10-29 (spec `docs/superpowers/specs/2026-10-29-ia-diametro-plano-design.md`): la IA
sugiere el diámetro de esas líneas eligiendo entre lo que la app YA leyó. `recognition_grosor.aplicar` guarda esto
en `grosor["cerca"]` de cada línea «dudoso» o «sin_dato»; no cambia ningún estado ni diámetro. Cada rótulo lleva
un id (R1, R2… por distancia), lo que dice, de qué utilidad es y a dónde va su guía:
  «esta» = la punta cae sobre ESTA línea; «ambigua» = cae sobre ésta y sobre otra casi igual de cerca;
  «otra» = cae sobre otra línea de la utilidad (`otra.capa`) o sobre tinta de otra utilidad (`otra.utilidad`);
  «nada» = la punta no cae sobre ninguna línea; «sin» = el rótulo no tiene guía.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from reconocimiento.recognition_grosor_texto import Rotulo, es_de

CERCA_PT = 120.0      # rótulos hasta esta distancia de la línea (pt)
MAX_CERCA = 8         # como mucho, los más cercanos
_ORDEN_GUIA = {"esta": 0, "ambigua": 1, "otra": 2, "nada": 3, "sin": 4}

Pt = Tuple[float, float]


def _dist_pl(p: Pt, pts: Sequence[Pt]) -> float:
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
        best = min(best, math.hypot(a[0] + t * vx - p[0], a[1] + t * vy - p[1]))
    return best


def _centro(r: Rotulo) -> Pt:
    return ((r.bbox[0] + r.bbox[2]) / 2.0, (r.bbox[1] + r.bbox[3]) / 2.0)


def _caja(pts: Sequence[Pt], m: float):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m


def _cerca_de_caja(q: Pt, caja, lim: float) -> bool:
    """¿La caja (x0, y0, x1, y1) queda a ≤ lim del punto q?"""
    x0, y0, x1, y1 = caja
    return x0 - lim <= q[0] <= x1 + lim and y0 - lim <= q[1] <= y1 + lim


def con_cajas(otras):
    """[(pts, capa, caja)] de [(pts, capa)]: las cajas una vez para todas las líneas de la hoja."""
    return [(o[0], o[1], o[2] if len(o) > 2 else _caja(o[0], 0.0)) for o in otras]


def _texto(r: Rotulo, rotulos: Sequence[Rotulo]) -> str:
    """Las líneas de su bloque (MText), de arriba a abajo."""
    if r.bloque < 0:
        return r.texto
    lineas = sorted({(x.bbox[1], x.texto) for x in rotulos if x.bloque == r.bloque})
    return " / ".join(t for _y, t in lineas) or r.texto


def _guia(r, pts, hoja, utilidad, zoom, px_por_in, otras):
    """(guia, otra) de un rótulo: a dónde llega la punta de su guía (la mejor si tiene varias)."""
    justo = 4.0 * zoom                                   # = recognition_grosor.PUNTA_HOLGURA_PT
    tol = justo + 0.5 * r.pulg * px_por_in
    mejor: Tuple[str, Optional[dict]] = ("sin", None)
    for k, (rr, _cad, punta) in enumerate(hoja.puntas):
        if rr is not r:
            continue
        d_esta = _dist_pl(punta, pts)
        # solo las líneas cuya caja queda a tiro de la punta (mismo resultado: las demás están más lejos que
        # `d_esta + justo` y que `tol`; en una hoja compuesta son cientos)
        lim = max(tol, d_esta + justo)
        dists = sorted((_dist_pl(punta, o), capa) for o, capa, caja in otras
                       if _cerca_de_caja(punta, caja, lim)) if otras else []
        tinta = hoja.tinta[k] if k < len(hoja.tinta) else None
        if d_esta <= tol:
            g = ("ambigua", None) if dists and dists[0][0] <= d_esta + justo else ("esta", None)
        elif tinta not in (None, utilidad):
            g = ("otra", {"utilidad": tinta, "capa": None, "dist_pt": None})
        elif dists and dists[0][0] <= tol:
            g = ("otra", {"utilidad": utilidad, "capa": dists[0][1], "dist_pt": round(dists[0][0] / zoom, 2)})
        else:
            g = ("nada", None)
        if _ORDEN_GUIA[g[0]] < _ORDEN_GUIA[mejor[0]]:
            mejor = g
    return mejor


def cerca(pts: Sequence[Pt], hoja, utilidad: str, zoom: float, px_por_in: float,
          otras: Sequence[Tuple[Sequence[Pt], str]] = ()) -> List[dict]:
    """Los rótulos con diámetro a ≤ `CERCA_PT` de la línea `pts` (px de la vista), los `MAX_CERCA` más cercanos.
    `hoja` = `recognition_grosor.Hoja`; `otras` = [(pts, capa)] o [(pts, capa, caja)] (`con_cajas`) de las demás líneas de la utilidad."""
    if len(pts) < 2 or not hoja.rotulos:
        return []
    otras = con_cajas(otras)
    lim = CERCA_PT * zoom
    x0, y0, x1, y1 = _caja(pts, lim)
    puntas_de = {}
    for rr, _c, p in hoja.puntas:
        puntas_de.setdefault(id(rr), []).append(p)
    cand = []
    for r in hoja.rotulos:
        lugares = [_centro(r)] + puntas_de.get(id(r), [])
        if not any(x0 <= q[0] <= x1 and y0 <= q[1] <= y1 for q in lugares):
            continue
        d = min(_dist_pl(q, pts) for q in lugares)
        if d <= lim:
            cand.append((d, r))
    cand.sort(key=lambda c: c[0])
    out = []
    for k, (d, r) in enumerate(cand[:MAX_CERCA]):
        guia, otra = _guia(r, pts, hoja, utilidad, zoom, px_por_in, otras)
        out.append({
            "id": f"R{k + 1}", "texto": _texto(r, hoja.rotulos), "diam_in": float(r.pulg),
            "material": r.material or "", "util": r.utilidad or "",
            "es_de": bool(es_de(r, utilidad)) and not (guia == "otra" and (otra or {}).get("utilidad") not in
                                                       (None, utilidad)),
            "dist_pt": round(d / zoom, 2), "guia": guia, "otra": otra, "caja": [float(v) for v in r.bbox],
            "estacion": bool(r.estacion), "union": bool(r.union), "varios": int(r.varios),
            "puntas": [[float(q[0]), float(q[1])] for q in puntas_de.get(id(r), [])],
            # a cuánto de ESTA línea termina su guía (pt): «nada» a 5 pt no es lo mismo que a 80
            "punta_pt": (round(min(_dist_pl(q, pts) for q in puntas_de[id(r)]) / zoom, 2)
                         if puntas_de.get(id(r)) else None),
        })
    return out
