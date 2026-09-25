"""recognition.py — Reconocimiento OCG de utilidades en una hoja PDF (puro, sin Qt).

Perfiles actuales: eléctricas subterráneas, drenaje, agua y alcantarillado, con sus
estructuras OCG.
No toca config.LAYER_TOKENS ni el modelo de pipes de la app. Devuelve un
RecognitionResult para la vista previa y para importar al editor.

Este módulo decide QUÉ paths entran (por capa OCG y roles confirmados por el
usuario) y convierte coordenadas PDF → píxeles del lienzo. La reconstrucción
geométrica (guiones → corridas → nodos → polilíneas con sus quiebres) vive en
`recognition_geom.py`, puro y testeado con PDFs sintéticos y con el DU06.
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import fitz

# Raíz del repo en path (app/ suele estar sola en sys.path vía main.py).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import vector_pipeline as VP
import recognition_geom as geom
import routes as routes_mod
from sheet_crops import page_rect as crop_page_rect, drawing_polygon

# Tokens locales — NO modificar config.LAYER_TOKENS del export.
# Orden: más específico primero.
RECOGNITION_LAYER_TOKENS: Sequence[Tuple[str, str]] = (
    ("C-ELEC-VALT", "structure"),
    ("U-PROP-ESFV-ELEC", "structure"),
    ("V-ELEC-", "structure"),
    ("C-ELEC-OVHD", "elec_ovhd"),
    ("C-ELEC-UNGD", "elec_ungd"),
)

UTILITY_HINT = "ELECTRICO"
SUPPORTED_UTILITIES = ("ELECTRICO", "DRENAJE", "AGUA", "ALCANTARILLADO")
# Selección por defecto al abrir un PDF (la de siempre). Agua y Alcantarillado se
# marcan a mano en el paso «Capas de la hoja»: así activarlos no cambia lo que ya
# se importaba.
DEFAULT_UTILITIES = ("ELECTRICO", "DRENAJE")
UTILITY_LINE_KINDS = {
    "ELECTRICO": "elec_ungd",
    "DRENAJE": "drain_ungd",
    "AGUA": "water_ungd",
    "ALCANTARILLADO": "sewer_ungd",
}
# Nombre visible de cada perfil (textos de la UI: selector, progreso, preview).
UTILITY_LABELS = {"ELECTRICO": "Eléctrico", "DRENAJE": "Drenaje", "AGUA": "Agua",
                  "ALCANTARILLADO": "Alcantarillado"}
DRAW_KINDS = frozenset(UTILITY_LINE_KINDS.values())
# Reglas del núcleo geométrico que activa cada perfil. El eléctrico usa las de
# siempre (sin opciones): las correcciones de drenaje no lo tocan.
UTILITY_GEOM_OPTIONS = {
    "DRENAJE": geom.GeomOptions(separate_vaults=True, nearest_vault=True, absorb_inside_runs=True),
    # Agua: el núcleo de siempre + unir primero las puntas que el PDF dibuja unidas.
    "AGUA": geom.GeomOptions(join_touching_ends=True, gap_turn_blocks=True,
                             markers_on_curves=True),
    # Alcantarillado (gravedad, buzones como el drenaje; acometidas con quiebre y
    # barras sobre curvas como el agua). Elegidas con la auditoría de los 4 PDFs
    # (71 hojas): sin reglas quedaban 22 tramos sin tinta; con las de drenaje, 19;
    # con las de agua, 11; con ambas, 8 — y con el anillo del buzón fuera de la
    # línea (`RING_VAULT_UTILITIES`), 0. `polygon_circles`: ese anillo es un
    # polígono de 39 lados y el buzón es CIRCULAR, no un rectángulo girado.
    "ALCANTARILLADO": geom.GeomOptions(separate_vaults=True, nearest_vault=True,
                                       absorb_inside_runs=True, join_touching_ends=True,
                                       gap_turn_blocks=True, markers_on_curves=True,
                                       polygon_circles=True, precise_junctions=True,
                                       continuation_before_vault=True),
}
# Perfiles que reconocen UNA sola vez una capa repetida por otro xref (`duplicate_ocgs`).
DEDUP_OCG_UTILITIES = frozenset({"DRENAJE"})
# Perfiles cuya capa de LÍNEA también dibuja el anillo del buzón (alcantarillado:
# el xref de la red existente traza el contorno del manhole en C-SSWR-UNGD-E,
# un círculo de ~18 pt alrededor del símbolo V-SSWR-MANH). Ese anillo es
# contorno de estructura, no tubería (`ring_symbol_paths`): sin esto salían 156
# «tuberías» circulares en los 4 PDFs y las líneas saltaban sin tinta hasta él.
RING_VAULT_UTILITIES = frozenset({"ALCANTARILLADO"})
RING_MIN_R_PT = 3.0          # radio del anillo del buzón (DU06/DU10/DU08/LABOE: 8.9–10.8 pt)
RING_MAX_R_PT = 25.0
RING_MIN_SWEEP_DEG = 270.0   # cubre casi toda la vuelta (un codo de la línea no pasa de ~120°)
RING_MIN_POINTS = 8
# Tubería dibujada como CONTORNO (rectángulo cerrado delgado) en la capa de la
# línea: DU06 h.4 `PROP_SEWER_PIPE_ALGN|C-SSWR-UNGD-N` es un solo rectángulo de
# 3.6 × 210 pt (1 ft de ancho a 1"=20') — salía como una polilínea que daba la
# vuelta al rectángulo. Su centerline es el EJE: la mediana de los dos lados
# largos, que los vectores definen exactamente (`outline_axis_paths`).
OUTLINE_AXIS_UTILITIES = frozenset({"ALCANTARILLADO"})
OUTLINE_MAX_WIDTH_PT = 8.0    # lado corto (≈2 ft a 1"=20')
OUTLINE_MIN_ASPECT = 6.0      # largo / ancho
ROLE_LINEAS = "lineas"
ROLE_BUZONES = "buzones"
ROLE_IGNORAR = "ignorar"
# Longitud mínima de una polilínea dibujable (pt PDF) — compatibilidad de API.
MIN_CHAIN_LEN_PT = 8.0
# Un trazo que tras recortarlo por un clip mide menos que esto es una astilla del
# corte (borde de una pieza de la hoja compuesta, marco de vista): se descarta.
CLIP_SLIVER_PT = 1.5
# Token NCS de capa que marca una VISTA DE PERFIL (estación/elevación, escala
# vertical distinta de la horizontal): p.ej. `C-PROF-GRID-MINR/MAJR`,
# `D-PROF-TEXT`. Algunas hojas reutilizan el MISMO nombre de capa de la
# centerline de una utilidad para dibujar el símbolo de tubería en corte
# dentro de esos perfiles (DU06 hojas UD-215/216 «OFFSET MANHOLE PROFILES»:
# `C-STRM-UNGD-N` ahí dibuja el óvalo con textura de la tubería en sección,
# no una línea de planta) — sin esto, el reconocedor lo toma por una ruta más
# y la importaría con coordenadas mezclando estación y elevación a escalas
# distintas. `profile_view_regions` recorta las cajas donde aparece esa
# grilla (con el MISMO stack de clips que `gather_paths`, así una hoja mixta
# como DU06 h.3/4 —perfiles arriba, planta abajo— solo excluye los perfiles)
# y `gather_paths` descarta ahí cualquier trazo de línea o bóveda.
PROFILE_LAYER_TOKEN = "PROF"
PROFILE_REGION_PAD_PT = 15.0   # margen alrededor de la grilla de perfil
# Distancia máx. (px lienzo) para proyectar una bóveda sobre una pipe.
VAULT_SNAP_PX = 90.0
# No duplicar vértice si ya hay uno cerca (px).
VAULT_NEAR_VERT_PX = 10.0


@dataclass
class RecognizedPolyline:
    layer_ocg: str
    utility_hint: str
    pts_pdf: list  # [(x, y), ...] en pixeles del pixmap a `zoom`
    kind: str      # elec_ungd | drain_ungd | water_ungd | sewer_ungd | elec_ovhd | structure
    # Tipo de cada vértice (mismo largo que pts_pdf): end | corner | bend |
    # junction | tee | vault | curve. Lo usa el import para decidir qué
    # vértices son cajas reales y cuáles solo quiebres (estructura oculta).
    kinds: list = field(default_factory=list)
    # Utilidad ABANDONADA (capa de estado «-A», linetype «──/── e ──»): se
    # importa como pipe con "ab" = True, igual que la casilla «Abandonado».
    abandoned: bool = False
    # Ruta (strokes): varias polilíneas de la misma capa unidas de frente.
    # route_id se numera por capa; n_segments=1 si no se unió nada.
    route_id: int = 0
    n_segments: int = 1
    # Codos: índice del vértice «fillet» (esquina = intersección de tangentes) →
    # {"a", "b": puntos de tangencia (px), "center": (px), "r_px": radio}. El
    # arco es el del PDF (círculo ajustado a sus vértices); en el editor es la
    # estructura CV con `radius_ft`, como en el flujo manual.
    fillets: dict = field(default_factory=dict)


@dataclass
class RecognitionResult:
    utility: str
    page_index: int
    scale_ft_per_pt: float
    polylines: List[RecognizedPolyline] = field(default_factory=list)
    ocg_summary: list = field(default_factory=list)  # dicts
    warnings: List[str] = field(default_factory=list)
    # Capas que el usuario ocultó en el paso «Capas de la hoja»: no se reconocen.
    hidden_ocgs: List[str] = field(default_factory=list)
    # Centroides/nodos de bóvedas (px lienzo), listos para insertar como vértices/CAJA.
    vault_pts: List[Tuple[float, float]] = field(default_factory=list)
    # Roles confirmados por el usuario (nombres OCG completos).
    layer_roles: dict = field(default_factory=dict)
    vaults_snapped: int = 0
    vaults_skipped: int = 0
    # Rutas (buena continuación). `polylines` es la variante activa; las dos
    # listas permiten deshacer la unión en el preview sin reabrir el PDF.
    join_routes: bool = True
    n_routes: int = 0
    n_segments_total: int = 0
    polylines_joined: List[RecognizedPolyline] = field(default_factory=list)
    polylines_raw: List[RecognizedPolyline] = field(default_factory=list)
    # QA del núcleo geométrico (todo en px del lienzo):
    coverage: float = 1.0                                   # fracción de guiones cubiertos
    uncovered_px: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    offpattern_px: List[List[Tuple[float, float]]] = field(default_factory=list)  # leaders, flechas…
    vault_orphans_px: List[Tuple[float, float]] = field(default_factory=list)      # bóvedas sin línea
    # Geometría real de cada bóveda (px del lienzo + medidas en pies): dicts con
    # center, corners (4 puntos o None si circular), shape, width_ft, length_ft,
    # angle_deg, layer (OCG), orphan (sin línea que la atraviese).
    vaults_geo: List[dict] = field(default_factory=list)

    @property
    def drawable(self) -> List[RecognizedPolyline]:
        return [p for p in self.polylines if p.kind in DRAW_KINDS and p.pts_pdf]


def utility_label(key: str) -> str:
    """«Eléctrico», «Drenaje», «Agua»… (la clave tal cual si no es un perfil)."""
    return UTILITY_LABELS.get((key or "").upper(), key)


def utilities_label(keys) -> str:
    """Selección → texto: «Eléctrico», «Eléctrico y Drenaje», «Eléctrico, Drenaje y Agua»."""
    names = [utility_label(k) for k in keys]
    if len(names) <= 1:
        return names[0] if names else utility_label(UTILITY_HINT)
    return ", ".join(names[:-1]) + " y " + names[-1]


def normalize_utilities(value=None) -> tuple[str, ...]:
    """Normaliza una selección de reconocimiento y conserva el orden visual."""
    if value is None:
        return DEFAULT_UTILITIES
    if isinstance(value, str):
        value = (value,)
    selected = {str(item).strip().upper() for item in value if item}
    result = tuple(key for key in SUPPORTED_UTILITIES if key in selected)
    return result or (UTILITY_HINT,)


def recognition_choices(available=()) -> list[tuple[tuple[str, ...], str]]:
    """Opciones visibles para el selector según las capas presentes."""
    present = {str(item).upper() for item in available}
    supported = tuple(key for key in SUPPORTED_UTILITIES if not present or key in present)
    if len(supported) >= 2:
        return [(supported, utilities_label(supported))] + [
            ((key,), "Solo " + utility_label(key)) for key in supported]
    key = supported[0] if supported else UTILITY_HINT
    return [((key,), utility_label(key))]


def utility_line_kind(utility: str = UTILITY_HINT) -> str:
    """Kind interno de la centerline para una utilidad reconocible."""
    key = (utility or UTILITY_HINT).strip().upper()
    return UTILITY_LINE_KINDS.get(key, UTILITY_LINE_KINDS[UTILITY_HINT])


# Disciplinas de NIVEL 1 del estándar BOE / NCS (BOE CADD Standards §8.1.3).
# J, K, N, U, Y: «Not Used».
BOE_DISCIPLINES = frozenset("ABCDEFGHILMOPQRSTVWXZ")
_LEVEL2_DISC = re.compile(r"^([A-Z])[A-Z]-")


def standard_short_name(ocg: Optional[str]) -> str:
    """Nombre corto de la capa (sin el xref) llevado a la forma BÁSICA del
    estándar BOE/NCS para clasificarla: mayúsculas, sin el relleno «~» de los
    grupos de menos de 4 letras (§8.1.4: `C-GAS~-…` = `C-GAS-…`) y sin la letra
    de subconjunto de la disciplina (nivel 2, §1.3.1: `CU-STRM-…` Civil
    Utilities = `C-STRM-…`)."""
    short = (ocg or "").split("|")[-1].strip().upper().replace("~", "")
    m = _LEVEL2_DISC.match(short)
    if m and m.group(1) in BOE_DISCIPLINES:
        short = m.group(1) + short[2:]
    return short


# Líneas de drenaje pluvial del estándar BOE: C-STRM-UGND («Storm sewer:
# underground»), C-STRM-PIPE(-RCON/-CMTL…) («piping»); y la variante UNGD de
# los planos del APDU (DU06/DU08/DU10).
_STRM_LINE = re.compile(r"^C-STRM-(?:UNGD|UGND|PIPE)(?:-|_|$)")
# Geometría auxiliar o anotación dentro de esas capas: camisa, muros,
# estructuras, perfil, estacionado, texto, patrones, contornos.
_STRM_NOT_LINE = ("WALL", "STRC", "CASE", "MHOL", "HWAL", "PROF", "STAN", "TEXT",
                  "ANNO", "IDEN", "PATT", "OTLN", "DIAG", "CNTR")


def classify_ocg(ocg: Optional[str], utility: str = UTILITY_HINT) -> Optional[str]:
    """Nombre OCG → kind de reconocimiento para ``utility``, o ``None``.

    Los perfiles solo clasifican capas. Toda la reconstrucción geométrica se
    mantiene compartida en :mod:`recognition_geom`. El nombre se normaliza al
    estándar BOE/NCS (`standard_short_name`) antes de mirarlo.
    """
    if not ocg:
        return None
    short = standard_short_name(ocg)
    up = ((ocg.rsplit("|", 1)[0] + "|") if "|" in ocg else "").upper() + short
    utility = (utility or UTILITY_HINT).strip().upper()
    if utility == "AGUA":
        return _classify_water(short)
    if utility == "ALCANTARILLADO":
        return _classify_sewer(short)
    if utility == "DRENAJE":
        if not any(token in short for token in ("STRM", "STORM", "DRAN", "DRAIN")):
            return None
        # Estructuras reales de drenaje. UNGD-STRC y UNGD-WALL son geometría
        # auxiliar del conducto y no deben atraer ni crear buzones.
        # BOE: C-STRM-MHOL («manhole»), C-STRM-HWAL («headwall»), C-STRM-STRC.
        if (short.startswith(("V-STRM-MANH", "V-STRM-CBSN", "V-STRM-DRAN"))
                or short.startswith(("C-STRM-CTCH-BASN", "C-STRM-STRC", "C-STRM-MHOL", "C-STRM-HWAL"))):
            return "structure"
        # «-NPLT» es solo un sufijo del xref: si está en el PDF, se imprime y es
        # una línea de drenaje real (DU06 h.4: el lateral «sd» a (560, 1020)
        # vive en C-STRM-UNGD-E-NPLT y quedaba sin reconocer).
        # «-CASE» = rectángulo de la camisa (encasement) alrededor del tubo
        # (DU08 h.43): contorno auxiliar como «-WALL», no centerline.
        if (("C-STRM-UNGD-" in short or _STRM_LINE.match(short))
                and not any(token in short for token in _STRM_NOT_LINE)):
            return utility_line_kind(utility)
        return None
    if "TELE" in up or "C-TELE" in up:
        return None
    # Muros del ducto (doble línea del banco): geometría auxiliar, no centerline
    # (DU08 h.35 `C-ELEC-UNGD-WALL-N`), igual que `-WALL` en drenaje.
    if short.startswith("C-ELEC-") and "WALL" in short:
        return None
    for tok, kind in RECOGNITION_LAYER_TOKENS:
        if tok.upper() in up:
            return kind
    # Variantes de nombre de otros paquetes (DU08/DU10): «UGND» en vez de
    # «UNGD» y un segmento de paquete en medio (`C-ELEC-3MI-UGND-N`,
    # `C-ELEC-UGND-N__UA4`): son las líneas PROPUESTAS «—E—» de la leyenda.
    if _ELEC_UG_LINE.match(short) and not any(t in short for t in ("ANNO", "TEXT", "STRC")):
        return "elec_ungd"
    if short.startswith("C-ELEC-") and any(t in short for t in ("-STRC", "-VALT", "-POLE", "-MANH", "-MHOL")):
        return "structure"
    return None


_ELEC_UG_LINE = re.compile(r"^C-ELEC-(?:[A-Z0-9]+-)?U(?:NGD|GND)(?:-|_|$)")

# Agua (perfil AGUA). Centerline: C-WATR-UNGD-* (APDU y estándar BOE), sus
# variantes de paquete (`C-WATR_UGND-E-ADD`, `C-WATER-UNGD-E-SHORT`) y la
# tubería del estándar C-WATR-PIPE(-LTRL…). Estado por el sufijo como siempre
# (-A abandonada, -D a abandonar, -E existente, -N nueva).
_WATR_LINE = re.compile(r"^C-WATE?R[-_](?:[A-Z0-9]+-)?(?:UNGD|UGND|PIPE)(?:-|_|$)")
# Dentro de esas capas: anotación, camisa, accesorios/válvulas/medidores e
# hidrantes (símbolos, no la línea), muros, perfil, estructuras.
_WATR_NOT_LINE = ("ANNO", "TEXT", "CASE", "FITT", "APPT", "VALV", "METR", "METER",
                  "HYDR", "-FH", "-GV", "WALL", "PROF", "STRC", "VALT", "MANH",
                  "MHOL", "IDEN", "PATT", "OTLN", "STAN")
# Estructuras de agua con caja real (bóveda, pozo): las válvulas, medidores,
# hidrantes, risers, backflow o cajas de riego son accesorios, no estructuras.
_WATR_STRUCT = ("V-WATR-VALT", "V-WATR-MANH", "V-WATR-STRU", "V-FIRE-STRU",
                "C-WATR-VALT", "C-WATR-MANH", "C-WATR-MHOL", "C-WATR-STRC")


def _classify_water(short: str) -> Optional[str]:
    """Perfil AGUA: nombre corto normalizado → kind, o None."""
    if short.startswith(_WATR_STRUCT):
        return "structure"
    if _WATR_LINE.match(short) and not any(t in short for t in _WATR_NOT_LINE):
        return utility_line_kind("AGUA")
    return None


# Alcantarillado sanitario (perfil ALCANTARILLADO). Centerline: C-SSWR-UNGD-*
# (APDU: -A/-D/-E/-N, -E-ADD), la variante de paquete C-SSWR-UGND-N (DU08
# h.36–38, «—SS—» propuesta continua con letras) y la tubería del estándar
# C-SSWR-PIPE. «UNDG» (errata del plot) cuenta igual.
_SSWR_LINE = re.compile(r"^C-(?:SSWR|SEWR|SEWER|SANI)[-_](?:[A-Z0-9]+-)?(?:UNGD|UGND|UNDG|PIPE)(?:-|_|$)")
# Dentro de esas capas: anotación, camisa (CASE/PATT), muros del conducto
# (WALL), perfil, estructuras (STRC: contornos de los buzones propuestos,
# LABOE `C-SSWR-UNGD-STRC-N-301`), y «SCRN» (DU08 `C-SSWR-UNDG-SCRN-N` = el
# símbolo tramado de los buzones propuestos, no una línea).
_SSWR_NOT_LINE = ("ANNO", "TEXT", "CASE", "PATT", "WALL", "PROF", "STRC", "MHOL", "MANH",
                  "SCRN", "IDEN", "OTLN", "STAN", "CNTR", "DIAG", "COUT", "LATL-SYMB")
# Buzones (manholes) y estructuras de la red: los cleanouts (V-SSWR-COUT) son
# accesorios pequeños, no estructuras (como las válvulas en agua).
_SSWR_STRUCT = ("V-SSWR-MANH", "V-SSWR-STRU", "C-SSWR-STRC", "C-SSWR-MANH", "C-SSWR-MHOL")


def _classify_sewer(short: str) -> Optional[str]:
    """Perfil ALCANTARILLADO: nombre corto normalizado → kind, o None."""
    if short.startswith(_SSWR_STRUCT) or re.match(r"^C-SSWR-(?:UNGD|UGND)-STRC(?:-|$)", short):
        return "structure"
    if _SSWR_LINE.match(short) and not any(t in short for t in _SSWR_NOT_LINE):
        return utility_line_kind("ALCANTARILLADO")
    return None


# Capas de estructuras que NO son una bóveda existente: propuestas de otro
# paquete (U-PROP…), postes, cajas de paso, luminarias, señales. Sus símbolos sin
# línea no se importan (solo marca discreta en la vista previa).
NON_VAULT_TOKENS = ("PROP", "POLE", "PBOX", "LITE", "SIGN", "METR", "TRAN")


def is_vault_ocg(ocg: Optional[str]) -> bool:
    """¿La capa es de bóvedas/buzones EXISTENTES (VALT, MANH, MH…) y no de
    estructuras propuestas, postes o cajas de paso?"""
    if not ocg:
        return False
    short = (ocg.split("|")[-1] if "|" in ocg else ocg).strip().upper()
    return not any(t in short for t in NON_VAULT_TOKENS)


def is_abandoned_ocg(ocg: Optional[str]) -> bool:
    """Capa de utilidad ABANDONADA: sufijo de estado NCS «-A» (C-ELEC-UNGD-A)
    o un token explícito (ABND / ABAN / ABANDON)."""
    if not ocg:
        return False
    short = (ocg.split("|")[-1] if "|" in ocg else ocg).strip().upper()
    if short.endswith("-A"):
        return True
    return any(t in short for t in ("ABND", "ABAN", "ABANDON"))


def is_to_abandon_ocg(ocg: Optional[str]) -> bool:
    """Capa de estado «-D» (DU08/DU10: `C-ELEC-UNGD-D`, `C-STRM-UNGD-D`): según la
    leyenda es la utilidad EXISTENTE «a abandonar» (línea con «//»)."""
    if not ocg:
        return False
    short = (ocg.split("|")[-1] if "|" in ocg else ocg).strip().upper()
    return short.endswith("-D")


def suggest_layer_role(ocg: str, utility: str = UTILITY_HINT) -> str:
    """Rol sugerido para el diálogo de confirmación."""
    kind = classify_ocg(ocg, utility)
    if kind == utility_line_kind(utility):
        return ROLE_LINEAS
    if kind == "structure":
        return ROLE_BUZONES
    return ROLE_IGNORAR


def roles_from_suggestions(ocg_names: Sequence[str], utility: str = UTILITY_HINT) -> dict:
    """Construye {lineas:[…], buzones:[…]} a partir de tokens (sin UI)."""
    lineas, buzones = [], []
    for name in ocg_names:
        role = suggest_layer_role(name, utility)
        if role == ROLE_LINEAS:
            lineas.append(name)
        elif role == ROLE_BUZONES:
            buzones.append(name)
    return {ROLE_LINEAS: lineas, ROLE_BUZONES: buzones}


DUP_OCG_TOL_PT = 0.5      # mismo trazo en dos xrefs: puntos a ≤0.5 pt (recortes distintos)
DUP_OCG_MIN_SHARE = 0.9   # …y ≥90 % de los trazos de una capa están en la otra


def _path_points(path: dict) -> List[Tuple[float, float]]:
    """Puntos de un path en orden (Point, Rect, Quad o tuplas ya recortadas)."""
    out = []
    for it in path.get("items") or []:
        for q in it[1:]:
            if hasattr(q, "x0"):                       # fitz.Rect
                out += [(q.x0, q.y0), (q.x1, q.y1)]
            elif hasattr(q, "ul"):                     # fitz.Quad
                out += [(v.x, v.y) for v in (q.ul, q.ur, q.lr, q.ll)]
            elif hasattr(q, "x"):                      # fitz.Point
                out.append((q.x, q.y))
            elif isinstance(q, (tuple, list)) and len(q) == 2:   # punto ya recortado
                out.append((float(q[0]), float(q[1])))
    return out


def is_ring_path(path: dict) -> bool:
    """¿El trazo es un ANILLO (círculo casi completo de radio 3–25 pt)? Un solo
    trazo de ≥8 puntos, todos sobre el círculo ajustado (rms ≤ max(0.3, 6 % r))
    y cubriendo ≥270° alrededor del centro."""
    pts = _path_points(path)
    if len(pts) < RING_MIN_POINTS:
        return False
    fit = _fit_circle(pts)
    if not fit:
        return False
    cx, cy, r, rms = fit
    if not (RING_MIN_R_PT <= r <= RING_MAX_R_PT) or rms > max(0.3, 0.06 * r):
        return False
    angs = sorted(math.degrees(math.atan2(y - cy, x - cx)) % 360.0 for x, y in pts)
    gaps = [b - a for a, b in zip(angs, angs[1:])] + [angs[0] + 360.0 - angs[-1]]
    return 360.0 - max(gaps) >= RING_MIN_SWEEP_DEG


def _rect_corners(path: dict) -> Optional[List[Tuple[float, float]]]:
    """4 esquinas si el path es UN rectángulo cerrado (item «re»/«qu», o 4
    segmentos «l» que cierran con ángulos rectos); si no, None."""
    items = path.get("items") or []
    if len(items) == 1 and items[0][0] in ("re", "qu"):
        q = items[0][1]
        if hasattr(q, "ul"):
            return [(v.x, v.y) for v in (q.ul, q.ur, q.lr, q.ll)]
        if hasattr(q, "x0"):
            return [(q.x0, q.y0), (q.x1, q.y0), (q.x1, q.y1), (q.x0, q.y1)]
        return None
    if len(items) == 4 and all(it[0] == "l" for it in items):
        xy = lambda q: (float(q.x), float(q.y)) if hasattr(q, "x") else (float(q[0]), float(q[1]))  # noqa: E731
        pts = [xy(it[1]) for it in items]
        ends = [xy(it[2]) for it in items]
        if any(math.dist(ends[k], pts[(k + 1) % 4]) > 0.1 for k in range(4)):
            return None
        for k in range(4):
            a, b, c = pts[k - 1], pts[k], pts[(k + 1) % 4]
            u = (a[0] - b[0], a[1] - b[1]); w = (c[0] - b[0], c[1] - b[1])
            nu, nw = math.hypot(*u), math.hypot(*w)
            if nu < 1e-6 or nw < 1e-6 or abs(u[0] * w[0] + u[1] * w[1]) > 0.05 * nu * nw:
                return None
        return pts
    return None


def outline_axis_paths(paths: Sequence[dict]) -> Tuple[List[dict], int]:
    """Cambia cada rectángulo DELGADO (lado corto ≤ OUTLINE_MAX_WIDTH_PT, largo ≥
    OUTLINE_MIN_ASPECT veces) por un trazo recto en su EJE (de la mitad de un lado
    corto a la del otro). Devuelve (paths, nº de contornos convertidos)."""
    out, n = [], 0
    for path in paths:
        c = _rect_corners(path)
        if c:
            s1, s2 = math.dist(c[0], c[1]), math.dist(c[1], c[2])
            short, long_ = min(s1, s2), max(s1, s2)
            if 0.1 < short <= OUTLINE_MAX_WIDTH_PT and long_ >= OUTLINE_MIN_ASPECT * short:
                if s1 <= s2:          # lados cortos: c0-c1 y c2-c3
                    m1 = ((c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2)
                    m2 = ((c[2][0] + c[3][0]) / 2, (c[2][1] + c[3][1]) / 2)
                else:                 # lados cortos: c1-c2 y c3-c0
                    m1 = ((c[1][0] + c[2][0]) / 2, (c[1][1] + c[2][1]) / 2)
                    m2 = ((c[3][0] + c[0][0]) / 2, (c[3][1] + c[0][1]) / 2)
                axis = dict(path)
                axis["items"] = [("l", fitz.Point(*m1), fitz.Point(*m2))]
                axis["closePath"] = False
                axis["rect"] = fitz.Rect(min(m1[0], m2[0]), min(m1[1], m2[1]), max(m1[0], m2[0]), max(m1[1], m2[1]))
                out.append(axis); n += 1
                continue
        out.append(path)
    return out, n


def ring_symbol_paths(paths: Sequence[dict]) -> Tuple[List[dict], List[dict]]:
    """Separa los anillos (contorno de buzón dibujado en la capa de la línea) del
    resto: devuelve (anillos, resto)."""
    rings, rest = [], []
    for path in paths:
        (rings if is_ring_path(path) else rest).append(path)
    return rings, rest


def _same_path(p: list, q: list, tol: float = DUP_OCG_TOL_PT) -> bool:
    return len(p) == len(q) and all(math.dist(a, b) <= tol for a, b in zip(p, q))


DUP_PATH_TOL_PT = 0.05    # el MISMO trazo dibujado dos veces en la misma capa


def dedup_paths(paths: Sequence[dict], tol: float = DUP_PATH_TOL_PT) -> List[dict]:
    """Quita los trazos IDÉNTICOS repetidos dentro de una capa (mismos puntos en
    el mismo orden o al revés, a ≤ `tol`). DU08 h.21: toda la capa
    `…3MI_UG_NORDHOFF|C-ELEC-3MI-UGND-N` viene dibujada dos veces (el xref
    insertado dos veces). Un duplicado no aporta tinta nueva, pero el núcleo
    encadenaba cada guión con su gemelo (líneas de ida y vuelta) y un tick de fin
    de tramo contaba como dos guiones, así que dejaba de ser «tick» y su recta se
    prolongaba 30–40 pt SIN tinta hasta formar esquina con la línea paralela."""
    out: List[dict] = []
    grid: Dict[Tuple[int, int], List[List[Tuple[float, float]]]] = defaultdict(list)
    for path in paths:
        pp = _path_points(path)
        if not pp:
            out.append(path)
            continue
        dup = False
        for key_pt, cand_pts in ((pp[0], pp), (pp[-1], pp[::-1])):
            cx, cy = round(key_pt[0]), round(key_pt[1])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for q in grid.get((cx + dx, cy + dy), ()):
                        if _same_path(cand_pts, q, tol):
                            dup = True; break
                    if dup: break
                if dup: break
            if dup: break
        if dup:
            continue
        grid[(round(pp[0][0]), round(pp[0][1]))].append(pp)
        out.append(path)
    return out


def duplicate_ocgs(by_ocg: dict) -> dict:
    """{ocg repetido: (ocg que se conserva, [paths propios del repetido])}.

    Dos xrefs distintos pueden traer la MISMA capa con la MISMA geometría (DU06
    h.4: `…UE-REF-GLINE_UG|C-STRM-UNGD-E` y `…EO-UD-REF-EXIST_SD-GLINE|
    C-STRM-UNGD-E`, trazo por trazo iguales salvo 0.1 pt y una letra que el
    recorte de cada xref deja distinta): es UNA línea del plano; reconocerla
    dos veces la importaba doble. Solo cuenta como repetida una capa con el
    mismo nombre corto cuyos trazos están ≥`DUP_OCG_MIN_SHARE` en la otra; los
    pocos que no, se devuelven para sumarlos a la conservada (no se pierde
    tinta)."""
    pts = {ocg: [_path_points(p) for p in paths] for ocg, paths in by_ocg.items()}
    short = {ocg: (ocg.split("|")[-1] if "|" in ocg else ocg).strip().upper() for ocg in by_ocg}
    order = sorted(by_ocg, key=lambda o: (-len(by_ocg[o]), o))

    def index(ocg):
        grid = defaultdict(list)
        for k, pp in enumerate(pts[ocg]):
            if pp:
                grid[(round(pp[0][0]), round(pp[0][1]))].append(k)
        return grid

    grids: dict = {}
    dup: dict = {}
    for i, ocg in enumerate(order):
        if not by_ocg[ocg]:
            continue
        for keep in order[:i]:
            if keep in dup or short[keep] != short[ocg]:
                continue
            grid = grids.setdefault(keep, index(keep))
            own = []
            for path, pp in zip(by_ocg[ocg], pts[ocg]):
                if not pp:
                    continue
                cx, cy = round(pp[0][0]), round(pp[0][1])
                cands = (k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in grid.get((cx + dx, cy + dy), ()))
                if not any(_same_path(pp, pts[keep][k]) for k in cands):
                    own.append(path)
            n = sum(1 for pp in pts[ocg] if pp)
            if n and len(own) <= (1.0 - DUP_OCG_MIN_SHARE) * n:
                dup[ocg] = (keep, own)
                break
    return dup


def _page_is_flat(doc, page_index: int) -> bool:
    """Hoja «aplanada»: el PDF no marca ninguno de sus vectores con una capa."""
    try:
        import pdf_layers
        return not pdf_layers.page_uses_layers(doc, page_index)
    except Exception:
        return False


def _clip_polygon(clip: dict, page_rect) -> Optional[list]:
    """Polígono (lista de (x, y)) de un item 'clip' de get_drawings(extended=True),
    o None si es el marco de la página entera (no recorta nada)."""
    sc = clip.get("scissor")
    if sc is not None and (sc.x0 <= page_rect.x0 + 1 and sc.y0 <= page_rect.y0 + 1
                           and sc.x1 >= page_rect.x1 - 1 and sc.y1 >= page_rect.y1 - 1):
        return None
    pts: List[Tuple[float, float]] = []
    for it in clip.get("items") or []:
        cmd = it[0]
        if cmd == "l":
            for q in (it[1], it[2]):
                if not pts or (abs(pts[-1][0] - q.x) > 1e-6 or abs(pts[-1][1] - q.y) > 1e-6):
                    pts.append((float(q.x), float(q.y)))
        elif cmd == "re":
            r = it[1]
            pts += [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        elif cmd == "qu":
            q = it[1]
            pts += [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)]
        elif cmd == "c":
            for q in (it[1], it[4]):
                pts.append((float(q.x), float(q.y)))
    if len(pts) >= 2 and abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6:
        pts.pop()
    if len(pts) < 3:
        # Sin polígono utilizable: usar el rectángulo scissor.
        if sc is None:
            return None
        return [(sc.x0, sc.y0), (sc.x1, sc.y0), (sc.x1, sc.y1), (sc.x0, sc.y1)]
    return pts


def _merge_close_boxes(boxes: Sequence[Tuple[float, float, float, float]], pad: float):
    """Une cajas que están a ≤`pad` una de otra (varias piezas de una misma
    grilla de perfil, o perfiles vecinos que se tocan) en regiones únicas."""
    merged: List[list] = []
    for x0, y0, x1, y1 in boxes:
        for m in merged:
            if x0 - pad <= m[2] and m[0] - pad <= x1 and y0 - pad <= m[3] and m[1] - pad <= y1:
                m[0] = min(m[0], x0); m[1] = min(m[1], y0)
                m[2] = max(m[2], x1); m[3] = max(m[3], y1)
                break
        else:
            merged.append([x0, y0, x1, y1])
    changed = True                       # una pasada más: dos cajas ya fusionadas pueden tocarse ahora
    while changed and len(merged) > 1:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                a, b = merged[i], merged[j]
                if a[0] - pad <= b[2] and b[0] - pad <= a[2] and a[1] - pad <= b[3] and b[1] - pad <= a[3]:
                    a[0] = min(a[0], b[0]); a[1] = min(a[1], b[1])
                    a[2] = max(a[2], b[2]); a[3] = max(a[3], b[3])
                    merged.pop(j)
                    changed = True
                    break
            if changed:
                break
    return [tuple(m) for m in merged]


def profile_view_regions(page, crop_polygon=None) -> List[Tuple[float, float, float, float]]:
    """Recuadros (ya recortados por los clips del PDF) de las capas «PROF»
    (grilla de estación/elevación) de la hoja — ver `PROFILE_LAYER_TOKEN`."""
    page_rect = page.rect
    clip_stack: dict = {}
    boxes: List[Tuple[float, float, float, float]] = []
    for path in page.get_drawings(extended=True):
        lvl = int(path.get("level", 0) or 0)
        if path.get("type") == "clip":
            clip_stack = {l: pg for l, pg in clip_stack.items() if l < lvl}
            clip_stack[lvl] = _clip_polygon(path, page_rect)
            continue
        ocg = path.get("layer") or ""
        short = (ocg.split("|")[-1] if "|" in ocg else ocg).upper()
        if PROFILE_LAYER_TOKEN not in short:
            continue
        polys = [pg for l, pg in clip_stack.items() if l < lvl and pg]
        if polys:
            path = geom.clip_path(path, polys)
            if path is None:
                continue
        if crop_polygon:
            path = geom.clip_path(path, [crop_polygon])
            if path is None:
                continue
        bb = geom._path_bbox(path)
        if bb is not None:
            boxes.append(bb)
    return _merge_close_boxes(boxes, PROFILE_REGION_PAD_PT)


def _region_hit(bb, regions) -> bool:
    if bb is None or not regions:
        return False
    cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    return any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in regions)


def gather_paths(page, kind_for, hidden=(), crop_polygon=None, stats: Optional[dict] = None):
    """Paths de la hoja por rol, ya RECORTADOS por los clips del PDF.

    extended=True trae también los CLIPS (marco de la vista de planta, XCLIP de
    referencias). get_drawings() devuelve la geometría sin recortar, así que las
    líneas "superaban el final" visible: se recortan por el polígono de clip
    activo (pila por `level`). También descarta lo que caiga dentro de una
    VISTA DE PERFIL detectada (`profile_view_regions`). Devuelve (line_paths,
    vault_paths, path_counts, kind_by_ocg); si se pasa `stats` (dict), se le
    añade `profile_excluded` con cuántos trazos se excluyeron por eso."""
    hidden = set(hidden or ())
    path_counts: dict = defaultdict(int)
    kind_by_ocg: dict = {}
    line_paths: List[dict] = []
    vault_paths: List[dict] = []
    page_rect = page.rect
    clip_stack: dict = {}
    regions = profile_view_regions(page, crop_polygon)
    n_profile_excluded = 0
    for path in page.get_drawings(extended=True):
        lvl = int(path.get("level", 0) or 0)
        if path.get("type") == "clip":
            clip_stack = {l: pg for l, pg in clip_stack.items() if l < lvl}
            clip_stack[lvl] = _clip_polygon(path, page_rect)
            continue
        ocg = path.get("layer") or ""
        if ocg in hidden:
            continue
        kind = kind_for(ocg)
        if kind is None:
            continue
        polys = [pg for l, pg in clip_stack.items() if l < lvl and pg]
        if polys:
            path = geom.clip_path(path, polys)
            if path is None:
                continue
        if crop_polygon:
            path = geom.clip_path(path, [crop_polygon])
            if path is None:
                continue
        if path.get("clipped") and _path_length(path) < CLIP_SLIVER_PT:
            continue        # astilla que dejó el recorte (p.ej. 0.9 pt de un guión): no es geometría
        if regions and _region_hit(geom._path_bbox(path), regions):
            n_profile_excluded += 1
            continue        # geometría dentro de una vista de perfil: no es planta, no se reconoce
        path_counts[ocg] += 1
        kind_by_ocg[ocg] = kind
        if kind == "structure":
            vault_paths.append(path)
        elif kind in DRAW_KINDS:
            line_paths.append(path)
    if stats is not None:
        stats["profile_excluded"] = n_profile_excluded
    return line_paths, vault_paths, path_counts, kind_by_ocg


def _path_length(path: dict) -> float:
    total = 0.0
    for it in path.get("items") or ():
        if it[0] == "l":
            p, q = it[1], it[2]
            total += math.hypot(q[0] - p[0], q[1] - p[1])
    return total


def _pdf_pt_to_view_px(x: float, y: float, zoom: float, page: fitz.Page) -> Tuple[float, float]:
    """Coords de get_drawings() → pixeles del pixmap (mismo espacio que el lienzo)."""
    p = fitz.Point(x, y) * page.rotation_matrix
    return (p.x * zoom, p.y * zoom)


def inject_vault_vertices(
    pipes: List[dict],
    vault_pts: Sequence[Tuple[float, float]],
    max_dist: float = VAULT_SNAP_PX,
    near_vert: float = VAULT_NEAR_VERT_PX,
) -> Tuple[int, int]:
    """Inserta un vértice en la pipe más cercana por cada bóveda.

    Con el núcleo nuevo las bóvedas ya vienen como vértices de las polilíneas,
    así que normalmente solo cuenta (vértice ya existente). Sigue sirviendo
    para bóvedas que quedaron cerca de una pipe sin ser vértice.
    Devuelve (snapped, skipped). Mutates ``pipes`` in place.
    """
    from geometry import project_pt_seg

    snapped = 0
    skipped = 0
    for vx, vy in vault_pts:
        best = None  # (dist, pipe_idx, seg_idx, qx, qy)
        for pi, p in enumerate(pipes):
            pts = p.get("pts") or []
            if len(pts) < 2 or p.get("world"):
                continue
            for si in range(len(pts) - 1):
                ax, ay = pts[si]
                bx, by = pts[si + 1]
                qx, qy, d = project_pt_seg(vx, vy, ax, ay, bx, by)
                if d <= max_dist and (best is None or d < best[0]):
                    best = (d, pi, si, qx, qy)
        if best is None:
            skipped += 1
            continue
        _, pi, si, qx, qy = best
        pts = pipes[pi]["pts"]
        if any(math.hypot(qx - px, qy - py) < near_vert for px, py in pts):
            snapped += 1  # ya hay vértice ≈ CAJA en rebuild
            continue
        pts.insert(si + 1, (float(qx), float(qy)))
        snapped += 1
    return snapped, skipped


def recognize_page(
    pdf_path: str | Path,
    page_index: int = 0,
    utility: str = UTILITY_HINT,
    zoom: float = 1.0,
    doc: Optional[fitz.Document] = None,
    hidden_ocgs: Optional[Sequence[str]] = None,
    layer_roles: Optional[dict] = None,
    join_routes: bool = True,
    crop: Optional[Sequence[float]] = None,
    scale_ft_per_pt: Optional[float] = None,
) -> RecognitionResult:
    """Reconoce una utilidad vectorial en una hoja. Abre el PDF si `doc` es None.

    `hidden_ocgs`: capas OCG ocultas (se saltan por nombre).
    `layer_roles`: ``{"lineas":[ocg…], "buzones":[ocg…]}``. Si es None, se
    usan los tokens ``RECOGNITION_LAYER_TOKENS``.
    `join_routes`: une tramos de la misma capa en rutas (buena continuación).
    False devuelve las polilíneas tal como las corta el núcleo geométrico.
        `scale_ft_per_pt`: escala fija (hoja compuesta); None = leerla del texto.
    """
    utility = (utility or UTILITY_HINT).strip().upper()
    line_kind = utility_line_kind(utility)
    own_doc = doc is None
    hidden = set(hidden_ocgs or ())
    roles = layer_roles
    lineas_set = set((roles or {}).get(ROLE_LINEAS) or ())
    buzones_set = set((roles or {}).get(ROLE_BUZONES) or ())
    use_roles = roles is not None

    if own_doc:
        doc = fitz.open(str(pdf_path))
    warnings: List[str] = []
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise IndexError(f"Página {page_index} fuera de rango (0..{doc.page_count - 1})")
        page = doc[page_index]
        scale = float(scale_ft_per_pt) if scale_ft_per_pt else VP.detect_scale(page)
        visual_crop = crop_page_rect(page, crop)
        crop_polygon = drawing_polygon(page, visual_crop) if crop else None

        def _kind_for(ocg: str) -> Optional[str]:
            if use_roles:
                if ocg in lineas_set:
                    return line_kind
                if ocg in buzones_set:
                    return "structure"
                return None
            return classify_ocg(ocg, utility)

        gather_stats: dict = {}
        line_paths, vault_paths, path_counts, kind_by_ocg = gather_paths(
            page, _kind_for, hidden, crop_polygon, stats=gather_stats)

        ocg_summary = [{
            "ocg": ocg, "kind": kind_by_ocg.get(ocg, ""), "path_count": n,
            "drawn": kind_by_ocg.get(ocg) in DRAW_KINDS,
            "abandoned": kind_by_ocg.get(ocg) in DRAW_KINDS and is_abandoned_ocg(ocg),
        } for ocg, n in sorted(path_counts.items(), key=lambda kv: (-kv[1], kv[0]))]

        # — Núcleo geométrico (coords PDF) —
        # Cada capa OCG de líneas se reconstruye SOLA: no se cosen ni se
        # imanan trazos de otra capa (aunque ambas sean «ELEC»). Activas y
        # abandonadas ya salen aparte porque son nombres OCG distintos.
        def px(point):
            x, y = _pdf_pt_to_view_px(point[0], point[1], zoom, page)
            return x - visual_crop.x0 * zoom, y - visual_crop.y0 * zoom
        by_ocg: dict[str, List[dict]] = defaultdict(list)
        for pth in line_paths:
            by_ocg[pth.get("layer") or ""].append(pth)
        n_dup_paths = 0
        for ocg in list(by_ocg):                       # el mismo trazo repetido en la capa: uno solo
            kept = dedup_paths(by_ocg[ocg])
            n_dup_paths += len(by_ocg[ocg]) - len(kept)
            by_ocg[ocg] = kept
        if n_dup_paths:
            warnings.append(f"Trazos repetidos (idénticos, en la misma capa): {n_dup_paths} — se usan una sola vez.")
        dup_of = duplicate_ocgs(by_ocg) if utility in DEDUP_OCG_UTILITIES else {}
        for ocg, (keep, own) in dup_of.items():
            by_ocg[keep].extend(own)
            del by_ocg[ocg]
        if dup_of:
            warnings.append(
                f"Capas repetidas por otro xref (misma geometría): {len(dup_of)} — se reconoce "
                "una sola vez: " + ", ".join(sorted(o.split("|")[0] for o in dup_of)) + ".")
        n_rings = 0
        if utility in RING_VAULT_UTILITIES:
            vault_paths = list(vault_paths)
            for ocg in list(by_ocg):
                rings, by_ocg[ocg] = ring_symbol_paths(by_ocg[ocg])
                vault_paths.extend(rings)
                n_rings += len(rings)
                if not by_ocg[ocg]:
                    del by_ocg[ocg]
        n_outlines = 0
        if utility in OUTLINE_AXIS_UTILITIES:
            for ocg in list(by_ocg):
                by_ocg[ocg], k = outline_axis_paths(by_ocg[ocg])
                n_outlines += k
        if n_outlines:
            warnings.append(f"Tuberías dibujadas como contorno (rectángulo delgado): {n_outlines} — se "
                            "toma su eje como centerline.")
        if n_rings:
            warnings.append(f"Anillos de buzón dibujados en la capa de la línea: {n_rings} — se toman "
                            "como contorno de la estructura, no como tubería.")
        geom_opts = UTILITY_GEOM_OPTIONS.get(utility, geom.GeomOptions())
        results: List[Tuple[bool, str, object]] = []
        for ocg, paths in sorted(by_ocg.items()):
            results.append((is_abandoned_ocg(ocg), ocg, geom.reconstruct(paths, vault_paths, geom_opts)))
        if not results:
            results = [(False, "", geom.reconstruct([], vault_paths, geom_opts))]

        polylines_joined: List[RecognizedPolyline] = []
        polylines_raw: List[RecognizedPolyline] = []
        uncovered_px: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        offpattern_px: List[List[Tuple[float, float]]] = []
        n_dashes = n_glyphs = n_uncovered = n_offpattern = 0
        covered_w = 0.0
        n_routes = n_segments_total = 0
        # Una bóveda queda huérfana solo si ninguna capa de líneas llega a ella.
        vault_seen: dict = {}
        vault_orph: dict = {}

        # Abandonada = capa de estado «-A» Y la línea sigue el patrón de marcadores
        # «/» en toda su longitud (las más cortas que el paso heredan el veredicto
        # de su capa). Dos barras sueltas, o el nombre de la capa solo, no bastan.
        ab_by_layer: dict = {}
        n_layer_no_pattern = 0          # capa «-A» pero sin el patrón «/»
        n_active_with_pattern = 0       # patrón «/» en una capa activa (solo se avisa)
        n_to_abandon = 0                # …de ellas, en capa «-D» (leyenda: existente a abandonar «//»)
        n_double_active = 0             # «//» fuera de capa «-A»: se importan ABANDONADAS

        def _through_dirs(polys):
            """{(x, y) px redondeado: dirección unitaria} de la línea que PASA por
            el tee/junction final de otra polilínea: el tramo de otra polilínea
            que contiene el punto (interior, ≤1 px) o el vértice cuyos dos tramos
            son colineales (≤ FILLET_DIR_DEG)."""
            out = {}
            ends = []
            for i, pl in enumerate(polys):
                if len(pl.pts) < 2:
                    continue
                for j in (0, len(pl.pts) - 1):
                    if pl.kinds[j] in ("tee", "junction"):
                        ends.append((i, px(pl.pts[j])))
            if not ends:
                return out
            for i, q in ends:
                key = (round(q[0], 1), round(q[1], 1))
                if key in out:
                    continue
                for k, o in enumerate(polys):
                    if k == i or len(o.pts) < 2:
                        continue
                    opts = [px(p) for p in o.pts]
                    for a, b in zip(opts, opts[1:]):
                        L = math.dist(a, b)
                        if L < 1e-6:
                            continue
                        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                        t = (q[0] - a[0]) * ux + (q[1] - a[1]) * uy
                        # solo por el INTERIOR del tramo: un ramal que muere en el mismo
                        # punto no es la línea que pasa
                        if 1.0 < t < L - 1.0 and abs((q[0] - a[0]) * uy - (q[1] - a[1]) * ux) <= 1.0:
                            out[key] = (ux, uy); break
                    if key in out:
                        break
                    # …o un vértice de la otra polilínea cuyos dos tramos siguen de largo
                    # (colineales ≤ FILLET_DIR_DEG): la línea pasa por ahí con un vértice
                    for m in range(1, len(opts) - 1):
                        if math.dist(opts[m], q) > 1.0:
                            continue
                        u1 = _unit(opts[m][0] - opts[m - 1][0], opts[m][1] - opts[m - 1][1])
                        u2 = _unit(opts[m + 1][0] - opts[m][0], opts[m + 1][1] - opts[m][1])
                        if math.degrees(math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1])))) <= FILLET_DIR_DEG:
                            out[key] = _unit(u1[0] + u2[0], u1[1] + u2[1]); break
                    if key in out:
                        break
            return out

        def _split_sharp(pl):
            """Parte la polilínea en cada vértice donde se DEVUELVE (ángulo interior
            < CORNER_MIN_INTERIOR_DEG): una sola línea no hace una «V»; ahí se
            juntan dos líneas distintas (ramales de una «Y», curvas que convergen,
            un gancho). Red de seguridad para todos los caminos que las cosían
            (esquina, quiebre, ensamblado, rutas). Nada se inventa ni se mueve."""
            pts, kinds = list(pl.pts), list(pl.kinds)
            cos_min = geom.CORNER_MIN_INTERIOR_COS
            pieces, start = [], 0
            for i in range(1, len(pts) - 1):
                u = (pts[i - 1][0] - pts[i][0], pts[i - 1][1] - pts[i][1])
                v = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                lu, lv = math.hypot(*u), math.hypot(*v)
                if lu < 1e-9 or lv < 1e-9:
                    continue
                if (u[0] * v[0] + u[1] * v[1]) / (lu * lv) > cos_min:
                    pieces.append(geom.Polyline(pts[start:i + 1], kinds[start:i + 1]))
                    start = i
            if not pieces:
                return [pl]
            pieces.append(geom.Polyline(pts[start:], kinds[start:]))
            return pieces

        def _emit(pl, ocg, ab, route_id, n_segments, through=None, ink=None, strokes=None):
            pts = [px(p) for p in pl.pts]
            clean, kinds = [], []
            for p, k in zip(pts, pl.kinds):
                if not clean or math.hypot(clean[-1][0] - p[0], clean[-1][1] - p[1]) >= 0.5:
                    clean.append(p); kinds.append(k)
            if len(clean) < 2:
                return None
            clean, kinds, fillets = fit_fillets(clean, kinds, tol_px=FILLET_FIT_TOL_PT * zoom,
                                                through_dirs=through, ink=ink, strokes=strokes)
            return RecognizedPolyline(
                ocg, utility, clean, line_kind, kinds, abandoned=ab,
                route_id=route_id, n_segments=n_segments, fillets=fillets)

        for ab_layer, ocg, g in results:
            joined = routes_mod.build_routes(g.polylines, g.pattern)
            raw = [routes_mod.Route(pl, 1, [i]) for i, pl in enumerate(g.polylines)]
            joined = [routes_mod.Route(p, r.n_segments if k == 0 else 0, r.members)
                      for r in joined for k, p in enumerate(_split_sharp(r.pl))]
            raw = [routes_mod.Route(p, 1, r.members) for r in raw for p in _split_sharp(r.pl)]
            mp_joined = geom.marker_pattern([r.pl for r in joined], g.markers)
            mp_raw = geom.marker_pattern([r.pl for r in raw], g.markers)
            layer_has = mp_joined.has_pattern or mp_raw.has_pattern
            # «//» = abandonada en CUALQUIER utilidad y capa (regla del usuario,
            # 2026-09-25): no hace falta la capa «-A»; la «/» simple sí la exige.
            layer_double = mp_joined.has_double_pattern or mp_raw.has_double_pattern
            ab_by_layer[ocg] = bool((ab_layer and layer_has) or layer_double)

            def _ab(v, dv=False):
                follows = v if v is not None else layer_has
                by_double = dv if dv is not None else layer_double
                return bool((ab_layer and follows) or by_double)

            def _dbl(mp, i):
                return mp.double_verdict[i] if i < len(mp.double_verdict) else False

            through_j = _through_dirs([r.pl for r in joined])
            through_r = _through_dirs([r.pl for r in raw])
            # Tinta de ESTA capa (px del lienzo): los trazos del PDF y sus puntos.
            # Se reparten por ruta para que una paralela cercana no entre en el
            # ajuste del codo vecino.
            st_all = ink_strokes(by_ocg.get(ocg, []), px)
            corridor = FILLET_INK_CORRIDOR_PT * zoom
            st_j = strokes_by_polyline(st_all, [[px(p) for p in r.pl.pts] for r in joined], corridor)
            st_r = strokes_by_polyline(st_all, [[px(p) for p in r.pl.pts] for r in raw], corridor)
            # ``st_j`` y ``st_r`` están expresados en píxeles de la imagen
            # renderizada. Mantener el paso de muestreo en puntos del PDF evita
            # que la densidad de muestras (y, por tanto, la validación del codo)
            # cambie al variar el zoom de reconocimiento.
            ink_step_px = 1.5 * zoom
            ink_j = [ink_samples(v, step_pt=ink_step_px) for v in st_j]
            ink_r = [ink_samples(v, step_pt=ink_step_px) for v in st_r]
            for rid, r in enumerate(joined):
                v = mp_joined.verdict[rid]
                ab = _ab(v, _dbl(mp_joined, rid))
                rec_pl = _emit(r.pl, ocg, ab, rid, r.n_segments, through_j, ink_j[rid], st_j[rid])
                if rec_pl is not None:
                    polylines_joined.append(rec_pl)
                    n_routes += 1
                    n_segments_total += r.n_segments
                    if ab_layer and not ab:
                        n_layer_no_pattern += 1
                    elif not ab_layer and ab:
                        n_double_active += 1
                    elif not ab_layer and v:
                        if is_to_abandon_ocg(ocg):
                            n_to_abandon += 1
                        else:
                            n_active_with_pattern += 1
            for rid, r in enumerate(raw):
                rec_pl = _emit(r.pl, ocg, _ab(mp_raw.verdict[rid], _dbl(mp_raw, rid)), rid, 1,
                               through_r, ink_r[rid], st_r[rid])
                if rec_pl is not None:
                    polylines_raw.append(rec_pl)
            uncovered_px += [(px(d.a), px(d.b)) for d in g.uncovered]
            offpattern_px += [[px(p) for p in pl.pts] for pl in g.offpattern]
            n_dashes += g.n_dashes; n_glyphs += g.n_glyphs
            n_uncovered += len(g.uncovered); n_offpattern += len(g.offpattern)
            covered_w += g.coverage * g.n_dashes
            for i, v in enumerate(g.vaults):
                # Caja de paso / poste (< VAULT_MIN_FT): no es una bóveda real,
                # `_vaults_geometry` ya la descarta más abajo — que no cuente
                # aquí tampoco, o «Bóvedas sin línea cercana» quedaba inflado
                # con símbolos que de todas formas nunca se iban a importar.
                if min(v.width, v.length) * scale < VAULT_MIN_FT:
                    continue
                key = (round(v.center[0], 1), round(v.center[1], 1))
                vault_seen[key] = vault_seen.get(key, 0) + 1
                if i in g.vault_orphans:
                    vault_orph[key] = vault_orph.get(key, 0) + 1
        coverage_total = covered_w / n_dashes if n_dashes else 1.0

        # Bóvedas = vértices 'vault' de las polilíneas que SÍ se importan
        # (deduplicados), así siempre coinciden con un vértice real.
        polylines = list(polylines_joined if join_routes else polylines_raw)
        vault_pts: List[Tuple[float, float]] = []
        for pl in polylines_raw or polylines_joined:
            for p, k in zip(pl.pts_pdf, pl.kinds):
                if k == "vault" and not any(math.hypot(p[0] - q[0], p[1] - q[1]) < 0.5 for q in vault_pts):
                    vault_pts.append(p)
        orphans_px = [px(key) for key, n in vault_seen.items() if vault_orph.get(key, 0) == n]
        vaults_geo = _vaults_geometry(results, px, scale, zoom, vault_orph, vault_seen, ab_by_layer)
        for vault in vaults_geo:
            vault["utility"] = utility

        stubs = []
        for ocg, kind in kind_by_ocg.items():          # stubs informativos (no dibujables)
            if kind in DRAW_KINDS or (kind == "structure" and vault_pts):
                continue
            stubs.append(RecognizedPolyline(ocg, utility, [], kind))
        polylines.extend(stubs)
        polylines_joined.extend(stubs)
        polylines_raw.extend(stubs)

        if not any(p.kind == line_kind and p.pts_pdf for p in polylines):
            utility_name = {"ELECTRICO": "eléctricas subterráneas", "DRENAJE": "de drenaje",
                            "AGUA": "de agua", "ALCANTARILLADO": "de alcantarillado"}.get(
                                utility, "de " + utility_label(utility).lower())
            warnings.append(f"No se encontraron líneas {utility_name} en esta hoja.")
        if not path_counts:
            if _page_is_flat(doc, page_index):
                warnings.append("Esta hoja no tiene capas: sus vectores no están en ninguna capa del PDF "
                                "(hoja aplanada), así que el reconocimiento por capas no puede encontrar "
                                "utilidades en ella.")
            else:
                warnings.append("Ninguna capa OCG coincidió con los roles / tokens de reconocimiento.")
        n_profile = gather_stats.get("profile_excluded", 0)
        if n_profile:
            warnings.append(
                f"Se excluyeron {n_profile} trazo(s) dentro de una vista de PERFIL (grilla "
                "de estación/elevación): esa vista no es planta y no se reconoce.")
        n_ab = sum(1 for p in polylines if p.kind == line_kind and p.pts_pdf and p.abandoned)
        if n_ab:
            warnings.append(f"Utilidades abandonadas (capa «-A» + patrón «/», o patrón «//»): {n_ab} "
                            "— se importan marcadas (AB).")
        if n_double_active:
            warnings.append(f"Patrón «//» en una capa que no es «-A»: {n_double_active} línea(s) "
                            "— se importan ABANDONADAS (el «//» manda).")
        if n_layer_no_pattern:
            warnings.append(f"Capa «-A» sin el patrón de marcadores «/» a lo largo de la línea: "
                            f"{n_layer_no_pattern} — NO se marcan como abandonadas.")
        if n_to_abandon:
            warnings.append(f"Existentes A ABANDONAR (capa «-D», marcadores «//» de la leyenda): "
                            f"{n_to_abandon} línea(s) — hoy se importan activas; revisar.")
        if n_active_with_pattern:
            warnings.append(f"Patrón de marcadores «/» en una capa ACTIVA: {n_active_with_pattern} línea(s) "
                            "— se importan activas (manda la capa); revisar.")
        if n_segments_total > n_routes:
            warnings.append(
                f"Rutas: {n_routes} (unen {n_segments_total} tramos de la misma capa).")
        n_fil = sum(len(p.fillets or {}) for p in polylines if p.kind == line_kind)
        n_loose = sum(1 for p in polylines if p.kind == line_kind for f in (p.fillets or {}).values() if f.get("loose"))
        if n_fil:
            msg = f"Codos como esquina + radio: {n_fil}"
            if n_loose:
                dev = max(f.get("dev_px", 0.0) for p in polylines if p.kind == line_kind
                          for f in (p.fillets or {}).values() if f.get("loose")) / max(zoom, 1e-9)
                msg += (f" ({n_loose} aproximado(s), a trazos: la curva del plano no es un arco tangente "
                        f"exacto; desvío máx. {dev:.1f} pt)")
            warnings.append(msg + ".")
        n_curvy = sum(1 for p in polylines if p.kind == line_kind and "curve" in (p.kinds or []))
        if n_curvy:
            warnings.append(f"Curvas que quedan como polilínea: {n_curvy} tramo(s) — curva compuesta (radio variable) "
                            "o sin recta tangente a un lado; no se inventa un arco que no está en el plano.")
        if n_glyphs:
            warnings.append(
                f"Se omitieron {n_glyphs} trazos de marcador/linetype (letras, barras); "
                "solo se dibuja la centerline.")
        if n_dashes:
            warnings.append(f"Cobertura de guiones: {coverage_total * 100:.1f}%"
                            + (f" ({n_uncovered} sin cubrir, en naranja)." if n_uncovered else "."))
        if n_offpattern:
            warnings.append(f"Trazos continuos fuera de patrón (leaders/flechas): {n_offpattern} — "
                            "no se importan.")
        if vault_pts:
            warnings.append(f"Bóvedas detectadas: {len(vault_pts)} (ya son vértices de las líneas).")
        if orphans_px:
            warnings.append(f"Bóvedas sin línea cercana: {len(orphans_px)}.")

        roles_out = roles if use_roles else roles_from_suggestions(list(kind_by_ocg.keys()), utility)
        return RecognitionResult(
            utility=utility, page_index=page_index, scale_ft_per_pt=scale,
            polylines=polylines, ocg_summary=ocg_summary, warnings=warnings,
            hidden_ocgs=sorted(hidden), vault_pts=vault_pts, layer_roles=dict(roles_out),
            coverage=coverage_total, uncovered_px=uncovered_px, offpattern_px=offpattern_px,
            vault_orphans_px=orphans_px, join_routes=join_routes, vaults_geo=vaults_geo,
            n_routes=n_routes, n_segments_total=n_segments_total,
            polylines_joined=polylines_joined, polylines_raw=polylines_raw,
        )
    finally:
        if own_doc and doc is not None:
            doc.close()


# ─────────────────────────── codos → esquina + radio ───────────────────────────
VAULT_MIN_FT = 2.0             # símbolo con lado corto menor: caja de paso / poste, no bóveda
FILLET_FIT_TOL_PT = 1.0        # RMS máximo del círculo ajustado a los vértices del codo (pt)
FILLET_DIR_DEG = 8.0           # rumbo del tramo que llega/sale vs. tangente exacta al círculo (la simplificación
                               # deja el final del arco dentro de la recta: ±0.5 pt → algunos grados en radios chicos)
FILLET_MIN_TURN_DEG = 8.0      # giro total mínimo para hablar de codo
FILLET_TANGENT_SLIP_PX = 12.0  # el punto de tangencia exacto puede alejarse hasta esto (pt) del extremo del trazo curvo
FILLET_TANGENCY_TOL_PT = 1.0   # |distancia(centro, recta) − r| máxima: la recta del plano debe ser TANGENTE al círculo
FILLET_ARC_DEV_PT = 1.5        # el arco entero debe quedar a ≤ esto de la polilínea reconocida (que sigue la tinta a ≤1 pt)
FILLET_CHORD_LEG_MIN_PT = 40.0 # tramo que termina en un vértice `curve`: solo vale como recta si es largo (una cuerda
                               # dentro de una curva de r < 200 pt mide < 40 pt con la simplificación de 1 pt)
FILLET_LEG_MIN_PT = 18.0       # una «recta» más corta que esto, sin guión anterior colineal que la confirme, no es
                               # recta del plano (menos que un guión del linetype): suele ser una cuerda sobre un hueco
FILLET_LOOSE_TOL_PT = 3.0      # 2.º intento, codo APROXIMADO: la curva del plano no es un arco tangente exacto (polilínea
                               # «a mano», espiral) pero un arco tangente queda a ≤ esto de ella; se marca `loose` y se avisa
FILLET_INK_CORRIDOR_PT = 2.5   # tinta de la capa a ≤ esto de la centerline del codo = tinta DE ese codo
FILLET_INK_MIN_PTS = 8         # con menos puntos de tinta no se ajusta un círculo (se cae a los vértices)
FILLET_INK_COVER = 0.45        # fracción mínima del arco con tinta a ≤1 pt (el linetype deja huecos y letras)
# Un guión RECTO no puede ser parte de un arco: sobre un círculo de radio r, una
# cuerda de largo L se aparta de su propia recta s = r − √(r² − (L/2)²). Si el
# guión del plano es recto donde el arco pide esa flecha, ahí NO hay curva (el
# quiebre está en el hueco entre guiones: es un chaflán, no un codo).
FILLET_SAG_MIN_PT = 0.5        # por debajo de esta flecha esperada el guión no puede decidir
FILLET_SAG_RATIO = 0.5         # flecha real / esperada: menos que esto = guión recto
FILLET_STRAIGHT_FRAC = 0.35    # fracción de la tinta del sector que puede ser recta
FILLET_STROKE_MIN_PT = 12.0    # trazos más cortos (letras, guión corto) no deciden
SOFT_ARC_KINDS = ("curve", "corner", "bend")


def _fit_circle(pts):
    """Ajuste algebraico (Kåsa) de un círculo: (cx, cy, r, rms) o None."""
    n = len(pts)
    if n < 3:
        return None
    mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
    u = [p[0] - mx for p in pts]; v = [p[1] - my for p in pts]
    suu = sum(a * a for a in u); svv = sum(b * b for b in v); suv = sum(a * b for a, b in zip(u, v))
    suuu = sum(a ** 3 for a in u); svvv = sum(b ** 3 for b in v)
    suvv = sum(a * b * b for a, b in zip(u, v)); svuu = sum(b * a * a for a, b in zip(u, v))
    det = suu * svv - suv * suv
    if abs(det) < 1e-9:
        return None
    rx = 0.5 * (suuu + suvv); ry = 0.5 * (svvv + svuu)
    uc = (rx * svv - ry * suv) / det; vc = (ry * suu - rx * suv) / det
    cx, cy = uc + mx, vc + my
    dists = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    r = sum(dists) / n
    rms = math.sqrt(sum((d - r) ** 2 for d in dists) / n)
    return cx, cy, r, rms


def ink_samples(strokes, step_pt: float = 1.5) -> List[Tuple[float, float, int]]:
    """Tinta de la capa como nube de puntos (x, y, nº de trazo): cada trazo del
    PDF se muestrea cada `step_pt`. Es la geometría TAL COMO está en el PDF —los
    guiones curvos del linetype trazan el arco real—, y con ella se ajusta el
    círculo de cada codo en vez de con la centerline ya simplificada. El nº de
    trazo permite después saber si ESE guión es recto o curvo."""
    out: List[Tuple[float, float, int]] = []
    for si, st in enumerate(strokes):
        for a, b in zip(st, st[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(1, int(L / max(1e-6, step_pt)))
            out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n, si) for k in range(n)]
        out.append((st[-1][0], st[-1][1], si))
    return out


def ink_strokes(paths, px) -> List[List[Tuple[float, float]]]:
    """Trazos de la capa tal como están en el PDF (px del lienzo), uniendo los
    items consecutivos de un mismo path. Cada trazo conserva sus vértices: así
    se puede medir si ESE guión es recto o curvo."""
    out: List[List[Tuple[float, float]]] = []
    for path in paths:
        pts: List[Tuple[float, float]] = []
        for it in (path.get("items") or []):
            if it[0] == "l":
                seq = [it[1], it[2]]
            elif it[0] == "c":
                seq = [it[1], it[2], it[3], it[4]]
            else:
                continue
            xy = [px((float(q.x), float(q.y))) if hasattr(q, "x") else px((float(q[0]), float(q[1]))) for q in seq]
            if pts and math.dist(pts[-1], xy[0]) < 0.05:
                pts += xy[1:]
            else:
                if len(pts) >= 2:
                    out.append(pts)
                pts = list(xy)
        if len(pts) >= 2:
            out.append(pts)
    return out


def strokes_by_polyline(strokes, polys, tol):
    """Reparte los trazos entre las polilíneas (cada uno a la más cercana, por su
    punto medio, y solo si está a ≤ `tol`)."""
    out = [[] for _ in polys]
    segs = [list(zip(pl, pl[1:])) for pl in polys]
    for st in strokes:
        m = st[len(st) // 2]
        best = None
        for i, sg in enumerate(segs):
            for a, b in sg:
                d = _pt_seg_dist(m, a, b)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, i)
        if best is not None:
            out[best[1]].append(st)
    return out


def _ink_near_chain(ink_grid, cell, chain, tol):
    """Puntos de tinta a ≤ `tol` de la polilínea `chain` (la centerline del codo)."""
    got = []
    seen = set()
    for a, b in zip(chain, chain[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / max(1e-6, cell * 0.5)))
        for k in range(n + 1):
            qx, qy = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
            cx0, cy0 = int(qx // cell), int(qy // cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for idx, q in ink_grid.get((cx0 + dx, cy0 + dy), ()):
                        if idx in seen:
                            continue
                        if min(_pt_seg_dist(q, u, v) for u, v in zip(chain, chain[1:])) <= tol:
                            seen.add(idx); got.append((q[0], q[1]))
    return got


def _ink_index(ink, cell):
    grid = {}
    for i, q in enumerate(ink):
        grid.setdefault((int(q[0] // cell), int(q[1] // cell)), []).append((i, q))
    return grid


def _stroke_curvature_kind(st, ctr, r, f_px):
    """¿Este trazo del PDF está curvado como pide el círculo (ctr, r)?
    «curved» = su flecha propia llega al menos a `FILLET_SAG_RATIO` de la que el
    arco implica para su cuerda; «straight» = el plano lo dibujó recto ahí (el
    quiebre está en el hueco: chaflán); «neutral» = demasiado corto para decidir
    (guión corto, letra del linetype)."""
    L = math.dist(st[0], st[-1])
    sag_exp = r - math.sqrt(max(0.0, r * r - (L / 2.0) ** 2))
    if L < FILLET_STROKE_MIN_PT * f_px or sag_exp < FILLET_SAG_MIN_PT * f_px:
        return "neutral"
    sag = max((_pt_seg_dist(q, st[0], st[-1]) for q in st[1:-1]), default=0.0)
    return "curved" if sag >= FILLET_SAG_RATIO * sag_exp else "straight"


def _pt_seg_dist(q, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


def _isect_lines(p, u, q, w):
    """Intersección de p + t·u y q + s·w (None si paralelas)."""
    den = u[0] * w[1] - u[1] * w[0]
    if abs(den) < 1e-9:
        return None
    t = ((q[0] - p[0]) * w[1] - (q[1] - p[1]) * w[0]) / den
    return p[0] + t * u[0], p[1] + t * u[1]


def _foot(o, p, u):
    """Pie de la perpendicular desde o a la recta p + t·u (u unitario)."""
    t = (o[0] - p[0]) * u[0] + (o[1] - p[1]) * u[1]
    return p[0] + t * u[0], p[1] + t * u[1]


def _tangent_from(P, ctr, r, toward):
    """Punto de tangencia desde el punto exterior P al círculo (ctr, r), el más
    cercano a `toward`. None si P está dentro del círculo."""
    dx, dy = ctr[0] - P[0], ctr[1] - P[1]
    d = math.hypot(dx, dy)
    if d <= r * 1.0001:
        return None
    ang = math.asin(min(1.0, r / d))
    base = math.atan2(dy, dx)
    L = math.sqrt(max(0.0, d * d - r * r))
    cands = [(P[0] + L * math.cos(base + sgn * ang), P[1] + L * math.sin(base + sgn * ang)) for sgn in (1, -1)]
    return min(cands, key=lambda q: math.hypot(q[0] - toward[0], q[1] - toward[1]))


def _arc_spans(kinds, pts=None, max_gap=None):
    """Tramos [lo, hi] que son CURVA del PDF: una ristra de vértices `curve`
    (interiores de un trazo curvo) —admitiendo uno o dos nodos intermedios entre
    dos ristras `curve` (dos trazos curvos encadenados; con dos nodos solo si
    están a ≤ `max_gap` uno del otro: el empalme corto entre guiones curvos)—
    más el vértice a cada lado, que es el extremo real del trazo curvo (punto
    de tangencia). Un `corner`/`bend` fuera de eso es una esquina recta y NO
    forma parte del arco."""
    n = len(kinds)
    spans = []
    i = 0
    while i < n:
        if kinds[i] != "curve":
            i += 1; continue
        j = i
        while True:
            while j + 1 < n and kinds[j + 1] == "curve":
                j += 1
            # nodo intermedio entre dos trazos curvos: curve, X, curve
            if j + 2 < n and kinds[j + 2] == "curve" and kinds[j + 1] in ("corner", "bend", "junction"):
                j += 2
                continue
            # dos nodos pegados: curve, X, Y, curve (X·Y corto)
            if (j + 3 < n and kinds[j + 3] == "curve" and kinds[j + 1] in ("corner", "bend")
                    and kinds[j + 2] in ("corner", "bend") and pts is not None and max_gap is not None
                    and math.dist(pts[j + 1], pts[j + 2]) <= max_gap):
                j += 3
                continue
            break
        lo, hi = i - 1, j + 1                    # extremos del trazo curvo
        if lo >= 0 and hi < n:
            spans.append((lo, hi))
        i = j + 1
    return spans


def _fit_circle_through(members, P, ua, Q):
    """Círculo TANGENTE a la recta (P, ua) y que PASA por el punto Q (un nodo del
    plano: tee, bóveda o extremo), el que mejor se ajusta a la tinta `members`.
    Es el caso de una curva que MUERE en un nodo: el plano da la recta y el
    punto, y la tinta elige el radio. Devuelve (cx, cy, r, rms, A) o None."""
    nx, ny = -ua[1], ua[0]
    du = (Q[0] - P[0]) * ua[0] + (Q[1] - P[1]) * ua[1]
    dn = (Q[0] - P[0]) * nx + (Q[1] - P[1]) * ny
    if abs(dn) < 1e-6:
        return None
    sgn = 1.0 if dn > 0 else -1.0

    def circle(t):
        # centro sobre la normal en A = P + t·ua, a distancia r del lado de Q;
        # que pase por Q fija r: (t−du)² + dn² = 2·r·dn
        r = ((t - du) ** 2 + dn * dn) / (2.0 * dn)
        cx, cy = P[0] + ua[0] * t + nx * r, P[1] + ua[1] * t + ny * r
        return cx, cy, abs(r), (P[0] + ua[0] * t, P[1] + ua[1] * t)

    def cost(t):
        cx, cy, r, A = circle(t)
        if r < 1e-6:
            return 1e18
        return sum((math.hypot(q[0] - cx, q[1] - cy) - r) ** 2 for q in members)

    lo, hi = du - 4.0 * abs(dn), du - 1e-3 * sgn * sgn
    g = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = hi - g * (hi - lo); x2 = lo + g * (hi - lo)
    f1, f2 = cost(x1), cost(x2)
    for _ in range(60):
        if f1 > f2:
            lo, x1, f1 = x1, x2, f2; x2 = lo + g * (hi - lo); f2 = cost(x2)
        else:
            hi, x2, f2 = x2, x1, f1; x1 = hi - g * (hi - lo); f1 = cost(x1)
    t = (lo + hi) / 2.0
    cx, cy, r, A = circle(t)
    if r < 1e-6:
        return None
    rms = math.sqrt(cost(t) / max(1, len(members)))
    return cx, cy, r, rms, A


# Nodos donde una curva del plano puede MORIR sin recta que la continúe.
NODE_KINDS_END = ("tee", "junction", "vault", "stop", "edge", "end", "cut")


def _close_at_node(P, u, A, Q, cx, cy, r, i_leg, i_node, rms, swap=False):
    """Cierra el codo «recta + arco que muere en el nodo Q»: la esquina C es la
    intersección de la recta con la tangente al círculo en Q."""
    tx, ty = -(Q[1] - cy), (Q[0] - cx)                 # tangente en Q (perpendicular al radio)
    L = math.hypot(tx, ty)
    if L < 1e-9:
        return None
    tx, ty = tx / L, ty / L
    C = _isect_lines(P, u, Q, (tx, ty))
    if C is None:
        return None
    if swap:
        return (C, Q, A, cx, cy, r, i_node, i_leg, True, False, rms)
    return (C, A, Q, cx, cy, r, i_leg, i_node, False, True, rms)


def _arc_ink_cover(ink_grid, cell, ctr, r, a0, sweep, tol, kind_of=None):
    """Fracción del arco (36 muestras) con tinta de la capa a ≤ `tol`. El
    linetype deja huecos y letras, por eso no se exige el 100 %. Con `kind_of`
    (nº de trazo → curved/straight/neutral) SOLO cuenta la tinta de guiones
    CURVADOS como pide el radio: un guión recto (chaflán: el quiebre va en el
    hueco) o una letra no sostienen un codo. Regla del usuario: «si en el plano
    está como línea, lo hacemos como línea»."""
    hit = 0
    n = 36
    for k in range(n + 1):
        ang = a0 + sweep * k / n
        qx, qy = ctr[0] + r * math.cos(ang), ctr[1] + r * math.sin(ang)
        cx0, cy0 = int(qx // cell), int(qy // cell)
        found = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for _, q in ink_grid.get((cx0 + dx, cy0 + dy), ()):
                    if math.hypot(q[0] - qx, q[1] - qy) > tol:
                        continue
                    if kind_of is not None and kind_of(q[2]) != "curved":
                        continue
                    found = True; break
                if found: break
            if found: break
        hit += 1 if found else 0
    return hit / (n + 1)


def _sub_spans(kinds, lo, hi):
    """Ristras `curve` sueltas dentro de un tramo encadenado [lo, hi] (cada una
    con su vecino a cada lado): si la cadena no cabe en UN círculo (dos curvas
    separadas por una recta corta), cada trazo curvo se prueba por su cuenta."""
    out = []
    i = lo + 1
    while i < hi:
        if kinds[i] != "curve":
            i += 1; continue
        j = i
        while j + 1 < hi and kinds[j + 1] == "curve":
            j += 1
        out.append((i - 1, j + 1))
        i = j + 1
    return out if len(out) > 1 else []


def _leg_lines(pts, kinds, i_end, step, slip, through_dirs=None):
    """Rectas candidatas del tramo RECTO que llega al arco (step=-1, i_end =
    lo-1) o sale de él (step=+1, i_end = hi+1), en orden de preferencia:
    [(punto, dirección unitaria hacia el arco, índice ancla, libre)]. «Libre» =
    la recta es la línea que PASA por un nodo (tee/junction): se extiende a los
    dos lados, así que la tangencia puede caer más allá del nodo.
    Si el vecino del arco es un `bend`/`corner` pegado a él (leg < slip), el
    tramo vecino→extremo del trazo curvo suele ser el empalme run↔curva o el
    salto sobre un hueco/letra del linetype, NO tinta recta: se prueba primero
    la recta del guión anterior (que sí es tinta y pasa por el vecino) y solo
    si el arco no le es tangente se usa la del empalme. DU06 h.4: con el
    empalme la tangente salía 4.75° torcida y la esquina 3.7 pt fuera."""
    v = pts[i_end]; a0 = pts[i_end - step]              # a0 = extremo del trazo curvo
    if kinds[i_end] == "curve" and math.dist(v, a0) < FILLET_CHORD_LEG_MIN_PT * (slip / FILLET_TANGENT_SLIP_PX):
        return []           # cuerda corta dentro de OTRA curva: no es recta del plano (una recta larga
                            # entre dos curvas sí, aunque la simplificación haya fundido su fin con la curva)
    u = _unit(a0[0] - v[0], a0[1] - v[1])
    f = slip / FILLET_TANGENT_SLIP_PX                    # px por pt
    out = []
    confirmed = False                                    # hay guión anterior colineal
    # Ancla en un tee/junction: la línea que PASA por ahí confirma (y da exacta)
    # la dirección de la recta si el tramo va por ella (≤ FILLET_DIR_DEG)
    d = (through_dirs or {}).get((round(v[0], 1), round(v[1], 1))) if kinds[i_end] in ("tee", "junction") else None
    if d is not None and u != (0.0, 0.0):
        if d[0] * u[0] + d[1] * u[1] < 0:
            d = (-d[0], -d[1])
        if math.degrees(math.acos(max(-1.0, min(1.0, d[0] * u[0] + d[1] * u[1])))) <= FILLET_DIR_DEG:
            out.append((v, d, i_end, True)); confirmed = True
    j = i_end + step
    if 0 <= j < len(pts):
        w = pts[j]
        u2 = _unit(v[0] - w[0], v[1] - w[1])
        if u2 != (0.0, 0.0) and u != (0.0, 0.0):
            turn = math.degrees(math.acos(max(-1.0, min(1.0, u[0] * u2[0] + u[1] * u2[1]))))
            if kinds[i_end] in ("bend", "corner") and math.dist(v, a0) < slip:
                if turn > FILLET_DIR_DEG and math.dist(w, v) < FILLET_CHORD_LEG_MIN_PT * f:
                    # dos tramos cortos que siguen girando: la «recta» es otra curva
                    # (curva compuesta / cuerdas sobre un hueco): no hay recta del plano
                    return []
                out.append((w, u2, j, False))       # empalme corto: recta del guión anterior, se absorbe v
            elif turn <= FILLET_DIR_DEG:
                # el tramo vecino→trazo curvo es la misma recta que el guión anterior
                # (p.ej. el fin de la corrida se fundió con el primer vértice de la
                # curva, ≤1 pt fuera de la recta): la dirección EXACTA es la del guión
                out.append((v, u2, i_end, False)); confirmed = True
    if u != (0.0, 0.0):
        if not confirmed and not out and math.dist(v, a0) < FILLET_LEG_MIN_PT * f:
            return []                                    # cuerda corta sin nada que la confirme: no es recta
        out.append((v, u, i_end, False))
    return out


def _fit_circle_tangent(members, C, ua, ub, s0):
    """Círculo TANGENTE a las dos rectas del codo (centro sobre la bisectriz
    interior, a distancia s de la esquina C; r = s·sin(φ/2)) que mejor pasa por
    los vértices del trazo curvo: mínimos cuadrados radiales en 1-D (sección
    áurea alrededor de s0). Devuelve (cx, cy, r, rms) o None."""
    bx, by = -ua[0] + ub[0], -ua[1] + ub[1]
    bl = math.hypot(bx, by)
    if bl < 1e-9:
        return None
    bx, by = bx / bl, by / bl
    cos_phi = max(-1.0, min(1.0, (-ua[0]) * ub[0] + (-ua[1]) * ub[1]))
    phi = math.acos(cos_phi)                             # ángulo interior entre las patas
    sin_h = math.sin(phi / 2.0)
    if sin_h < 1e-6:
        return None

    def cost(sv):
        cx, cy = C[0] + bx * sv, C[1] + by * sv
        r = sv * sin_h
        return sum((math.hypot(q[0] - cx, q[1] - cy) - r) ** 2 for q in members), (cx, cy, r)
    lo, hi = 0.5 * s0, 2.0 * s0
    g = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = hi - g * (hi - lo); x2 = lo + g * (hi - lo)
    f1 = cost(x1)[0]; f2 = cost(x2)[0]
    for _ in range(60):
        if f1 > f2:
            lo, x1, f1 = x1, x2, f2; x2 = lo + g * (hi - lo); f2 = cost(x2)[0]
        else:
            hi, x2, f2 = x2, x1, f1; x1 = hi - g * (hi - lo); f1 = cost(x1)[0]
    sv = (lo + hi) / 2.0
    ss, (cx, cy, r) = cost(sv)
    return cx, cy, r, math.sqrt(ss / max(1, len(members)))


def fit_fillets(pts, kinds, tol_px: float = 1.0, tan_tol: float = None, debug=None, through_dirs=None,
                ink=None, strokes=None):
    """Sustituye cada codo por su esquina C (intersección de las rectas que
    llegan y salen) con kind «fillet», y guarda A/B (puntos de tangencia),
    centro y radio. Nada se inventa: el arco es EXACTAMENTE un trazo curvo del
    PDF (vértices `curve` del núcleo + sus extremos, ver `_arc_spans`), las
    rectas son las de los guiones del plano (`_leg_line`) y el círculo es el
    TANGENTE a esas dos rectas que pasa por los vértices del trazo curvo
    (`_fit_circle_tangent`, RMS ≤ tol). A y B salen de C, las rectas y r
    (T = r·tan(Δ/2)) — exactamente lo que dibuja el editor y genera el plugin.
    Si la curva no es un arco de círculo tangente a sus rectas, se deja como
    polilínea. `through_dirs` = {(x, y) redondeado a 0.1 px: dirección unitaria
    de la línea que PASA por ese tee/junction}: un arco que muere en un tee
    (ramal que entra tangente a la línea principal) se cierra con la recta de
    esa línea y el punto de tangencia FIJO en el tee (no se mueve el vértice:
    el radio sale de T = |C·tee|). Devuelve (pts, kinds, fillets)."""
    pts = list(pts); kinds = list(kinds)
    n = len(pts)
    if n < 4:
        return pts, kinds, {}
    slip = FILLET_TANGENT_SLIP_PX * (tol_px / FILLET_FIT_TOL_PT)
    f_px = tol_px / FILLET_FIT_TOL_PT                     # px por pt
    ink_cell = max(4.0, FILLET_INK_CORRIDOR_PT * f_px * 2)
    ink_grid = _ink_index(ink, ink_cell) if ink else None
    strokes = strokes or []
    through_dirs = through_dirs or {}

    def _through(i):
        """Dirección de la línea que pasa por el vértice i (tee/junction en un
        extremo de la polilínea), o None."""
        if kinds[i] not in ("tee", "junction"):
            return None
        return through_dirs.get((round(pts[i][0], 1), round(pts[i][1], 1)))

    def _span_members(lo, hi):
        """Puntos con los que se ajusta el círculo: la TINTA del trazo curvo del
        PDF (los guiones curvos del linetype trazan el arco real). El corredor se
        toma sobre los vértices `curve` —no sobre todo el tramo—, para que la
        tinta de las rectas vecinas no tuerza el círculo. Sin tinta suficiente se
        cae a los vértices de la centerline."""
        base = pts[lo:hi + 1]
        if ink_grid is None:
            return base, False
        core = [k for k in range(lo, hi + 1) if kinds[k] == "curve"]
        if len(core) >= 2:
            chain0 = pts[core[0]:core[-1] + 1]
        elif core:
            chain0 = pts[max(lo, core[0] - 1):min(hi, core[0] + 1) + 1]
        else:
            chain0 = base
        near = _ink_near_chain(ink_grid, ink_cell, chain0, FILLET_INK_CORRIDOR_PT * f_px)
        if len(near) < FILLET_INK_MIN_PTS and chain0 is not base:
            near = _ink_near_chain(ink_grid, ink_cell, base, FILLET_INK_CORRIDOR_PT * f_px)
        if len(near) >= FILLET_INK_MIN_PTS:
            return near, True
        return base, False

    def _side_legs(edge, step):
        """Rectas candidatas del lado `step` del arco: (punto, dirección HACIA el
        arco, índice ancla, libre). «Libre» = es la línea que PASA por un nodo
        (tee/junction) en el extremo de la polilínea: como se extiende a los dos
        lados del nodo, el punto de tangencia puede caer antes o después de él."""
        out = []
        end = 0 if step < 0 else n - 1
        near_end = (edge <= 1) if step < 0 else (edge >= n - 2)
        if near_end and n >= 2 and _through(end) is not None:
            nb = pts[1] if step < 0 else pts[n - 2]
            toward = (nb[0] - pts[end][0], nb[1] - pts[end][1])     # del nodo hacia el arco
            d = _through(end)
            if d[0] * toward[0] + d[1] * toward[1] < 0:
                d = (-d[0], -d[1])
            out.append((pts[end], d, end, True))
        i_end = edge + step
        if 0 <= i_end < n:
            out += list(_leg_lines(pts, kinds, i_end, step, slip, through_dirs))
        return out

    def _accept(lo, hi, members, on_ink, ia, ib, C, A, B, cx, cy, r, rms, tol_use,
                free_a, free_b, node_a=False, node_b=False):
        """Comprobaciones comunes de un candidato. Devuelve la entrada del plan o None."""
        A0, B0 = pts[lo], pts[hi]
        V0 = pts[lo - 1] if lo > 0 else pts[0]
        W0 = pts[hi + 1] if hi < n - 1 else pts[n - 1]
        if not node_a and min(math.dist(A, A0), math.dist(A, V0)) > slip:
            if debug is not None: debug.append((lo, hi, 'tangencia lejos del extremo', ia, ib))
            return None
        if not node_b and min(math.dist(B, B0), math.dist(B, W0)) > slip:
            if debug is not None: debug.append((lo, hi, 'tangencia lejos del extremo', ia, ib))
            return None
        a0 = math.atan2(A[1] - cy, A[0] - cx); a1 = math.atan2(B[1] - cy, B[0] - cx)
        sweep = (a1 - a0 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
        if abs(math.degrees(sweep)) < FILLET_MIN_TURN_DEG:
            if debug is not None: debug.append((lo, hi, 'giro', round(abs(math.degrees(sweep)), 1)))
            return None
        dev = rms
        if not on_ink:
            # Sin tinta suficiente, el control es contra la centerline: si el arco
            # se aparta de ella, el plano va recto ahí y no hay codo.
            chain = pts[min(ia, lo):max(ib, hi) + 1]
            dev_lim = max(FILLET_ARC_DEV_PT * f_px, tol_use)
            for k in range(1, 40):
                ang = a0 + sweep * k / 40.0
                q = (cx + r * math.cos(ang), cy + r * math.sin(ang))
                dev = max(dev, min(_pt_seg_dist(q, u, v) for u, v in zip(chain, chain[1:])))
            if dev > dev_lim:
                if debug is not None: debug.append((lo, hi, 'arco fuera de la centerline', ia, ib, round(dev, 2)))
                return None
        if ink_grid is not None:
            # La TINTA tiene que estar sobre el arco Y venir de guiones CURVADOS
            # como pide el radio: si el plano los dibujó rectos, el quiebre está
            # en el hueco entre guiones (chaflán) y no hay codo. Regla del
            # usuario: «si en el plano está como línea, lo hacemos como línea».
            kinds_cache = {}

            def kind_of(si):
                if si not in kinds_cache:
                    kinds_cache[si] = (_stroke_curvature_kind(strokes[si], (cx, cy), r, f_px)
                                       if 0 <= si < len(strokes) else "neutral")
                return kinds_cache[si]

            cover = _arc_ink_cover(ink_grid, ink_cell, (cx, cy), r, a0, sweep, 1.0 * f_px,
                                   kind_of if strokes else None)
            if cover < FILLET_INK_COVER:
                if debug is not None: debug.append((lo, hi, 'sin tinta CURVA sobre el arco', ia, ib, round(cover, 2)))
                return None
        return (lo, hi, C, A, B, (cx, cy), r, ia, ib, node_a, node_b, tol_use > tol_px, dev,
                bool(free_a), bool(free_b))

    def _try_span(lo, hi, seed, tol_use):
        """Codo del tramo [lo, hi]: círculo TANGENTE a las dos rectas del plano
        que mejor ajusta la tinta del trazo curvo. Si de un lado no hay recta
        pero el arco muere en un nodo (tee/bóveda/extremo), el círculo se cierra
        tangente a la otra recta y PASANDO por ese nodo. Devuelve la entrada del
        plan (la de menor error) o None, con el motivo en `debug`."""
        cx0, cy0, r0 = seed
        members, on_ink = _span_members(lo, hi)
        legs_a = _side_legs(lo, -1)
        legs_b = _side_legs(hi, +1)
        cands = []
        for (P, ua, ia, free_a) in legs_a:
            for (N, ub_in, ib, free_b) in legs_b:
                ub = (-ub_in[0], -ub_in[1])             # dirección de avance al salir del arco
                turn = math.degrees(math.acos(max(-1.0, min(1.0, ua[0] * ub[0] + ua[1] * ub[1]))))
                if turn < FILLET_MIN_TURN_DEG:
                    if debug is not None: debug.append((lo, hi, 'giro', round(turn, 1)))
                    continue
                C = _isect_lines(P, ua, N, ub)
                if C is None:
                    continue
                phi = math.pi - math.radians(turn)
                s0 = r0 / max(1e-6, math.sin(phi / 2.0))
                fit_t = _fit_circle_tangent(members, C, ua, ub, s0)
                if fit_t is None:
                    continue
                cx, cy, r, rms = fit_t
                if rms > tol_use or r < 2 * tol_px:
                    if debug is not None: debug.append((lo, hi, 'recta no tangente al arco', ia, ib, round(rms, 2)))
                    continue
                T = r * math.tan(math.radians(turn) / 2.0)
                A = (C[0] - ua[0] * T, C[1] - ua[1] * T); B = (C[0] + ub[0] * T, C[1] + ub[1] * T)
                # orden: P … A … C … B … N a lo largo de cada recta (una recta libre
                # se extiende a los dos lados del nodo: ahí el orden no dice nada)
                if not free_a and (A[0] - P[0]) * ua[0] + (A[1] - P[1]) * ua[1] <= 0:
                    if debug is not None: debug.append((lo, hi, 'orden', ia, ib))
                    continue
                if not free_b and (N[0] - B[0]) * ub[0] + (N[1] - B[1]) * ub[1] <= 0:
                    if debug is not None: debug.append((lo, hi, 'orden', ia, ib))
                    continue
                e = _accept(lo, hi, members, on_ink, ia, ib, C, A, B, cx, cy, r, rms, tol_use,
                            free_a, free_b)
                if e is not None:
                    cands.append(e)
        if cands:
            return min(cands, key=lambda e: e[12])
        # Respaldo: la curva MUERE en un nodo del plano (tee, bóveda, extremo) y
        # del otro lado sí hay recta → círculo tangente a esa recta que pasa por
        # el nodo. Nada inventado: recta + nodo + tinta.
        for side in (+1, -1):
            end = n - 1 if side > 0 else 0
            if not ((hi >= n - 2) if side > 0 else (lo <= 1)):
                continue
            if kinds[end] not in NODE_KINDS_END:
                continue
            legs = legs_a if side > 0 else legs_b
            for (P, u, i_leg, _free) in legs:
                if i_leg == end:
                    continue
                u_line = u if side > 0 else (-u[0], -u[1])
                fit_q = _fit_circle_through(members, P, u_line, pts[end])
                if fit_q is None:
                    continue
                cx, cy, r, rms, Tp = fit_q
                if rms > tol_use or r < 2 * tol_px:
                    if debug is not None: debug.append((lo, hi, 'arco al nodo no ajusta', round(rms, 2)))
                    continue
                cl = _close_at_node(P, u_line, Tp, pts[end], cx, cy, r, i_leg, end, rms, swap=side < 0)
                if cl is None:
                    continue
                C, A, B, cx, cy, r, ia, ib, na, nb, rms = cl
                e = _accept(lo, hi, members, on_ink, ia, ib, C, A, B, cx, cy, r, rms, tol_use,
                            False, False, node_a=na, node_b=nb)
                if e is not None:
                    return e
        return None

    plan = []                                   # (lo, hi, C, A, B, centro, R, ia, ib, fijoA, fijoB, loose, dev)
    chord_min = FILLET_CHORD_LEG_MIN_PT * (tol_px / FILLET_FIT_TOL_PT)
    loose_tol = FILLET_LOOSE_TOL_PT * (tol_px / FILLET_FIT_TOL_PT)
    queue = [(lo, hi, tol_px) for lo, hi in _arc_spans(kinds, pts, chord_min)]
    used = set()
    while queue:
        lo, hi, tol_use = queue.pop(0)
        if (lo, hi, tol_use) in used:
            continue
        used.add((lo, hi, tol_use))
        subs = [(a, b, tol_use) for a, b in _sub_spans(kinds, lo, hi)]
        retry = [] if tol_use > tol_px else [(lo, hi, loose_tol)]   # 2.º intento: codo aproximado
        # Un vecino LEJOS del trazo curvo (≥ chord_min) no es el extremo del trazo
        # sino el fin de la recta (la simplificación fundió el fin de la corrida
        # con el primer vértice de la curva): va como ancla de la recta, no como
        # punto del arco.
        if hi - lo >= 2 and math.dist(pts[lo], pts[lo + 1]) >= chord_min:
            lo += 1
        if hi - lo >= 2 and math.dist(pts[hi], pts[hi - 1]) >= chord_min:
            hi -= 1
        # el arco nace/muere en el extremo de la polilínea: solo hay recta si ese
        # extremo es un tee/junction con línea pasante (ramal tangente)
        if (lo <= 0 and not (lo == 0 and _through(0))) or (hi >= n - 1 and not (hi == n - 1 and _through(n - 1))):
            if debug is not None: debug.append((lo, hi, 'sin recta tangente'))
            queue.extend(subs)
            continue
        fit = _fit_circle(pts[lo:hi + 1])       # ajuste libre: solo como semilla y filtro grueso
        if fit is None:
            continue
        cx0, cy0, r0, rms0 = fit
        if rms0 > tol_use or r0 < 2 * tol_px:
            if debug is not None: debug.append((lo, hi, 'no es arco de círculo', round(rms0, 2)))
            queue.extend(subs + retry)
            continue
        # Un `bend`/`corner` vecino que está SOBRE el círculo (radial ≤ tol) suele
        # ser parte del arco, no de la recta: el último guión curvo corto que la
        # simplificación dejó recto, o el empalme con el guión recto. Se prueba
        # primero absorbiéndolo (nunca un nodo topológico) y, si así el arco no
        # cierra (curva compuesta: el vecino es de OTRO arco), con el tramo original.
        on_circle = lambda q: abs(math.hypot(q[0] - cx0, q[1] - cy0) - r0) <= tol_px
        lo2, hi2 = lo, hi
        while lo2 - 1 > 0 and kinds[lo2 - 1] in ("bend", "corner") and on_circle(pts[lo2 - 1]):
            lo2 -= 1
        while hi2 + 1 < n - 1 and kinds[hi2 + 1] in ("bend", "corner") and on_circle(pts[hi2 + 1]):
            hi2 += 1
        entry = None
        tried = set()
        for span in ((lo2, hi2), (lo2, hi), (lo, hi2), (lo, hi)):
            if span in tried:
                continue
            tried.add(span)
            entry = _try_span(span[0], span[1], (cx0, cy0, r0), tol_use)
            if entry is not None:
                break
        if entry is not None:
            plan.append(entry)
        else:
            # cadena «curve, nodo, curve» que no cabe en un círculo: cada trazo
            # curvo por su cuenta (dos codos con una recta corta entre medio); y
            # si nada cierra con la tolerancia exacta, el intento aproximado.
            queue.extend(subs + retry)
    if not plan:
        return pts, kinds, {}
    out_pts, out_kinds, fillets = [], [], {}
    # Los `bend` de empalme que quedaron DENTRO de la recta (ia < lo-1 o ib > hi+1)
    # se absorben: la recta ya pasa por el vértice anterior/siguiente.
    # tramos solapados (una cadena y una de sus sub-ristras, o el intento exacto
    # y el aproximado): gana el exacto y, a igual tolerancia, el primero
    plan.sort(key=lambda e: (e[11], e[0]))   # exacto antes que aproximado
    taken = []
    plan2 = []
    for e in plan:
        if any(not (e[1] < a or e[0] > b) for a, b in taken):
            continue
        taken.append((e[0], e[1])); plan2.append(e)
    plan = sorted(plan2, key=lambda e: e[0])
    # Codos consecutivos que comparten la recta del medio: C2 tiene que estar
    # sobre la recta de salida de C1 (misma tinta); si no, el segundo sobra
    # (sería una esquina sobre una recta que no existe en el plano).
    ok = []
    for e in plan:
        if ok and e[7] is not None and ok[-1][8] >= e[7] - 1:      # e.ia ≤ prev.ib (+1): recta compartida
            C1, B1, C2 = ok[-1][2], ok[-1][4], e[2]
            ux, uy = _unit(B1[0] - C1[0], B1[1] - C1[1])
            off = abs((C2[0] - C1[0]) * uy - (C2[1] - C1[1]) * ux)
            if off > 0.5 * (tol_px / FILLET_FIT_TOL_PT):
                if debug is not None: debug.append((e[0], e[1], 'codo consecutivo fuera de la recta', round(off, 2)))
                continue
        ok.append(e)
    plan = ok
    skip = set()
    for e in plan:
        lo, hi, ia, ib = e[0], e[1], e[7], e[8]
        skip.update(range(ia + 1, lo)); skip.update(range(hi + 1, ib))

    def _leg_vertex(C, T, node, free):  # noqa: D401
        """Vértice del extremo recto del codo: el nodo del plano… o el punto de
        tangencia si la recta es la línea que PASA por ese nodo y la tangencia
        cae más allá (sigue sobre esa misma línea; así el tramo recto del codo
        no queda más corto que T y el arco es exactamente el del plano)."""
        if not free:
            return node
        u = _unit(node[0] - C[0], node[1] - C[1])
        return T if (T[0] - C[0]) * u[0] + (T[1] - C[1]) * u[1] > math.dist(C, node) else node

    def _push(q, kind):
        if out_pts and math.dist(out_pts[-1], q) < 0.5:
            return
        out_pts.append(q); out_kinds.append(kind)

    # Vértices que se mueven al punto de tangencia (recta «libre»: ver _leg_vertex)
    repl = {}
    for e in plan:
        C, A, B, ia, ib, fra, frb = e[2], e[3], e[4], e[7], e[8], e[13], e[14]
        if fra:
            repl[ia] = _leg_vertex(C, A, pts[ia], True)
        if frb:
            repl[ib] = _leg_vertex(C, B, pts[ib], True)
    k = 0; q = 0
    while k < n:
        if q < len(plan) and k == plan[q][0]:
            lo, hi, C, A, B, ctr, r, ia, ib, na, nb, loose, dev, fra, frb = plan[q]
            # El vértice ancla de cada recta se conserva: si la recta es la línea
            # que pasa por un nodo del extremo (o el arco muere ahí), ese nodo
            # queda dentro del tramo y hay que escribirlo igual — si no, la
            # polilínea se quedaría sin el tramo recto a un lado del codo.
            if ia >= lo:
                _push(repl.get(ia, pts[ia]), kinds[ia])
            _push(C, "fillet")
            if out_kinds[-1] == "fillet":
                fillets[len(out_pts) - 1] = {"a": A, "b": B, "center": ctr, "r_px": r,
                                             "loose": bool(loose), "dev_px": round(dev, 2),
                                             # el arco MUERE en ese nodo del plano (no hay
                                             # recta después: la tangente ahí es la del arco)
                                             "node_a": bool(na), "node_b": bool(nb)}
            if ib <= hi:
                _push(repl.get(ib, pts[ib]), kinds[ib])
            k = hi + 1; q += 1
            continue
        if k not in skip:
            _push(repl.get(k, pts[k]), kinds[k])
        k += 1
    return out_pts, out_kinds, fillets


def _unit(dx: float, dy: float):
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-12 else (0.0, 0.0)


def _vaults_geometry(results, px, scale: float, zoom: float, vault_orph: dict, vault_seen: dict,
                     ab_by_layer: Optional[dict] = None) -> List[dict]:
    """Bóvedas (deduplicadas por centro) con su contorno real en px del lienzo y
    sus medidas en pies (pt × pies/pt). Nada se inventa: son los vectores del
    símbolo tal como vienen en el PDF."""
    out: List[dict] = []
    seen: set = set()
    for _ab, _ocg, g in results:
        for v in g.vaults:
            key = (round(v.center[0], 1), round(v.center[1], 1))
            if key in seen:
                continue
            seen.add(key)
            ab_layer = bool(_ab) if ab_by_layer is None else bool(ab_by_layer.get(_ocg, _ab))
            abandoned = ab_layer and v.n_paths >= 4 and v.outline is not None and v.ref is None
            # el "centro" útil es la referencia (manhole) si la hay; si no, el del contorno
            cx, cy = v.reference
            corners = [px(q) for q in v.outline] if v.outline else None
            if min(v.width, v.length) * scale < VAULT_MIN_FT:
                continue                    # caja de paso / poste: no es bóveda (no se mide ni se dibuja)
            orphan = vault_orph.get(key, 0) == vault_seen.get(key, 0)
            out.append({
                "center": px((cx, cy)),
                "corners": corners,
                "shape": v.shape,
                "width_ft": round(v.width * scale, 3),
                "length_ft": round(v.length * scale, 3),
                "angle_deg": round(v.angle_deg, 2),
                "orphan": orphan,
                "abandoned": abandoned,
                "layer": v.layer,
                # Se importa aunque no llegue ninguna línea: es una bóveda real del
                # plano (capa de bóvedas existentes o contorno en la capa de la línea)
                # y en Civil 3D será un sólido. Las propuestas/postes/cajas de paso no.
                "importable": (not orphan) or (v.n_paths >= 4 and v.outline is not None) or is_vault_ocg(v.layer),
            })
    return out


def pipes_from_recognition(result: RecognitionResult, layer: str = UTILITY_HINT,
                           zoom: float = 1.0, origin=None) -> List[dict]:
    """Convierte polilíneas drawable en dicts de pipe del inventario (como finish_pipe).

    No toca Qt ni la ventana: solo datos. `pts` ya están en coords del lienzo.
    `vertex_kinds` viaja con el pipe para que el import marque como ocultas
    las estructuras de los quiebres que no son bóveda.
    `xdata` guarda como referencia la capa OCG de origen (y lo que dice su
    nombre) + el origen: `origin(pts) -> str` (PDF · hoja), opcional.
    """
    import xdata
    from model import PIPE_DIAMETERS_IN, DEFAULT_PIPE_MATERIAL

    out = []
    for pl in result.drawable:
        pts = [(float(x), float(y)) for x, y in pl.pts_pdf]
        if len(pts) < 2:
            continue
        xd = xdata.make(getattr(pl, "layer_ocg", None), origin(pts) if callable(origin) else origin)
        out.append({
            "layer": layer,
            "pts": pts,
            "ab": bool(getattr(pl, "abandoned", False)),
            "diam": float(PIPE_DIAMETERS_IN[0]),
            "diam_unit": "in",
            "material": DEFAULT_PIPE_MATERIAL,
            "vertex_kinds": list(pl.kinds) if len(pl.kinds) == len(pts) else [],
            "origen": "reconocido",
            # codos: vértice → radio en pies (px / zoom × pies/pt)
            "fillets": {int(i): round(f["r_px"] / max(zoom, 1e-9) * result.scale_ft_per_pt, 3)
                        for i, f in (pl.fillets or {}).items()},
        })
        if xd:
            out[-1]["xdata"] = xd
    return out
