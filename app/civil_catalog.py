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


def _lang_root(year):
    """Devuelve la carpeta <lang> dentro de C3D <year>, o None."""
    base = os.path.join(_programdata_root(), "Autodesk", f"C3D {year}")
    if not os.path.isdir(base): return None
    for lang in LANG_PREFERENCES:
        p = os.path.join(base, lang)
        if os.path.isdir(p): return p
    return None


def catalog_root(year):
    """Carpeta 'US Imperial Structures' de la versión indicada, o None."""
    r = _lang_root(year)
    if r is None: return None
    p = os.path.join(r, "Pipes Catalog", "US Imperial Structures")
    return p if os.path.isdir(p) else None


def pipes_root(year):
    """Carpeta 'US Imperial Pipes' de la versión indicada, o None."""
    r = _lang_root(year)
    if r is None: return None
    p = os.path.join(r, "Pipes Catalog", "US Imperial Pipes")
    return p if os.path.isdir(p) else None


def pressure_root(year):
    """Carpeta 'Pressure Pipes Catalog\\Imperial' de la versión indicada, o None."""
    r = _lang_root(year)
    if r is None: return None
    p = os.path.join(r, "Pressure Pipes Catalog", "Imperial")
    return p if os.path.isdir(p) else None


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


def add_structure_size(year, fid, values):
    """Agrega nuevos valores a los <ColumnConstList> del XML de la familia. `values`
    es un dict {name: value_str}. Se crea un backup .xml.bak la primera vez, y solo
    se agrega el Item si ese valor no existía ya. Devuelve un dict con:
      ok: bool | error: str | added: {name: value_agregado} | skipped: {name: motivo}"""
    path = structure_family_xml(year, fid)
    if path is None: return {"ok": False, "error": f"No existe el XML de {fid}"}
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
