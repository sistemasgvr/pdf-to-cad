"""Superficies (terreno) del proyecto, PURO (2026-11-11, versión 2.1.0).

Regla: la superficie sale SIEMPRE junto a las redes. Las redes llegan al DXF en las coordenadas de la
georreferencia (`Georef.epsg`, `Main._to_cad`); la superficie se lleva a ESE mismo sistema
(`normalizar`): X/Y reproyectados si el archivo trae otro sistema (pyproj) o en la misma unidad si es el mismo,
y Z en pies como todas las cotas del proyecto. El mismo TIN (mismos puntos, mismos triángulos) es el que se
dibuja en la app y el que se escribe en LandXML para Civil 3D (`escribir_landxml`), donde el plugin lo crea
con `TinSurface.CreateFromLandXML` y lo verifica contra `MUESTRAS` y las cifras del XDATA.

Cada superficie del proyecto es un dict (`registro`), sin la geometría: nombre, formato, archivo de origen,
sha1 del archivo (sus bytes viajan aparte, en el .digproj), índice dentro del archivo, CRS de origen y cifras.
"""
from __future__ import annotations

import numpy as np

from traduccion.i18n_core import t

from nucleo.superficies_leer import UNIDADES, Superficie, sha1  # noqa: F401  (sha1 lo usa la ventana)

CAPA = "PDFCAD_SUPERFICIES"
UNIDAD_PIES = "foot"
UNIDAD_PIES_US = "USSurveyFoot"


class ErrorSistema(Exception):
    """No se puede llevar la superficie al sistema de coordenadas del proyecto."""


def registro(sup: Superficie, archivo: str, sha: str, indice: int, crs_origen: str) -> dict:
    """Lo que se guarda en el proyecto (la geometría se vuelve a leer del archivo)."""
    return {"nombre": sup.nombre, "formato": sup.formato, "archivo": archivo, "sha1": sha, "indice": int(indice),
            "crs": crs_origen or "", "unidad": sup.unidad, "n_puntos": int(len(sup.puntos)),
            "n_triangulos": int(len(sup.triangulos)), "visible": True}


def nombre_libre(nombre: str, usados) -> str:
    usados = set(usados)
    if nombre not in usados:
        return nombre
    k = 2
    while f"{nombre} ({k})" in usados:
        k += 1
    return f"{nombre} ({k})"


# ───────────────────────── sistema y unidades ─────────────────────────

def unidad_de_epsg(epsg) -> str:
    """Unidad lineal del CRS (UNIDADES) o "" si no se puede saber."""
    if not epsg:
        return ""
    try:
        from pyproj import CRS
        nombre = (CRS.from_user_input(epsg).axis_info[0].unit_name or "").lower()
    except Exception:                                          # noqa: BLE001
        return UNIDAD_PIES_US if str(epsg).endswith("2229") else ""
    if "us survey" in nombre:
        return UNIDAD_PIES_US
    if "foot" in nombre or "feet" in nombre:
        return UNIDAD_PIES
    if "met" in nombre:
        return "meter"
    return ""


def destino(epsg_proyecto) -> tuple:
    """(crs, unidad X/Y, unidad Z) del dibujo: el de la georreferencia; cotas siempre en pies (US si el CRS lo es)."""
    crs = f"EPSG:{int(epsg_proyecto)}" if epsg_proyecto else ""
    uxy = unidad_de_epsg(crs) if crs else ""
    uz = UNIDAD_PIES_US if uxy == UNIDAD_PIES_US else UNIDAD_PIES
    return crs, uxy, uz


def normalizar(sup: Superficie, crs_origen: str, crs_destino: str, unidad_xy_destino: str,
               unidad_z_destino: str = UNIDAD_PIES) -> np.ndarray:
    """Puntos (n, 3) en el sistema del dibujo. Sin reproyectar (mismo CRS o alguno desconocido) X/Y solo cambian
    de unidad si el destino tiene otra; sin unidad de destino conocida, quedan tal cual. Z → `unidad_z_destino`."""
    p = np.array(sup.puntos, dtype=np.float64, copy=True)
    if crs_origen and crs_destino and crs_origen != crs_destino:
        try:
            from pyproj import Transformer
        except ImportError:
            raise ErrorSistema(t("Para reproyectar hace falta pyproj (no está instalado)."))
        try:
            tr = Transformer.from_crs(crs_origen, crs_destino, always_xy=True)
        except Exception as e:                                  # noqa: BLE001
            raise ErrorSistema(t("No se puede pasar de {v0} a {v1} ({v2}).").format(v0=crs_origen, v1=crs_destino, v2=e))
        p[:, 0], p[:, 1] = tr.transform(p[:, 0], p[:, 1])
    elif unidad_xy_destino and unidad_xy_destino != sup.unidad:
        f = UNIDADES[sup.unidad] / UNIDADES[unidad_xy_destino]
        p[:, 0] *= f
        p[:, 1] *= f
    if unidad_z_destino != sup.unidad:
        p[:, 2] *= UNIDADES[sup.unidad] / UNIDADES[unidad_z_destino]
    if not np.all(np.isfinite(p)):
        raise ErrorSistema(t("La reproyección dio puntos inválidos (¿el sistema elegido es el del archivo?)."))
    return p


# ───────────────────────── plano sobre la superficie ─────────────────────────

def matriz_sobre_superficie(cad_de_px, ancho_px, alto_px, centro, unidad_mundo) -> list:
    """Georreferencia del plano (2026-11-12, opción «Ubicar el plano en el sistema de la superficie»): px → mundo
    = la escala de la hoja (`cad_de_px`: px → pies, la del cajetín, con su giro) llevada a la unidad del sistema y
    trasladada para que el CENTRO de la hoja caiga en `centro` (centro de la superficie). Sin giro: el norte del
    sistema = el de la hoja. Devuelve la matriz 3×3 (listas) exacta de esa afín."""
    k = 0.3048 / UNIDADES[unidad_mundo] if unidad_mundo else 1.0         # pies → unidad del sistema
    px = np.array([[0.0, 0.0], [ancho_px, 0.0], [0.0, alto_px]])
    cad = np.array([cad_de_px(x, y) for x, y in px], dtype=np.float64) * k
    cx, cy = (np.array(cad_de_px(ancho_px / 2.0, alto_px / 2.0), dtype=np.float64) * k)
    mundo = cad + (np.asarray(centro[:2], dtype=np.float64) - (cx, cy))
    a = np.column_stack([px, np.ones(3)])
    sol = np.linalg.solve(a, mundo)                                      # 3×2: columnas E y N
    return [[float(sol[0, 0]), float(sol[1, 0]), float(sol[2, 0])],
            [float(sol[0, 1]), float(sol[1, 1]), float(sol[2, 1])],
            [0.0, 0.0, 1.0]]


# ───────────────────────── geometría ─────────────────────────

def recuadro(puntos) -> tuple:
    return (float(puntos[:, 0].min()), float(puntos[:, 1].min()), float(puntos[:, 0].max()), float(puntos[:, 1].max()))


def contorno(triangulos, invisibles=None) -> list:
    """Bordes del TIN (aristas de un solo triángulo visible) encadenados: lista de listas de índices de punto."""
    tri = np.asarray(triangulos)
    if invisibles is not None and len(invisibles):
        tri = tri[~np.asarray(invisibles, dtype=bool)]
    if not len(tri):
        return []
    aristas = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    orden = np.sort(aristas, axis=1)
    _u, inv, cuenta = np.unique(orden, axis=0, return_inverse=True, return_counts=True)
    borde = aristas[cuenta[inv.ravel()] == 1]
    sig = {}
    for a, b in borde.tolist():
        sig.setdefault(a, []).append(b)
    lazos = []
    while sig:
        ini = next(iter(sig))
        lazo, actual = [ini], ini
        while True:
            nxt = sig.get(actual)
            if not nxt:
                break
            b = nxt.pop()
            if not nxt:
                del sig[actual]
            if b == ini:
                lazo.append(ini)
                break
            lazo.append(b)
            actual = b
        if len(lazo) >= 3:
            lazos.append(lazo)
    return lazos


def muestras(puntos, triangulos, n=10) -> list:
    """Hasta n puntos de control (x, y, z): vértices y centroides de triángulos repartidos por el TIN; con ellos el
    plugin comprueba en Civil 3D que la cota en ese lugar es la misma."""
    pts = np.asarray(puntos)
    tri = np.asarray(triangulos)
    out = []
    mitad = max(1, n // 2)
    for k in np.linspace(0, len(pts) - 1, num=min(mitad, len(pts)), dtype=int):
        out.append(tuple(float(v) for v in pts[k]))
    for k in np.linspace(0, len(tri) - 1, num=min(n - len(out), len(tri)), dtype=int):
        c = pts[tri[k]].mean(axis=0)
        out.append((float(c[0]), float(c[1]), float(c[2])))
    return out[:n]


def cota_en(puntos, triangulos, x, y):
    """Cota del TIN en (x, y) o None fuera de él (interpolación lineal en el triángulo que lo contiene)."""
    pts = np.asarray(puntos)
    t = pts[np.asarray(triangulos)]
    x0, y0 = t[:, 0, 0], t[:, 0, 1]
    d1x, d1y = t[:, 1, 0] - x0, t[:, 1, 1] - y0
    d2x, d2y = t[:, 2, 0] - x0, t[:, 2, 1] - y0
    det = d1x * d2y - d2x * d1y
    with np.errstate(divide="ignore", invalid="ignore"):
        u = ((x - x0) * d2y - d2x * (y - y0)) / det
        v = (d1x * (y - y0) - (x - x0) * d1y) / det
    dentro = np.nonzero((u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (det != 0))[0]
    if not len(dentro):
        return None
    k = dentro[0]
    z = t[k, :, 2]
    return float(z[0] + u[k] * (z[1] - z[0]) + v[k] * (z[2] - z[0]))


# ───────────────────────── LandXML para Civil 3D ─────────────────────────

def _num(v) -> str:
    """Número con TODA su precisión (repr de float: vuelve exacto al leerlo)."""
    s = repr(float(v))
    return "0.0" if s == "-0.0" else s


def _esc(t) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def escribir_landxml(nombre, puntos, triangulos, unidad, invisibles=None, fecha="", hora="") -> bytes:
    """LandXML 1.2 de UNA superficie TIN con los puntos y triángulos tal cual (P = «Norte Este Cota»). Sin
    <CoordinateSystem>: los números ya están en el sistema del dibujo (Civil 3D no debe transformarlos)."""
    pts = np.asarray(puntos, dtype=np.float64)
    tri = np.asarray(triangulos)
    inv = np.zeros(len(tri), dtype=bool) if invisibles is None else np.asarray(invisibles, dtype=bool)
    if unidad == "meter":
        units = ('<Metric areaUnit="squareMeter" linearUnit="meter" volumeUnit="cubicMeter" '
                 'temperatureUnit="celsius" pressureUnit="milliBars" diameterUnit="millimeter" '
                 'angularUnit="decimal degrees" directionUnit="decimal degrees"/>')
    else:
        units = (f'<Imperial areaUnit="squareFoot" linearUnit="{unidad}" volumeUnit="cubicYard" '
                 'temperatureUnit="fahrenheit" pressureUnit="inchHG" diameterUnit="inch" '
                 'angularUnit="decimal degrees" directionUnit="decimal degrees"/>')
    zmin, zmax = (float(pts[:, 2].min()), float(pts[:, 2].max())) if len(pts) else (0.0, 0.0)
    partes = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.2" version="1.2" '
              f'date="{_esc(fecha)}" time="{_esc(hora)}">',
              f"<Units>{units}</Units>",
              '<Application name="Asistente C3D" manufacturer="GVR"/>',
              "<Surfaces>", f'<Surface name="{_esc(nombre)}">',
              f'<Definition surfType="TIN" elevMin="{_num(zmin)}" elevMax="{_num(zmax)}">', "<Pnts>"]
    partes += [f'<P id="{k + 1}">{_num(p[1])} {_num(p[0])} {_num(p[2])}</P>' for k, p in enumerate(pts)]
    partes.append("</Pnts><Faces>")
    partes += [f'<F{" i=" + chr(34) + "1" + chr(34) if inv[k] else ""}>{a + 1} {b + 1} {c + 1}</F>'
               for k, (a, b, c) in enumerate(tri.tolist())]
    partes += ["</Faces>", "</Definition>", "</Surface>", "</Surfaces>", "</LandXML>"]
    return ("\n".join(partes) + "\n").encode("utf-8")


def xdata(reg: dict, puntos, triangulos, archivo_rel: str, archivo_abs: str, sha_archivo: str, unidad: str) -> list:
    """Items (1000, «CLAVE=valor») del punto PDFCAD_SUPERFICIE (contrato con `ImportarRedSuperficies.cs`)."""
    x0, y0, x1, y1 = recuadro(puntos)
    # cada texto de XDATA admite 255 caracteres: una muestra por item (MUESTRA_1…), rutas largas se omiten
    items = ["PDFCAD_SUPERFICIE", f"NAME={reg['nombre'][:200]}", f"ARCHIVO={archivo_rel[:240]}",
             *([f"ARCHIVO_ABS={archivo_abs}"] if len(archivo_abs) <= 240 else []),
             f"SHA1={sha_archivo}", f"N_PUNTOS={len(puntos)}", f"N_TRIANGULOS={len(triangulos)}",
             f"ZMIN={_num(puntos[:, 2].min())}", f"ZMAX={_num(puntos[:, 2].max())}",
             f"XMIN={_num(x0)}", f"YMIN={_num(y0)}", f"XMAX={_num(x1)}", f"YMAX={_num(y1)}",
             f"UNIDAD={unidad}", f"FUENTE={reg.get('archivo', '')[:200]}", f"CRS={reg.get('crs', '')}"]
    items += [f"MUESTRA_{k}=" + ",".join(_num(v) for v in m) for k, m in enumerate(muestras(puntos, triangulos), 1)]
    return [(1000, s) for s in items]


def nombre_archivo(nombre: str) -> str:
    """Nombre de archivo seguro para la superficie."""
    limpio = "".join(c if c.isalnum() or c in " -_()." else "_" for c in nombre).strip() or "superficie"
    return limpio[:80] + ".xml"


def area_xy(puntos, triangulos) -> float:
    t = np.asarray(puntos)[np.asarray(triangulos)]
    return float(np.abs(np.cross(t[:, 1, :2] - t[:, 0, :2], t[:, 2, :2] - t[:, 0, :2])).sum() / 2.0)

