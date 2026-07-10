"""
excel_import.py — Lector de los Excel de red del cliente (openpyxl).

Encabezados en la FILA 5, datos debajo. Cada hoja es una red (o parte de una):
  BUZONES : X, Y, Z, C. SOLERA, Cod, Tipo Bz
  TUBERIAS: Cod. Tub ("NOMBRE_A - NOMBRE_B"), Xi, Yi, Zi, Xf, Yf, Zf, Altura, Tipo Tub

read_network_workbook(path) -> (networks, warnings)
  networks: dict ordenado  nombre_red -> {"structures": [...], "pipes": [...]}
    structure = {cod, x, y, rim, sump, part}
    pipe      = {id, from, to, xi, yi, zi, xf, yf, zf, diam, part}
Las coordenadas son REALES de mundo (no píxeles).
"""
import re
from collections import OrderedDict

HEADER_ROW = 5


def _norm(h):
    """Normaliza un encabezado: sin puntos ni espacios, en mayúsculas."""
    return re.sub(r"[.\s]+", "", str(h or "").strip().upper())


def _net_name(sheet_title):
    s = sheet_title or ""
    for tok in ("BUZONES", "BUZON", "TUBERIAS", "TUBERIA"):
        s = re.sub(tok, "", s, flags=re.I)
    s = s.strip(" _-").replace("  ", " ").strip()
    return s or (sheet_title or "Red")


def _fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_network_workbook(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    nets = OrderedDict()
    warnings = []

    def net_for(name):
        if name not in nets:
            nets[name] = {"structures": [], "pipes": []}
        return nets[name]

    for ws in wb.worksheets:
        try:
            rows = list(ws.iter_rows(min_row=HEADER_ROW, values_only=True))
        except Exception:
            continue
        if not rows:
            continue
        headers = [_norm(h) for h in rows[0]]
        col = {}
        for idx, h in enumerate(headers):
            if h and h not in col:
                col[h] = idx
        data = rows[1:]

        def val(row, key):
            i = col.get(key)
            return row[i] if (i is not None and i < len(row)) else None

        if "CODTUB" in col:
            kind = "tub"
        elif "COD" in col and ("CSOLERA" in col or "TIPOBZ" in col):
            kind = "buz"
        else:
            continue                                   # hoja que no es de red: se ignora

        name = _net_name(ws.title)
        net = net_for(name)
        if kind == "buz":
            for row in data:
                cod = val(row, "COD")
                if cod is None or str(cod).strip() == "":
                    continue
                net["structures"].append({
                    "cod": str(cod).strip(),
                    "x": _fnum(val(row, "X")), "y": _fnum(val(row, "Y")),
                    "rim": _fnum(val(row, "Z")), "sump": _fnum(val(row, "CSOLERA")),
                    "part": (str(val(row, "TIPOBZ")).strip() if val(row, "TIPOBZ") is not None else ""),
                })
        else:
            for row in data:
                codtub = val(row, "CODTUB")
                if codtub is None or str(codtub).strip() == "":
                    continue
                codtub = str(codtub).strip()
                parts = re.split(r"\s+-\s+", codtub, maxsplit=1)     # separador " - " (los codes llevan '-' interno)
                frm = parts[0].strip() if parts else ""
                to = parts[1].strip() if len(parts) > 1 else ""
                net["pipes"].append({
                    "id": codtub, "from": frm, "to": to,
                    "xi": _fnum(val(row, "XI")), "yi": _fnum(val(row, "YI")), "zi": _fnum(val(row, "ZI")),
                    "xf": _fnum(val(row, "XF")), "yf": _fnum(val(row, "YF")), "zf": _fnum(val(row, "ZF")),
                    "diam": _fnum(val(row, "ALTURA")),
                    "part": (str(val(row, "TIPOTUB")).strip() if val(row, "TIPOTUB") is not None else ""),
                })

    try: wb.close()
    except Exception: pass
    if not nets:
        warnings.append("No se encontraron hojas de BUZONES/TUBERIAS con encabezados en la fila 5.")
    return nets, warnings
