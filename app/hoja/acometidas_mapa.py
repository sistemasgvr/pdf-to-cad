"""acometidas_mapa.py — las ACOMETIDAS (servicios a los predios) de un mapa sin capas (PURO).

Pedido del usuario (2026-10-14, «QS Water South» h.4): la línea fina que sale de la tubería
de agua hacia un lote es la acometida («As-Built Tap» en la leyenda; «*All water taps are
.75" in diameter»). Se dibuja con el MISMO estilo que los linderos y la vía pública (negro
0.19 pt), así que el estilo solo no la separa (la leyenda lo deja «ambiguo»). Dos cosas sí:

  · NACE sobre la tubería: una punta sobre la tinta de la red (≤ `TOCA_PT`), la otra no.
  · El SIG dibuja cada capa en un BLOQUE seguido (orden de dibujo, `seqno`): las 498
    acometidas de esa hoja van juntas tras la red, y el 88 % de ellas nace sobre la
    tubería; los linderos de su bloque que la tocan son el 3 %.
Acometida = trazo del estilo de una fila «Tap»/«Service» de la leyenda, en un bloque
(`BLOQUE_HUECO`) donde ≥ `FRACCION_MIN` de los trazos nacen sobre la red de esa utilidad
(estilos de sus filas de LÍNEA en `leyenda_mapa.asignaciones`), y que nace sobre ella.

  · `trazos(page)` → {seqno: utilidad} (caché por documento y hoja).
  · `capa(estilo, utilidad)` / `es_capa(nombre)`: la capa virtual «Acometidas» de ese estilo
    (`pdf_styles.drawings` les pone esa capa; en «Capas de la hoja» es una fila aparte).
Nada se mueve ni se borra: es otra capa virtual con los mismos trazos.
"""
from __future__ import annotations

import json
import math
from typing import Dict, List, Sequence, Tuple

from hoja import leyenda_mapa as LM

Pt = Tuple[float, float]

TOCA_PT = 0.35               # punta sobre la tinta de la red
BLOQUE_HUECO = 20            # trazos de otros estilos entre dos del bloque (orden de dibujo)
FRACCION_MIN = 0.5           # del bloque que nace sobre la red
TRAZOS_MIN = 3               # un bloque de acometidas tiene varias
BEZIER_PASO_PT = 1.0         # muestreo de las curvas de la red
CELDA_PT = 20.0              # celdas del índice de tramos de la red

PREFIJO = "PDF_STYLE:"       # = pdf_styles.PREFIX (sin importarlo: pdf_styles importa este módulo)


def capa(estilo: str, utilidad: str) -> str:
    """Capa virtual de las acometidas de `utilidad` dibujadas con la capa por estilo `estilo`."""
    base = json.loads(estilo[len(PREFIJO):])
    return PREFIJO + json.dumps(["tap", utilidad, base], separators=(",", ":"))


def es_capa(nombre: str) -> bool:
    return (nombre or "").startswith(PREFIJO + '["tap"')


def estilo_de(nombre: str) -> str:
    """Capa por estilo de la que sale la capa de acometidas `nombre`."""
    _t, _u, base = json.loads(nombre[len(PREFIJO):])
    return PREFIJO + json.dumps(base, separators=(",", ":"))


def utilidad_de(nombre: str) -> str:
    return json.loads(nombre[len(PREFIJO):])[1]


def _cadenas(d) -> List[List[Pt]]:
    """Ristras del trazo; las curvas Bézier en puntos cada ≤ `BEZIER_PASO_PT` (la tubería
    curva de Phoenix se aparta hasta 0.5 pt de su cuerda: la acometida nace en la curva)."""
    out, cur = [], []
    for it in d.get("items") or ():
        if it[0] not in ("l", "c"):
            if len(cur) >= 2:
                out.append(cur)
            cur = []
            continue
        a, b = (float(it[1][0]), float(it[1][1])), (float(it[-1][0]), float(it[-1][1]))
        if cur and math.dist(cur[-1], a) > 0.05:
            if len(cur) >= 2:
                out.append(cur)
            cur = []
        if not cur:
            cur.append(a)
        if it[0] == "c":
            p = [a] + [(float(q[0]), float(q[1])) for q in it[2:5]]
            n = max(2, math.ceil(sum(math.dist(u, v) for u, v in zip(p, p[1:])) / BEZIER_PASO_PT))
            for k in range(1, n):
                t = k / n
                w = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3)
                cur.append((sum(wi * q[0] for wi, q in zip(w, p)), sum(wi * q[1] for wi, q in zip(w, p))))
        cur.append(b)
    if len(cur) >= 2:
        out.append(cur)
    return out


def _dentro(rect, zonas) -> bool:
    return any(z[0] <= rect.x0 and rect.x1 <= z[2] and z[1] <= rect.y0 and rect.y1 <= z[3] for z in zonas)


def _nace_sobre(cadenas, cerca) -> bool:
    """Una punta sobre la red y la otra no (en alguna de sus ristras)."""
    for ch in cadenas:
        a, b = cerca(ch[0]), cerca(ch[-1])
        if a != b:
            return True
    return False


def _bloques(trazos: Sequence[Tuple[int, dict]]) -> List[List[Tuple[int, dict]]]:
    """Trazos (índice en el orden de dibujo, trazo) partidos donde entre dos seguidos hay
    más de `BLOQUE_HUECO` trazos de otros estilos."""
    out: List[List[Tuple[int, dict]]] = []
    for t in sorted(trazos, key=lambda t: t[0]):
        if out and t[0] - out[-1][-1][0] <= BLOQUE_HUECO + 1:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def _calcular(page) -> Dict[int, str]:
    import numpy as np
    from hoja import leyenda_mapa_lectura as lectura
    doc = page.parent
    ley = LM.leer(doc, page)
    filas = [f for f in ley.filas if f.rol == LM.ACOMETIDA and f.utilidad]
    if not filas:
        return {}
    dibujos = lectura._dibujos(page)
    en_mapa: Dict[str, int] = {}
    for d in dibujos:
        en_mapa[d["layer"]] = en_mapa.get(d["layer"], 0) + 1
    asig, _amb = LM.asignaciones(ley, en_mapa)
    zonas = list(ley.zonas)
    out: Dict[int, str] = {}
    for utilidad in sorted({f.utilidad for f in filas}):
        red = {n for n, (u, r) in asig.items() if u == utilidad and r == LM.ROL_LINEAS}
        estilos = {LM._trazo_principal(f) for f in filas if f.utilidad == utilidad} - {None} - red
        if not red or not estilos:
            continue
        segs = np.array([(a[0], a[1], b[0], b[1]) for d in dibujos if d["layer"] in red and not _dentro(d["rect"], zonas)
                         for ch in _cadenas(d) for a, b in zip(ch, ch[1:])], float)
        if not len(segs):
            continue
        ax, ay, bx, by = segs.T
        vx, vy = bx - ax, by - ay
        L2 = np.maximum(vx * vx + vy * vy, 1e-12)
        x0, y0 = np.minimum(ax, bx) - TOCA_PT, np.minimum(ay, by) - TOCA_PT
        x1, y1 = np.maximum(ax, bx) + TOCA_PT, np.maximum(ay, by) + TOCA_PT

        # tramos por celdas (todos contra todos eran minutos en una hoja compuesta): cada
        # punta mide solo los de su celda y las vecinas, con la misma cuenta
        celdas: Dict[Tuple[int, int], List[int]] = {}
        for k in range(len(segs)):
            for cx in range(int(x0[k] // CELDA_PT), int(x1[k] // CELDA_PT) + 1):
                for cy in range(int(y0[k] // CELDA_PT), int(y1[k] // CELDA_PT) + 1):
                    celdas.setdefault((cx, cy), []).append(k)

        def cerca(p) -> bool:
            cand = celdas.get((int(p[0] // CELDA_PT), int(p[1] // CELDA_PT)))
            if not cand:
                return False
            c = np.array(cand)
            m = c[(x0[c] <= p[0]) & (p[0] <= x1[c]) & (y0[c] <= p[1]) & (p[1] <= y1[c])]
            if not len(m):
                return False
            t = np.clip(((p[0] - ax[m]) * vx[m] + (p[1] - ay[m]) * vy[m]) / L2[m], 0.0, 1.0)
            return bool(np.min(np.hypot(ax[m] + t * vx[m] - p[0], ay[m] + t * vy[m] - p[1])) <= TOCA_PT)
        for estilo in estilos:
            cand = [(i, d) for i, d in enumerate(dibujos) if d["layer"] == estilo and not _dentro(d["rect"], zonas)]
            for bloque in _bloques(cand):
                nacen = [d for _i, d in bloque if _nace_sobre(_cadenas(d), cerca)]
                if len(nacen) >= TRAZOS_MIN and len(nacen) >= FRACCION_MIN * len(bloque):
                    for d in nacen:
                        out[d["seqno"]] = utilidad
    return out


def trazos(page) -> Dict[int, str]:
    """{seqno: utilidad} de los trazos de la hoja que son acometidas (ver el docstring)."""
    cache = page.parent.__dict__.setdefault("_pdfcad_acometidas", {})
    if page.number not in cache:
        try:
            cache[page.number] = _calcular(page)
        except Exception:
            cache[page.number] = {}
        finally:
            # los trazos de la hoja que dejó la leyenda (decenas de MB en un mapa): ya no hacen falta
            page.parent.__dict__.pop("_pdfcad_dibujos", None)
    return cache[page.number]
