"""estilos_sugeridos.py — qué estilos son la red en una hoja SIN capas ni leyenda (PURO: fitz).

Reporte del usuario 2026-11-14 («Southwest Gas Combined 811 Records»: el PDF dice que es gas y
«Capas de la hoja» no marcaba nada; había que asignar cada estilo a mano). Sin capas ni leyenda,
el plano todavía dice dos cosas:

- QUÉ RED es: el texto del plano la nombra («GAS DISTRIBUTION SYSTEM», «Southwest Gas
  Corporation»). `utilidad_de_texto` cuenta las palabras de cada red (`PALABRAS`); gana una solo
  si la nombran ≥ `MIN_MENCIONES` veces y `VENTAJA` veces más que a cualquier otra.
- QUÉ ESTILOS son sus tuberías: los rótulos de tubería (`2" PE '87`, `81' 3/4" STL '56`) corren
  paralelos a su línea. (1) Un rótulo del MISMO COLOR que un estilo de línea pegado a él (≤
  `CERCA_LETRAS` letras) vota por ese estilo: ArcGIS pinta el rótulo como su capa (Southwest: las
  acometidas naranjas). Gana el estilo con ≥ `MIN_VOTOS` votos y ≥ `MIN_FRACCION` de los rótulos de
  color. (2) La red PRINCIPAL: las acometidas nacen sobre ella; el estilo de línea (no un símbolo)
  sobre el que caen ≥ `MIN_PUNTAS` de las puntas del estilo hallado, y el doble que cualquier otro.
  Si el rótulo no tiene el color de ningún estilo, el estilo que la mayoría de rótulos tiene al
  lado, único más cercano (`_cercanos`).

Nada se asigna si no es claro: `Sugerencia.motivo` dice por qué (la interfaz lo avisa).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

PALABRAS: Dict[str, Tuple[str, ...]] = {
    "GAS": (r"\bN?GAS\b", r"\bNATURAL\s+GAS\b"),
    "AGUA": (r"\bWATER\b", r"\bAGUA\b"),
    "ALCANTARILLADO": (r"\bSEWER\b", r"\bSANITARY\b", r"\bALCANTARILLADO\b"),
    "DRENAJE": (r"\bSTORM\s+DRAIN\b", r"\bSTORM\s+SEWER\b", r"\bDRENAJE\b"),
    "ELECTRICO": (r"\bELECTRIC(AL)?\b", r"\bPOWER\b", r"\bEL[EÉ]CTRIC[AO]\b"),
    "TELECOM": (r"\bTELECOM\w*\b", r"\bFIBER\s+OPTIC\b", r"\bTELEPHONE\b", r"\bCOMMUNICATIONS?\b"),
}
MIN_MENCIONES = 3          # (un mapa de gas nombra «ELECTRIC» un par de veces en sus rótulos)
VENTAJA = 3                # la red nombrada al menos esto × más que cualquier otra
CERCA_LETRAS = 3.0          # × letra: lo más lejos que va un rótulo de su línea
PARALELO_SEN = 0.26         # ±15°
MIN_VOTOS = 5
MIN_FRACCION = 0.2
MIN_PUNTAS = 0.15           # fracción de puntas de las acometidas sobre la red principal
PUNTA_PT = 0.6              # una punta «cae» sobre una línea a ≤ esto
COLOR_TOL = 0.1             # por canal (0–1): el rótulo y su línea no siempre llevan el MISMO color
CELDA_PT = 40.0

# motivos (la interfaz los traduce)
OK = "ok"
SIN_ROTULOS = "sin_rotulos"         # no hay rótulos de tubería: no se sabe qué estilo es la red
SIN_ESTILO = "sin_estilo"           # hay rótulos, pero ningún estilo los lleva claramente
SIN_UTILIDAD = "sin_utilidad"       # se sabe qué estilos son tuberías, no de qué red


@dataclass
class Sugerencia:
    utilidad: Optional[str] = None
    lineas: List[str] = field(default_factory=list)      # capas virtuales (estilos) de LÍNEA
    principal: Optional[str] = None
    rotulada: Optional[str] = None                       # el estilo de los rótulos de color
    motivo: str = SIN_ROTULOS
    menciones: Dict[str, int] = field(default_factory=dict)
    rotulos: int = 0
    # capas de LÍNEA de imagen (`imagen_ejes`): utilidad, seguro/dudoso y evidencias (`certeza_capas`)
    capas: list = field(default_factory=list)


def utilidad_de_texto(textos: Iterable[str]) -> Tuple[Optional[str], Dict[str, int]]:
    cuenta: Counter = Counter()
    for t in textos:
        T = (t or "").upper()
        for u, rxs in PALABRAS.items():
            cuenta[u] += sum(len(re.findall(rx, T)) for rx in rxs)
    orden = cuenta.most_common()
    if not orden or orden[0][1] < MIN_MENCIONES:
        return None, dict(cuenta)
    if len(orden) > 1 and orden[1][1] * VENTAJA > orden[0][1]:
        return None, dict(cuenta)
    return orden[0][0], dict(cuenta)


def familias(cuenta: Dict[str, int]) -> Dict[str, str]:
    """{estilo: estilo de su familia} (`pdf_styles.familias`)."""
    from hoja import pdf_styles
    return pdf_styles.familias(cuenta)


def _segmentos(paths):
    """{estilo: [(x0, y0, x1, y1)]}, {estilo: color}, {estilo: [(punta, punta) de cada trazo]} —
    solo trazos de línea de las capas virtuales por estilo (no símbolos ni rellenos sin borde),
    por FAMILIA de estilo (`familias`); y {familia: [sus estilos]}."""
    from hoja import pdf_styles
    segs, color, puntas = defaultdict(list), {}, defaultdict(list)
    validos = [p for p in paths if (p.get("layer") or "").startswith(pdf_styles.PREFIX)
               and not pdf_styles.is_symbol(p["layer"]) and p.get("color") is not None
               and p.get("type") not in ("clip", "group")]
    rep = familias(Counter(p["layer"] for p in validos))
    miembros: Dict[str, List[str]] = defaultdict(list)
    for n, r in rep.items():
        miembros[r].append(n)
    for p in validos:
        L = rep[p["layer"]]
        color[L] = tuple(float(v) for v in p["color"][:3])
        its = [it for it in p.get("items", ()) if it[0] in ("l", "c")]
        for it in its:
            a, b = it[1], it[-1]
            segs[L].append((a.x, a.y, b.x, b.y))
        if its:
            a, b = its[0][1], its[-1][-1]
            puntas[L].append(((a.x, a.y), (b.x, b.y)))
    return segs, color, puntas, miembros


def _rejilla(segs):
    g = defaultdict(list)
    for L, ss in segs.items():
        for s in ss:
            x0, x1 = sorted((s[0], s[2]))
            y0, y1 = sorted((s[1], s[3]))
            for gx in range(int(x0 // CELDA_PT), int(x1 // CELDA_PT) + 1):
                for gy in range(int(y0 // CELDA_PT), int(y1 // CELDA_PT) + 1):
                    g[(gx, gy)].append((L, s))
    return g


def _cercanos(c, rejilla) -> Dict[str, float]:
    """{estilo: distancia} de las líneas paralelas al rótulo `c` (corrida de texto) a su lado."""
    tam = c.tam
    dx, dy = c.dir
    o, f = c.origen, c.fin
    nx, ny = dy, -dx                                    # hacia «arriba» de la letra
    cx = (o[0] + f[0]) / 2.0 + nx * 0.35 * tam
    cy = (o[1] + f[1]) / 2.0 + ny * 0.35 * tam
    largo = math.dist(o, f)
    lim = CERCA_LETRAS * tam
    out: Dict[str, float] = {}
    for gx in range(int((cx - lim) // CELDA_PT), int((cx + lim) // CELDA_PT) + 1):
        for gy in range(int((cy - lim) // CELDA_PT), int((cy + lim) // CELDA_PT) + 1):
            for L, (ax, ay, bx, by) in rejilla.get((gx, gy), ()):
                ex, ey = bx - ax, by - ay
                l = math.hypot(ex, ey)
                if l < 1.0:
                    continue
                ux, uy = ex / l, ey / l
                if abs(ux * dy - uy * dx) > PARALELO_SEN:
                    continue
                u = (cx - ax) * ux + (cy - ay) * uy
                if u < -largo / 2.0 or u > l + largo / 2.0:
                    continue
                d = abs((cx - ax) * uy - (cy - ay) * ux)
                if d <= lim and d < out.get(L, 1e18):
                    out[L] = d
    return out


def _sobre(p, rejilla, propio: str) -> set:
    x, y = p
    hit = set()
    for L, (ax, ay, bx, by) in rejilla.get((int(x // CELDA_PT), int(y // CELDA_PT)), ()):
        if L == propio:
            continue
        ex, ey = bx - ax, by - ay
        l2 = ex * ex + ey * ey
        if l2 < 1e-9:
            continue
        t = max(0.0, min(1.0, ((x - ax) * ex + (y - ay) * ey) / l2))
        if math.hypot(ax + t * ex - x, ay + t * ey - y) <= PUNTA_PT:
            hit.add(L)
    return hit


def sugerir(page, paths=None, corridas=None, textos: Iterable[str] = (), nombres: Iterable[str] = (),
            leyenda=None) -> Sugerencia:
    """Estilos de la red de esta hoja (sin capas ni leyenda). `paths` = `pdf_styles.drawings(page)`
    y `corridas` = `texto_pdf.corridas(page)` si ya se leyeron; `textos` = más texto del documento
    (hojas de origen de una hoja compuesta: su cajetín quedó fuera del recorte); `nombres` = nombres
    de los PDF (el abierto y, en una compuesta, los de origen). Al final, la certeza de cada capa de
    LÍNEA de imagen (`certeza_capas.evaluar` → `Sugerencia.capas`; [] en hojas sin red en imagen)."""
    from hoja import certeza_capas, pdf_styles, texto_pdf
    if paths is None:
        paths = pdf_styles.drawings(page)
    if corridas is None:
        corridas = texto_pdf.corridas(page)
    sug = _sugerir(page, paths, corridas, textos)
    sug.capas = certeza_capas.evaluar(paths, corridas, sug.utilidad, list(nombres or ()), leyenda)
    return sug


def _sugerir(page, paths, corridas, textos) -> Sugerencia:
    from reconocimiento import recognition_grosor_registros as GR
    sug = Sugerencia()
    sug.utilidad, sug.menciones = utilidad_de_texto([page.get_text()] + list(textos))
    rot = [c for c in corridas if c.glifos and GR.RX_DIAM.match((c.texto or "").upper())]
    sug.rotulos = len(rot)
    if not rot:
        sug.motivo = SIN_ROTULOS
        return sug
    segs, color, puntas, miembros = _segmentos(paths)
    rejilla = _rejilla(segs)
    por_color: Counter = Counter()
    sin_color: Counter = Counter()
    n_color = 0
    for c in rot:
        cerca = _cercanos(c, rejilla)
        if not cerca:
            continue
        tc = tuple(float(v) for v in (c.glifos[0].color or (0, 0, 0))[:3])
        mismo = [L for L in cerca if max(abs(a - b) for a, b in zip(color[L], tc)) <= COLOR_TOL]
        if mismo:
            n_color += 1
            por_color[min(mismo, key=cerca.get)] += 1
            continue
        orden = sorted(cerca.items(), key=lambda kv: kv[1])
        d0 = orden[0][1]
        if d0 <= 1.2 * c.tam and (len(orden) == 1 or orden[1][1] > 1.6 * d0 + 0.2 * c.tam):
            sin_color[orden[0][0]] += 1
    rotulada = None
    if por_color:
        L, n = por_color.most_common(1)[0]
        if n >= MIN_VOTOS and n >= MIN_FRACCION * n_color:
            rotulada = L
    if rotulada is None and sin_color:
        L, n = sin_color.most_common(1)[0]
        otros = sin_color.most_common(2)[1][1] if len(sin_color) > 1 else 0
        if n >= MIN_VOTOS and n >= 2 * otros:
            rotulada = L
    if rotulada is None:
        sug.motivo = SIN_ESTILO
        return sug
    sug.rotulada = rotulada
    toca: Counter = Counter()
    n_puntas = 0
    for a, b in puntas.get(rotulada, ()):
        for p in (a, b):
            n_puntas += 1
            for L in _sobre(p, rejilla, rotulada):
                toca[L] += 1
    if toca:
        L, n = toca.most_common(1)[0]
        otro = toca.most_common(2)[1][1] if len(toca) > 1 else 0
        if n >= MIN_PUNTAS * n_puntas and n >= 2 * otro:
            sug.principal = L
    sug.lineas = [m for L in (sug.principal, rotulada) if L for m in sorted(miembros.get(L, [L]))]
    sug.motivo = OK if sug.utilidad else SIN_UTILIDAD
    return sug


def textos_de_documento(doc, max_paginas: int = 60) -> List[str]:
    """Texto de las hojas de un PDF (el cajetín de cada hoja), para `utilidad_de_texto`."""
    out = []
    for i in range(min(len(doc), max_paginas)):
        try:
            out.append(doc[i].get_text())
        except Exception:
            continue
    return out
