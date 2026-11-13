"""Sistema de coordenadas escrito por el usuario → «EPSG:n» (2026-11-12, pedido del usuario: «tiene que ser adaptable
a todo sistema de coordenadas»; escribía `UTM84-17S`, el código de Civil 3D, y el campo solo aceptaba números).

Acepta, en este orden:
  1. número EPSG («32717», «EPSG:32717»);
  2. código CS-MAP de Civil 3D/Map 3D («UTM84-17S», «CA83-VF», «LL84»): se busca en el `NameMapper.csv` del
     diccionario de sistemas que instala Autodesk (`%ProgramData%/Autodesk/Geospatial Coordinate Systems */`, el más
     nuevo); sin él, las familias UTM y lat/long más comunes por su patrón;
  3. lo que pyproj entienda («ESRI:102100», un WKT, una cadena PROJ) si equivale a un EPSG.

PURO (sin Qt). `resolver(texto) -> (crs, error, descripcion)`.
"""
from __future__ import annotations

import csv
import glob
import os
import re
from functools import lru_cache

from traduccion.i18n_core import t

_GEO = ("Geospatial Coordinate Systems *",)
_TIPOS = {"15", "16"}                                      # 15 = geográfico, 16 = proyectado (NameMapper)


def _carpetas():
    base = os.environ.get("PDFCAD_CSMAP_DIR")
    if base:
        return [base]
    raiz = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Autodesk")
    cand = sorted(glob.glob(os.path.join(raiz, _GEO[0])), reverse=True)    # «15.02» antes que «14.07»
    return cand


def _sin_guion(cod: str) -> str:
    return cod.replace("-", "").replace("_", "")


def _tabla() -> dict:
    """{CÓDIGO CS-MAP en mayúsculas: EPSG} del NameMapper.csv más nuevo; {} si no hay."""
    return _datos()[0]


def _limpiar():
    _datos.cache_clear()


_tabla.cache_clear = _limpiar                                 # las pruebas cambian de diccionario


@lru_cache(maxsize=1)
def _datos() -> tuple:
    """(código → EPSG, EPSG → código CS-MAP tal cual lo escribe Civil 3D)."""
    for d in _carpetas():
        ruta = os.path.join(d, "NameMapper.csv")
        if not os.path.isfile(ruta):
            continue
        grupos: dict = {}
        try:
            with open(ruta, encoding="latin-1", newline="") as f:
                for r in csv.DictReader(f):
                    if r.get("NameType") in _TIPOS:
                        grupos.setdefault(r["GenericId"], []).append(r)
        except (OSError, csv.Error):
            continue
        tabla, inversa = {}, {}
        for filas in grupos.values():
            epsg = [r for r in filas if r["Flavor"] == "EPSG" and r["NumericId"].isdigit() and int(r["NumericId"])]
            if not epsg:
                continue
            epsg.sort(key=lambda r: (r["Deprecation"] != "0", r["DupSort"] != "0"))
            n = int(epsg[0]["NumericId"])
            for r in filas:
                if r["Flavor"] in ("CsMap", "Autodesk") and r["NameId"]:
                    tabla.setdefault(r["NameId"].strip().upper(), n)
                if r["Flavor"] == "CsMap" and r["NameId"] and r["DupSort"] == "0":
                    inversa.setdefault(n, r["NameId"].strip())
        if tabla:
            for k, n in list(tabla.items()):                   # «CA83VF» = «CA83-VF» (sin guiones)
                tabla.setdefault(_sin_guion(k), n)
            return tabla, inversa
    return {}, {}


_UTM = re.compile(r"^UTM(84|83|27)-(\d{1,2})([NS]?)$")
_LL = {"LL84": 4326, "LL83": 4269, "LL27": 4267, "WGS84.PSEUDOMERCATOR": 3857}


def _por_patron(cod: str):
    """EPSG de las familias CS-MAP más usadas, sin diccionario (UTM y lat/long)."""
    if cod in _LL:
        return _LL[cod]
    m = _UTM.match(cod)
    if not m:
        return None
    datum, zona, hemi = m.group(1), int(m.group(2)), m.group(3)
    if not 1 <= zona <= 60:
        return None
    if datum == "84":
        return (32700 if hemi == "S" else 32600) + zona
    if hemi == "S":
        return None
    if datum == "83" and 1 <= zona <= 23:
        return 26900 + zona
    if datum == "27" and 1 <= zona <= 22:
        return 26700 + zona
    return None


def _nombre(epsg: int) -> str:
    try:
        from pyproj import CRS
        return CRS.from_epsg(epsg).name
    except Exception:                                          # noqa: BLE001
        return ""


def _existe(epsg: int) -> bool:
    try:
        from pyproj import CRS
    except ImportError:
        return True
    try:
        CRS.from_epsg(epsg)
        return True
    except Exception:                                          # noqa: BLE001
        return False


def resolver(texto) -> tuple:
    """(«EPSG:n» o "", error, descripción legible). Vacío → ("", "", "")."""
    crudo = (texto or "").strip()
    if not crudo:
        return "", "", ""
    cod = crudo.upper()
    num = cod.removeprefix("EPSG:").strip()
    if num.isdigit():
        n = int(num)
        if not _existe(n):
            return "", t("EPSG {n} no existe.").format(n=n), ""
        return f"EPSG:{n}", "", _nombre(n)
    tabla = _tabla()
    n = tabla.get(cod) or tabla.get(_sin_guion(cod)) or _por_patron(cod)
    if n:
        return f"EPSG:{n}", "", f"{_nombre(n)} · EPSG:{n}".lstrip(" ·")
    try:
        from pyproj import CRS
        crs = CRS.from_user_input(crudo)
        n = crs.to_epsg(min_confidence=70)
        if n:
            return f"EPSG:{n}", "", f"{crs.name} · EPSG:{n}"
    except Exception:                                          # noqa: BLE001
        pass
    return "", t("No reconozco «{c}»: escribe el número EPSG (p. ej. 32717) o el código de Civil 3D "
                 "(p. ej. UTM84-17S).").format(c=crudo), ""


def codigo_civil3d(texto_o_epsg) -> str:
    """Código CS-MAP para el «Huso» del dibujo de Civil 3D: el que escribió el usuario si ya lo es, si no el del
    diccionario de Autodesk para ese EPSG (o el de la familia UTM). "" si no se sabe."""
    crudo = str(texto_o_epsg or "").strip()
    num = crudo.upper().removeprefix("EPSG:").strip()
    if crudo and not num.isdigit():
        crs, err, _d = resolver(crudo)
        if err or not crs:
            return ""
        num = crs.removeprefix("EPSG:")
        if _datos()[1].get(int(num)) is None and _por_patron(crudo.upper()):
            return crudo.upper()
    if not num.isdigit():
        return ""
    n = int(num)
    cod = _datos()[1].get(n)
    if cod:
        return cod
    if 32601 <= n <= 32660:
        return f"UTM84-{n - 32600}N"
    if 32701 <= n <= 32760:
        return f"UTM84-{n - 32700}S"
    if 26901 <= n <= 26923:
        return f"UTM83-{n - 26900}"
    return ""
