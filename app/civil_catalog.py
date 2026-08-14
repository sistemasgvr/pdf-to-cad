r"""
civil_catalog.py — Detección de instalaciones de Civil 3D y listado de familias
del catálogo imperial:

- Structures (buzones de gravedad): ...\Pipes Catalog\US Imperial Structures\**\*.xml
  Cada .xml lleva al lado un .bmp con la miniatura de la familia.
- Pressure appurtenances (nodos de presión): ...\Pressure Pipes Catalog\Imperial\*.sqlite
  Cada sub-catálogo (por material) es un .sqlite. Las familias se agrupan por
  PART_FAMILY_NAME; la miniatura vive en <subcat>/IMG/<PART_FAMILY_ID>.png.

Uso típico:
    versions = installed_versions()                # ['2025', '2027']
    fams = imperial_structures(2025)               # gravedad → [Family, ...]
    pfams = pressure_families(2025)                # presión → [Family, ...]

Cada Family devuelto es un dict con:
    id        — identificador único (basename del .xml o PART_FAMILY_ID GUID)
    pretty    — nombre humano corto
    subfolder — nombre del subcatálogo/subcarpeta
    img_path  — ruta absoluta al .bmp/.png para miniatura (None si no existe)
    kind      — "structure" o "appurtenance"
"""
import os
import re
import sqlite3
import xml.etree.ElementTree as ET

SUPPORTED_YEARS = (2024, 2025, 2026, 2027)
LANG_PREFERENCES = ("esp", "enu", "fra", "deu", "ita", "ptb")

# Idioma activo del catálogo — la UI Python lo setea con set_current_lang() al
# elegir una versión/idioma. Las funciones catalog_root / pipes_root / pressure_root
# lo respetan cuando se llaman sin arg `lang` explícito.
_current_lang = None


def set_current_lang(lang):
    """Fija el idioma activo del catálogo Civil 3D. Todas las funciones que
    resuelven carpetas (catalog_root, pipes_root, etc.) lo usan como default."""
    global _current_lang
    _current_lang = lang

# Subcarpetas dentro de "US Imperial Structures"
STRUCTURE_SUBFOLDERS = (
    "BuzonesElectricas",
    "Junction Structures with Frames",
    "Junction Structures without Frames",
    "Inlet-Outlets",
    "Simple Shapes",
)

# Subcarpetas dentro de "US Imperial Pipes" que contienen los .xml de tubería.
PIPE_SUBFOLDERS = (
    "Circular Pipes",
    "Egg-Shaped Pipes",
    "Elliptical Pipes",
    "Rectangular Pipes",
    "Bancoductos",
    "Bancos Tubos",
)

# Tablas relevantes dentro de cada .sqlite del catálogo de presión.
PRESSURE_TABLES = (
    "WA_APPURTENANCE_MODEL",
    "WA_VALVE_MODEL",
    "WA_FITTING_MODEL",
    "WA_ELBOW_MODEL",
    "WA_HYDRANT_MODEL",
    "WA_BRANCH_FITTING_MODEL",
)


def _programdata_root():
    return os.environ.get("ProgramData", r"C:\ProgramData")


def installed_langs(year):
    """Lista los códigos de idioma instalados para un año (esp/enu/etc).
    Devuelve [] si el año no está instalado."""
    base = os.path.join(_programdata_root(), "Autodesk", f"C3D {year}")
    if not os.path.isdir(base): return []
    out = []
    try:
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if os.path.isdir(p) and d.lower() in LANG_PREFERENCES:
                out.append(d)
    except OSError:
        pass
    return out


def _lang_root(year, lang=None):
    """Devuelve la carpeta <lang> dentro de C3D <year>.
    Prioridad para elegir idioma:
      1. arg `lang` explícito
      2. `_current_lang` fijado por la UI (via set_current_lang())
      3. primera de LANG_PREFERENCES que exista en disco (comportamiento legacy)
    """
    base = os.path.join(_programdata_root(), "Autodesk", f"C3D {year}")
    if not os.path.isdir(base): return None
    eff = lang or _current_lang
    if eff:
        p = os.path.join(base, eff)
        return p if os.path.isdir(p) else None
    for lg in LANG_PREFERENCES:
        p = os.path.join(base, lg)
        if os.path.isdir(p): return p
    return None


def _find_catalog_subdir(parent, expected_prefix):
    """Busca dentro de `parent` una carpeta cuyo nombre coincida (case-insensitive)
    con `expected_prefix` o empiece con ese prefijo (para tolerar sufijos que a
    veces Civil 3D pone según idioma o renombraciones manuales, p.ej.
    'US Imperial Pipes_ING'). Devuelve el path o None."""
    if not parent or not os.path.isdir(parent): return None
    exact = os.path.join(parent, expected_prefix)
    if os.path.isdir(exact): return exact
    ep_low = expected_prefix.lower()
    for entry in sorted(os.listdir(parent)):
        p = os.path.join(parent, entry)
        if not os.path.isdir(p): continue
        el = entry.lower()
        if el == ep_low or el.startswith(ep_low):
            return p
    return None


def catalog_root(year, lang=None):
    """Carpeta 'US Imperial Structures' (o variantes con sufijo) de la versión
    y idioma indicados, o None."""
    r = _lang_root(year, lang)
    if r is None: return None
    return _find_catalog_subdir(os.path.join(r, "Pipes Catalog"),
                                 "US Imperial Structures")


def pipes_root(year, lang=None):
    """Carpeta 'US Imperial Pipes' (o variantes con sufijo) de la versión
    y idioma indicados, o None."""
    r = _lang_root(year, lang)
    if r is None: return None
    return _find_catalog_subdir(os.path.join(r, "Pipes Catalog"),
                                 "US Imperial Pipes")


def pressure_root(year, lang=None):
    """Carpeta 'Pressure Pipes Catalog\\Imperial' (o variantes con sufijo) de
    la versión e idioma indicados, o None."""
    r = _lang_root(year, lang)
    if r is None: return None
    return _find_catalog_subdir(os.path.join(r, "Pressure Pipes Catalog"),
                                 "Imperial")


def installed_versions():
    """Años con al menos catálogo de estructuras imperial instalado."""
    return [y for y in SUPPORTED_YEARS if catalog_root(y) is not None]


def _pretty_from_filename(fname):
    base = os.path.splitext(fname)[0]
    for prefix in ("AeccStruct", "Aecc"):
        if base.startswith(prefix):
            base = base[len(prefix):]; break
    if base.endswith("_Imperial"):
        base = base[:-len("_Imperial")]
    base = re.sub(r"(?<!^)(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", base)
    return base.strip()


def structure_family_xml(year, fid):
    """Ruta absoluta al .xml de la familia de gravedad (o None)."""
    root = catalog_root(year)
    if root is None: return None
    for sub in STRUCTURE_SUBFOLDERS:
        p = os.path.join(root, sub, fid + ".xml")
        if os.path.isfile(p): return p
    return None


def structure_family_params(year, fid):
    """Lee los <ColumnConstList> del XML de una familia y devuelve una lista de
    dicts describiendo cada parámetro. Cada dict trae:
      name       — 'SID', 'SCH', 'WTh'…
      desc       — label humano en el idioma del catálogo (atributo desc)
      context    — 'StructInnerDiameter', 'StructConeHeight'…
      unit       — 'inch', 'foot', ...
      data_type  — 'float', 'int', 'string'
      items      — lista de valores actualmente permitidos (strings)
    Vacía si el XML no existe o no tiene ColumnConstList."""
    path = structure_family_xml(year, fid)
    if path is None: return []
    try:
        tree = ET.parse(path); root_el = tree.getroot()
    except ET.ParseError:
        return []
    out = []
    for col in root_el.findall("ColumnConstList"):
        items = [it.text for it in col.findall("Item") if it.text is not None]
        out.append({
            "name": col.get("name", ""),
            "desc": col.get("desc", col.get("context", "")),
            "context": col.get("context", ""),
            "unit": col.get("unit", ""),
            "data_type": col.get("dataType", "float"),
            "items": items,
        })
    return out


def _add_size_to_xml(path, values):
    """Núcleo compartido: agrega nuevos <Item> a los <ColumnConstList> del XML en
    `path`, con backup .xml.bak. Ver add_structure_size / add_pipe_size."""
    if path is None: return {"ok": False, "error": "XML no encontrado"}
    if not os.access(path, os.W_OK):
        return {"ok": False, "error": f"Sin permiso de escritura en {path}. "
                                       "Ejecuta la app como administrador y reintenta."}
    # Backup una sola vez.
    bak = path + ".bak"
    if not os.path.exists(bak):
        try:
            import shutil; shutil.copy2(path, bak)
        except OSError as e:
            return {"ok": False, "error": f"No se pudo hacer backup: {e}"}
    try:
        tree = ET.parse(path); root_el = tree.getroot()
    except ET.ParseError as e:
        return {"ok": False, "error": f"XML corrupto: {e}"}

    added, skipped = {}, {}
    # Formato normalizado del valor: usar el mismo estilo con 4 decimales que ya
    # usan los Items del catálogo, así el XML queda uniforme.
    def _fmt(v):
        v = str(v).strip()
        if not v: return None
        try: return f"{float(v):.4f}"
        except ValueError: return None

    for col in root_el.findall("ColumnConstList"):
        name = col.get("name", "")
        if name not in values: continue
        raw = values[name]
        norm = _fmt(raw)
        if norm is None: skipped[name] = "valor inválido"; continue
        # Ya existe?
        existing = {(it.text or "").strip() for it in col.findall("Item")}
        # Comparar por número, no por string (evita "48.0" vs "48.0000").
        exists = False
        try:
            n = float(norm)
            for ex in existing:
                try:
                    if abs(float(ex) - n) < 1e-6: exists = True; break
                except ValueError: continue
        except ValueError:
            exists = norm in existing
        if exists: skipped[name] = "ya existía"; continue
        # Insertar. El siguiente id de Item = i<n_existentes>.
        n_items = len(col.findall("Item"))
        new_it = ET.SubElement(col, "Item")
        new_it.set("id", f"i{n_items}")
        new_it.text = norm
        added[name] = norm

    if not added:
        return {"ok": True, "added": {}, "skipped": skipped}

    try:
        # Preservar declaración XML y encoding original ("utf-8" con BOM en algunos).
        tree.write(path, encoding="utf-8", xml_declaration=True)
    except OSError as e:
        return {"ok": False, "error": f"No se pudo guardar: {e}"}
    return {"ok": True, "added": added, "skipped": skipped}


def add_structure_size(year, fid, values):
    """Agrega nuevos valores al XML de una familia de ESTRUCTURA (buzón)."""
    return _add_size_to_xml(structure_family_xml(year, fid), values)


def add_pipe_size(year, fid, values):
    """Agrega nuevos valores al XML de una familia de TUBERÍA (incluye Bancoductos
    y Bancos Tubos, que usan el mismo formato <ColumnConstList>/<Item>)."""
    return _add_size_to_xml(pipe_family_xml(year, fid), values)


def pipe_family_params(year, fid):
    """Igual que structure_family_params pero para el XML de una TUBERÍA. Devuelve
    los <ColumnConstList> (Bancoductos/Bancos Tubos los usan). Si la familia usa
    <Column>/<Row> paramétrica devuelve lista vacía (no soportado por este editor)."""
    path = pipe_family_xml(year, fid)
    if path is None: return []
    try:
        tree = ET.parse(path); root_el = tree.getroot()
    except ET.ParseError:
        return []
    out = []
    for col in root_el.findall("ColumnConstList"):
        items = [it.text for it in col.findall("Item") if it.text is not None]
        out.append({
            "name": col.get("name", ""),
            "desc": col.get("desc", col.get("context", "")),
            "context": col.get("context", ""),
            "unit": col.get("unit", ""),
            "data_type": col.get("dataType", "float"),
            "items": items,
        })
    return out


def family_params(year, fid, kind):
    """Wrapper que despacha a structure_family_params o pipe_family_params."""
    return (pipe_family_params(year, fid) if kind == "pipe"
            else structure_family_params(year, fid))


def add_family_size(year, fid, values, kind):
    """Wrapper que despacha a add_structure_size o add_pipe_size."""
    return (add_pipe_size(year, fid, values) if kind == "pipe"
            else add_structure_size(year, fid, values))


def family_description(year, fid, kind):
    """Lee el campo PrtD (Catalog_PartDesc) del XML de la familia — es la
    'Description' que ve Civil 3D. Se usa para exportar al DXF, porque el
    matcher del addin compara por Description real, no por basename del .xml.
    Fallback: devuelve el fid si no encuentra PrtD."""
    path = pipe_family_xml(year, fid) if kind == "pipe" else structure_family_xml(year, fid)
    if path is None: return fid
    try:
        tree = ET.parse(path); root_el = tree.getroot()
    except ET.ParseError:
        return fid
    for cc in root_el.findall("ColumnConst"):
        if cc.get("context") == "Catalog_PartDesc" and cc.text:
            return cc.text.strip()
    return fid


def structure_sizes(year, fid):
    """Devuelve la lista de tamaños de una familia de estructura de gravedad, como
    strings tipo "48 in", "60 in". Se toma el ColumnConstList con context que
    represente el diámetro interior (SID) o, en su defecto, el primer parámetro
    con unit definida. Lista vacía si no encuentra nada."""
    root = catalog_root(year)
    if root is None: return []
    xml_path = None
    for sub in STRUCTURE_SUBFOLDERS:
        p = os.path.join(root, sub, fid + ".xml")
        if os.path.isfile(p): xml_path = p; break
    if xml_path is None: return []
    try:
        tree = ET.parse(xml_path); root_el = tree.getroot()
    except ET.ParseError:
        return []
    # Prioridad: StructInnerDiameter, luego cualquier ColumnConstList con Items.
    preferred_contexts = ("StructInnerDiameter", "StructOuterDiameter",
                          "StructFrameLength", "StructWidth")
    def _fmt(v, unit):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return str(v)
        u = (unit or "").lower()
        u = "in" if u in ("inch", "in", "\"") else ("ft" if u in ("foot", "feet", "ft", "'") else u)
        # Sin decimales innecesarios.
        s = f"{x:.4f}".rstrip("0").rstrip(".")
        return f"{s} {u}" if u else s
    def _extract(col):
        unit = col.get("unit", "")
        vals = [it.text for it in col.findall("Item") if it.text]
        seen, out = set(), []
        for v in vals:
            s = _fmt(v, unit)
            if s in seen: continue
            seen.add(s); out.append(s)
        return out
    # Estructuras RECTANGULARES (buzones tipo Box): tienen StructInnerWidth +
    # StructInnerLength en el XML. Civil 3D muestra las dimensiones EXTERIORES
    # en el Part Size Name (fórmula típica: outer = inner + 2*WallThickness).
    # Devolvemos el producto cartesiano usando outer, para que coincida con la UI.
    by_ctx = {}
    for col in root_el.findall("ColumnConstList"):
        ctx = col.get("context", "")
        if ctx in ("StructInnerWidth", "StructInnerLength"):
            vals = [it.text for it in col.findall("Item") if it.text]
            if vals: by_ctx[ctx] = (col.get("unit", ""), vals)
    # WallThickness suele venir como ColumnConst (valor único).
    wall_th = 0.0
    for cc in root_el.findall("ColumnConst"):
        if cc.get("context") == "WallThickness":
            try: wall_th = float(cc.text or "0")
            except (TypeError, ValueError): wall_th = 0.0
            break
    if "StructInnerWidth" in by_ctx and "StructInnerLength" in by_ctx:
        uw, ws = by_ctx["StructInnerWidth"]
        ul, ls = by_ctx["StructInnerLength"]
        u = uw or ul
        norm_u = "in" if (u or "").lower() in ("inch", "in", "\"") else \
                 ("ft" if (u or "").lower() in ("foot", "feet", "ft", "'") else (u or ""))
        def _outer(v):
            try: return float(v) + 2.0 * wall_th
            except (TypeError, ValueError): return None
        def _n(x):
            if x is None: return "?"
            return f"{x:.4f}".rstrip("0").rstrip(".")
        out, seen = [], set()
        for w in ws:
            for l in ls:
                s = f"{_n(_outer(w))} x {_n(_outer(l))}" + (f" {norm_u}" if norm_u else "")
                if s in seen: continue
                seen.add(s); out.append(s)
        return out

    for ctx in preferred_contexts:
        for col in root_el.findall("ColumnConstList"):
            if col.get("context") == ctx:
                sizes = _extract(col)
                if sizes: return sizes
    for col in root_el.findall("ColumnConstList"):
        sizes = _extract(col)
        if sizes: return sizes
    return []


def pressure_sizes(year, fid):
    """Devuelve los DIAMETER_NOMINAL únicos de una familia de accesorio de presión.
    fid = '<subcat>|<PART_FAMILY_NAME>'. Lista vacía si no encuentra nada."""
    if "|" not in (fid or ""): return []
    subcat, fam_name = fid.split("|", 1)
    root = pressure_root(year)
    if root is None: return []
    db_path = os.path.join(root, subcat + ".sqlite")
    if not os.path.isfile(db_path): return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return []
    raw = []
    try:
        c = conn.cursor()
        for tbl in PRESSURE_TABLES:
            try:
                c.execute(
                    f"SELECT DISTINCT DIAMETER_NOMINAL FROM {tbl} "
                    f"WHERE PART_FAMILY_NAME=? AND DIAMETER_NOMINAL IS NOT NULL",
                    (fam_name,)
                )
            except sqlite3.Error:
                continue
            for (dn,) in c.fetchall():
                if dn and dn not in raw: raw.append(dn)
    finally:
        conn.close()
    # DIAMETER_NOMINAL puede ser "8", "10", "10 x 5". Ordenar numéricamente por el
    # primer número y agregar " in" si el string es solo dígitos/decimales.
    def _key(s):
        m = re.match(r"\s*(\d+(?:\.\d+)?)", str(s))
        return float(m.group(1)) if m else 1e9
    raw.sort(key=_key)
    def _pretty(s):
        s = str(s).strip()
        return f"{s} in" if re.fullmatch(r"\d+(?:\.\d+)?", s) else s
    return [_pretty(s) for s in raw]


def imperial_pipes(year):
    """Familias del catálogo imperial de tuberías (para pipes de gravedad).
    Cada elemento es dict con id/pretty/subfolder/img_path/kind='pipe'."""
    root = pipes_root(year)
    if root is None: return []
    out = []
    for sub in PIPE_SUBFOLDERS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d): continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".xml"): continue
            fid = os.path.splitext(fn)[0]
            bmp = os.path.join(d, fid + ".bmp")
            out.append({
                "id": fid,
                "pretty": _pretty_from_filename(fn),
                "subfolder": sub,
                "img_path": bmp if os.path.isfile(bmp) else None,
                "kind": "pipe",
            })
    return out


def pipe_family_xml(year, fid):
    """Ruta absoluta al .xml de la familia de tubería (o None)."""
    root = pipes_root(year)
    if root is None: return None
    for sub in PIPE_SUBFOLDERS:
        p = os.path.join(root, sub, fid + ".xml")
        if os.path.isfile(p): return p
    return None


def pipe_sizes(year, fid):
    """Tamaños disponibles de una familia de tubería. Los XML de pipes usan
    <Column>/<Row> (a diferencia de las estructuras que usan ColumnConstList/Item).
    Busca el diámetro interior (PID / PipeInnerDiameter) o el primer parámetro
    con filas disponibles."""
    path = pipe_family_xml(year, fid)
    if path is None: return []
    try:
        tree = ET.parse(path); root_el = tree.getroot()
    except ET.ParseError:
        return []
    preferred_contexts = ("PipeInnerDiameter", "PipeOuterDiameter",
                          "PipeInnerHeight", "PipeInnerWidth")
    def _fmt(v, unit):
        try: x = float(v)
        except (TypeError, ValueError): return str(v)
        u = (unit or "").lower()
        u = "in" if u in ("inch", "in", "\"") else ("ft" if u in ("foot", "feet", "ft", "'") else u)
        s = f"{x:.4f}".rstrip("0").rstrip(".")
        return f"{s} {u}" if u else s
    def _extract(col, row_tag):
        unit = col.get("unit", "")
        vals = [it.text for it in col.findall(row_tag) if it.text]
        seen, out = set(), []
        for v in vals:
            s = _fmt(v, unit)
            if s in seen: continue
            seen.add(s); out.append(s)
        return out
    for ctx in preferred_contexts:
        for col in root_el.findall("Column"):
            if col.get("context") == ctx:
                sizes = _extract(col, "Row")
                if sizes: return sizes
    for col in root_el.findall("Column"):
        sizes = _extract(col, "Row")
        if sizes: return sizes

    # Fallback: familias tipo Bancoductos usan <ColumnConstList>/<Item> igual que
    # las estructuras. Si hay a la vez PipeInnerWidth + PipeInnerHeight (rectangular)
    # devolvemos el producto cartesiano "W x H in". Si solo hay diámetro (circular),
    # devolvemos esa lista sola.
    cols_by_ctx = {}
    for col in root_el.findall("ColumnConstList"):
        ctx = col.get("context", "")
        vals = [it.text for it in col.findall("Item") if it.text]
        if vals: cols_by_ctx[ctx] = (col.get("unit", ""), vals)
    if "PipeInnerWidth" in cols_by_ctx and "PipeInnerHeight" in cols_by_ctx:
        uw, ws = cols_by_ctx["PipeInnerWidth"]
        uh, hs = cols_by_ctx["PipeInnerHeight"]
        u = uw or uh
        def _n(v):
            try: x = float(v); s = f"{x:.4f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError): s = str(v)
            return s
        norm_u = "in" if (u or "").lower() in ("inch", "in", "\"") else \
                 ("ft" if (u or "").lower() in ("foot", "feet", "ft", "'") else (u or ""))
        # Formato "{W} in x {H} in" — el mismo que el ColumnCalc del catálogo
        # (p.ej. "Bancoducto BT 28 in x 10 in"). Necesario para que el matcher
        # del addin (Norm + Contains) lo encuentre en el PartSize.Name.
        out, seen = [], set()
        for w in ws:
            for h in hs:
                if norm_u: s = f"{_n(w)} {norm_u} x {_n(h)} {norm_u}"
                else:      s = f"{_n(w)} x {_n(h)}"
                if s in seen: continue
                seen.add(s); out.append(s)
        return out
    for ctx in preferred_contexts:
        if ctx in cols_by_ctx:
            unit, vals = cols_by_ctx[ctx]
            fake_col = ET.Element("C"); fake_col.set("unit", unit)
            for v in vals:
                it = ET.SubElement(fake_col, "R"); it.text = v
            sizes = _extract(fake_col, "R")
            if sizes: return sizes
    return []


def imperial_structures(year):
    """Familias del catálogo imperial de estructuras (buzones de gravedad).
    Cada elemento es dict con id/pretty/subfolder/img_path/kind."""
    root = catalog_root(year)
    if root is None: return []
    out = []
    for sub in STRUCTURE_SUBFOLDERS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d): continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".xml"): continue
            fid = os.path.splitext(fn)[0]
            bmp = os.path.join(d, fid + ".bmp")
            out.append({
                "id": fid,
                "pretty": _pretty_from_filename(fn),
                "subfolder": sub,
                "img_path": bmp if os.path.isfile(bmp) else None,
                "kind": "structure",
            })
    return out


def _pretty_pressure(family_name):
    """Convierte 'reducer (conc)-flanged-ductile iron-150 psi' → title case."""
    if not family_name: return "(sin nombre)"
    return family_name.strip()


def pressure_pipes(year):
    """Familias de TUBERÍAS de presión del catálogo por sub-material (WA_PIPE_MODEL).
    Devuelve la misma estructura de dict que imperial_pipes/pressure_families."""
    root = pressure_root(year)
    if root is None: return []
    out = []
    for fn in sorted(os.listdir(root)):
        if not fn.lower().endswith(".sqlite"): continue
        subcat = os.path.splitext(fn)[0]
        db_path = os.path.join(root, fn)
        img_dir = os.path.join(root, subcat, "IMG")
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True); c = conn.cursor()
        except Exception:
            continue
        try:
            try:
                c.execute(
                    "SELECT PART_FAMILY_NAME, MIN(PART_FAMILY_ID) FROM WA_PIPE_MODEL "
                    "WHERE PART_FAMILY_NAME IS NOT NULL "
                    "GROUP BY PART_FAMILY_NAME ORDER BY PART_FAMILY_NAME"
                )
            except sqlite3.Error:
                continue
            for fam_name, fam_id in c.fetchall():
                if not fam_name: continue
                img = None
                if fam_id:
                    p = os.path.join(img_dir, f"{fam_id}.png")
                    if os.path.isfile(p): img = p
                out.append({
                    "id": f"{subcat}|{fam_name}",
                    "pretty": fam_name.strip(),
                    "subfolder": subcat,
                    "img_path": img,
                    "kind": "pressure_pipe",
                })
        finally:
            conn.close()
    return out


def pressure_pipe_sizes(year, fid):
    """DIAMETER_NOMINAL únicos de una familia de tubería de presión."""
    if "|" not in (fid or ""): return []
    subcat, fam_name = fid.split("|", 1)
    root = pressure_root(year)
    if root is None: return []
    db_path = os.path.join(root, subcat + ".sqlite")
    if not os.path.isfile(db_path): return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True); c = conn.cursor()
    except Exception:
        return []
    raw = []
    try:
        try:
            c.execute(
                "SELECT DISTINCT DIAMETER_NOMINAL FROM WA_PIPE_MODEL "
                "WHERE PART_FAMILY_NAME=? AND DIAMETER_NOMINAL IS NOT NULL",
                (fam_name,)
            )
        except sqlite3.Error:
            return []
        for (dn,) in c.fetchall():
            if dn and dn not in raw: raw.append(dn)
    finally:
        conn.close()
    def _key(s):
        m = re.match(r"\s*(\d+(?:\.\d+)?)", str(s))
        return float(m.group(1)) if m else 1e9
    raw.sort(key=_key)
    def _pretty(s):
        s = str(s).strip()
        return f"{s} in" if re.fullmatch(r"\d+(?:\.\d+)?", s) else s
    return [_pretty(s) for s in raw]


def pressure_families(year):
    """Familias de accesorios de presión (nodos: válvulas, hidrantes, tees, codos…).
    Agrupa por (sub-catálogo, PART_FAMILY_NAME) para no explotar en cientos de tamaños."""
    root = pressure_root(year)
    if root is None: return []
    out = []
    for fn in sorted(os.listdir(root)):
        if not fn.lower().endswith(".sqlite"): continue
        subcat = os.path.splitext(fn)[0]                   # p.ej. 'Imperial_AWWA_Flanged'
        db_path = os.path.join(root, fn)
        img_dir = os.path.join(root, subcat, "IMG")
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            c = conn.cursor()
        except Exception:
            continue
        try:
            for tbl in PRESSURE_TABLES:
                try:
                    c.execute(f"SELECT COUNT(*) FROM {tbl}")
                    if c.fetchone()[0] == 0: continue
                except sqlite3.Error:
                    continue
                # Familia = agrupación por PART_FAMILY_NAME; PART_FAMILY_ID (GUID) sirve
                # de identificador único y apunta al PNG en IMG/. Tomamos el mínimo GUID
                # como representante para tener un único ícono estable.
                try:
                    c.execute(
                        f"SELECT PART_FAMILY_NAME, MIN(PART_FAMILY_ID) "
                        f"FROM {tbl} WHERE PART_FAMILY_NAME IS NOT NULL "
                        f"GROUP BY PART_FAMILY_NAME ORDER BY PART_FAMILY_NAME"
                    )
                except sqlite3.Error:
                    continue
                for fam_name, fam_id in c.fetchall():
                    if not fam_name: continue
                    img = None
                    if fam_id:
                        p = os.path.join(img_dir, f"{fam_id}.png")
                        if os.path.isfile(p): img = p
                    # ID canónico: <subcat>|<fam_name>. Estable y único.
                    fid = f"{subcat}|{fam_name}"
                    out.append({
                        "id": fid,
                        "pretty": _pretty_pressure(fam_name),
                        "subfolder": subcat,
                        "img_path": img,
                        "kind": "appurtenance",
                    })
        finally:
            conn.close()
    return out


# ==================================================================
# INSTALADOR DE FAMILIAS PERSONALIZADAS
# ==================================================================
# scan_family_folder — analiza una carpeta local y devuelve la lista de familias
# encontradas con su metadata (tipo, tamaños, hash, warnings).
# family_already_installed — indica si esa familia ya existe en el catálogo de
# una versión Civil 3D (por hash o por basename).
# install_family — copia los archivos al subfolder correcto del catálogo con
# backup .bak si sobreescribe.

import hashlib
import shutil


def _file_hash(path):
    """SHA-256 del contenido de un archivo (hex, 16 chars primeros para tabla)."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _detect_family_kind(xml_path):
    """A partir del contenido de un XML de familia, decide si es de gravedad
    (structure) o de tubería (pipe). Heurística: los XML de PIPE contienen
    parámetros PID/PIH/PIW en <Column>/<ColumnConstList>; los de STRUCTURE
    usan SID/SIW/SIL/SCH/StructInnerDiameter/StructInnerWidth etc.
    Devuelve 'pipe' | 'structure' | 'unknown'."""
    try:
        tree = ET.parse(xml_path); root = tree.getroot()
    except (ET.ParseError, OSError):
        return "unknown"
    pipe_hints = 0; struct_hints = 0
    # Recorrer ColumnConstList y Column, chequear atributos context/name
    for tag in ("ColumnConstList", "ColumnConst", "Column"):
        for el in root.iter(tag):
            ctx = (el.get("context", "") or "").lower()
            nm  = (el.get("name", "") or "").lower()
            for key in (ctx, nm):
                if "pipe" in key or key in ("pid", "pih", "piw", "pod", "poh", "pow"):
                    pipe_hints += 1
                if "struct" in key or key in ("sid", "siw", "sil", "sch", "sod"):
                    struct_hints += 1
    if pipe_hints and pipe_hints >= struct_hints: return "pipe"
    if struct_hints: return "structure"
    return "unknown"


def _target_subfolder(kind, xml_path):
    """Elige la subcarpeta destino dentro del catálogo. Prioridad:
      1. Nombre de la carpeta padre del .xml si coincide con un subfolder
         conocido (o su alias). Así respetamos la organización manual del
         usuario: si tiene sus archivos en 'FAMILIAS/Bancoductos/*.xml', se
         instalan en 'Bancoductos/'.
      2. Palabras clave en el filename.
      3. Fallback por tipo.
    """
    parent = os.path.basename(os.path.dirname(xml_path))
    parent_key = parent.lower().replace(" ", "").replace("-", "").replace("_", "")

    # Aliases y matches directos: cualquier subfolder conocido cuyo nombre
    # (normalizado) coincida con la carpeta padre.
    aliases_struct = {
        "buzones": "BuzonesElectricas",
        "buzoneselectricos": "BuzonesElectricas",
        "buzonesbt": "BuzonesElectricas",
        "junctionstructures": "Junction Structures with Frames",
        "junctions": "Junction Structures with Frames",
        "junctionswithoutframes": "Junction Structures without Frames",
        "inletoutlets": "Inlet-Outlets",
        "inlets": "Inlet-Outlets",
        "outlets": "Inlet-Outlets",
        "headwalls": "Inlet-Outlets",
        "simpleshapes": "Simple Shapes",
    }
    aliases_pipe = {
        "circularpipes": "Circular Pipes",
        "eggshapedpipes": "Egg-Shaped Pipes",
        "ellipticalpipes": "Elliptical Pipes",
        "rectangularpipes": "Rectangular Pipes",
        "bancoductos": "Bancoductos",
        "bancostubos": "Bancos Tubos",
        "bancos": "Bancos Tubos",
    }

    if kind == "pipe":
        # 1) por carpeta padre
        for sub in PIPE_SUBFOLDERS:
            if sub.lower().replace(" ", "") == parent_key: return sub
        if parent_key in aliases_pipe: return aliases_pipe[parent_key]
        # 2) por filename
        fname = os.path.basename(xml_path).lower()
        fnorm = fname.replace("_", "").replace("-", "").replace(" ", "")
        for sub in PIPE_SUBFOLDERS:
            if sub.lower().replace(" ", "") in fnorm: return sub
        if "bancoducto" in fname: return "Bancoductos"
        if "bancotubo" in fname or "bancostubos" in fname: return "Bancos Tubos"
        if "rectang" in fname: return "Rectangular Pipes"
        if "eggshaped" in fname or "egg" in fname: return "Egg-Shaped Pipes"
        if "elliptic" in fname: return "Elliptical Pipes"
        if "circular" in fname or "concrete" in fname or "hdpe" in fname or "pvc" in fname or "cmp" in fname:
            return "Circular Pipes"
        # 3) fallback conservador
        return None
    if kind == "structure":
        # 1) por carpeta padre
        for sub in STRUCTURE_SUBFOLDERS:
            if sub.lower().replace(" ", "") == parent_key: return sub
        if parent_key in aliases_struct: return aliases_struct[parent_key]
        # 2) por filename
        fname = os.path.basename(xml_path).lower()
        fnorm = fname.replace("_", "").replace("-", "").replace(" ", "")
        for sub in STRUCTURE_SUBFOLDERS:
            if sub.lower().replace(" ", "") in fnorm: return sub
        if "buzon" in fname or "electri" in fname or "ict" in fname or "mt" in fname:
            return "BuzonesElectricas"
        if "junction" in fname and "without" in fname: return "Junction Structures without Frames"
        if "junction" in fname: return "Junction Structures with Frames"
        if "inlet" in fname or "outlet" in fname or "headwall" in fname or "endsection" in fname:
            return "Inlet-Outlets"
        return "Simple Shapes"
    return None


def _extract_family_desc(xml_path):
    """Lee el PrtD (Catalog_PartDesc) del XML — nombre humano de la familia."""
    try:
        tree = ET.parse(xml_path); root = tree.getroot()
    except (ET.ParseError, OSError):
        return None
    for cc in root.findall("ColumnConst"):
        if cc.get("context") == "Catalog_PartDesc" and cc.text:
            return cc.text.strip()
    return None


def validate_family_xml(xml_path):
    """Auditoría del XML de una familia. Devuelve una lista de dicts
    {severity, message} donde severity es 'grave' o 'warn'. Los mensajes están
    escritos para ing. civil (sin jerga XML).

    Se validan cosas que hacen que Civil 3D reconozca la familia pero no la
    dibuje bien:
      · listas de parámetros vacías (Diámetro, Espesor de muro, etc.)
      · valores no numéricos donde deben ser números
      · fórmulas que usan una variable inexistente
      · ausencia de la fórmula del "Nombre del tamaño" (Part Size Name)
    """
    issues = []
    try:
        tree = ET.parse(xml_path); root = tree.getroot()
    except (ET.ParseError, OSError) as e:
        return [{"severity": "grave",
                 "message": f"El archivo XML de la familia no se puede abrir o está corrupto ({e})."}]

    # Los XML de familias Civil 3D siempre tienen la raíz <LandPart>. Si no,
    # es probable que sea otro tipo de archivo.
    if root.tag != "LandPart":
        return [{"severity": "grave",
                 "message": "El XML no parece una familia de Civil 3D válida "
                            "(la etiqueta raíz no es 'LandPart')."}]

    # Diccionario name → tipo de columna, usado para chequear que las fórmulas
    # referencian variables que sí existen.
    declared = set()
    def _register(el):
        n = (el.get("name") or "").strip()
        if n: declared.add(n)

    # Todas las columnas que pueden ser referenciadas en fórmulas. Cada tag
    # de "Column*" declara una variable con atributo name="...".
    for tag in ("ColumnConst", "ColumnConstList", "ColumnRangeList",
                "ColumnCalc", "Column", "ColumnUnique"):
        for el in root.findall(tag):
            _register(el)

    # ¿Está la fórmula del nombre de tamaño? Puede estar en ColumnConst o ColumnCalc.
    has_part_size_name = False
    for el in list(root.findall("ColumnConst")) + list(root.findall("ColumnCalc")):
        if (el.get("context") or "").strip() == "Catalog_PartSizeName":
            has_part_size_name = True; break

    if not has_part_size_name:
        issues.append({"severity": "grave",
                       "message": "La familia no define el 'Nombre del tamaño' — Civil 3D "
                                  "no sabrá cómo llamar a cada tamaño y el plugin no podrá "
                                  "encontrar esta familia al importar."})

    # ColumnConstList: listas de valores por parámetro (Diámetro, Espesor, etc.)
    for lst in root.findall("ColumnConstList"):
        name = (lst.get("desc") or lst.get("name") or lst.get("context") or "parámetro").strip()
        items = lst.findall("Item")
        if not items:
            issues.append({"severity": "grave",
                           "message": f"El parámetro '{name}' no tiene ningún valor cargado. Sin valores, Civil 3D no generará ningún tamaño."})
            continue
        dtype = (lst.get("dataType") or "").lower()
        for it in items:
            txt = (it.text or "").strip()
            if not txt:
                issues.append({"severity": "grave",
                               "message": f"El parámetro '{name}' tiene un valor en blanco entre sus opciones."})
                continue
            if dtype in ("float", "double", "int", "long"):
                try: float(txt)
                except ValueError:
                    issues.append({"severity": "grave",
                                   "message": f"El parámetro '{name}' tiene el valor '{txt}' que no es un número."})

    # ColumnRangeList: rangos (mínimo/máximo/default). Solo warn si faltan Min y Max.
    for lst in root.findall("ColumnRangeList"):
        name = (lst.get("desc") or lst.get("name") or "rango").strip()
        vals = {(it.get("rangeVal") or "").lower(): (it.text or "").strip()
                for it in lst.findall("Item")}
        if not vals.get("min") or not vals.get("max"):
            issues.append({"severity": "warn",
                           "message": f"El rango '{name}' no tiene mínimo o máximo definido."})

    # ColumnCalc: fórmulas. En Civil 3D las variables usan sintaxis $NombreCol.
    # Solo consideramos identificadores válidos (letras, dígitos, _).
    var_re = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
    for cc in root.findall("ColumnCalc"):
        formula = (cc.text or "").strip()
        if not formula: continue
        vars_in_formula = set(var_re.findall(formula))
        for var in vars_in_formula:
            if var not in declared:
                fname = (cc.get("desc") or cc.get("name") or cc.get("context") or "fórmula").strip()
                issues.append({"severity": "grave",
                               "message": f"La fórmula '{fname}' usa la variable '${var}' que no está definida en la familia. Civil 3D no podrá calcular ese valor."})

    # <Recipe>: ruta al .dwg del Part Builder. Debe ser SOLO el nombre del
    # archivo, sin prefijo de carpeta — Civil 3D lo busca en el mismo directorio
    # que el .xml. Si trae un prefijo como "Bancoductos\foo.dwg", Civil no
    # encuentra el archivo y la familia se dibuja como caja vacía.
    # Nota: el instalador AUTO-CORRIGE esto al copiar, por eso es 'warn'.
    for rec in root.iter("Recipe"):
        val = (rec.text or "").strip()
        if not val: continue
        if "\\" in val or "/" in val:
            issues.append({"severity": "warn",
                           "message": f"La referencia al archivo .dwg lleva un prefijo de carpeta ('{val}'). El instalador lo corregirá al copiar."})

    return issues


def _fix_family_xml_content(src_xml_path, entry_name):
    """Lee el XML fuente y devuelve el contenido corregido con:
      · <Recipe> reducido a solo basename (sin prefijo de carpeta).
      · <URL xlink:href> del BMP idem.
    Si no hay nada que corregir, devuelve None (usar el original tal cual).
    Nunca lanza — devuelve None ante cualquier error."""
    try:
        with open(src_xml_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None
    changed = False
    # Fix <Recipe>path\foo.dwg</Recipe> → <Recipe>foo.dwg</Recipe>
    def _fix_recipe(m):
        nonlocal changed
        val = m.group(1)
        new = os.path.basename(val.replace("\\", "/"))
        if new != val:
            changed = True
        return f">{new}</Recipe>"
    content2 = re.sub(r">([^<>]*?\.dwg)</Recipe>", _fix_recipe, content, flags=re.IGNORECASE)
    # Fix <URL xlink:href="path\foo.bmp"/> → xlink:href="foo.bmp"
    def _fix_href(m):
        nonlocal changed
        attr = m.group(1); val = m.group(2)
        new = os.path.basename(val.replace("\\", "/"))
        if new != val:
            changed = True
        return f'{attr}"{new}"'
    content2 = re.sub(r'(xlink:href=)"([^"]*?\.(?:bmp|dwg))"', _fix_href, content2, flags=re.IGNORECASE)
    return content2 if changed else None


def _sizes_list(kind, xml_path):
    """Devuelve la lista real de tamaños que un usuario vería en el combo
    Python. Prioridad:
      - Estructuras rectangulares (SIW+SIL): "W x L in"
      - Estructuras circulares (SID / diameter): "D in"
      - Pipes rectangulares (PIW+PIH): "W x H in"
      - Pipes circulares (PID): "D in"
      - Column/Row: primera columna del design table
    Lista vacía si no encuentra nada.
    """
    try:
        tree = ET.parse(xml_path); root = tree.getroot()
    except (ET.ParseError, OSError):
        return []

    def _norm_unit(u):
        u = (u or "").lower()
        if u in ("inch", "in", "\""): return "in"
        if u in ("foot", "feet", "ft", "'"): return "ft"
        return u

    def _clean_num(s):
        try:
            x = float(s); return f"{x:.4f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(s).strip()

    # Recolectar ColumnConstList por context
    lists_by_ctx = {}
    for cc in root.findall("ColumnConstList"):
        ctx = cc.get("context", "")
        items = [(it.text or "").strip() for it in cc.findall("Item") if (it.text or "").strip()]
        if items:
            lists_by_ctx[ctx] = (cc.get("unit", ""), items)

    def _cart(w_ctx, h_ctx):
        """Producto cartesiano: cada W x cada H."""
        if w_ctx not in lists_by_ctx or h_ctx not in lists_by_ctx: return None
        uw, ws = lists_by_ctx[w_ctx]; uh, hs = lists_by_ctx[h_ctx]
        u = _norm_unit(uw or uh)
        out, seen = [], set()
        for w in ws:
            for h in hs:
                s = f"{_clean_num(w)} x {_clean_num(h)}" + (f" {u}" if u else "")
                if s in seen: continue
                seen.add(s); out.append(s)
        return out

    def _single(ctx):
        if ctx not in lists_by_ctx: return None
        u, vs = lists_by_ctx[ctx]; unit = _norm_unit(u)
        out, seen = [], set()
        for v in vs:
            s = _clean_num(v) + (f" {unit}" if unit else "")
            if s in seen: continue
            seen.add(s); out.append(s)
        return out

    # Estructuras rectangulares
    r = _cart("StructInnerWidth", "StructInnerLength")
    if r: return r
    # Estructuras circulares
    r = _single("StructInnerDiameter") or _single("StructOuterDiameter") \
        or _single("StructFrameLength") or _single("StructWidth")
    if r: return r
    # Pipes rectangulares
    r = _cart("PipeInnerWidth", "PipeInnerHeight")
    if r: return r
    # Pipes circulares / óvalos
    r = _single("PipeInnerDiameter") or _single("PipeOuterDiameter") \
        or _single("PipeInnerHeight") or _single("PipeInnerWidth")
    if r: return r

    # Fallback: Column/Row design table — primera Column con Rows
    for col in root.findall("Column"):
        rows = [(rr.text or "").strip() for rr in col.findall("Row") if (rr.text or "").strip()]
        if rows:
            u = _norm_unit(col.get("unit", ""))
            out, seen = [], set()
            for v in rows:
                s = _clean_num(v) + (f" {u}" if u else "")
                if s in seen: continue
                seen.add(s); out.append(s)
            return out
    return []


def scan_family_folder(path):
    """Analiza una carpeta local con XMLs de familias personalizadas. Devuelve
    una lista de dicts, uno por familia (.xml) detectada.

    Cada entry:
        name             — basename sin extensión
        display_name     — Catalog_PartDesc si existe, si no _pretty_from_filename
        kind             — 'pipe' | 'structure' | 'unknown'
        target_subfolder — subcarpeta destino dentro del catálogo (o None)
        xml_path         — ruta al .xml en la carpeta origen
        bmp_path         — ruta al thumb .bmp si existe al lado
        hash             — SHA-256 hex del .xml
        sizes_list       — lista real de tamaños legibles p.ej. ["72 in", "96 in"]
        warnings         — lista de strings específicos
        grave_reasons    — subconjunto de warnings que impiden instalar
    """
    out = []
    if not path or not os.path.isdir(path): return out
    for fn in sorted(os.listdir(path)):
        if not fn.lower().endswith(".xml"): continue
        xml_path = os.path.join(path, fn)
        name = os.path.splitext(fn)[0]
        bmp_path = os.path.join(path, name + ".bmp")
        if not os.path.isfile(bmp_path): bmp_path = None
        # DWG del Part Builder — esencial; sin él la familia no compila en Civil 3D.
        dwg_path = os.path.join(path, name + ".dwg")
        if not os.path.isfile(dwg_path): dwg_path = None
        kind = _detect_family_kind(xml_path)
        sub = _target_subfolder(kind, xml_path)
        desc = _extract_family_desc(xml_path)
        sizes_list = _sizes_list(kind, xml_path)

        warnings = []
        grave = []
        if kind == "unknown":
            msg = "No pude detectar si es tubería o estructura (revisa que el XML tenga ColumnConstList con SID/PID/etc)."
            warnings.append(msg); grave.append(msg)
        if dwg_path is None:
            msg = f"Falta el archivo .dwg de Part Builder ('{name}.dwg') al lado del .xml — la familia NO funcionará en Civil 3D sin él."
            warnings.append(msg); grave.append(msg)
        if bmp_path is None:
            warnings.append("Sin miniatura .bmp — el usuario no verá thumbnail al elegir la familia.")
        if desc is None:
            warnings.append("Falta ColumnConst 'Catalog_PartDesc' — el plugin C# usará el nombre del archivo como Description.")
        if not sizes_list:
            msg = "El XML no declara ningún tamaño (no hay ColumnConstList con Items ni Column con Rows). Civil 3D no compilará ningún PartSize."
            warnings.append(msg); grave.append(msg)

        # Validación profunda del contenido del XML — detecta problemas
        # semánticos que hacen que Civil 3D reconozca la familia pero no la
        # dibuje correctamente (fórmulas rotas, items inválidos, etc.).
        for issue in validate_family_xml(xml_path):
            warnings.append(issue["message"])
            if issue["severity"] == "grave":
                grave.append(issue["message"])

        # Leer PartName interno (para detectar duplicados en el batch — si dos
        # XMLs comparten PartName, Civil 3D solo registra uno y descarta el otro).
        part_name = None
        try:
            tr = ET.parse(xml_path); rr = tr.getroot()
            for cc in rr.findall("ColumnConst"):
                if (cc.get("context") or "") == "Catalog_PartName" and cc.text:
                    part_name = cc.text.strip(); break
        except (ET.ParseError, OSError):
            pass

        out.append({
            "name": name,
            "display_name": desc or _pretty_from_filename(fn),
            "kind": kind,
            "target_subfolder": sub,
            "xml_path": xml_path,
            "bmp_path": bmp_path,
            "dwg_path": dwg_path,
            "hash": _file_hash(xml_path),
            "sizes_list": sizes_list,
            "part_name": part_name,
            "warnings": warnings,
            "grave_reasons": grave,
        })

    # Post-proceso: detectar PartName duplicados entre archivos del batch.
    # Civil 3D usa PartName como clave — dos familias con el mismo PartName
    # producen que Civil solo cargue una y descarte la otra silenciosamente.
    from collections import Counter
    pn_counts = Counter(e["part_name"] for e in out if e.get("part_name"))
    for e in out:
        pn = e.get("part_name")
        if pn and pn_counts[pn] > 1:
            msg = (f"Otro archivo XML en esta carpeta usa el mismo nombre interno "
                   f"'{pn}'. Civil 3D solo cargará uno de ellos y descartará el otro. "
                   f"Cambia el nombre interno para diferenciarlos.")
            e["warnings"].append(msg)
            e["grave_reasons"].append(msg)
    return out


def _installed_family_path(year, kind, subfolder, name):
    """Ruta absoluta donde iría el .xml de la familia en el catálogo instalado
    (según subfolder heurística). Para escribir. Puede no coincidir con la
    ubicación real si el archivo se puso a mano en otra subcarpeta."""
    if kind == "pipe":
        root = pipes_root(year)
    else:
        root = catalog_root(year)
    if root is None or not subfolder: return None
    return os.path.join(root, subfolder, name + ".xml")


def _find_installed_xml(year, kind, name):
    """Busca el .xml de la familia en TODAS las subcarpetas del catálogo del año.
    Esto es lo que corresponde para detección: si alguien puso el archivo en una
    subcarpeta distinta a la que nuestra heurística eligió, igual lo encontramos.
    Devuelve la ruta absoluta o None. Si kind='unknown' busca en pipes y structs."""
    hits = []
    if kind in ("pipe", "unknown"):
        r = pipes_root(year)
        if r:
            for sub in PIPE_SUBFOLDERS:
                p = os.path.join(r, sub, name + ".xml")
                if os.path.isfile(p): hits.append(p)
    if kind in ("structure", "unknown"):
        r = catalog_root(year)
        if r:
            for sub in STRUCTURE_SUBFOLDERS:
                p = os.path.join(r, sub, name + ".xml")
                if os.path.isfile(p): hits.append(p)
    return hits[0] if hits else None


def family_already_installed(year, entry):
    """Compara la familia contra el catálogo del año dado. Busca en TODAS las
    subcarpetas del catálogo (no solo la sugerida por heurística) — así detecta
    archivos que el usuario haya colocado a mano en otra subcarpeta.
    Devuelve:
        'same'      — existe con el mismo hash → no reinstalar
        'different' — existe con el mismo basename pero contenido distinto
        'no'        — no existe todavía en ninguna subcarpeta
    """
    hit = _find_installed_xml(year, entry.get("kind"), entry.get("name"))
    if hit is None: return "no"
    existing_hash = _file_hash(hit)
    if existing_hash and existing_hash == entry.get("hash"): return "same"
    return "different"


def installed_custom_families(year):
    """Lista las familias PERSONALIZADAS instaladas en el catálogo del año dado.
    Criterio: cualquier .xml en las subcarpetas del catálogo cuyo basename NO
    empiece con 'Aecc' (todas las familias stock de Autodesk empiezan así).
    Devuelve lista de dicts con:
        name             — basename sin extensión
        display_name     — Catalog_PartDesc si existe, si no _pretty_from_filename
        kind             — 'pipe' | 'structure'
        subfolder        — subcarpeta real donde está el archivo
        xml_path         — ruta absoluta al .xml
        bmp_path         — ruta al .bmp al lado o None
        sizes_list       — lista real de tamaños
    """
    out = []
    # Estructuras
    r = catalog_root(year)
    if r:
        for sub in STRUCTURE_SUBFOLDERS:
            d = os.path.join(r, sub)
            if not os.path.isdir(d): continue
            for fn in sorted(os.listdir(d)):
                if not fn.lower().endswith(".xml"): continue
                if fn.startswith("Aecc"): continue
                xml_path = os.path.join(d, fn)
                name = os.path.splitext(fn)[0]
                bmp = os.path.join(d, name + ".bmp")
                if not os.path.isfile(bmp): bmp = None
                out.append({
                    "name": name,
                    "display_name": _extract_family_desc(xml_path) or _pretty_from_filename(fn),
                    "kind": "structure",
                    "subfolder": sub,
                    "xml_path": xml_path,
                    "bmp_path": bmp,
                    "sizes_list": _sizes_list("structure", xml_path),
                })
    # Tuberías
    r = pipes_root(year)
    if r:
        for sub in PIPE_SUBFOLDERS:
            d = os.path.join(r, sub)
            if not os.path.isdir(d): continue
            for fn in sorted(os.listdir(d)):
                if not fn.lower().endswith(".xml"): continue
                if fn.startswith("Aecc"): continue
                xml_path = os.path.join(d, fn)
                name = os.path.splitext(fn)[0]
                bmp = os.path.join(d, name + ".bmp")
                if not os.path.isfile(bmp): bmp = None
                out.append({
                    "name": name,
                    "display_name": _extract_family_desc(xml_path) or _pretty_from_filename(fn),
                    "kind": "pipe",
                    "subfolder": sub,
                    "xml_path": xml_path,
                    "bmp_path": bmp,
                    "sizes_list": _sizes_list("pipe", xml_path),
                })
    return out


def install_family(year, entry):
    """Copia el .xml (y el .bmp si existe) al subfolder destino del catálogo del
    año elegido. Si el .xml ya existe (en cualquier subfolder), sobreescribe
    IN SITU en ese lugar (no crea duplicado) y hace backup .bak (o .bak.N).
    Si no existe todavía, usa la subfolder heurística de entry['target_subfolder'].
    Devuelve dict:
        ok           — bool
        error        — string si !ok
        backed_up    — path del .bak creado o None
        installed_at — path del .xml final
    """
    # Si ya existe en algún lugar, reemplazamos ahí; si no, usamos la heurística.
    tgt_xml = _find_installed_xml(year, entry.get("kind"), entry.get("name"))
    if tgt_xml is None:
        tgt_xml = _installed_family_path(year, entry.get("kind"),
                                          entry.get("target_subfolder"),
                                          entry.get("name"))
    if tgt_xml is None:
        return {"ok": False, "error": "No pude resolver la carpeta destino del catálogo Civil 3D.", "backed_up": None, "installed_at": None}
    tgt_dir = os.path.dirname(tgt_xml)
    try:
        os.makedirs(tgt_dir, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": f"No pude crear la carpeta destino: {e}", "backed_up": None, "installed_at": None}
    backup = None
    if os.path.isfile(tgt_xml):
        # backup .bak, o .bak.N si ya existía
        bak = tgt_xml + ".bak"
        n = 1
        while os.path.exists(bak):
            bak = tgt_xml + f".bak.{n}"; n += 1
        try:
            shutil.copy2(tgt_xml, bak)
            backup = bak
        except OSError as e:
            return {"ok": False, "error": f"No pude hacer backup del .xml existente: {e}", "backed_up": None, "installed_at": None}
    # Auto-corregir problemas comunes del XML antes de copiar:
    # · <Recipe> con prefijo de carpeta → solo basename
    # · xlink:href del BMP con prefijo → solo basename
    fixed = _fix_family_xml_content(entry["xml_path"], entry["name"])
    try:
        if fixed is not None:
            with open(tgt_xml, "w", encoding="utf-8") as f:
                f.write(fixed)
        else:
            shutil.copy2(entry["xml_path"], tgt_xml)
    except OSError as e:
        return {"ok": False, "error": f"No pude copiar el .xml: {e}", "backed_up": backup, "installed_at": None}
    bmp_src = entry.get("bmp_path")
    if bmp_src:
        tgt_bmp = os.path.join(tgt_dir, entry["name"] + ".bmp")
        try:
            shutil.copy2(bmp_src, tgt_bmp)
        except OSError:
            pass                                        # thumb es opcional
    dwg_src = entry.get("dwg_path")
    if dwg_src:
        tgt_dwg = os.path.join(tgt_dir, entry["name"] + ".dwg")
        # Backup del dwg si ya existía (importante — Part Builder puede estar
        # usándolo). Usamos misma convención .bak/.bak.N.
        if os.path.isfile(tgt_dwg):
            bakd = tgt_dwg + ".bak"
            n = 1
            while os.path.exists(bakd):
                bakd = tgt_dwg + f".bak.{n}"; n += 1
            try: shutil.copy2(tgt_dwg, bakd)
            except OSError: pass
        try:
            shutil.copy2(dwg_src, tgt_dwg)
        except OSError as e:
            return {"ok": False,
                    "error": f".xml copiado pero no pude copiar el .dwg: {e}. "
                             "La familia NO funcionará sin él.",
                    "backed_up": backup, "installed_at": tgt_xml}
    return {"ok": True, "error": "", "backed_up": backup, "installed_at": tgt_xml}


# ============================================================================
# INSTALACIÓN DE PAQUETE DE CATÁLOGO CUSTOM
# ============================================================================
# Enfoque correcto (según el flujo estándar de Autodesk y el proyecto de
# referencia): en vez de copiar .xml sueltos a ProgramData (que requiere
# regenerar el .apc), copiamos la CARPETA COMPLETA de un catálogo custom
# (que YA incluye el .apc pre-regenerado por el modelador). El usuario luego
# apunta Civil 3D a esa carpeta con SETPIPENETWORKCATALOG.

DEFAULT_CATALOG_DEST = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "AsistenteC3D", "Catalog")


def _find_catalog_subdirs(source_folder):
    """Busca dentro de `source_folder` las subcarpetas 'US Imperial Pipes' y
    'US Imperial Structures' (o variantes con sufijo). Devuelve dict con:
        pipes_src     — path source, o None
        pipes_apc     — path al .apc, o None
        structs_src   — path source, o None
        structs_apc   — path al .apc, o None
    """
    result = {"pipes_src": None, "pipes_apc": None,
              "structs_src": None, "structs_apc": None}
    if not source_folder or not os.path.isdir(source_folder):
        return result
    # La estructura estándar tiene el catálogo en Pipes Catalog\... . Pero el
    # modelador puede haber comprimido el nivel intermedio. Buscamos en 2
    # profundidades: source_folder\... y source_folder\Pipes Catalog\...
    roots_to_search = [source_folder]
    pc = os.path.join(source_folder, "Pipes Catalog")
    if os.path.isdir(pc): roots_to_search.append(pc)
    for root in roots_to_search:
        # Pipes
        if result["pipes_src"] is None:
            p = _find_catalog_subdir(root, "US Imperial Pipes")
            if p:
                result["pipes_src"] = p
                apc = os.path.join(p, "US Imperial Pipes.apc")
                if os.path.isfile(apc): result["pipes_apc"] = apc
        # Structures
        if result["structs_src"] is None:
            p = _find_catalog_subdir(root, "US Imperial Structures")
            if p:
                result["structs_src"] = p
                apc = os.path.join(p, "US Imperial Structures.apc")
                if os.path.isfile(apc): result["structs_apc"] = apc
    return result


def install_catalog_package(source_folder, dest_folder=None):
    """Copia una carpeta de catálogo custom completa al destino. Requiere que
    el source contenga 'US Imperial Pipes\\US Imperial Pipes.apc' y/o
    'US Imperial Structures\\US Imperial Structures.apc' (con sus subcarpetas
    y .xml/.dwg/.bmp de las familias).

    Args:
        source_folder — carpeta local con el catálogo custom del modelador.
        dest_folder   — destino, default %APPDATA%\\AsistenteC3D\\Catalog\\.

    Devuelve dict:
        ok            — bool
        error         — string si !ok
        dest          — path del catálogo copiado (o None)
        pipes_path    — path a US Imperial Pipes\\ dentro de dest (o None)
        structs_path  — path a US Imperial Structures\\ dentro de dest (o None)
        summary       — texto legible con estadísticas
    """
    if dest_folder is None: dest_folder = DEFAULT_CATALOG_DEST
    found = _find_catalog_subdirs(source_folder)
    if not found["pipes_src"] and not found["structs_src"]:
        return {"ok": False, "dest": None, "pipes_path": None, "structs_path": None,
                "summary": "",
                "error": (f"En '{source_folder}' no encontré ninguna subcarpeta "
                          "'US Imperial Pipes' ni 'US Imperial Structures'. "
                          "El source debe ser la raíz del catálogo custom del "
                          "modelador (con .apc adentro).")}
    warnings = []
    if found["pipes_src"] and not found["pipes_apc"]:
        warnings.append(f"'{os.path.basename(found['pipes_src'])}' no tiene "
                        "'US Imperial Pipes.apc' — Civil 3D no verá familias "
                        "hasta que se regenere el .apc.")
    if found["structs_src"] and not found["structs_apc"]:
        warnings.append(f"'{os.path.basename(found['structs_src'])}' no tiene "
                        "'US Imperial Structures.apc' — idem structures.")

    try:
        os.makedirs(dest_folder, exist_ok=True)
    except OSError as e:
        return {"ok": False, "dest": None, "pipes_path": None, "structs_path": None,
                "summary": "",
                "error": f"No pude crear el destino '{dest_folder}': {e}"}

    def _copy_tree(src, dst):
        """Copia recursivamente src → dst, SOBREESCRIBIENDO archivos existentes.
        Si el destino ya existe (reinstalación), primero lo borra para asegurar
        un estado limpio. Devuelve (n_files, n_bytes)."""
        # Si el destino ya existe, lo borramos entero para evitar mezcla con
        # archivos viejos de una instalación anterior.
        if os.path.isdir(dst):
            try:
                shutil.rmtree(dst)
            except OSError:
                pass                                        # si falla, seguimos con overwrite
        n_files = 0; n_bytes = 0
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            tgt = dst if rel == "." else os.path.join(dst, rel)
            os.makedirs(tgt, exist_ok=True)
            for fn in files:
                # Ignorar .bak y .backup-* (basura del modelador que ocupa mucho)
                if fn.endswith(".bak"): continue
                if ".apc.backup-" in fn: continue
                s = os.path.join(root, fn); t = os.path.join(tgt, fn)
                try:
                    shutil.copy2(s, t)                     # sobreescribe si existe
                    n_files += 1
                    try: n_bytes += os.path.getsize(s)
                    except OSError: pass
                except OSError:
                    pass
        return n_files, n_bytes

    pipes_path = None; structs_path = None
    total_files = 0; total_bytes = 0
    if found["pipes_src"]:
        pipes_path = os.path.join(dest_folder, "US Imperial Pipes")
        n, b = _copy_tree(found["pipes_src"], pipes_path)
        total_files += n; total_bytes += b
    if found["structs_src"]:
        structs_path = os.path.join(dest_folder, "US Imperial Structures")
        n, b = _copy_tree(found["structs_src"], structs_path)
        total_files += n; total_bytes += b

    mb = total_bytes / (1024 * 1024)
    lines = [
        f"✓ Catálogo copiado a: {dest_folder}",
        f"  Archivos copiados: {total_files}  ·  Tamaño: {mb:.1f} MB",
    ]
    if pipes_path:   lines.append(f"  · Tubería:    {pipes_path}")
    if structs_path: lines.append(f"  · Estructura: {structs_path}")
    if warnings:
        lines.append("")
        lines.append("Avisos:")
        for w in warnings: lines.append(f"  · {w}")
    summary = "\n".join(lines)

    return {"ok": True, "error": "", "dest": dest_folder,
            "pipes_path": pipes_path, "structs_path": structs_path,
            "summary": summary}
