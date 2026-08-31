"""
georef.py — Georreferenciación por puntos de control (píxel → mundo UTM).

Núcleo SIN Qt. pyproj y scikit-image se importan de forma perezosa, así la app
abre aunque no estén instalados; solo hacen falta al AJUSTAR una georreferencia o
al reproyectar lon/lat→UTM.

La transformación afín/similar mapea el píxel de la vista (mismas coordenadas que
usa el modelo: escena a `zoom`) directamente a UTM (E, N) en metros.
"""
import math


# ─────────────────────────── UTM / pyproj ───────────────────────────
def utm_epsg_from_lonlat(lon, lat):
    """EPSG UTM WGS84 a partir de lon/lat (p. ej. Lima ≈ EPSG:32718)."""
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def lonlat_to_utm(lon, lat, epsg):
    """(lon, lat) WGS84 → (E, N) en el EPSG dado. Requiere pyproj."""
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{int(epsg)}", always_xy=True)
    return tr.transform(lon, lat)


def epsg_unit(epsg):
    """Unidad lineal del CRS: 'ft' si está en pies (p. ej. State Plane 2229),
    si no 'm'. Usa pyproj si está; si no, heurística mínima."""
    try:
        from pyproj import CRS
        name = (CRS.from_epsg(int(epsg)).axis_info[0].unit_name or "").lower()
        return "ft" if ("foot" in name or "feet" in name) else "m"
    except Exception:
        return "ft" if int(epsg) == 2229 else "m"


# ─────────────────────────── Ajuste de la transformación ───────────────────────────
def _fit_numpy(src, dst, ttype):
    """Fallback sin scikit-image (mínimos cuadrados). Devuelve matriz 3x3."""
    import numpy as np
    src = np.asarray(src, float); dst = np.asarray(dst, float)
    if ttype == "affine":
        n = len(src)
        A = np.zeros((2 * n, 6)); b = np.zeros(2 * n)
        for i, (x, y) in enumerate(src):
            A[2 * i] = [x, y, 1, 0, 0, 0]; b[2 * i] = dst[i][0]
            A[2 * i + 1] = [0, 0, 0, x, y, 1]; b[2 * i + 1] = dst[i][1]
        p, *_ = np.linalg.lstsq(A, b, rcond=None); p = [float(v) for v in p]
        return [[p[0], p[1], p[2]], [p[3], p[4], p[5]], [0.0, 0.0, 1.0]]
    # similarity: E = a*x - b*y + tx ; N = b*x + a*y + ty
    n = len(src)
    A = np.zeros((2 * n, 4)); b = np.zeros(2 * n)
    for i, (x, y) in enumerate(src):
        A[2 * i] = [x, -y, 1, 0]; b[2 * i] = dst[i][0]
        A[2 * i + 1] = [y, x, 0, 1]; b[2 * i + 1] = dst[i][1]
    p, *_ = np.linalg.lstsq(A, b, rcond=None)
    a, bb, tx, ty = (float(v) for v in p)
    return [[a, -bb, tx], [bb, a, ty], [0.0, 0.0, 1.0]]


def fit(px_points, world_points, kind="affine"):
    """Ajusta píxel→mundo. kind: 'affine' (>=3 pts) o 'similarity' (2 pts).
    Devuelve (matrix3x3, rms_metros, ttype_usado). Usa scikit-image si está;
    si no, cae a un ajuste por mínimos cuadrados con numpy."""
    import numpy as np
    src = np.asarray(px_points, float); dst = np.asarray(world_points, float)
    if len(src) < 2:
        raise ValueError("Se necesitan al menos 2 puntos de control.")
    ttype = "affine" if (kind == "affine" and len(src) >= 3) else "similarity"
    try:
        from skimage.transform import estimate_transform
        tf = estimate_transform(ttype, src, dst)
        M = tf.params.tolist()
    except Exception:
        M = _fit_numpy(src, dst, ttype)
    g = Georef(matrix=M, kind=ttype)
    proj = np.array([g.to_world(x, y) for (x, y) in src])
    rms = float(np.sqrt(((proj - dst) ** 2).sum(axis=1).mean()))
    return M, rms, ttype


# ─────────────────────────── Modelo de georreferencia ───────────────────────────
class Georef:
    """Transformación píxel→mundo (matriz afín homogénea) + EPSG UTM."""

    def __init__(self, matrix=None, epsg=None, kind="affine", rms=None, points=None):
        self.matrix = matrix          # 3x3 (homogénea), mapea (x_px, y_px) → (E, N)
        self.epsg = epsg
        self.kind = kind
        self.rms = rms
        self.points = points or []    # [{"px":[x,y], "lonlat":[lon,lat], "utm":[E,N]}]

    def active(self):
        if self.matrix is None or self.epsg is None:
            return False
        m = self.matrix
        det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
        if abs(det) < 1e-6:
            return False
        ratio = max(abs(m[0][0]), abs(m[0][1]), abs(m[1][0]), abs(m[1][1]))
        minv = min(abs(m[0][0]) + abs(m[0][1]), abs(m[1][0]) + abs(m[1][1]))
        if minv < 1e-9 or ratio / minv > 100:
            return False
        return True

    def to_world(self, x, y):
        m = self.matrix
        e = m[0][0] * x + m[0][1] * y + m[0][2]
        n = m[1][0] * x + m[1][1] * y + m[1][2]
        return (e, n)

    def to_dict(self):
        if not self.active():
            return None
        return {"matrix": self.matrix, "epsg": self.epsg, "kind": self.kind,
                "rms": self.rms, "points": self.points}

    @classmethod
    def from_dict(cls, d):
        if not d:
            return cls()
        return cls(d.get("matrix"), d.get("epsg"), d.get("kind", "affine"),
                   d.get("rms"), d.get("points"))
