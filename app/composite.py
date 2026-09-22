"""composite.py — Hoja compuesta (virtual) armada con PIEZAS vectoriales.

El usuario recorta un área de cualquier hoja de cualquier PDF cargado y la
suelta en una hoja nueva, como un XREF en AutoCAD. Cada pieza conserva sus
vectores, sus capas OCG (nombres completos), sus textos y sus medidas: la hoja
compuesta se materializa como una página PDF real (`build_document`) con
`page.show_pdf_page` (Form XObject recortado) y se reconstruye el catálogo
`/OCProperties` para que las capas se puedan apagar igual que en el original.
El marco de cada pieza actúa como clip para `recognition.gather_paths`, así que
el reconocimiento corre UNA sola vez sobre todos los trazos ya colocados y las
corridas que cruzan el borde entre piezas se unen solas.

Sin Qt. Solo `fitz` para leer trazos y materializar.

Convenciones:
  - `clip` normalizado [x0,y0,x1,y1] sobre la hoja VISIBLE (como sheet_crops).
  - `x, y`: esquina superior izquierda de la pieza en la hoja compuesta (pt).
  - `rotation`: grados ANTIHORARIO en pantalla (convención de show_pdf_page).
  - `src_scale`: pies por punto de la hoja origen. La hoja compuesta tiene una
    escala única (`Composite.target_scale`) y cada pieza se agranda/achica por
    `src_scale / target` para que todo quede coherente en pies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import fitz

Pt = Tuple[float, float]

MARGIN_PT = 36.0          # margen alrededor de las piezas en la hoja compuesta
SIDES = ("left", "right", "top", "bottom")
MAGNET_TOL_PT = 8.0       # radio del imán (pt de la hoja compuesta)
SEAM_ALONG_TOL_PT = 90.0  # cuánto busca el imán A LO LARGO de la costura (el desfase entre recortes)
SEAM_LINE_TOL_PT = 10.0   # la match line puede quedar a ≤ esto del borde de la pieza
SEAM_LINE_MIN_PT = 40.0   # …y tiene que medir al menos esto para servir de referencia
SEAM_LINE_SAME_PT = 2.0   # dos match lines son la MISMA si sus extremos coinciden ±esto tras alinear
SEAM_LAT_TOL_PT = 2.0     # …y cuánto puede sobrar/faltar en el sentido de la línea
SEAM_MIN_PAIRS = 3        # parejas de extremos que tienen que estar de acuerdo para moverse
MAGNET_AGREE_PT = 0.3     # dos deltas "coinciden" si difieren menos que esto
MIN_PIECE_PT = 2.0
EDGE_TOL_PT = 0.75        # un extremo a ≤ esto del borde del clip cuenta como anclaje
NEAR_EDGE_PT = 8.0        # …o a ≤ esto si apunta hacia el borde (el hueco del linetype cayó en el corte)
NEAR_EDGE_COS = math.cos(math.radians(30.0))
BRIDGE_MAX_PT = 150.0     # hueco máximo (pt hoja compuesta) que un puente puede salvar
BRIDGE_PERP_PT = 1.5      # desvío lateral máximo entre dos extremos para emparejarlos
BRIDGE_COS = math.cos(math.radians(12.0))   # direcciones "opuestas" si el ángulo ≤ 12°
ANCHOR_MERGE_PT = 0.5     # anclajes más cerca que esto (misma dirección) se fusionan
BRIDGE_GAP_RATIO = 0.17   # hueco entre guiones del puente, relativo al largo del guión
MIN_ANCHOR_SEG_PT = 3.0   # un trazo más corto que esto (letras, símbolos) no da anclaje
MAX_ANCHOR_ITEMS = 6      # un path con más items es un glifo/símbolo, no una línea
BORDER_BAND_PT = 14.0     # una línea larga a ≤ esto del borde del área es la línea de borde (match line)
BORDER_MIN_FRAC = 0.35    # …si mide al menos esta fracción del lado
GRID_SCAN_MULT = 4.5      # se mira hasta 4.5× la banda: si hay ≥ GRID_MIN_LINES paralelas, es una grilla
GRID_MIN_LINES = 3
GUIDE_MIN_PT = 40.0       # una línea (o serie de guiones colineales) de ≥ esto es guía para el área
COVER_PAD_PT = 0.3        # la franja blanca que tapa la línea de borde sobresale esto de su tinta
COVER_OUT_PT = 0.5        # …y además sale esto por FUERA del borde: sin eso el píxel de la costura
                          # queda gris (la tinta anti-aliased de ambas piezas suma y cada franja solo
                          # restaura su mitad). La última franja pintada cubre ese píxel entero.
LINE_CLUSTER_PT = 1.25    # guiones de una misma match line pueden ir en columnas a ~1 pt


# ─────────────────────────── modelo ───────────────────────────
@dataclass
class Piece:
    source: int                      # índice en la lista de PDFs origen (0 = principal)
    page: int                        # hoja dentro de ese PDF
    clip: List[float]                # [x0,y0,x1,y1] normalizado sobre la hoja visible
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0            # grados antihorario (pantalla)
    src_scale: float = 20 / 72.0     # pies por punto de la hoja origen
    label: str = ""
    # Franjas blancas que tapan la línea de borde (match line, marco) por lado:
    # {"left"|"right"|"top"|"bottom": ancho en pt de la hoja origen, hacia adentro}.
    # El clip pasa por el CENTRO de la línea (los vectores de debajo se conservan
    # para el reconocimiento) y la franja esconde su tinta en la hoja compuesta.
    covers: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dict(source=int(self.source), page=int(self.page),
                    clip=[float(v) for v in self.clip], x=float(self.x), y=float(self.y),
                    rotation=float(self.rotation), src_scale=float(self.src_scale),
                    label=self.label, covers={k: float(v) for k, v in self.covers.items()})

    @classmethod
    def from_dict(cls, d: dict) -> "Piece":
        clip = normalize_clip(d.get("clip"))
        return cls(source=int(d.get("source", 0)), page=int(d.get("page", 0)),
                   clip=clip, x=float(d.get("x", 0.0)), y=float(d.get("y", 0.0)),
                   rotation=float(d.get("rotation", 0.0)) % 360.0,
                   src_scale=float(d.get("src_scale", 20 / 72.0)) or 20 / 72.0,
                   label=str(d.get("label", "")),
                   covers={str(k): float(v) for k, v in (d.get("covers") or {}).items()
                           if k in SIDES and float(v) > 0})


@dataclass
class Composite:
    pieces: List[Piece] = field(default_factory=list)
    scale_ft_per_pt: Optional[float] = None   # None → escala de la primera pieza
    bridges: bool = True                      # unir extremos entre piezas con puentes vectoriales
    bridge_max_pt: float = BRIDGE_MAX_PT      # hueco máximo que salva un puente

    def target_scale(self) -> float:
        if self.scale_ft_per_pt:
            return float(self.scale_ft_per_pt)
        if self.pieces:
            return float(self.pieces[0].src_scale)
        return 20 / 72.0

    def is_single_full_page(self) -> bool:
        """Una sola pieza = hoja entera sin girar: no hace falta materializar."""
        if len(self.pieces) != 1:
            return False
        p = self.pieces[0]
        return (abs(p.rotation % 360.0) < 1e-9 and normalize_clip(p.clip) == [0.0, 0.0, 1.0, 1.0]
                and abs(p.src_scale - self.target_scale()) < 1e-12)

    def to_dict(self) -> dict:
        return dict(pieces=[p.to_dict() for p in self.pieces],
                    scale_ft_per_pt=self.scale_ft_per_pt,
                    bridges=bool(self.bridges), bridge_max_pt=float(self.bridge_max_pt))

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> Optional["Composite"]:
        if not isinstance(d, dict):
            return None
        pieces = [Piece.from_dict(p) for p in d.get("pieces") or [] if isinstance(p, dict)]
        s = d.get("scale_ft_per_pt")
        try:
            gap = float(d.get("bridge_max_pt", BRIDGE_MAX_PT))
        except (TypeError, ValueError):
            gap = BRIDGE_MAX_PT
        return cls(pieces=pieces, scale_ft_per_pt=float(s) if s else None,
                   bridges=bool(d.get("bridges", True)), bridge_max_pt=gap)


def normalize_clip(values) -> List[float]:
    """Clip normalizado válido; sin datos → hoja completa."""
    try:
        x0, y0, x1, y1 = (float(v) for v in values)
    except (TypeError, ValueError):
        return [0.0, 0.0, 1.0, 1.0]
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
        return [0.0, 0.0, 1.0, 1.0]
    return [x0, y0, x1, y1]


# ─────────────────────────── geometría ───────────────────────────
def clip_rect_pt(page_size: Tuple[float, float], clip: Sequence[float]) -> Tuple[float, float, float, float]:
    """Clip normalizado → rectángulo en pt de la hoja visible (x0, y0, x1, y1)."""
    w, h = page_size
    x0, y0, x1, y1 = normalize_clip(clip)
    return x0 * w, y0 * h, x1 * w, y1 * h


def piece_factor(piece: Piece, target_scale: float) -> float:
    """Factor de tamaño de la pieza en la hoja compuesta (misma escala en pies)."""
    return float(piece.src_scale) / float(target_scale)


def rotated_size(w: float, h: float, rotation: float) -> Tuple[float, float]:
    th = math.radians(rotation)
    c, s = abs(math.cos(th)), abs(math.sin(th))
    return w * c + h * s, w * s + h * c


def piece_size(piece: Piece, page_size: Tuple[float, float], target_scale: float) -> Tuple[float, float]:
    """Ancho/alto que ocupa la pieza en la hoja compuesta (pt)."""
    x0, y0, x1, y1 = clip_rect_pt(page_size, piece.clip)
    f = piece_factor(piece, target_scale)
    w, h = rotated_size((x1 - x0) * f, (y1 - y0) * f, piece.rotation)
    return w, h


def piece_rect(piece: Piece, page_size: Tuple[float, float], target_scale: float) -> Tuple[float, float, float, float]:
    w, h = piece_size(piece, page_size, target_scale)
    return piece.x, piece.y, piece.x + w, piece.y + h


def piece_map(piece: Piece, page_size: Tuple[float, float], target_scale: float):
    """Función (x, y) hoja origen VISIBLE (pt) → (x, y) hoja compuesta (pt).

    Misma convención que `page.show_pdf_page(rect, …, clip, rotate)`: el clip se
    gira antihorario `rotation` grados alrededor de su centro, se escala por
    `piece_factor` y su caja envolvente queda con la esquina superior izquierda
    en (piece.x, piece.y)."""
    x0, y0, x1, y1 = clip_rect_pt(page_size, piece.clip)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    f = piece_factor(piece, target_scale)
    w, h = piece_size(piece, page_size, target_scale)
    dx, dy = piece.x + w / 2.0, piece.y + h / 2.0
    th = math.radians(piece.rotation)
    c, s = math.cos(th), math.sin(th)

    def fn(x: float, y: float) -> Pt:
        rx, ry = x - cx, y - cy
        # antihorario en pantalla (y hacia abajo): (rx, ry) → (rx c + ry s, −rx s + ry c)
        qx = rx * c + ry * s
        qy = -rx * s + ry * c
        return dx + qx * f, dy + qy * f
    return fn


def piece_unmap(piece: Piece, page_size: Tuple[float, float], target_scale: float):
    """Inversa de `piece_map`: (x, y) hoja compuesta → (x, y) hoja origen visible."""
    x0, y0, x1, y1 = clip_rect_pt(page_size, piece.clip)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    f = piece_factor(piece, target_scale)
    w, h = piece_size(piece, page_size, target_scale)
    dx, dy = piece.x + w / 2.0, piece.y + h / 2.0
    th = math.radians(piece.rotation)
    c, s = math.cos(th), math.sin(th)

    def fn(X: float, Y: float) -> Pt:
        qx, qy = (X - dx) / f, (Y - dy) / f
        # giro inverso (horario): (qx, qy) → (qx c − qy s, qx s + qy c)
        return cx + qx * c - qy * s, cy + qx * s + qy * c
    return fn


def piece_dir_map(piece: Piece):
    """Función (ux, uy) hoja origen → (ux, uy) hoja compuesta (solo el giro)."""
    th = math.radians(piece.rotation)
    c, s = math.cos(th), math.sin(th)

    def fn(ux: float, uy: float) -> Pt:
        return ux * c + uy * s, -ux * s + uy * c
    return fn


def cover_rects(piece: Piece, page_size: Tuple[float, float],
                out_pt: float = COVER_OUT_PT) -> List[Tuple[float, float, float, float]]:
    """Franjas blancas de la pieza en coords de la hoja origen visible (pt):
    [(x0, y0, x1, y1), …], una por lado con `covers`: desde `w` por dentro del
    borde del clip hasta `out_pt` por fuera (ver COVER_OUT_PT)."""
    x0, y0, x1, y1 = clip_rect_pt(page_size, piece.clip)
    out = []
    for side, w in piece.covers.items():
        w = min(float(w), (x1 - x0) if side in ("left", "right") else (y1 - y0))
        if w <= 0:
            continue
        if side == "left":
            out.append((x0 - out_pt, y0, x0 + w, y1))
        elif side == "right":
            out.append((x1 - w, y0, x1 + out_pt, y1))
        elif side == "top":
            out.append((x0, y0 - out_pt, x1, y0 + w))
        elif side == "bottom":
            out.append((x0, y1 - w, x1, y1 + out_pt))
    return out


def cover_polygons(piece: Piece, page_size: Tuple[float, float], target_scale: float) -> List[List[Pt]]:
    """Las franjas de `cover_rects` como polígonos en coords de la hoja compuesta."""
    fn = piece_map(piece, page_size, target_scale)
    return [[fn(x0, y0), fn(x1, y0), fn(x1, y1), fn(x0, y1)] for x0, y0, x1, y1 in cover_rects(piece, page_size)]


def piece_layout(comp: Composite, page_sizes, names: Optional[Sequence[str]] = None
                 ) -> List[Tuple[Tuple[float, float, float, float], str]]:
    """Esquema de la hoja materializada: [(rect en pt de la hoja compuesta ya
    con el margen, etiqueta), …]. Etiqueta «Hoja N» (y el PDF delante si hay
    más de uno). Para el minimapa de «Capas de la hoja»."""
    _, _, dx, dy = sheet_geometry(comp, page_sizes)
    multi = len({p.source for p in comp.pieces}) > 1
    out = []
    for p in comp.pieces:
        x0, y0, x1, y1 = piece_rect(p, page_sizes(p), comp.target_scale())
        label = f"Hoja {p.page + 1}"
        if multi and names and p.source < len(names):
            label = f"{names[p.source]} · {label}"
        out.append(((x0 + dx, y0 + dy, x1 + dx, y1 + dy), label))
    return out


def bounds(comp: Composite, page_sizes) -> Optional[Tuple[float, float, float, float]]:
    """Caja envolvente de todas las piezas (pt hoja compuesta) o None si no hay."""
    rects = [piece_rect(p, page_sizes(p), comp.target_scale()) for p in comp.pieces]
    if not rects:
        return None
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def sheet_geometry(comp: Composite, page_sizes) -> Tuple[float, float, float, float]:
    """(ancho, alto, dx, dy) de la hoja compuesta: las piezas se trasladan (dx, dy)
    para que la caja envolvente quede a MARGIN_PT del borde."""
    bb = bounds(comp, page_sizes)
    if bb is None:
        return 2.0 * MARGIN_PT, 2.0 * MARGIN_PT, MARGIN_PT, MARGIN_PT
    x0, y0, x1, y1 = bb
    return (x1 - x0 + 2 * MARGIN_PT, y1 - y0 + 2 * MARGIN_PT,
            MARGIN_PT - x0, MARGIN_PT - y0)


# ─────────────────────────── imán ───────────────────────────
def _mutual(pairs: List[Tuple[float, int, int, float, float]]) -> List[Pt]:
    """(coste, i_móvil, j_estático, dx, dy) → deltas de las parejas mutuas:
    cada extremo participa una sola vez, empezando por las más cercanas."""
    used_m, used_s, out = set(), set(), []
    for cost, i, j, dx, dy in sorted(pairs, key=lambda t: t[0]):
        if i in used_m or j in used_s:
            continue
        used_m.add(i); used_s.add(j)
        out.append((dx, dy))
    return out


def magnet_delta(moving: Sequence[Pt], static: Sequence[Pt],
                 tol: float = MAGNET_TOL_PT) -> Optional[Pt]:
    """Desplazamiento (dx, dy) que hace coincidir el mayor número de puntos de
    `moving` con puntos de `static` a distancia ≤ `tol`. None si ninguno.

    Cada punto móvil propone el delta a su vecino estático más cercano; gana
    el delta con más propuestas coincidentes (±MAGNET_AGREE_PT) y se devuelve
    su promedio. Así una sola pareja espuria no arrastra la pieza si hay dos o
    más extremos que sí encajan."""
    if not moving or not static:
        return None
    tol2 = tol * tol
    pairs = []
    for i, (mx, my) in enumerate(moving):
        for j, (sx, sy) in enumerate(static):
            d2 = (sx - mx) ** 2 + (sy - my) ** 2
            if d2 <= tol2:
                pairs.append((d2, i, j, sx - mx, sy - my))
    return _best_group(_mutual(pairs))


@dataclass
class Anchor:
    """Extremo de trazo sobre el borde de una pieza (coords hoja visible, pt).
    `u` apunta hacia AFUERA de la pieza (por donde la línea "quiere" seguir)."""
    x: float
    y: float
    ux: float
    uy: float
    layer: str = ""
    color: Optional[Tuple[float, float, float]] = None
    width: float = 0.0
    dash_len: float = 0.0       # largo del trazo del que sale (0 = desconocido/continuo)
    on_edge: bool = True        # exactamente sobre el borde (corte o extremo ±tol); False = cerca, por dentro
    inset: bool = False         # está en el borde INTERIOR de una franja blanca (no en el borde de la pieza)

    @property
    def xy(self) -> Pt:
        return self.x, self.y


def _rgb(path: dict) -> Optional[Tuple[float, float, float]]:
    col = path.get("color")
    if col is None:
        return None
    try:
        return float(col[0]), float(col[1]), float(col[2])
    except (TypeError, IndexError, ValueError):
        return None


def edge_anchors(page: fitz.Page, clip: Sequence[float], max_paths: int = 200000,
                 tol: float = EDGE_TOL_PT, insets: Optional[Dict[str, float]] = None) -> List[Anchor]:
    """Anclajes del imán y de los puentes: cada trazo VISIBLE que cruza el
    borde del clip (punto de corte) o que termina sobre él (±`tol`; en una hoja
    ploteada la línea suele morir exactamente en la match line). Cada anclaje
    lleva la dirección de salida y la capa OCG del trazo.

    `insets` (= `Piece.covers`): en los lados con franja blanca el borde que
    cuenta es el INTERIOR de la franja, así los puentes cruzan la franja y
    completan encima de ella cada línea que la atraviesa."""
    from sheet_crops import drawing_polygon

    x0, y0, x1, y1 = clip_rect_pt((page.rect.width, page.rect.height), clip)
    inset_edges: Dict[str, float] = {}
    for side, w in (insets or {}).items():
        w = float(w)
        if side == "left":
            x0 += w; inset_edges["left"] = x0
        elif side == "right":
            x1 -= w; inset_edges["right"] = x1
        elif side == "top":
            y0 += w; inset_edges["top"] = y0
        elif side == "bottom":
            y1 -= w; inset_edges["bottom"] = y1
    if x1 - x0 < MIN_PIECE_PT or y1 - y0 < MIN_PIECE_PT:
        return []
    rect = fitz.Rect(page.rect.x0 + x0, page.rect.y0 + y0, page.rect.x0 + x1, page.rect.y0 + y1)
    poly = drawing_polygon(page, rect)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    inner = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
    near = max(tol, NEAR_EDGE_PT)
    core = fitz.Rect(inner.x0 + near, inner.y0 + near, inner.x1 - near, inner.y1 - near)
    rot = page.rotation_matrix

    def inside(x: float, y: float) -> bool:
        return inner.x0 - tol <= x <= inner.x1 + tol and inner.y0 - tol <= y <= inner.y1 + tol

    def on_border(x: float, y: float) -> bool:
        return inside(x, y) and (abs(x - inner.x0) <= tol or abs(x - inner.x1) <= tol
                                 or abs(y - inner.y0) <= tol or abs(y - inner.y1) <= tol)

    def toward_border(x: float, y: float, ux: float, uy: float) -> bool:
        """(x, y) a ≤ NEAR_EDGE_PT de un lado y (ux, uy) apuntando hacia ese lado."""
        if not inside(x, y):
            return False
        n = math.hypot(ux, uy)
        if n < 1e-9:
            return False
        ux, uy = ux / n, uy / n
        return ((abs(x - inner.x1) <= NEAR_EDGE_PT and ux >= NEAR_EDGE_COS)
                or (abs(x - inner.x0) <= NEAR_EDGE_PT and -ux >= NEAR_EDGE_COS)
                or (abs(y - inner.y1) <= NEAR_EDGE_PT and uy >= NEAR_EDGE_COS)
                or (abs(y - inner.y0) <= NEAR_EDGE_PT and -uy >= NEAR_EDGE_COS))

    def clip_exit(px: float, py: float, qx: float, qy: float) -> Optional[Pt]:
        """p dentro, q fuera → punto donde el segmento sale del rectángulo."""
        t_exit = 1.0
        dx, dy = qx - px, qy - py
        for lo, hi, d, o in ((inner.x0, inner.x1, dx, px), (inner.y0, inner.y1, dy, py)):
            if d > 0 and o + d > hi:
                t_exit = min(t_exit, (hi - o) / d)
            elif d < 0 and o + d < lo:
                t_exit = min(t_exit, (lo - o) / d)
        if not 0.0 <= t_exit <= 1.0:
            return None
        return px + dx * t_exit, py + dy * t_exit

    out: List[Anchor] = []

    def emit(x: float, y: float, fx: float, fy: float, path: dict, dash_len: float = 0.0):
        """(x, y) sobre el borde (o cerca); (fx, fy) un punto interior del mismo trazo."""
        ux, uy = x - fx, y - fy
        n = math.hypot(ux, uy)
        if n < 1e-6:
            return
        a = fitz.Point(x, y) * rot
        d = fitz.Point(ux / n, uy / n) * fitz.Matrix(rot.a, rot.b, rot.c, rot.d, 0, 0)
        vx, vy = a.x - page.rect.x0, a.y - page.rect.y0
        on_inset = any(abs((vx if side in ("left", "right") else vy) - e) <= tol
                       for side, e in inset_edges.items())
        out.append(Anchor(vx, vy, d.x, d.y,
                          path.get("layer") or "", _rgb(path), float(path.get("width") or 0.0),
                          dash_len, on_border(x, y), on_inset))

    for i, path in enumerate(page.get_drawings()):
        if i >= max_paths:
            break
        r = path.get("rect")
        if r is None or core.contains(r):
            continue                        # lejos del borde: no aporta anclajes
        if path.get("type") == "f":
            continue                        # relleno puro (logos, hatch sólido): no es una línea
        # (Rect.intersects es False para rects de área cero: líneas rectas.)
        if r.x1 < inner.x0 - tol or r.x0 > inner.x1 + tol or r.y1 < inner.y0 - tol or r.y0 > inner.y1 + tol:
            continue                        # totalmente fuera
        items = path.get("items") or ()
        if len(items) > MAX_ANCHOR_ITEMS:
            continue                        # letra explotada / símbolo: no es una línea que continúe
        for it in items:
            if it[0] == "l":
                p, q = it[1], it[2]
            elif it[0] == "c" and len(items) <= 3:
                p, q = it[1], it[4]
            else:
                continue
            if math.hypot(q.x - p.x, q.y - p.y) < MIN_ANCHOR_SEG_PT:
                continue                    # trazo minúsculo (letras, marcas): no ayuda a alinear
            pin, qin = inside(p.x, p.y), inside(q.x, q.y)
            # Largo del trazo: si es un guión de linetype, el puente copia su patrón.
            seg_len = math.hypot(q.x - p.x, q.y - p.y) if len(items) == 1 else 0.0
            if pin and qin:
                # Extremo sobre el borde, o cerca de él apuntando hacia afuera
                # (el último guión del linetype no siempre llega al corte).
                q_out = on_border(q.x, q.y) or toward_border(q.x, q.y, q.x - p.x, q.y - p.y)
                p_out = on_border(p.x, p.y) or toward_border(p.x, p.y, p.x - q.x, p.y - q.y)
                if q_out and not p_out:
                    emit(q.x, q.y, p.x, p.y, path, seg_len)
                elif p_out and not q_out:
                    emit(p.x, p.y, q.x, q.y, path, seg_len)
            elif pin != qin:
                a, b = (p, q) if pin else (q, p)
                cut = clip_exit(a.x, a.y, b.x, b.y)
                if cut is not None:
                    emit(cut[0], cut[1], a.x, a.y, path, seg_len)
    return _merge_anchors(out)


def _merge_anchors(anchors: Sequence[Anchor], radius: float = ANCHOR_MERGE_PT) -> List[Anchor]:
    """Fusiona anclajes apiñados (≤ `radius`, misma dirección): un símbolo o
    un texto explotado cortado por el borde no debe pesar como cien líneas."""
    uniq: List[Anchor] = []
    for an in sorted(anchors, key=lambda a: (a.layer, a.x, a.y)):
        for u in uniq:
            if (u.layer == an.layer and abs(an.x - u.x) <= radius and abs(an.y - u.y) <= radius
                    and an.ux * u.ux + an.uy * u.uy > 0.9):
                break
        else:
            uniq.append(an)
    return uniq


def trim_border_lines(page: fitz.Page, clip: Sequence[float], band: float = BORDER_BAND_PT,
                      min_frac: float = BORDER_MIN_FRAC) -> List[float]:
    """Solo el clip de `trim_border` (compatibilidad)."""
    return trim_border(page, clip, band, min_frac)[0]


def trim_border(page: fitz.Page, clip: Sequence[float], band: float = BORDER_BAND_PT,
                min_frac: float = BORDER_MIN_FRAC) -> Tuple[List[float], Dict[str, float]]:
    """Lleva cada lado del clip al CENTRO de la línea de borde del plano (match
    line, marco de la vista) que corra pegada a ese lado, sea de la capa que sea
    y aunque sea DISCONTINUA (guiones gruesos): trazos paralelos al lado, a
    ≤ `band` pt por dentro, que entre todos cubren ≥ `min_frac` del lado. Una
    serie de ≥ GRID_MIN_LINES paralelas (grilla) no cuenta.

    Cortar por el centro no pierde ningún vector (los de debajo de la tinta
    siguen en el PDF y el reconocimiento los ve). La tinta de la línea se tapa
    después con una franja blanca: devuelve ``(clip, covers)`` con el ancho de
    esa franja por lado (pt hoja visible, hacia adentro; incluye la deriva si la
    línea va un poco inclinada)."""
    from sheet_crops import drawing_polygon

    W, H = page.rect.width, page.rect.height
    x0, y0, x1, y1 = clip_rect_pt((W, H), clip)
    rect = fitz.Rect(page.rect.x0 + x0, page.rect.y0 + y0, page.rect.x0 + x1, page.rect.y0 + y1)
    poly = drawing_polygon(page, rect)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    inner = fitz.Rect(min(xs), min(ys), max(xs), max(ys))      # en coords de dibujo
    # lado → (coordenada del borde, eje, signo hacia adentro, extensión del lado)
    sides = {"left": (inner.x0, "x", +1, (inner.y0, inner.y1)), "right": (inner.x1, "x", -1, (inner.y0, inner.y1)),
             "top": (inner.y0, "y", +1, (inner.x0, inner.x1)), "bottom": (inner.y1, "y", -1, (inner.x0, inner.x1))}
    segs: Dict[str, List[Tuple[float, float, float, float, float]]] = {k: [] for k in sides}
    for path in page.get_drawings():
        if path.get("type") == "f":
            continue
        width = float(path.get("width") or 0.0)
        for it in path.get("items") or ():
            if it[0] != "l":
                continue
            p, q = it[1], it[2]
            for side, (edge, axis, sign, (s_lo, s_hi)) in sides.items():
                if axis == "x":
                    if abs(p.x - q.x) > 0.75 or abs(p.y - q.y) < 2.0:
                        continue
                    coord = (p.x + q.x) / 2.0
                    lo, hi = min(p.y, q.y), max(p.y, q.y)
                else:
                    if abs(p.y - q.y) > 0.75 or abs(p.x - q.x) < 2.0:
                        continue
                    coord = (p.y + q.y) / 2.0
                    lo, hi = min(p.x, q.x), max(p.x, q.x)
                lo, hi = max(lo, s_lo), min(hi, s_hi)     # solo lo que cae en la extensión del lado
                if hi <= lo:
                    continue
                d = (coord - edge) * sign
                if -0.75 <= d <= GRID_SCAN_MULT * band:
                    segs[side].append((d, coord, width, lo, hi))
    cut: Dict[str, Optional[Tuple[float, float]]] = {}      # lado → (coord del corte, ancho de la franja)
    for side, (edge, axis, sign, (s_lo, s_hi)) in sides.items():
        side_len = s_hi - s_lo
        lines = _collinear_lines(segs[side], side_len, min_frac)
        near = [ln for ln in lines if ln[0] <= band]
        if not near or len(lines) >= GRID_MIN_LINES:
            cut[side] = None
        else:
            _, coord_mean, coord_inner, width = max(near, key=lambda t: t[0])
            drift = (coord_inner - coord_mean) * sign          # cuánto se mete la línea si va inclinada
            cut[side] = (coord_mean, max(0.0, drift) + width / 2.0 + COVER_PAD_PT)
    if all(v is None for v in cut.values()):
        return normalize_clip(clip), {}
    tx0 = cut["left"][0] if cut["left"] else inner.x0
    tx1 = cut["right"][0] if cut["right"] else inner.x1
    ty0 = cut["top"][0] if cut["top"] else inner.y0
    ty1 = cut["bottom"][0] if cut["bottom"] else inner.y1
    if tx1 - tx0 < MIN_PIECE_PT or ty1 - ty0 < MIN_PIECE_PT:
        return normalize_clip(clip), {}
    rot = page.rotation_matrix
    corners = {"left": (tx0, (ty0 + ty1) / 2), "right": (tx1, (ty0 + ty1) / 2),
               "top": ((tx0 + tx1) / 2, ty0), "bottom": ((tx0 + tx1) / 2, ty1)}
    pts = [fitz.Point(x, y) * rot for x, y in ((tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1))]
    vx = [pt.x - page.rect.x0 for pt in pts]; vy = [pt.y - page.rect.y0 for pt in pts]
    vis = (min(vx), min(vy), max(vx), max(vy))
    covers: Dict[str, float] = {}
    for side, val in cut.items():
        if not val:
            continue
        m = fitz.Point(*corners[side]) * rot
        mx, my = m.x - page.rect.x0, m.y - page.rect.y0
        # ¿en qué lado VISIBLE cae el punto medio de ese lado del dibujo?
        dists = {"left": abs(mx - vis[0]), "right": abs(mx - vis[2]),
                 "top": abs(my - vis[1]), "bottom": abs(my - vis[3])}
        covers[min(dists, key=dists.get)] = val[1]
    return normalize_clip([vis[0] / W, vis[1] / H, vis[2] / W, vis[3] / H]), covers


def guide_lines(page: fitz.Page, min_len: float = GUIDE_MIN_PT) -> Dict[str, List[Tuple[float, float, float]]]:
    """Líneas «generales» de la hoja para imantar los lados del área a tomar:
    trazos horizontales/verticales (también a guiones colineales) cuya cobertura
    llega a `min_len`. Coords de la hoja VISIBLE, pt:
    ``{"x": [(x, y_lo, y_hi, cobertura), …], "y": [(y, x_lo, x_hi, cobertura), …]}``
    ordenadas por coordenada."""
    segs_v: List[Tuple[float, float, float, float, float]] = []   # (0, coord, w, lo, hi) verticales (x=coord)
    segs_h: List[Tuple[float, float, float, float, float]] = []
    for path in page.get_drawings():
        if path.get("type") == "f":
            continue
        for it in path.get("items") or ():
            if it[0] != "l":
                continue
            p, q = it[1], it[2]
            if abs(p.x - q.x) <= 0.75 and abs(p.y - q.y) >= 2.0:
                segs_v.append((0.0, (p.x + q.x) / 2.0, 0.0, min(p.y, q.y), max(p.y, q.y)))
            elif abs(p.y - q.y) <= 0.75 and abs(p.x - q.x) >= 2.0:
                segs_h.append((0.0, (p.y + q.y) / 2.0, 0.0, min(p.x, q.x), max(p.x, q.x)))
    rot = page.rotation_matrix
    out: Dict[str, List[Tuple[float, float, float, float]]] = {"x": [], "y": []}

    def emit(coord: float, lo: float, hi: float, cov: float, vertical: bool):
        a = fitz.Point(coord, lo) * rot if vertical else fitz.Point(lo, coord) * rot
        b = fitz.Point(coord, hi) * rot if vertical else fitz.Point(hi, coord) * rot
        ax, ay = a.x - page.rect.x0, a.y - page.rect.y0
        bx, by = b.x - page.rect.x0, b.y - page.rect.y0
        if abs(ax - bx) <= 1e-6:
            out["x"].append(((ax + bx) / 2.0, min(ay, by), max(ay, by), cov))
        else:
            out["y"].append(((ay + by) / 2.0, min(ax, bx), max(ax, bx), cov))

    for segs, vertical in ((segs_v, True), (segs_h, False)):
        for lo, hi, coord, cov in _covered_clusters(segs, min_len):
            emit(coord, lo, hi, cov, vertical)
    out["x"].sort(); out["y"].sort()
    return out


def _covered_clusters(segs: List[Tuple[float, float, float, float, float]], min_len: float
                      ) -> List[Tuple[float, float, float, float]]:
    """Agrupa trazos paralelos por coordenada (±LINE_CLUSTER_PT); devuelve
    (lo, hi, coord, cobertura) de los grupos cuya unión de tramos mide ≥ `min_len`."""
    if not segs:
        return []
    segs = sorted(segs, key=lambda t: t[1])
    groups: List[List[Tuple[float, float, float, float, float]]] = [[segs[0]]]
    for sg in segs[1:]:
        if sg[1] - groups[-1][-1][1] <= LINE_CLUSTER_PT:
            groups[-1].append(sg)
        else:
            groups.append([sg])
    out = []
    for g in groups:
        spans = sorted((lo, hi) for _, _, _, lo, hi in g)
        covered, cur_lo, cur_hi = 0.0, spans[0][0], spans[0][1]
        for lo, hi in spans[1:]:
            if lo <= cur_hi + 1.0:
                cur_hi = max(cur_hi, hi)
            else:
                covered += cur_hi - cur_lo; cur_lo, cur_hi = lo, hi
        covered += cur_hi - cur_lo
        if covered >= min_len:
            coord = sum(t[1] for t in g) / len(g)
            out.append((spans[0][0], max(hi for _, hi in spans), coord, covered))
    return out


def snap_edge(guides: Sequence[tuple], coord: float, lo: float, hi: float,
              tol: float) -> Optional[tuple]:
    """Guía a la que salta un lado en `coord`: entre las que están a ≤ `tol` y
    cuya extensión solapa [lo, hi], gana la de MÁS cobertura (la match line o el
    marco antes que un borde de vía fino), y a igual cobertura la más cercana."""
    cands = []
    for g in guides:
        g_coord, g_lo, g_hi = g[0], g[1], g[2]
        cov = g[3] if len(g) > 3 else (g_hi - g_lo)
        if g_hi < lo or g_lo > hi:
            continue
        d = abs(g_coord - coord)
        if d <= tol:
            cands.append((-cov, d, g))
    if not cands:
        return None
    return min(cands)[2]


def _collinear_lines(segs: List[Tuple[float, float, float, float, float]], side_len: float,
                     min_frac: float) -> List[Tuple[float, float, float, float]]:
    """Agrupa trazos paralelos por coordenada (±LINE_CLUSTER_PT) y devuelve las
    "líneas" cuya cobertura (unión de sus tramos) llega a `min_frac` del lado:
    [(d_medio, coord_media, coord_más_interior, ancho), …] ordenadas por d.
    Así una match line a guiones gruesos cuenta igual que una continua."""
    if not segs or side_len <= 0:
        return []
    segs = sorted(segs, key=lambda t: t[1])
    groups: List[List[Tuple[float, float, float, float, float]]] = [[segs[0]]]
    for sg in segs[1:]:
        if sg[1] - groups[-1][-1][1] <= LINE_CLUSTER_PT:
            groups[-1].append(sg)
        else:
            groups.append([sg])
    out = []
    for g in groups:
        spans = sorted((lo, hi) for _, _, _, lo, hi in g)
        covered, cur_lo, cur_hi = 0.0, spans[0][0], spans[0][1]
        for lo, hi in spans[1:]:
            if lo <= cur_hi:
                cur_hi = max(cur_hi, hi)
            else:
                covered += cur_hi - cur_lo; cur_lo, cur_hi = lo, hi
        covered += cur_hi - cur_lo
        if covered >= min_frac * side_len:
            d_mean = sum(t[0] for t in g) / len(g)
            coord_mean = sum(t[1] for t in g) / len(g)
            coord_inner = max(g, key=lambda t: t[0])[1]
            width = max(t[2] for t in g)
            out.append((d_mean, coord_mean, coord_inner, width))
    return sorted(out)


def edge_points(page: fitz.Page, clip: Sequence[float], max_paths: int = 200000,
                tol: float = EDGE_TOL_PT) -> List[Pt]:
    """Solo las posiciones de `edge_anchors` (compatibilidad)."""
    return [a.xy for a in edge_anchors(page, clip, max_paths, tol)]


def map_anchors(piece: Piece, page_size: Tuple[float, float], target_scale: float,
                anchors: Sequence[Anchor], at: Optional[Pt] = None) -> List[Anchor]:
    """Anclajes de la pieza en coords de la hoja compuesta (posición `at` opcional)."""
    if at is not None:
        piece = Piece(**{**piece.to_dict(), "x": at[0], "y": at[1]})
    fn = piece_map(piece, page_size, target_scale)
    dn = piece_dir_map(piece)
    out = []
    for a in anchors:
        x, y = fn(a.x, a.y)
        ux, uy = dn(a.ux, a.uy)
        f = piece_factor(piece, target_scale)
        out.append(Anchor(x, y, ux, uy, a.layer, a.color, a.width, a.dash_len * f, a.on_edge, a.inset))
    return out


def _best_group(proposals: List[Pt]) -> Optional[Pt]:
    if not proposals:
        return None
    best_group: List[Pt] = []
    for dx, dy in proposals:
        group = [(ex, ey) for ex, ey in proposals
                 if abs(ex - dx) <= MAGNET_AGREE_PT and abs(ey - dy) <= MAGNET_AGREE_PT]
        if len(group) > len(best_group) or (
                len(group) == len(best_group) and group
                and math.hypot(dx, dy) < math.hypot(*best_group[0])):
            best_group = group
    # Mediana: las parejas exactas (guiones cortados en la misma match line)
    # dominan y una pareja "casi" no desplaza el resultado.
    xs = sorted(g[0] for g in best_group); ys = sorted(g[1] for g in best_group)
    return xs[len(xs) // 2], ys[len(ys) // 2]


def coincide_delta(moving: Sequence[Anchor], static: Sequence[Anchor],
                   tol: float = MAGNET_TOL_PT) -> Optional[Pt]:
    """Como `magnet_delta` pero con anclajes: solo emparejan extremos que se
    MIRAN de frente (así los bordes superior/inferior de dos piezas vecinas,
    cuyos extremos apuntan igual, no se pegan entre sí)."""
    tol2 = tol * tol
    pairs = []
    for i, m in enumerate(moving):
        for j, s in enumerate(static):
            if m.ux * s.ux + m.uy * s.uy > -BRIDGE_COS:
                continue
            d2 = (s.x - m.x) ** 2 + (s.y - m.y) ** 2
            if d2 <= tol2:
                pairs.append((d2, i, j, s.x - m.x, s.y - m.y))
    return _best_group(_mutual(pairs))


def collinear_delta(moving: Sequence[Anchor], static: Sequence[Anchor],
                    tol: float = MAGNET_TOL_PT, max_gap: float = BRIDGE_MAX_PT) -> Optional[Pt]:
    """Imán con HUECO: desplazamiento lateral que deja los extremos de `moving`
    en línea con los de `static` que los miran de frente (direcciones opuestas,
    a ≤ `max_gap` por delante), sin cerrar el hueco. None si nada encaja."""
    pairs = []
    for i, m in enumerate(moving):
        for j, s in enumerate(static):
            if m.ux * s.ux + m.uy * s.uy > -BRIDGE_COS:
                continue                                    # no se miran de frente
            vx, vy = s.x - m.x, s.y - m.y
            along = vx * m.ux + vy * m.uy
            if along < -tol or along > max_gap:
                continue
            px, py = vx - along * m.ux, vy - along * m.uy   # componente lateral
            d2 = px * px + py * py
            if d2 <= tol * tol:
                pairs.append((d2 + 0.01 * along, i, j, px, py))
    return _best_group(_mutual(pairs))


def refine_delta(moving: Sequence[Anchor], static: Sequence[Anchor], tol: float = MAGNET_TOL_PT,
                 max_gap: float = BRIDGE_MAX_PT) -> Tuple[Optional[float], Optional[float]]:
    """Ajuste FINO tras el imán: (dx, dy) que minimiza por mínimos cuadrados el
    desvío lateral de todas las parejas de extremos enfrentados (mutuas). Las
    líneas inclinadas fijan también la posición a lo largo de la normal de la
    costura (algo que «borde con borde» solo estima por el centro de la match
    line). Devuelve None en el eje que las parejas no determinan (todas las
    líneas paralelas a ese eje)."""
    pairs = []
    for i, m in enumerate(moving):
        for j, s in enumerate(static):
            if m.ux * s.ux + m.uy * s.uy > -BRIDGE_COS:
                continue
            vx, vy = s.x - m.x, s.y - m.y
            along = vx * m.ux + vy * m.uy
            if along < -tol or along > max_gap:
                continue
            lat = vx * (-m.uy) + vy * m.ux                  # componente sobre la normal n = (−uy, ux)
            if abs(lat) <= tol:
                pairs.append((abs(lat) + 0.01 * along, i, j, lat, -m.uy, m.ux))
    used_m, used_s, rows = set(), set(), []
    for _, i, j, lat, nx, ny in sorted(pairs, key=lambda t: t[0]):
        if i in used_m or j in used_s:
            continue
        used_m.add(i); used_s.add(j)
        rows.append((nx, ny, lat))
    if len(rows) < 2:
        return None, None
    # mínimos cuadrados: n·d = lat  → (NᵀN) d = Nᵀ lat, con descarte robusto de outliers
    for _ in range(2):
        sxx = sum(nx * nx for nx, _, _ in rows); syy = sum(ny * ny for _, ny, _ in rows)
        sxy = sum(nx * ny for nx, ny, _ in rows)
        bx = sum(nx * lat for nx, _, lat in rows); by = sum(ny * lat for _, ny, lat in rows)
        det = sxx * syy - sxy * sxy
        n = len(rows)
        ok_x = sxx > 0.05 * n and det > 1e-3 * (sxx * syy + 1e-12)   # x determinado solo con líneas no verticales… y no paralelas
        ok_y = syy > 0.05 * n and det > 1e-3 * (sxx * syy + 1e-12)
        if ok_x and ok_y:
            dx = (bx * syy - by * sxy) / det; dy = (by * sxx - bx * sxy) / det
        elif syy > sxx:
            dx, dy = None, (by / syy if syy > 0 else None)
        else:
            dx, dy = (bx / sxx if sxx > 0 else None), None
        # descartar residuos grandes (una pareja mal emparejada) y repetir una vez
        resid = [abs(lat - ((dx or 0.0) * nx + (dy or 0.0) * ny)) for nx, ny, lat in rows]
        keep = [r for r, e in zip(rows, resid) if e <= max(0.5, 3 * (sum(resid) / len(resid)))]
        if len(keep) == len(rows) or len(keep) < 2:
            break
        rows = keep
    return dx, dy


def edge_snap_delta(moving: Tuple[float, float, float, float],
                    statics: Sequence[Tuple[float, float, float, float]],
                    tol: float = MAGNET_TOL_PT) -> Optional[Pt]:
    """Imán BORDE con BORDE: si un lado del rectángulo móvil queda a ≤ `tol` del
    lado enfrentado de otra pieza (y se solapan en el otro eje), devuelve el
    desplazamiento que los deja tocándose (solo en ese eje). Gana el más cercano."""
    mx0, my0, mx1, my1 = moving
    best = None
    for sx0, sy0, sx1, sy1 in statics:
        if min(my1, sy1) > max(my0, sy0):                 # se solapan en vertical → costura vertical
            for d in (sx1 - mx0, sx0 - mx1):
                if abs(d) <= tol and (best is None or abs(d) < abs(best[0]) + abs(best[1])):
                    best = (d, 0.0)
        if min(mx1, sx1) > max(mx0, sx0):                 # se solapan en horizontal → costura horizontal
            for d in (sy1 - my0, sy0 - my1):
                if abs(d) <= tol and (best is None or abs(d) < abs(best[0]) + abs(best[1])):
                    best = (0.0, d)
    return best


@dataclass
class Bridge:
    piece_a: int
    a: Pt                       # coords hoja compuesta
    piece_b: int
    b: Pt
    layer_a: str                # nombre OCG completo en el PDF de la pieza A
    layer_b: str
    color: Optional[Tuple[float, float, float]] = None
    width: float = 0.0
    dash: float = 0.0           # largo de guión del linetype (0 = trazo continuo)
    ua: Pt = (0.0, 0.0)         # dirección de salida de cada extremo (para prolongar por su recta)
    ub: Pt = (0.0, 0.0)

    @property
    def length(self) -> float:
        return math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1])

    def polyline(self, rect_a=None, rect_b=None) -> List[Pt]:
        """Trazado del puente: cada extremo sigue RECTO por su propia dirección
        hasta el borde de su pieza (`rect_*`, coords hoja compuesta) y solo ahí
        se cierra con el otro. Así una línea que cruza la costura no cambia de
        rumbo aunque los dos lados difieran una centésima; sin rects es a→b."""
        pts = [self.a]
        a2 = _ray_exit(rect_a, self.a, self.ua) if rect_a else None
        b2 = _ray_exit(rect_b, self.b, self.ub) if rect_b else None
        if a2 is not None and _dist(a2, self.a) > 1e-6:
            pts.append(a2)
        if b2 is not None and _dist(b2, self.b) > 1e-6:
            pts.append(b2)
        pts.append(self.b)
        out: List[Pt] = []
        for q in pts:
            if not out or _dist(out[-1], q) > 1e-6:
                out.append(q)
        return out


def _dist(p: Pt, q: Pt) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _ray_exit(rect: Tuple[float, float, float, float], p: Pt, u: Pt) -> Optional[Pt]:
    """Punto donde el rayo p + t·u (t ≥ 0) sale del rectángulo; None si u es nulo
    o el rayo no avanza hacia ningún lado (queda p)."""
    x0, y0, x1, y1 = rect
    ux, uy = u
    if abs(ux) < 1e-12 and abs(uy) < 1e-12:
        return None
    t = float("inf")
    if ux > 1e-12:
        t = min(t, (x1 - p[0]) / ux)
    elif ux < -1e-12:
        t = min(t, (x0 - p[0]) / ux)
    if uy > 1e-12:
        t = min(t, (y1 - p[1]) / uy)
    elif uy < -1e-12:
        t = min(t, (y0 - p[1]) / uy)
    if not math.isfinite(t) or t < 0:
        return None
    return p[0] + ux * t, p[1] + uy * t


def find_bridges(anchors_by_piece: Dict[int, Sequence[Anchor]], max_gap: float = BRIDGE_MAX_PT,
                 perp_tol: float = BRIDGE_PERP_PT) -> List[Bridge]:
    """Empareja extremos de piezas distintas que se miran de frente sobre la
    misma capa (nombre corto) con desvío lateral ≤ `perp_tol` y hueco ≤
    `max_gap`. Cada extremo participa en UN puente (el más cercano mutuo)."""
    from pdf_layers import short_name

    items = [(pi, a) for pi, lst in anchors_by_piece.items() for a in lst]
    best_for: Dict[int, Tuple[float, int]] = {}
    cands: List[Tuple[float, int, int]] = []
    for i, (pi, a) in enumerate(items):
        for j in range(i + 1, len(items)):
            pj, b = items[j]
            if pi == pj:
                continue
            if short_name(a.layer).casefold() != short_name(b.layer).casefold():
                continue
            if a.ux * b.ux + a.uy * b.uy > -BRIDGE_COS:
                continue
            vx, vy = b.x - a.x, b.y - a.y
            along = vx * a.ux + vy * a.uy
            if along < -perp_tol or along > max_gap:
                continue
            lateral = abs(vx * a.uy - vy * a.ux)
            if lateral > perp_tol:
                continue
            cands.append((along + lateral, i, j))
    cands.sort()
    used = set()
    out: List[Bridge] = []
    for _, i, j in cands:
        if i in used or j in used:
            continue
        used.add(i); used.add(j)
        pi, a = items[i]; pj, b = items[j]
        dashes = [d for d in (a.dash_len, b.dash_len) if d > 0]
        out.append(Bridge(pi, a.xy, pj, b.xy, a.layer, b.layer, a.color or b.color,
                          max(a.width, b.width), min(dashes) if dashes else 0.0,
                          (a.ux, a.uy), (b.ux, b.uy)))
    return out


# ─────────────────────────── materializar ───────────────────────────
def build_document(comp: Composite, docs: Sequence[fitz.Document],
                   hidden_by_source: Optional[Dict[str, Sequence[str]]] = None,
                   bridges: Optional[Sequence[Bridge]] = None) -> fitz.Document:
    """Hoja compuesta como PDF real de una página.

    Cada pieza entra con `show_pdf_page` (vectores, textos y capas intactos).
    Como el XObject no trae catálogo de capas, se reconstruye `/OCProperties`
    con los OCG que graftmap copió y se dejan apagadas (`/OFF`) las capas que
    el usuario ocultó en su PDF de origen. Los `bridges` (puentes entre
    extremos de piezas) se dibujan como trazos vectoriales sobre la MISMA capa
    OCG del extremo, así el reconocimiento los ve como parte de la línea.
    Devuelve el documento abierto."""
    hidden_by_source = hidden_by_source or {}

    def page_sizes(piece: Piece) -> Tuple[float, float]:
        r = docs[piece.source][piece.page].rect
        return r.width, r.height

    width, height, dx, dy = sheet_geometry(comp, page_sizes)
    target = comp.target_scale()
    dst = fitz.open()
    page = dst.new_page(width=width, height=height)
    seen = _ocg_xrefs(dst)
    ocg_source: Dict[int, int] = {}
    for piece in comp.pieces:
        src = docs[piece.source]
        spage = src[piece.page]
        cx0, cy0, cx1, cy1 = clip_rect_pt((spage.rect.width, spage.rect.height), piece.clip)
        visible = fitz.Rect(spage.rect.x0 + cx0, spage.rect.y0 + cy0,
                            spage.rect.x0 + cx1, spage.rect.y0 + cy1)
        # show_pdf_page IGNORA el /Rotate de la hoja origen: trabaja en la hoja
        # sin rotar. El clip se pasa des-rotado y la rotación de la hoja se
        # compensa en `rotate` (positivo = antihorario; /Rotate es horario).
        clip = (visible * spage.derotation_matrix).normalize()
        px0, py0, px1, py1 = piece_rect(piece, page_sizes(piece), target)
        rect = fitz.Rect(px0 + dx, py0 + dy, px1 + dx, py1 + dy)
        page.show_pdf_page(rect, src, piece.page, clip=clip,
                           rotate=piece.rotation - spage.rotation)
        # Franjas blancas que tapan la tinta de la línea de borde (sin capa: el
        # reconocimiento no las ve; los vectores de debajo siguen en el XObject).
        for poly in cover_polygons(piece, page_sizes(piece), target):
            page.draw_polyline([(x + dx, y + dy) for x, y in poly], color=None,
                               fill=(1, 1, 1), closePath=True)
        now = _ocg_xrefs(dst)
        for xref in now - seen:
            ocg_source[xref] = piece.source
        seen = now
    _rebuild_ocproperties(dst, ocg_source, hidden_by_source)
    if bridges:
        by_name: Dict[Tuple[int, str], int] = {}
        for xref, src in ocg_source.items():
            by_name[(src, _ocg_name(dst, xref))] = xref
        for br in bridges:
            src_a = comp.pieces[br.piece_a].source
            xref = by_name.get((src_a, br.layer_a)) or by_name.get(
                (comp.pieces[br.piece_b].source, br.layer_b))
            kw = dict(color=br.color or (0, 0, 0), width=br.width or 0.0)
            if xref:
                kw["oc"] = xref
            ra = piece_rect(comp.pieces[br.piece_a], page_sizes(comp.pieces[br.piece_a]), target)
            rb = piece_rect(comp.pieces[br.piece_b], page_sizes(comp.pieces[br.piece_b]), target)
            pts = [(x + dx, y + dy) for x, y in br.polyline(ra, rb)]
            for p, q in bridge_segments_poly(pts, br.dash):
                page.draw_line(p, q, **kw)
    return dst


def bridge_segments(a: Pt, b: Pt, dash: float, gap_ratio: float = BRIDGE_GAP_RATIO) -> List[Tuple[Pt, Pt]]:
    """Trozos con que se dibuja un puente: continuo si `dash` es 0 o el hueco es
    corto; si no, guiones del largo del linetype con huecos proporcionales,
    para que el núcleo lo vea como la misma línea explotada y no como un trazo
    largo fuera de patrón."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if dash <= 0 or L <= dash * (1.0 + gap_ratio):
        return [(a, b)]
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    gap = dash * gap_ratio
    out: List[Tuple[Pt, Pt]] = []
    t = 0.0
    while t < L - 1e-6:
        e = min(L, t + dash)
        out.append(((a[0] + ux * t, a[1] + uy * t), (a[0] + ux * e, a[1] + uy * e)))
        t = e + gap
    return out


def bridge_segments_poly(pts: Sequence[Pt], dash: float, gap_ratio: float = BRIDGE_GAP_RATIO
                         ) -> List[Tuple[Pt, Pt]]:
    """Como `bridge_segments` pero a lo largo de una polilínea: el patrón de
    guiones sigue de un tramo al siguiente sin reiniciarse."""
    if len(pts) < 2:
        return []
    total = sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if dash <= 0 or total <= dash * (1.0 + gap_ratio):
        return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    period = dash * (1.0 + gap_ratio)
    out: List[Tuple[Pt, Pt]] = []
    walked = 0.0
    for i in range(len(pts) - 1):
        p, q = pts[i], pts[i + 1]
        L = _dist(p, q)
        if L < 1e-9:
            continue
        ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
        t = 0.0
        while t < L - 1e-9:
            phase = (walked + t) % period
            if period - phase < 1e-6:                        # residuo de coma flotante: es el inicio del período
                phase = 0.0
            if phase < dash - 1e-6:                         # dentro de un guión (con margen: sin pasos nulos)
                e = min(L, t + (dash - phase))
                out.append(((p[0] + ux * t, p[1] + uy * t), (p[0] + ux * e, p[1] + uy * e)))
                t = e
            else:                                           # dentro del hueco
                t = min(L, t + max(1e-6, period - phase))
        walked += L
    return out


def page_segments(page: fitz.Page) -> List[Tuple[float, float, float, float]]:
    """Segmentos rectos de la hoja VISIBLE (x0, y0, x1, y1), una sola pasada."""
    rot = page.rotation_matrix
    out: List[Tuple[float, float, float, float]] = []
    for path in page.get_drawings():
        if path.get("type") == "f":
            continue
        for it in path.get("items") or ():
            if it[0] != "l":
                continue
            a = fitz.Point(it[1].x, it[1].y) * rot
            b = fitz.Point(it[2].x, it[2].y) * rot
            out.append((a.x - page.rect.x0, a.y - page.rect.y0,
                        b.x - page.rect.x0, b.y - page.rect.y0))
    return out


def seam_line_extent(page: fitz.Page, piece: Piece, page_size: Tuple[float, float], target: float,
                     side: str, tol: float = SEAM_LINE_TOL_PT, min_len: float = SEAM_LINE_MIN_PT,
                     segments=None):
    """Extremos (inicio, fin) A LO LARGO de la costura de la línea larga que
    corre pegada a ese lado de la pieza —la **match line**—, en coordenadas de la
    hoja compuesta; `None` si no hay.

    Dos hojas contiguas de un plano dibujan LA MISMA match line (la de la hoja de
    al lado), así que sus extremos son la referencia exacta para alinear la
    costura: no hay que adivinar nada ni fiarse de qué guión empareja con cuál."""
    if (piece.rotation % 360.0) != 0.0:
        return None
    x0, y0, x1, y1 = clip_rect_pt(page_size, piece.clip)
    f = (piece.src_scale or target) / target
    if f <= 0:
        return None
    vertical = side in ("left", "right")
    edge = (x0 if side == "left" else x1) if vertical else (y0 if side == "top" else y1)
    groups: Dict[float, List[Tuple[float, float]]] = {}
    for ax, ay, bx, by in (segments if segments is not None else page_segments(page)):
            if vertical:
                if abs(ax - bx) > 0.8 or abs(ay - by) < 2.0:
                    continue
                coord, lo, hi = (ax + bx) / 2.0, min(ay, by), max(ay, by)
            else:
                if abs(ay - by) > 0.8 or abs(ax - bx) < 2.0:
                    continue
                coord, lo, hi = (ay + by) / 2.0, min(ax, bx), max(ax, bx)
            if abs(coord - edge) > tol:
                continue
            groups.setdefault(round(coord, 1), []).append((lo, hi))
    span_lo, span_hi = (y0, y1) if vertical else (x0, x1)
    best = None
    for coord, segs in groups.items():
        lo = min(s0 for s0, _ in segs); hi = max(s1 for _, s1 in segs)
        # Solo cuenta lo que cae DENTRO del recorte: una vertical del perfil o
        # del marco de la hoja no es la match line del plano.
        lo = max(lo, span_lo); hi = min(hi, span_hi)
        if hi - lo < min_len or hi - lo < 0.25 * (span_hi - span_lo):
            continue
        if best is None or (hi - lo) > (best[1] - best[0]):
            best = (lo, hi)
    if best is None:
        return None
    start_pt = (y0 if vertical else x0)      # extremos RELATIVOS al origen de la pieza
    return ((best[0] - start_pt) * f, (best[1] - start_pt) * f)


def seam_line_delta(ext_static, ext_moving, same_tol: float = SEAM_LINE_SAME_PT):
    """Desplazamiento a lo largo de la costura que hace coincidir las dos match
    lines. None si no son la misma línea (largos distintos)."""
    if ext_static is None or ext_moving is None:
        return None
    la = ext_static[1] - ext_static[0]
    lb = ext_moving[1] - ext_moving[0]
    if abs(la - lb) > same_tol or min(la, lb) <= 0:
        return None
    d0 = ext_static[0] - ext_moving[0]
    d1 = ext_static[1] - ext_moving[1]
    if abs(d0 - d1) > same_tol:
        return None
    return (d0 + d1) / 2.0


def seam_along_delta(moving: Sequence[Anchor], static: Sequence[Anchor], axis: int,
                     tol_along: float = SEAM_ALONG_TOL_PT, tol_lat: float = SEAM_LAT_TOL_PT,
                     max_gap: float = BRIDGE_MAX_PT, min_pairs: int = SEAM_MIN_PAIRS):
    """Desplazamiento A LO LARGO de la costura (pt) que pone en línea los extremos
    enfrentados de las dos piezas. `axis` = 0 si la costura es horizontal (las
    piezas se mueven en x) o 1 si es vertical (se mueven en y).

    Es el mismo emparejamiento que usan los puentes —extremos que se miran de
    frente, a ≤ `max_gap`, de la misma capa— pero buscando mucho más lejos a lo
    largo de la costura: tras pegar los bordes, el desfase que queda puede ser de
    decenas de pt (cada hoja se recortó con un margen distinto) y el imán normal,
    limitado al radio de pantalla, no llegaba. Devuelve None si no hay al menos
    `min_pairs` parejas de acuerdo: sin evidencia no se mueve nada."""
    from pdf_layers import short_name

    other = 1 - axis
    props: List[float] = []
    pairs: List[Tuple[float, int, int, float, float]] = []
    for i, m in enumerate(moving):
        for j, s_ in enumerate(static):
            if m.ux * s_.ux + m.uy * s_.uy > -BRIDGE_COS:
                continue                                    # no se miran de frente
            if m.layer and s_.layer and short_name(m.layer).casefold() != short_name(s_.layer).casefold():
                continue                                    # cada línea con la suya
            v = (s_.x - m.x, s_.y - m.y)
            if abs(v[other]) > max_gap or v[other] * (m.ux if other == 0 else m.uy) < -tol_lat:
                continue                                    # el hueco va por delante del extremo
            if abs(v[axis]) > tol_along:
                continue
            cost = abs(v[axis]) + 0.01 * abs(v[other])
            pairs.append((cost, i, j, v[0], v[1]))
    for dx, dy in _mutual(pairs):
        props.append(dy if axis == 1 else dx)
    if len(props) < min_pairs:
        return None
    best: List[float] = []
    for d in props:
        g = [e for e in props if abs(e - d) <= MAGNET_AGREE_PT]
        if len(g) > len(best) or (len(g) == len(best) and g and abs(d) < abs(best[0])):
            best = g
    if len(best) < min_pairs:
        return None
    best.sort()
    return best[len(best) // 2]


def compute_bridges(comp: Composite, docs: Sequence[fitz.Document]) -> List[Bridge]:
    """Puentes de la composición según su estado (`comp.bridges`, `bridge_max_pt`)."""
    if not comp.bridges or len(comp.pieces) < 2:
        return []
    target = comp.target_scale()
    by_piece: Dict[int, List[Anchor]] = {}
    for i, p in enumerate(comp.pieces):
        page = docs[p.source][p.page]
        size = (page.rect.width, page.rect.height)
        by_piece[i] = map_anchors(p, size, target, edge_anchors(page, p.clip, insets=p.covers))
    return find_bridges(by_piece, comp.bridge_max_pt)


def _ocg_xrefs(doc: fitz.Document) -> set:
    out = set()
    for xref in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(xref, "Type")[1] == "/OCG":
                out.add(xref)
        except Exception:
            continue
    return out


def _ocg_name(doc: fitz.Document, xref: int) -> str:
    kind, value = doc.xref_get_key(xref, "Name")
    if kind != "string":
        return str(value or "")
    return str(value)


def _rebuild_ocproperties(doc: fitz.Document, ocg_source: Dict[int, int],
                          hidden_by_source: Dict[str, Sequence[str]]) -> None:
    xrefs = sorted(ocg_source)
    if not xrefs:
        return
    off = []
    for xref in xrefs:
        hidden = set(hidden_by_source.get(str(ocg_source[xref]), ()) or ())
        if hidden and _ocg_name(doc, xref) in hidden:
            off.append(xref)
    refs = " ".join(f"{x} 0 R" for x in xrefs)
    on = " ".join(f"{x} 0 R" for x in xrefs if x not in set(off))
    off_s = " ".join(f"{x} 0 R" for x in off)
    doc.xref_set_key(doc.pdf_catalog(), "OCProperties",
                     f"<< /OCGs [{refs}] /D << /Order [{refs}] /ON [{on}] /OFF [{off_s}] >> >>")
