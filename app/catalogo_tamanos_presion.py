"""Agregar un tamaño a una familia de PRESIÓN (catálogo SQLite de Civil 3D).

Parte de `catalogo_tamanos` (PURO: sin Qt): se clona el tubo más cercano de la
familia (WA_PIPE_MODEL + sus WA_CONNECTION_POINT) y se crean los accesorios de
ese diámetro que falten (mismo algoritmo que scripts/fill_pressure_catalog_gaps.py).
Los PID nuevos son UUID v5 de «familia|DN|tabla»: repetir no duplica."""
from __future__ import annotations

import math
import re
import sqlite3
import uuid

TOL = 1e-4


def _fmt(x):
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s or "0"

_TABLAS_ACC = ("WA_ELBOW_MODEL", "WA_BRANCH_FITTING_MODEL", "WA_FITTING_MODEL")


def _diam_dn(dn):
    m = re.search(r"(\d+(?:\.\d+)?)", str(dn or ""))
    return float(m.group(1)) if m else None


def _cols(conn, tabla):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")]


def _filas_presion(db, fam):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cols = _cols(conn, "WA_PIPE_MODEL")
        filas = [dict(zip(cols, r)) for r in conn.execute(
            "SELECT * FROM WA_PIPE_MODEL WHERE PART_FAMILY_NAME=?", (fam,))]
    finally:
        conn.close()
    filas.sort(key=lambda r: _diam_dn(r["DIAMETER_NOMINAL"]) or 0)
    return filas


def _dn_como(plantilla, d):
    """«10 in x 10 in» / «10 in» / «10» con el número nuevo."""
    s = _fmt(d)
    p = str(plantilla or "")
    n = len(re.findall(r"\d+(?:\.\d+)?", p)) or 1
    if " in" in p:
        return " x ".join([f"{s} in"] * n)
    return " x ".join([s] * n)


def _desc_como(plantilla, d_viejo, d):
    """La descripción del tamaño más cercano con el diámetro nuevo (la primera
    «N in» es la que lee el plugin, ExtraerDiametroDeDescripcion)."""
    s = _fmt(d)
    nueva, n = re.subn(r"(?<![\d.])\d+(?:[._]\d+)?(\s*)in\b", lambda m: f"{s}{m.group(1)}in", plantilla or "", count=1)
    return nueva if n else f"{s} in {plantilla or ''}".strip()


def _max_fid(conn):
    m = 0
    for (tabla,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if "FID" in _cols(conn, tabla):
            v = conn.execute(f"SELECT MAX(FID) FROM {tabla}").fetchone()[0]
            m = max(m, v or 0)
    return m


def _agregar_presion(db, fam, d, extras):
    conn = sqlite3.connect(db, timeout=2)
    try:
        cols = _cols(conn, "WA_PIPE_MODEL")
        filas = [dict(zip(cols, r)) for r in conn.execute(
            "SELECT * FROM WA_PIPE_MODEL WHERE PART_FAMILY_NAME=?", (fam,))]
        if any(abs((_diam_dn(r["DIAMETER_NOMINAL"]) or -1) - d) < TOL for r in filas):
            return "ya_existia"
        plantilla = min(filas, key=lambda r: abs((_diam_dn(r["DIAMETER_NOMINAL"]) or 0) - d))
        d0 = _diam_dn(plantilla["DIAMETER_NOMINAL"]) or d
        nueva = dict(plantilla)
        nueva["DIAMETER_NOMINAL"] = _dn_como(plantilla["DIAMETER_NOMINAL"], d)
        nueva["DESCRIPTION"] = _desc_como(plantilla.get("DESCRIPTION"), d0, d)
        for k in ("DIAMETER_INSIDE", "DIAMETER_OUTSIDE", "THICKNESS"):
            if extras.get(k) is not None and k in nueva:
                nueva[k] = float(extras[k])
        nueva["PID"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{fam}|{nueva['DIAMETER_NOMINAL']}|WA_PIPE_MODEL"))
        fid = _max_fid(conn) + 100
        nueva["FID"] = fid
        conn.execute(f"INSERT INTO WA_PIPE_MODEL ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                     [nueva.get(c) for c in cols])
        cp_cols = _cols(conn, "WA_CONNECTION_POINT")
        for cp in [dict(zip(cp_cols, r)) for r in conn.execute(
                "SELECT * FROM WA_CONNECTION_POINT WHERE PID=?", (plantilla["PID"],))]:
            fid += 1
            cp.update(FID=fid, PID=nueva["PID"], NOMINAL_DIAMETER=d)
            if cp.get("OUTER_DIAMETER") is not None:
                cp["OUTER_DIAMETER"] = nueva.get("DIAMETER_OUTSIDE") or cp["OUTER_DIAMETER"] * d / d0
            if cp.get("WALL_THICKNESS") is not None:
                cp["WALL_THICKNESS"] = nueva.get("THICKNESS") or cp["WALL_THICKNESS"] * d / d0
            conn.execute(f"INSERT INTO WA_CONNECTION_POINT ({','.join(cp_cols)}) VALUES ({','.join('?' * len(cp_cols))})",
                         [cp.get(c) for c in cp_cols])
        _rellenar_accesorios(conn, d, fid + 100)
        conn.commit()
        return "agregado"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _rellenar_accesorios(conn, d, fid):
    """Codos/Tee/… de diámetro `d` que falten, clonando el más cercano de cada
    familia y escalando (port de scripts/fill_pressure_catalog_gaps.py)."""
    cp_cols = _cols(conn, "WA_CONNECTION_POINT")
    for tabla in _TABLAS_ACC:
        try:
            cols = _cols(conn, tabla)
            familias = [r[0] for r in conn.execute(f"SELECT DISTINCT PART_FAMILY_NAME FROM {tabla}")]
        except sqlite3.Error:
            continue
        for fam in familias:
            filas = [dict(zip(cols, r)) for r in conn.execute(
                f"SELECT * FROM {tabla} WHERE PART_FAMILY_NAME=?", (fam,))]
            con_d = [r for r in filas if _diam_dn(r["DIAMETER_NOMINAL"]) is not None]
            if not con_d or any(abs(_diam_dn(r["DIAMETER_NOMINAL"]) - d) < TOL for r in con_d):
                continue
            pl = min(con_d, key=lambda r: abs(_diam_dn(r["DIAMETER_NOMINAL"]) - d))
            d0 = _diam_dn(pl["DIAMETER_NOMINAL"])
            if not d0:
                continue
            k = d / d0
            nueva = dict(pl)
            nueva["DIAMETER_NOMINAL"] = _dn_como(pl["DIAMETER_NOMINAL"], d)
            nueva["DESCRIPTION"] = _desc_como(pl.get("DESCRIPTION"), d0, d)
            nueva["PID"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{fam}|{nueva['DIAMETER_NOMINAL']}|{tabla}"))
            fid += 1
            nueva["FID"] = fid
            conn.execute(f"INSERT INTO {tabla} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                         [nueva.get(c) for c in cols])
            for cp in [dict(zip(cp_cols, r)) for r in conn.execute(
                    "SELECT * FROM WA_CONNECTION_POINT WHERE PID=?", (pl["PID"],))]:
                fid += 1
                cp.update(FID=fid, PID=nueva["PID"], NOMINAL_DIAMETER=d)
                for c in ("OUTER_DIAMETER", "WALL_THICKNESS", "POSITION_3D_X", "POSITION_3D_Y",
                          "POSITION_3D_Z", "ENGAGEMENT_LENGTH"):
                    if cp.get(c) is not None and not (isinstance(cp[c], float) and math.isnan(cp[c])):
                        cp[c] = cp[c] * k
                conn.execute(f"INSERT INTO WA_CONNECTION_POINT ({','.join(cp_cols)}) VALUES ({','.join('?' * len(cp_cols))})",
                             [cp.get(c) for c in cp_cols])
