"""
callout_ocr.py — Lectura de CALLOUTS por OCR en PDFs vectoriales APLANADOS.

Algunos as-builts vienen como vector sin texto vivo (las letras son trazos), así
que el texto de los callouts —el rótulo donde arranca cada flecha que señala una
línea o elemento— no se puede extraer con get_text(). Aquí se renderiza la página,
se lee con Tesseract, se mapea cada etiqueta a coordenadas CAD (alineadas con la
geometría) y se parsea su NOMENCLATURA:

    diámetro · material · dueño/utilidad · distancia(offset) · estación · elemento

Cada etiqueta se coloca en la capa TEXTO (con los atributos en XDATA) y se produce
un reporte .txt. Parámetros en config.py (VECTOR_OCR_*).
"""
import re
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


# ─────────────────────────────────────────────────────────────────────────────
# Diccionarios de nomenclatura
# ─────────────────────────────────────────────────────────────────────────────
MATERIALS = {  # token OCG -> descripción (primero los más específicos)
    "DIP": "Hierro dúctil (DIP)", "DI": "Hierro dúctil (DI)",
    "CIP": "Hierro fundido (CIP)", "CI": "Hierro fundido (CI)",
    "PVC": "PVC", "RCP": "Concreto reforzado (RCP)",
    "VCP": "Arcilla vitrificada (VCP)", "ACP": "Asbesto-cemento (ACP)",
    "CMP": "Metal corrugado (CMP)", "PCCP": "PCCP",
    "STL": "Acero (STL)", "STEEL": "Acero", "HDPE": "HDPE",
    "CONC": "Concreto", "CML": "Acero CML&C",
}
OWNERS = {  # token -> dueño / utilidad
    "DWPWS": "LADWP (agua)", "LADWP": "LADWP", "DWP": "LADWP",
    "SCG": "SoCal Gas", "SOCAL": "SoCal Gas", "MTA": "MTA",
    "BRT": "BRT / Metro", "ATT": "AT&T", "CITY": "Ciudad de Los Ángeles",
}
ELEMENTS = {  # token -> elemento
    "GV": "Válvula de compuerta", "FH": "Hidrante", "BEND": "Codo",
    "REDUCER": "Reductor", "CROSS": "Cruz", "TEE": "Tee", "CAP": "Tapa",
    "CPLG": "Acople mecánico", "COUPLING": "Acople", "VALVE": "Válvula",
    "CASING": "Encamisado / Casing", "CSG": "Encamisado / Casing",
    "SEWER": "Alcantarillado", "WATER": "Agua", "GAS": "Gas",
    "CURB": "Bordillo", "TRAFFIC": "Señal de tráfico",
}


def clean_text(t):
    """Normaliza el resultado del OCR (el símbolo � cubre " ' y °) y elimina
    caracteres de ruido típicos del OCR que nunca aparecen en el rótulo."""
    t = (t.replace("�", '"').replace("”", '"').replace("“", '"')
          .replace("’", "'").replace("‘", "'").replace("º", "°"))
    for ch in "|\\{}*~^_":
        t = t.replace(ch, "")
    return re.sub(r"\s{2,}", " ", t).strip()


def parse_callout(text):
    """Extrae la nomenclatura de un callout. Devuelve dict (solo campos hallados)."""
    t = clean_text(text).upper()
    a = {}
    # Diámetro: número + comilla, valor plausible, NO ángulo de codo ni escala.
    for m in re.finditer(r'(\d{1,2})\s*"', t):
        v = int(m.group(1))
        tail = t[m.end():m.end() + 6]
        pre = t[max(0, m.start() - 2):m.start() + 3]
        if 2 <= v <= 60 and "BEND" not in tail and "=" not in pre:
            a["diametro"] = f'{v}"'
            break
    for k, v in MATERIALS.items():
        if re.search(r'\b' + k + r'\b', t):
            a["material"] = v
            break
    for k, v in OWNERS.items():
        if re.search(r'\b' + k + r'\b', t):
            a["dueno"] = v
            break
    m = re.search(r"(\d{1,3})\s*'?\s*([EWNS])\s*/?\s*O?F?\.?\s*(OF\s*)?C\s*/?\s*[LA]", t)
    if m:
        a["distancia"] = f"{m.group(1)}' {m.group(2)} de CL"
    m = re.search(r'(\d{1,3}\+\d{2})', t)
    if m:
        a["estacion"] = m.group(1)
    m = re.search(r'(\d{1,3})\s*"?\s*BEND', t)
    if m:
        a["codo_grados"] = m.group(1) + "°"
    els = []
    for k, v in ELEMENTS.items():
        if re.search(r'\b' + k + r'\b', t):
            els.append(v)
    if els:
        a["elemento"] = "; ".join(sorted(set(els)))
    if "ABND" in t or "ABAND" in t:
        a["estado"] = "Abandonado"
    return a


_DIM_RE = re.compile(r'^[<(]?\s*\d{1,4}(\.\d+)?\s*[\'"°]?\s*[)>¢]?\.?$')


def is_dimension(text):
    """True si el texto es una COTA / elevación / número suelto (no se dibuja)."""
    s = clean_text(text).strip().strip(".").strip()
    if not s:
        return True
    if "+" in s:                      # estación (149+10) -> NO es cota
        return False
    if _DIM_RE.match(s):              # 43'  640  18"  <18'¢
        return True
    if re.fullmatch(r'\d{1,3}"?P', s):   # cajas 48"P 44"P
        return True
    if re.fullmatch(r"[\d\s'\"().,=+/x×-]+", s) and not re.search(r'[A-Za-z]', s):
        return True                   # solo números/símbolos de cota
    return False


def utility_class(text):
    """Capa de utilidad implícita en el texto del callout (o None)."""
    t = clean_text(text).upper()
    for kw, layer in C.UTILITY_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', t):
            return layer
    return None


# Abreviaturas reales de 2-3 letras que SÍ aparecen en estos planos.
_OK_SHORT = {
    "FH", "GV", "CL", "RW", "DI", "SS", "SD", "CG", "WL", "MH", "PL", "TS", "WM",
    "CI", "IJ", "GA", "EG", "CB", "VC", "OF", "IN", "AT", "TO", "ON", "NO", "EX",
    "SEE", "DET", "STA", "TYP", "NTS", "AVE", "BND", "GAS", "VCP", "RCP", "PVC",
    "DIP", "CIP", "STL", "SCG", "CSG", "OHE", "MTA", "BRT", "DWP", "INV", "ANO",
}


# Diccionario de términos del dominio: si el token contiene uno, es texto REAL
# (sin importar mayúsculas/minúsculas) y NO se descarta. Resuelve los planos en
# minúscula ("Sewer", "Aband.") sin reactivar la basura.
KNOWN_TERMS = {
    "SEWER", "WATER", "GAS", "PIPE", "MAIN", "ANODE", "VALVE", "BEND", "REDUCER",
    "TEE", "CROSS", "CASING", "CSG", "HYDRANT", "MANHOLE", "COUPLING", "CPLG",
    "MECH", "INSTALL", "EXIST", "GRADE", "ABAND", "PROPOSED", "RECYCLED",
    "VCP", "RCP", "DIP", "CIP", "PVC", "ACP", "CMP", "PCCP", "HDPE", "STL",
    "STEEL", "CONC", "CML", "DWP", "DWPWS", "DWPPS", "DWPGS", "LADWP", "SCG",
    "SOCAL", "MTA", "BRT", "CITY", "PERMIT", "BUREAU", "ENGINEERING", "DISTRICT",
    "VALLEY", "REVISIONS", "REFERENCE", "ANGELES", "ALLEY", "STREET", "BLVD",
    "AVE", "CURB", "PAVEMENT", "STA", "PER", "INV", "DUCT", "COMM", "FRAC",
    "GV", "FH", "PTT", "OHE", "ANODES",
}


def has_known_term(text):
    up = text.upper()
    return any(k in up for k in KNOWN_TERMS)


def is_garbage(text):
    """True si el texto OCR es ruido. Primero se ACEPTA si contiene un término del
    dominio (dict) o una medida/estación; sólo entonces se aplican las heurísticas
    de ruido (símbolos raros, minúscula dominante sin contenido, tokens cortos)."""
    s = clean_text(text).strip()
    if len(s) < 2:
        return True
    if not any(c.isalnum() for c in s):
        return True
    # Aceptación por contenido válido (independiente de mayúsc/minúsc):
    if has_known_term(s):
        return False
    if re.search(r'\d\s*["\']', s) or re.search(r'\d+\+\d{2}', s):   # diámetro / estación
        return False
    if any(c in s for c in "<>@"):            # caracteres que no aparecen en el rótulo
        return True
    weird = [c for c in s if not (c.isalnum() or c in " '\".,/°+-()=:%&")]
    if len(weird) >= max(1, len(s) // 4):
        return True
    letters = [c for c in s if c.isalpha()]
    if letters:
        up = sum(1 for c in letters if c.isupper())
        if up / len(letters) < 0.6:               # mayúscula dominante (planos)
            if not re.search(r'\d', s):           # salvo que traiga número/cota
                return True
            if up / len(letters) < 0.3:
                return True
    # token puramente alfabético de 2-3 letras no reconocido -> ruido
    compact = s.replace(" ", "")
    if compact.isalpha() and len(compact) <= 3 and compact.upper() not in _OK_SHORT:
        return True
    # palabra de UNA sola letra minúscula aislada (p.ej. "4 IZ q", "a IES") -> ruido
    if any(len(w) == 1 and w.isalpha() and w.islower() for w in s.split()):
        return True
    # token corto con símbolo de operador (%&=+) -> fragmento de cota/símbolo
    if len(compact) <= 3 and any(c in s for c in "%&=+"):
        return True
    # mezcla letra+dígito de <=2 caracteres (p.ej. "2D", "4S", "Q2", "Z0") -> ruido
    if len(compact) <= 2 and re.search(r'[A-Za-z]', compact) and re.search(r'\d', compact):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# OCR + mapeo a coordenadas CAD
# ─────────────────────────────────────────────────────────────────────────────
def _ocr_lines(gray, min_conf):
    """Agrupa palabras OCR por línea. min_conf bajo = se captura más (para
    suprimir el texto de fondo). Cada salida incluye la confianza media."""
    import pytesseract
    from pytesseract import Output
    data = pytesseract.image_to_data(gray, output_type=Output.DICT, config="--psm 11")
    groups = defaultdict(list)
    for i in range(len(data["text"])):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if conf < min_conf:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups[key].append((data["left"][i], data["top"][i],
                            data["width"][i], data["height"][i], txt, conf))
    out = []
    for ws in groups.values():
        ws.sort(key=lambda w: w[0])
        raw = " ".join(w[4] for w in ws)
        x = min(w[0] for w in ws)
        y = min(w[1] for w in ws)
        x1 = max(w[0] + w[2] for w in ws)
        y1 = max(w[1] + w[3] for w in ws)
        h = sorted(w[3] for w in ws)[len(ws) // 2]   # mediana de altura
        conf = sum(w[5] for w in ws) / len(ws)
        out.append((raw, x, y, x1 - x, h, x1, y1, conf))
    return out


def isolate_text_cc(gray):
    """Separación texto/gráficos por componentes conexos: conserva SOLO los blobs
    de tamaño de carácter (texto) y elimina las líneas largas y símbolos grandes
    (tuberías, burbujas, achurado). Devuelve imagen con texto negro sobre blanco.
    Es lo que evita que el OCR invente texto a partir de los símbolos."""
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    cmin = C.VECTOR_OCR_CHAR_MIN_PX
    cmax = C.VECTOR_OCR_CHAR_MAX_PX
    fmin = C.VECTOR_OCR_CHAR_FILL_MIN
    keep = np.zeros(n, dtype=bool)
    for i in range(1, n):
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        a = stats[i, cv2.CC_STAT_AREA]
        mx = max(w, h)
        if mx < cmin or mx > cmax:        # ni motas ni líneas/símbolos grandes
            continue
        if a < fmin * w * h:              # muy fino/hueco = trazo de línea
            continue
        keep[i] = True
    return np.where(keep[lbl], np.uint8(0), np.uint8(255))


def _orient_backmap(orient, Hd, Wd):
    """Devuelve f(ox,oy)->(dx,dy): píxel de la imagen rotada -> píxel del render
    display original. Hd,Wd = alto,ancho del render display."""
    if orient == 0:
        return lambda ox, oy: (ox, oy)
    if orient == 90:    # cv2.ROTATE_90_CLOCKWISE
        return lambda ox, oy: (oy, Hd - 1 - ox)
    return lambda ox, oy: (Wd - 1 - oy, ox)   # 270 (CCW)


def extract_callouts(page, T):
    """OCR multi-orientación (0/90/270): captura texto horizontal y rotado, lo
    mapea fielmente a CAD (posición y ángulo) y parsea su nomenclatura.
    Devuelve registros {raw, clean, attrs, util, cad, rot, h_ft, mbox, cad_box,
    conf, is_dim}."""
    if not _CV_OK:
        print("   ⚠ OpenCV no disponible: se omite el OCR de callouts.")
        return []
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        print("   ⚠ pytesseract no instalado: se omite el OCR de callouts.")
        return []

    zoom = C.VECTOR_OCR_ZOOM
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY if pix.n == 3 else cv2.COLOR_RGBA2GRAY)
    if getattr(C, "VECTOR_OCR_TEXT_CC", False):
        gray = isolate_text_cc(gray)        # separar texto de gráficos antes del OCR
    elif getattr(C, "VECTOR_OCR_BINARIZE", False):
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    Hd, Wd = gray.shape
    derot = page.derotation_matrix
    suppress_conf = getattr(C, "VECTOR_OCR_SUPPRESS_CONF", 8)

    def disp_to_cad(dx, dy):
        mp = fitz.Point(dx / zoom, dy / zoom) * derot
        return T.point(mp.x, mp.y)

    rot_codes = {90: cv2.ROTATE_90_CLOCKWISE, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    records = []
    for orient in getattr(C, "VECTOR_OCR_ORIENTATIONS", (0,)):
        oimg = gray if orient == 0 else cv2.rotate(gray, rot_codes[orient])
        try:
            lines = _ocr_lines(oimg, suppress_conf)
        except Exception as e:
            print(f"   ⚠ OCR no disponible ({type(e).__name__}): se omite el texto.")
            return []
        back = _orient_backmap(orient, Hd, Wd)
        for raw, x, y, w, h, x1, y1, conf in lines:
            # Dirección de lectura (izq->der en la imagen orientada) -> CAD.
            sd = back(x, y + h / 2.0)          # inicio de lectura (display px)
            ed = back(x1, y + h / 2.0)         # fin de lectura
            cs_d = disp_to_cad(*sd); ce_d = disp_to_cad(*ed)
            cad = ((cs_d[0] + ce_d[0]) / 2.0, (cs_d[1] + ce_d[1]) / 2.0)
            rot = math.degrees(math.atan2(ce_d[1] - cs_d[1], ce_d[0] - cs_d[0])) % 360
            # bbox en mediabox (para suprimir fondo) y en CAD (para leaders).
            corners_d = [back(x, y), back(x1, y), back(x, y1), back(x1, y1)]
            mbs = [fitz.Point(dx / zoom, dy / zoom) * derot for dx, dy in corners_d]
            mbox = (min(p.x for p in mbs), min(p.y for p in mbs),
                    max(p.x for p in mbs), max(p.y for p in mbs))
            cad_c = [disp_to_cad(dx, dy) for dx, dy in corners_d]
            cad_box = (min(p[0] for p in cad_c), min(p[1] for p in cad_c),
                       max(p[0] for p in cad_c), max(p[1] for p in cad_c))
            cleaned = clean_text(raw)
            records.append({
                "raw": raw, "clean": cleaned, "attrs": parse_callout(raw),
                "util": utility_class(raw), "is_dim": is_dimension(raw),
                "cad": cad, "rot": rot, "mbox": mbox, "cad_box": cad_box, "conf": conf,
                "h_ft": max((h / zoom) * T.scale * C.TEXT_SCALE_FACTOR, C.TEXT_MIN_HEIGHT_FT),
            })
    return records


def _box_overlap(a, b):
    """Fracción de solape (intersección / área menor) entre dos cajas CAD."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    aa = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    ab = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / min(aa, ab)


def dedupe_for_placement(records, min_conf, symbols=None):
    """Selecciona qué etiquetas COLOCAR:
      - confianza >= min_conf, no cota, no basura, >=2 caracteres
      - dedup ESPACIAL entre orientaciones: por cada zona se queda la de mayor
        confianza (mata la basura vertical que solapa texto horizontal real)
      - excluye texto que cae sobre un símbolo circular (válvulas, burbujas)."""
    symbols = symbols or []
    cand = [r for r in records
            if r["conf"] >= min_conf and not r["is_dim"]
            and len(r["clean"].strip()) >= 2 and not is_garbage(r["clean"])]
    def area(b):
        return max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))

    def _vertical(r):
        a = r.get("rot", 0.0) % 180.0
        return 1 if 45 < a < 135 else 0     # 1 = vertical (se procesa después)
    # Horizontales primero (se conservan); un fantasma vertical que solape un
    # texto horizontal real se descarta. Empate -> mayor confianza.
    cand.sort(key=lambda r: (_vertical(r), -r["conf"]))
    kept = []
    for r in cand:
        cx, cy = r["cad"]
        # sobre un símbolo circular -> no es texto
        if any((cx - sx) ** 2 + (cy - sy) ** 2 <= sr * sr for (sx, sy, sr) in symbols):
            continue
        # Duplicado REAL de una etiqueta ya aceptada (misma zona leída en otra
        # orientación). NO se descarta una caja pequeña solo porque una grande la
        # solape: se exige tamaño similar O mismo texto.
        dup = False
        for k in kept:
            ov = _box_overlap(r["cad_box"], k["cad_box"])
            if ov <= 0.25:
                continue
            ratio = area(r["cad_box"]) / area(k["cad_box"])
            same = r["clean"].replace(" ", "") == k["clean"].replace(" ", "")
            if same or (ov > 0.6 and 0.4 <= ratio <= 2.5):
                dup = True
                break
        if not dup:
            kept.append(r)
    return kept


def add_text_layer(msp, dxf, records):
    """Coloca cada callout como TEXT en TEXTO, centrado y con el ángulo real."""
    from vector_pipeline import ensure_layer
    from ezdxf.enums import TextEntityAlignment
    ensure_layer(dxf, "ANOTACION")
    if "CAD_TEXT" not in dxf.styles:
        dxf.styles.add("CAD_TEXT", font=C.TEXT_FONT)
    try:
        dxf.appids.add("PDFCAD")
    except Exception:
        pass
    n = 0
    for r in records:
        rot = r.get("rot", 0.0)
        if rot > 90 and rot < 270:       # mantener el texto legible (no de cabeza)
            rot = (rot + 180) % 360
        ent = msp.add_text(r["clean"], height=r["h_ft"], dxfattribs={
            "layer": "ANOTACION", "style": "CAD_TEXT", "rotation": rot})
        ent.set_placement(r["cad"], align=TextEntityAlignment.MIDDLE_CENTER)
        if r["attrs"]:
            try:
                ent.set_xdata("PDFCAD", [(1000, f"{k}={v}") for k, v in r["attrs"].items()])
            except Exception:
                pass
        n += 1
    return n


# ─────────────────────────────────────────────────────────────────────────────
# Reporte .txt
# ─────────────────────────────────────────────────────────────────────────────
_FIELDS = [("diametro", "Diámetro"), ("material", "Material"), ("dueno", "Dueño"),
           ("distancia", "Distancia"), ("estacion", "Estación"),
           ("codo_grados", "Codo"), ("elemento", "Elemento"), ("estado", "Estado")]


def write_report(records, path, pdf_name, scale_ft_per_pt):
    """Escribe el reporte de nomenclatura. Devuelve (n_total, n_con_nomenclatura)."""
    KEYS = ("diametro", "material", "dueno", "distancia", "estacion", "elemento")
    meaningful = [r for r in records if any(k in r["attrs"] for k in KEYS)]

    lines = []
    lines.append("=" * 78)
    lines.append("REPORTE DE NOMENCLATURA DE CALLOUTS")
    lines.append("=" * 78)
    lines.append(f"PDF origen      : {pdf_name}")
    lines.append(f"Escala          : 1\" = {scale_ft_per_pt * 72:.0f}'")
    lines.append(f"Callouts leídos : {len(records)}")
    lines.append(f"Con nomenclatura: {len(meaningful)}")
    lines.append("")
    lines.append("Campos detectados por callout: ✓ = presente")
    lines.append("-" * 78)
    hdr = (f"{'#':>3}  {'Diám':>5} {'Mat':>3} {'Dueño':>5} {'Dist':>4} "
           f"{'Estac':>5} {'Elem':>4}  Texto")
    lines.append(hdr)
    lines.append("-" * 78)
    for i, r in enumerate(meaningful, 1):
        a = r["attrs"]
        def mk(k):
            return "✓" if k in a else "·"
        lines.append(
            f"{i:>3}  {mk('diametro'):>5} {mk('material'):>3} {mk('dueno'):>5} "
            f"{mk('distancia'):>4} {mk('estacion'):>5} {mk('elemento'):>4}  "
            f"{r['clean'][:40]}")
    lines.append("")
    lines.append("=" * 78)
    lines.append("DETALLE POR CALLOUT")
    lines.append("=" * 78)
    for i, r in enumerate(meaningful, 1):
        a = r["attrs"]
        cx, cy = r["cad"]
        lines.append(f"\n[{i}] \"{r['clean']}\"")
        lines.append(f"     Ubicación CAD : ({cx:.1f}, {cy:.1f}) ft")
        for k, label in _FIELDS:
            if k in a:
                lines.append(f"     {label:<13}: {a[k]}")

    # Resúmenes
    def tally(key):
        c = defaultdict(int)
        for r in meaningful:
            if key in r["attrs"]:
                c[r["attrs"][key]] += 1
        return c

    lines.append("\n" + "=" * 78)
    lines.append("RESUMEN")
    lines.append("=" * 78)
    for key, label in (("diametro", "Diámetros"), ("material", "Materiales"),
                       ("dueno", "Dueños / utilidades"), ("elemento", "Elementos")):
        c = tally(key)
        if c:
            lines.append(f"\n{label}:")
            for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
                lines.append(f"   {v:>3} × {k}")
    estaciones = sorted({r["attrs"]["estacion"] for r in meaningful if "estacion" in r["attrs"]})
    if estaciones:
        lines.append("\nEstaciones referenciadas:")
        lines.append("   " + ", ".join(estaciones))

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(records), len(meaningful)
