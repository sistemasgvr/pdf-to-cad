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
DRAW_KINDS = frozenset({"elec_ungd"})
ROLE_LINEAS = "lineas"
ROLE_BUZONES = "buzones"
ROLE_IGNORAR = "ignorar"
# Longitud mínima de una polilínea dibujable (pt PDF) — compatibilidad de API.
MIN_CHAIN_LEN_PT = 8.0
# Un trazo que tras recortarlo por un clip mide menos que esto es una astilla del
# corte (borde de una pieza de la hoja compuesta, marco de vista): se descarta.
CLIP_SLIVER_PT = 1.5
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


def is_abandoned_ocg(ocg: Optional[str]) -> bool:
    """Capa de utilidad ABANDONADA: sufijo de estado NCS «-A» (C-ELEC-UNGD-A)
    o un token explícito (ABND / ABAN / ABANDON)."""
    if not ocg:
        return False
    short = (ocg.split("|")[-1] if "|" in ocg else ocg).strip().upper()
    if short.endswith("-A"):
        return True
    return any(t in short for t in ("ABND", "ABAN", "ABANDON"))


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


def gather_paths(page, kind_for, hidden=(), crop_polygon=None):
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
        if crop_polygon:
            path = geom.clip_path(path, [crop_polygon])
            if path is None:
                continue
        if path.get("clipped") and _path_length(path) < CLIP_SLIVER_PT:
            continue        # astilla que dejó el recorte (p.ej. 0.9 pt de un guión): no es geometría
        path_counts[ocg] += 1
        kind_by_ocg[ocg] = kind
        if kind == "structure":
            vault_paths.append(path)
        elif kind == "elec_ungd":
            line_paths.append(path)
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
    """Reconoce utilidades eléctricas en una hoja. Abre el PDF si `doc` es None.

    `hidden_ocgs`: capas OCG ocultas (se saltan por nombre).
    `layer_roles`: ``{"lineas":[ocg…], "buzones":[ocg…]}``. Si es None, se
    usan los tokens ``RECOGNITION_LAYER_TOKENS``.
    `join_routes`: une tramos de la misma capa en rutas (buena continuación).
    False devuelve las polilíneas tal como las corta el núcleo geométrico.
        `scale_ft_per_pt`: escala fija (hoja compuesta); None = leerla del texto.
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
        scale = float(scale_ft_per_pt) if scale_ft_per_pt else VP.detect_scale(page)
        visual_crop = crop_page_rect(page, crop)
        crop_polygon = drawing_polygon(page, visual_crop) if crop else None

        def _kind_for(ocg: str) -> Optional[str]:
            if use_roles:
                if ocg in lineas_set:
                    return "elec_ungd"
                if ocg in buzones_set:
                    return "structure"
                return None
            return classify_ocg(ocg)

        line_paths, vault_paths, path_counts, kind_by_ocg = gather_paths(
            page, _kind_for, hidden, crop_polygon)

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
        results: List[Tuple[bool, str, object]] = []
        for ocg, paths in sorted(by_ocg.items()):
            results.append((is_abandoned_ocg(ocg), ocg, geom.reconstruct(paths, vault_paths)))
        if not results:
            results = [(False, "", geom.reconstruct([], vault_paths))]

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

        def _emit(pl, ocg, ab, route_id, n_segments):
            pts = [px(p) for p in pl.pts]
            clean, kinds = [], []
            for p, k in zip(pts, pl.kinds):
                if not clean or math.hypot(clean[-1][0] - p[0], clean[-1][1] - p[1]) >= 0.5:
                    clean.append(p); kinds.append(k)
            if len(clean) < 2:
                return None
            clean, kinds, fillets = fit_fillets(clean, kinds, tol_px=FILLET_FIT_TOL_PT * zoom)
            return RecognizedPolyline(
                ocg, utility, clean, "elec_ungd", kinds, abandoned=ab,
                route_id=route_id, n_segments=n_segments, fillets=fillets)

        for ab_layer, ocg, g in results:
            joined = routes_mod.build_routes(g.polylines, g.pattern)
            raw = [routes_mod.Route(pl, 1, [i]) for i, pl in enumerate(g.polylines)]
            mp_joined = geom.marker_pattern([r.pl for r in joined], g.markers)
            mp_raw = geom.marker_pattern([r.pl for r in raw], g.markers)
            layer_has = mp_joined.has_pattern or mp_raw.has_pattern
            ab_by_layer[ocg] = bool(ab_layer and layer_has)

            def _ab(v):
                follows = v if v is not None else layer_has
                return bool(ab_layer and follows)

            for rid, r in enumerate(joined):
                v = mp_joined.verdict[rid]
                rec_pl = _emit(r.pl, ocg, _ab(v), rid, r.n_segments)
                if rec_pl is not None:
                    polylines_joined.append(rec_pl)
                    n_routes += 1
                    n_segments_total += r.n_segments
                    if ab_layer and not _ab(v):
                        n_layer_no_pattern += 1
                    elif not ab_layer and v:
                        n_active_with_pattern += 1
            for rid, r in enumerate(raw):
                rec_pl = _emit(r.pl, ocg, _ab(mp_raw.verdict[rid]), rid, 1)
                if rec_pl is not None:
                    polylines_raw.append(rec_pl)
            uncovered_px += [(px(d.a), px(d.b)) for d in g.uncovered]
            offpattern_px += [[px(p) for p in pl.pts] for pl in g.offpattern]
            n_dashes += g.n_dashes; n_glyphs += g.n_glyphs
            n_uncovered += len(g.uncovered); n_offpattern += len(g.offpattern)
            covered_w += g.coverage * g.n_dashes
            for i, v in enumerate(g.vaults):
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

        stubs = []
        for ocg, kind in kind_by_ocg.items():          # stubs informativos (no dibujables)
            if kind in DRAW_KINDS or (kind == "structure" and vault_pts):
                continue
            stubs.append(RecognizedPolyline(ocg, utility, [], kind))
        polylines.extend(stubs)
        polylines_joined.extend(stubs)
        polylines_raw.extend(stubs)

        if not any(p.kind == "elec_ungd" and p.pts_pdf for p in polylines):
            warnings.append("No se encontraron líneas eléctricas subterráneas en esta hoja.")
        if not path_counts:
            warnings.append("Ninguna capa OCG coincidió con los roles / tokens de reconocimiento.")
        n_ab = sum(1 for p in polylines if p.kind == "elec_ungd" and p.pts_pdf and p.abandoned)
        if n_ab:
            warnings.append(f"Utilidades abandonadas (capa «-A» + patrón «/»): {n_ab} — se importan marcadas (AB).")
        if n_layer_no_pattern:
            warnings.append(f"Capa «-A» sin el patrón de marcadores «/» a lo largo de la línea: "
                            f"{n_layer_no_pattern} — NO se marcan como abandonadas.")
        if n_active_with_pattern:
            warnings.append(f"Patrón de marcadores «/» en una capa ACTIVA: {n_active_with_pattern} línea(s) "
                            "— se importan activas (manda la capa); revisar.")
        if n_segments_total > n_routes:
            warnings.append(
                f"Rutas: {n_routes} (unen {n_segments_total} tramos de la misma capa).")
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

        roles_out = roles if use_roles else roles_from_suggestions(list(kind_by_ocg.keys()))
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


def _arc_spans(kinds):
    """Tramos [lo, hi] que son CURVA del PDF: una ristra de vértices `curve`
    (interiores de un trazo curvo) —admitiendo un nodo intermedio entre dos
    ristras `curve` (dos trazos curvos encadenados)— más el vértice a cada
    lado, que es el extremo real del trazo curvo (punto de tangencia). Un
    `corner`/`bend` fuera de eso es una esquina recta y NO forma parte del arco."""
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
            break
        lo, hi = i - 1, j + 1                    # extremos del trazo curvo
        if lo >= 0 and hi < n:
            spans.append((lo, hi))
        i = j + 1
    return spans


def _leg_lines(pts, kinds, i_end, step, slip):
    """Rectas candidatas del tramo RECTO que llega al arco (step=-1, i_end =
    lo-1) o sale de él (step=+1, i_end = hi+1), en orden de preferencia:
    [(punto, dirección unitaria hacia el arco, índice del vértice ancla)].
    Si el vecino del arco es un `bend`/`corner` pegado a él (leg < slip), el
    tramo vecino→extremo del trazo curvo suele ser el empalme run↔curva o el
    salto sobre un hueco/letra del linetype, NO tinta recta: se prueba primero
    la recta del guión anterior (que sí es tinta y pasa por el vecino) y solo
    si el arco no le es tangente se usa la del empalme. DU06 h.4: con el
    empalme la tangente salía 4.75° torcida y la esquina 3.7 pt fuera."""
    v = pts[i_end]; a0 = pts[i_end - step]              # a0 = extremo del trazo curvo
    u = _unit(a0[0] - v[0], a0[1] - v[1])
    out = []
    j = i_end + step
    if 0 <= j < len(pts) and kinds[i_end] in ("bend", "corner") and math.dist(v, a0) < slip:
        w = pts[j]
        u2 = _unit(v[0] - w[0], v[1] - w[1])
        if u2 != (0.0, 0.0):
            out.append((w, u2, j))
    if u != (0.0, 0.0):
        out.append((v, u, i_end))
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


def fit_fillets(pts, kinds, tol_px: float = 1.0, tan_tol: float = None, debug=None):
    """Sustituye cada codo por su esquina C (intersección de las rectas que
    llegan y salen) con kind «fillet», y guarda A/B (puntos de tangencia),
    centro y radio. Nada se inventa: el arco es EXACTAMENTE un trazo curvo del
    PDF (vértices `curve` del núcleo + sus extremos, ver `_arc_spans`), las
    rectas son las de los guiones del plano (`_leg_line`) y el círculo es el
    TANGENTE a esas dos rectas que pasa por los vértices del trazo curvo
    (`_fit_circle_tangent`, RMS ≤ tol). A y B salen de C, las rectas y r
    (T = r·tan(Δ/2)) — exactamente lo que dibuja el editor y genera el plugin.
    Si la curva no es un arco de círculo tangente a sus rectas, se deja como
    polilínea. Devuelve (pts, kinds, fillets)."""
    pts = list(pts); kinds = list(kinds)
    n = len(pts)
    if n < 4:
        return pts, kinds, {}
    slip = FILLET_TANGENT_SLIP_PX * (tol_px / FILLET_FIT_TOL_PT)

    def _try_span(lo, hi, seed):
        """Codo para el tramo [lo, hi] con la semilla (cx0, cy0, r0) del ajuste
        libre. Devuelve la entrada del plan o None (con el motivo en `debug`)."""
        cx0, cy0, r0 = seed
        members = pts[lo:hi + 1]
        A0, B0 = pts[lo], pts[hi]
        chosen = None
        for (P, ua, ia) in _leg_lines(pts, kinds, lo - 1, -1, slip):
            for (N, ub_in, ib) in _leg_lines(pts, kinds, hi + 1, +1, slip):
                ub = (-ub_in[0], -ub_in[1])             # dirección de avance al salir del arco
                turn = math.degrees(math.acos(max(-1.0, min(1.0, ua[0] * ub[0] + ua[1] * ub[1]))))
                if turn < FILLET_MIN_TURN_DEG:
                    if debug is not None: debug.append((lo, hi, 'giro', round(turn, 1)))
                    continue
                C = _isect_lines(P, ua, N, ub)
                if C is None:
                    continue
                # círculo tangente a las dos rectas que pasa por el trazo curvo
                phi = math.pi - math.radians(turn)
                s0 = r0 / max(1e-6, math.sin(phi / 2.0))
                fit_t = _fit_circle_tangent(members, C, ua, ub, s0)
                if fit_t is None:
                    continue
                cx, cy, r, rms = fit_t
                if rms > tol_px or r < 2 * tol_px:
                    if debug is not None: debug.append((lo, hi, 'recta no tangente al arco', ia, ib, round(rms, 2)))
                    continue
                chosen = (P, ua, ia, N, ub, ib, turn, C, cx, cy, r)
                break
            if chosen:
                break
        if chosen is None:
            return None
        P, ua, ia, N, ub, ib, turn, C, cx, cy, r = chosen
        T = r * math.tan(math.radians(turn) / 2.0)
        A = (C[0] - ua[0] * T, C[1] - ua[1] * T); B = (C[0] + ub[0] * T, C[1] + ub[1] * T)
        # el punto de tangencia debe quedar donde la tinta pasa de recta a curva:
        # cerca del extremo del trazo curvo o del último vértice recto (entre
        # ambos puede haber un hueco/letra del linetype sin tinta)
        V0, W0 = pts[lo - 1], pts[hi + 1]
        if min(math.dist(A, A0), math.dist(A, V0)) > slip or min(math.dist(B, B0), math.dist(B, W0)) > slip:
            if debug is not None: debug.append((lo, hi, 'tangencia lejos del extremo'))
            return None
        # orden: P … A … C … B … N a lo largo de cada recta
        if (A[0] - P[0]) * ua[0] + (A[1] - P[1]) * ua[1] <= 0 or (N[0] - B[0]) * ub[0] + (N[1] - B[1]) * ub[1] <= 0:
            if debug is not None: debug.append((lo, hi, 'orden'))
            return None
        return (lo, hi, C, A, B, (cx, cy), r, ia, ib)

    plan = []                                   # (lo, hi, C, A, B, centro, R, ia, ib)
    for lo, hi in _arc_spans(kinds):
        if lo <= 0 or hi >= n - 1:
            if debug is not None: debug.append((lo, hi, 'sin recta tangente'))
            continue                            # el arco nace/muere en el extremo: no hay recta tangente
        fit = _fit_circle(pts[lo:hi + 1])       # ajuste libre: solo como semilla y filtro grueso
        if fit is None:
            continue
        cx0, cy0, r0, rms0 = fit
        if rms0 > tol_px or r0 < 2 * tol_px:
            if debug is not None: debug.append((lo, hi, 'no es arco de círculo', round(rms0, 2)))
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
            entry = _try_span(span[0], span[1], (cx0, cy0, r0))
            if entry is not None:
                break
        if entry is not None:
            plan.append(entry)
    if not plan:
        return pts, kinds, {}
    out_pts, out_kinds, fillets = [], [], {}
    plan.sort()
    # Los `bend` de empalme que quedaron DENTRO de la recta (ia < lo-1 o ib > hi+1)
    # se absorben: la recta ya pasa por el vértice anterior/siguiente.
    skip = set()
    for lo, hi, C, A, B, ctr, r, ia, ib in plan:
        skip.update(range(ia + 1, lo)); skip.update(range(hi + 1, ib))
    k = 0; q = 0
    while k < n:
        if q < len(plan) and k == plan[q][0]:
            lo, hi, C, A, B, ctr, r, ia, ib = plan[q]
            out_pts.append(C); out_kinds.append("fillet")
            fillets[len(out_pts) - 1] = {"a": A, "b": B, "center": ctr, "r_px": r}
            k = hi + 1; q += 1
            continue
        if k not in skip:
            out_pts.append(pts[k]); out_kinds.append(kinds[k])
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
            out.append({
                "center": px((cx, cy)),
                "corners": corners,
                "shape": v.shape,
                "width_ft": round(v.width * scale, 3),
                "length_ft": round(v.length * scale, 3),
                "angle_deg": round(v.angle_deg, 2),
                "orphan": vault_orph.get(key, 0) == vault_seen.get(key, 0),
                "abandoned": abandoned,
            })
    return out


def pipes_from_recognition(result: RecognitionResult, layer: str = UTILITY_HINT,
                           zoom: float = 1.0) -> List[dict]:
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
    return out
