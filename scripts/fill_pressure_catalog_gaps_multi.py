"""
fill_pressure_catalog_gaps_multi.py
Versión parametrizada: recibe la ruta raíz del catálogo por argumento y procesa
TODOS los .sqlite que tengan gaps (auto-detección).

Uso:
  python fill_pressure_catalog_gaps_multi.py <catalog_root> [--dry-run]

Ejemplo:
  python fill_pressure_catalog_gaps_multi.py "C:\ProgramData\Autodesk\C3D 2024\enu\Pressure Pipes Catalog\Imperial"
  python fill_pressure_catalog_gaps_multi.py "C:\ProgramData\Autodesk\C3D 2025\enu\Pressure Pipes Catalog\Metric"
"""
import sqlite3
import shutil
import os
import uuid
import re
import sys
import glob
from datetime import datetime

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
    max_fid = 0
    for tbl in FITTING_TABLES + ["WA_CONNECTION_POINT"]:
        try:
            v = conn.execute(f"SELECT MAX(FID) FROM {tbl}").fetchone()[0]
            if v and v > max_fid:
                max_fid = v
        except sqlite3.Error:
            pass
    return max_fid


def get_columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def get_pipe_dims(conn):
    dims = {}
    try:
        for nom, od, wt in conn.execute(
            """SELECT DISTINCT cp.NOMINAL_DIAMETER, cp.OUTER_DIAMETER, cp.WALL_THICKNESS
               FROM WA_CONNECTION_POINT cp
               JOIN WA_PIPE_MODEL p ON cp.PID = p.PID
               ORDER BY cp.NOMINAL_DIAMETER"""):
            if nom not in dims:
                dims[nom] = (od, wt)
    except sqlite3.Error:
        pass
    return dims


def get_fitting_dims(conn):
    dims = {}
    for tbl in FITTING_TABLES:
        try:
            for nom, od, wt in conn.execute(
                f"""SELECT DISTINCT cp.NOMINAL_DIAMETER, cp.OUTER_DIAMETER, cp.WALL_THICKNESS
                    FROM WA_CONNECTION_POINT cp
                    JOIN {tbl} t ON cp.PID = t.PID
                    ORDER BY cp.NOMINAL_DIAMETER"""):
                if nom not in dims:
                    dims[nom] = (od, wt)
        except sqlite3.Error:
            pass
    return dims


def extract_nom_diams(dn_str):
    if not dn_str:
        return []
    parts = re.split(r'\s*x\s*', str(dn_str))
    result = []
    for p in parts:
        m = re.search(r'([\d.]+)', p.strip())
        if m:
            result.append(float(m.group(1)))
    return result


def find_closest_existing_size(conn, table, family_name, target_diam):
    cols = get_columns(conn, table)
    rows = conn.execute(f"SELECT * FROM {table} WHERE PART_FAMILY_NAME = ?", (family_name,)).fetchall()
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


def make_dn_string(diams, use_in_suffix):
    def fmt(d):
        s = str(int(d)) if d == int(d) else str(d)
        return f"{s} in" if use_in_suffix else s
    return " x ".join(fmt(d) for d in diams)


def detect_dn_format(conn, table, family_name):
    row = conn.execute(
        f"SELECT DIAMETER_NOMINAL FROM {table} WHERE PART_FAMILY_NAME = ? LIMIT 1",
        (family_name,)).fetchone()
    if row and row[0]:
        return " in" in str(row[0])
    return False


def create_fitting_for_size(conn, table, family_name, target_diam, pipe_dims,
                            fitting_dims, fid_counter, dry_run=False):
    template, template_diam = find_closest_existing_size(conn, table, family_name, target_diam)
    if template is None:
        return fid_counter, 0

    cols = get_columns(conn, table)
    cp_cols = get_columns(conn, "WA_CONNECTION_POINT")
    use_in = detect_dn_format(conn, table, family_name)

    template_cps = [dict(zip(cp_cols, row)) for row in
                    conn.execute("SELECT * FROM WA_CONNECTION_POINT WHERE PID = ?",
                                 (template['PID'],)).fetchall()]
    if not template_cps:
        return fid_counter, 0

    template_diams = extract_nom_diams(template.get('DIAMETER_NOMINAL', ''))
    n_diams = len(template_diams)
    new_diams = [target_diam] * n_diams
    new_dn = make_dn_string(new_diams, use_in)

    if conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE PART_FAMILY_NAME = ? AND DIAMETER_NOMINAL = ?",
        (family_name, new_dn)).fetchone()[0] > 0:
        return fid_counter, 0

    new_pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{family_name}|{new_dn}|{table}"))
    fid_counter += 1
    new_fid = fid_counter

    old_desc = template.get('DESCRIPTION', '')
    if use_in:
        desc = re.sub(r'\d+(?:\.\d+)?\s*in(?:\s*x\s*\d+(?:\.\d+)?\s*in)*',
                      new_dn.replace(' x ', ' x '), old_desc, count=1)
    else:
        parts_d = old_desc.split('_ ')
        for i, p in enumerate(parts_d):
            try:
                v = float(p.strip())
                if abs(v - template_diam) < 0.1:
                    parts_d[i] = str(int(target_diam)) if target_diam == int(target_diam) else str(target_diam)
                    break
            except ValueError:
                m = re.match(r'(\d+(?:\.\d+)?)in\s+ND', p.strip())
                if m and abs(float(m.group(1)) - template_diam) < 0.1:
                    nd_str = str(target_diam) if target_diam != int(target_diam) else str(int(target_diam))
                    parts_d[i] = f"{nd_str}in ND"
                    break
        desc = '_ '.join(parts_d)
        if desc == old_desc:
            td_str = str(int(template_diam)) if template_diam == int(template_diam) else str(template_diam)
            nd_str = str(int(target_diam)) if target_diam == int(target_diam) else str(target_diam)
            desc = old_desc.replace(td_str, nd_str, 1)

    od_new = target_diam
    wt_new = None
    if target_diam in pipe_dims:
        od_new, wt_new = pipe_dims[target_diam]
    elif target_diam in fitting_dims:
        od_new, wt_new = fitting_dims[target_diam]
    elif template_diam and template_diam > 0:
        ratio = target_diam / template_diam
        t_cp = template_cps[0]
        if t_cp.get('OUTER_DIAMETER'):
            od_new = t_cp['OUTER_DIAMETER'] * ratio
        if t_cp.get('WALL_THICKNESS'):
            wt_new = t_cp['WALL_THICKNESS'] * ratio

    new_row = dict(template)
    new_row['FID'] = new_fid
    new_row['DIAMETER_NOMINAL'] = new_dn
    new_row['DESCRIPTION'] = desc
    new_row['PID'] = new_pid

    if dry_run:
        print(f"    [DRY] {table}: {desc}")
        return fid_counter, 1

    insert_cols_with_fid = ['FID'] + [c for c in cols if c != 'FID']
    placeholders = ','.join(['?'] * len(insert_cols_with_fid))
    values = [new_row.get(c) for c in insert_cols_with_fid]
    conn.execute(f"INSERT INTO {table} ({','.join(insert_cols_with_fid)}) VALUES ({placeholders})", values)

    for tcp in template_cps:
        fid_counter += 1
        new_cp = dict(tcp)
        new_cp['FID'] = fid_counter
        new_cp['PID'] = new_pid
        new_cp['NOMINAL_DIAMETER'] = target_diam
        new_cp['OUTER_DIAMETER'] = od_new
        new_cp['WALL_THICKNESS'] = wt_new
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
        conn.execute(f"INSERT INTO WA_CONNECTION_POINT ({','.join(cp_insert_cols)}) VALUES ({cp_placeholders})",
                     cp_values)

    return fid_counter, 1


def get_existing_diams(conn, table, family_name):
    diams = set()
    for (dn,) in conn.execute(
        f"SELECT DIAMETER_NOMINAL FROM {table} WHERE PART_FAMILY_NAME = ?", (family_name,)).fetchall():
        for d in extract_nom_diams(dn):
            diams.add(d)
    return diams


def get_pipe_diams(conn):
    diams = set()
    try:
        for (dn,) in conn.execute("SELECT DISTINCT DIAMETER_NOMINAL FROM WA_PIPE_MODEL").fetchall():
            for d in extract_nom_diams(dn):
                diams.add(d)
    except sqlite3.Error:
        pass
    return diams


def process_catalog(db_path, dry_run=False):
    if not os.path.isfile(db_path):
        print(f"  ERROR: {db_path} not found")
        return 0

    name = os.path.basename(db_path)
    conn = sqlite3.connect(db_path)

    pipe_diams = get_pipe_diams(conn)
    all_fitting_diams = set()
    for tbl in FITTING_TABLES:
        try:
            for (dn,) in conn.execute(f"SELECT DIAMETER_NOMINAL FROM {tbl}").fetchall():
                for d in extract_nom_diams(dn):
                    all_fitting_diams.add(d)
        except sqlite3.Error:
            pass

    missing_diams = sorted(pipe_diams - all_fitting_diams)
    if not missing_diams:
        conn.close()
        return 0

    print(f"\n{'='*60}")
    print(f"Procesando: {name}")
    print(f"  Gaps: {missing_diams}")
    print(f"{'='*60}")

    if not dry_run:
        backup_db(db_path)

    fid_counter = get_max_fid(conn) + 100
    pipe_dims = get_pipe_dims(conn)
    fitting_dims = get_fitting_dims(conn)
    total_created = 0

    for tbl in FITTING_TABLES:
        try:
            families = [r[0] for r in conn.execute(
                f"SELECT DISTINCT PART_FAMILY_NAME FROM {tbl} ORDER BY PART_FAMILY_NAME").fetchall()]
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
                    fid_counter, dry_run=dry_run)
                tbl_created += n

        if tbl_created > 0:
            print(f"  {tbl}: {tbl_created} registros {'(dry run)' if dry_run else 'creados'}")
            total_created += tbl_created

    if not dry_run and total_created > 0:
        conn.commit()
    conn.close()
    print(f"  TOTAL: {total_created} registros {'(dry run)' if dry_run else 'insertados'}")
    return total_created


def main():
    if len(sys.argv) < 2:
        print("Uso: python fill_pressure_catalog_gaps_multi.py <catalog_root> [--dry-run]")
        sys.exit(1)

    catalog_root = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if not os.path.isdir(catalog_root):
        print(f"ERROR: No existe el directorio {catalog_root}")
        sys.exit(1)

    if dry_run:
        print("=== MODO DRY RUN - no se modifica nada ===\n")
    else:
        print("=== MODO ESCRITURA - se modificarán los catálogos ===\n")

    print(f"Raíz: {catalog_root}")
    sqlite_files = sorted(glob.glob(os.path.join(catalog_root, "*.sqlite")))
    print(f"Catálogos encontrados: {len(sqlite_files)}")

    grand_total = 0
    processed = 0
    for db_path in sqlite_files:
        n = process_catalog(db_path, dry_run=dry_run)
        if n > 0:
            processed += 1
            grand_total += n

    print(f"\n{'='*60}")
    print(f"Resumen: {processed} catálogos procesados, {grand_total} registros totales")
    if dry_run:
        print("Ejecuta sin --dry-run para aplicar cambios.")
    else:
        print("Catálogos actualizados.")


if __name__ == "__main__":
    main()
