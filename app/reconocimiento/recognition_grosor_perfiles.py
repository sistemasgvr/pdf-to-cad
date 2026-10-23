"""recognition_grosor_perfiles.py — lo que dicen las VISTAS DE PERFIL de los laterales (PURO; ver
`recognition_grosor`).

Pedido del usuario 2026-10-22 («ayudándonos de toda la información posible que esté disponible en
el PDF»). En DU06 la planta casi no rotula el agua, el gas ni el alcantarillado; lo dicen los
PERFILES de cada lateral («CB-208 LATERAL PROFILE»): el eje horizontal es la ESTACIÓN a lo largo del
lateral (STA 1+00.00 = el eje de la principal, STA 1+70.21 = el sumidero) y cada tubería que lo
cruza está dibujada en su estación con su rótulo («EX. 4" GAS, SCG», «PROP. 8" WATER, DWPWS»);
el propio lateral, «L=65.54', 18" RCP SD».

`leer` arma, por hoja, una `PerfilLateral` por vista: su nombre (el del título), la estación del
eje de la principal (la menor de sus cotas «STA n+nn.nn» de arriba) y su posición (la línea base
de ese texto vertical), la escala (HORIZ: 1"=20'), el diámetro del lateral y los CRUCES: cada
rótulo de la vista con su guía, a la distancia (pies) del eje de la principal donde cae su
punta, y si es existente, propuesta o abandonada. Llevarlo a la planta lo hace
`recognition_grosor_cruces`, con todas las utilidades.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from reconocimiento.recognition_grosor_texto import MATERIAL_UTIL, nombres_de

Pt = Tuple[float, float]

RX_STA = re.compile(r"^\s*STA\s+(\d+)\s*\+\s*(\d+(?:\.\d+)?)")
RX_HORIZ = re.compile(r"HORIZ\.?\s*:?\s*1\s*(?:\"|”|'')\s*=\s*(\d+(?:\.\d+)?)\s*(?:'|’)")
RX_TITULO = re.compile(r"\bCB\s*(?:#\s*)?-?\s*\d+(?:\.\d+)?\s+LATERAL\b")
RX_LARGO = re.compile(r"\bL\s*=\s*\d")
RX_ABANDONADA = re.compile(r"\b(ABND|ABAND|ABANDONED|TBA)\b")
RX_EXISTENTE = re.compile(r"^\s*(EX|EXIST|EXISTING)\b")
RX_PROPUESTA = re.compile(r"^\s*(PROP|PROPOSED|NEW)\b")
CADENA_TOL_PIES = 2.0          # dos cotas de la misma vista: su separación = la de sus estaciones ±esto
MARGEN_ANTES_PIES = 8.0        # una vista va de su principal (−esto) …
MARGEN_DESPUES_PIES = 15.0     # … a su última cota (+esto)
CRUCE_MIN_PIES = 1.5           # un cruce pegado al eje de la principal es la propia principal
CRUCE_MISMO_PIES = 1.5         # dos puntas de la misma guía así de cerca = el mismo cruce


@dataclass
class Cruce:
    utilidad: str
    diam_in: float
    texto: str
    pies: float                    # del eje de la principal, a lo largo del lateral
    estado: str = ""               # E existente, N propuesta, A abandonada (lo que dice el rótulo); "" = no lo dice


@dataclass
class PerfilLateral:
    nombre: str                    # «CB-208»
    px_por_pie: float              # escala horizontal de la vista (px de la vista por pie)
    largo_pies: float              # del eje de la principal a la última cota (el sumidero)
    diam_in: Optional[float] = None    # el del propio lateral («L=65.54', 18" RCP SD»)
    texto: str = ""
    cruces: List[Cruce] = field(default_factory=list)
    planta_px_por_pie: float = 0.0     # escala de la PLANTA (la pone `recognize_page`)


def escala_horizontal(lineas, zoom: float) -> Optional[float]:
    """px por pie de la escala horizontal de los perfiles («HORIZ: 1"=20'»), o None."""
    for t, _bb, _tam, _d in lineas:
        m = RX_HORIZ.search(t.upper())
        if m and float(m.group(1)) > 0:
            return 72.0 * zoom / float(m.group(1))
    return None


def estado_de(texto: str) -> str:
    t = texto.upper()
    if RX_ABANDONADA.search(t):
        return "A"
    if RX_EXISTENTE.search(t):
        return "E"
    if RX_PROPUESTA.search(t):
        return "N"
    return ""


def _dentro(q: Pt, regiones) -> bool:
    return any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in regiones)


def _centro(bb) -> Pt:
    return ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)


def _cotas(lineas, regiones):
    """[(x de la línea base, estación en pies)] de las cotas «STA n+nn.nn» verticales (de abajo
    arriba: su línea base es el lado derecho de su caja) dentro de los perfiles."""
    out = []
    for t, bb, _tam, d in lineas:
        m = RX_STA.match(t.upper())
        if not m or abs(d[0]) > 0.05 or d[1] > -0.95 or not _dentro(_centro(bb), regiones):
            continue
        out.append((bb[2], float(m.group(1)) * 100.0 + float(m.group(2))))
    return sorted(out)


def _vistas(cotas, ppf: float):
    """Las cotas agrupadas por vista: dos seguidas son de la misma si su separación es la de sus
    estaciones a la escala (las vistas van una al lado de la otra y todas empiezan en 1+00)."""
    vistas: List[List[Tuple[float, float]]] = []
    for x, s in cotas:
        if vistas:
            xa, sa = vistas[-1][-1]
            if s > sa and abs((x - xa) - (s - sa) * ppf) <= CADENA_TOL_PIES * ppf:
                vistas[-1].append((x, s))
                continue
        vistas.append([(x, s)])
    return vistas


def _mas_cercana(x: float, rangos) -> Optional[int]:
    """La vista (índice) a la que pertenece un texto por su x: la que lo contiene o, si no, la
    más cercana (el «L=…» y el título pueden ir a un lado del dibujo). Empate: ninguna."""
    ds = sorted((max(lo - x, x - hi, 0.0), k) for k, (lo, hi) in enumerate(rangos))
    if not ds or (len(ds) > 1 and ds[1][0] - ds[0][0] < 1.0):
        return None
    return ds[0][1]


def leer(lineas: Sequence, rots, puntas, regiones, zoom: float) -> List[PerfilLateral]:
    """Los perfiles de laterales de la hoja. `lineas` = `lineas_texto` (px); `rots`/`puntas` = los
    rótulos de diámetro DENTRO de los perfiles y sus guías; `regiones` = cajas de los perfiles."""
    if not regiones:
        return []
    ppf = escala_horizontal(lineas, zoom)
    if not ppf:
        return []
    vistas = [v for v in _vistas(_cotas(lineas, regiones), ppf) if v[-1][1] - v[0][1] >= 3.0]
    if not vistas:
        return []
    # el dibujo de cada vista: de su principal a su última cota
    rangos = [(v[0][0], v[0][0] + (v[-1][1] - v[0][1]) * ppf) for v in vistas]
    nombres: List[set] = [set() for _ in vistas]
    for t, bb, _tam, _d in lineas:
        if RX_TITULO.search(t.upper()) and nombres_de(t) and _dentro(_centro(bb), regiones):
            k = _mas_cercana(_centro(bb)[0], rangos)
            if k is not None:
                nombres[k].add(nombres_de(t)[0])
    perfiles: List[Optional[PerfilLateral]] = [
        PerfilLateral(next(iter(n)), ppf, v[-1][1] - v[0][1]) if len(n) == 1 else None
        for v, n in zip(vistas, nombres)]
    largos: List[set] = [set() for _ in vistas]
    for r in rots:
        c = _centro(r.bbox)
        if RX_LARGO.search(r.texto.upper()):
            k = _mas_cercana(c[0], rangos)
            if k is not None and perfiles[k] is not None:
                largos[k].add((r.pulg, r.texto))
            continue
        utils = (r.utilidad,) if r.utilidad else MATERIAL_UTIL.get(r.material, ())
        if len(utils) != 1 or utils[0] == "DRENAJE":
            continue          # de qué utilidad no se sabe, o es la principal / otro drenaje
        for rr, _cad, p in puntas:
            if rr is not r:
                continue
            for k, (v, pv) in enumerate(zip(vistas, perfiles)):
                x0 = v[0][0]
                lo, hi = x0 - MARGEN_ANTES_PIES * ppf, rangos[k][1] + MARGEN_DESPUES_PIES * ppf
                if pv is None or not lo <= p[0] <= hi:
                    continue
                pies = (p[0] - x0) / ppf
                if CRUCE_MIN_PIES <= pies <= pv.largo_pies + 2.0 and not any(
                        c.texto == r.texto and abs(c.pies - pies) < CRUCE_MISMO_PIES for c in pv.cruces):
                    pv.cruces.append(Cruce(utils[0], r.pulg, r.texto, round(pies, 2), estado_de(r.texto)))
    out = []
    for pv, ls in zip(perfiles, largos):
        if pv is None:
            continue
        if len({d for d, _t in ls}) == 1:
            pv.diam_in, pv.texto = next(iter(ls))
        out.append(pv)
    return out


_DE_HOJA: dict = {}


def de_hojas(fuentes: Sequence[Tuple[str, int]]) -> List[PerfilLateral]:
    """Los perfiles de laterales de las HOJAS DE ORIGEN de una hoja compuesta (pedido del usuario
    2026-10-22: la compuesta toma solo la planta de cada hoja y sus perfiles quedan fuera). Un
    perfil no tiene coordenadas de la planta: su nombre («CB-208») y sus distancias en pies sirven
    igual en la compuesta. Cada hoja se lee una vez por proceso (`_DE_HOJA`, por archivo, fecha y
    hoja); un nombre que dos hojas dibujan distinto no se usa."""
    import os
    import fitz
    from hoja import pdf_styles
    from reconocimiento import recognition as rec
    from reconocimiento import recognition_grosor as grosor
    por_nombre: dict = {}
    dudosos = set()
    for path, pagina in dict.fromkeys((str(p), int(k)) for p, k in fuentes or ()):
        try:
            clave = (os.path.abspath(path), os.path.getmtime(path), pagina)
        except OSError:
            continue
        if clave not in _DE_HOJA:
            with fitz.open(path) as doc, pdf_styles.lectura_unica(doc):
                page = doc[pagina]
                m = page.rotation_matrix
                px = (lambda q, m=m: (float((fitz.Point(q) * m).x), float((fitz.Point(q) * m).y)))
                regiones = []
                for x0, y0, x1, y1 in rec.profile_view_regions(page, None):
                    cs = [px((x0, y0)), px((x1, y0)), px((x1, y1)), px((x0, y1))]
                    regiones.append((min(c[0] for c in cs), min(c[1] for c in cs),
                                     max(c[0] for c in cs), max(c[1] for c in cs)))
                _DE_HOJA[clave] = (grosor.leer_hoja(page, px, 1.0, "DRENAJE", (), perfiles=regiones).perfiles
                                   if regiones else [])
        for pv in _DE_HOJA[clave]:
            otro = por_nombre.get(pv.nombre)
            if otro is not None and (otro.diam_in, [(c.utilidad, c.diam_in, c.pies) for c in otro.cruces]) != \
                    (pv.diam_in, [(c.utilidad, c.diam_in, c.pies) for c in pv.cruces]):
                dudosos.add(pv.nombre)
            por_nombre.setdefault(pv.nombre, pv)
    return [pv for n, pv in por_nombre.items() if n not in dudosos]
