"""Normativas de diseño en TABLAS (PURO: sin Qt).

Formato del Excel que armó el usuario (2026-10-09; reemplaza a la plantilla «All (Flat)»
y al motor de reglas anterior). Cuatro tablas, una fila por regla y sin símbolos dentro
de las celdas:

  TIPOS               UTILIDAD | TIPO — los tipos que cada utilidad puede elegir
                      (Distribución principal, Instalación domiciliaria…). El usuario
                      suma tipos con el «+» del panel y salen al exportar el Excel.
  PRESION-DIAMETROS   UTILIDAD | TIPO | DIAMETRO (in) | SOLO SE PERMITE EN (nota)
  PRESION-ACCESORIOS  UTILIDAD | ACCESORIO | SOLO SE PERMITE EN | DIAMETRO PRINCIPAL |
                      PROHIBIDO USO | DIAMETRO RAMAL DISTRIBUCION (-1 = un tamaño menor
                      en la lista) | ANGULOS PERMITIDOS
  ELECT-TELECOM       UTILIDAD | ESTRUCTURA | TIPO | AMPERAJE (A) | LONGITUD RANGO (pies) |
                      DIAMETRO FIJO / MIN / MAX (in) | RADIO CURVA MIN (pies)

Celda vacía = sin restricción o no aplica. Listas con «;» y decimales con coma
(«1; 1,5; 2»), rangos «0-320». El catálogo es GLOBAL (vale para todos los proyectos):
`ruta()` en %APPDATA%/pdf-to-cad (o `PDFCAD_NORMAS_TABLAS` en las pruebas).
"""
from __future__ import annotations

import copy
import json
import os
import re
import unicodedata

UTILIDADES = ("AGUA", "ALCANTARILLADO", "DRENAJE", "GAS", "ELECTRICO", "TELECOM")
# Accesorio del Excel → tipo que reconoce `accesorios.py` (o el especial «T domiciliaria»).
ACCESORIOS = {"Y": "wye", "WYE": "wye", "T": "tee", "TEE": "tee", "CRUZ": "cruz", "CODO": "codo",
              "T - DOMICILIARIA": "tee_dom", "T DOMICILIARIA": "tee_dom", "T-DOMICILIARIA": "tee_dom"}

BASE = {
    "version": 1,
    "tipos": [["AGUA", "DISTRIBUCION PRINCIPAL"], ["AGUA", "ALIMENTACION Y CONDUCCION"],
              ["AGUA", "INSTALACION DOMICILIARIA"], ["ELECTRICO", "DISTRIBUCION PRINCIPAL"],
              ["ELECTRICO", "INSTALACION DOMICILIARIA"]],
    "diametros": [
        {"utilidad": "AGUA", "tipo": "DISTRIBUCION PRINCIPAL", "diametros": [6, 8, 12, 16],
         "nota": "TUBERIA DE DISTRIBUCION PRINCIPAL"},
        {"utilidad": "AGUA", "tipo": "DISTRIBUCION PRINCIPAL", "diametros": [4],
         "nota": "CALLES SIN SALIDA (cul-de-sacs), donde no necesiten hidrantes mayores a 2 pulgadas"},
        {"utilidad": "AGUA", "tipo": "ALIMENTACION Y CONDUCCION", "diametros": [16, 20, 24],
         "nota": "LINEAS DE ALIMENTACION Y CONDUCCION"},
        {"utilidad": "AGUA", "tipo": "INSTALACION DOMICILIARIA", "diametros": [1, 1.5, 2],
         "nota": "INSTALACIONES DOMICILIARIAS"},
    ],
    "accesorios": [
        {"utilidad": "AGUA", "accesorio": "Y", "solo_en": "", "diam_principal": [],
         "prohibido_en": "DISTRIBUCION PRINCIPAL", "ramal": None, "angulos": []},
        {"utilidad": "AGUA", "accesorio": "T", "solo_en": "DISTRIBUCION PRINCIPAL",
         "diam_principal": [6, 8, 12, 16], "prohibido_en": "", "ramal": -1, "angulos": []},
        {"utilidad": "AGUA", "accesorio": "Cruz", "solo_en": "DISTRIBUCION PRINCIPAL",
         "diam_principal": [6, 8], "prohibido_en": "", "ramal": None, "angulos": []},
        {"utilidad": "AGUA", "accesorio": "Codo", "solo_en": "DISTRIBUCION PRINCIPAL",
         "diam_principal": [], "prohibido_en": "", "ramal": None, "angulos": [11.25, 22.5, 45, 90]},
        {"utilidad": "AGUA", "accesorio": "T - Domiciliaria", "solo_en": "INSTALACION DOMICILIARIA",
         "diam_principal": [1, 1.5, 2], "prohibido_en": "", "ramal": None, "angulos": []},
        {"utilidad": "GAS", "accesorio": "Codo", "solo_en": "", "diam_principal": [],
         "prohibido_en": "", "ramal": None, "angulos": [45, 90]},
    ],
    "electricas": [
        {"utilidad": "ELECTRICO", "estructura": "SIMPLE", "tipo": "DISTRIBUCION PRINCIPAL", "amperaje": None,
         "longitud": None, "diam_fijo": [], "diam_min": 3, "diam_max": None, "radio_min": None},
        {"utilidad": "TELECOM", "estructura": "SIMPLE", "tipo": "", "amperaje": None,
         "longitud": None, "diam_fijo": [], "diam_min": 4, "diam_max": None, "radio_min": None},
        {"utilidad": "ELECTRICO", "estructura": "SIMPLE", "tipo": "INSTALACION DOMICILIARIA",
         "amperaje": [0, 320], "longitud": [0, 100], "diam_fijo": [3], "diam_min": None, "diam_max": None,
         "radio_min": None},
        {"utilidad": "ELECTRICO", "estructura": "SIMPLE", "tipo": "INSTALACION DOMICILIARIA",
         "amperaje": [0, 320], "longitud": [101, 200], "diam_fijo": [3], "diam_min": None, "diam_max": None,
         "radio_min": None},
        {"utilidad": "ELECTRICO", "estructura": "SIMPLE", "tipo": "INSTALACION DOMICILIARIA",
         "amperaje": [321, 400], "longitud": [0, 100], "diam_fijo": [3], "diam_min": None, "diam_max": None,
         "radio_min": None},
        {"utilidad": "ELECTRICO", "estructura": "SIMPLE", "tipo": "INSTALACION DOMICILIARIA",
         "amperaje": [321, 400], "longitud": [101, 200], "diam_fijo": [4], "diam_min": None, "diam_max": None,
         "radio_min": None},
    ],
}


# ─────────────────────────── textos y números ───────────────────────────

def clave(texto):
    """Para comparar nombres: sin tildes, en mayúsculas y con espacios simples."""
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def mismo(a, b):
    return clave(a) == clave(b)


def numero(v):
    """Número de una celda («1,5», 3, «12.5») o None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def lista_numeros(v):
    """«6; 8; 12; 16» / «1;1,5;2» / 4 → [6.0, 8.0, …]. Lo que no es número se ignora."""
    if v is None:
        return []
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return [float(v)]
    return [n for n in (numero(x) for x in str(v).split(";")) if n is not None]


def rango(v):
    """«0-320» → [0.0, 320.0]; un número solo → [n, n]; vacío → None."""
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return [float(v), float(v)]
    m = re.match(r"^\s*(-?[\d.,]+)\s*-\s*(-?[\d.,]+)\s*$", str(v))
    if m:
        lo, hi = numero(m.group(1)), numero(m.group(2))
        if lo is not None and hi is not None:
            return [min(lo, hi), max(lo, hi)]
    n = numero(v)
    return [n, n] if n is not None else None


def texto_numero(n):
    """3 → «3», 1.5 → «1,5» (como en el Excel)."""
    return f"{float(n):g}".replace(".", ",")


def texto_lista(nums):
    return "; ".join(texto_numero(n) for n in nums or [])


def texto_rango(r):
    return "" if not r else f"{texto_numero(r[0])}-{texto_numero(r[1])}"


def texto_pulgadas(n):
    return f'{float(n):g}"'


# ─────────────────────────── catálogo ───────────────────────────

def nuevo():
    return copy.deepcopy(BASE)


def ruta():
    r = os.environ.get("PDFCAD_NORMAS_TABLAS")
    if r:
        return r
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pdf-to-cad", "normativas_tablas.json")


def normalizar(cat):
    """Catálogo completo y con los tipos de las otras tablas sumados a TIPOS."""
    out = nuevo() if not isinstance(cat, dict) else copy.deepcopy(cat)
    for k in ("tipos", "diametros", "accesorios", "electricas"):
        if not isinstance(out.get(k), list):
            out[k] = []
    out["tipos"] = [[clave(u), clave(t)] for u, t in out["tipos"] if clave(u) and clave(t)]
    for fila in out["diametros"]:
        agregar_tipo(out, fila.get("utilidad"), fila.get("tipo"))
    for fila in out["electricas"]:
        agregar_tipo(out, fila.get("utilidad"), fila.get("tipo"))
    for fila in out["accesorios"]:
        for k in ("solo_en", "prohibido_en"):
            agregar_tipo(out, fila.get("utilidad"), fila.get(k))
    out["version"] = 1
    return out


def cargar(ruta_json=None):
    try:
        with open(ruta_json or ruta(), encoding="utf-8") as f:
            return normalizar(json.load(f))
    except (OSError, ValueError, TypeError, AttributeError):
        return nuevo()


def guardar(cat, ruta_json=None):
    r = ruta_json or ruta()
    os.makedirs(os.path.dirname(r) or ".", exist_ok=True)
    tmp = r + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(normalizar(cat), f, ensure_ascii=False, indent=1)
    os.replace(tmp, r)


def tipos_de(cat, utilidad):
    """Tipos que puede elegir esa utilidad, en el orden del catálogo."""
    u = clave(utilidad)
    vistos, out = set(), []
    for uu, t in (cat or {}).get("tipos", []):
        if clave(uu) == u and clave(t) not in vistos:
            vistos.add(clave(t))
            out.append(t)
    return out


def agregar_tipo(cat, utilidad, tipo):
    """Suma un tipo a la utilidad (si no estaba). Devuelve el nombre guardado o ""."""
    u, t = clave(utilidad), clave(tipo)
    if not u or not t:
        return ""
    if t not in {clave(x) for x in tipos_de(cat, u)}:
        cat.setdefault("tipos", []).append([u, t])
    return t
