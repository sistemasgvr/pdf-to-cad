"""Propiedades de una superficie (TIN) para el panel de Propiedades (pedido del usuario 2026-11-14: «al menos la ruta
del archivo original y otras propiedades clásicas que también se ven en Civil 3D»).

Las de la pestaña «Estadísticas» de Civil 3D que salen del TIN tal cual: puntos, triángulos, cotas mínima / máxima /
media, área 2D y 3D, pendiente media y máxima, lado y área de triángulo mínimos y máximos y la extensión. PURO (numpy).

Unidades: la cota llega en pies (`superficies.normalizar` la deja así); X/Y pueden venir en metros (sistema en metros
del proyecto) o pies: las áreas, lados y pendientes se dan en PIES (`unidad_xy` → factor), la extensión en la unidad
del dibujo.
"""
from __future__ import annotations

import numpy as np

A_PIES = {"meter": 1.0 / 0.3048, "foot": 1.0, "USSurveyFoot": 1200.0 / 3937.0 / 0.3048, "": 1.0}
PIES2_POR_ACRE = 43560.0


def estadisticas(puntos, triangulos, invisibles=None, unidad_xy="foot") -> dict:
    """{clave: valor} de la superficie; sin triángulos visibles solo cuenta puntos y cotas."""
    pts = np.asarray(puntos, np.float64).reshape(-1, 3)
    tri = np.asarray(triangulos, np.int64).reshape(-1, 3)
    if invisibles is not None and len(invisibles) == len(tri):
        tri = tri[~np.asarray(invisibles, dtype=bool)]
    k = A_PIES.get(unidad_xy or "", 1.0)
    out = {"n_puntos": int(len(pts)), "n_triangulos": int(len(tri))}
    if len(pts):
        z = pts[:, 2]
        out.update(z_min=float(z.min()), z_max=float(z.max()), z_media=float(z.mean()),
                   x_min=float(pts[:, 0].min()), x_max=float(pts[:, 0].max()),
                   y_min=float(pts[:, 1].min()), y_max=float(pts[:, 1].max()))
    if not len(tri):
        return out
    p = pts[tri] * np.array([k, k, 1.0])                         # todo en pies
    u, v = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    n = np.cross(u, v)
    a3 = np.linalg.norm(n, axis=1) / 2.0
    a2 = np.abs(n[:, 2]) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        pend = np.where(np.abs(n[:, 2]) > 0, np.hypot(n[:, 0], n[:, 1]) / np.abs(n[:, 2]) * 100.0, np.nan)
    lados = np.concatenate([np.linalg.norm(p[:, 1] - p[:, 0], axis=1), np.linalg.norm(p[:, 2] - p[:, 1], axis=1),
                            np.linalg.norm(p[:, 0] - p[:, 2], axis=1)])
    validas = np.isfinite(pend) & (a2 > 0)
    out.update(area_2d_ft2=float(a2.sum()), area_3d_ft2=float(a3.sum()),
               area_tri_min_ft2=float(a2.min()), area_tri_max_ft2=float(a2.max()),
               lado_min_ft=float(lados.min()), lado_max_ft=float(lados.max()))
    if np.any(validas):
        out.update(pendiente_media_pct=float(np.average(pend[validas], weights=a2[validas])),
                   pendiente_max_pct=float(pend[validas].max()))
    return out
