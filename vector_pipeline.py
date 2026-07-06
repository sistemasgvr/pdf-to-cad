"""
vector_pipeline.py — Extracción de geometría y texto de PDFs CAD vectorizados.

Estrategia:
  - La capa de cada trazo viene del nombre OCG del PDF (fiable), NO del color.
  - Glifos de letra SHX (marcadores W/G/SS/T sobre las líneas) se suprimen.
  - Trazos de un solo segmento -> al fusionador (puentea huecos de marcadores).
  - Trazos multi-segmento (curvas) -> polilínea única (preserva la forma).
  - El texto se extrae con altura y rotación reales, filtrando membrete/cotas.

Parámetros en config.py.
"""
import fitz
import math
import re
from collections import Counter, defaultdict

import config as C


# ─────────────────────────────────────────────────────────────────────────────
# Tokens de línea de servicio  (--W--, --SS--, --E(OH)--, ...)
# ─────────────────────────────────────────────────────────────────────────────
# Token base delimitado por guiones/espacios (no por letras), con sufijo aéreo
# "(OH)" opcional. Tolerante a variaciones de OCR: guiones largos (– — ―), espacios
# extra, may/min y puntos ("O.H."). SD/SS van antes que las de una letra.
_SERVICE_TOKEN_RE = re.compile(
    r'(?<![A-Za-z])'                    # no precedido por letra (evita palabras)
    r'(SD|SS|W|G|E|T)'                  # token base
    r'\s*(\(\s*O\.?\s*H\.?\s*\))?'      # sufijo aéreo (OH) opcional
    r'(?![A-Za-z])',                    # no seguido por letra
    re.I,
)


def normalize_service_token(text):
    """Reconoce un token de línea de servicio ('--W--', '- SS -', '─G─', 'T(OH)',
    'E (OH)') tolerante a variaciones de OCR y devuelve el token canónico de
    C.SERVICE_LINE_COLORS (W/SS/SD/G/E/T/E(OH)/T(OH)) o None."""
    if not text:
        return None
    s = str(text).upper().replace("–", "-").replace("—", "-").replace("―", "-")
    m = _SERVICE_TOKEN_RE.search(s)
    if not m:
        return None
    base = m.group(1).upper()
    overhead = m.group(2) is not None
    if overhead and base in ("E", "T"):
        return f"{base}(OH)"
    return base


def service_line_layer(token):
    """Token canónico -> capa DXF (según C.SERVICE_LINE_COLORS), o None."""
    info = getattr(C, "SERVICE_LINE_COLORS", {}).get(token)
    return info[0] if info else None


def is_abandoned_ocg(ocg):
    """True si el nombre OCG marca una utilidad ABANDONADA (ej. …-EXIS-ABAND)."""
    if not getattr(C, "ABANDONED_ENABLED", False):
        return False
    up = (ocg or "").upper()
    return any(tok.upper() in up for tok in getattr(C, "ABANDONED_OCG_TOKENS", []))


def abandoned_layer(layer):
    """Nombre de la capa gris de abandono para una capa de utilidad."""
    return layer + getattr(C, "ABANDONED_LAYER_SUFFIX", "_ABANDONADO")


# ─────────────────────────────────────────────────────────────────────────────
# Resolución de capa
# ─────────────────────────────────────────────────────────────────────────────
def layer_for(ocg):
    """Nombre OCG del PDF -> capa de salida (o None para descartar)."""
    up = (ocg or "").upper()
    for tok, layer in C.LAYER_TOKENS:
        if tok.upper() in up:
            return layer
    # Fallback: si el nombre OCG trae un token de línea de servicio (--W--, --SD--,
    # --E(OH)--) sin haber coincidido arriba, clasificar por ese token.
    tok = normalize_service_token(up)
    if tok:
        mapped = service_line_layer(tok)
        if mapped:
            return mapped
    return C.FALLBACK_LAYER


def color_layer(color):
    """Color de trazo RGB (0..1) -> capa, para PDFs vectoriales APLANADOS sin
    capas OCG. Devuelve VECTOR_COLOR_DEFAULT si no coincide con ninguno."""
    if color is not None:
        tol = C.VECTOR_COLOR_TOL
        for rgb, layer in C.VECTOR_COLOR_LAYER_MAP:
            if all(abs(a - b) <= tol for a, b in zip(color, rgb)):
                return layer
    return C.VECTOR_COLOR_DEFAULT


def classify_linetype_from_dashes(path):
    """Mapea el patrón de guiones del PDF (path['dashes']) al linetype estándar
    más parecido: CONTINUOUS / DASHED / CENTER / DASHDOT."""
    d = path.get("dashes")
    if not d:
        return "CONTINUOUS"
    nums = [float(x) for x in re.findall(r'[\d.]+', str(d).split("]")[0])]
    if not nums or all(v == 0 for v in nums):
        return "CONTINUOUS"
    if len(nums) >= 6:
        return "CENTER"          # raya-punto-raya (eje)
    if len(nums) == 4:
        return "DASHDOT"         # raya-punto
    return "DASHED"              # raya-hueco


def is_marker_glyph(path):
    """True si el path es un marcador de letra ('W','T','(OH)'...) sobre la línea:
    varios segmentos (o curvas) dentro de un bbox pequeño. Los guiones reales de la
    tubería son de 1 segmento; las curvas de tubería tienen bbox grande."""
    items = path.get("items", [])
    if len(items) < 2:
        return False
    r = path.get("rect")
    if r is None:
        return False
    if max(r.x1 - r.x0, r.y1 - r.y0) >= C.MARKER_GLYPH_MAX_DIM_PT:
        return False
    cmds = [i[0] for i in items]
    n_l = sum(1 for c in cmds if c == "l")
    return n_l > 2 or any(c == "c" for c in cmds)


def overlay_layer_for(color):
    """Color de una MARCA (overlay) -> capa destino, o None si no es marca."""
    if color is None:
        return None
    tol = getattr(C, "VECTOR_OVERLAY_TOL", 0.16)
    for rgb, layer in getattr(C, "VECTOR_OVERLAY_LAYER_MAP", []):
        if all(abs(a - b) <= tol for a, b in zip(color, rgb)):
            return layer
    return None


def is_fill_glyph(path):
    """True si el trazo es una LETRA dibujada como relleno (vector aplanado sin
    texto vivo): solo-relleno, sin borde, bbox pequeño y con CURVAS o muchos
    vértices. Las PUNTAS DE FLECHA (triángulos: pocos segmentos rectos, sin
    curvas) se CONSERVAN para que las flechas terminen en punta."""
    if path.get("fill") is None or path.get("color") is not None:
        return False
    r = path.get("rect")
    if r is None or (r.x1 - r.x0) * (r.y1 - r.y0) >= C.VECTOR_FILL_GLYPH_MAX_AREA_PT:
        return False
    cmds = [i[0] for i in path.get("items", [])]
    n_lines = sum(1 for c in cmds if c == "l")
    has_curve = any(c == "c" for c in cmds)
    # Triángulo de flecha: sin curvas y <=4 segmentos rectos -> conservar.
    if not has_curve and n_lines <= 4:
        return False
    return True   # glifo de texto (curvas o muchos vértices) -> descartar


def setup_linetypes(dxf):
    """Crea los tipos de línea de utilidad (con letra embebida) y asegura los
    estándar. Idempotente. Debe llamarse antes de crear capas."""
    for var, val in (("$LTSCALE", C.LINETYPE_SCALE), ("$CELTSCALE", 1.0),
                     ("$MSLTSCALE", 1), ("$PSLTSCALE", 1)):
        try:
            dxf.header[var] = val
        except Exception:
            pass

    # Interruptor: tipos de línea personalizados con letra desactivados.
    # Sin crearlos, ensure_layer cae a CONTINUOUS para AGUA/GAS/etc.
    if not C.USE_CUSTOM_LINETYPES:
        return

    # Estilo de texto para las letras del linetype.
    if "LTSTD" not in dxf.styles:
        dxf.styles.add("LTSTD", font=C.TEXT_FONT)

    d, g, h = C.UTIL_LT_DASH, C.UTIL_LT_GAP, C.UTIL_LT_TEXT_H
    total = d + g + g
    for lt_name, letter in C.UTIL_LINETYPE_MARKERS.items():
        if lt_name in dxf.linetypes:
            continue
        # Patrón complejo AutoCAD: raya, hueco, [texto], hueco.
        x_off = -(g * 0.5 + h * 0.3 * len(letter))   # centra la letra en el hueco
        pattern = (
            f'A,{d},-{g},["{letter}",LTSTD,S={h},R=0.0,'
            f'X={x_off:.2f},Y={-h/2:.2f}],-{g}'
        )
        try:
            dxf.linetypes.add(
                lt_name, pattern=pattern,
                description=f"Utilidad {letter} " + "-" * 6 + letter + "-" * 6,
                length=total,
            )
        except Exception:
            # Fallback: linetype discontinuo simple si el complejo falla.
            dxf.linetypes.add(lt_name, pattern=[total, d, -(total - d)],
                              description=f"Utilidad {letter}")


def ensure_layer(dxf, name):
    if name and name not in dxf.layers:
        # Capas de líneas ABANDONADAS (…_ABANDONADO): gris, CONTINUOUS.
        suffix = getattr(C, "ABANDONED_LAYER_SUFFIX", "_ABANDONADO")
        if suffix and name.endswith(suffix):
            dxf.layers.add(name, color=getattr(C, "ABANDONED_COLOR", 8),
                           linetype="CONTINUOUS")
            return
        # Modo fiel: TODAS las capas salen CONTINUOUS (el aspecto discontinuo lo dan
        # los propios trazos del PDF, no un linetype de capa).
        if getattr(C, "VECTOR_FAITHFUL_GEOMETRY", False):
            ltype = "CONTINUOUS"
        else:
            ltype = C.LAYER_LINETYPE.get(name, "CONTINUOUS")
            # Los UTIL_* (letra) dependen del interruptor; los ESTÁNDAR (DASHED,
            # CENTER2, ...) se aplican siempre si existen en el documento.
            if ltype.startswith("UTIL_") and not C.USE_CUSTOM_LINETYPES:
                ltype = "CONTINUOUS"
        if ltype not in dxf.linetypes:
            ltype = "CONTINUOUS"       # seguridad: el linetype debe existir
        dxf.layers.add(name, color=C.OUTPUT_LAYERS.get(name, 7), linetype=ltype)


# ─────────────────────────────────────────────────────────────────────────────
# Escala
# ─────────────────────────────────────────────────────────────────────────────
_SCALE_EQ_RE = re.compile(r'1\s*["\']?\s*=\s*(\d+(?:\.\d+)?)\s*[\'`]?', re.I)
_SCALE_RATIO_RE = re.compile(r'1\s*:\s*(\d+)')


def detect_scale(page):
    """Lee la escala del texto del plano (1\"=20', 1:240). Devuelve pies/punto.

    Un plano suele traer VARIAS escalas: la del dibujo principal y la de mapas
    índice/locator (p.ej. 1\"=1500'). Se prioriza la escala de trabajo:
      1) override manual (config.SCALE_FT_PER_PT_OVERRIDE)
      2) escalas dentro del rango de trabajo [SCALE_WORKING_MIN, MAX] pie/pulg
      3) entre esas, la más frecuente; en empate, la más detallada (menor)
    """
    if getattr(C, "SCALE_FT_PER_PT_OVERRIDE", None):
        return C.SCALE_FT_PER_PT_OVERRIDE

    found = []   # lista de (pies por pulgada)
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                txt = (span.get("text") or "").strip()
                m = _SCALE_EQ_RE.search(txt)
                if m:
                    found.append(float(m.group(1)))          # 1"=X'  -> X pie/pulg
                    continue
                m = _SCALE_RATIO_RE.search(txt)
                if m:
                    found.append(float(m.group(1)) / 12.0)   # 1:N -> N/12 pie/pulg
    if not found:
        return C.DEFAULT_SCALE_FT_PER_PT

    working = [v for v in found if C.SCALE_WORKING_MIN <= v <= C.SCALE_WORKING_MAX]
    pool = working or found
    counts = Counter(round(v, 6) for v in pool)
    top = max(counts.values())
    best = min(v for v, n in counts.items() if n == top)   # empate -> más detallada
    return best / 72.0


# ─────────────────────────────────────────────────────────────────────────────
# Transformación de coordenadas (todas las rotaciones de página)
# ─────────────────────────────────────────────────────────────────────────────
class CoordTransform:
    def __init__(self, page, scale):
        self.rot, self.scale = page.rotation, scale
        mb = page.mediabox
        self.W, self.H = mb.width, mb.height

    def point(self, px, py):
        s, r, W, H = self.scale, self.rot, self.W, self.H
        if r == 0:
            return px * s, (H - py) * s
        elif r == 90:
            return py * s, px * s
        elif r == 180:
            return (W - px) * s, py * s
        else:  # 270
            return py * s, px * s

    def pt(self, p):
        return self.point(p.x, p.y)

    def dir_to_angle(self, dir_vec):
        dx, dy = dir_vec
        if self.rot == 0:
            a = math.atan2(-dy, dx)
        elif self.rot == 180:
            a = math.atan2(dy, -dx)
        else:
            a = math.atan2(dx, dy)
        return math.degrees(a) % 360

    def origin_to_cad(self, ox, oy):
        return self.point(ox, oy)


# ─────────────────────────────────────────────────────────────────────────────
# Supresión de glifos SHX  (ventana de área 5 < area < 80 pt²)
# ─────────────────────────────────────────────────────────────────────────────
def is_shx_glyph(path):
    items = path.get("items", [])
    if not items:
        return False
    r = path.get("rect")
    if r is None:
        return False
    area = (r.x1 - r.x0) * (r.y1 - r.y0)
    if area <= C.SHX_AREA_MIN or area >= C.SHX_AREA_MAX:
        return False
    cmds = [i[0] for i in items]
    if path.get("fill") is None and all(c == "l" for c in cmds) and len(cmds) > 2:
        return True
    if path.get("fill") is not None and all(c in ("c", "m", "re") for c in cmds) and len(cmds) > 3:
        return True
    return False


def flatten_bezier(p0, p1, p2, p3, steps=C.BEZIER_STEPS):
    """Aplana una Bézier cúbica p0->p3 (controles p1,p2). Devuelve los puntos
    para t en (0, 1]; incluye el punto final exacto p3, excluye el inicial p0
    (que ya está en la polilínea)."""
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        bx = mt ** 3 * p0.x + 3 * mt ** 2 * t * p1.x + 3 * mt * t ** 2 * p2.x + t ** 3 * p3.x
        by = mt ** 3 * p0.y + 3 * mt ** 2 * t * p1.y + 3 * mt * t ** 2 * p2.y + t ** 3 * p3.y
        pts.append(fitz.Point(bx, by))
    return pts


# ─────────────────────────────────────────────────────────────────────────────
# Fusión de segmentos colineales -> polilíneas
# ─────────────────────────────────────────────────────────────────────────────
class LayerSegmentCollector:
    """Acumula segmentos sueltos por capa (en coords PDF) y polilíneas ya
    transformadas (coords CAD). flush() fusiona los segmentos colineales."""

    def __init__(self):
        self.segments = defaultdict(list)   # capa -> [(p0, p1) en coords PDF]
        self.polylines = defaultdict(list)  # capa -> [ [pts CAD] ]

    def add_line(self, layer, p0, p1):
        # Descartar segmentos degenerados (longitud ~0)
        if abs(p0.x - p1.x) < C.DEGENERATE_EPS_PT and abs(p0.y - p1.y) < C.DEGENERATE_EPS_PT:
            return
        self.segments[layer].append((p0, p1))

    def add_polyline(self, layer, cad_pts, ltype=None):
        # Eliminar puntos consecutivos repetidos (degenerados)
        eps = C.DEGENERATE_EPS_PT
        clean = []
        for p in cad_pts:
            if not clean or abs(clean[-1][0] - p[0]) >= eps or abs(clean[-1][1] - p[1]) >= eps:
                clean.append((p[0], p[1]) if not hasattr(p, "x") else (p.x, p.y))
        if len(clean) >= 2:
            self.polylines[layer].append((clean, ltype))

    def flush(self, msp, dxf, T):
        n = 0
        drop = getattr(C, "DROP_LAYERS", set())
        # Modo fiel: NO filtrar por ruido — se conservan las tramas/gráficos de
        # trazos diminutos (p.ej. domo truncado, achurados) tal cual el PDF.
        if getattr(C, "VECTOR_FAITHFUL_GEOMETRY", False):
            noise_pt = 0.0
        else:
            noise_pt = getattr(C, "VECTOR_NOISE_MIN_PT", 0.0)
        noise_ft = noise_pt * T.scale
        util_layers = getattr(C, "UTILITY_LINE_LAYERS", set())

        std_scale = getattr(C, "LINETYPE_STD_SCALE", 30.0)
        tol = max(getattr(C, "STITCH_TOL_PT", 12.0) * T.scale, 1.0)
        faithful = getattr(C, "VECTOR_FAITHFUL_GEOMETRY", False)

        # Guiones fusionados -> piezas CAD por capa. (En modo fiel self.segments
        # está vacío: todo entró como polilíneas sin fusionar.)
        seg_pieces = defaultdict(list)
        for layer, segs in self.segments.items():
            if layer in drop:
                continue
            clean_markers = (C.CLEAN_UTILITY_MARKERS and not faithful
                             and layer in C.UTILITY_CLEAN_LAYERS)
            for (a, b, count, span) in merge_collinear_segments(segs):
                if (clean_markers and count <= C.MARKER_MAX_SEGMENTS
                        and span < C.MARKER_MAX_LEN_PT):
                    continue
                if math.hypot(a.x - b.x, a.y - b.y) < noise_pt:
                    continue
                seg_pieces[layer].append([T.pt(a), T.pt(b)])

        def _emit(pts, layer, ltype=None):
            att = {"layer": layer}
            if ltype and ltype != "CONTINUOUS":
                att["linetype"] = ltype
            e = (msp.add_line(pts[0], pts[1], dxfattribs=att) if len(pts) == 2
                 else msp.add_lwpolyline(pts, dxfattribs=att))
            if ltype and ltype != "CONTINUOUS":
                try: e.dxf.ltscale = std_scale
                except Exception: pass

        for layer in set(seg_pieces) | set(self.polylines):
            if layer in drop:
                continue
            ensure_layer(dxf, layer)
            if layer in util_layers and not faithful:
                # TUBERÍA: coser guiones + polilíneas en UN elemento (letra por linetype de capa).
                pcs = list(seg_pieces.get(layer, []))
                for pts, _lt in self.polylines.get(layer, []):
                    if _poly_len(pts) >= noise_ft:
                        pcs.append([(p[0], p[1]) for p in pts])
                for pts in chain_pieces(pcs, tol):
                    if len(pts) >= 2:
                        _emit(pts, layer); n += 1
            else:
                # NO tubería: guiones continuos + polilíneas con su linetype detectado.
                for pts in seg_pieces.get(layer, []):
                    _emit(pts, layer); n += 1
                for pts, lt in self.polylines.get(layer, []):
                    if _poly_len(pts) >= noise_ft:
                        _emit([(p[0], p[1]) for p in pts], layer, lt); n += 1
        return n


def chain_pieces(pieces, tol):
    """Cose piezas (listas de puntos CAD) en polilíneas continuas: une las que
    comparten un extremo (a <= tol). Así cada tubería queda como UN solo elemento.
    Las ramas separadas quedan como polilíneas distintas."""
    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    remaining = [list(p) for p in pieces if len(p) >= 2]
    result = []
    while remaining:
        chain = remaining.pop()
        extended = True
        while extended:
            extended = False
            for i in range(len(remaining) - 1, -1, -1):
                pc = remaining[i]
                for cand in (pc, pc[::-1]):
                    if key(cand[0]) == key(chain[-1]):
                        chain.extend(cand[1:]); remaining.pop(i); extended = True; break
                    if key(cand[-1]) == key(chain[0]):
                        chain[:0] = cand[:-1]; remaining.pop(i); extended = True; break
                if extended:
                    break
        result.append(chain)
    return result


def merge_collinear_segments(segs):
    """Agrupa por rumbo y posición perpendicular; fusiona los consecutivos
    cuyo hueco <= MERGE_MAX_BRIDGE_PT. Entrada/salida en coords PDF."""
    buckets = defaultdict(list)
    for (p0, p1) in segs:
        dx, dy = p1.x - p0.x, p1.y - p0.y
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        nx, ny = -dy / length, dx / length          # normal unitaria
        perp = p0.x * nx + p0.y * ny                # distancia perpendicular al origen
        akey = round(ang / C.MERGE_ANGLE_TOL_DEG)
        pkey = round(perp / max(C.MERGE_PERP_TOL_PT, 1e-6))
        buckets[(akey, pkey)].append((p0, p1, ang))

    out = []   # (p0, p1, count_segmentos, span_longitud)
    for (akey, _pkey), group in buckets.items():
        ang = group[0][2]
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        # Proyecta extremos sobre la dirección de la línea
        proj = []
        for (p0, p1, _a) in group:
            t0 = p0.x * ux + p0.y * uy
            t1 = p1.x * ux + p1.y * uy
            lo, hi = (p0, p1) if t0 <= t1 else (p1, p0)
            proj.append((min(t0, t1), max(t0, t1), lo, hi))
        proj.sort(key=lambda r: r[0])

        cs, ce, cp0, cp1, cnt = proj[0][0], proj[0][1], proj[0][2], proj[0][3], 1
        for (s, e, lo, hi) in proj[1:]:
            if s <= ce + C.MERGE_MAX_BRIDGE_PT:    # continúa la misma línea
                cnt += 1
                if e > ce:
                    ce, cp1 = e, hi
            else:
                out.append((cp0, cp1, cnt, ce - cs))
                cs, ce, cp0, cp1, cnt = s, e, lo, hi, 1
        out.append((cp0, cp1, cnt, ce - cs))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Procesar un trazo
# ─────────────────────────────────────────────────────────────────────────────
def _inside_text_box(path, text_boxes, margin=3.0):
    """True si el trazo es geometría pequeña contenida en una caja de texto OCR
    (= un trazo de letra del rótulo original). No suprime líneas largas (su bbox
    se sale de la caja) ni trazos de color (utilidades)."""
    color = path.get("color")
    if color is not None and tuple(round(c, 2) for c in color) != (0.0, 0.0, 0.0):
        return False   # solo se suprime texto negro/sin color
    r = path.get("rect")
    if r is None:
        return False
    for (bx0, by0, bx1, by1) in text_boxes:
        if (r.x0 >= bx0 - margin and r.y0 >= by0 - margin and
                r.x1 <= bx1 + margin and r.y1 <= by1 + margin):
            return True
    return False


def process_path(collector, path, dxf, T, has_ocg=True, text_boxes=None, zones=None):
    faithful = getattr(C, "VECTOR_FAITHFUL_GEOMETRY", False)
    # Modo fiel: NO suprimir glifos de letra (W/G/SS…) — se dibujan como en el PDF.
    if is_shx_glyph(path) and not faithful:
        return
    # Zona de exclusión (leyenda de pothole / membrete): no digitalizar su geometría.
    if _path_in_zones(path, zones):
        return
    ocg = path.get("layer", "") or ""
    if has_ocg:
        layer = layer_for(ocg)
    else:
        # Las MARCAS de color (overlays) NO se dibujan: se usan aparte para
        # etiquetar la línea negra de abajo.
        if overlay_layer_for(path.get("color")) is not None:
            return
        # Vector aplanado (sin capas OCG): clasificar por color y descartar las
        # letras (dibujadas como relleno o como trazos dentro de cajas de texto).
        if is_fill_glyph(path):
            return
        if text_boxes and _inside_text_box(path, text_boxes):
            return
        layer = color_layer(path.get("color"))
    if layer is None:
        return
    # Utilidad ABANDONADA (OCG …-ABAND): enrutar a su capa gris dedicada.
    if layer in getattr(C, "UTILITY_LINE_LAYERS", set()) and is_abandoned_ocg(ocg):
        layer = abandoned_layer(layer)
    # Suprimir marcadores de letra en las capas de tubería (los fragmentaban).
    # En modo fiel NO se suprimen: las letras y ticks se dibujan como en el PDF.
    if (not faithful and layer in getattr(C, "UTILITY_LINE_LAYERS", set())
            and is_marker_glyph(path)):
        return
    items = path.get("items", [])
    if not items:
        return
    cmds = [i[0] for i in items]
    # No fusionar: en modo fiel NADA se fusiona; si no, solo tramas/símbolos o
    # geometría sin clasificar (as-builts planos donde el texto son trazos).
    no_merge = (faithful or layer == C.FALLBACK_LAYER or
                any(tok.upper() in ocg.upper() for tok in C.NO_MERGE_TOKENS))
    # Linetype real (dashed/center/…) SOLO para líneas no personalizadas; las de
    # tubería usan su linetype de letra (UTIL_*) por capa. En modo fiel se honra el
    # patrón de guiones del propio trazo (normalmente CONTINUOUS, ya que cada dash
    # es un segmento aparte).
    if faithful:
        plt = classify_linetype_from_dashes(path)
    else:
        plt = None if layer in getattr(C, "UTILITY_LINE_LAYERS", set()) \
            else classify_linetype_from_dashes(path)

    # Caso rápido: todo segmentos rectos
    if all(c == "l" for c in cmds):
        if len(items) == 1:
            if no_merge:
                # trama/símbolo: dibujar tal cual, sin fusionar
                collector.add_polyline(layer, [T.pt(items[0][1]), T.pt(items[0][2])], plt)
            else:
                collector.add_line(layer, items[0][1], items[0][2])  # dash suelto -> fusión
        else:
            pts = [items[0][1]] + [it[2] for it in items]            # curva poligonal -> polilínea
            collector.add_polyline(layer, [T.pt(p) for p in pts], plt)
        return

    # Caso general: mezcla de líneas, beziers, rectángulos, quads
    current = []

    def flush_current():
        if len(current) >= 2:
            collector.add_polyline(layer, [T.pt(p) for p in current], plt)
        current.clear()

    for item in items:
        cmd = item[0]
        if cmd == "l":
            if not current:
                current.append(item[1])
            current.append(item[2])
        elif cmd == "m":
            flush_current()
            current.append(item[1])
        elif cmd == "c":
            # item = ('c', inicio, ctrl1, ctrl2, fin)  -> tupla de 5
            start, c1, c2, end = item[1], item[2], item[3], item[4]
            if not current:
                current.append(start)
            elif current[-1] != start:
                # continuidad: la curva arranca en 'start'
                current.append(start)
            current.extend(flatten_bezier(start, c1, c2, end))
        elif cmd == "re":
            rx = item[1]
            if (rx.x1 - rx.x0) * (rx.y1 - rx.y0) < 5:
                continue
            collector.add_polyline(layer, [
                T.point(rx.x0, rx.y0), T.point(rx.x1, rx.y0),
                T.point(rx.x1, rx.y1), T.point(rx.x0, rx.y1),
                T.point(rx.x0, rx.y0),
            ])
        elif cmd == "qu":
            q = item[1]
            collector.add_polyline(layer, [
                T.point(q.ul.x, q.ul.y), T.point(q.ur.x, q.ur.y),
                T.point(q.lr.x, q.lr.y), T.point(q.ll.x, q.ll.y),
                T.point(q.ul.x, q.ul.y),
            ])
    flush_current()


# ─────────────────────────────────────────────────────────────────────────────
# Texto
# ─────────────────────────────────────────────────────────────────────────────
_COTA_RE = re.compile(r'^\d+(\.\d+)?\s*[\'"°]?\.?$')
# Atributos a capturar de los labels: diámetro, material, estación.
_DIAM_RE = re.compile(r'(\d+(?:\.\d+)?)\s*["\']?\s*(?:IN|INCH|DIA|Ø|")', re.I)
_MATERIAL_RE = re.compile(r'\b(VCP|RCP|PVC|DIP|CIP|HDPE|ACP|CMP|PCCP|STEEL|CONC|DI|CI)\b', re.I)
_STATION_RE = re.compile(r'\b(\d+\+\d{2}(?:\.\d+)?)\b')


def plan_drawing_bbox(page):
    """Caja del dibujo en coords PDF, derivada de la geometría real (utilidades/
    vías/topo, sin estructuras ni el marco). Devuelve (x0,y0,x1,y1) o None."""
    xs, ys = [], []
    for path in page.get_drawings():
        lay = layer_for(path.get("layer", "") or "")
        if lay in (None, "ESTRUCTURAS", "ANOTACION"):
            continue  # estructuras/leaders dispersos; usar solo líneas de obra
        for it in path.get("items", []):
            if it[0] == "l":
                xs += [it[1].x, it[2].x]
                ys += [it[1].y, it[2].y]
    if len(xs) < 200:        # geometría insuficiente -> sin caja fiable
        return None
    xs.sort(); ys.sort()

    def pct(a, q):
        return a[int(q * (len(a) - 1))]

    m = C.TEXT_PLAN_BBOX_MARGIN_PT
    return (
        pct(xs, C.TEXT_PLAN_BBOX_PCT_LO) - m, pct(ys, C.TEXT_PLAN_BBOX_PCT_LO) - m,
        pct(xs, C.TEXT_PLAN_BBOX_PCT_HI) + m, pct(ys, C.TEXT_PLAN_BBOX_PCT_HI) + m,
    )


def build_text_filter(page, zones=None, consumed_text=None):
    """Umbrales de exclusión de anotación calculados por PDF.

    Estrategia principal: descartar el texto que cae FUERA del área del dibujo
    (ahí está el membrete). Fallback a umbral fraccional si no hay geometría.
    Además descarta el texto dentro de las zonas de exclusión (leyenda de pothole
    / membrete), las marcas de agua diagonales (PROGRESS SET…) y el texto ya
    representado como MTEXT de un multileader (consumed_text).
    """
    bbox = plan_drawing_bbox(page)

    mb = page.mediabox
    disp_x_dim = mb.height if page.rotation in (90, 270) else mb.width
    title_oy = C.TEXT_TITLE_OY_FRAC * disp_x_dim
    watermarks = [k.upper() for k in getattr(C, "TITLEBLOCK_WATERMARK_KEYWORDS", [])]
    consumed = consumed_text or []

    def is_annotation(txt, ox, oy, size):
        # 0) Texto ya emitido como MTEXT de un multileader -> no duplicar.
        for (bx0, by0, bx1, by1) in consumed:
            if bx0 - 1.0 <= ox <= bx1 + 1.0 and by0 - 1.0 <= oy <= by1 + 1.0:
                return True
        # 0b) Dentro de una zona de exclusión (pothole / membrete) o watermark
        if _pt_in_zones(ox, oy, zones or []):
            return True
        if watermarks and any(k in txt.upper() for k in watermarks):
            return True
        # 1) Fuera del área del dibujo -> membrete / leyenda / marco
        if bbox is not None:
            if not (bbox[0] <= ox <= bbox[2] and bbox[1] <= oy <= bbox[3]):
                return True
        elif oy > title_oy:        # fallback sin geometría
            return True
        # 2) Filtros finos
        if _COTA_RE.match(txt):
            return True
        if txt == "X":
            return True
        if re.match(r'^[A-L]$', txt) and size < 18:
            return True
        return False

    return is_annotation


def parse_attributes(txt):
    """Extrae diámetro / material / estación de un label."""
    attrs = {}
    m = _DIAM_RE.search(txt)
    if m:
        attrs["diametro"] = m.group(1)
    m = _MATERIAL_RE.search(txt)
    if m:
        attrs["material"] = m.group(1).upper()
    m = _STATION_RE.search(txt)
    if m:
        attrs["estacion"] = m.group(1)
    return attrs


def add_text(msp, page, dxf, T, is_annotation):
    """Una entidad TEXT por línea PDF (concatena spans). XDATA con atributos."""
    ensure_layer(dxf, "ANOTACION")
    if "CAD_TEXT" not in dxf.styles:
        dxf.styles.add("CAD_TEXT", font=C.TEXT_FONT)
    # Registramos un APPID para XDATA de atributos.
    try:
        dxf.appids.add("PDFCAD")
    except Exception:
        pass

    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    seen, count = set(), 0
    for b in blocks:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            dir_vec = line.get("dir", (0, 1))
            cad_rot = T.dir_to_angle(dir_vec)
            valid = []
            for span in line["spans"]:
                txt = (span.get("text") or "").strip()
                if not txt:
                    continue
                size_pt = span.get("size", 8)
                if size_pt < 1:
                    continue
                ox, oy = span["origin"]
                if is_annotation(txt, ox, oy, size_pt):
                    continue
                valid.append((txt, size_pt, ox, oy))
            if not valid:
                continue

            joined = " ".join(v[0] for v in valid)
            size_pt = valid[0][1]
            ox, oy = valid[0][2], valid[0][3]
            cx, cy = T.origin_to_cad(ox, oy)
            key = (round(cx, 1), round(cy, 1), joined[:24])
            if key in seen:
                continue
            seen.add(key)

            h_ft = max(size_pt * T.scale * C.TEXT_SCALE_FACTOR, C.TEXT_MIN_HEIGHT_FT)
            ent = msp.add_text(joined, height=h_ft, dxfattribs={
                "layer": "ANOTACION", "style": "CAD_TEXT",
                "insert": (cx, cy), "rotation": cad_rot,
            })
            attrs = parse_attributes(joined)
            if attrs:
                xdata = [(1000, f"{k}={v}") for k, v in attrs.items()]
                try:
                    ent.set_xdata("PDFCAD", xdata)
                except Exception:
                    pass
            count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Clasificación de utilidad por callout (método flecha + texto)
# ─────────────────────────────────────────────────────────────────────────────
def _pt_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _ent_points(e):
    if e.dxftype() == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if e.dxftype() == "LWPOLYLINE":
        return [(p[0], p[1]) for p in e.get_points()]
    return None


def _poly_len(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
              for i in range(len(pts) - 1))


def _pt_to_poly(pt, pts):
    return min(_pt_seg_dist(pt[0], pt[1], pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
              for i in range(len(pts) - 1))


def detect_symbol_circles(paths, T):
    """Detecta símbolos circulares (válvulas, burbujas de nota) para excluir que
    el OCR los lea como texto. Devuelve [(cx, cy, r)] en CAD (ft)."""
    out = []
    rmax = getattr(C, "VECTOR_SYMBOL_CIRCLE_MAX_PT", 30.0)
    for p in paths:
        r = p.get("rect")
        if r is None:
            continue
        w, h = r.x1 - r.x0, r.y1 - r.y0
        if w <= 3 or h <= 3:
            continue
        if max(w, h) / 2.0 > rmax:
            continue
        if not (0.6 <= (w / h if h else 0) <= 1.7):
            continue
        cmds = [i[0] for i in p.get("items", [])]
        is_round = any(c == "c" for c in cmds) or len(cmds) >= 8   # bezier o polígono cerrado
        if not is_round:
            continue
        cx, cy = T.point((r.x0 + r.x1) / 2.0, (r.y0 + r.y1) / 2.0)
        out.append((cx, cy, max(w, h) / 2.0 * T.scale * 1.1))
    return out


def _nn_chain(points):
    """Ordena puntos en una trayectoria por vecino más cercano, empezando por el
    extremo (menor x+y). Convierte marcas de VÉRTICE (puntos) en una polilínea."""
    rem = list(points)
    start = min(range(len(rem)), key=lambda i: rem[i][0] + rem[i][1])
    path = [rem.pop(start)]
    while rem:
        cur = path[-1]
        j = min(range(len(rem)), key=lambda k: (rem[k][0] - cur[0]) ** 2 + (rem[k][1] - cur[1]) ** 2)
        path.append(rem.pop(j))
    return path


# Abreviaturas de plano -> significado (para VALIDAR y expandir antes de guardar).
_ABBREV = {
    "VCP": "Vitrified Clay Pipe (arcilla vitrificada)",
    "RCP": "Reinforced Concrete Pipe (concreto reforzado)",
    "DIP": "Ductile Iron Pipe (hierro dúctil)", "DI": "Ductile Iron (hierro dúctil)",
    "CIP": "Cast Iron Pipe (hierro fundido)", "CI": "Cast Iron (hierro fundido)",
    "PVC": "Polyvinyl Chloride", "HDPE": "High-Density Polyethylene",
    "ACP": "Asbestos Cement Pipe", "CMP": "Corrugated Metal Pipe",
    "PCCP": "Prestressed Concrete Cylinder Pipe", "STL": "Steel (acero)", "STEEL": "Steel (acero)",
    "CSG": "Casing (encamisado)", "ABAND": "Abandoned (abandonado)", "ABND": "Abandoned (abandonado)",
    "EX": "Existing (existente)", "EXIST": "Existing (existente)", "PROP": "Proposed (propuesto)",
    "INV": "Invert (cota de fondo)", "OHE": "Overhead Electric (eléctrico aéreo)",
    "GV": "Gate Valve (válvula de compuerta)", "FH": "Fire Hydrant (hidrante)",
    "MH": "Manhole (pozo)", "CPLG": "Coupling (acople)", "SEWER": "Sanitary Sewer",
    "WATER": "Water (agua)", "SS": "Sanitary Sewer (alcantarillado)",
    "SD": "Storm Drain (drenaje pluvial)", "PIPE": "Pipe (tubería)", "MAIN": "Main (matriz)",
    "DWPWS": "LADWP Water Service", "SCG": "SoCal Gas", "CATV": "Cable TV",
    "COMM": "Communications", "DUCT": "Duct (ducto)",
}
# Palabras que confirman que el texto ES nomenclatura de tubería (no cota/estación).
_STRONG_UTIL = re.compile(
    r'\b(SEWER|WATER|GAS|PIPE|MAIN|VCP|RCP|DIP|CIP|PVC|HDPE|ACP|CMP|PCCP|STL|STEEL|'
    r'CSG|CASING|DUCT|CATV|COMM|ELEC|TEL|OHE)\b', re.I)


def expand_abbrev(text):
    """Devuelve [(sigla, significado)] reconocidas (solo siglas NO ambiguas)."""
    up = text.upper()
    return [(ab, mean) for ab, mean in _ABBREV.items()
            if re.search(r'\b' + re.escape(ab) + r'\b', up)]


# Utilidad implícita en el texto del callout -> capas candidatas (verdad = OCG).
def callout_target_layers(txt):
    up = txt.upper()
    if "STORM" in up or re.search(r'\bSD\b', up):
        return {"DRENAJE_PLUVIAL"}
    if "SEWER" in up or "VCP" in up or re.search(r'\bSS\b', up):
        return {"ALCANTARILLADO"}
    if "GAS" in up:
        return {"GAS"}
    if "WATER" in up:
        return {"AGUA"}
    if "ELECTRIC" in up or "POWER" in up or re.search(r'\bOHE?\b', up):
        return {"ELECTRICO", "ELECTRICO_AEREO"}
    if ("TEL" in up or "CATV" in up or "COMM" in up or "DUCT" in up
            or "FIBER" in up or "FO " in up):
        return {"TELECOM", "TELECOM_AEREO"}
    return None


def attach_callout_xdata(msp, dxf, T, radius_ft=90.0):
    """Adjunta la nomenclatura de cada callout a la línea de tubería correcta:
    lee la UTILIDAD del texto (SEWER, GAS, WATER, VCP...) y la asigna a la línea
    más cercana DE ESA MISMA UTILIDAD (las capas OCG son la verdad). Solo texto
    con nomenclatura real; las siglas se expanden a su significado."""
    from collections import defaultdict
    ents = [(e, _ent_points(e), e.dxf.layer) for e in msp
            if e.dxf.layer in getattr(C, "UTILITY_LINE_LAYERS", set()) and _ent_points(e)]
    if not ents:
        return 0
    try:
        dxf.appids.add("PDFCAD")
    except Exception:
        pass
    per_line = defaultdict(lambda: {"ent": None, "notas": [], "attrs": {}})
    for te in msp:
        if te.dxftype() != "TEXT" or te.dxf.layer != "ANOTACION":
            continue
        txt = (te.dxf.text or "").strip()
        if not txt:
            continue
        attrs = parse_attributes(txt)
        meaningful = ("diametro" in attrs or "material" in attrs
                      or _STRONG_UTIL.search(txt))
        if not meaningful:
            continue
        targets = callout_target_layers(txt)
        if not targets:
            continue                       # no se sabe la utilidad -> no adivinar
        abbr = expand_abbrev(txt)
        pt = (te.dxf.insert.x, te.dxf.insert.y)
        best, bd = None, radius_ft
        for e, pts, lyr in ents:
            if lyr not in targets:         # solo líneas de la MISMA utilidad
                continue
            d = _pt_to_poly(pt, pts)
            if d < bd:
                bd, best = d, e
        if best is None:
            continue
        rec = per_line[id(best)]
        rec["ent"] = best
        rec["notas"].append(txt)
        rec["attrs"].update(attrs)
        for ab, mean in abbr:
            rec["attrs"].setdefault(ab, mean)
    n = 0
    for rec in per_line.values():
        e = rec["ent"]
        xd = [(1000, "nota=" + "; ".join(rec["notas"])[:240])]
        for k, v in list(rec["attrs"].items())[:18]:
            xd.append((1000, f"{k}={v}"[:240]))
        try:
            e.set_xdata("PDFCAD", xd)
            n += 1
        except Exception:
            pass
    return n


def collect_overlays(paths, T):
    """Marcas de color -> {capa: [segmentos CAD (a,b)]}. Soporta dos formas de marca:
      · TRAZO sobre la tubería  -> sus segmentos.
      · PUNTOS en los vértices  -> se encadenan en una polilínea (los puntos están
        sobre la tubería, así que la cadena indica dónde está la línea negra)."""
    from collections import defaultdict
    ov = defaultdict(list)
    dots = defaultdict(list)
    for p in paths:
        layer = overlay_layer_for(p.get("color"))
        if layer is None:
            continue
        items = p.get("items", [])
        cmds = [it[0] for it in items]
        r = p.get("rect")
        w = (r.x1 - r.x0) if r else 0
        h = (r.y1 - r.y0) if r else 0
        is_dot = (p.get("fill") is not None and cmds and all(c == "c" for c in cmds)
                  and max(w, h) < 4.0)
        if is_dot:
            dots[layer].append(T.point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
        else:
            for it in items:
                if it[0] == "l":
                    ov[layer].append((T.pt(it[1]), T.pt(it[2])))
                elif it[0] == "c":
                    ov[layer].append((T.pt(it[1]), T.pt(it[4])))
    for layer, pl in dots.items():
        if len(pl) >= 2:
            chain = _nn_chain(pl)
            for a, b in zip(chain, chain[1:]):
                ov[layer].append((a, b))
    return ov


def _seg_angle(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def _ang_diff(u, v):
    d = abs(u - v) % 180.0
    return min(d, 180.0 - d)


def reassign_under_overlays(msp, dxf, T, overlays):
    """Enfoque por MARCA: cada segmento de marca colorea las líneas negras que
    quedan DEBAJO — cercanas (<= snap), PARALELAS (la tubería, no los lotes que
    cruzan) y que se solapan con la marca. Autoritativo (sobrescribe). Colorea
    todos los tramos de la tubería, no solo uno."""
    from collections import Counter
    snap = C.VECTOR_OVERLAY_SNAP_PT * T.scale
    atol = getattr(C, "VECTOR_OVERLAY_ANGLE_TOL", 22.0)
    for layer in overlays:
        ensure_layer(dxf, layer)
    ents = []
    for e in msp:
        pts = _ent_points(e)
        if pts and len(pts) >= 2:
            ents.append((e, pts, _seg_angle(pts[0], pts[-1])))
    counts = Counter()
    for layer, segs in overlays.items():
        for (a, b) in segs:
            mang = _seg_angle(a, b)
            samples = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                       for t in (0.1, 0.3, 0.5, 0.7, 0.9)]
            # La marca traza el EJE de la tubería: se colorea SOLO la línea más
            # cercana y paralela (no todo el corredor, para no arrastrar vecinas).
            best, bestd = None, snap
            for e, pts, eang in ents:
                if _ang_diff(mang, eang) > atol:      # no paralela -> cruce, se salta
                    continue
                d = sum(_pt_to_poly(s, pts) for s in samples) / len(samples)
                if d < bestd:
                    bestd, best = d, e
            if best is not None and best.dxf.layer != layer:
                best.dxf.layer = layer
                counts[layer] += 1
    return counts


def classify_utilities(msp, dxf, T, callouts):
    """Para cada callout de utilidad: busca el leader (línea que arranca en la caja
    del texto), sigue hasta su punta, y reclasifica la TUBERÍA más cercana a esa
    punta a la capa de la utilidad, adjuntando la nomenclatura en XDATA.
    Si no hay leader, usa el centro del texto. Devuelve conteo por capa."""
    from collections import Counter
    sft = T.scale
    box_m = C.LEADER_BOX_MARGIN_PT * sft
    lmin = C.LEADER_MIN_LEN_PT * sft
    radius = C.CLASSIFY_RADIUS_PT * sft

    ents = []
    for e in msp:
        pts = _ent_points(e)
        if pts and len(pts) >= 2:
            ents.append((e, pts, _poly_len(pts)))

    try:
        dxf.appids.add("PDFCAD")
    except Exception:
        pass

    counts = Counter()
    for c in callouts:
        util = c.get("util")
        if not util:
            continue
        bx0, by0, bx1, by1 = c["cad_box"]
        cx, cy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
        # 1) Buscar leader: línea con un extremo dentro de la caja (margen) y el
        #    otro extremo lejos -> la punta es ese extremo lejano.
        target, best_far = (cx, cy), -1.0
        for e, pts, L in ents:
            if L < lmin:
                continue
            for end, other in ((pts[0], pts[-1]), (pts[-1], pts[0])):
                if (bx0 - box_m <= end[0] <= bx1 + box_m and
                        by0 - box_m <= end[1] <= by1 + box_m):
                    d = math.hypot(other[0] - cx, other[1] - cy)
                    if d > best_far:
                        best_far, target = d, other
        # 2) Tubería más cercana a la punta (dentro del radio).
        bestd, beste = radius, None
        for e, pts, L in ents:
            if L < lmin:
                continue
            d = _pt_to_poly(target, pts)
            if d < bestd:
                bestd, beste = d, e
        if beste is None:
            continue
        ensure_layer(dxf, util)
        beste.dxf.layer = util
        if c.get("attrs"):
            try:
                beste.set_xdata("PDFCAD", [(1000, f"{k}={v}") for k, v in c["attrs"].items()])
            except Exception:
                pass
        counts[util] += 1
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# Zonas de exclusión por contenido  (POTHOLE LEGEND + membrete de título)
# ─────────────────────────────────────────────────────────────────────────────
def _text_spans(page):
    """Genera (texto, bbox_pdf) de cada span de texto VIVO de la página."""
    try:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    except Exception:
        return
    for b in blocks:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                t = (span.get("text") or "").strip()
                if t:
                    yield t, tuple(span["bbox"])


def _union_box(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _box_gap(a, b):
    """Distancia (pt) entre dos bboxes; 0 si se solapan/tocan."""
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)


def _cluster_boxes(boxes, gap):
    """Agrupa bboxes por cercanía (single-linkage) con umbral 'gap'. Devuelve la
    lista de bboxes-unión, uno por cluster."""
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _box_gap(boxes[i], boxes[j]) <= gap:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(boxes[i])
    return [_union_box(g) for g in groups.values()]


def build_exclusion_zones(page):
    """Devuelve zonas de exclusión en coords PDF: la leyenda de POTHOLE y el/los
    bloque(s) de membrete de título, detectados por CONTENIDO del texto vivo.
    Toda geometría/anotación con centro dentro de una zona se descarta.

    Robusto al layout (no depende de posiciones fijas): ancla en las palabras
    clave del contenido y expande su bbox. Las marcas de agua diagonales
    (PROGRESS SET…) NO definen zona (su bbox cubriría el dibujo)."""
    if not getattr(C, "EXCLUDE_ZONES_ENABLED", False):
        return []
    spans = list(_text_spans(page))
    if not spans:
        return []   # PDF aplanado sin texto vivo: fuera de alcance aquí

    margin = getattr(C, "EXCLUDE_ZONE_MARGIN_PT", 28.0)
    pot_kw = [k.upper() for k in getattr(C, "POTHOLE_LEGEND_KEYWORDS", [])]
    tb_kw = [k.upper() for k in getattr(C, "TITLEBLOCK_FIELD_KEYWORDS", [])]
    gap = getattr(C, "TITLEBLOCK_CLUSTER_GAP_PT", 140.0)

    page_area = abs(page.mediabox.width * page.mediabox.height) or 1.0
    max_frac = getattr(C, "EXCLUDE_ZONE_MAX_PAGE_FRAC", 0.28)

    zones = []

    # 1) Leyenda de pothole: cluster único (siempre es un recuadro compacto).
    pot_boxes = [bb for (t, bb) in spans if any(k in t.upper() for k in pot_kw)]
    if pot_boxes:
        for z in _cluster_boxes(pot_boxes, gap):
            zones.append(("POTHOLE_LEGEND", z))

    # 2) Membrete: campos típicos, agrupados por cercanía -> uno o varios cajetines.
    tb_boxes = [bb for (t, bb) in spans if any(k in t.upper() for k in tb_kw)]
    if tb_boxes:
        for z in _cluster_boxes(tb_boxes, gap):
            if (z[2] - z[0]) * (z[3] - z[1]) <= max_frac * page_area:
                zones.append(("TITLEBLOCK", z))

    # Expandir por el margen configurado.
    out = []
    for tag, (x0, y0, x1, y1) in zones:
        out.append((tag, (x0 - margin, y0 - margin, x1 + margin, y1 + margin)))
    return out


def _pt_in_zones(x, y, zones):
    for _tag, (x0, y0, x1, y1) in zones:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def _path_in_zones(path, zones):
    """True si el centro del bbox del trazo cae dentro de alguna zona de exclusión."""
    if not zones:
        return False
    r = path.get("rect")
    if r is None:
        return False
    return _pt_in_zones((r.x0 + r.x1) / 2.0, (r.y0 + r.y1) / 2.0, zones)


def zones_to_cad(zones, T):
    """Convierte las zonas (bbox PDF) a bbox CAD (ft) usando la transformación de
    página. Devuelve [(tag, (x0,y0,x1,y1))] para el QA de capa contaminada."""
    out = []
    for tag, (x0, y0, x1, y1) in zones:
        cs = [T.point(x0, y0), T.point(x1, y0), T.point(x1, y1), T.point(x0, y1)]
        xs = [c[0] for c in cs]
        ys = [c[1] for c in cs]
        out.append((tag, (min(xs), min(ys), max(xs), max(ys))))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Metadata del membrete (se LEE aunque el cajetín no se dibuje)
# ─────────────────────────────────────────────────────────────────────────────
# Palabras que son ETIQUETAS del membrete, no valores: si un patrón las captura
# como "valor" es porque en el texto rotado la etiqueta siguiente quedó pegada a
# la anterior (sin el valor real en medio) -> se descarta (mejor omitir que mentir).
_METADATA_STOPWORDS = {
    "DRAWING", "SHEET", "CONTRACT", "SCALE", "DESIGNED", "DRAWN", "CHECKED",
    "APPROVED", "PROJECT", "TITLE", "DATE", "REV", "REVISION", "SUBMITTAL",
    "BY", "NO", "OF", "NAME",
}


def extract_titleblock_metadata(page):
    """Extrae metadata del membrete (contrato, dibujo, hoja, escala, fecha) del
    texto vivo de la página. Devuelve dict (solo campos hallados y fiables).

    Conservador: si un patrón captura como valor otra ETIQUETA del membrete
    (DRAWING, SHEET…), se descarta ese campo — preferimos omitir a reportar mal."""
    if not getattr(C, "METADATA_ENABLED", False):
        return {}
    try:
        txt = page.get_text()
    except Exception:
        return {}
    md = {}
    for key, patterns in getattr(C, "METADATA_PATTERNS", {}).items():
        for pat in patterns:
            m = pat.search(txt)
            if not m:
                continue
            val = m.group(1).strip()
            if not val or val.upper() in _METADATA_STOPWORDS:
                continue
            md[key] = val
            break
    return md


def add_metadata_entity(msp, dxf, T, page, md):
    """Guarda la metadata del membrete como XDATA sobre una entidad TEXT en la capa
    METADATA (esquina del dibujo). El cajetín NO se dibuja como geometría; solo
    esta anotación de metadata."""
    if not md:
        return 0
    layer = getattr(C, "METADATA_LAYER", "METADATA")
    ensure_layer(dxf, layer)
    if "CAD_TEXT" not in dxf.styles:
        dxf.styles.add("CAD_TEXT", font=C.TEXT_FONT)
    try:
        dxf.appids.add("PDFCAD")
    except Exception:
        pass
    mb = page.mediabox
    pos = T.point(mb.x0, mb.y0)     # esquina de la hoja en CAD
    label = " | ".join(f"{k}={v}" for k, v in md.items())
    ent = msp.add_text(label, height=max(2.0, C.TEXT_MIN_HEIGHT_FT), dxfattribs={
        "layer": layer, "style": "CAD_TEXT", "insert": pos, "rotation": 0})
    try:
        ent.set_xdata("PDFCAD", [(1000, f"{k}={v}"[:240]) for k, v in md.items()])
    except Exception:
        pass
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Líneas abandonadas -> gris (extensión por proximidad)
# ─────────────────────────────────────────────────────────────────────────────
def _entity_dir_mid(pts):
    """(ángulo 0-180, longitud, punto medio) del segmento extremo-a-extremo."""
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    ang = math.degrees(math.atan2(dy, dx)) % 180.0
    return ang, L, ((ax + bx) / 2.0, (ay + by) / 2.0)


def recolor_abandoned(msp, dxf, T):
    """Colorea GRIS las líneas de utilidad ABANDONADAS. Detección por señal
    universal: los ticks "/" (segmentos cortos y diagonales que cruzan la tubería)
    y las marcas del OCG …-ABAND (ya enrutadas a la capa gris). Toda la CORRIDA
    colineal de la tubería que contiene un tick se mueve a la capa …_ABANDONADO
    (arrastra rayas y letras). Devuelve nº de entidades reasignadas.

    No depende del OCG (el agua no trae -ABAND); funciona por geometría, así que
    aplica a cualquier utilidad marcada con ticks."""
    if not getattr(C, "ABANDONED_ENABLED", False):
        return 0
    suffix = getattr(C, "ABANDONED_LAYER_SUFFIX", "_ABANDONADO")
    util = getattr(C, "UTILITY_LINE_LAYERS", set())
    s = T.scale
    tick_min = getattr(C, "ABANDONED_TICK_MIN_PT", 4.0) * s
    tick_max = getattr(C, "ABANDONED_TICK_MAX_PT", 40.0) * s
    ang_min = getattr(C, "ABANDONED_TICK_ANGLE_MIN", 18.0)
    perp_tol = getattr(C, "ABANDONED_RUN_PERP_TOL_PT", 4.0) * s
    ang_tol = getattr(C, "MERGE_ANGLE_TOL_DEG", 3.0)
    detect_ticks = getattr(C, "ABANDONED_DETECT_TICKS", True)
    min_ticks = max(1, getattr(C, "ABANDONED_MIN_TICKS", 2))

    from collections import defaultdict
    # Entidades por capa base de utilidad (incluye las ya grises como ancla).
    ents_by = defaultdict(list)
    for e in msp:
        lyr = e.dxf.layer
        base = lyr[:-len(suffix)] if lyr.endswith(suffix) else lyr
        if base in util:
            pts = _ent_points(e)
            if pts and len(pts) >= 2:
                ents_by[base].append((e, pts))

    n = 0
    for base, items in ents_by.items():
        anchors = []                       # puntos ancla (ticks + marcas -ABAND)
        runs = defaultdict(list)           # (akey,pkey) -> [(e, tmin, tmax)]
        run_geom = {}                      # (akey,pkey) -> (ang,perp,nx,ny,ux,uy)
        for e, pts in items:
            ang, L, mid = _entity_dir_mid(pts)
            if L < 1e-9:
                continue
            already = e.dxf.layer.endswith(suffix)
            aa = ang % 90.0
            # Un tick "/" es UN solo segmento (2 puntos), corto y diagonal. Las
            # LETRAS (W/G/SS) son polilíneas multi-vértice -> NO son ticks.
            is_tick = (detect_ticks and len(pts) == 2 and tick_min <= L <= tick_max
                       and ang_min < aa < (90.0 - ang_min))
            if already or is_tick:
                anchors.append(mid)        # ancla de abandono
                continue
            # Raya/letra ortogonal-ish -> agrupar en su corrida colineal.
            ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            nx, ny = -uy, ux
            perp = pts[0][0] * nx + pts[0][1] * ny
            akey, pkey = round(ang / ang_tol), round(perp / max(perp_tol, 1e-6))
            proj = [p[0] * ux + p[1] * uy for p in pts]
            runs[(akey, pkey)].append((e, min(proj), max(proj)))
            run_geom.setdefault((akey, pkey), (ang, perp, nx, ny, ux, uy))
        if not anchors:
            continue

        # Corridas con >= min_ticks anclas ENCIMA (ticks periódicos) -> abandonadas.
        # Una diagonal suelta (lateral) no basta: evita agrisar líneas activas.
        aband_lines = []
        for key, members in runs.items():
            ang, perp, nx, ny, ux, uy = run_geom[key]
            tmin = min(m[1] for m in members)
            tmax = max(m[2] for m in members)
            cnt = 0
            for (mx, my) in anchors:
                mp = mx * nx + my * ny
                mt = mx * ux + my * uy
                if abs(mp - perp) <= perp_tol and tmin - perp_tol <= mt <= tmax + perp_tol:
                    cnt += 1
                    if cnt >= min_ticks:
                        break
            if cnt >= min_ticks:
                aband_lines.append((perp, nx, ny, ux, uy, tmin, tmax))
        if not aband_lines:
            continue

        # Segunda pasada: agrisar TODA entidad de la capa (rayas, letras, ticks)
        # que caiga sobre una línea abandonada (perp <= tol y dentro de la corrida).
        newl = abandoned_layer(base)
        for e, pts in items:
            if e.dxf.layer.endswith(suffix):
                continue
            hit = False
            for (perp, nx, ny, ux, uy, tmin, tmax) in aband_lines:
                for (px, py) in pts:
                    if (abs(px * nx + py * ny - perp) <= perp_tol
                            and tmin - perp_tol <= px * ux + py * uy <= tmax + perp_tol):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                ensure_layer(dxf, newl)
                e.dxf.layer = newl
                n += 1
    return n


# ─────────────────────────────────────────────────────────────────────────────
# LEADERS / MULTILEADERS  (flecha + texto)  — entidades CAD nativas
# ─────────────────────────────────────────────────────────────────────────────
def _leader_points_pdf(path):
    """Puntos (pdf) de la polilínea del leader, en orden."""
    pts = []
    for it in path.get("items", []):
        if it[0] == "l":
            if not pts:
                pts.append((it[1].x, it[1].y))
            pts.append((it[2].x, it[2].y))
        elif it[0] == "c":
            if not pts:
                pts.append((it[1].x, it[1].y))
            pts.append((it[4].x, it[4].y))
    return pts


def _text_lines_pdf(page):
    """Líneas de texto vivo: [{text, bbox, size}] en coords PDF."""
    out = []
    try:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    except Exception:
        return out
    for b in blocks:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            spans = [s for s in line["spans"] if (s.get("text") or "").strip()]
            if not spans:
                continue
            txt = " ".join((s["text"] or "").strip() for s in spans)
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            out.append({"text": txt, "bbox": (x0, y0, x1, y1), "size": spans[0].get("size", 8)})
    return out


def _pt_box_dist(pt, box):
    x, y = pt
    dx = max(box[0] - x, 0.0, x - box[2])
    dy = max(box[1] - y, 0.0, y - box[3])
    return math.hypot(dx, dy)


def _setup_leader_dimstyle(dxf, arrow_ft):
    """Crea/ajusta un DIMSTYLE para los LEADER con flecha de 'arrow_ft' pies."""
    name = "PDFCAD_LDR"
    try:
        if name not in dxf.dimstyles:
            dxf.dimstyles.duplicate_entry("Standard", name)
        ds = dxf.dimstyles.get(name)
        ds.dxf.dimasz = arrow_ft       # tamaño de flecha (pies)
        ds.dxf.dimscale = 1.0
        return name
    except Exception:
        return "Standard"


def _setup_mleader_style(dxf, arrow_ft):
    """Ajusta el estilo de mleader 'Standard' (tamaño de flecha en pies)."""
    try:
        st = dxf.mleader_styles.get("Standard")
        st.dxf.arrow_size = arrow_ft
    except Exception:
        pass
    return "Standard"


def build_multileaders(paths, page, msp, dxf, T):
    """Reconstruye los callouts del PDF como entidades leader NATIVAS, respetando
    la geometría del PDF (no reflow).

    Modo C.MLEADER_MODE:
      · "leader" (def): una entidad LEADER con los VÉRTICES EXACTOS del PDF (flecha
        en la punta que apunta a la utilidad). El TEXTO se deja tal cual (lo coloca
        add_text en su posición/rotación del PDF) -> fiel.
      · "multileader": MULTILEADER con auto-layout (agrupa flecha+texto, pero NO
        respeta la geometría/rotación del PDF; útil solo si se quiere reflowar).
      · "off": no reconstruir (la línea guía + punta quedan como geometría fiel).

    Empareja cada línea guía con su punta de flecha (path relleno pequeño cercano a
    un extremo). Devuelve (n_multileader, n_leader, indices_consumidos, cajas_texto).
    """
    mode = getattr(C, "MLEADER_MODE", "leader")
    if not getattr(C, "VECTOR_BUILD_MLEADERS", False) or mode == "off":
        return 0, 0, set(), []

    tokens = getattr(C, "MLEADER_LEADER_TOKENS", [])
    arrow_max = getattr(C, "MLEADER_ARROW_MAX_PT", 18.0)
    pair_tol = getattr(C, "MLEADER_PAIR_TOL_PT", 16.0)
    snap = getattr(C, "MLEADER_TEXT_SNAP_PT", 55.0)
    layer = getattr(C, "MLEADER_LAYER", "ANOTACION")
    arrow_ft = getattr(C, "MLEADER_ARROW_SIZE_FT", 3.0)
    ensure_layer(dxf, layer)

    # Separar puntas de flecha (paths rellenos pequeños) y líneas guía.
    arrows, lines = [], []
    for i, p in enumerate(paths):
        if not any(t in (p.get("layer") or "") for t in tokens):
            continue
        r = p.get("rect")
        if r is None:
            continue
        maxdim = max(r.x1 - r.x0, r.y1 - r.y0)
        if p.get("fill") is not None and maxdim <= arrow_max:
            arrows.append((i, ((r.x0 + r.x1) / 2.0, (r.y0 + r.y1) / 2.0)))
        else:
            pts = _leader_points_pdf(p)
            if len(pts) >= 2:
                lines.append((i, pts))

    consumed_paths, consumed_text = set(), []
    n_ml = n_ld = 0

    def nearest_arrow(pt):
        best, bd = None, pair_tol
        for ai, a in arrows:
            d = math.hypot(pt[0] - a[0], pt[1] - a[1])
            if d < bd:
                bd, best = d, ai
        return best, bd

    # ── Modo LEADER (fiel a la geometría del PDF) ────────────────────────────
    if mode == "leader":
        ldr_style = _setup_leader_dimstyle(dxf, arrow_ft)
        for (li, pts) in lines:
            a0, d0 = nearest_arrow(pts[0])
            a1, d1 = nearest_arrow(pts[-1])
            if a0 is None and a1 is None:
                continue                    # sin flecha -> no es leader
            # Ordenar [punta(flecha), ..., landing]: la flecha va en el 1er vértice.
            if a0 is not None and (a1 is None or d0 <= d1):
                verts, arr = list(pts), a0            # flecha en pts[0]
            else:
                verts, arr = list(reversed(pts)), a1  # flecha en pts[-1]
            cad_v = [T.point(x, y) for (x, y) in verts]   # [punta, codo, landing]
            try:
                msp.add_leader(cad_v, dxfattribs={"layer": layer, "dimstyle": ldr_style})
                n_ld += 1
                consumed_paths.add(li)
                if arr is not None:
                    consumed_paths.add(arr)
            except Exception:
                pass
        return 0, n_ld, consumed_paths, consumed_text   # texto se deja tal cual (fiel)

    # ── Modo MULTILEADER (auto-layout; NO fiel) ──────────────────────────────
    try:
        from ezdxf.math import Vec2
        from ezdxf.render.mleader import ConnectionSide, TextAlignment
    except Exception:
        return 0, 0, set(), []
    style = _setup_mleader_style(dxf, arrow_ft)
    tlines = _text_lines_pdf(page)
    for (li, pts) in lines:
        a0, d0 = nearest_arrow(pts[0])
        a1, d1 = nearest_arrow(pts[-1])
        if a0 is None and a1 is None:
            continue
        if a0 is not None and (a1 is None or d0 <= d1):
            verts, arr = list(reversed(pts)), a0
        else:
            verts, arr = list(pts), a1
        cad_v = [T.point(x, y) for (x, y) in verts]     # [landing, ..., tip]
        insert, tip = cad_v[0], cad_v[-1]
        best, bd = None, snap
        for tl in tlines:
            d = _pt_box_dist(verts[0], tl["bbox"])
            if d < bd:
                bd, best = d, tl
        side = ConnectionSide.left if tip[0] < insert[0] else ConnectionSide.right
        leader_pts = [Vec2(x, y) for (x, y) in cad_v[1:]]
        ok = False
        if best is not None:
            ch = max(best["size"] * T.scale * C.TEXT_SCALE_FACTOR, C.TEXT_MIN_HEIGHT_FT)
            align = TextAlignment.left if side == ConnectionSide.right else TextAlignment.right
            try:
                mb = msp.add_multileader_mtext(style)
                mb.set_content(best["text"], char_height=ch, alignment=align)
                mb.add_leader_line(side, leader_pts)
                mb.build(insert=Vec2(insert[0], insert[1]))
                try:
                    mb.multileader.dxf.layer = layer
                except Exception:
                    pass
                consumed_text.append(best["bbox"])
                n_ml += 1
                ok = True
            except Exception:
                ok = False
        if not ok and best is None:
            try:
                msp.add_leader([tuple(p) for p in cad_v], dxfattribs={"layer": layer})
                n_ld += 1
                ok = True
            except Exception:
                ok = False
        if ok:
            consumed_paths.add(li)
            if arr is not None:
                consumed_paths.add(arr)
    return n_ml, n_ld, consumed_paths, consumed_text


# ─────────────────────────────────────────────────────────────────────────────
# Entrada principal de la ruta vectorizada
# ─────────────────────────────────────────────────────────────────────────────
def run(page, dxf_doc):
    """Procesa una página vectorizada sobre un documento ezdxf abierto.
    Devuelve dict con métricas."""
    scale = detect_scale(page)
    T = CoordTransform(page, scale)
    msp = dxf_doc.modelspace()

    setup_linetypes(dxf_doc)
    collector = LayerSegmentCollector()
    paths = page.get_drawings()
    has_ocg = any(p.get("layer") for p in paths)

    # Zonas de exclusión por contenido (leyenda de pothole + membrete de título):
    # su geometría y anotación NO se digitalizan. La metadata del membrete SÍ se lee.
    zones = build_exclusion_zones(page)
    if zones:
        tags = ", ".join(sorted({t for t, _ in zones}))
        print(f"   Zonas de exclusión detectadas: {len(zones)} ({tags})")
    metadata = extract_titleblock_metadata(page)
    if metadata:
        print(f"   Metadata del membrete: {metadata}")

    # PDF aplanado sin texto vivo: leer los callouts por OCR ANTES de la geometría,
    # para poder suprimir los trazos del texto original con sus cajas.
    callouts, text_boxes = [], []
    live_text = bool(page.get_text().strip())
    if not has_ocg:
        print("   PDF vectorial APLANADO (sin capas OCG) -> clasificación por color")
        if not live_text and getattr(C, "VECTOR_OCR_CALLOUTS", False):
            import callout_ocr
            detected = callout_ocr.extract_callouts(page, T)
            # TODAS las cajas (incluso poco fiables y cotas) suprimen el texto de
            # fondo; solo se COLOCAN las de confianza alta, sin duplicados, sin cotas,
            # sin basura y sin texto sobre símbolos circulares.
            text_boxes = [c["mbox"] for c in detected]
            # La exclusión por símbolos circulares se omite: detectaba demasiados
            # falsos y borraba texto real cercano a tuberías. Los símbolos mal
            # leídos los filtra is_garbage por contenido.
            callouts = callout_ocr.dedupe_for_placement(detected, C.VECTOR_OCR_MIN_CONF, [])

    # LEADERS / MULTILEADERS: reconstruir los callouts (flecha + texto) como
    # entidades CAD nativas ANTES de dibujar geometría/texto, para no duplicarlos.
    ml_paths, ml_text = set(), []
    if getattr(C, "VECTOR_BUILD_MLEADERS", False) and has_ocg and live_text:
        n_ml, n_ld, ml_paths, ml_text = build_multileaders(paths, page, msp, dxf_doc, T)
        if n_ml or n_ld:
            print(f"   Leaders reconstruidos (modo {getattr(C,'MLEADER_MODE','leader')}): "
                  f"{n_ld} LEADER, {n_ml} MULTILEADER  (texto: "
                  f"{'fiel del PDF' if not ml_text else 'MTEXT del multileader'})")

    for i, path in enumerate(paths):
        if i in ml_paths:
            continue                       # ya representado como (multi)leader
        process_path(collector, path, dxf_doc, T, has_ocg, text_boxes, zones)
    n_geom = collector.flush(msp, dxf_doc, T)

    is_annotation = build_text_filter(page, zones, ml_text)
    n_text = add_text(msp, page, dxf_doc, T, is_annotation)

    # Metadata del membrete -> XDATA en capa METADATA (el cajetín no se dibuja).
    add_metadata_entity(msp, dxf_doc, T, page, metadata)

    # Adjuntar la nomenclatura (validada/expandida) a la línea de tubería cercana.
    n_xd = attach_callout_xdata(msp, dxf_doc, T)
    if n_xd:
        print(f"   Nomenclatura adjuntada a {n_xd} líneas (XDATA appid PDFCAD)")

    if callouts:
        import callout_ocr
        n_text = callout_ocr.add_text_layer(msp, dxf_doc, callouts)
        n_clf = classify_utilities(msp, dxf_doc, T, callouts)
        print(f"   OCR de callouts: {len(text_boxes)} textos suprimidos, "
              f"{len(callouts)} etiquetas colocadas (cotas omitidas)")
        print(f"   Utilidades clasificadas por flecha+texto: {dict(n_clf)}")

    # MARCAS de color -> transferir a la línea negra de abajo (autoritativo).
    if not has_ocg:
        overlays = collect_overlays(paths, T)
        if overlays:
            n_ov = reassign_under_overlays(msp, dxf_doc, T, overlays)
            print(f"   Marcas de color transferidas a la línea de abajo: {dict(n_ov)}")

    # Líneas ABANDONADAS -> extender el gris a las rayas EXIS vecinas.
    n_ab = recolor_abandoned(msp, dxf_doc, T)
    if n_ab:
        print(f"   Líneas abandonadas -> gris: {n_ab} entidades arrastradas por proximidad")

    mb = page.mediabox
    if page.rotation in (90, 270):
        disp_w_ft, disp_h_ft = mb.height * scale, mb.width * scale
    else:
        disp_w_ft, disp_h_ft = mb.width * scale, mb.height * scale

    return {
        "scale_ft_per_pt": scale,
        "n_paths": len(paths),
        "n_geometry": n_geom,
        "n_text": n_text,
        "extent_ft": (round(disp_w_ft), round(disp_h_ft)),
        "callouts": callouts,
        "exclusion_zones_cad": zones_to_cad(zones, T),
        "metadata": metadata,
    }
