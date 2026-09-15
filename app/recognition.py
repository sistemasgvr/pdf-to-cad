"""recognition.py — Reconocimiento OCG de utilidades en una hoja PDF (puro, sin Qt).

v1: eléctricas subterráneas (C-ELEC-UNGD*) + bóvedas (C-ELEC-VALT / V-ELEC-*).
No toca config.LAYER_TOKENS ni el modelo de pipes de la app. Devuelve un
RecognitionResult para la vista previa y para importar al editor.

Este módulo decide QUÉ paths entran (por capa OCG y roles confirmados por el
usuario) y convierte coordenadas PDF → píxeles del lienzo. La reconstrucción
geométrica (guiones → corridas → nodos → polilíneas con sus quiebres) vive en
`recognition_geom.py`, puro y testeado con PDFs sintéticos y con el DU06.
"""
from __future__ import annotations

import math
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
DRAW_KINDS = frozenset({"elec_ungd"})
ROLE_LINEAS = "lineas"
ROLE_BUZONES = "buzones"
ROLE_IGNORAR = "ignorar"
# Longitud mínima de una polilínea dibujable (pt PDF) — compatibilidad de API.
MIN_CHAIN_LEN_PT = 8.0
# Distancia máx. (px lienzo) para proyectar una bóveda sobre una pipe.
VAULT_SNAP_PX = 90.0
# No duplicar vértice si ya hay uno cerca (px).
VAULT_NEAR_VERT_PX = 10.0


@dataclass
class RecognizedPolyline:
    layer_ocg: str
    utility_hint: str
    pts_pdf: list  # [(x, y), ...] en pixeles del pixmap a `zoom`
    kind: str      # elec_ungd | elec_ovhd | structure
    # Tipo de cada vértice (mismo largo que pts_pdf): end | corner | bend |
    # junction | tee | vault | curve. Lo usa el import para decidir qué
    # vértices son cajas reales y cuáles solo quiebres (estructura oculta).
    kinds: list = field(default_factory=list)


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
    # QA del núcleo geométrico (todo en px del lienzo):
    coverage: float = 1.0                                   # fracción de guiones cubiertos
    uncovered_px: List[Tuple[Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    offpattern_px: List[List[Tuple[float, float]]] = field(default_factory=list)  # leaders, flechas…
    vault_orphans_px: List[Tuple[float, float]] = field(default_factory=list)      # bóvedas sin línea

    @property
    def drawable(self) -> List[RecognizedPolyline]:
        return [p for p in self.polylines if p.kind in DRAW_KINDS and p.pts_pdf]


def classify_ocg(ocg: Optional[str]) -> Optional[str]:
    """Nombre OCG → kind de reconocimiento, o None si no aplica / telecom."""
    if not ocg:
        return None
    up = ocg.upper()
    if "TELE" in up or "C-TELE" in up:
        return None
    for tok, kind in RECOGNITION_LAYER_TOKENS:
        if tok.upper() in up:
            return kind
    return None


def suggest_layer_role(ocg: str) -> str:
    """Rol sugerido para el diálogo de confirmación."""
    kind = classify_ocg(ocg)
    if kind == "elec_ungd":
        return ROLE_LINEAS
    if kind == "structure":
        return ROLE_BUZONES
    return ROLE_IGNORAR


def roles_from_suggestions(ocg_names: Sequence[str]) -> dict:
    """Construye {lineas:[…], buzones:[…]} a partir de tokens (sin UI)."""
    lineas, buzones = [], []
    for name in ocg_names:
        role = suggest_layer_role(name)
        if role == ROLE_LINEAS:
            lineas.append(name)
        elif role == ROLE_BUZONES:
            buzones.append(name)
    return {ROLE_LINEAS: lineas, ROLE_BUZONES: buzones}


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


def gather_paths(page, kind_for, hidden=()):
    """Paths de la hoja por rol, ya RECORTADOS por los clips del PDF.

    extended=True trae también los CLIPS (marco de la vista de planta, XCLIP de
    referencias). get_drawings() devuelve la geometría sin recortar, así que las
    líneas "superaban el final" visible: se recortan por el polígono de clip
    activo (pila por `level`). Devuelve (line_paths, vault_paths, path_counts,
    kind_by_ocg)."""
    hidden = set(hidden or ())
    path_counts: dict = defaultdict(int)
    kind_by_ocg: dict = {}
    line_paths: List[dict] = []
    vault_paths: List[dict] = []
    page_rect = page.rect
    clip_stack: dict = {}
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
        path_counts[ocg] += 1
        kind_by_ocg[ocg] = kind
        if kind == "structure":
            vault_paths.append(path)
        elif kind == "elec_ungd":
            line_paths.append(path)
    return line_paths, vault_paths, path_counts, kind_by_ocg


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
) -> RecognitionResult:
    """Reconoce utilidades eléctricas en una hoja. Abre el PDF si `doc` es None.

    `hidden_ocgs`: capas OCG ocultas (se saltan por nombre).
    `layer_roles`: ``{"lineas":[ocg…], "buzones":[ocg…]}``. Si es None, se
    usan los tokens ``RECOGNITION_LAYER_TOKENS``.
    """
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
        scale = VP.detect_scale(page)

        def _kind_for(ocg: str) -> Optional[str]:
            if use_roles:
                if ocg in lineas_set:
                    return "elec_ungd"
                if ocg in buzones_set:
                    return "structure"
                return None
            return classify_ocg(ocg)

        line_paths, vault_paths, path_counts, kind_by_ocg = gather_paths(page, _kind_for, hidden)

        ocg_summary = [{
            "ocg": ocg, "kind": kind_by_ocg.get(ocg, ""), "path_count": n,
            "drawn": kind_by_ocg.get(ocg) in DRAW_KINDS,
        } for ocg, n in sorted(path_counts.items(), key=lambda kv: (-kv[1], kv[0]))]

        # — Núcleo geométrico (coords PDF) —
        g = geom.reconstruct(line_paths, vault_paths)
        px = lambda p: _pdf_pt_to_view_px(p[0], p[1], zoom, page)
        line_ocgs = [o for o, k in kind_by_ocg.items() if k == "elec_ungd"]
        layer_tag = line_ocgs[0] if len(line_ocgs) == 1 else " + ".join(sorted(line_ocgs))

        polylines: List[RecognizedPolyline] = []
        for pl in g.polylines:
            pts = [px(p) for p in pl.pts]
            clean, kinds = [], []
            for p, k in zip(pts, pl.kinds):
                if not clean or math.hypot(clean[-1][0] - p[0], clean[-1][1] - p[1]) >= 0.5:
                    clean.append(p); kinds.append(k)
            if len(clean) < 2:
                continue
            polylines.append(RecognizedPolyline(layer_tag, utility, clean, "elec_ungd", kinds))

        # Bóvedas = vértices 'vault' de las polilíneas que SÍ se importan
        # (deduplicados), así siempre coinciden con un vértice real.
        vault_pts: List[Tuple[float, float]] = []
        for pl in polylines:
            for p, k in zip(pl.pts_pdf, pl.kinds):
                if k == "vault" and not any(math.hypot(p[0] - q[0], p[1] - q[1]) < 0.5 for q in vault_pts):
                    vault_pts.append(p)
        orphans_px = [px(g.vaults[i].center) for i in g.vault_orphans]
        uncovered_px = [(px(d.a), px(d.b)) for d in g.uncovered]
        offpattern_px = [[px(p) for p in pl.pts] for pl in g.offpattern]

        for ocg, kind in kind_by_ocg.items():          # stubs informativos (no dibujables)
            if kind in DRAW_KINDS or (kind == "structure" and vault_pts):
                continue
            polylines.append(RecognizedPolyline(ocg, utility, [], kind))

        if not any(p.kind == "elec_ungd" and p.pts_pdf for p in polylines):
            warnings.append("No se encontraron líneas eléctricas subterráneas en esta hoja.")
        if not path_counts:
            warnings.append("Ninguna capa OCG coincidió con los roles / tokens de reconocimiento.")
        if g.n_glyphs:
            warnings.append(
                f"Se omitieron {g.n_glyphs} trazos de marcador/linetype (letras); "
                "solo se dibuja la centerline.")
        if g.n_dashes:
            warnings.append(f"Cobertura de guiones: {g.coverage * 100:.1f}%"
                            + (f" ({len(g.uncovered)} sin cubrir, en naranja)." if g.uncovered else "."))
        if g.offpattern:
            warnings.append(f"Trazos continuos fuera de patrón (leaders/flechas): {len(g.offpattern)} — "
                            "no se importan.")
        if vault_pts:
            warnings.append(f"Bóvedas detectadas: {len(vault_pts)} (ya son vértices de las líneas).")
        if orphans_px:
            warnings.append(f"Bóvedas sin línea cercana: {len(orphans_px)}.")

        roles_out = roles if use_roles else roles_from_suggestions(list(kind_by_ocg.keys()))
        return RecognitionResult(
            utility=utility, page_index=page_index, scale_ft_per_pt=scale,
            polylines=polylines, ocg_summary=ocg_summary, warnings=warnings,
            hidden_ocgs=sorted(hidden), vault_pts=vault_pts, layer_roles=dict(roles_out),
            coverage=g.coverage, uncovered_px=uncovered_px, offpattern_px=offpattern_px,
            vault_orphans_px=orphans_px,
        )
    finally:
        if own_doc and doc is not None:
            doc.close()


def pipes_from_recognition(result: RecognitionResult, layer: str = UTILITY_HINT) -> List[dict]:
    """Convierte polilíneas drawable en dicts de pipe del inventario (como finish_pipe).

    No toca Qt ni la ventana: solo datos. `pts` ya están en coords del lienzo.
    `vertex_kinds` viaja con el pipe para que el import marque como ocultas
    las estructuras de los quiebres que no son bóveda.
    """
    from model import PIPE_DIAMETERS_IN, DEFAULT_PIPE_MATERIAL

    out = []
    for pl in result.drawable:
        pts = [(float(x), float(y)) for x, y in pl.pts_pdf]
        if len(pts) < 2:
            continue
        out.append({
            "layer": layer,
            "pts": pts,
            "ab": False,
            "diam": float(PIPE_DIAMETERS_IN[0]),
            "diam_unit": "in",
            "material": DEFAULT_PIPE_MATERIAL,
            "vertex_kinds": list(pl.kinds) if len(pl.kinds) == len(pts) else [],
            "origen": "reconocido",
        })
    return out
