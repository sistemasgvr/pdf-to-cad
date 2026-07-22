"""
la_reference.py — Descarga geometría real de la Ciudad de Los Ángeles (NavigateLA)
para el recuadro del plano georreferenciado y la agrega al DXF como CAPAS de
referencia, en EPSG:2229 (pies). Requiere internet.

Se pide la geometría directamente en 2229 (outSR), así entra al DXF sin reproyectar.
"""
import json
import urllib.parse
import urllib.request

_BASE = "https://maps.lacity.org/arcgis/rest/services/Mapping/NavigateLA/MapServer"
_UA = "pdf-to-cad-georef/1.0 (staff-engineering)"
LAYER_STREETS = 337     # ejes de calle (polilíneas)
LAYER_PARCELS = 395     # parcelas (polígonos)


def _fetch(layer, bbox, epsg=2229, timeout=30):
    xmin, ymin, xmax, ymax = bbox
    p = {"where": "1=1", "geometry": f"{xmin},{ymin},{xmax},{ymax}",
         "geometryType": "esriGeometryEnvelope", "inSR": str(epsg),
         "spatialRel": "esriSpatialRelIntersects", "outFields": "OBJECTID",
         "returnGeometry": "true", "outSR": str(epsg), "f": "json"}
    url = f"{_BASE}/{layer}/query?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


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


def fetch_streets_2229(cx, cy, radius=800):
    """Calles (polilíneas [(x,y),…]) de NavigateLA alrededor de (cx,cy) en 2229."""
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    return [pts for pts, _closed in _shapes(_fetch(LAYER_STREETS, bbox))]


def fetch_parcels_2229(cx, cy, radius=800):
    """Parcelas (anillos [(x,y),…]) de NavigateLA alrededor de (cx,cy) en 2229.
    Best-effort: devuelve [] si falla o hay demasiadas."""
    try:
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        return [pts for pts, _c in _shapes(_fetch(LAYER_PARCELS, bbox))]
    except Exception:
        return []


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
