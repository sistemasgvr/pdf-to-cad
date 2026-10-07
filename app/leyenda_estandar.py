"""leyenda_estandar.py — LEYENDA de la hoja según el estándar BOE (PURO, sin Qt).

Pedido del usuario 2026-10-07 (DU06 h.5, «Capas de la hoja»): un plano sin leyenda
mostraba «Este PDF no trae una leyenda de líneas», y al resaltar una capa por sus letras
no se veían las demás líneas de esa utilidad (que al importar sí salen). Con los datos
del manual «BOE CADD Standards» (City of Los Angeles, `BOE_CADD_Manual_210610.pdf`):

  · §3.1.7.1 «Utility Linetypes» (fig. 3.1.7.1-1/-2): nombre y abreviatura de cada
    utilidad (ELEC, HV ELEC, NGAS, PW, FPW, IRR, SSWR, SD, TEL, FO) y de sus estructuras
    (ELECTRICAL VAULTS, SSMH, SDMH); la utilidad PROPUESTA de ≤12" va en línea CONTINUA
    («TYP. PROP. UTIL ≤12"»: SINGLE CONT. LINE), la existente con su tipo de línea.
  · §8.1 nombre de capa DISCIPLINA-GRUPO MAYOR-grupo menor-ESTADO y §8.1.6 los códigos
    de estado (A abandonada, D existente a demoler, E existente, N nueva…).

se arma una leyenda con lo que HAY en la hoja: por utilidad, una fila por tipo de línea
(estado + letras leídas en sus líneas) y otra para sus estructuras, cada una con sus capas.
Qué capas —y, en una capa mezclada, qué trazos— son de cada utilidad lo decide `rol_capa`
igual que el reconocimiento (`recognition.classify_ocg` por el nombre; por las letras, el
reparto de `recognition.letter_uses`, ya con la decisión «Usar» del usuario aplicada por
`pdf_layers.without_letters`): lo que se resalta al hacer clic es lo que se reconocerá.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from i18n_core import N_
import pdf_layers
import recognition
import recognition_geom as geom
import recognition_letters as letters_mod

LINE, STRUCTURE = "line", "structure"

# Fig. 3.1.7.1-1/-2 «UNDERGROUND UTILITY LINETYPES»: (abreviatura, nombre en el manual,
# nombre en la app, utilidad, tokens del nombre de capa que la eligen). Sin tokens = la
# de la utilidad por defecto. Solo las que la app reconoce (oil, sludge, effluent… no).
LINETYPES: Tuple[Tuple[str, str, str, str, Tuple[str, ...]], ...] = (
    ("HV ELEC", "HIGH VOLTAGE 4160V+ ELECTRICAL", N_("Eléctrico de alta tensión (4160 V o más)"),
     "ELECTRICO", ("HV", "HVLT", "HIVT")),
    ("ELEC", "LOW VOLTAGE ELECTRICAL", N_("Eléctrico de baja tensión"), "ELECTRICO", ()),
    ("NGAS", "NATURAL GAS", N_("Gas natural"), "GAS", ()),
    ("FPW", "FIRE PROTECTION WATER", N_("Agua contra incendios"), "AGUA", ("FIRE", "FPW")),
    ("IRR", "IRRIGATION", N_("Riego"), "AGUA", ("IRRG", "IRR")),
    ("PW", "POTABLE WATER", N_("Agua potable"), "AGUA", ()),
    ("SSWR", "SANITARY SEWER", N_("Alcantarillado sanitario"), "ALCANTARILLADO", ()),
    ("SD", "STORM DRAIN", N_("Drenaje pluvial"), "DRENAJE", ()),
    ("FO", "FIBER OPTIC", N_("Fibra óptica"), "TELECOM", ("FIBR", "FIBER", "FO")),
    ("TEL", "TELEPHONE / COMM", N_("Teléfono / comunicaciones"), "TELECOM", ()),
)
# Estructuras de la misma figura (las demás utilidades: nombre genérico).
STRUCTURES = {
    "ELECTRICO": ("", "ELECTRICAL VAULTS", N_("Bóvedas eléctricas")),
    "ALCANTARILLADO": ("SSMH", "SAN. SEWER STRUCTURES", N_("Buzones de alcantarillado")),
    "DRENAJE": ("SDMH", "SD STRUCTURES", N_("Buzones de drenaje")),
}
STRUCTURE_OTHER = N_("Estructuras (bóvedas, buzones)")

# §8.1.6 «Status (phase)» → nombre en la app; orden de las filas en la leyenda.
STATUSES = {
    "E": N_("Existente"), "D": N_("Existente a demoler"), "A": N_("Abandonada"),
    "M": N_("A retirar"), "N": N_("Nueva (propuesta)"), "T": N_("Temporal"),
    "F": N_("Futura"), "X": N_("Fuera de contrato"),
}
STATUS_ORDER = "EDAMNTFX123456789"
PHASE = N_("Fase {n}")
NO_STATUS = N_("Sin estado en el nombre")

# De dónde salió el estado (para el tooltip).
FROM_NAME, FROM_XREF, FROM_LETTERS = "name", "xref", "letters"
_EXIST_TOKENS = ("EXIST", "EXST", "EXISTING")
_PROP_TOKENS = ("PROP", "PROPOSED")
_ABAND_TOKENS = ("ABND", "ABAN", "ABANDON", "ABANDONED")


@dataclass
class Fila:
    """Una entrada de la leyenda: un tipo de línea (o las estructuras) de una utilidad."""
    utilidad: str
    rol: str                                   # LINE | STRUCTURE
    estado: str = ""                           # código §8.1.6 o ""
    origen: str = ""                           # FROM_NAME | FROM_XREF | FROM_LETTERS | ""
    abbr: str = ""                             # abreviatura BOE (TEL, ELEC…)
    capas: List[str] = field(default_factory=list)       # nombres completos
    letras: List[str] = field(default_factory=list)      # letras leídas, con su caja («t», «T»)
    por_letras: bool = False                   # alguna capa entra por las letras de su línea

    @property
    def marcas(self) -> str:
        """Marcas de la muestra: «//» a demoler/abandonar, «/» abandonada (leyendas DU08/DU10)."""
        return "//" if self.estado == "D" else "/" if self.estado == "A" else ""

    @property
    def continua(self) -> bool:
        """Propuesta = línea continua (fig. 3.1.7.1-2, «TYP. PROP. UTIL»); el resto a trazos."""
        return self.estado == "N"

    @property
    def clave(self) -> tuple:
        return (self.utilidad, self.rol, self.estado, self.abbr)


@dataclass
class Grupo:
    """Una utilidad de la hoja con sus filas (líneas primero, estructuras al final)."""
    utilidad: str
    filas: List[Fila] = field(default_factory=list)

    @property
    def abbr(self) -> str:
        """Abreviatura BOE de sus líneas (la de más capas)."""
        cnt: Dict[str, int] = {}
        for f in self.filas:
            if f.rol == LINE and f.abbr:
                cnt[f.abbr] = cnt.get(f.abbr, 0) + len(f.capas)
        return max(cnt, key=lambda a: (cnt[a], a)) if cnt else ""

    @property
    def capas(self) -> List[str]:
        return list(dict.fromkeys(n for f in self.filas for n in f.capas))


# ── qué es cada capa para el reconocimiento ──────────────────────────────────
def rol_capa(L: dict, utilidad: str) -> Tuple[Optional[str], bool]:
    """Cómo entra la capa `L` (de `pdf_layers.page_layers`, ya con `without_letters`)
    en el reconocimiento de `utilidad`: (rol, por_trazo). `rol` = LINE, STRUCTURE o None;
    `por_trazo` = solo los trazos de `L["letter_paths"]` que son de esa utilidad (capa
    mezclada leída línea por línea), si no la capa entera. Igual que
    `recognition.line_selectors` (`kind_for` + `keep`)."""
    lu = L.get("letter_utilities") or ()
    if lu:
        if utilidad in lu:
            return LINE, bool(L.get("letter_paths")) and not L.get("name_utility")
        if L.get("name_utility"):
            return None, False                 # su nombre decía esta utilidad; sus letras, otra
    kind = recognition.classify_ocg(L.get("name") or "", utilidad)
    if kind == recognition.utility_line_kind(utilidad):
        return LINE, False
    if kind == "structure":
        return STRUCTURE, False
    return None, False


def es_trazo_de(L: dict, utilidad: str, path: dict) -> Optional[str]:
    """Rol del trazo `path` (de `get_drawings`) de la capa `L` para `utilidad`, o None."""
    rol, por_trazo = rol_capa(L, utilidad)
    if rol is None:
        return None
    if utilidad in (L.get("letter_utilities") or ()) and not L.get("name_utility"):
        if path.get("fill") is not None:
            return None                        # el linetype es trazo: un relleno no es línea
        if por_trazo and (L.get("letter_paths") or {}).get(letters_mod.path_key(path)) != utilidad:
            return None
    return rol


def capa_sin_lista(name: str) -> dict:
    """Capa con trazos en la hoja que NO está en la lista de capas del PDF
    (`layer_ui_configs`; DU06 h.2: `…(A2_TRIM)|V-ELEC-MANH`): no se puede apagar, pero el
    reconocimiento la toma por su nombre; aquí también."""
    return {"name": name, "short": pdf_layers.short_name(name), "path_count": 1, "on": True,
            "unlisted": True}


def _de_utilidad(L: dict) -> bool:
    return bool(L.get("letter_utilities")) or any(rol_capa(L, u)[0] for u in recognition.SUPPORTED_UTILITIES)


def capas_de_utilidad(layers: Iterable[dict]) -> Callable[[str], bool]:
    """¿La capa puede ser línea o estructura de alguna utilidad (por su nombre o por las
    letras de su línea)? Las únicas que se resaltan. Una capa que no está en `layers`
    (fuera de la lista del PDF) se juzga por su nombre."""
    layers = list(layers)
    known = {L["name"] for L in layers}
    yes = {L["name"] for L in layers if _de_utilidad(L)}
    memo: Dict[str, bool] = {}

    def quiere(name: str) -> bool:
        if name in known:
            return name in yes
        if name not in memo:
            memo[name] = bool(name) and _de_utilidad(capa_sin_lista(name))
        return memo[name]
    return quiere


def _rect_poly(pg) -> Optional[Tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) si el polígono de clip es un rectángulo alineado a los ejes."""
    if len(pg) != 4:
        return None
    xs = sorted({round(q[0], 6) for q in pg})
    ys = sorted({round(q[1], 6) for q in pg})
    return (xs[0], ys[0], xs[1], ys[1]) if len(xs) == 2 and len(ys) == 2 else None


def _recortar(path: dict, polys: list) -> Optional[dict]:
    """`geom.clip_path`, con atajo: un trazo que cae entero dentro de clips
    rectangulares (el caso común: el marco de la vista) queda tal cual."""
    if not polys:
        return path
    r = path.get("rect")
    if r is not None:
        rects = [_rect_poly(pg) for pg in polys]
        if all(b is not None and b[0] <= r.x0 and b[1] <= r.y0 and r.x1 <= b[2] and r.y1 <= b[3]
               for b in rects):
            return path
    return geom.clip_path(path, polys)


def trazos_visibles(page, capas: Optional[Callable[[str], bool]] = None) -> List[Tuple[dict, dict]]:
    """(trazo de `get_drawings`, lo que se VE de él) de cada trazo de la hoja, como los
    toma `recognition.gather_paths`: recortado por los clips del PDF (marco de la vista,
    XCLIP de un xref, el BBox de cada pieza de la hoja compuesta), sin las astillas del
    recorte ni lo que cae en una vista de perfil (`recognition.profile_view_regions`,
    aquí en la MISMA pasada). Lo que queda fuera no se pinta ni se reconoce: tampoco se
    resalta ni va a la leyenda (auditoría 2026-10-07: bóvedas de un xref recortado en
    DU06 h.3). El original sirve para decidir de qué utilidad es (`letter_paths` se
    leyó sobre él); el recortado, para dibujar. `capas`: solo esas (recortar toda la
    hoja tarda 2–4 s; así, lo que tarda leer sus trazos). Con todas las capas encendidas."""
    page_rect = page.rect
    clip_stack: Dict[int, list] = {}
    cand: List[Tuple[dict, dict]] = []
    prof: list = []
    for path in page.get_drawings(extended=True):
        lvl = int(path.get("level", 0) or 0)
        if path.get("type") == "clip":
            clip_stack = {lv: pg for lv, pg in clip_stack.items() if lv < lvl}
            clip_stack[lvl] = recognition._clip_polygon(path, page_rect)
            continue
        if path.get("type") == "group" or not path.get("items"):
            continue
        layer = path.get("layer") or ""
        is_prof = recognition.PROFILE_LAYER_TOKEN in pdf_layers.short_name(layer).upper()
        mine = capas is None or capas(layer)
        if not (mine or is_prof):
            continue
        shown = _recortar(path, [pg for lv, pg in clip_stack.items() if lv < lvl and pg])
        if shown is None:
            continue
        if is_prof:
            bb = geom._path_bbox(shown)
            if bb is not None:
                prof.append(bb)
        if not mine or (shown.get("clipped") and recognition._path_length(shown) < recognition.CLIP_SLIVER_PT):
            continue
        cand.append((path, shown))
    regions = recognition._merge_close_boxes(prof, recognition.PROFILE_REGION_PAD_PT) if prof else []
    return [(p, s) for p, s in cand if not (regions and recognition._region_hit(geom._path_bbox(s), regions))]


# ── estado y abreviatura de una capa ─────────────────────────────────────────
def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[-_ |]+", (text or "").upper().replace("~", "")) if t]


def estado_capa(L: dict, letras: Iterable[str] = ()) -> Tuple[str, str]:
    """(código de estado §8.1.6, origen). Por orden: la letra de estado del nombre NCS
    (la última suelta, sin contar la disciplina ni el paquete «__UA4»); «PROP»/«EXIST»/
    «ABND» en el nombre o, si no, en el xref; la CAJA de las letras de su línea (las
    leyendas de los planos: existente en minúscula, propuesta en MAYÚSCULA)."""
    name = L.get("name") or ""
    xref, _, short = name.rpartition("|")
    base = recognition.standard_short_name(short).partition("__")[0]
    toks = _tokens(base)
    for i in range(len(toks) - 1, 0, -1):          # el 1.º token es la disciplina
        tk = toks[i]
        if len(tk) == 1 and (tk in STATUSES or tk.isdigit()):
            return tk, FROM_NAME
    for source, origin in ((toks, FROM_NAME), (_tokens(xref), FROM_XREF)):
        if any(tk in _ABAND_TOKENS for tk in source):
            return "A", origin
        if any(tk in _PROP_TOKENS for tk in source):
            return "N", origin
        if any(tk in _EXIST_TOKENS for tk in source):
            return "E", origin
    alpha = [x for x in letras if any(c.isalpha() for c in x)]
    if alpha and all(x == x.upper() for x in alpha):
        return "N", FROM_LETTERS
    if alpha and all(x == x.lower() for x in alpha):
        return "E", FROM_LETTERS
    return "", ""


def abbr_capa(L: dict, utilidad: str) -> str:
    """Abreviatura BOE (fig. 3.1.7.1) de una capa de líneas de `utilidad`."""
    toks = set(_tokens(recognition.standard_short_name(L.get("name") or "")))
    fallback = ""
    for abbr, _en, _es, util, tokens in LINETYPES:
        if util != utilidad:
            continue
        if tokens and toks & set(tokens):
            return abbr
        if not tokens and not fallback:
            fallback = abbr
    return fallback


def letras_capa(L: dict, utilidad: str) -> List[str]:
    """Letras del linetype leídas en la capa que son de `utilidad`, con su caja."""
    raw = L.get("letter_raw") or {}
    out = []
    codes = list(L.get("read_codes") or ())
    label = (L.get("letter_codes") or {}).get(utilidad)
    if label:
        codes += [c.strip() for c in label.split("·")]
    for code in codes:
        if letters_mod.code_utility(code) != utilidad:
            continue
        txt = raw.get(code) or code
        if txt not in out:
            out.append(txt)
    return out


# ── la leyenda ───────────────────────────────────────────────────────────────
def _orden_estado(code: str) -> int:
    i = STATUS_ORDER.find(code) if code else -1
    return i if i >= 0 else len(STATUS_ORDER)


def leyenda(layers: Iterable[dict], utilidades: Optional[Iterable[str]] = None) -> List[Grupo]:
    """Leyenda de la hoja: un `Grupo` por utilidad con trazos en ella (en el orden de
    «Capas del plano»), y en cada uno una `Fila` por (estado, abreviatura) de sus líneas
    + una de sus estructuras. Solo capas con trazos en la hoja (`path_count`)."""
    utils = [u for u in (utilidades or recognition.SUPPORTED_UTILITIES)]
    order = [k for k, _label in pdf_layers.UTILITIES if k in utils] + [
        u for u in utils if u not in dict(pdf_layers.UTILITIES)]
    grupos: List[Grupo] = []
    layers = [L for L in layers if int(L.get("path_count") or 0) > 0]
    for u in order:
        filas: Dict[tuple, Fila] = {}
        for L in layers:
            rol, _por_trazo = rol_capa(L, u)
            if rol is None:
                continue
            if rol == STRUCTURE:
                f = filas.setdefault((u, STRUCTURE), Fila(u, STRUCTURE, abbr=STRUCTURES.get(u, ("",))[0]))
            else:
                letras = letras_capa(L, u)
                estado, origen = estado_capa(L, letras)
                abbr = abbr_capa(L, u)
                f = filas.setdefault((u, LINE, estado, abbr), Fila(u, LINE, estado, origen, abbr))
                if origen and f.origen != FROM_NAME:
                    f.origen = origen if f.origen in ("", FROM_LETTERS) else f.origen
                f.letras += [x for x in letras if x not in f.letras]
                f.por_letras = f.por_letras or u in (L.get("letter_utilities") or ())
            f.capas.append(L["name"])
        if filas:
            rows = sorted(filas.values(), key=lambda f: (f.rol == STRUCTURE, _orden_estado(f.estado), f.abbr))
            grupos.append(Grupo(u, rows))
    return grupos


def nombre_estado(code: str) -> str:
    """Clave (sin traducir) del nombre de un estado; las fases llevan `{n}`."""
    if code and code.isdigit():
        return PHASE
    return STATUSES.get(code, NO_STATUS)


def linetype(abbr: str) -> Optional[Tuple[str, str]]:
    """(nombre en el manual, nombre en la app sin traducir) de una abreviatura BOE."""
    for a, en, es, _u, _t in LINETYPES:
        if a == abbr:
            return en, es
    for a, en, es in STRUCTURES.values():
        if a and a == abbr:
            return en, es
    return None
