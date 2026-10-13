"""leyenda_mapa.py — La LEYENDA de un mapa sin capas: qué estilo y qué símbolo es qué (PURO).

Pedido del usuario (2026-10-13, mapas «Quarter Section» de Phoenix, una utilidad por PDF,
sin capas OCG): «interpretar su leyenda, reconocer las líneas por su estilo, sus buzones…
adaptarnos a cualquier escenario». El PDF trae un cuadro de leyenda con secciones
(«GENERAL», «WATER INFRASTRUCTURE», «RECLAIMED INFRASTRUCTURE», «SEWER INFRASTRUCTURE»…) y
en cada fila una MUESTRA (un trazo con su estilo, o un símbolo de la fuente) a la izquierda
de su DESCRIPCIÓN («Standard Main», «Fire Hydrant», «Access Manhole»). El texto se lee con
`texto_pdf` (la fuente Type3 no trae mapa de caracteres).

  · `leer(doc, page)` → `LeyendaMapa`: filas (descripción, sección, muestra: estilos de sus
    trazos y clave de su símbolo, y lo que significa: utilidad, rol, abandonada), la
    UTILIDAD del plano (título «WATER», encabezados), la ESCALA escrita («SCALE: 1" = 100'»)
    y la ZONA de la leyenda (sus muestras no son tuberías del mapa). Caché por documento.
  · `asignaciones(ley, en_mapa)` → {capa virtual: (utilidad, rol)}: estilo de la muestra de
    una fila de LÍNEA («Standard Main», «Fire Main»…) → líneas de su utilidad; símbolo o
    contorno de una fila de ESTRUCTURA («Access Manhole», «Water Vaults») → estructuras.
    Un estilo que la leyenda usa también para el mapa base o anotaciones no se asigna
    (`ambiguas`): lo decide el usuario.
  · `simbolos_capas(page)` → trazos virtuales (círculo de su tinta) de los símbolos que la
    leyenda describe, cada clase en su capa `pdf_styles.symbol_name`: así entran al mismo
    flujo de capas por estilo (resaltar, asignar, reconocer como estructura).
Sección → utilidad: WATER→Agua, SEWER/WASTEWATER→Alcantarillado, STORM/DRAIN→Drenaje,
GAS, ELECTRIC→Eléctrico, TELECOM/COMMUNICATION→Telecom; RECLAIMED (agua regenerada) y
GENERAL (mapa base) no son utilidades de la app. Una descripción que nombra su utilidad
(«Water Vaults», «Reclaimed Manhole») manda sobre la sección.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from hoja import pdf_styles, texto_pdf

LINEA, ESTRUCTURA, ACCESORIO, ANOTACION, BASE = "linea", "estructura", "accesorio", "anotacion", "base"
ROL_LINEAS, ROL_ESTRUCTURAS = "lineas", "buzones"      # = recognition.ROLE_LINEAS / ROLE_BUZONES

ENCABEZADO = re.compile(r"INFRASTRUCTURE|LEGEND|LEYENDA|SIMBOLOG|\bGENERAL\b")
_UTILIDAD = (                  # orden: «Reclaimed Water» es agua regenerada, no agua
    (re.compile(r"RECLAIM|RECYCL|NON.?POTABLE|REGENERAD"), None),
    (re.compile(r"SEWER|WASTEWATER|SANITARY|ALCANTARILL|DESAG|SANITARI"), "ALCANTARILLADO"),
    (re.compile(r"STORM|DRAIN|PLUVIAL|DRENAJE"), "DRENAJE"),
    (re.compile(r"\bWATER\b|POTABLE|\bAGUA\b"), "AGUA"),
    (re.compile(r"\bGAS\b"), "GAS"),
    (re.compile(r"ELECTRIC|\bPOWER\b|EL[EÉ]CTRIC"), "ELECTRICO"),
    (re.compile(r"TELECOM|COMMUNICATION|FIBER|FIBRE|TELEPHONE|TELEF"), "TELECOM"),
)
_ANOTACION = re.compile(r"\bTICS?\b|LEADER|OFFSET|REVISION|ENCASEMENT|DETAIL|FOOTPRINT|SYMBOL|#|LOCATE"
                        r"|REHAB|S[IÍ]MBOLO|R[OÓ]TULO")
_BASE = re.compile(r"\bROW\b|\bLOT\b|TRACT|EASEMENT|CENTERLINE|LIMITS?\b|\bGRID\b|MONUMENT|SEPARATION"
                   r"|CANAL|RAILROAD|PARCEL|PROPERTY|PLANT|\bAREAS?\b|BASIN|PREDIO|LOTE")
# la descripción TERMINA en el sustantivo de la red («Hydrant Main», «Water Chlorine Line»):
# es una tubería aunque nombre un accesorio
_FIN_LINEA = re.compile(r"\b(MAINS?|PIPES?|LINES?|LATERALS?|SEWERS?|TUBER[IÍ]AS?|L[IÍ]NEAS?)\s*$")
_ROLES = (                     # orden: «Access Manhole # Symbol» es el rótulo del número
    (ANOTACION, _ANOTACION),
    (BASE, _BASE),
    (LINEA, _FIN_LINEA),
    (ESTRUCTURA, re.compile(r"MANHOLE|\bMH\b|VAULTS?|CHAMBER|STRUCTURE|\bINLET|CATCH\s*BASIN|JUNCTION\s*BOX"
                            r"|BUZ[OÓ]N|C[AÁ]MARA|POZO|REGISTRO|B[OÓ]VEDA|ARQUETA")),
    (ACCESORIO, re.compile(r"VALVE|\bVLV|HYDRANT|METER|REDUCER|\bPRVS?\b|CHECK|FLUSH|ANODE|RECTIFIER|STATION"
                           r"|STORAGE|\bWELL|\bTAPS?\b|SLEEVE|CLEANOUT|\bPLUG|BLOW|PROTECTION|INTER\s*CONNECT"
                           r"|V[AÁ]LVULA|HIDRANTE|MEDIDOR")),
    (LINEA, re.compile(r"\bMAINS?\b|PIPE|\bLINE\b|LATERAL|SERVICE|OUTLET|FORCE|SEWER|CONDUIT|\bDUCT"
                       r"|TUBER[IÍ]A|L[IÍ]NEA|COLECTOR|EMISOR|MATRIZ")),
)
ABANDONADA = re.compile(r"ABANDON|\bABND|\bABAN\b|ABANDONAD")
ESCALA = re.compile(r"""SCALE\s*:?\s*1\s*(?:"|''|IN(?:CH)?)\s*=\s*(\d+(?:\.\d+)?)\s*(?:'|FT|FEET)""", re.I)

MUESTRA_ANCHO = 7.0          # la muestra va a ≤ esto × tamaño de letra a la izquierda del texto
COLUMNA_TOL = 0.8            # descripciones de la misma columna: mismo inicio (± esto × tamaño)
FILAS_MIN = 3                # una columna de leyenda tiene varias filas
DIVISOR_MIN = 4.0            # línea divisoria del cuadro: ≥ esto × tamaño del encabezado


@dataclass
class FilaMapa:
    texto: str
    seccion: str
    utilidad: Optional[str]
    rol: str
    abandonada: bool
    muestra: Tuple[float, float, float, float]          # caja de la muestra (pt de la hoja sin girar)
    estilos: Dict[str, float] = field(default_factory=dict)   # capa virtual → largo dibujado
    simbolo: Optional[Tuple] = None                      # clave `texto_pdf.Simbolo` de la muestra
    simbolo_fuente: str = ""
    letras: str = ""                                     # letras dentro de la muestra («W M», «TS»)


@dataclass
class LeyendaMapa:
    filas: List[FilaMapa]
    utilidad: Optional[str]
    escala_ft_pt: Optional[float]
    zonas: List[Tuple[float, float, float, float]]       # caja de la leyenda (sus muestras no son mapa)
    titulo: str = ""


# ── significado de una descripción ──────────────────────────────────────────
def utilidad_de(texto: str) -> Tuple[bool, Optional[str]]:
    """(¿nombra una utilidad?, cuál: None = una que no es de la app, como «Reclaimed»)."""
    up = (texto or "").upper()
    for rx, u in _UTILIDAD:
        if rx.search(up):
            return True, u
    return False, None


def rol_de(texto: str) -> str:
    up = (texto or "").upper()
    for rol, rx in _ROLES:
        if rx.search(up):
            return rol
    return ANOTACION


# ── geometría en el marco de la leyenda ─────────────────────────────────────
class _Marco:
    """Coordenadas de la leyenda: u a lo largo del texto, w hacia abajo (siguiente fila)."""

    def __init__(self, d):
        self.e = (float(d[0]), float(d[1]))
        self.n = (-self.e[1], self.e[0])

    def uw(self, p):
        return (p[0] * self.e[0] + p[1] * self.e[1], p[0] * self.n[0] + p[1] * self.n[1])

    def caja(self, r):
        pts = [self.uw(q) for q in ((r[0], r[1]), (r[2], r[1]), (r[0], r[3]), (r[2], r[3]))]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))

    def a_hoja(self, u0, w0, u1, w1):
        pts = []
        for u in (u0, u1):
            for w in (w0, w1):
                pts.append((u * self.e[0] + w * self.n[0], u * self.e[1] + w * self.n[1]))
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _color_claro(nombre: str) -> bool:
    try:
        kind, color, width, _dash, fill, *_ = json.loads(nombre[len(pdf_styles.PREFIX):])
    except Exception:
        return True
    rgb = color if color is not None else fill
    return rgb is None or min(rgb) > 0.9


def _largo(d) -> float:
    r = d["rect"]
    return max(math.hypot(r.width, r.height), 0.05)


def _dibujos(page) -> List[dict]:
    """Trazos de la hoja con su capa virtual por estilo (sin los símbolos virtuales)."""
    out = []
    for d in page.get_drawings():
        if d.get("type") in ("clip", "group") or d.get("layer"):
            continue
        nombre = pdf_styles.style_name(d)
        if nombre:
            out.append(dict(d, layer=nombre))
    return out


def _divisores(dibujos, marco, w_lo, w_hi, largo_min) -> List[float]:
    """u de las líneas del cuadro que bajan de los encabezados (separan las secciones)."""
    us = []
    for d in dibujos:
        for it in d.get("items") or ():
            if it[0] == "l":
                segs = [(it[1], it[2])]
            elif it[0] == "re":
                r = it[1]
                segs = [((r.x0, r.y0), (r.x0, r.y1)), ((r.x1, r.y0), (r.x1, r.y1)),
                        ((r.x0, r.y0), (r.x1, r.y0)), ((r.x0, r.y1), (r.x1, r.y1))]
            else:
                continue
            for a, b in segs:
                ua, wa = marco.uw(a)
                ub, wb = marco.uw(b)
                if abs(ua - ub) <= 0.3 and abs(wa - wb) >= largo_min and min(wa, wb) <= w_hi and max(wa, wb) >= w_lo:
                    us.append((ua + ub) / 2.0)
    return sorted(us)


def _paso_regular(ws: Sequence[float]) -> bool:
    if len(ws) < FILAS_MIN:
        return False
    gaps = [b - a for a, b in zip(ws, ws[1:]) if b - a > 1e-3]
    if not gaps:
        return False
    paso = sorted(gaps)[len(gaps) // 2]
    return sum(1 for g in gaps if g <= 3.2 * paso) >= 0.7 * len(gaps)


def _leer(page) -> Optional[LeyendaMapa]:
    corr = texto_pdf.corridas(page)
    corr_uw = None
    simbs = texto_pdf.simbolos(page)
    utilidad = _utilidad_del_plano(corr)
    escala = _escala(corr)
    heads = [c for c in corr if c.texto.isupper() and ENCABEZADO.search(c.texto)
             and "RECORD" not in c.texto and "PROTECTED" not in c.texto]
    if not heads:
        return LeyendaMapa([], utilidad, escala, [], "")
    dir_ = max({h.dir for h in heads}, key=lambda d: sum(1 for h in heads if h.dir == d))
    heads = [h for h in heads if h.dir == dir_]
    marco = _Marco(dir_)
    hs = sorted(h.tam for h in heads)[len(heads) // 2]
    hw = [marco.uw(h.origen)[1] for h in heads]
    hu = [(marco.uw(h.origen)[0], marco.uw(h.fin)[0], h) for h in heads]
    w_top, w_bot = min(hw) - 0.5 * hs, max(hw) + 40.0 * hs
    u_lo, u_hi = min(u for u, _f, _h in hu) - 30.0 * hs, max(f for _u, f, _h in hu) + 60.0 * hs
    labels = []
    for c in corr:
        if c.dir != dir_ or not (0.3 * hs <= c.tam <= 0.95 * hs) or len(re.findall(r"[A-Za-z]", c.texto)) < 2:
            continue
        u, w = marco.uw(c.origen)
        if w_top < w <= w_bot and u_lo <= u <= u_hi:
            labels.append((u, w, c))
    # columnas: mismo inicio de texto, varias filas a paso regular
    labels.sort(key=lambda t: t[0])
    columnas: List[List[tuple]] = []
    for t in labels:
        if columnas and abs(t[0] - columnas[-1][0][0]) <= COLUMNA_TOL * t[2].tam:
            columnas[-1].append(t)
        else:
            columnas.append([t])
    columnas = [sorted(col, key=lambda t: t[1]) for col in columnas]
    columnas = [col for col in columnas if _paso_regular([t[1] for t in col])]
    if not columnas:
        return LeyendaMapa([], utilidad, escala, [], "")
    dibujos = _dibujos(page)
    # solo lo que cae en el cuadro de la leyenda (un mapa trae decenas de miles de trazos)
    lu0 = min(col[0][0] for col in columnas) - (MUESTRA_ANCHO + 1) * hs
    lu1 = max(marco.uw(t[2].fin)[0] for col in columnas for t in col) + hs
    lw0 = min(t[1] for col in columnas for t in col) - 3 * hs
    lw1 = max(t[1] for col in columnas for t in col) + 3 * hs
    dib_uw = []
    for d in dibujos:
        b = marco.caja(tuple(d["rect"]))
        if b[2] >= lu0 and b[0] <= lu1 and b[3] >= lw0 and b[1] <= lw1:
            dib_uw.append((b, d))
    corr_uw = [(marco.uw(o.origen), o) for o in corr if o.dir == dir_]
    divs = _divisores(dibujos, marco, min(hw) - hs, max(hw) + hs, DIVISOR_MIN * hs)
    fin_col = [max(marco.uw(t[2].fin)[0] for t in col) for col in columnas]
    filas: List[FilaMapa] = []
    cajas: List[Tuple[float, float, float, float]] = []
    for k, col in enumerate(columnas):
        u0 = col[0][0]
        seccion = _seccion(u0, hu, divs)
        paso = sorted(b[1] - a[1] for a, b in zip(col, col[1:]))[(len(col) - 1) // 2]
        izq = max([fin_col[j] + 0.2 * col[0][2].tam for j in range(k) if fin_col[j] < u0] + [-1e9])
        for u, w, c in col:
            s = c.tam
            zu0, zu1 = max(u - MUESTRA_ANCHO * s, izq), u - 0.1 * s
            wc = w - 0.35 * s
            zw0, zw1 = wc - 0.5 * paso, wc + 0.5 * paso
            estilos: Dict[str, float] = {}
            caja = None
            for (bu0, bw0, bu1, bw1), d in dib_uw:
                cu, cw = (bu0 + bu1) / 2.0, (bw0 + bw1) / 2.0
                if zu0 <= cu <= zu1 and zw0 <= cw <= zw1 and bu1 - bu0 <= 1.5 * (zu1 - zu0) + 0.5:
                    estilos[d["layer"]] = estilos.get(d["layer"], 0.0) + _largo(d)
                    caja = _union(caja, (bu0, bw0, bu1, bw1))
            sim = None
            for sm in simbs:
                cu, cw = marco.uw(sm.centro)
                if zu0 <= cu <= zu1 and zw0 <= cw <= zw1 and (sim is None or sm.radio > sim.radio):
                    sim = sm
            if sim is not None:
                caja = _union(caja, marco.caja(sim.caja))
            letras = " ".join(o.texto for (ou, ow), o in corr_uw
                              if zu0 <= ou <= zu1 and zw0 <= ow - 0.35 * o.tam <= zw1)
            if caja is None:
                continue                          # una nota del cuadro, no una fila de leyenda
            nombra, u_texto = utilidad_de(c.texto)
            nombra_s, u_seccion = utilidad_de(seccion)
            filas.append(FilaMapa(c.texto.strip(), seccion, u_texto if nombra else u_seccion,
                                  rol_de(c.texto), bool(ABANDONADA.search(c.texto.upper())),
                                  marco.a_hoja(*caja), estilos,
                                  sim.clave if sim is not None else None,
                                  sim.fuente if sim is not None else "", letras))
            cajas.append(_union(caja, (u, w - s, marco.uw(c.fin)[0], w + 0.3 * s)))
    _rotulos(page, filas, simbs)
    for _u, _f, h in hu:
        hu0, hw0 = marco.uw(h.origen)
        cajas.append((hu0, hw0 - h.tam, marco.uw(h.fin)[0], hw0 + 0.3 * h.tam))
    zona = None
    for cj in cajas:
        zona = _union(zona, cj)
    zonas = [marco.a_hoja(zona[0] - hs, zona[1] - hs, zona[2] + hs, zona[3] + hs)] if zona and filas else []
    return LeyendaMapa(filas, utilidad, escala, zonas, "")


ROTULO_CON_TEXTO = 0.5       # símbolo con texto DENTRO en ≥ esto de sus apariciones: es un rótulo


def _rotulos(page, filas: List[FilaMapa], simbs) -> None:
    """Un símbolo que en el mapa lleva texto DENTRO es el RÓTULO del número de una
    estructura, no la estructura: en el alcantarillado de Phoenix «Manhole» es el hexágono
    con el número del buzón (122 de 126 con número dentro), puesto al lado del buzón
    («Standard Manhole», el círculo chico: 2 de 141). Esas filas pasan a anotación."""
    import numpy as np
    letras = np.array([g.origen for g in texto_pdf.glifos(page) if g.letra not in (None, " ")], float)
    if not len(letras):
        return
    lx, ly = letras[:, 0], letras[:, 1]
    por_clave: Dict[tuple, List] = {}
    for s in simbs:
        por_clave.setdefault((s.fuente, s.clave), []).append(s)
    for f in filas:
        if f.rol not in (ESTRUCTURA, ACCESORIO) or not f.simbolo:
            continue
        ss = por_clave.get((f.simbolo_fuente, f.simbolo), [])
        con = 0
        for s in ss:
            x0, y0, x1, y1 = s.caja
            mx, my = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
            con += bool(np.any((lx >= x0 + mx) & (lx <= x1 - mx) & (ly >= y0 + my) & (ly <= y1 - my)))
        if ss and con >= ROTULO_CON_TEXTO * len(ss):
            f.rol = ANOTACION


def _union(a, b):
    if a is None:
        return b
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _seccion(u0, hu, divs) -> str:
    """Encabezado de la sección de una columna: el de la celda del cuadro (entre líneas
    divisorias) que la contiene; sin divisorias, el encabezado más cercano."""
    def celda(u):
        izq = max([d for d in divs if d < u] + [-1e9])
        der = min([d for d in divs if d > u] + [1e9])
        return izq, der
    cu = celda(u0 + 0.01)
    for a, f, h in hu:
        if divs and celda((a + f) / 2.0) == cu:
            return h.texto
    return min(hu, key=lambda t: abs((t[0] + t[1]) / 2.0 - u0))[2].texto


def _utilidad_del_plano(corr) -> Optional[str]:
    """La utilidad del plano: la que nombran sus textos más GRANDES (el título «WATER»,
    «SEWER») y los encabezados de la leyenda. «WATER SERVICES DEPARTMENT» es el nombre
    de la oficina (sale también en los planos de alcantarillado): no cuenta."""
    puntos: Dict[str, float] = {}
    for c in corr:
        up = c.texto.upper()
        if "DEPARTMENT" in up or "SERVICES" in up or "RECORD" in up or len(up) > 40:
            continue
        nombra, u = utilidad_de(up)
        if not nombra or u is None:
            continue
        peso = c.tam * c.tam * (3.0 if ENCABEZADO.search(up) else 1.0)
        if not ENCABEZADO.search(up) and len(up.split()) > 3:
            peso *= 0.1                           # una descripción («Water Vaults»), no un título
        puntos[u] = puntos.get(u, 0.0) + peso
    return max(puntos, key=puntos.get) if puntos else None


def _escala(corr) -> Optional[float]:
    for c in corr:
        m = ESCALA.search(c.texto)
        if m:
            return float(m.group(1)) / 72.0
    return None


def leer(doc, page) -> LeyendaMapa:
    """La leyenda de la hoja (ver el docstring del módulo); caché por documento y hoja."""
    cache = doc.__dict__.setdefault("_pdfcad_leyenda_mapa", {})
    if page.number not in cache:
        try:
            ley = _leer(page)
        except Exception:
            ley = None
        cache[page.number] = ley or LeyendaMapa([], None, None, [], "")
    return cache[page.number]


def aplica(page) -> bool:
    """¿Hoja sin capas OCG con texto que hay que decodificar (mapa SIG / PDF aplanado)?"""
    return texto_pdf.necesita_decodificar(page)


# ── qué capa virtual es qué ─────────────────────────────────────────────────
def _trazo_principal(fila: FilaMapa) -> Optional[str]:
    oscuros = {n: L for n, L in fila.estilos.items() if not _color_claro(n)}
    return max(oscuros, key=oscuros.get) if oscuros else None


_OTRA_RED = ("otra red",)       # voto de una fila de red que no es de la app («Reclaimed Main»)


def asignaciones(ley: LeyendaMapa, en_mapa: Dict[str, int]) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, List[str]]]:
    """({capa: (utilidad, rol)}, {capa ambigua: descripciones}) — ver el docstring del módulo.
    `en_mapa` = trazos de cada capa virtual en la hoja (solo se asigna lo que el mapa usa).

    Votos: una fila de LÍNEA vota por el trazo principal de su muestra (el más largo, sin
    los claros: el blanco de «Hydrant Main» es su relleno); una de ESTRUCTURA por su
    símbolo (o su contorno). Las filas del mapa base y de anotaciones votan EN CONTRA de
    los trazos que usan (un estilo que también dibuja lotes no se asigna). Una red que no
    es de la app («Reclaimed», agua regenerada) no bloquea si el estilo es también de la
    utilidad DEL PLANO (en blanco y negro comparten el trazo); si no, queda ambigua."""
    votos: Dict[str, List[Tuple[object, str]]] = {}

    def votar(capa, que, texto):
        if capa:
            votos.setdefault(capa, []).append((que, texto))
    for f in ley.filas:
        principal = _trazo_principal(f)
        sym = symbol_layer(f.simbolo, f.simbolo_fuente) if f.simbolo else None
        if f.rol in (LINEA, ESTRUCTURA):
            rol = ROL_LINEAS if f.rol == LINEA else ROL_ESTRUCTURAS
            capa = principal if f.rol == LINEA else (sym or principal)
            votar(capa, (f.utilidad, rol) if f.utilidad else _OTRA_RED, f.texto)
        elif f.rol == ACCESORIO:
            votar(sym, None, f.texto)
            if not sym:                       # «Tap Sleeve»: una barra con su estilo
                votar(principal, None, f.texto)
        else:                                 # mapa base y anotaciones: todos sus trazos
            total = sum(f.estilos.values()) or 1.0
            for capa, largo in f.estilos.items():
                if not _color_claro(capa) and largo >= 0.25 * total:
                    votar(capa, None, f.texto)
            votar(sym, None, f.texto)
    out, ambiguas = {}, {}
    for capa, vs in votos.items():
        if not en_mapa.get(capa):
            continue
        si = {q for q, _t in vs if q not in (None, _OTRA_RED)}
        if not si:
            continue
        contra = any(q is None for q, _t in vs)
        otra = any(q == _OTRA_RED for q, _t in vs)
        if len(si) > 1 or otra:
            del_plano = {q for q in si if q[0] == ley.utilidad}
            si = del_plano if len(del_plano) == 1 else (si if not otra else set())
        if len(si) == 1 and not contra:
            out[capa] = next(iter(si))
        else:
            ambiguas[capa] = sorted({t for _q, t in vs})
    return out, ambiguas


def descripciones(ley: LeyendaMapa) -> Dict[str, List[str]]:
    """{capa virtual: descripciones de la leyenda que la usan} (para mostrarlas)."""
    out: Dict[str, List[str]] = {}
    for f in ley.filas:
        for capa in [_trazo_principal(f), symbol_layer(f.simbolo, f.simbolo_fuente) if f.simbolo else None]:
            if capa and f.texto not in out.setdefault(capa, []):
                out[capa].append(f.texto)
    return out


# ── símbolos de la leyenda como capas virtuales ─────────────────────────────
def symbol_layer(clave, fuente: str) -> str:
    return pdf_styles.symbol_name(fuente, clave)


def _circulo(cx, cy, r) -> List[tuple]:
    """Círculo como 4 Béziers (como lo devuelve `get_drawings`)."""
    import fitz
    k = 0.5523 * r
    P = fitz.Point
    return [("c", P(cx + r, cy), P(cx + r, cy + k), P(cx + k, cy + r), P(cx, cy + r)),
            ("c", P(cx, cy + r), P(cx - k, cy + r), P(cx - r, cy + k), P(cx - r, cy)),
            ("c", P(cx - r, cy), P(cx - r, cy - k), P(cx - k, cy - r), P(cx, cy - r)),
            ("c", P(cx, cy - r), P(cx + k, cy - r), P(cx + r, cy - k), P(cx + r, cy))]


def simbolos_capas(page) -> List[dict]:
    """Trazos virtuales de los símbolos de la hoja que la leyenda describe (ver docstring)."""
    import fitz
    doc = page.parent
    cache = doc.__dict__.setdefault("_pdfcad_simbolos_capas", {})
    if page.number in cache:
        return cache[page.number]
    out = []
    try:
        ley = leer(doc, page)
        claves = {(f.simbolo_fuente, f.simbolo) for f in ley.filas if f.simbolo}
        for s in texto_pdf.simbolos(page) if claves else ():
            if (s.fuente, s.clave) not in claves:
                continue
            r = max(s.radio, 0.3)
            cx, cy = s.centro
            out.append({"type": "s", "items": _circulo(cx, cy, r), "closePath": True,
                        "rect": fitz.Rect(cx - r, cy - r, cx + r, cy + r), "color": (0.0, 0.0, 0.0),
                        "fill": None, "width": 0.1, "dashes": "[] 0", "even_odd": False,
                        "stroke_opacity": 1.0, "fill_opacity": None, "lineCap": (0, 0, 0),
                        "lineJoin": 0, "seqno": -1, "level": 0, "layer": symbol_layer(s.clave, s.fuente),
                        "symbol": True})
    except Exception:
        out = []
    cache[page.number] = out
    return out
