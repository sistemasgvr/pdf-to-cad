"""certeza_capas.py — de qué utilidad es cada capa de LÍNEA de imagen y si es SEGURO aplicarla sola (PURO: sin Qt).

Plan 2026-11-18 «Ejes de la red en imagen», Tarea 6 (spec §7.5). Los mapas «QS SD» de Phoenix traen la red en
imagen; `imagen_ejes` la vuelve capas virtuales `PDF_STYLE:["img","line",[r,g,b]]` (y la `"fino"` de un color con
dos grosores). Por cada capa de línea de imagen se juntan evidencias:

- **nombre** del PDF (`composicion_hermanos.utilidad`: «QS SD_…» → DRENAJE; en una hoja compuesta, también los de
  las hojas de origen: `nombres`);
- **leyenda**: una fila de LÍNEA con utilidad cuya muestra es de ese color (vectorial o de imagen);
- **texto** del plano (`estilos_sugeridos.utilidad_de_texto`);
- **rotulos** de diámetro («18" HDPE») junto a sus ejes (≤ `CERCA_LETRAS` letras, paralelos; cada rótulo vota por
  la capa de imagen más cercana): ≥ `MIN_VOTOS` dicen que ESA capa es una red. Un rótulo que nombra otra utilidad
  («8" WATER», «8" W») vota por ella: si son ≥ `CONTRADICE_FRAC` de los rótulos de la capa → `contradice:<UTIL>`.
  Los materiales (`recognition_grosor_mapa.MATERIALES`) no nombran utilidad: solo cuentan como rótulo de tubería;
- **trayectoria**: capas de SÍMBOLO del mismo color con ≥ `FRACCION_EN_PUNTAS` de sus centros a ≤ 1.5·r de una
  punta o un vértice de los ejes (sumideros, buzones) → `simbolos` (no decide sola).

**Seguro** = una sola utilidad candidata (nombre, leyenda o texto); la capa es la única de línea de COLOR de la hoja
(imagen o vector, sin negro ni gris; una capa y su `"fino"` del mismo color cuentan como UN color) o tiene ≥
`MIN_VOTOS` rótulos; y nada la contradice. Una capa `"fino"` nunca es segura solo por el color: necesita sus propios
rótulos (`en_contra` «fino»). Negro/gris de imagen: nunca seguro sin leyenda o rótulos (`en_contra` «acromatico»).

Evidencias como claves: «nombre», «leyenda», «texto», «rotulos», «trayectoria», «contradice:<UTIL>»,
«varios_colores», «sin_evidencia», «fino», «acromatico».
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

MIN_VOTOS = 5                   # rótulos de diámetro junto a la capa para decir «esta capa es una red»
CERCA_LETRAS = 3.0              # × letra (como `estilos_sugeridos.CERCA_LETRAS`)
FRACCION_EN_PUNTAS = 0.3        # de los símbolos de una capa, en las puntas/vértices de los ejes
PUNTA_R = 1.5                   # × radio del símbolo
CONTRADICE_FRAC = 0.2           # de los rótulos de la capa que nombran OTRA utilidad
ACROMATICO = 0.02               # (0–1) como `imagen_ejes.ACROMATICO_TOL`
COLOR_TOL = 0.1                 # por canal (0–1): dos colores «iguales»
CELDA_PT = 20.0

# código o palabra al final de un rótulo de tubería → utilidad (los materiales se miran antes)
CODIGOS = {"W": "AGUA", "WTR": "AGUA", "SS": "ALCANTARILLADO", "SSL": "ALCANTARILLADO", "SAN": "ALCANTARILLADO",
           "SD": "DRENAJE", "STM": "DRENAJE", "G": "GAS", "E": "ELECTRICO", "TEL": "TELECOM"}


@dataclass
class CapaCerteza:
    capa: str
    utilidad: Optional[str]
    seguro: bool
    a_favor: List[str] = field(default_factory=list)
    en_contra: List[str] = field(default_factory=list)
    simbolos: List[str] = field(default_factory=list)


def _acromatico(rgb01) -> bool:
    return max(rgb01) - min(rgb01) < ACROMATICO or max(rgb01) < ACROMATICO


def _mismo(a, b) -> bool:
    return max(abs(x - y) for x, y in zip(a, b)) <= COLOR_TOL


def _colores_de_hoja(paths) -> List[tuple]:
    """Colores (0–1) de las capas de LÍNEA de la hoja, sin negro, gris ni blanco: las de imagen por su rgb (una capa
    y su «fino», el mismo), las vectoriales por estilo con borde (no símbolos, no rellenos de imagen)."""
    from hoja import imagen_ejes as IE, pdf_styles
    out: List[tuple] = []
    vistos = set()
    for p in paths:
        L = p.get("layer") or ""
        if L in vistos or not L.startswith(pdf_styles.PREFIX) or pdf_styles.is_symbol(L):
            continue
        vistos.add(L)
        if IE.es_imagen(L):
            if IE.tipo_imagen(L) != "line":
                continue
            c = tuple(v / 255.0 for v in IE.rgb_de(L))
        else:
            if p.get("color") is None or p.get("type") in ("clip", "group", "f"):
                continue
            c = tuple(float(v) for v in p["color"][:3])
        if not _acromatico(c) and not any(_mismo(c, o) for o in out):
            out.append(c)
    return out


def _utilidades_rotulo(resto: str):
    """(utilidades que nombra el resto de un rótulo de diámetro). Los materiales no nombran utilidad."""
    from hoja import estilos_sugeridos as ES
    from reconocimiento import recognition_grosor_mapa as GM
    T = (resto or "").upper()
    out = set()
    for w in re.findall(r"[A-Z]+", T):
        if w in GM.MATERIALES:
            continue
        if w in CODIGOS:
            out.add(CODIGOS[w])
    for u, rxs in ES.PALABRAS.items():
        if any(re.search(rx, T) for rx in rxs):
            out.add(u)
    return out


def _rotulos_por_capa(lineas: Dict[str, list], corridas):
    """{capa: nº de rótulos de diámetro junto a ella}, {capa: Counter(utilidad nombrada)}."""
    from hoja import estilos_sugeridos as ES
    from reconocimiento import recognition_grosor_registros as GR
    segs = {L: [s for t in ts for s in t] for L, ts in lineas.items()}
    rejilla = ES._rejilla(segs)
    votos: Counter = Counter()
    utils: Dict[str, Counter] = defaultdict(Counter)
    for c in corridas or ():
        if not getattr(c, "glifos", None):
            continue
        m = GR.RX_DIAM.match((c.texto or "").upper())
        if not m:
            continue
        cerca = ES._cercanos(c, rejilla)
        if not cerca:
            continue
        L = min(cerca, key=lambda k: (cerca[k], k))
        votos[L] += 1
        for u in _utilidades_rotulo(m.groups()[-1] or ""):            # el resto, tras el diámetro
            utils[L][u] += 1
    return votos, utils


def _simbolos_en_puntas(paths, capa: str, puntos) -> List[str]:
    from hoja import imagen_ejes as IE
    rgb = IE.rgb_de(capa)
    celdas = defaultdict(list)
    for x, y in puntos:
        celdas[(int(x // CELDA_PT), int(y // CELDA_PT))].append((x, y))
    total, cerca = Counter(), Counter()
    for p in paths:
        L = p.get("layer") or ""
        if IE.tipo_imagen(L) != "sym" or IE.rgb_de(L) != rgb:
            continue
        r = p["rect"]
        cx, cy = (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0
        lim = PUNTA_R * max((r[2] - r[0]) / 2.0, (r[3] - r[1]) / 2.0)
        total[L] += 1
        hit = False
        for gx in range(int((cx - lim) // CELDA_PT), int((cx + lim) // CELDA_PT) + 1):
            for gy in range(int((cy - lim) // CELDA_PT), int((cy + lim) // CELDA_PT) + 1):
                if any(math.hypot(x - cx, y - cy) <= lim for x, y in celdas.get((gx, gy), ())):
                    hit = True
                    break
            if hit:
                break
        cerca[L] += hit
    return sorted(L for L in total if cerca[L] >= FRACCION_EN_PUNTAS * total[L] and cerca[L] > 0)


def _de_leyenda(leyenda, rgb01) -> set:
    """Utilidades de las filas de LÍNEA de la leyenda con una muestra de ese color."""
    from hoja import imagen_ejes as IE, leyenda_mapa as LM, pdf_styles
    out = set()
    for f in getattr(leyenda, "filas", None) or ():
        if f.rol != LM.LINEA or not f.utilidad:
            continue
        for n in f.estilos:
            if IE.es_imagen(n):
                c = tuple(v / 255.0 for v in IE.rgb_de(n))
            else:
                k = pdf_styles._partes(n)
                c = k[1] if k and k[1] is not None else None
            if c is not None and _mismo(tuple(c[:3]), rgb01):
                out.add(f.utilidad)
    return out


def evaluar(paths, corridas, utilidad_texto: Optional[str], nombres: Sequence[str] = (),
            leyenda=None) -> List[CapaCerteza]:
    """Una `CapaCerteza` por capa de LÍNEA de imagen de `paths` (ver el docstring); [] si no hay ninguna."""
    from hoja import composicion_hermanos as CH, imagen_ejes as IE
    lineas: Dict[str, list] = defaultdict(list)
    puntos: Dict[str, list] = defaultdict(list)
    for p in paths or ():
        L = p.get("layer") or ""
        if IE.tipo_imagen(L) != "line":
            continue
        tramos = [(it[1].x, it[1].y, it[-1].x, it[-1].y) for it in p.get("items", ()) if it[0] == "l"]
        lineas[L].append(tramos)
        for x0, y0, x1, y1 in tramos:
            puntos[L] += [(x0, y0), (x1, y1)]
    if not lineas:
        return []
    colores = _colores_de_hoja(paths)
    votos, utils = _rotulos_por_capa(lineas, corridas)
    por_nombre = {u for u in (CH.utilidad(n) for n in nombres or ()) if u}
    out = []
    for L in sorted(lineas):
        rgb01 = tuple(v / 255.0 for v in IE.rgb_de(L))
        fino = L.endswith(',"' + IE.FINO + '"]')
        fuentes = {"nombre": por_nombre, "leyenda": _de_leyenda(leyenda, rgb01),
                   "texto": {utilidad_texto} if utilidad_texto else set()}
        a_favor, en_contra = [], []
        cands = set().union(*fuentes.values())
        util = None
        for k in ("nombre", "leyenda", "texto"):           # la de más peso, si hay varias
            if len(fuentes[k]) == 1 and util is None:
                util = next(iter(fuentes[k]))
        if util is None and cands:
            util = sorted(cands)[0]
        for k in ("nombre", "leyenda", "texto"):
            if util in fuentes[k]:
                a_favor.append(k)
        for u in sorted(cands - {util}):
            en_contra.append("contradice:" + u)
        n_rot = votos.get(L, 0)
        if n_rot >= MIN_VOTOS:
            a_favor.append("rotulos")
        for u, n in sorted(utils.get(L, Counter()).items()):
            if u != util and n >= CONTRADICE_FRAC * n_rot and "contradice:" + u not in en_contra:
                en_contra.append("contradice:" + u)
        sim = _simbolos_en_puntas(paths, L, puntos[L])
        if sim:
            a_favor.append("trayectoria")
        acrom = _acromatico(rgb01)
        unico = not acrom and len(colores) == 1 and _mismo(colores[0], rgb01)
        if not cands:
            en_contra.append("sin_evidencia")
        if fino and n_rot < MIN_VOTOS:
            en_contra.append("fino")
        elif acrom and n_rot < MIN_VOTOS and "leyenda" not in a_favor:
            en_contra.append("acromatico")
        elif not acrom and not unico and n_rot < MIN_VOTOS:
            en_contra.append("varios_colores")
        seguro = bool(util) and not en_contra
        out.append(CapaCerteza(L, util, seguro, a_favor, en_contra, sim))
    return out
