"""
network_json.py — Exporta la "red resuelta" al contrato utility-network/2.0.

Una red por hoja/red → un archivo JSON. Datos tomados del modelo de la app
(win.pipes de gravedad + win.structures). Coordenadas:
  - IMPORTADAS de Excel (world=True): reales, se usan tal cual.
  - DIBUJADAS sobre el PDF (world=False): se pasan por win._to_cad(x, y).
    NOTA/LIMITACIÓN: hasta no georreferenciar el PDF, esas X,Y NO coinciden con las
    coordenadas reales del Excel; se exportan igual (documentado).
"""
import json
import math
import os
import re
from collections import OrderedDict

from model import GRAVITY_LAYERS


def _r(v):
    return round(float(v), 4) if isinstance(v, (int, float)) else v


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("_") or "red"


def _nearest_cod(win, netname, px_point, tol=16.0):
    """Cod del buzón dibujado (mismo net) más cercano al punto en píxeles, o ''."""
    best, bd = "", tol
    for s in win.structures:
        if s.get("world"):
            continue
        if (s.get("net") or netname) != netname:
            continue
        sx, sy = s.get("x"), s.get("y")
        if sx is None or sy is None:
            continue
        d = math.hypot(sx - px_point[0], sy - px_point[1])
        if d <= bd:
            bd, best = d, s.get("cod", "")
    return best


def _default_net(win):
    base = os.path.splitext(os.path.basename(win.pdf_path or ""))[0]
    return base or "Red"


def build_networks(win):
    """Agrupa estructuras y tuberías por nombre de red (dict ordenado)."""
    default = _default_net(win)
    nets = OrderedDict()

    def net(name):
        name = name or default
        if name not in nets:
            nets[name] = {"kind": "gravity", "structs": OrderedDict(), "pipes": []}
        return nets[name]

    for s in win.structures:
        nm = s.get("net") or default
        if s.get("world"):
            x, y = s.get("x"), s.get("y")
        else:
            if s.get("x") is None or s.get("y") is None:
                continue
            x, y = win._to_cad(s["x"], s["y"])
        net(nm)["structs"][s.get("cod", "")] = {
            "id": s.get("cod", ""), "part": s.get("part", ""),
            "x": _r(x), "y": _r(y), "rim": s.get("rim"), "sump": s.get("sump"),
        }

    for p in win.pipes:
        if p.get("layer") not in GRAVITY_LAYERS:
            continue
        nm = p.get("net") or default
        if p.get("world"):
            ws, we = p.get("wstart"), p.get("wend")
            if not ws or not we:
                continue
            (sx, sy), (ex, ey) = ws, we
            frm, to = p.get("from", ""), p.get("to", "")
        else:
            pts = p.get("pts")
            if not pts or len(pts) < 2:
                continue
            sx, sy = win._to_cad(*pts[0]); ex, ey = win._to_cad(*pts[-1])
            frm = p.get("from") or _nearest_cod(win, nm, pts[0])
            to = p.get("to") or _nearest_cod(win, nm, pts[-1])
        pid = p.get("id") or (f"{frm} - {to}" if (frm or to) else (p.get("name") or "tramo"))
        net(nm)["pipes"].append({
            "id": pid, "part": p.get("part", ""), "from": frm, "to": to,
            "start": {"x": _r(sx), "y": _r(sy), "invert": p.get("inv_start")},
            "end": {"x": _r(ex), "y": _r(ey), "invert": p.get("inv_end")},
        })

    return nets


def validate(name, structs, pipes):
    w = []
    for st in structs.values():
        if st["rim"] is None or st["sump"] is None:
            w.append(f"[{name}] buzón '{st['id']}' sin rim o sump.")
        elif st["sump"] > st["rim"]:
            w.append(f"[{name}] buzón '{st['id']}': sump ({st['sump']}) > rim ({st['rim']}).")
    for pp in pipes:
        for end in ("from", "to"):
            cod = pp[end]
            if cod and cod not in structs:
                w.append(f"[{name}] tubería '{pp['id']}' referencia un buzón inexistente: '{cod}'.")
    return w


def write_network_json(win, out_base):
    """Escribe un JSON por red junto a `out_base`. Devuelve (paths, warnings)."""
    nets = build_networks(win)
    stem = os.path.splitext(out_base)[0]
    paths, warnings = [], []
    if not nets:
        return paths, ["No hay tuberías de gravedad ni buzones que exportar."]
    for name, nd in nets.items():
        structs, pipes = nd["structs"], nd["pipes"]
        warnings += validate(name, structs, pipes)
        data = {
            "schema": "utility-network/2.0",
            "units": "m",
            "network_name": name,
            "network_kind": nd["kind"],
            "structures": [{"id": s["id"], "part": s["part"], "x": s["x"], "y": s["y"],
                            "rim": s["rim"], "sump": s["sump"]} for s in structs.values()],
            "pipes": pipes,
        }
        path = f"{stem}.{_safe(name)}.network.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        paths.append(path)
    return paths, warnings
