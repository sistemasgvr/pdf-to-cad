"""Rótulos de diámetro de un PDF vectorial SIN capas ni leyenda (PURO; pedido del usuario 2026-11-03, «Southwest Gas
Combined 811 Records»: la utilidad se le asigna a mano a cada estilo en «Capas de la hoja», y ni el diámetro ni la IA
funcionaban: `recognition_grosor_mapa` solo corría con la leyenda de un mapa de Phoenix, y el grosor CAD solo con capas).

Estos registros (ArcGIS) escriben cada rótulo en piezas sueltas, con texto de verdad: `81'` `3/4"` `STL` ` `56` (largo,
diámetro, material y año de instalación), o en una sola: `95' 1/2" PE '88`, `3/4"STL`, `1-1/4"`. Aquí se juntan las
piezas y salen `RotuloMapa`, los mismos de los mapas: la asignación a su tubería, la IA y los rótulos del DXF son los de
`recognition_grosor_mapa`. Sin leyenda no se sabe qué estilo es una acometida: `acometida` siempre False.

El rótulo también dice el LARGO de la tubería (`81'`): si el texto va apartado o la línea quiebra y no queda paralelo a
ella, `por_largo` lo empareja por su largo. La relación pies/largo sale de las líneas ya leídas (no de la escala de la
hoja, que puede no ser la real): «Southwest Gas» 37 = 298 líneas a 1.43–1.48 ft/pt. Si no hay esa evidencia, no hace nada.

Los mapas con leyenda siguen por `recognition_grosor_mapa.rotulos`, sin ningún cambio.
"""
from __future__ import annotations

import bisect
import math
import re
from statistics import median
from typing import Dict, List, Optional, Tuple

from reconocimiento import recognition_grosor_mapa as G

DIAM_MIN_IN, DIAM_MAX_IN = 0.25, 144.0
LARGO_LETRAS = 15.0          # × letra: lo más lejos que puede ir un rótulo emparejado por su largo
LARGO_TOL = 0.08             # el largo escrito y el medido coinciden a ±8 %…
LARGO_TOL_FT = 2.0           # …o ±2 ft en una línea corta
LARGO_MIN_LINEAS = 5         # líneas leídas que dan la relación pies/largo
LARGO_DISPERSION = 0.05      # la mitad central de esas líneas no se aparta más que esto
HUECO_LETRAS = 3.0           # × letra: hueco máximo entre dos piezas del mismo rótulo
LINEA_LETRAS = 0.35          # × letra: desfase máximo de la línea base

MATERIALES = G.MATERIALES | {"PE", "MDPE", "POLY", "ST", "AC", "CI", "DI", "WS", "GS", "PP"}
_NUM = r"(\d+-\d+/\d+|\d+/\d+|\d{1,3}(?:\.\d+)?)"
_ANIO = r"[`'´’]\d{2}"
_MAT = "|".join(sorted(MATERIALES, key=len, reverse=True)).replace("(", r"\(").replace(")", r"\)")
RX_DIAM = re.compile(r'^\s*(?:\d{1,4}\s*\'\s*)?' + _NUM + r'\s*"\s*(.*?)\s*$')
RX_LARGO = re.compile(r"^\s*(\d{1,4})\s*'")
RX_ANIO = re.compile(r"\s*" + _ANIO + r"\s*$")
RX_PIEZA = re.compile(rf"^\s*(?:\d{{1,4}}'|(?:(?:{_MAT})\s*)?{_ANIO}|(?:{_MAT}))\s*$", re.I)


def _pulgadas(txt: str) -> float:
    if "-" in txt:
        ent, frac = txt.split("-", 1)
        return int(ent) + _pulgadas(frac)
    if "/" in txt:
        a, b = txt.split("/", 1)
        return int(a) / int(b) if int(b) else 0.0
    return float(txt)


def leer(texto: str) -> Optional[Tuple[float, str]]:
    """(pulgadas, material) de un rótulo, o None si no es de una tubería."""
    t = " ".join((texto or "").upper().split())
    m = RX_DIAM.match(t)
    if not m:
        return None
    d = _pulgadas(m.group(1))
    if not DIAM_MIN_IN <= d <= DIAM_MAX_IN:
        return None
    material = ""
    for w in RX_ANIO.sub("", m.group(2)).split():
        if w in MATERIALES:
            material = material or w
        elif w in G.NO_TUBO or w not in G.CALIFICATIVOS:
            return None                   # la camisa, un accesorio o algo que no se entiende
    return d, material


def _extremos(c) -> Tuple[float, float, float]:
    """(inicio, fin, línea base) del texto, medidos en su propio rumbo."""
    centro, largo = G._caja(c)
    d = c.dir
    u = centro[0] * d[0] + centro[1] * d[1]
    return u - largo / 2.0, u + largo / 2.0, centro[0] * d[1] - centro[1] * d[0]


def _vecinas(c, otras: List, usadas: set, sentido: int) -> List:
    """Las piezas seguidas de `c` hacia un lado, de la más cercana a la más lejana."""
    u0, u1, v = _extremos(c)
    borde, out = (u1 if sentido > 0 else u0), []
    for o, a, b, w in sorted(otras, key=lambda x: x[1] * sentido):
        if id(o) in usadas or abs(w - v) > LINEA_LETRAS * c.tam or (a < u0 if sentido > 0 else b > u1):
            continue
        hueco = (a - borde) if sentido > 0 else (borde - b)
        if hueco > HUECO_LETRAS * c.tam:
            break
        if not RX_PIEZA.match(o.texto):
            break
        out.append(o)
        borde = b if sentido > 0 else a
    return out


def _rotulo(c, antes: List, despues: List, pieza: int) -> Optional[G.RotuloMapa]:
    partes = list(reversed(antes)) + [c] + despues
    got = leer(" ".join(p.texto.strip() for p in partes))
    if got is None:
        got = leer(c.texto)               # lo de al lado no era del rótulo: vale el diámetro solo
        partes = [c]
    if got is None:
        return None
    ext = [_extremos(p) for p in partes]
    u0, u1, v = min(e[0] for e in ext), max(e[1] for e in ext), _extremos(c)[2]
    d, u = c.dir, (min(e[0] for e in ext) + max(e[1] for e in ext)) / 2.0
    centro = (u * d[0] + v * d[1], u * d[1] - v * d[0])
    return G.RotuloMapa(centro, (float(d[0]), float(d[1])), float(c.tam), u1 - u0, got[0], got[1], False,
                        " ".join(p.texto.strip() for p in partes), pieza)


def de_corridas(corridas, inicios=()) -> List[G.RotuloMapa]:
    """Los rótulos de diámetro de estas corridas de texto, con sus piezas juntas."""
    por_rumbo: Dict[Tuple[float, float], List] = {}
    for c in corridas:
        por_rumbo.setdefault((round(c.dir[0], 2), round(c.dir[1], 2)), []).append(c)
    out: List[G.RotuloMapa] = []
    for grupo in por_rumbo.values():
        otras = [(c, *_extremos(c)) for c in grupo if RX_PIEZA.match(c.texto)]
        usadas: set = set()
        for c in grupo:
            if not RX_DIAM.match(c.texto.upper()):
                continue
            antes = _vecinas(c, otras, usadas, -1)
            despues = _vecinas(c, otras, usadas, 1)
            seq = c.glifos[0].seqno if c.glifos else -1
            r = _rotulo(c, antes, despues, bisect.bisect_right(inicios, seq) if inicios else 0)
            if r is not None:
                usadas |= {id(p) for p in antes + despues}
                out.append(r)
    return out


def rotulos(page) -> List[G.RotuloMapa]:
    """Rótulos de diámetro de la hoja, en coordenadas de la hoja sin girar (como `recognition_grosor_mapa.rotulos`)."""
    from hoja import texto_pdf
    from hoja.leyenda_mapa_lectura import inicios_de_piezas
    return G.sin_miniaturas(de_corridas(texto_pdf.corridas(page), inicios_de_piezas(page) or []))


def _largo(pl) -> float:
    return sum(math.dist(a, b) for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:]))


def _pies(r) -> Optional[int]:
    m = RX_LARGO.match(r.texto)
    return int(m.group(1)) if m else None


def _relacion(lineas, suyos) -> Optional[float]:
    """Pies por unidad de largo de las líneas leídas con un rótulo que dice su largo; None sin evidencia clara."""
    v = sorted(_pies(rs[0]) / _largo(lineas[k]) for k, rs in suyos.items() if len(rs) == 1 and _pies(rs[0])
               and (lineas[k].grosor or {}).get("estado") == "leido" and _largo(lineas[k]) > 0)
    if len(v) < LARGO_MIN_LINEAS:
        return None
    m = median(v)
    return m if v[3 * len(v) // 4] - v[len(v) // 4] <= LARGO_DISPERSION * m else None


def por_largo(lineas, rots, es_acometida, pendientes=()) -> int:
    """Las líneas sin dato con el rótulo libre cercano que dice su largo: se les pone (lo mismo que un rótulo junto a
    ellas). Si dos rótulos de distinto diámetro le sirven, o una línea más cercana pide el mismo, no se pone nada."""
    lineas = [pl for pl in lineas if len(pl.pts_pdf) >= 2]
    suyos, _dudas, _alcance = G.asignar(lineas, rots, es_acometida)
    k_pies = _relacion(lineas, suyos)
    if k_pies is None:
        return 0
    ocupados = {id(r) for rs in suyos.values() for r in rs}
    libres = [r for r in rots if id(r) not in ocupados and _pies(r)]
    pedidos: Dict[int, List[Tuple[float, int]]] = {}
    for k, pl in enumerate(lineas):
        if (pl.grosor or {}).get("estado") != "sin_dato" or id(pl) in pendientes:
            continue
        medido = _largo(pl) * k_pies
        cand = []
        for r in libres:
            if abs(_pies(r) - medido) > max(LARGO_TOL_FT, LARGO_TOL * medido):
                continue
            d = min(G.P._dist_seg(r.centro, a, b) for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:]))
            if d <= LARGO_LETRAS * r.tam:
                cand.append((d, r))
        if len({r.pulg for _d, r in cand}) == 1:
            d, r = min(cand, key=lambda x: x[0])
            pedidos.setdefault(id(r), []).append((d, k))
    n = 0
    por_id = {id(r): r for r in libres}
    for rid, quien in pedidos.items():
        quien.sort()
        if len(quien) > 1 and quien[1][0] - quien[0][0] < por_id[rid].tam:
            continue                                     # dos líneas casi igual de cerca: no se sabe de cuál es
        r, pl = por_id[rid], lineas[quien[0][1]]
        pl.grosor = dict(pl.grosor, estado="leido", diam_in=r.pulg, fuente="rotulo", textos=[r.texto],
                         material=r.material, candidatos=[])
        pl.diam_in = r.pulg
        n += 1
    return n
