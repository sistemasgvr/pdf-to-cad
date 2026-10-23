"""Normativas de diseño: catálogo y lectura de celdas (PURO: sin Qt).

Desde 2026-10-21 el catálogo es UNA tabla de reglas (`normas_reglas`, pedido del usuario: «unificar todo en una
sola tabla… integrada con lo que la app puede validar») + la tabla TIPOS:

  {"version": 2, "tipos": [[UTILIDAD, TIPO], …], "reglas": [regla, …]}

Las de fábrica están en `normas_base` (lo que había + el Excel del ingeniero + lo medible de los Word). Antes eran
cuatro tablas (TIPOS, PRESION-DIAMETROS, PRESION-ACCESORIOS, ELECT-TELECOM): `normas_migrar` las pasa a reglas
(Excel viejo al importarlo). Un catálogo guardado viejo se reemplaza por el de fábrica (decisión del usuario: «manda
el Excel, borrar lo viejo»), conservando los tipos que el usuario agregó; el archivo viejo queda como respaldo
(`normativas_tablas.v1.json`).

Celdas: vacía = sin restricción o no aplica; listas con «;» y decimales con coma («1; 1,5; 2»); los rangos en dos
columnas MIN y MAX (en memoria [mín, máx] con None en el extremo abierto). El catálogo es GLOBAL (vale para todos
los proyectos): `ruta()` en %APPDATA%/pdf-to-cad (o `PDFCAD_NORMAS_TABLAS` en las pruebas).
"""
from __future__ import annotations

import copy
import json
import os
import functools
import re
import shutil
import unicodedata

from nucleo import model

# Las utilidades las define la APLICACIÓN (`model.TIPOS`), no el Excel (pedido del usuario 2026-10-20:
# «la aplicación manda en todo»): una fila con otra utilidad no se usa y se avisa.
UTILIDADES = tuple(codigo for _nombre, codigo in model.TIPOS)
# Accesorio del Excel VIEJO → tipo que reconoce `accesorios.py` (o el especial «T domiciliaria»).
ACCESORIOS = {"Y": "wye", "WYE": "wye", "T": "tee", "TEE": "tee", "CRUZ": "cruz", "CODO": "codo",
              "T - DOMICILIARIA": "tee_dom", "T DOMICILIARIA": "tee_dom", "T-DOMICILIARIA": "tee_dom"}
# Tipos de fábrica del formato viejo: al pasar un catálogo viejo solo se conservan los que agregó el usuario.
TIPOS_FABRICA_V1 = {("AGUA", "DISTRIBUCION PRINCIPAL"), ("AGUA", "ALIMENTACION Y CONDUCCION"),
                    ("AGUA", "INSTALACION DOMICILIARIA"), ("GAS", "SERVICIO RESIDENCIAL"),
                    ("GAS", "SERVICIO COMERCIAL/MULTIFAMILIAR"), ("GAS", "DISTRIBUCION PRINCIPAL"),
                    ("ELECTRICO", "DISTRIBUCION PRINCIPAL"), ("ELECTRICO", "DIMENSIONAMIENTO RESIDENCIAL"),
                    ("TELECOM", "DISTRIBUCION PRINCIPAL")}


# ─────────────────────────── textos y números ───────────────────────────

def clave(texto):
    """Para comparar nombres: sin tildes, en mayúsculas y con espacios simples."""
    return _clave(str(texto or ""))


@functools.lru_cache(maxsize=4096)
def _clave(texto):
    # memorizada: con miles de utilidades se pedía ~800 mil veces por redibujo (los mismos pocos textos)
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
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
    """[0, 320] → «0-320»; [400, None] → «≥ 400»; [None, 100] → «≤ 100»."""
    if not r or (r[0] is None and r[1] is None):
        return ""
    if r[1] is None:
        return f"≥ {texto_numero(r[0])}"
    if r[0] is None:
        return f"≤ {texto_numero(r[1])}"
    return f"{texto_numero(r[0])}-{texto_numero(r[1])}"


def rango_min_max(minimo, maximo):
    """Rango de las columnas MIN y MAX: [mín, máx] (None = sin ese límite) o None si las dos
    están vacías."""
    lo, hi = numero(minimo), numero(maximo)
    if lo is None and hi is None:
        return None
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return [lo, hi]


def en_rango(v, r, tol=1e-9):
    """¿v dentro del rango [mín, máx] (extremos incluidos, None = sin límite)?"""
    if r is None:
        return True
    if v is None:
        return False
    lo, hi = r
    return (lo is None or v >= lo - tol) and (hi is None or v <= hi + tol)


def texto_pulgadas(n):
    return f'{float(n):g}"'


# ─────────────────────────── catálogo ───────────────────────────

def nuevo():
    from nucleo import normas_base
    return copy.deepcopy(normas_base.base())


def ruta():
    r = os.environ.get("PDFCAD_NORMAS_TABLAS")
    if r:
        return r
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pdf-to-cad", "normativas_tablas.json")


def es_v1(cat):
    return isinstance(cat, dict) and "reglas" not in cat and any(
        k in cat for k in ("diametros", "accesorios", "electricas"))


def normalizar(cat):
    """Catálogo completo: cada regla con todas sus claves y los tipos que nombran las reglas sumados a TIPOS.
    Un catálogo de cuatro tablas (viejo) se pasa a reglas (`normas_migrar`)."""
    from nucleo import normas_migrar, normas_reglas as NR
    if es_v1(cat):
        cat = normas_migrar.de_v1(cat)
    out = nuevo() if not isinstance(cat, dict) else copy.deepcopy(cat)
    if not isinstance(out.get("tipos"), list):
        out["tipos"] = []
    if not isinstance(out.get("reglas"), list):
        out["reglas"] = []
    out["tipos"] = [[clave(u), clave(t)] for u, t in out["tipos"] if clave(u) and clave(t)]
    out["reglas"] = [NR.regla_vacia(**{k: v for k, v in r.items()}) for r in out["reglas"] if isinstance(r, dict)]
    for r in out["reglas"]:
        for u, t in NR.tipos_usados(r):
            agregar_tipo(out, u, t)
    for k in [k for k in out if k not in ("version", "tipos", "reglas")]:
        del out[k]
    out["version"] = 2
    return out


def desde_v1_guardado(viejo):
    """Catálogo viejo guardado → el de fábrica + los tipos que agregó el usuario."""
    cat = nuevo()
    for u, t in viejo.get("tipos") or []:
        if (clave(u), clave(t)) not in TIPOS_FABRICA_V1:
            agregar_tipo(cat, u, t)
    return normalizar(cat)


def cargar(ruta_json=None):
    r = ruta_json or ruta()
    try:
        with open(r, encoding="utf-8") as f:
            cat = json.load(f)
    except (OSError, ValueError, TypeError, AttributeError):
        return nuevo()
    try:
        if es_v1(cat):
            nuevo_cat = desde_v1_guardado(cat)
            try:
                respaldo = os.path.splitext(r)[0] + ".v1.json"
                if not os.path.exists(respaldo):
                    shutil.copyfile(r, respaldo)
                guardar(nuevo_cat, r)
            except OSError:
                pass
            return nuevo_cat
        return normalizar(cat)
    except (TypeError, AttributeError, KeyError, ValueError):
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
