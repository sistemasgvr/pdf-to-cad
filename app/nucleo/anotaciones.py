"""anotaciones.py — los rótulos del plano guardados en el proyecto (PURO; pedido del usuario 2026-11-03).

Los lee el reconocimiento (`reconocimiento/recognition_anotaciones`: MLeader con su guía, MText de los mapas) y
viven en `Main.anotaciones` (px de la vista, .digproj, deshacer). Aquí: juntar sin repetir, a qué utilidad señala
cada uno (la punta de su guía o, sin guía, su centro) y volver a leer utilidad/diámetro/material de un texto que
corrigió la IA o el usuario. El DXF los exporta como MULTILEADER / MTEXT con XDATA `PDFCAD_ANOT` (`exportar/
dxf_anotaciones`).
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

MISMO_PX = 1.5                 # dos anotaciones con el mismo texto y su caja a menos de esto (px) = la misma
SENALA_PX = 12.0               # la punta de una guía señala la utilidad que pasa a menos de esto (px)


def _firma(a: dict):
    c = a.get("caja") or (0, 0, 0, 0)
    return (a.get("texto") or "", a.get("tipo"), tuple(int(round(v / MISMO_PX)) for v in c))


def juntar(existentes: Sequence[dict], nuevas: Sequence[dict]) -> List[dict]:
    """Las de antes + las nuevas que no estaban (mismo texto, misma caja). Una que ya estaba y la IA o el usuario
    leyeron (`fuente` ≠ pdf) se conserva; si el PDF ahora la lee, gana la del PDF."""
    out = list(existentes)
    idx = {_firma(a): k for k, a in enumerate(out)}
    ilegibles = {tuple(int(round(v / MISMO_PX)) for v in (a.get("caja") or ())): k
                 for k, a in enumerate(out) if a.get("estado") == "ilegible" or a.get("fuente") != "pdf"}
    for a in nuevas:
        f = _firma(a)
        if f in idx:
            continue
        k = ilegibles.get(f[2])
        if k is not None and a.get("estado") == "ilegible":
            continue                                 # ya estaba (quizá ya leída por la IA)
        out.append(dict(a))
        idx[f] = len(out) - 1
    return out


def _dist_seg(p: Pt, a: Pt, b: Pt) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    u = 0.0 if L2 <= 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(p[0] - a[0] - u * vx, p[1] - a[1] - u * vy)


def _centro(a: dict) -> Pt:
    c = a.get("caja") or (0, 0, 0, 0)
    return ((c[0] + c[2]) / 2.0, (c[1] + c[3]) / 2.0)


def senala(a: dict, pipes: Sequence[dict], tol_px: float = SENALA_PX) -> Optional[int]:
    """Índice de la utilidad a la que señala la anotación (la más cercana a una punta de su guía, ≤ tol; sin guía,
    la más cercana a su centro, ≤ 3×tol), o None."""
    puntos = list(a.get("puntas") or ()) or [_centro(a)]
    lim = tol_px if a.get("puntas") else 3.0 * tol_px
    mejor = None
    for i, p in enumerate(pipes):
        pts = p.get("pts") or []
        for q in puntos:
            d = min((_dist_seg(q, s, e) for s, e in zip(pts, pts[1:])), default=math.inf)
            if d <= lim and (mejor is None or d < mejor[0]):
                mejor = (d, i)
    return mejor[1] if mejor else None


def releer(a: dict, texto: str, fuente: str, confianza: str = "") -> dict:
    """La anotación con un texto nuevo (de la IA o del usuario): utilidad, diámetro y material otra vez."""
    from reconocimiento import recognition_grosor_texto as GT
    lineas = [t for t in (texto or "").splitlines() if t.strip()]
    util = next((u for u in (GT.utilidad_de(t) for t in lineas) if u), "")
    diams = sorted({v for t in lineas for v, _n in GT.lecturas(t)})
    mat = next((m for m in (GT.material_de(t) for t in lineas) if m), "")
    b = dict(a, texto="\n".join(lineas), utilidad=util, diam_in=diams[0] if len(diams) == 1 else None,
             material=mat, fuente=fuente, estado="leido" if lineas else "ilegible")
    if confianza:
        b["confianza"] = confianza
    return b


def ilegibles(anotaciones: Sequence[dict]) -> List[int]:
    return [k for k, a in enumerate(anotaciones) if a.get("estado") == "ilegible"]


def resumen(anotaciones: Sequence[dict]) -> dict:
    """{multileader, mtext, ilegible, ia}: cuántas de cada clase."""
    out = dict(multileader=0, mtext=0, ilegible=0, ia=0)
    for a in anotaciones:
        out["multileader" if a.get("tipo") == "multileader" else "mtext"] += 1
        out["ilegible"] += a.get("estado") == "ilegible"
        out["ia"] += a.get("fuente") == "ia"
    return out
