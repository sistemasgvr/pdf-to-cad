"""
la_reference.py — Descarga geometría real de la Ciudad de Los Ángeles (NavigateLA)
para el recuadro del plano georreferenciado y la agrega al DXF como CAPAS de
referencia, en EPSG:2229 (pies). Requiere internet.

Se pide la geometría directamente en 2229 (outSR), así entra al DXF sin reproyectar.
"""
import json
import math
import urllib.parse
import urllib.request

_BASE = "https://maps.lacity.org/arcgis/rest/services/Mapping/NavigateLA/MapServer"
_UA = "pdf-to-cad-georef/1.0 (staff-engineering)"
LAYER_STREETS = 337     # ejes de calle (polilíneas)
LAYER_PARCELS = 395     # parcelas (polígonos)


def _fetch(layer, bbox, epsg=2229, timeout=30, tol=None):
    """`tol` = maxAllowableOffset en pies: el servidor simplifica la geometría
    antes de enviarla (menos vértices → descarga y dibujo más rápidos). Sin él,
    un radio de varias cuadras traía decenas de miles de vértices y el mapa se
    volvía inusable al hacer zoom/desplazar."""
    xmin, ymin, xmax, ymax = bbox
    p = {"where": "1=1", "geometry": f"{xmin},{ymin},{xmax},{ymax}",
         "geometryType": "esriGeometryEnvelope", "inSR": str(epsg),
         "spatialRel": "esriSpatialRelIntersects", "outFields": "OBJECTID",
         "returnGeometry": "true", "outSR": str(epsg), "f": "json"}
    if tol:
        p["maxAllowableOffset"] = str(tol)
    url = f"{_BASE}/{layer}/query?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ─────────────────────────── intersecciones por NOMBRE de calle ───────────────────────────
# La capa 337 guarda el nombre y el sufijo en campos SEPARADOS (STNAME='COLFAX',
# STSFX='AVE'). Eso permite resolver "colfax and chandler" sin que el usuario
# tenga que escribir "COLFAX AVE & CHANDLER BLVD": se piden los tramos de cada
# calle por STNAME y se cruzan geométricamente, que es justo lo que hace
# NavigateLA. Los geocodificadores genéricos (Esri/Nominatim) sí exigen el
# sufijo, y por eso fallaban.

# Tipos de vía y prefijos direccionales: STNAME NO los incluye (van en STSFX y
# TDIR), así que hay que quitarlos de lo que escribe el usuario. Si no, buscar
# "COLFAX AVE" no encontraría nada porque STNAME es solo "COLFAX".
_ST_TYPES = {"AVE", "AVENUE", "BLVD", "BOULEVARD", "ST", "STREET", "DR", "DRIVE",
             "RD", "ROAD", "PL", "PLACE", "WAY", "LN", "LANE", "CT", "COURT",
             "TER", "TERRACE", "CIR", "CIRCLE", "PKWY", "PARKWAY", "HWY",
             "HIGHWAY", "TRL", "TRAIL", "WALK", "ALY", "ALLEY"}
_ST_DIRS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW",
            "NORTH", "SOUTH", "EAST", "WEST"}


def normalize_street_name(name):
    """Deja solo el NOMBRE de la calle: quita el tipo de vía y el direccional.
    'W COLFAX AVE' → 'COLFAX'."""
    toks = [t for t in str(name).upper().replace(".", " ").split() if t]
    while toks and toks[0] in _ST_DIRS:
        toks.pop(0)
    while toks and toks[-1] in _ST_DIRS:
        toks.pop()
    while toks and toks[-1] in _ST_TYPES:
        toks.pop()
    return " ".join(toks)


def _street_paths(name, timeout=25):
    """Tramos [(sufijo, [(x,y),…]), …] en 2229 de todas las calles cuyo STNAME
    coincide con `name`. Prueba coincidencia exacta y, si no hay nada, por
    prefijo; también mira el nombre alternativo STNAME_A."""
    safe = normalize_street_name(name).replace("'", "''").strip()
    if not safe:
        return []
    for where in (f"STNAME='{safe}'",
                  f"STNAME LIKE '{safe}%'",
                  f"STNAME_A='{safe}'"):
        p = {"where": where, "outFields": "STNAME,STSFX", "returnGeometry": "true",
             "outSR": "2229", "f": "json"}
        url = f"{_BASE}/{LAYER_STREETS}/query?" + urllib.parse.urlencode(p)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except Exception:
            continue
        out = []
        for f in data.get("features", []):
            sfx = (f.get("attributes") or {}).get("STSFX") or ""
            for path in f.get("geometry", {}).get("paths", []):
                if len(path) >= 2:
                    out.append((sfx, [(x, y) for x, y, *_ in path]))
        if out:
            return out
    return []


def _seg_cross(a1, a2, b1, b2):
    """Punto de cruce de los segmentos a1a2 y b1b2, o None."""
    x1, y1 = a1; x2, y2 = a2; x3, y3 = b1; x4, y4 = b2
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def find_intersection_2229(street_a, street_b, timeout=25):
    """(x, y, etiqueta) en EPSG:2229 del cruce de dos calles de LA dadas por
    NOMBRE, sin sufijo: find_intersection_2229("colfax", "chandler").

    Devuelve None si alguna calle no existe o no se cruzan. Cuando la avenida
    es de doble calzada hay varios cruces a pocos pies: se agrupan y se
    promedia, para entregar UN punto y no tres."""
    A = _street_paths(street_a, timeout)
    if not A:
        return None
    B = _street_paths(street_b, timeout)
    if not B:
        return None
    hits = []
    for sa, pa in A:
        for a1, a2 in zip(pa, pa[1:]):
            for sb, pb in B:
                for b1, b2 in zip(pb, pb[1:]):
                    p = _seg_cross(a1, a2, b1, b2)
                    if p:
                        hits.append((p, sa, sb))
    if not hits:
        return None
    # Agrupa cruces a menos de 150 ft (calzadas separadas del mismo cruce)
    groups = []
    for p, sa, sb in hits:
        for g in groups:
            gx, gy = g["pts"][0]
            if (p[0] - gx) ** 2 + (p[1] - gy) ** 2 <= 150.0 ** 2:
                g["pts"].append(p); break
        else:
            groups.append({"pts": [p], "sa": sa, "sb": sb})
    g = max(groups, key=lambda g: len(g["pts"]))     # el cruce mejor soportado
    xs = [p[0] for p in g["pts"]]; ys = [p[1] for p in g["pts"]]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    na = f"{normalize_street_name(street_a)} {g['sa']}".strip()
    nb = f"{normalize_street_name(street_b)} {g['sb']}".strip()
    return (cx, cy, f"{na} & {nb}")


def _shapes(data):
    """Devuelve [(puntos, cerrado)] de las features (paths=abierto, rings=cerrado)."""
    out = []
    for f in data.get("features", []):
        g = f.get("geometry", {})
        for path in g.get("paths", []):
            if len(path) >= 2:
                out.append((path, False))
        for ring in g.get("rings", []):
            if len(ring) >= 2:
                out.append((ring, True))
    return out


def _ensure_layer(doc, name, color):
    if name not in doc.layers:
        doc.layers.new(name, dxfattribs={"color": color})


# Simplificación pedida al servidor, en pies (maxAllowableOffset).
#
# Calles: una tolerancia pequeña acelera la descarga y es inofensiva —queda muy
# por debajo del imán de 15 ft con el que se marcan los puntos de control—.
#
# Parcelas: NO se simplifican. Es tentador hacerlo (llegan ~4x más vértices que
# de las calles), pero son justo los vértices finos los que forman las esquinas
# REDONDEADAS de las que se extraen los centros de radio (ver arc_centers): con
# 1 ft de tolerancia el servidor las convierte en esquinas rectas y los centros
# detectados caen de ~190 a 17. Además no compensa: midiendo el redibujado del
# mapa, las capas vectoriales cuestan ~9 ms de ~166 ms — el grueso es el mapa
# base, que se controla con el nivel de tile (ver MAX_BASEMAP_ZOOM).
SIMPLIFY_STREETS_FT = 0.25
SIMPLIFY_PARCELS_FT = None


def fetch_streets_2229(cx, cy, radius=800, simplify=SIMPLIFY_STREETS_FT):
    """Calles (polilíneas [(x,y),…]) de NavigateLA alrededor de (cx,cy) en 2229."""
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    return [pts for pts, _closed in _shapes(_fetch(LAYER_STREETS, bbox, tol=simplify))]


def fetch_parcels_2229(cx, cy, radius=800, simplify=SIMPLIFY_PARCELS_FT):
    """Parcelas (anillos [(x,y),…]) de NavigateLA alrededor de (cx,cy) en 2229.
    Best-effort: devuelve [] si falla o hay demasiadas."""
    try:
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        return [pts for pts, _c in _shapes(_fetch(LAYER_PARCELS, bbox, tol=simplify))]
    except Exception:
        return []


# ─────────────────────────── centros de radio de las parcelas ───────────────────────────
def _circumcenter(p1, p2, p3):
    """Centro del círculo que pasa por 3 puntos, o None si son casi colineales."""
    ax, ay = p1; bx, by = p2; cx, cy = p3
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    a2 = ax * ax + ay * ay; b2 = bx * bx + by * by; c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy)


def arc_centers(rings, min_radius=5.0, max_radius=150.0, tol_ratio=0.10, min_run=3):
    """PUNTO MEDIO de cada esquina redondeada de las parcelas — un punto que
    cae SOBRE la propia línea curva, en la mitad del arco. Sirve como imán muy
    preciso para colocar un punto de control encima del redondeo real.

    (Antes se emitía el CENTRO del círculo, o sea el punto EQUIDISTANTE del
    arco a distancia = radio: quedaba dentro del área de la parcela y no sobre
    la curva. Ese es un punto geométricamente exacto pero no es donde el
    usuario espera clicar para georreferenciar — el usuario ve el borde
    redondeado en el plano y quiere marcar un punto sobre ese borde.)

    Detección: cada esquina redondeada llega como una sucesión de segmentos
    cortos que aproximan un arco. Se recorre cada anillo en ventanas de 3
    vértices; se acepta solo cuando hay `min_run` ventanas contiguas con
    circuncentro y radio coherentes (curvatura sostenida). El punto que se
    emite es la INTERSECCIÓN del arco con la bisectriz de los vértices
    involucrados: se toma el centro geométrico de esos vértices, se lleva a
    distancia = radio desde el centro del círculo, y ese es un punto exacto
    sobre el arco — justo en su mitad.

    Devuelve [(x, y, radio), …] en las mismas unidades de entrada (ft 2229).
    """
    out = []
    for pts in rings or []:
        p = [(x, y) for x, y, *_ in pts]
        if len(p) >= 3 and abs(p[0][0] - p[-1][0]) < 1e-9 and abs(p[0][1] - p[-1][1]) < 1e-9:
            p = p[:-1]                                  # anillo cerrado: sin duplicar
        n = len(p)
        if n < 4:
            continue
        # Por cada ventana i,i+1,i+2: (centro, radio, indice del vertice MEDIO)
        cand = []
        for i in range(n):
            a, b, c = p[i], p[(i + 1) % n], p[(i + 2) % n]
            ctr = _circumcenter(a, b, c)
            if ctr is None:
                cand.append(None); continue
            r = math.hypot(b[0] - ctr[0], b[1] - ctr[1])
            if not (min_radius <= r <= max_radius):
                cand.append(None); continue
            # segmentos CORTOS respecto al radio: filtra esquinas rectas cuyo
            # circuncentro es casual (tres vertices casi colineales)
            s1 = math.hypot(b[0] - a[0], b[1] - a[1])
            s2 = math.hypot(c[0] - b[0], c[1] - b[1])
            if s1 > r * 1.2 or s2 > r * 1.2:
                cand.append(None); continue
            cand.append((ctr, r, (i + 1) % n))          # vertice medio de esta ventana
        # Ventanas contiguas coherentes = UNA esquina. Se recorre la lista de
        # candidatos y se agrupa cada corrida (todas las ventanas cuyo centro
        # está a la misma posición dentro de tol_ratio y radio compatible).
        # Antes se emitía un punto por VENTANA y luego un dedup por proximidad
        # los juntaba — pero puntos sobre un mismo arco están espaciados hasta
        # ~1.5 R, más que la tolerancia razonable del dedup, y salían muchos
        # duplicados por esquina (28 en un cuadrado redondeado con 4 esquinas).
        # Agrupar directamente por corridas da exactamente 1 punto por esquina.
        i = 0
        while i < n:
            if cand[i] is None:
                i += 1; continue
            j = i
            c0, r0, _v = cand[i]
            while j + 1 < 2 * n:
                nxt = cand[(j + 1) % n]
                if nxt is None:
                    break
                c1, r1, _v1 = nxt
                if abs(r1 - r0) > tol_ratio * max(r0, r1):
                    break
                if math.hypot(c1[0] - c0[0], c1[1] - c0[1]) > tol_ratio * max(r0, r1):
                    break
                j += 1
                if (j + 1) % n == i:                    # dio la vuelta entera
                    break
            length = j - i + 1
            if length >= min_run:
                w = [cand[k % n] for k in range(i, j + 1)]
                cs = [c for c, _r, _v in w]
                rs = [r for _c, r, _v in w]
                cx = sum(c[0] for c in cs) / len(cs)
                cy = sum(c[1] for c in cs) / len(cs)
                rad = sum(rs) / len(rs)
                # Vértices que forman el arco (los del medio de cada ventana);
                # su centroide indica la dirección desde el centro del círculo
                # hacia el MEDIO del arco. Al proyectar a distancia = radio,
                # se obtiene un punto exacto sobre la curva.
                vs = [p[v] for _c, _r, v in w]
                mx = sum(v[0] for v in vs) / len(vs)
                my = sum(v[1] for v in vs) / len(vs)
                dx, dy = mx - cx, my - cy
                d = math.hypot(dx, dy)
                if d >= 1e-9:
                    out.append((cx + dx / d * rad, cy + dy / d * rad, rad))
            i = j + 1
    # Parcelas vecinas comparten esquinas físicas: cada una las detecta por su
    # cuenta y salen 2–3 puntos casi coincidentes. Se colapsan a UNO por
    # cercanía (fracción pequeña del radio: la esquina de una parcela y la
    # de la vecina caen a menos de 1 ft, mientras dos esquinas distintas de
    # una misma parcela están a > R de distancia).
    ded = []
    for x, y, r in out:
        for k, (X, Y, R) in enumerate(ded):
            if math.hypot(x - X, y - Y) <= max(1.5, 0.15 * min(r, R)):
                ded[k] = ((X + x) / 2.0, (Y + y) / 2.0, (R + r) / 2.0)
                break
        else:
            ded.append((x, y, r))
    return ded


def add_reference_layers(doc, bbox, streets=True, parcels=False):
    """Agrega al modelspace de `doc` las calles (y opcional parcelas) de LA dentro
    de `bbox` (en 2229) como LWPOLYLINE en capas de referencia. Devuelve
    (n_calles, n_parcelas). Propaga excepción si falla la red."""
    msp = doc.modelspace()
    nc = npa = 0
    if streets:
        _ensure_layer(doc, "REF_LA_CALLES", 4)               # cian (calles reales)
        for pts, closed in _shapes(_fetch(LAYER_STREETS, bbox)):
            msp.add_lwpolyline([(x, y) for x, y, *_ in pts],
                               dxfattribs={"layer": "REF_LA_CALLES"}, close=closed)
            nc += 1
    if parcels:
        _ensure_layer(doc, "REF_LA_PARCELAS", 8)             # gris (parcelas reales)
        for pts, _closed in _shapes(_fetch(LAYER_PARCELS, bbox)):
            msp.add_lwpolyline([(x, y) for x, y, *_ in pts],
                               dxfattribs={"layer": "REF_LA_PARCELAS"}, close=True)
            npa += 1
    return nc, npa
