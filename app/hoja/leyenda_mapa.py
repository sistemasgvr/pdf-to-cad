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
  · Filas de ACOMETIDA («As-Built Tap», «Service Line»): sus trazos que nacen sobre la red
    van a la capa «Acometidas» (`acometidas_mapa`), asignada como líneas de su utilidad;
    las NOTAS del cuadro dan su diámetro y el material de la red (`diam_acometida_in`,
    `material`). La lectura del cuadro está en `leyenda_mapa_lectura`.
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
ACOMETIDA = "acometida"      # servicio de la red a un predio («As-Built Tap»): ver `acometidas_mapa`
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
# la conexión de un predio a la red: «As-Built Tap», «Application Tap», «Service Line»
# (no «Tap Sleeve»: el manguito de la toma es un accesorio)
_ACOMETIDA = re.compile(r"\bTAPS?\s*$|\bSERVICES?(\s+(LINES?|LATERALS?|CONNECTIONS?|PIPES?))?\s*$"
                        r"|ACOMETIDA|DOMICILIARI|CONEXI[OÓ]N\s+DE\s+SERVICIO")
_ROLES = (                     # orden: «Access Manhole # Symbol» es el rótulo del número
    (ANOTACION, _ANOTACION),
    (BASE, _BASE),
    (ACOMETIDA, _ACOMETIDA),
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
# notas del cuadro: «*All water taps are .75" in diameter unless otherwise noted.»,
# «*All water main material is ACP (Asbestos Cement Pipe) unless otherwise noted.»
NOTA_DIAM_ACOMETIDA = re.compile(r"""TAPS?\s+(?:ARE|IS)\s+(\d*\.?\d+)\s*(?:"|''|IN)""", re.I)
NOTA_MATERIAL = re.compile(r"MAIN\s+MATERIAL\s+IS\s+([A-Z][A-Z0-9-]*)(?:\s*\(([^)]*)\))?", re.I)
ESCALA = re.compile(r"""SCALE\s*:?\s*1\s*(?:"|''|IN(?:CH)?)\s*=\s*(\d+(?:\.\d+)?)\s*(?:'|FT|FEET)""", re.I)

MUESTRA_ANCHO = 7.0          # la muestra va a ≤ esto × tamaño de letra a la izquierda del texto
COLUMNA_TOL = 0.8            # descripciones de la misma columna: mismo inicio (± esto × tamaño)
FILAS_MIN = 3                # una columna de leyenda tiene varias filas
SALTO_COLUMNA = 4.0          # un salto mayor que esto × el paso de filas parte la columna
SIMBOLO_BANDA = 0.35         # centro del símbolo de una fila a ≤ esto × el paso de su línea media
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
    diam_acometida_in: Optional[float] = None           # nota «taps are .75" in diameter»
    material: str = ""                                   # nota «main material is ACP (…)»
    diam_acometida_in: Optional[float] = None           # nota «taps are .75" in diameter»
    material: str = ""                                   # nota «main material is ACP (…)»


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


def _color_claro(nombre: str) -> bool:
    try:
        kind, color, width, _dash, fill, *_ = json.loads(nombre[len(pdf_styles.PREFIX):])
    except Exception:
        return True
    rgb = color if color is not None else fill
    return rgb is None or min(rgb) > 0.9


def leer(doc, page) -> LeyendaMapa:
    """La leyenda de la hoja (ver el docstring del módulo); caché por documento y hoja."""
    cache = doc.__dict__.setdefault("_pdfcad_leyenda_mapa", {})
    if page.number not in cache:
        try:
            from hoja import leyenda_mapa_lectura as lectura
            ley = lectura._leer(page)
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
        elif f.rol == ACOMETIDA:              # su estilo es también el de linderos: sus
            votar(principal, None, f.texto)   # trazos van a la capa «Acometidas» (abajo)
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
    # acometidas que nacen sobre la red (`acometidas_mapa`): líneas de su utilidad en TODAS
    # las redes (pedido del usuario 2026-10-14: en alcantarillado solo salía la principal).
    # A presión el plugin parte la tubería en la T; en gravedad y conductos el import pone
    # el vértice en la principal y estructuras NULAS, sin buzón visible (`nucleo.acometidas`)
    from hoja import acometidas_mapa
    for capa, n in en_mapa.items():
        if n and acometidas_mapa.es_capa(capa):
            out[capa] = (acometidas_mapa.utilidad_de(capa), ROL_LINEAS)
    return out, ambiguas


def descripciones(ley: LeyendaMapa) -> Dict[str, List[str]]:
    """{capa virtual: descripciones de la leyenda que la usan} (para mostrarlas)."""
    from hoja import acometidas_mapa
    out: Dict[str, List[str]] = {}
    for f in ley.filas:
        capas = [_trazo_principal(f), symbol_layer(f.simbolo, f.simbolo_fuente) if f.simbolo else None]
        if f.rol == ACOMETIDA and f.utilidad and capas[0]:
            capas.append(acometidas_mapa.capa(capas[0], f.utilidad))
        for capa in capas:
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
