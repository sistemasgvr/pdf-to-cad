"""
raster_pipeline.py — Vectorización de PDFs escaneados (rasterizados) con OpenCV.

Flujo:
  1. Rasterizar la página a RASTER_DPI.
  2. Separar por color (HSV) -> máscara por tipo de utilidad.
  3. HoughLinesP por máscara, con parámetros (grosor) ajustables por capa.
  4. Unir segmentos colineales en polilíneas.
  5. OCR (pytesseract) para labels; asociar al elemento más cercano.

Es "best-effort": un escaneo nunca dará la exactitud de un PDF vectorizado.
Todos los parámetros están en config.py (sección RASTER_*).

Dependencias extra (instalar solo si se usa esta ruta):
    pip install opencv-python numpy pytesseract pillow
    + binario Tesseract-OCR en el sistema para OCR.
"""
import math
from collections import defaultdict

import fitz

import config as C

try:
    import cv2
    import numpy as np
    _CV_OK = True
except ImportError:
    _CV_OK = False


def _require_cv():
    if not _CV_OK:
        raise RuntimeError(
            "Ruta rasterizada requiere OpenCV: pip install opencv-python numpy pytesseract pillow"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Rasterizado
# ─────────────────────────────────────────────────────────────────────────────
def rasterize(page, dpi=None):
    """Devuelve (imagen BGR uint8, px_per_pt)."""
    _require_cv()
    dpi = dpi or C.RASTER_DPI
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img, zoom


# ─────────────────────────────────────────────────────────────────────────────
# Máscaras por color
# ─────────────────────────────────────────────────────────────────────────────
def color_mask(hsv, ranges):
    _require_cv()
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for low, high in ranges:
        mask |= cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))
    return mask


# ─────────────────────────────────────────────────────────────────────────────
# Detección de líneas
# ─────────────────────────────────────────────────────────────────────────────
def detect_lines(mask, params):
    """HoughLinesP sobre una máscara. Devuelve lista de (x0,y0,x1,y1) en px."""
    _require_cv()
    th = max(1, params.get("thickness", 1))
    if th > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (th, th))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    edges = cv2.Canny(mask, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, math.pi / 180,
        threshold=params.get("threshold", 50),
        minLineLength=params.get("minLineLength", 40),
        maxLineGap=params.get("maxLineGap", 8),
    )
    if lines is None:
        return []
    return [tuple(map(float, l[0])) for l in lines]


def classify_linetype(mask, x0, y0, x1, y1, n_samples=24):
    """Continua vs discontinua vs punto-guión: muestrea la máscara a lo largo
    del segmento y mide la fracción de tinta y el número de transiciones."""
    _require_cv()
    h, w = mask.shape
    on = 0
    seq = []
    for i in range(n_samples):
        t = i / (n_samples - 1)
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        if 0 <= x < w and 0 <= y < h:
            v = 1 if mask[y, x] > 0 else 0
        else:
            v = 0
        seq.append(v)
        on += v
    frac = on / n_samples
    transitions = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    if frac > 0.85:
        return "CONTINUOUS"
    if transitions >= 6:
        return "DASH_DOT"
    return "DASHED"


# ─────────────────────────────────────────────────────────────────────────────
# Unión de segmentos colineales (en píxeles)
# ─────────────────────────────────────────────────────────────────────────────
def merge_segments_px(segs):
    buckets = defaultdict(list)
    for (x0, y0, x1, y1) in segs:
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        nx, ny = -dy / length, dx / length
        perp = x0 * nx + y0 * ny
        akey = round(ang / C.RASTER_MERGE_ANGLE_TOL_DEG)
        pkey = round(perp / max(C.RASTER_MERGE_PERP_TOL_PX, 1e-6))
        buckets[(akey, pkey)].append((x0, y0, x1, y1, ang))

    out = []
    for _key, group in buckets.items():
        ang = group[0][4]
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        proj = []
        for (x0, y0, x1, y1, _a) in group:
            t0 = x0 * ux + y0 * uy
            t1 = x1 * ux + y1 * uy
            (lo, hi) = ((x0, y0), (x1, y1)) if t0 <= t1 else ((x1, y1), (x0, y0))
            proj.append((min(t0, t1), max(t0, t1), lo, hi))
        proj.sort(key=lambda r: r[0])
        cs, ce, cp0, cp1 = proj[0]
        for (s, e, lo, hi) in proj[1:]:
            if s <= ce + C.RASTER_MERGE_MAX_BRIDGE_PX:
                if e > ce:
                    ce, cp1 = e, hi
            else:
                out.append((cp0, cp1))
                cs, ce, cp0, cp1 = s, e, lo, hi
        out.append((cp0, cp1))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# OCR  (devuelve cajas completas: texto + bbox + confianza)
# ─────────────────────────────────────────────────────────────────────────────
def ocr_boxes(gray):
    """OCR con Tesseract en modo 'texto disperso' (--psm 11), apto para planos.
    Devuelve [{txt, conf, x, y, w, h, cx, cy}] en píxeles. [] si no hay binario."""
    if not C.RASTER_OCR_ENABLED:
        return []
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return []
    _require_cv()
    try:
        data = pytesseract.image_to_data(
            gray, output_type=Output.DICT, config="--psm 11")
    except (pytesseract.TesseractNotFoundError, EnvironmentError):
        print("   ⚠ Tesseract no encontrado: se omite el OCR.")
        return []
    out = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        x, y, w, h = (data["left"][i], data["top"][i],
                      data["width"][i], data["height"][i])
        out.append({"txt": txt, "conf": conf, "x": x, "y": y, "w": w, "h": h,
                    "cx": x + w / 2.0, "cy": y + h / 2.0})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Limpieza del raster: borrar texto/símbolos y motas antes de vectorizar
# ─────────────────────────────────────────────────────────────────────────────
def erase_text(gray, boxes, pad, conf_min):
    """Pinta de blanco (fondo) las cajas de texto OCR para que sus trazos no se
    vectoricen como líneas. Devuelve copia limpia."""
    out = gray.copy()
    h, w = gray.shape
    for b in boxes:
        if b["conf"] < conf_min:
            continue
        x0 = max(0, b["x"] - pad); y0 = max(0, b["y"] - pad)
        x1 = min(w, b["x"] + b["w"] + pad); y1 = min(h, b["y"] + b["h"] + pad)
        out[y0:y1, x0:x1] = 255
    return out


def remove_text_cc(ink, char_max):
    """Elimina texto/marcas de forma independiente a la orientación: un componente
    conexo cuyo bbox cabe en char_max x char_max px (AMBOS lados) es un glifo o
    una marca 'X' y se descarta. Las líneas (largas en alguna dirección, p.ej. una
    diagonal de 200px tiene bbox 141x141) se conservan."""
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.ones(n, dtype=bool)
    keep[0] = False  # fondo
    for i in range(1, n):
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if bw < char_max and bh < char_max:
            keep[i] = False
    return np.where(keep[lbl], np.uint8(255), np.uint8(0))


# ─────────────────────────────────────────────────────────────────────────────
# Detección de líneas por LSD (Line Segment Detector)
# ─────────────────────────────────────────────────────────────────────────────
def skeletonize(ink):
    """Adelgaza los trazos a su eje (1 px) por esqueleto morfológico. Evita que el
    LSD detecte los DOS bordes de una misma línea (líneas dobles). Las líneas
    realmente dobles del plano (bordillos) se conservan: son trazos separados."""
    img = ink.copy()
    skel = np.zeros_like(img)
    elem = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    for _ in range(60):                      # tope de seguridad
        opened = cv2.morphologyEx(img, cv2.MORPH_OPEN, elem)
        temp = cv2.subtract(img, opened)
        eroded = cv2.erode(img, elem)
        skel = cv2.bitwise_or(skel, temp)
        img = eroded
        if cv2.countNonZero(img) == 0:
            break
    # engrosar 1px para que el LSD enganche el eje de forma continua
    return cv2.dilate(skel, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)))


def lsd_segments(gray, scale, min_len):
    """LSD sobre escala de grises. Devuelve [(x0,y0,x1,y1)] en px de la imagen
    original (escala completa), filtrando segmentos cortos."""
    work = gray
    if scale and scale != 1.0:
        work = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lsd = cv2.createLineSegmentDetector()
    lines = lsd.detect(work)[0]
    if lines is None:
        return []
    inv = 1.0 / (scale or 1.0)
    out = []
    for l in lines:
        v = np.ravel(np.asarray(l))   # robusto a (1,4) o (4,) según versión de OpenCV
        if v.size < 4:
            continue
        x0, y0, x1, y1 = float(v[0]) * inv, float(v[1]) * inv, float(v[2]) * inv, float(v[3]) * inv
        if math.hypot(x1 - x0, y1 - y0) >= min_len:
            out.append((x0, y0, x1, y1))
    return out


def collapse_doubles(merged, ang_tol_deg, max_gap_px):
    """Colapsa los DOS bordes que el LSD detecta por cada trazo: si dos líneas son
    casi paralelas, se solapan y están a <= max_gap_px perpendicular, deja la más
    larga. Conserva las dobles reales (bordillos), que van más separadas."""
    buckets = defaultdict(list)
    for (p0, p1) in merged:
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        nx, ny = -dy / L, dx / L
        ux, uy = dx / L, dy / L
        perp = p0[0] * nx + p0[1] * ny
        t0 = p0[0] * ux + p0[1] * uy
        t1 = p1[0] * ux + p1[1] * uy
        buckets[round(ang / ang_tol_deg)].append(
            {"p0": p0, "p1": p1, "L": L, "perp": perp,
             "t0": min(t0, t1), "t1": max(t0, t1)})
    out = []
    for items in buckets.values():
        items.sort(key=lambda d: -d["L"])
        used = [False] * len(items)
        for i, a in enumerate(items):
            if used[i]:
                continue
            out.append((a["p0"], a["p1"]))
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                b = items[j]
                overlap = not (b["t1"] < a["t0"] - 2 or b["t0"] > a["t1"] + 2)
                if abs(a["perp"] - b["perp"]) <= max_gap_px and overlap:
                    used[j] = True   # es el otro borde / duplicado del mismo trazo
    return out


def _pt_seg_dist(px, py, ax, ay, bx, by):
    """Distancia de un punto al segmento AB."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ─────────────────────────────────────────────────────────────────────────────
# Entrada principal de la ruta rasterizada
# ─────────────────────────────────────────────────────────────────────────────
def run(page, dxf_doc):
    """Procesa una página rasterizada. Si el escaneo tiene color, separa por
    color (RASTER_COLOR_RANGES); si es monocromo (B&N), usa la tubería basada
    en forma: OCR borra texto -> LSD vectoriza líneas -> se unen y clasifican."""
    _require_cv()
    from vector_pipeline import detect_scale, setup_linetypes, CoordTransform
    setup_linetypes(dxf_doc)

    img, zoom = rasterize(page)
    h_px = img.shape[0]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sat_mean = float(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1].mean())

    scale = detect_scale(page)
    # MISMO mapeo que el pipeline vector y la app de marcado (px de imagen ->
    # punto display -> mediabox (derotación) -> CAD). Así los 3 coinciden en
    # coordenadas para cualquier rotación de página.
    T = CoordTransform(page, scale)
    derot = page.derotation_matrix

    def to_cad(px, py):
        mp = fitz.Point(px / zoom, py / zoom) * derot
        return T.point(mp.x, mp.y)

    if sat_mean >= C.RASTER_BW_SAT_THRESH:
        print(f"   escaneo a COLOR (sat={sat_mean:.1f}) -> separación por color")
        return _run_color(page, dxf_doc, img, zoom, to_cad, scale)

    print(f"   escaneo MONOCROMO (sat={sat_mean:.1f}) -> vectorización por forma (LSD)")
    return _run_bw(page, dxf_doc, gray, zoom, to_cad, scale)


def _run_bw(page, dxf_doc, gray, zoom, to_cad, scale):
    from vector_pipeline import ensure_layer, parse_attributes
    msp = dxf_doc.modelspace()

    # 1) OCR: detectar texto/marcas. Sirve para (a) borrarlas del raster y
    #    (b) escribirlas como TEXT y (c) identificar tuberías por callout.
    boxes = ocr_boxes(gray)

    # 2) Borrar texto y binarizar la geometría restante.
    clean = erase_text(gray, boxes, C.RASTER_TEXT_ERASE_PAD_PX, C.RASTER_TEXT_ERASE_CONF)
    _, ink = cv2.threshold(clean, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = remove_text_cc(ink, C.RASTER_TEXT_CC_MAX_PX)
    if getattr(C, "RASTER_SKELETONIZE", True):
        ink = skeletonize(ink)               # 1px de eje -> el LSD da UNA línea, no dos bordes
    # Volver a gris (fondo blanco, líneas negras) para el LSD.
    gray_clean = cv2.bitwise_not(ink)

    # 3) Vectorizar con LSD y unir colineales en líneas largas uniformes.
    segs = lsd_segments(gray_clean, C.RASTER_LSD_SCALE, C.RASTER_MIN_LINE_LEN_PX)
    merged = merge_segments_px(segs)
    merged = [(p0, p1) for (p0, p1) in merged
              if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) >= C.RASTER_MIN_LINE_LEN_PX]
    n_before = len(merged)
    merged = collapse_doubles(merged, C.RASTER_MERGE_ANGLE_TOL_DEG,
                              getattr(C, "RASTER_DOUBLE_MAX_GAP_PX", 6.0))
    print(f"   Líneas: {n_before} -> {len(merged)} (colapso de bordes dobles)")

    # 4) Solo geometría: coser los segmentos en polilíneas y CERRAR las cuadras
    #    (una cuadra es una geometría que se cierra). Sin clasificar tipos ni color.
    from vector_pipeline import ensure_layer, chain_pieces
    ensure_layer(dxf_doc, "EJE_VIA")
    tol = getattr(C, "RASTER_MERGE_MAX_BRIDGE_PX", 26.0)
    chains = chain_pieces([[p0, p1] for (p0, p1) in merged], tol)
    n_geom = 0
    n_closed = 0
    for ch in chains:
        if len(ch) < 2:
            continue
        closed = len(ch) >= 4 and math.hypot(ch[0][0] - ch[-1][0], ch[0][1] - ch[-1][1]) <= tol * 1.5
        pts = [to_cad(x, y) for (x, y) in ch]
        e = msp.add_lwpolyline(pts, dxfattribs={"layer": "EJE_VIA"})
        if closed:
            e.close(True)
            n_closed += 1
        n_geom += 1
    print(f"   Contornos: {n_geom} polilíneas ({n_closed} cerradas como cuadra)")

    return {
        "scale_ft_per_pt": scale, "dpi": C.RASTER_DPI, "mode": "bw_plain",
        "n_geometry": n_geom, "per_layer": {"EJE_VIA": n_geom}, "n_text": 0,
        "callouts": [],
    }


def _run_color(page, dxf_doc, img, zoom, to_cad, scale):
    from vector_pipeline import ensure_layer
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    msp = dxf_doc.modelspace()
    n_geom = 0
    per_layer = {}
    for layer, ranges in C.RASTER_COLOR_RANGES.items():
        ensure_layer(dxf_doc, layer)
        mask = color_mask(hsv, ranges)
        params = C.RASTER_HOUGH.get(layer, C.RASTER_HOUGH["default"])
        merged = merge_segments_px(detect_lines(mask, params))
        per_layer[layer] = len(merged)
        for (p0, p1) in merged:
            msp.add_line(to_cad(*p0), to_cad(*p1), dxfattribs={"layer": layer})
            n_geom += 1

    ensure_layer(dxf_doc, "TEXTO")
    from ezdxf.enums import TextEntityAlignment
    n_text = 0
    for b in ocr_boxes(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)):
        if b["conf"] < C.RASTER_OCR_MIN_CONF:
            continue
        cx, cy = to_cad(b["cx"], b["cy"])
        h_ft = max((b["h"] / zoom) * scale * C.TEXT_SCALE_FACTOR, C.TEXT_MIN_HEIGHT_FT)
        ent = msp.add_text(b["txt"], height=h_ft, dxfattribs={"layer": "TEXTO"})
        ent.set_placement((cx, cy), align=TextEntityAlignment.MIDDLE_CENTER)
        n_text += 1

    return {
        "scale_ft_per_pt": scale, "dpi": C.RASTER_DPI, "mode": "color",
        "n_geometry": n_geom, "per_layer": per_layer, "n_text": n_text,
    }
