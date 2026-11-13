"""Lectura de superficies (terreno) de los archivos del cliente, PURO (2026-11-11, versión 2.1.0).

- LandXML (.xml): TIN tal cual (puntos «Norte Este Cota» + triángulos por id; caras invisibles `i="1"`
  se conservan). Un archivo puede traer varias superficies.
- GeoTIFF (.tif/.tiff): modelo de elevación en grilla (DEM). Cada píxel con dato es un punto (centro de la
  celda si el TIFF es «PixelIsArea», la esquina si es «PixelIsPoint») y cada celda con sus 4 esquinas da 2
  triángulos (con 3, uno). Así la app y Civil 3D reciben el MISMO TIN.

Unidades y sistema de coordenadas: los que dice el archivo (LandXML <Units>/<CoordinateSystem>, GeoTIFF
GeoKeys). Si no lo dice, `crs` queda vacío y quien importa decide (por defecto, el del proyecto).
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np

from traduccion.i18n_core import t

# metros por unidad
UNIDADES = {"meter": 1.0, "foot": 0.3048, "USSurveyFoot": 1200.0 / 3937.0}
_ALIAS = {"m": "meter", "meter": "meter", "metre": "meter", "kilometer": None, "millimeter": None,
          "foot": "foot", "ft": "foot", "intlfoot": "foot", "internationalfoot": "foot",
          "ussurveyfoot": "USSurveyFoot", "usfoot": "USSurveyFoot", "ftus": "USSurveyFoot", "surveyfoot": "USSurveyFoot"}
# GeoTIFF: códigos EPSG de unidad lineal
_UNIDAD_EPSG = {9001: "meter", 9002: "foot", 9003: "USSurveyFoot"}
MAX_PUNTOS = 4_000_000          # una grilla más grande se rechaza (se avisa): no cabe cómoda en la app ni en C3D


class ErrorSuperficie(Exception):
    """El archivo no se puede leer como superficie; el mensaje es para el usuario."""


@dataclass
class Superficie:
    nombre: str
    formato: str                   # "LandXML" | "GeoTIFF"
    puntos: np.ndarray             # (n, 3) float64: X (Este), Y (Norte), Z, en las unidades del archivo
    triangulos: np.ndarray         # (m, 3) int64, índices a `puntos`
    invisibles: np.ndarray = None  # (m,) bool: caras ocultas del LandXML (bordes)
    unidad: str = "meter"          # unidad de X, Y y Z (UNIDADES)
    crs: str = ""                  # «EPSG:32717» o "" si el archivo no lo dice
    avisos: list = field(default_factory=list)

    def __post_init__(self):
        if self.invisibles is None:
            self.invisibles = np.zeros(len(self.triangulos), dtype=bool)


def sha1(datos: bytes) -> str:
    return hashlib.sha1(datos).hexdigest()


def formato_de(nombre: str) -> str:
    ext = os.path.splitext(nombre)[1].lower()
    if ext == ".xml":
        return "LandXML"
    if ext in (".tif", ".tiff"):
        return "GeoTIFF"
    raise ErrorSuperficie(t("Formato no admitido: «{v0}». Usa LandXML (.xml) o GeoTIFF (.tif).").format(v0=ext or nombre))


def leer(nombre_archivo: str, datos: bytes) -> list:
    """Todas las superficies del archivo (LandXML puede traer varias; GeoTIFF, una)."""
    fmt = formato_de(nombre_archivo)
    base = os.path.splitext(os.path.basename(nombre_archivo))[0]
    if fmt == "LandXML":
        return leer_landxml(datos, base)
    return [leer_geotiff(datos, base)]


# ───────────────────────── LandXML ─────────────────────────

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _unidad(texto):
    if not texto:
        return None
    return _ALIAS.get(re.sub(r"[^a-z]", "", texto.lower()))


def leer_landxml(datos: bytes, base="Superficie") -> list:
    try:
        raiz = ET.parse(io.BytesIO(datos)).getroot()
    except ET.ParseError as e:
        raise ErrorSuperficie(t("El XML no se puede leer ({v0}).").format(v0=e))
    if _local(raiz.tag) != "LandXML":
        raise ErrorSuperficie(t("El archivo no es un LandXML."))
    unidad, crs = "meter", ""
    for el in raiz.iter():
        nom = _local(el.tag)
        if nom in ("Metric", "Imperial"):
            u = _unidad(el.get("linearUnit"))
            if u is None:
                raise ErrorSuperficie(t("Unidad lineal no admitida: «{v0}».").format(v0=el.get('linearUnit')))
            unidad = u
        elif nom == "CoordinateSystem":
            epsg = el.get("epsgCode") or ""
            if epsg.strip().isdigit():
                crs = f"EPSG:{int(epsg)}"
    salida = []
    for k, s in enumerate(e for e in raiz.iter() if _local(e.tag) == "Surface"):
        defi = next((d for d in s if _local(d.tag) == "Definition"), None)
        if defi is None:
            continue
        if (defi.get("surfType") or "TIN").upper() != "TIN":
            raise ErrorSuperficie(t("Superficie «{v0}»: tipo «{v1}» no admitido (solo TIN).").format(v0=s.get('name'), v1=defi.get('surfType')))
        ids, xyz = {}, []
        caras, invis = [], []
        for bloque in defi:
            if _local(bloque.tag) == "Pnts":
                for p in bloque:
                    v = (p.text or "").split()
                    if len(v) < 3:
                        raise ErrorSuperficie(t("Punto {v0} sin tres coordenadas.").format(v0=p.get('id')))
                    ids[p.get("id")] = len(xyz)
                    xyz.append((float(v[1]), float(v[0]), float(v[2])))       # LandXML: Norte Este Cota
            elif _local(bloque.tag) == "Faces":
                for f in bloque:
                    v = (f.text or "").split()
                    try:
                        caras.append([ids[v[0]], ids[v[1]], ids[v[2]]])
                    except (KeyError, IndexError):
                        raise ErrorSuperficie(t("Triángulo con un punto que no existe: «{v0}».").format(v0=f.text))
                    invis.append(f.get("i") == "1")
        if len(xyz) < 3 or not caras:
            raise ErrorSuperficie(t("Superficie «{v0}» sin puntos o sin triángulos.").format(v0=s.get('name')))
        salida.append(Superficie(nombre=s.get("name") or f"{base} {k + 1}", formato="LandXML",
                                 puntos=np.array(xyz, dtype=np.float64),
                                 triangulos=np.array(caras, dtype=np.int64),
                                 invisibles=np.array(invis, dtype=bool), unidad=unidad, crs=crs))
    if not salida:
        raise ErrorSuperficie(t("El LandXML no trae ninguna superficie TIN."))
    return salida


# ───────────────────────── GeoTIFF ─────────────────────────

def _geokeys(tags):
    """{clave: valor} de GeoKeyDirectoryTag (34735)."""
    d = tags.get(34735)
    if not d:
        return {}
    d = [int(x) for x in d]
    out = {}
    for i in range(4, 4 + 4 * d[3], 4):
        key, loc, _n, val = d[i:i + 4]
        if loc == 0:
            out[key] = val
    return out


def leer_geotiff(datos: bytes, base="Superficie") -> Superficie:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    try:
        im = Image.open(io.BytesIO(datos))
        im.load()
    except Exception as e:                                   # noqa: BLE001
        raise ErrorSuperficie(t("El TIFF no se puede leer ({v0}).").format(v0=e))
    tags = dict(im.tag_v2)
    escala, tie = tags.get(33550), tags.get(33922)
    if not escala or not tie or len(tie) < 6:
        raise ErrorSuperficie(t("El TIFF no está georreferenciado (le faltan ModelPixelScale / ModelTiepoint)."))
    if 34264 in tags:
        raise ErrorSuperficie(t("TIFF con ModelTransformation (girado) no admitido."))
    z = np.asarray(im, dtype=np.float64)
    if z.ndim != 2:
        raise ErrorSuperficie(t("El TIFF debe tener una sola banda de elevación."))
    filas, cols = z.shape
    if filas * cols > MAX_PUNTOS:
        raise ErrorSuperficie(t("Grilla demasiado grande ({v0} × {v1}); el máximo es {v2} celdas.").format(v0=cols, v1=filas, v2=format(MAX_PUNTOS, ',')))
    sx, sy = float(escala[0]), float(escala[1])
    i0, j0, x0, y0 = float(tie[0]), float(tie[1]), float(tie[3]), float(tie[4])
    keys = _geokeys(tags)
    centro = 0.5 if keys.get(1025, 1) == 1 else 0.0          # 1 = PixelIsArea: el dato vale en el centro
    valido = np.isfinite(z)
    nodata = tags.get(42113)
    if nodata is not None:
        try:
            valido &= z != float(str(nodata).strip("\x00 "))
        except ValueError:
            pass
    valido &= np.abs(z) < 1e30
    unidad = _UNIDAD_EPSG.get(keys.get(3076) or keys.get(2052) or 9001)
    if unidad is None:
        raise ErrorSuperficie(t("Unidad lineal del TIFF no admitida."))
    zu = _UNIDAD_EPSG.get(keys.get(4099), unidad)      # sin unidad vertical: la de X/Y
    avisos = []
    if zu != unidad:
        z = z * (UNIDADES[zu] / UNIDADES[unidad])
        avisos.append(t("Cotas convertidas de {v0} a {v1}.").format(v0=zu, v1=unidad))
    crs = f"EPSG:{keys[3072]}" if keys.get(3072) and keys[3072] not in (0, 32767) else ""
    idx = -np.ones((filas, cols), dtype=np.int64)
    idx[valido] = np.arange(int(valido.sum()))
    rr, cc = np.nonzero(valido)
    xs = x0 + (cc - i0 + centro) * sx
    ys = y0 - (rr - j0 + centro) * sy
    puntos = np.column_stack([xs, ys, z[rr, cc]])
    if len(puntos) < 3:
        raise ErrorSuperficie(t("El TIFF no tiene datos de elevación."))
    a, b = idx[:-1, :-1], idx[:-1, 1:]           # esquinas de cada celda: a b / c d
    c, d = idx[1:, :-1], idx[1:, 1:]
    tri = []
    for tr in ((a, c, b), (b, c, d)):            # dos triángulos por celda (diagonal b–c)
        m = (tr[0] >= 0) & (tr[1] >= 0) & (tr[2] >= 0)
        tri.append(np.column_stack([tr[0][m], tr[1][m], tr[2][m]]))
    llenas = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    # celdas con exactamente 3 esquinas: el triángulo que no usa la que falta (diagonal a–d)
    for tr, falta in (((a, c, d), b), ((a, b, d), c)):
        m = (tr[0] >= 0) & (tr[1] >= 0) & (tr[2] >= 0) & (falta < 0) & ~llenas
        tri.append(np.column_stack([tr[0][m], tr[1][m], tr[2][m]]))
    triangulos = np.concatenate(tri) if tri else np.zeros((0, 3), dtype=np.int64)
    if not len(triangulos):
        raise ErrorSuperficie(t("El TIFF no tiene celdas completas para formar triángulos."))
    return Superficie(nombre=base, formato="GeoTIFF", puntos=puntos, triangulos=triangulos.astype(np.int64),
                      unidad=unidad, crs=crs, avisos=avisos)
