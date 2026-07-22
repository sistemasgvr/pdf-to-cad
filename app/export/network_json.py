"""
network_json.py — Exporta la red al contrato utility-network/3.0.

¿Qué es este archivo? Cuando terminas de marcar el plano, este módulo escribe
un archivo .json (formato JSON, texto plano legible) con la RED completa
(tuberías y buzones) para que otra herramienta (p. ej. un plugin de Civil 3D
en C#) reconstruya el modelo 3D. El archivo NO reemplaza al DXF; es un
"gemelo" con los datos de red bien estructurados.

UNIDAD (obligatoria, ft o in): la unidad del proyecto (`win.work_unit`) se
escribe en `"units"` del JSON y TODAS las coordenadas, cotas y diámetros
salen en esa unidad. Nunca en metros.

Salida ÚNICA en un solo archivo JSON, con array `networks[]` agrupado por
(capa, nombre de red). Nunca mezcla capas: agua y drenaje van en redes
distintas.

Reglas:
  • kind por capa (nivel de red): gravity | pressure | conduit.
  • `has_structures=true` solo para gravity; en pressure/conduit → structures=[]
    y `from/to` = null en cada tramo.
  • Polilínea de N vértices → N−1 tramos consecutivos (NO se colapsa).
  • En redes por gravedad, cada vértice compartido entre tramos es una
    estructura (dedup por coordenada con tolerancia). Se autonumeran BZ-1,
    BZ-2… salvo que el usuario haya asignado un código en el panel Buzones.
  • `diameter` siempre presente {value, unit} tal cual lo maneja el usuario.
  • `material`, `part`, `network_type` y `color` viajan por CADA tramo:
      - material: texto libre del usuario (p. ej. "HDPE Corrugado"); null si no
      - part: nombre de la pieza (p. ej. "900 mm HDPE"); null si no
      - color: {aci, name} heredado de la capa (índice ACI de AutoCAD + nombre)
      - network_type: "pipe" (con buzones) o "pressure" (línea a presión); se
        toma del panel Propiedades si el usuario lo forzó, si no del default
        de la capa (agua/gas → pressure; el resto → pipe).
  • Cotas (rim/sump por buzón, invert por extremo): del usuario o null; no se
    inventan.

Coordenadas: TODAS pasan por win._to_cad (compuerta única a mundo). Con
georreferencia activa son UTM reales; sin ella siguen la escala del titleblock
y NO coinciden con datos UTM externos hasta calzar el plano.
"""
import json
import math
from collections import OrderedDict

from model import network_kind, default_network_type, layer_color_info
from geometry import convert_length


def _f(v):
    """Serializa a float redondeado (Python float) o None."""
    if v is None: return None
    try: return round(float(v), 4)
    except (TypeError, ValueError): return None


def _project_xy(win, x_px, y_px):
    """Convierte un punto (píxel de la vista) a coordenada de mundo en la unidad
    del proyecto (ft o in). El paso intermedio:
      1) win._to_cad devuelve METROS (si hay georreferencia) o PIES (si no).
      2) Convertimos ese resultado a win.work_unit ('ft' o 'in')."""
    xw, yw = win._to_cad(x_px, y_px)
    src = "m" if win.georef.active() else "ft"
    return (convert_length(xw, src, win.work_unit),
            convert_length(yw, src, win.work_unit))


def _clean(s):
    """Cadena no vacía o None."""
    if s is None: return None
    s = str(s).strip()
    return s or None


def _find_user_struct(win, pipe_is_world, pt_native):
    """Estructura del usuario que coincide con este extremo:
    dibujado→ coincide en píxeles (tol 14 px); importado→ en mundo (tol 0.5 m)."""
    if pipe_is_world:
        for s in win.structures:
            if not s.get("world"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if math.hypot(sx - pt_native[0], sy - pt_native[1]) <= 0.5:
                return s
    else:
        for s in win.structures:
            if s.get("world"): continue
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if math.hypot(sx - pt_native[0], sy - pt_native[1]) <= 14.0:
                return s
    return None


def _network_key(p):
    return (p["layer"], p.get("net") or "")


def build_networks(win):
    """Agrupa `win.pipes` por (layer, net); cada polilínea N-vért → N−1 tramos."""
    groups = OrderedDict()
    warnings = []
    for p in win.pipes:
        # descarta pipes sin geometría útil
        if not p.get("pts") and not (p.get("world") and p.get("wstart") and p.get("wend")):
            continue
        groups.setdefault(_network_key(p), []).append(p)
        # Validaciones previas basadas en el modelo interno:
        name = p.get("name") or p.get("id") or f"({p.get('layer')})"
        has_s = p.get("inv_start") not in (None, "")
        has_e = p.get("inv_end") not in (None, "")
        if has_s and not has_e:
            warnings.append(f"[{name}] tiene invert de INICIO pero no de FIN.")
        elif has_e and not has_s:
            warnings.append(f"[{name}] tiene invert de FIN pero no de INICIO.")
        # Utilidad de presión (por su capa) marcada como gravedad ("pipe") por el usuario.
        if network_kind(p["layer"]) == "pressure" and _clean(p.get("net_type")) == "pipe":
            warnings.append(f"[{name}] es una capa a presión ({p['layer']}) marcada como red con buzones (pipe).")
    networks = []
    layer_counter = {}          # layer → cuántas redes auto-numeradas llevamos

    for (layer, net), pipes in groups.items():
        kind = network_kind(layer)
        if kind == "unknown":
            kind = "conduit"
        has_structures = (kind == "gravity")

        if net:
            name = f"{layer}-{net}"
        else:
            layer_counter[layer] = layer_counter.get(layer, 0) + 1
            name = f"{layer}-{layer_counter[layer]}"

        struct_map = OrderedDict()   # id → {id, part, x, y, rim, sump, _key, _auto}
        pipe_out = []
        pipe_ctr = 0
        auto_bz = 0

        def _register_struct(world_pt, hint_cod=None, hint_user=None):
            """Devuelve el id de la estructura en (mundo) world_pt. Deduplica
            estructuras dentro de 0.5 m; enriquece rim/sump/part si vienen."""
            nonlocal auto_bz
            for sid, s in struct_map.items():
                if math.hypot(s["_key"][0] - world_pt[0], s["_key"][1] - world_pt[1]) <= 0.5:
                    if hint_cod and s.get("_auto"):
                        # ascender de BZ-auto al código del usuario, sin duplicar entrada
                        s["id"] = hint_cod; s["_auto"] = False
                        struct_map[hint_cod] = struct_map.pop(sid)
                    if hint_user:
                        if s.get("part") is None: s["part"] = _clean(hint_user.get("part"))
                        if s.get("rim") is None: s["rim"] = _f(hint_user.get("rim"))
                        if s.get("sump") is None: s["sump"] = _f(hint_user.get("sump"))
                    return s["id"]
            if hint_cod:
                sid = hint_cod
            else:
                auto_bz += 1
                sid = f"BZ-{auto_bz}"
            struct_map[sid] = {
                "id": sid,
                "part": _clean(hint_user.get("part")) if hint_user else None,
                "x": _f(world_pt[0]),
                "y": _f(world_pt[1]),
                "rim": _f(hint_user.get("rim")) if hint_user else None,
                "sump": _f(hint_user.get("sump")) if hint_user else None,
                "_key": (world_pt[0], world_pt[1]),
                "_auto": not bool(hint_cod),
            }
            return sid

        # Datos DERIVADOS de la capa que son iguales para todas las tuberías de
        # este grupo (color en la paleta ACI y tipo por defecto pipe/pressure).
        layer_color = layer_color_info(layer)
        layer_default_type = default_network_type(layer)

        for p in pipes:
            # DIÁMETRO: SIEMPRE en pulgadas (lista fija del catálogo), independiente
            # de la unidad de trabajo (que rige coordenadas/cotas).
            diameter = {"value": _f(p.get("diam")), "unit": "in"}
            part = _clean(p.get("part"))
            material = _clean(p.get("material"))          # texto libre del usuario, p.ej. "HDPE"
            # network_type: si el usuario eligió "pipe"/"pressure" lo respetamos;
            # si dejó "auto" (o vacío) usamos el default de la capa.
            nt_raw = _clean(p.get("net_type"))
            if nt_raw in ("pipe", "pressure"):
                pipe_net_type = nt_raw
            else:
                pipe_net_type = layer_default_type
            is_world = bool(p.get("world"))

            if is_world:
                # Los tramos importados de Excel ya están en la unidad del proyecto
                # (convertidos a la unidad al momento de importar).
                verts_world = [tuple(p["wstart"]), tuple(p["wend"])]
                verts_native = verts_world
                explicit = [_clean(p.get("from")), _clean(p.get("to"))]
            else:
                pts = p["pts"]
                verts_native = [tuple(pt) for pt in pts]
                # Coordenadas en la unidad del proyecto (ft o in) — ver _project_xy.
                verts_world = [_project_xy(win, pt[0], pt[1]) for pt in pts]
                explicit = [None] * len(pts)

            # En gravedad, cada vértice (incl. los intermedios) es una estructura.
            vertex_ids = [None] * len(verts_world)
            if has_structures:
                for i, (wv, nv) in enumerate(zip(verts_world, verts_native)):
                    user = _find_user_struct(win, is_world, nv)
                    hint = explicit[i] or (user.get("cod") if (user and user.get("cod")) else None)
                    vertex_ids[i] = _register_struct(wv, hint_cod=hint, hint_user=user)

            n_seg = len(verts_world) - 1
            for i in range(n_seg):
                pipe_ctr += 1
                s_pt = verts_world[i]; e_pt = verts_world[i + 1]
                # Cota de RECORRIDO (no por segmento): el invert del usuario se
                # pega SOLO al 1er vértice del recorrido (start del tramo 0) y al
                # último (end del último tramo). Los vértices intermedios van null
                # — el plugin C# se encarga de interpolarlos si hace falta.
                s_inv = _f(p.get("inv_start")) if i == 0 else None
                e_inv = _f(p.get("inv_end")) if i == n_seg - 1 else None
                pipe_id = p.get("id") if (is_world and p.get("id")) else f"T{pipe_ctr}"
                pipe_out.append({
                    "id": pipe_id,
                    "part": part,
                    "material": material,             # texto libre; None si el usuario no lo rellenó
                    "diameter": diameter,
                    "color": layer_color,             # {"aci": n, "name": "blue"} — heredado de la capa
                    "network_type": pipe_net_type,    # "pipe" | "pressure"
                    "from": vertex_ids[i] if has_structures else None,
                    "to": vertex_ids[i + 1] if has_structures else None,
                    "start": {"x": _f(s_pt[0]), "y": _f(s_pt[1]), "invert": s_inv},
                    "end": {"x": _f(e_pt[0]), "y": _f(e_pt[1]), "invert": e_inv},
                })

        structures = []
        if has_structures:
            for s in struct_map.values():
                structures.append({"id": s["id"], "part": s.get("part"),
                                   "x": s["x"], "y": s["y"],
                                   "rim": s.get("rim"), "sump": s.get("sump")})

        networks.append({"name": name, "kind": kind,
                         "has_structures": has_structures,
                         "structures": structures, "pipes": pipe_out})

    # Validaciones (no bloqueantes)
    for net in networks:
        ids = {s["id"] for s in net["structures"]}
        for pp in net["pipes"]:
            v = pp["diameter"].get("value")
            if v is None or v == 0:
                warnings.append(f"[{net['name']}] tubería '{pp['id']}' sin diámetro definido.")
            for end in ("from", "to"):
                v = pp[end]
                if v is not None and v not in ids:
                    warnings.append(f"[{net['name']}] tubería '{pp['id']}' referencia un buzón inexistente: '{v}'.")
        for s in net["structures"]:
            if s.get("rim") is None or s.get("sump") is None:
                warnings.append(f"[{net['name']}] buzón '{s['id']}' sin rim o sump.")
            elif s["sump"] > s["rim"]:
                warnings.append(f"[{net['name']}] buzón '{s['id']}': sump ({s['sump']}) > rim ({s['rim']}).")

    return networks, warnings


def write_network_json(win, out_path):
    """Escribe el JSON schema utility-network/3.0. Devuelve (path, warnings).

    La UNIDAD del JSON es `win.work_unit` — 'ft' (pies) o 'in' (pulgadas). Todo
    (coords, cotas, diámetros) queda en esa unidad."""
    networks, warnings = build_networks(win)
    if not networks:
        return None, warnings + ["No hay tuberías que exportar."]
    data = {"schema": "utility-network/3.0", "units": win.work_unit, "networks": networks}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return out_path, warnings
