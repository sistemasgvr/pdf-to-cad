"""Agregar un TAMAÑO nuevo a una familia del catálogo de Civil 3D (PURO: sin Qt).

Se escribe en TODAS las instalaciones elegidas (C3D 2025 en adelante × idioma:
esp, enu…) para que el mismo proyecto funcione en cualquiera. La familia se
identifica por lo que NO cambia con el idioma:
  - gravedad / conductos / buzones: el nombre del ARCHIVO .xml de la familia
    (`AeccCircularConcretePipe_Imperial`, `Bancoducto…`); su descripción sí se
    traduce y no se usa;
  - presión: archivo .sqlite + PART_FAMILY_NAME (idénticos en todos los idiomas;
    el PART_FAMILY_ID se repite entre familias distintas: no sirve de clave).

Tres formatos de tabla de tamaños (los que lee `civil_catalog`):
  - FILAS (<Column>/<Row>, tuberías de Autodesk): una fila nueva en TODAS las
    columnas + un UUID en <ColumnUnique>. Las columnas que no son la medida
    (grosor de pared…) se INTERPOLAN entre los tamaños vecinos (fuera del rango:
    proporcional al más cercano); el usuario las puede corregir.
  - LISTAS (<ColumnConstList>/<Item>: bancoductos, buzones): el valor se suma a
    la lista de cada eje (Civil 3D combina los ejes).
  - PRESIÓN (SQLite, `catalogo_tamanos_presion.py`): se clona el tubo más cercano de la familia (WA_PIPE_MODEL +
    sus WA_CONNECTION_POINT) y se crean los accesorios de ese diámetro que falten
    (mismo algoritmo que `PressureCatalogFiller.cs` / scripts/fill_pressure_catalog_gaps.py).

Los XML se editan como TEXTO (se inserta la línea nueva junto a la última del
bloque): no se reescribe el archivo entero, así no se pierden el BOM, la sangría
ni el `xmlns:xlink`. Antes de tocar un archivo se copia a `<archivo>.pdfcad.bak`
(una sola vez). Los IDs nuevos son deterministas (UUID v5): repetir la operación
no duplica y el mismo tamaño tiene el mismo ID en todas las instalaciones.

Tras cambiar un catálogo de gravedad se deja la marca `Pipes Catalog/
pdfcad_regenerar.txt`: el plugin la ve al importar y regenera el catálogo
(`PARTCATALOGREGEN`) antes de dibujar.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from catalogo import civil_catalog as cc
from catalogo.catalogo_tamanos_presion import _agregar_presion, _diam_dn, _dn_como, _filas_presion
from traduccion.i18n_core import N_, t

MARCA_REGEN = "pdfcad_regenerar.txt"
_NS = uuid.UUID("2b6f0c1e-7d43-4f0a-9c55-0f8d3e6a9b21")       # espacio de nombres de los UUID nuevos
TOL = 1e-4

EJES = {   # contexto → (etiqueta, orden)
    "PipeInnerDiameter": (N_("Diámetro interior"), 0),
    "PipeInnerWidth": (N_("Ancho interior"), 0),
    "PipeInnerHeight": (N_("Alto interior"), 1),
    "StructInnerDiameter": (N_("Diámetro interior"), 0),
    "StructInnerWidth": (N_("Ancho interior"), 0),
    "StructInnerLength": (N_("Largo interior"), 1),
}
PARES = (("PipeInnerWidth", "PipeInnerHeight"), ("StructInnerWidth", "StructInnerLength"))


@dataclass
class Eje:
    clave: str                 # name de la columna (XML) o nombre del campo (SQLite)
    contexto: str
    etiqueta: str              # texto del catálogo o N_(…)
    unidad: str = "in"
    valor: float = None        # propuesto (extras) o pedido (ejes)


@dataclass
class Formato:
    modo: str                  # filas | listas | presion
    ejes: list                 # las medidas que pide el usuario
    extras: list = field(default_factory=list)   # se calculan (editables)
    existentes: list = field(default_factory=list)  # tamaños actuales (texto)


@dataclass
class Resultado:
    year: int
    lang: str
    estado: str                # agregado | ya_existia | sin_familia | error
    mensaje: str = ""


def instalaciones():
    """[(año, idioma)] de C3D ≥ 2025 instalados en esta PC."""
    return [(y, lg) for y in cc.SUPPORTED_YEARS for lg in cc.installed_langs(y)]


def nombre_instalacion(year, lang):
    idioma = {"esp": N_("español"), "enu": N_("inglés")}.get(lang.lower(), lang)
    return t("Civil 3D {a} · {i}").format(a=year, i=t(idioma))


# ─────────────────────────────── localizar ───────────────────────────────


def _xml_de(kind, year, lang, fid):
    raiz = cc.pipes_root(year, lang) if kind == "pipe" else cc.catalog_root(year, lang)
    if not raiz:
        return None
    for sub in cc._list_subfolders(raiz):
        p = os.path.join(raiz, sub, fid + ".xml")
        if os.path.isfile(p):
            return p
    return None


def _sqlite_de(year, lang, fid):
    if "|" not in (fid or ""):
        return None, None
    sub, fam = fid.split("|", 1)
    raiz = cc.pressure_root(year, lang)
    p = os.path.join(raiz, sub + ".sqlite") if raiz else None
    return (p if p and os.path.isfile(p) else None), fam


def ubicar(kind, fid, year, lang):
    """Archivo de la familia en esa instalación (o None)."""
    if kind == "pressure":
        return _sqlite_de(year, lang, fid)[0]
    return _xml_de(kind, year, lang, fid)


# ─────────────────────────────── formato ────────────────────────────────


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _unidad(u):
    u = (u or "").lower()
    return "ft" if u in ("foot", "feet", "ft") else "in"


def _fmt(x):
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s or "0"


def _leer_xml(path):
    return ET.parse(path).getroot()


def formato(kind, fid, year, lang=None):
    """Cómo se agrega un tamaño a esta familia: ejes a pedir, datos calculados y
    tamaños actuales. None si la familia no tiene una tabla de tamaños que la app
    sepa ampliar."""
    if kind == "pressure":
        db, fam = _sqlite_de(year, lang or cc._current_lang, fid)
        if not db:
            return None
        filas = _filas_presion(db, fam)
        if not filas:
            return None
        return Formato("presion", [Eje("DIAMETER_NOMINAL", "", N_("Diámetro nominal"))],
                       [Eje("DIAMETER_INSIDE", "", N_("Diámetro interior")),
                        Eje("DIAMETER_OUTSIDE", "", N_("Diámetro exterior")),
                        Eje("THICKNESS", "", N_("Grosor de pared"))],
                       [r["DIAMETER_NOMINAL"] for r in filas])
    path = _xml_de(kind, year, lang, fid)
    if not path:
        return None
    root = _leer_xml(path)
    cols = [c for c in root.findall("Column")]
    por_ctx = {c.get("context"): c for c in cols}
    # 1) FILAS: tuberías de Autodesk (diámetro, o ancho × alto).
    for ctxs in (("PipeInnerDiameter",), ("PipeInnerWidth", "PipeInnerHeight")):
        if all(c in por_ctx for c in ctxs):
            ejes = [Eje(por_ctx[c].get("name"), c, por_ctx[c].get("desc") or t(EJES[c][0]),
                        _unidad(por_ctx[c].get("unit"))) for c in ctxs]
            extras = [Eje(c.get("name"), c.get("context") or "", c.get("desc") or c.get("name"),
                          _unidad(c.get("unit")))
                      for c in cols if c.get("context") not in ctxs and (c.get("dataType") or "float") == "float"]
            filas = list(zip(*[[r.text for r in por_ctx[c].findall("Row")] for c in ctxs]))
            exist = [" x ".join(_fmt(_num(v) or 0) for v in f) + " " + ejes[0].unidad for f in filas]
            return Formato("filas", ejes, extras, exist)
    # 2) LISTAS: bancoductos (ancho × alto) y buzones (diámetro o ancho × largo).
    listas = {c.get("context"): c for c in root.findall("ColumnConstList")}
    candidatos = (("PipeInnerWidth", "PipeInnerHeight"), ("PipeInnerDiameter",),
                  ("StructInnerWidth", "StructInnerLength"), ("StructInnerDiameter",))
    for ctxs in candidatos:
        if all(c in listas for c in ctxs):
            ejes = [Eje(listas[c].get("name"), c, listas[c].get("desc") or t(EJES[c][0]),
                        _unidad(listas[c].get("unit"))) for c in ctxs]
            exist = [" / ".join(_fmt(_num(i.text) or 0) for i in listas[c].findall("Item")) for c in ctxs]
            return Formato("listas", ejes, [], exist)
    return None


# ─────────────────────────── cálculo de extras ──────────────────────────


def _interpolar(puntos, x):
    """puntos = [(x, y)] → y en x: lineal entre vecinos; fuera del rango,
    proporcional al más cercano (un grosor de pared no se extrapola a negativo)."""
    pts = sorted((a, b) for a, b in puntos if a is not None and b is not None)
    if not pts:
        return None
    if all(abs(b - pts[0][1]) < TOL for _a, b in pts):
        return pts[0][1]                                  # columna constante
    if x <= pts[0][0]:
        a, b = pts[0]
        return b * (x / a) if a else b
    if x >= pts[-1][0]:
        a, b = pts[-1]
        return b * (x / a) if a else b
    for (a0, b0), (a1, b1) in zip(pts, pts[1:]):
        if a0 <= x <= a1:
            return b0 + (b1 - b0) * (x - a0) / (a1 - a0) if a1 > a0 else b0
    return pts[-1][1]


def proponer(kind, fid, year, lang, valores):
    """{clave: valor} de los datos calculados (extras) para estas medidas."""
    f = formato(kind, fid, year, lang)
    if not f or not f.extras:
        return {}
    x = float(valores[f.ejes[0].clave])
    if f.modo == "presion":
        db, fam = _sqlite_de(year, lang, fid)
        filas = _filas_presion(db, fam)
        return {e.clave: _interpolar([(_diam_dn(r["DIAMETER_NOMINAL"]), _num(r.get(e.clave))) for r in filas], x)
                for e in f.extras}
    root = _leer_xml(_xml_de(kind, year, lang, fid))
    cols = {c.get("name"): c for c in root.findall("Column")}
    base = [_num(r.text) for r in cols[f.ejes[0].clave].findall("Row")]
    salida = {}
    for e in f.extras:
        ys = [_num(r.text) for r in cols[e.clave].findall("Row")]
        # Filas que otra herramienta agregó con grosor 0 no cuentan para interpolar.
        pares = [(a, b) for a, b in zip(base, ys) if not (e.contexto == "WallThickness" and not b)]
        salida[e.clave] = _interpolar(pares or list(zip(base, ys)), x)
    return salida


# ─────────────────────────────── escribir ───────────────────────────────


def _respaldo(path):
    bak = path + ".pdfcad.bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)


def _leer_texto(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    texto = raw.decode("utf-8-sig")
    return texto, bom, ("\r\n" if "\r\n" in texto else "\n")


def _escribir_texto(path, texto, bom):
    tmp = path + ".pdfcad.tmp"
    with open(tmp, "wb") as fh:
        fh.write((b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8"))
    os.replace(tmp, path)


def _insertar(texto, tag, nombre, linea, nl):
    """Inserta `linea` como último hijo del bloque <tag … name="nombre"> (o del
    primer <tag> si nombre es None), con la sangría del hijo anterior."""
    if nombre is None:
        m = re.search(rf"<{tag}\b[^>]*>", texto)
    else:
        m = re.search(rf'<{tag}\b[^>]*\bname="{re.escape(nombre)}"[^>]*>', texto)
    if not m:
        raise ValueError(f"<{tag} name={nombre}> no encontrado")
    fin = texto.find(f"</{tag}>", m.end())
    if fin < 0:
        raise ValueError(f"</{tag}> no encontrado")
    previo = texto.rfind(nl, m.end(), fin)
    if previo >= 0:
        # sangría del último hijo y la del cierre
        ultimo = texto.rfind(nl, m.end(), previo)
        linea_prev = texto[(ultimo if ultimo >= 0 else m.end()):previo].lstrip("\r\n")
        sangria = re.match(r"\s*", linea_prev).group(0)
        return texto[:previo] + nl + sangria + linea + texto[previo:]
    return texto[:fin] + linea + texto[fin:]


def _uuid(*partes):
    return str(uuid.uuid5(_NS, "|".join(str(p) for p in partes))).upper()


def _marcar_regen(year, lang, linea):
    r = cc._lang_root(year, lang)
    if not r:
        return
    p = os.path.join(r, "Pipes Catalog", MARCA_REGEN)
    try:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(linea + "\n")
    except OSError:
        pass


def _agregar_filas(path, f, valores, extras, fid):
    root = _leer_xml(path)
    cols = {c.get("name"): c for c in root.findall("Column")}
    pedidos = [float(valores[e.clave]) for e in f.ejes]
    filas = list(zip(*[[_num(r.text) for r in cols[e.clave].findall("Row")] for e in f.ejes]))
    if any(all(abs((a or 0) - b) < TOL for a, b in zip(fila, pedidos)) for fila in filas):
        return "ya_existia"
    ids = [r.get("id", "") for c in root.iter() for r in c if r.tag in ("Row", "RowUnique")]
    n = 1 + max([int(m.group(1)) for i in ids for m in [re.match(r"r(\d+)$", i)] if m] or [-1])
    rid = f"r{n}"
    texto, bom, nl = _leer_texto(path)
    if root.find("ColumnUnique") is not None:
        texto = _insertar(texto, "ColumnUnique", None,
                          f'<RowUnique id="{rid}">{_uuid(fid, *pedidos)}</RowUnique>', nl)
    for nombre, col in cols.items():
        eje = next((i for i, e in enumerate(f.ejes) if e.clave == nombre), None)
        if eje is not None:
            v = _fmt4(pedidos[eje])
        else:
            x = extras.get(nombre)
            if x is None:                                    # columna de texto u otro dato
                ult = col.findall("Row")
                x = ult[-1].text if ult else ""
                v = x
            else:
                v = _fmt4(float(x))
        texto = _insertar(texto, "Column", nombre, f'<Row id="{rid}">{v}</Row>', nl)
    _escribir_texto(path, texto, bom)
    return "agregado"


def _fmt4(x):
    return f"{x:.4f}"


def _agregar_listas(path, f, valores):
    root = _leer_xml(path)
    texto, bom, nl = _leer_texto(path)
    cambio = False
    for e in f.ejes:
        col = next(c for c in root.findall("ColumnConstList") if c.get("name") == e.clave)
        v = float(valores[e.clave])
        items = col.findall("Item")
        if any(abs((_num(i.text) or -1) - v) < TOL for i in items):
            continue
        ids = [int(m.group(1)) for i in items for m in [re.match(r"i(\d+)$", i.get("id", ""))] if m]
        texto = _insertar(texto, "ColumnConstList", e.clave,
                          f'<Item id="i{(max(ids) + 1) if ids else len(items)}">{_fmt4(v)}</Item>', nl)
        cambio = True
    if not cambio:
        return "ya_existia"
    _escribir_texto(path, texto, bom)
    return "agregado"


def agregar(kind, fid, valores, destinos, extras=None):
    """Agrega el tamaño en cada (año, idioma) de `destinos`. `valores` = {clave
    del eje: medida}; `extras` = datos calculados ya revisados por el usuario.
    Devuelve [Resultado]."""
    out = []
    for year, lang in destinos:
        try:
            f = formato(kind, fid, year, lang)
            if f is None:
                out.append(Resultado(year, lang, "sin_familia", t("La familia no está en esta instalación.")))
                continue
            if kind == "pressure":
                db, fam = _sqlite_de(year, lang, fid)
                ex = extras or proponer(kind, fid, year, lang, valores)
                _respaldo(db)
                estado = _agregar_presion(db, fam, float(valores["DIAMETER_NOMINAL"]), ex)
            else:
                path = _xml_de(kind, year, lang, fid)
                _respaldo(path)
                if f.modo == "filas":
                    ex = extras or proponer(kind, fid, year, lang, valores)
                    estado = _agregar_filas(path, f, valores, ex, fid)
                else:
                    estado = _agregar_listas(path, f, valores)
                if estado == "agregado":
                    _marcar_regen(year, lang, f"{kind}|{fid}|" + "x".join(_fmt(float(valores[e.clave])) for e in f.ejes))
            out.append(Resultado(year, lang, estado))
        except PermissionError:
            out.append(Resultado(year, lang, "error", t("Sin permiso para escribir el catálogo: ejecuta la app como administrador.")))
        except sqlite3.OperationalError as e:
            msg = t("El catálogo está en uso: cierra Civil 3D y vuelve a intentarlo.") if "lock" in str(e).lower() else str(e)
            out.append(Resultado(year, lang, "error", msg))
        except (OSError, ValueError, KeyError, StopIteration) as e:
            out.append(Resultado(year, lang, "error", str(e) or type(e).__name__))
    return out


def texto_tamano(kind, fid, valores, year, lang=None):
    """Cómo se verá el tamaño nuevo en el desplegable de la app (para elegirlo)."""
    f = formato(kind, fid, year, lang)
    if not f:
        return ""
    vals = [float(valores[e.clave]) for e in f.ejes]
    if kind == "pressure":                             # igual que civil_catalog.pressure_pipe_sizes
        db, fam = _sqlite_de(year, lang or cc._current_lang, fid)
        filas = _filas_presion(db, fam) if db else []
        dn = _dn_como(filas[0]["DIAMETER_NOMINAL"], vals[0]) if filas else _fmt(vals[0])
        return f"{dn} in" if re.fullmatch(r"\d+(?:\.\d+)?", dn) else dn
    u = f.ejes[0].unidad
    if len(vals) == 1:
        return f"{_fmt(vals[0])} {u}"
    if kind == "pipe" and f.modo == "listas":
        return f"{_fmt(vals[0])} {u} x {_fmt(vals[1])} {u}"
    return f"{_fmt(vals[0])} x {_fmt(vals[1])} {u}"
