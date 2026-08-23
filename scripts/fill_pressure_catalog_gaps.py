"""
fill_pressure_catalog_gaps.py
Agrega accesorios faltantes (codos, tees, crosses, reductores) a los catálogos
SQLite de Pressure Pipes de Civil 3D 2025.

Gaps detectados:
  - Imperial_AWWA_Flanged:  30, 36, 42, 48, 54, 60, 64 in
  - Imperial_AWWA_Steel:    26, 28, 32, 34, 38, 40, 44, 46, 50, 52 in
  - Imperial_AWWA_HDPE:     0.5, 0.75, 1, 1.25, 1.5, 2, 2.5 in

Método: para cada familia existente que no tiene el diámetro faltante, copia la
estructura del registro del diámetro más cercano y escala las dimensiones
geométricas (connection points) proporcionalmente al nuevo diámetro.

REQUIERE: Civil 3D cerrado. Hace backup .bak automático antes de editar.
"""
import sqlite3
import shutil
import os
import uuid
import math
import sys
from datetime import datetime

CATALOG_ROOT = r"C:\ProgramData\Autodesk\C3D 2025\enu\Pressure Pipes Catalog\Imperial"

FITTING_TABLES = [
    "WA_ELBOW_MODEL",
    "WA_BRANCH_FITTING_MODEL",
    "WA_FITTING_MODEL",
]


def backup_db(db_path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{db_path}.{ts}.bak"
    shutil.copy2(db_path, bak)
    print(f"  Backup: {bak}")
    return bak


def get_max_fid(conn):
    c = conn.cursor()
    max_fid = 0
    for tbl in FITTING_TABLES + ["WA_CONNECTION_POINT"]:
        try:
            c.execute(f"SELECT MAX(FID) FROM {tbl}")
            v = c.fetchone()[0]
            if v and v > max_fid:
                max_fid = v
        except sqlite3.Error:
            pass
    return max_fid


def get_columns(conn, table):
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in c.fetchall()]


def get_pipe_dims(conn):
    """Build a dict: nominal_diameter -> (outer_diameter, wall_thickness)
    from pipe connection points."""
    c = conn.cursor()
    dims = {}
    try:
        c.execute("""SELECT DISTINCT cp.NOMINAL_DIAMETER, cp.OUTER_DIAMETER, cp.WALL_THICKNESS
                     FROM WA_CONNECTION_POINT cp
                     JOIN WA_PIPE_MODEL p ON cp.PID = p.PID
                     ORDER BY cp.NOMINAL_DIAMETER""")
        for nom, od, wt in c.fetchall():
            if nom not in dims:
                dims[nom] = (od, wt)
    except sqlite3.Error:
        pass
    return dims


def get_fitting_dims(conn):
    """Build a dict from fitting connection points for reference."""
    c = conn.cursor()
    dims = {}
    for tbl in FITTING_TABLES:
        try:
            c.execute(f"""SELECT DISTINCT cp.NOMINAL_DIAMETER, cp.OUTER_DIAMETER, cp.WALL_THICKNESS
                         FROM WA_CONNECTION_POINT cp
                         JOIN {tbl} t ON cp.PID = t.PID
                         ORDER BY cp.NOMINAL_DIAMETER""")
            for nom, od, wt in c.fetchall():
                if nom not in dims:
                    dims[nom] = (od, wt)
        except sqlite3.Error:
            pass
    return dims


def extract_nom_diams(dn_str):
    """Extract numeric diameters from strings like '24 in x 24 in' or '24'."""
    if not dn_str:
        return []
    import re
    parts = re.split(r'\s*x\s*', str(dn_str))
    result = []
    for p in parts:
        m = re.search(r'([\d.]+)', p.strip())
        if m:
            result.append(float(m.group(1)))
    return result


def find_closest_existing_size(conn, table, family_name, target_diam):
    """Find the existing record in a family whose nominal diameter is closest
    to the target. Returns the row as a dict, or None."""
    c = conn.cursor()
    cols = get_columns(conn, table)
    c.execute(f"SELECT * FROM {table} WHERE PART_FAMILY_NAME = ?", (family_name,))
    rows = c.fetchall()
    if not rows:
        return None, None

    best_row = None
    best_dist = float('inf')
    best_main_diam = None

    for row in rows:
        row_dict = dict(zip(cols, row))
        diams = extract_nom_diams(row_dict.get('DIAMETER_NOMINAL', ''))
        if not diams:
            continue
        main_diam = diams[0]
        dist = abs(main_diam - target_diam)
        if dist < best_dist:
            best_dist = dist
            best_row = row_dict
            best_main_diam = main_diam

    return best_row, best_main_diam


def scale_position(pos, old_diam, new_diam):
    """Scale a connection point position proportionally."""
    if old_diam == 0:
        return pos
    return pos * (new_diam / old_diam)


def make_dn_string(diams, use_in_suffix):
    """Create DIAMETER_NOMINAL string from a list of diameters."""
    def fmt(d):
        if d == int(d):
            s = str(int(d))
        else:
            s = str(d)
        return f"{s} in" if use_in_suffix else s
    return " x ".join(fmt(d) for d in diams)


def detect_dn_format(conn, table, family_name):
    """Detect whether the family uses 'N in x N in' or just 'N' format."""
    c = conn.cursor()
    c.execute(f"SELECT DIAMETER_NOMINAL FROM {table} WHERE PART_FAMILY_NAME = ? LIMIT 1",
              (family_name,))
    row = c.fetchone()
    if row and row[0]:
        return " in" in str(row[0])
    return False


def create_fitting_for_size(conn, table, family_name, target_diam, pipe_dims,
                            fitting_dims, fid_counter, dry_run=False):
    """Create a new fitting record for target_diam by cloning and scaling
    the closest existing record in the same family.
    Returns (new_fid_counter, records_created)."""
    template, template_diam = find_closest_existing_size(conn, table, family_name, target_diam)
    if template is None:
        return fid_counter, 0

    c = conn.cursor()
    cols = get_columns(conn, table)
    cp_cols = get_columns(conn, "WA_CONNECTION_POINT")
    use_in = detect_dn_format(conn, table, family_name)

    # Get template's connection points
    c.execute("SELECT * FROM WA_CONNECTION_POINT WHERE PID = ?", (template['PID'],))
    template_cps = [dict(zip(cp_cols, row)) for row in c.fetchall()]

    if not template_cps:
        return fid_counter, 0

    # Determine how many diameter slots the DIAMETER_NOMINAL has
    template_diams = extract_nom_diams(template.get('DIAMETER_NOMINAL', ''))
    n_diams = len(template_diams)

    # Build new diameter list: all slots get target_diam (for non-reducing fittings)
    new_diams = [target_diam] * n_diams

    new_dn = make_dn_string(new_diams, use_in)

    # Check if this size already exists
    c.execute(f"SELECT COUNT(*) FROM {table} WHERE PART_FAMILY_NAME = ? AND DIAMETER_NOMINAL = ?",
              (family_name, new_dn))
    if c.fetchone()[0] > 0:
        return fid_counter, 0

    # Generate new IDs
    new_pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{family_name}|{new_dn}|{table}"))
    fid_counter += 1
    new_fid = fid_counter

    # Build new fitting description
    old_desc = template.get('DESCRIPTION', '')
    # Replace the old diameter reference with new one
    import re
    if use_in:
        desc = re.sub(r'\d+(?:\.\d+)?\s*in(?:\s*x\s*\d+(?:\.\d+)?\s*in)*',
                      new_dn.replace(' x ', ' x '), old_desc, count=1)
    else:
        # For Steel: description format like "2-Piece Elbow 12.5_ 24_ BV..."
        # Replace the size number
        parts = old_desc.split('_ ')
        for i, p in enumerate(parts):
            try:
                v = float(p.strip())
                if abs(v - template_diam) < 0.1:
                    parts[i] = str(int(target_diam)) if target_diam == int(target_diam) else str(target_diam)
                    break
            except ValueError:
                # Also try "NNin ND" pattern for HDPE
                m = re.match(r'(\d+(?:\.\d+)?)in\s+ND', p.strip())
                if m and abs(float(m.group(1)) - template_diam) < 0.1:
                    nd_str = str(target_diam) if target_diam != int(target_diam) else str(int(target_diam))
                    parts[i] = f"{nd_str}in ND"
                    break
        desc = '_ '.join(parts)
        if desc == old_desc:
            # Fallback: just append new size
            desc = old_desc.replace(str(int(template_diam)) if template_diam == int(template_diam) else str(template_diam),
                                     str(int(target_diam)) if target_diam == int(target_diam) else str(target_diam),
                                     1)

    # Look up outer_diameter and wall_thickness for new size
    od_new = target_diam  # default: nom = outer for steel
    wt_new = None
    if target_diam in pipe_dims:
        od_new, wt_new = pipe_dims[target_diam]
    elif target_diam in fitting_dims:
        od_new, wt_new = fitting_dims[target_diam]
    else:
        # Interpolate from template
        if template_diam and template_diam > 0:
            ratio = target_diam / template_diam
            t_cp = template_cps[0]
            if t_cp.get('OUTER_DIAMETER'):
                od_new = t_cp['OUTER_DIAMETER'] * ratio
            if t_cp.get('WALL_THICKNESS'):
                wt_new = t_cp['WALL_THICKNESS'] * ratio

    # Build new record
    new_row = dict(template)
    new_row['FID'] = new_fid
    new_row['DIAMETER_NOMINAL'] = new_dn
    new_row['DESCRIPTION'] = desc
    new_row['PID'] = new_pid

    if dry_run:
        print(f"    [DRY] {table}: {desc}")
        return fid_counter, 1

    # Insert fitting
    insert_cols = [c for c in cols if c != 'FID']  # FID is auto but we set it
    insert_cols_with_fid = ['FID'] + insert_cols
    placeholders = ','.join(['?'] * len(insert_cols_with_fid))
    values = [new_row.get(c) for c in insert_cols_with_fid]
    c.execute(f"INSERT INTO {table} ({','.join(insert_cols_with_fid)}) VALUES ({placeholders})", values)

    # Create connection points
    for tcp in template_cps:
        fid_counter += 1
        new_cp = dict(tcp)
        new_cp['FID'] = fid_counter
        new_cp['PID'] = new_pid
        new_cp['NOMINAL_DIAMETER'] = target_diam
        new_cp['OUTER_DIAMETER'] = od_new
        new_cp['WALL_THICKNESS'] = wt_new

        # Scale positions proportionally
        if template_diam and template_diam > 0:
            ratio = target_diam / template_diam
            for coord in ('POSITION_3D_X', 'POSITION_3D_Y', 'POSITION_3D_Z'):
                if new_cp.get(coord) is not None:
                    new_cp[coord] = tcp[coord] * ratio
            if new_cp.get('ENGAGEMENT_LENGTH') is not None and tcp.get('ENGAGEMENT_LENGTH'):
                new_cp['ENGAGEMENT_LENGTH'] = tcp['ENGAGEMENT_LENGTH'] * ratio

        cp_insert_cols = ['FID'] + [c for c in cp_cols if c != 'FID']
        cp_placeholders = ','.join(['?'] * len(cp_insert_cols))
        cp_values = [new_cp.get(c) for c in cp_insert_cols]
        c.execute(f"INSERT INTO WA_CONNECTION_POINT ({','.join(cp_insert_cols)}) VALUES ({cp_placeholders})",
                  cp_values)

    return fid_counter, 1


def get_existing_diams(conn, table, family_name):
    """Get set of nominal diameters already present in a family."""
    c = conn.cursor()
    c.execute(f"SELECT DIAMETER_NOMINAL FROM {table} WHERE PART_FAMILY_NAME = ?", (family_name,))
    diams = set()
    for (dn,) in c.fetchall():
        for d in extract_nom_diams(dn):
            diams.add(d)
    return diams


def get_pipe_diams(conn):
    """Get all nominal diameters from the pipe table."""
    c = conn.cursor()
    diams = set()
    try:
        c.execute("SELECT DISTINCT DIAMETER_NOMINAL FROM WA_PIPE_MODEL")
        for (dn,) in c.fetchall():
            for d in extract_nom_diams(dn):
                diams.add(d)
    except sqlite3.Error:
        pass
    return diams


def process_catalog(db_name, missing_diams=None, dry_run=False):
    """Process one SQLite catalog, filling gaps for all fitting families."""
    db_path = os.path.join(CATALOG_ROOT, db_name)
    if not os.path.isfile(db_path):
        print(f"  ERROR: {db_path} not found")
        return

    print(f"\n{'='*60}")
    print(f"Procesando: {db_name}")
    print(f"{'='*60}")

    if not dry_run:
        backup_db(db_path)

    conn = sqlite3.connect(db_path)
    fid_counter = get_max_fid(conn) + 100  # Leave gap for safety

    pipe_dims = get_pipe_dims(conn)
    fitting_dims = get_fitting_dims(conn)
    pipe_diams = get_pipe_diams(conn)

    if missing_diams is None:
        # Auto-detect: pipe diams that lack fittings
        all_fitting_diams = set()
        c = conn.cursor()
        for tbl in FITTING_TABLES:
            try:
                c.execute(f"SELECT DIAMETER_NOMINAL FROM {tbl}")
                for (dn,) in c.fetchall():
                    for d in extract_nom_diams(dn):
                        all_fitting_diams.add(d)
            except sqlite3.Error:
                pass
        missing_diams = sorted(pipe_diams - all_fitting_diams)
        if not missing_diams:
            print("  No hay gaps - todos los diámetros de tubo tienen accesorios")
            conn.close()
            return

    print(f"  Diámetros faltantes: {missing_diams}")
    total_created = 0

    for tbl in FITTING_TABLES:
        c = conn.cursor()
        try:
            c.execute(f"SELECT DISTINCT PART_FAMILY_NAME FROM {tbl} ORDER BY PART_FAMILY_NAME")
            families = [r[0] for r in c.fetchall()]
        except sqlite3.Error:
            continue

        if not families:
            continue

        tbl_created = 0
        for fam in families:
            existing = get_existing_diams(conn, tbl, fam)
            for diam in missing_diams:
                if diam in existing:
                    continue
                fid_counter, n = create_fitting_for_size(
                    conn, tbl, fam, diam, pipe_dims, fitting_dims,
                    fid_counter, dry_run=dry_run
                )
                tbl_created += n

        if tbl_created > 0:
            print(f"  {tbl}: {tbl_created} registros {'(dry run)' if dry_run else 'creados'}")
            total_created += tbl_created

    if not dry_run and total_created > 0:
        conn.commit()
    conn.close()
    print(f"  TOTAL: {total_created} registros {'(dry run)' if dry_run else 'insertados'}")


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=== MODO DRY RUN - no se modifica nada ===\n")
    else:
        print("=== MODO ESCRITURA - se modificarán los catálogos ===\n")

    # 1. Flanged: gaps at 30, 36, 42, 48, 54, 60, 64
    process_catalog("Imperial_AWWA_Flanged.sqlite",
                    missing_diams=[30, 36, 42, 48, 54, 60, 64],
                    dry_run=dry_run)

    # 2. Steel: gaps at 26, 28, 32, 34, 38, 40, 44, 46, 50, 52
    process_catalog("Imperial_AWWA_Steel.sqlite",
                    missing_diams=[26, 28, 32, 34, 38, 40, 44, 46, 50, 52],
                    dry_run=dry_run)

    # 3. HDPE: gaps at 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5
    process_catalog("Imperial_AWWA_HDPE.sqlite",
                    missing_diams=[0.5, 0.75, 1, 1.25, 1.5, 2, 2.5],
                    dry_run=dry_run)

    print("\n" + "="*60)
    if dry_run:
        print("Dry run completado. Ejecuta sin --dry-run para aplicar cambios.")
    else:
        print("Catálogos actualizados. Abre Civil 3D para verificar.")


if __name__ == "__main__":
    main()
