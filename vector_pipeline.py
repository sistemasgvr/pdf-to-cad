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
# Resolución de capa
# ─────────────────────────────────────────────────────────────────────────────
def layer_for(ocg):
    """Nombre OCG del PDF -> capa de salida (o None para descartar)."""
    up = (ocg or "").upper()
    for tok, layer in C.LAYER_TOKENS:
        if tok.upper() in up:
            return layer
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
        noise_pt = getattr(C, "VECTOR_NOISE_MIN_PT", 0.0)
        noise_ft = noise_pt * T.scale
        util_layers = getattr(C, "UTILITY_LINE_LAYERS", set())

        std_scale = getattr(C, "LINETYPE_STD_SCALE", 30.0)
        tol = max(getattr(C, "STITCH_TOL_PT", 12.0) * T.scale, 1.0)

        # Guiones fusionados -> piezas CAD por capa.
        seg_pieces = defaultdict(list)
        for layer, segs in self.segments.items():
            if layer in drop:
                continue
            clean_markers = (C.CLEAN_UTILITY_MARKERS and layer in C.UTILITY_CLEAN_LAYERS)
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
            if layer in util_layers:
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


def process_path(collector, path, dxf, T, has_ocg=True, text_boxes=None):
    if is_shx_glyph(path):
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
    # Suprimir marcadores de letra en las capas de tubería (los fragmentaban).
    if layer in getattr(C, "UTILITY_LINE_LAYERS", set()) and is_marker_glyph(path):
        return
    items = path.get("items", [])
    if not items:
        return
    cmds = [i[0] for i in items]
    # No fusionar: tramas/símbolos, o geometría sin clasificar (as-builts planos
    # donde el texto está dibujado como trazos y se dañaría al fusionar).
    no_merge = (layer == C.FALLBACK_LAYER or
                any(tok.upper() in ocg.upper() for tok in C.NO_MERGE_TOKENS))
    # Linetype real (dashed/center/…) SOLO para líneas no personalizadas; las de
    # tubería usan su linetype de letra (UTIL_*) por capa.
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


def build_text_filter(page):
    """Umbrales de exclusión de anotación calculados por PDF.

    Estrategia principal: descartar el texto que cae FUERA del área del dibujo
    (ahí está el membrete). Fallback a umbral fraccional si no hay geometría.
    """
    bbox = plan_drawing_bbox(page)

    mb = page.mediabox
    disp_x_dim = mb.height if page.rotation in (90, 270) else mb.width
    title_oy = C.TEXT_TITLE_OY_FRAC * disp_x_dim

    def is_annotation(txt, ox, oy, size):
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
        return {"DRENAJE"}
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

    for path in paths:
        process_path(collector, path, dxf_doc, T, has_ocg, text_boxes)
    n_geom = collector.flush(msp, dxf_doc, T)

    is_annotation = build_text_filter(page)
    n_text = add_text(msp, page, dxf_doc, T, is_annotation)

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
    }
