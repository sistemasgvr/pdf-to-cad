"""recognition_map_vaults.py — los buzones de la LEYENDA sobre las líneas de un mapa sin capas (PURO).

Mapas SIG aplanados (Quarter Section de Phoenix): el buzón es un SÍMBOLO de la fuente
(`leyenda_mapa.simbolos_capas`: un círculo virtual con el radio de su tinta) y la tubería,
un trazo de la capa por estilo que llega a su CENTRO (el SIG dibuja la red de buzón a
buzón), que termina ahí (cabecera, red que sale del mapa) o que lo atraviesa sin vértice.
Los pasos generales no lo cubren: `recognition_vault_snap` no mueve una punta que ya está
dentro del contorno, `recognition_vault_through` salta la línea que nace o muere en la
bóveda y `recognition_style_nodes` solo mira extremos compartidos por ≥2 trazos. Así 33 de
los 137 buzones de «QS Sewer North» 17-10 quedaban «sin línea» con la tinta a 0.1 pt de su
centro y, al importar, salían DOS veces (el buzón del extremo de la línea + una caja suelta).

Este paso, sobre la salida y sin mover nada (reporte del usuario 2026-10-14, «mejorar el
reconocimiento de buzones con la leyenda»):
  · Solo bóvedas de capas de SÍMBOLO (`pdf_styles.is_symbol`) y líneas de capas por estilo.
  · Cada línea con un vértice dentro del símbolo (radio + `TOL_PT`): el más cercano al
    centro pasa a «vault» (nunca la esquina de un codo).
  · Si no tiene vértice ahí pero su parte RECTA pasa a ≤ radio + `TOL_PT` del centro, se
    inserta el vértice «vault» en el pie (la línea dibujada es la misma).
  · La bóveda deja de ser «sin línea».
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from hoja import pdf_styles
from reconocimiento import recognition_vault_through as through_mod

Pt = Tuple[float, float]

TOL_PT = 0.5                 # margen sobre el radio de la tinta del símbolo
KEEP_KINDS = ("cut", "edge", "vault", "stop")


def _radius_px(vg: dict, zoom: float, scale_ft_per_pt: float) -> float:
    circ = vg.get("circle")
    if circ and circ[2] > 0:
        return float(circ[2])
    w = max(float(vg.get("width_ft") or 0.0), float(vg.get("length_ft") or 0.0))
    return 0.5 * w / max(scale_ft_per_pt, 1e-9) * zoom


def mark_symbol_vaults(polylines: Sequence, vaults_geo: Sequence[dict], zoom: float,
                       scale_ft_per_pt: float) -> List[dict]:
    """Une los buzones-símbolo con sus líneas (ver el docstring del módulo). Modifica
    `polylines` en su lugar. Devuelve [{"vault": índice, "at": [(x, y) px, …]}, …]."""
    lines = [pl for pl in polylines
             if (pl.layer_ocg or "").startswith(pdf_styles.PREFIX) and len(pl.pts_pdf) >= 2
             and len(pl.kinds) == len(pl.pts_pdf)]
    done = []
    for vi, vg in enumerate(vaults_geo):
        if not pdf_styles.is_symbol(vg.get("layer") or ""):
            continue
        c = tuple(vg["center"])
        lim = _radius_px(vg, zoom, scale_ft_per_pt) + TOL_PT * zoom
        at = []
        for pl in lines:
            fl = pl.fillets or {}
            near = [j for j, p in enumerate(pl.pts_pdf) if j not in fl and math.dist(p, c) <= lim]
            if near:
                j = min(near, key=lambda j: math.dist(pl.pts_pdf[j], c))
                if pl.kinds[j] not in KEEP_KINDS:
                    pl.kinds[j] = "vault"
                at.append(tuple(pl.pts_pdf[j]))
                continue
            best = None
            for k, s, e in through_mod._straight_parts(pl):
                f = through_mod._foot(c, s, e)
                if f is None:
                    continue
                q, t, off = f
                if 0.0 < t < 1.0 and off <= lim and (best is None or off < best[0]):
                    best = (off, k, q)
            if best is not None:
                _off, k, q = best
                through_mod._insert_vertex(pl, k, q, "vault")
                at.append(tuple(q))
        if at:
            done.append({"vault": vi, "at": at})
    return done
