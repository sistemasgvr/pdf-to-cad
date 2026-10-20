"""Piezas con ESQUINAS LIBRES (cuadrilátero, `Piece.polygon`) en la hoja compuesta.

Pedido del usuario 2026-10-19: el área de cualquier hoja (con capas, aplanada o escaneo)
se recorta esquina por esquina. El PDF ya recortaba por el cuadrilátero
(`composite.build_document`) y el reconocimiento lo ve como un clip más
(`recognition.gather_paths`); aquí, los ANCLAJES del imán y de los puentes: cada trazo
que cruza el borde INCLINADO del cuadrilátero, o muere sobre él. Mismas reglas que
`composite.edge_anchors` para el rectángulo (que no cambia), con la distancia con signo
a cada lado en vez de las coordenadas de la caja."""
from __future__ import annotations

import math
from typing import List, Sequence

import fitz

from hoja import composite as C


def drawing_quad(page: fitz.Page, polygon: Sequence[C.Pt]) -> List[C.Pt]:
    """Cuadrilátero normalizado sobre la hoja VISIBLE → coords de `get_drawings`
    (hoja sin rotar), como `sheet_crops.drawing_polygon` con un rectángulo."""
    W, H = page.rect.width, page.rect.height
    out = []
    for x, y in polygon:
        p = fitz.Point(page.rect.x0 + x * W, page.rect.y0 + y * H) * page.derotation_matrix
        out.append((p.x, p.y))
    return out


def edge_anchors_poly(page: fitz.Page, polygon: Sequence[C.Pt], max_paths: int = 200000,
                      tol: float = C.EDGE_TOL_PT) -> List[C.Anchor]:
    poly = drawing_quad(page, polygon)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    if max(xs) - min(xs) < C.MIN_PIECE_PT or max(ys) - min(ys) < C.MIN_PIECE_PT:
        return []
    edges = C._convex_edges(poly)
    inner = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
    near = max(tol, C.NEAR_EDGE_PT)
    rot = page.rotation_matrix

    def dists(x: float, y: float) -> List[float]:
        """Distancia con signo a cada lado (> 0 = fuera)."""
        return [(x - a[0]) * nx + (y - a[1]) * ny for a, (nx, ny) in edges]

    def inside(x: float, y: float) -> bool:
        return max(dists(x, y)) <= tol

    def on_border(x: float, y: float) -> bool:
        d = dists(x, y)
        return max(d) <= tol and any(abs(v) <= tol for v in d)

    def toward_border(x: float, y: float, ux: float, uy: float) -> bool:
        """(x, y) a ≤ NEAR_EDGE_PT de un lado y (ux, uy) apuntando hacia afuera de ese lado."""
        d = dists(x, y)
        if max(d) > tol:
            return False
        n = math.hypot(ux, uy)
        if n < 1e-9:
            return False
        ux, uy = ux / n, uy / n
        return any(abs(v) <= C.NEAR_EDGE_PT and ux * nx + uy * ny >= C.NEAR_EDGE_COS
                   for v, (_a, (nx, ny)) in zip(d, edges))

    def deep_inside(r: fitz.Rect) -> bool:
        """El trazo entero queda a > `near` de todos los lados: no aporta anclajes."""
        return all(max(dists(x, y)) <= -near for x, y in ((r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)))

    def clip_exit(px: float, py: float, qx: float, qy: float):
        """p dentro, q fuera → punto donde el segmento sale del cuadrilátero."""
        dx, dy = qx - px, qy - py
        t_exit = 1.0
        for a, (nx, ny) in edges:
            dn = dx * nx + dy * ny
            if dn > 0 and (qx - a[0]) * nx + (qy - a[1]) * ny > 0:
                t_exit = min(t_exit, ((a[0] - px) * nx + (a[1] - py) * ny) / dn)
        if not 0.0 <= t_exit <= 1.0:
            return None
        return px + dx * t_exit, py + dy * t_exit

    out: List[C.Anchor] = []

    def emit(x: float, y: float, fx: float, fy: float, path: dict, dash_len: float = 0.0):
        ux, uy = x - fx, y - fy
        n = math.hypot(ux, uy)
        if n < 1e-6:
            return
        a = fitz.Point(x, y) * rot
        d = fitz.Point(ux / n, uy / n) * fitz.Matrix(rot.a, rot.b, rot.c, rot.d, 0, 0)
        out.append(C.Anchor(a.x - page.rect.x0, a.y - page.rect.y0, d.x, d.y,
                            path.get("layer") or "", C._rgb(path), float(path.get("width") or 0.0),
                            dash_len, on_border(x, y), False))

    for i, path in enumerate(C.page_drawings(page)):
        if i >= max_paths:
            break
        r = path.get("rect")
        if r is None or path.get("type") == "f":
            continue                        # relleno puro (logos, hatch sólido): no es una línea
        if r.x1 < inner.x0 - tol or r.x0 > inner.x1 + tol or r.y1 < inner.y0 - tol or r.y0 > inner.y1 + tol:
            continue                        # totalmente fuera
        if deep_inside(r):
            continue
        items = path.get("items") or ()
        if len(items) > C.MAX_ANCHOR_ITEMS:
            continue                        # letra explotada / símbolo
        for it in items:
            if it[0] == "l":
                p, q = it[1], it[2]
            elif it[0] == "c" and len(items) <= 3:
                p, q = it[1], it[4]
            else:
                continue
            if math.hypot(q.x - p.x, q.y - p.y) < C.MIN_ANCHOR_SEG_PT:
                continue
            pin, qin = inside(p.x, p.y), inside(q.x, q.y)
            seg_len = math.hypot(q.x - p.x, q.y - p.y) if len(items) == 1 else 0.0
            if pin and qin:
                q_out = on_border(q.x, q.y) or toward_border(q.x, q.y, q.x - p.x, q.y - p.y)
                p_out = on_border(p.x, p.y) or toward_border(p.x, p.y, p.x - q.x, p.y - q.y)
                if q_out and not p_out:
                    emit(q.x, q.y, p.x, p.y, path, seg_len)
                elif p_out and not q_out:
                    emit(p.x, p.y, q.x, q.y, path, seg_len)
            elif pin != qin:
                a, b = (p, q) if pin else (q, p)
                cut = clip_exit(a.x, a.y, b.x, b.y)
                if cut is not None:
                    emit(cut[0], cut[1], a.x, a.y, path, seg_len)
    return C._merge_anchors(out)
