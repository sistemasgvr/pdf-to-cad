"""model_ops.py — Operaciones PURAS sobre el modelo de datos (sin Qt).

Lógica de datos que antes vivía dentro de la ventana `Main` y que ahora se puede
probar en aislamiento:

  - rebuild_structures(pipes, structures): auto-detecta los buzones/cajas en los
    vértices de las tuberías dibujadas, reconciliando las ediciones previas por
    coordenada. Devuelve la lista NUEVA de estructuras (no muta la ventana).
  - bz_segment_count(pipes, s): cuántos extremos de segmento de tubería tocan la
    posición de una estructura (para decidir si puede ser un elemento curvo).

`Main` conserva un método delgado que llama a estas funciones y hace la asignación
(`self.structures = …`) y el marcado de cambios (`self._dirty = True`).
"""
import copy
import math

from model import network_kind, LEADER_TEXT_FT

_TOL = 14.0   # tolerancia de coincidencia de coordenadas (px), compartida por ambas


def pipe_at_vertex(pipes, x, y, tol=14.0):
    """Tubería (dict, no 'world') con el vértice MÁS CERCANO a (x,y) a distancia
    <= tol, o None. La familia/tamaño de un elemento curvo se hereda de esta
    tubería — nunca se elige aparte, para que la curva calce con los tramos rectos.
    El más cercano, no el primero: dos codos reconocidos pueden quedar a menos de
    tol (DU08 h.26: dos curvas eléctricas que salen de la misma recta, esquinas a
    3.8 pt = 13 px) y la curva de una se dibujaba con la tubería de la otra."""
    best, bd = None, tol * tol
    for p in pipes:
        if p.get("world") or not p.get("pts"): continue
        for (vx, vy) in p["pts"]:
            d = (vx - x) ** 2 + (vy - y) ** 2
            if d <= bd:
                best, bd = p, d
    return best


def nearest_vertex(pts, x, y, tol=14.0):
    """Índice del vértice de `pts` más cercano a (x,y) a distancia <= tol, o None."""
    best, bd = None, tol * tol
    for i, (vx, vy) in enumerate(pts or []):
        d = (vx - x) ** 2 + (vy - y) ** 2
        if d <= bd:
            best, bd = i, d
    return best


def structures_at_vertex(pipes, structures, pipe_idx, vi, tol=_TOL):
    """Estructuras (buzón, caja, sólido, CV) que pertenecen al vértice `vi` de la
    tubería `pipe_idx`: a ≤ tol px y SIN otro vértice más cercano en ninguna
    tubería (mismo criterio que curve_vertex_indices). Las importadas (world) no."""
    pts = (pipes[pipe_idx].get("pts") or []) if 0 <= pipe_idx < len(pipes) else []
    if not (0 <= vi < len(pts)):
        return []
    vx, vy = pts[vi]
    out = []
    for s in structures or []:
        if s.get("world") or s.get("x") is None:
            continue
        sx, sy = float(s["x"]), float(s["y"])
        d = math.hypot(sx - vx, sy - vy)
        if d > tol:
            continue
        mejor = True
        for pj, p in enumerate(pipes):
            for vj, (qx, qy) in enumerate(p.get("pts") or []):
                if (pj, vj) != (pipe_idx, vi) and math.hypot(sx - qx, sy - qy) < d - 1e-9:
                    mejor = False; break
            if not mejor:
                break
        if mejor:
            out.append(s)
    return out


def translate_structure(s, dx, dy):
    """Desplaza una estructura (y el contorno de su bóveda/sólido) en px."""
    s["x"] = float(s["x"]) + dx; s["y"] = float(s["y"]) + dy
    if s.get("outline"):
        s["outline"] = [(float(x) + dx, float(y) + dy) for x, y in s["outline"]]


def curve_vertex_indices(pipe, structures, pipes=(), tol=14.0):
    """{índice de vértice: estructura CV} de los vértices de `pipe` que SON codo.
    Cada estructura curva pertenece a UN solo vértice: el más cercano (a ≤ tol)
    entre todas las tuberías (`pipes`). Antes bastaba con que hubiera una CV a ≤14 px:
    con codos reconocidos juntos (DU08 h.26: el ancla de un codo a 13.6 px de su propia
    esquina, dos esquinas de curvas distintas a 13 px) el editor tomaba por curvo un
    vértice recto (tope 0.48 → radio recortado) y el DXF lo mandaba al plugin como
    vértice sin buzón (curva de radio automático donde el plano no tiene ninguna)."""
    pts = pipe.get("pts") or []
    out = {}
    for s in structures or ():
        if not s.get("curve") or s.get("world"):
            continue
        sx, sy = s.get("x"), s.get("y")
        if sx is None or sy is None:
            continue
        i = nearest_vertex(pts, sx, sy, tol)
        if i is None:
            continue
        d = (pts[i][0] - sx) ** 2 + (pts[i][1] - sy) ** 2
        if any(o is not pipe and not o.get("world")
               and any((vx - sx) ** 2 + (vy - sy) ** 2 < d for vx, vy in (o.get("pts") or ()))
               for o in pipes or ()):
            continue                                 # es el codo de OTRA tubería (más cerca)
        prev = out.get(i)
        if prev is None or (prev["x"] - pts[i][0]) ** 2 + (prev["y"] - pts[i][1]) ** 2 > d:
            out[i] = s
    return out


def leader_geo(ld, px_for_ft):
    """Geometría del Multileader (px). La 'cola' (parte de la línea junto al texto)
    se adapta al largo del texto. La punta se orienta con segs[0][1]. `px_for_ft`
    convierte pies→px (depende de la escala/zoom actuales; lo provee la ventana)."""
    ax, ay = ld["arrow"]; tx, ty = ld["tp"]
    ftsize = ld.get("size_ft", LEADER_TEXT_FT)
    H = px_for_ft(ftsize)
    lines = ld["text"].split("\n"); maxlen = max((len(s) for s in lines), default=1); nlines = len(lines)
    tw = max(maxlen * H * 0.6, H * 2); th = nlines * H; gap = H * 0.5; near = H * 0.22
    if ld.get("simple"):                               # LEADER simple: solo flecha, sin texto
        lp = ld.get("landing")
        if lp:                                         # diagonal con landing: cabeza → bisagra → final
            segs = [[(ax, ay), (lp[0], lp[1]), (tx, ty)]]
        else:                                          # recto h/v: cabeza → final del cuerpo
            segs = [[(ax, ay), (tx, ty)]]
        end = segs[0][-1]
        return dict(segs=segs, label_pos=end, rot=0, side="right", verts_px=segs[0], insert_px=end,
                    dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=end, cad_rot=0)
    orient = ld.get("orient", "h")
    if orient == "v":                                  # recto vertical; texto vertical junto a la cola
        signY = -1 if ty < ay else 1
        L = max(abs(ty - ay), tw + gap); ey = ay + signY * L; my = (ay + ey) / 2
        side = "top" if signY < 0 else "bottom"
        lbl = (ax + H * 0.08, my + tw / 2)              # rot -90, centrado a lo largo, pegado a la línea
        segs = [[(ax, ay), (ax, ey)]]
        return dict(segs=segs, label_pos=lbl, rot=-90, side=side, verts_px=segs[0], insert_px=(ax, ey),
                    dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=(ax + th / 2 + H * 0.08, my), cad_rot=90)
    if orient == "h":                                  # recto horizontal; texto encima de la cola
        signX = 1 if tx >= ax else -1
        L = max(abs(tx - ax), tw + gap); ex = ax + signX * L
        lblx = ex - tw if signX > 0 else ex
        side = "right" if signX > 0 else "left"
        segs = [[(ax, ay), (ex, ay)]]
        return dict(segs=segs, label_pos=(lblx, ay - th - near), rot=0, side=side, verts_px=segs[0], insert_px=(ex, ay),
                    dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=(lblx + tw / 2, ay - near - th / 2), cad_rot=0)
    # diagonal: flecha → 2º clic → landing horizontal → texto encima del landing
    right = tx >= ax; sgn = 1 if right else -1
    lx = tx + sgn * (tw + gap); text_x = min(tx, lx) + gap
    side = "right" if right else "left"
    lbl = (text_x, ty - H - near)                      # 1ª línea encima; extras al otro lado
    segs = [[(ax, ay), (tx, ty), (lx, ty)]]
    return dict(segs=segs, label_pos=lbl, rot=0, side=side, verts_px=segs[0], insert_px=(lx, ty),
                dogleg=0.0, H=H, cad_h=ftsize, tcenter_px=(text_x + tw / 2, ty - H - near + th / 2), cad_rot=0)


def rebuild_structures(pipes, structures):
    """Detecta buzones por los VÉRTICES (extremos + intermedios) de las tuberías
    dibujadas:
      - Gravedad (SS/SD) → prefijo BZ- (buzones cilíndricos con tapa).
      - Conduit (eléctrico/telecom) → NUNCA nodos automáticos en sus vértices,
        ni al dibujar a mano ni en líneas reconocidas del PDF (regla del
        usuario 2026-09-28: un vértice de la utilidad no es una caja). El
        estándar en campo es tener MUY POCAS cajas de registro; si necesita
        una puntual, la agrega con Herramientas → «Insertar buzón en línea…».
        Las cajas del reconocimiento salen SOLO de una bóveda reconocida en
        sus capas (`attach_vault_geometry`) y aquí se conservan.
      - Presión (agua/gas) → sin nodos automáticos.
    Preserva ediciones (cod/rim/sump/part/part_size/covered) por coincidencia
    de coordenada. Los buzones importados de Excel (world) y las cajas ya
    existentes en conduit (creadas a mano o desde el reconocimiento) se
    conservan tal cual. Devuelve la lista nueva de estructuras."""
    tol = _TOL
    def near(a, b): return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
    # Descarta buzones espurios de versiones previas con net inválida (p.ej. "pressure").
    # Conduit (eléctrico/telecom) NO auto-detecta en sus vértices: sus cajas
    # existentes (a mano, o de una bóveda reconocida vía attach_vault_geometry)
    # se conservan. Los importados de Excel (world) y las bóvedas reconocidas
    # SIN línea (standalone) se conservan tal cual.
    old_gravity = [s for s in structures
                   if not s.get("world") and not s.get("standalone")
                   and (s.get("net") or "gravity") == "gravity"]
    kept_conduit = [s for s in structures
                    if not s.get("world") and not s.get("standalone")
                    and (s.get("net") or "") == "conduit"]
    world = [s for s in structures if s.get("world") or s.get("standalone")]
    detected = []
    for p in pipes:
        if p.get("world"): continue
        kind = network_kind(p.get("layer") or "")
        # Solo GRAVEDAD auto-detecta, en todos los vértices. CONDUIT nunca (sus
        # cajas vienen de bóvedas reconocidas o las pone el usuario). Presión nunca.
        if kind != "gravity": continue
        pts = p.get("pts")
        if not pts or len(pts) < 2: continue
        for pt in pts:                              # todos los vértices (extremos + intermedios)
            if not any(s.get("net") == kind and near(pt, (s["x"], s["y"]))
                       for s in detected):
                detected.append({"cod": "", "x": pt[0], "y": pt[1], "rim": None,
                                 "sump": None, "part": "", "part_size": "",
                                 "net": kind, "covered": True, "world": False,
                                 "hidden": False})
    for s in detected:                                 # reasigna ediciones previas por coordenada
        for o in old_gravity:
            if near((s["x"], s["y"]), (o.get("x", -1e9), o.get("y", -1e9))):
                s.update(cod=o.get("cod", ""), rim=o.get("rim"), sump=o.get("sump"),
                         part=o.get("part", ""), part_size=o.get("part_size", ""),
                         covered=bool(o.get("covered", True)),
                         height_ft=o.get("height_ft", 0.0),
                         curve=bool(o.get("curve", False)),
                         radius_ft=o.get("radius_ft", 0.0),
                         hidden=bool(o.get("hidden", False)))
                # geometría real de la bóveda reconocida (ver attach_vault_geometry)
                for k in VAULT_GEO_KEYS:
                    if k in o:
                        s[k] = o[k]
                if o.get("xdata"):                     # datos extendidos (capa de origen + del usuario)
                    s["xdata"] = copy.deepcopy(o["xdata"])
                break
    # Códigos únicos: BZ-N gravedad, CAJA-N conduit (solo las conservadas del
    # usuario / reconocimiento), CV-N esquina de elemento curvo (curve=True
    # manda sobre el prefijo por red: no es un buzón/caja real).
    combined = world + kept_conduit + detected
    used = {s.get("cod", "") for s in combined if s.get("cod")}
    cnt_bz = cnt_caja = cnt_cv = 1
    for s in detected + kept_conduit:
        if s.get("cod"): continue
        if s.get("curve"):
            while f"CV-{cnt_cv}" in used: cnt_cv += 1
            s["cod"] = f"CV-{cnt_cv}"; used.add(s["cod"]); cnt_cv += 1
            continue
        prefix = "CAJA-" if s.get("net") == "conduit" else "BZ-"
        if prefix == "BZ-":
            while f"BZ-{cnt_bz}" in used: cnt_bz += 1
            s["cod"] = f"BZ-{cnt_bz}"; used.add(s["cod"]); cnt_bz += 1
        else:
            while f"CAJA-{cnt_caja}" in used: cnt_caja += 1
            s["cod"] = f"CAJA-{cnt_caja}"; used.add(s["cod"]); cnt_caja += 1
    return normalize_solids(combined)


# Vértices del reconocimiento donde la línea llega a una bóveda: la atraviesa
# («vault») o muere en su borde («stop»). En conduit NO crean caja por sí solos:
# attach_vault_geometry pone ahí la caja de una bóveda RECONOCIDA para conectarla.
VAULT_VERTEX_KINDS = ("vault", "stop")


# Tipos de vértice que NO son un acceso físico (vienen del reconocimiento de
# PDF: quiebre suave, esquina sin bóveda, vértice de arco). El buzón que
# rebuild_structures crea ahí se oculta: se exporta como "Estructura nula".
SOFT_VERTEX_KINDS = ("bend", "corner", "curve", "edge")   # "stop" = caja visible donde la línea muere en el buzón


def hide_soft_vertex_structures(pipes, structures):
    """Marca hidden=True en las estructuras detectadas sobre vértices "blandos"
    de pipes reconocidas (clave `vertex_kinds`, paralela a `pts`). Un vértice
    compartido con otra pipe donde SÍ es bóveda/T/junction se respeta (visible).
    Devuelve cuántas estructuras se ocultaron. Muta `structures` en sitio."""
    tol = _TOL
    hard = {"gravity": [], "conduit": []}
    soft = {"gravity": [], "conduit": []}
    for p in pipes:
        net = network_kind(p.get("layer") or "")
        if net not in hard:
            continue
        kinds = p.get("vertex_kinds") or []
        pts = p.get("pts") or []
        if len(kinds) != len(pts):
            hard[net].extend(pts)            # pipe manual: todos sus vértices son reales
            continue
        for pt, k in zip(pts, kinds):
            (soft[net] if k in SOFT_VERTEX_KINDS else hard[net]).append(pt)
    n = 0
    for s in structures:
        if s.get("world") or s.get("hidden") or s.get("curve"):
            continue
        net = s.get("net") or "gravity"
        xy = (s.get("x", 0.0), s.get("y", 0.0))
        near = lambda q: math.hypot(q[0] - xy[0], q[1] - xy[1]) <= tol
        if any(near(q) for q in soft.get(net, ())) and not any(near(q) for q in hard.get(net, ())):
            s["hidden"] = True
            n += 1
    return n


def interp_vertex_z(pts, z_start, z_end, overrides):
    """Cota por vértice interpolada por distancia acumulada 2D, entre anclas
    (extremos + overrides fijados). Espejo exacto de InterpolateZ/ZalongByDistance
    en ImportarRed.cs — usado para mostrar el valor 'automático' en la tabla de
    vértices intermedios."""
    n = len(pts)
    z = [0.0] * n
    if n == 0: return z
    if n == 1: z[0] = z_start; return z
    anchors = {0: z_start, n - 1: z_end}
    for k, v in (overrides or {}).items():
        if 0 < k < n - 1: anchors[k] = v
    keys = sorted(anchors.keys())
    for a, b in zip(keys, keys[1:]):
        sub = pts[a:b + 1]
        d = [0.0] * len(sub)
        for i in range(1, len(sub)):
            d[i] = d[i - 1] + math.hypot(sub[i][0] - sub[i - 1][0], sub[i][1] - sub[i - 1][1])
        total = d[-1]
        za, zb = anchors[a], anchors[b]
        for i in range(len(sub)):
            z[a + i] = za + (zb - za) * (d[i] / total) if total > 1e-9 else za
    return z


def migrate_vertex_inv(p):
    """Migra el formato viejo (vertex_inv compartido) al nuevo
    (vertex_inv_out + vertex_inv_in independientes)."""
    old = p.pop("vertex_inv", None)
    if old and "vertex_inv_out" not in p:
        p["vertex_inv_out"] = dict(old)
        p["vertex_inv_in"] = dict(old)


def snapshot_seg_values(p):
    """Congela como overrides explícitos todos los valores actualmente
    mostrados en la tabla (excepto v0 del primer tramo y v_n del último,
    que se editan vía inv_start/inv_end). Idempotente."""
    pts = p.get("pts") or []
    n = len(pts)
    if n < 3: return
    ov_out = p.setdefault("vertex_inv_out", {})
    ov_in  = p.setdefault("vertex_inv_in",  {})
    z_start = p.get("inv_start") or 0.0; z_end = p.get("inv_end") or 0.0
    auto_out = interp_vertex_z(pts, z_start, z_end, ov_out)
    auto_in  = interp_vertex_z(pts, z_start, z_end, ov_in)
    for vi in range(1, n - 1):
        ov_out.setdefault(vi, auto_out[vi])
        ov_in.setdefault(vi, auto_in[vi])


def bz_segment_count(pipes, s):
    """Cuántos EXTREMOS de segmento de tubería coinciden con la posición del
    buzón `s`. Un buzón al final de una línea suma 1 (un solo tramo llega); un
    vértice intermedio suma 2 (tramo que entra + tramo que sale); un cruce de
    dos utilidades, 2 o más. Solo con >=2 hay una esquina con dos tangentes,
    que es lo único que puede convertirse en un elemento curvo."""
    sx, sy = s.get("x"), s.get("y")
    if sx is None or sy is None:
        return 0
    tol = _TOL                               # misma tolerancia que rebuild_structures
    n = 0
    for p in pipes:
        if p.get("world"):
            continue
        pts = p.get("pts")
        if not pts or len(pts) < 2:
            continue
        last = len(pts) - 1
        for i, pt in enumerate(pts):
            if math.hypot(pt[0] - sx, pt[1] - sy) <= tol:
                n += 1 if (i == 0 or i == last) else 2
    return n


# ─────────────────────────── bóvedas reconocidas ───────────────────────────
# Campos de geometría real que una estructura puede traer del reconocimiento
# (contorno del símbolo en el PDF, nada inventado): forma, ancho y largo en
# pies, giro del lado largo y el contorno en px del lienzo para dibujarlo.
VAULT_GEO_KEYS = ("shape", "width_ft", "length_ft", "rot_deg", "outline")


def attach_vault_geometry(structures, vaults_geo, tol=12.0, net="conduit",
                          utility="ELECTRICO", origin=None, pipes=None):
    """Asocia cada bóveda reconocida (`RecognitionResult.vaults_geo`) a la
    estructura más cercana a su centro (≤ `tol` px) y le copia forma, medidas
    y contorno. Una bóveda real sin estructura cerca (ninguna línea la atraviesa
    ni muere en ella; `importable`) se importa igual como CAJA SUELTA
    (`standalone=True`, sin vértice: en Civil 3D será un sólido aislado); las
    cajas propuestas / postes no. Los datos extendidos (`xdata`) guardan la capa
    OCG del símbolo y el origen (`origin((x, y)) -> str`, opcional); los campos
    que el usuario haya anotado se conservan. Devuelve (asignadas, sueltas_creadas).

    Conduit (eléctrico/telecom): `rebuild_structures` no pone cajas en los
    vértices, así que la caja de la bóveda nace AQUÍ, del símbolo reconocido.
    Si una línea de `pipes` llega a la bóveda (vértice «vault»/«stop» sobre su
    centro o dentro de su contorno), la caja va en ESE vértice para que en
    Civil 3D la línea quede conectada a ella (una sola caja por bóveda). Un
    vértice «vault»/«stop» sin bóveda reconocida no crea nada."""
    done = 0; created = 0
    for vg in vaults_geo or []:
        cx, cy = vg.get("center", (None, None))
        if cx is None:
            continue
        best = None
        for s in structures:
            if s.get("world") or s.get("curve") or (s.get("net") or "gravity") != net:
                continue
            d = math.hypot(float(s.get("x", 1e9)) - cx, float(s.get("y", 1e9)) - cy)
            if d <= tol and (best is None or d < best[0]):
                best = (d, s)
        if best is None and vg.get("corners"):
            # Sin CAJA en el centro (las líneas mueren en el borde con «stop», caso
            # típico de la bóveda abandonada): la más cercana DENTRO del contorno.
            xs = [x for x, _ in vg["corners"]]; ys = [y for _, y in vg["corners"]]
            for s in structures:
                if s.get("world") or s.get("curve") or (s.get("net") or "gravity") != net:
                    continue
                sx, sy = float(s.get("x", 1e9)), float(s.get("y", 1e9))
                if min(xs) - 2 <= sx <= max(xs) + 2 and min(ys) - 2 <= sy <= max(ys) + 2:
                    d = math.hypot(sx - cx, sy - cy)
                    if best is None or d < best[0]:
                        best = (d, s)
        if best is None and net == "conduit" and pipes:
            # La línea llega a la bóveda: su caja va en el vértice de llegada
            # (conexión en Civil 3D), no suelta en el centro del símbolo.
            pt = _vertice_de_boveda(pipes, vg, tol)
            if pt is not None:
                st = {"cod": "", "x": float(pt[0]), "y": float(pt[1]), "rim": None,
                      "sump": None, "part": "", "part_size": "", "net": net,
                      "covered": True, "world": False, "hidden": False}
                structures.append(st)
                best = (0.0, st)
        if best is None:
            if not vg.get("importable", False):
                continue
            # ya importada en una pasada anterior (mismo centro): reutilizar
            for s in structures:
                if (s.get("standalone") and (s.get("net") or "gravity") == net
                        and math.hypot(float(s["x"]) - cx, float(s["y"]) - cy) <= tol):
                    best = (0.0, s); break
            if best is None:
                st = {"cod": "", "x": float(cx), "y": float(cy), "rim": None, "sump": None,
                      "part": "", "part_size": "", "net": net, "utility": utility,
                      "covered": True,
                      "world": False, "hidden": False, "standalone": True}
                structures.append(st); created += 1
                best = (0.0, st)
        st = best[1]
        st["shape"] = vg.get("shape", "rect")
        st["width_ft"] = float(vg.get("width_ft") or 0.0)
        st["length_ft"] = float(vg.get("length_ft") or 0.0)
        st["rot_deg"] = float(vg.get("angle_deg") or 0.0)
        st["outline"] = [(float(x), float(y)) for x, y in (vg.get("corners") or [])] or None
        st["hidden"] = False                      # una bóveda real siempre se ve
        if vg.get("abandoned"):
            st["abandoned"] = True
        if vg.get("layer"):
            import xdata
            where = origin((cx, cy)) if callable(origin) else origin
            xdata.set_auto(st, xdata.auto_fields(vg.get("layer"), where))
        done += 1
    _assign_standalone_codes(structures)
    normalize_solids(structures)
    return done, created


def _vertice_de_boveda(pipes, vg, tol):
    """Vértice «vault»/«stop» (`VAULT_VERTEX_KINDS`) de `pipes` por el que una
    línea llega a la bóveda `vg`: a ≤ `tol` px de su centro o dentro de su
    contorno (±2 px). Prefiere «vault» (la línea la atraviesa) y, a igualdad,
    el más cercano al centro. None si ninguna línea llega a ella."""
    cx, cy = vg["center"]
    caja = None
    if vg.get("corners"):
        xs = [x for x, _ in vg["corners"]]; ys = [y for _, y in vg["corners"]]
        caja = (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)
    best = None
    for p in pipes:
        pts = p.get("pts") or []
        kinds = p.get("vertex_kinds") or []
        if len(kinds) != len(pts):
            continue                              # dibujada a mano: sin bóvedas
        for (x, y), k in zip(pts, kinds):
            if k not in VAULT_VERTEX_KINDS:
                continue
            d = math.hypot(x - cx, y - cy)
            dentro = caja is not None and caja[0] <= x <= caja[2] and caja[1] <= y <= caja[3]
            if d > tol and not dentro:
                continue
            clave = (k != "vault", d)
            if best is None or clave < best[0]:
                best = (clave, (x, y))
    return None if best is None else best[1]


def _assign_standalone_codes(structures):
    """Código CAJA-N/BZ-N a las estructuras sueltas y a las cajas de conduit
    recién creadas por `attach_vault_geometry` (rebuild_structures no las
    numera: las conserva tal cual)."""
    used = {s.get("cod", "") for s in structures if s.get("cod")}
    n = 1
    for s in structures:
        if s.get("cod"):
            continue
        if s.get("standalone") or (s.get("net") == "conduit" and not s.get("curve")
                                   and not s.get("world")):
            prefix = "BZ-" if s.get("net") == "gravity" else "CAJA-"
            while f"{prefix}{n}" in used:
                n += 1
            s["cod"] = f"{prefix}{n}"; used.add(s["cod"]); n += 1


def attach_fillets(pipes, structures, tol=1.0):
    """Marca como esquina de elemento curvo (CV: `curve=True`, `radius_ft`) la
    estructura del vértice «fillet» de cada pipe reconocida (`pipe["fillets"]`
    = {índice: radio_ft}). Mismo modelo que el codo manual; el plugin genera la
    tubería curva tangente con ese radio. Devuelve cuántas marcó."""
    n = 0
    for p in pipes:
        fil = p.get("fillets") or {}
        pts = p.get("pts") or []
        net = network_kind(p.get("layer") or "")
        for idx, r_ft in fil.items():
            try:
                x, y = pts[int(idx)]
            except (IndexError, ValueError, TypeError):
                continue
            s = next((s for s in structures if not s.get("world")
                      and math.hypot(float(s.get("x", 1e9)) - x, float(s.get("y", 1e9)) - y) <= tol),
                     None)
            if s is None:
                # Eléctrico/telecom no tiene caja en cada vértice: el codo crea su
                # propia marca CV (rebuild_structures conserva las de conduit).
                if net != "conduit":
                    continue
                s = {"cod": "", "x": float(x), "y": float(y), "rim": None, "sump": None,
                     "part": "", "part_size": "", "net": net, "covered": True,
                     "world": False, "hidden": False}
                structures.append(s)
            if not s.get("curve") or abs(float(s.get("radius_ft") or 0.0) - float(r_ft)) > 1e-6:
                s["curve"] = True
                s["radius_ft"] = float(r_ft)
                s["hidden"] = False
                s["part"] = ""; s["part_size"] = ""
                if not s.get("cod", "").startswith("CV-"):
                    s["cod"] = ""                      # rebuild_structures le asigna CV-N
                n += 1
    return n


# Tope de la tangencia de una esquina curva sobre cada recta vecina (fracción del
# tramo) — MISMOS valores que ImportarRed.cs (CAP_CURVA_RECTA / CAP_CURVA_DOBLE).
# Recta: la tangencia puede llegar hasta el vértice vecino (el reconocimiento
# escribe ahí el vértice cuando la recta sigue por un tee: T = tramo completo).
# Vecino también curvo: la mitad menos un poco, para que los arcos no se crucen.
FILLET_CAP_RECTA = 1.0
FILLET_CAP_CURVA = 0.48
# Un radio pedido que supera el máximo en menos de esto (pies) no es un recorte:
# es el redondeo del campo (2 decimales) o del DXF. Mismo valor que TOL_RADIO_FT
# del plugin, que en ese caso usa el máximo sin avisar.
FILLET_TOL_RADIO_FT = 0.01


def fillet_geo(prev, corner, nxt, r_px, max_frac=FILLET_CAP_RECTA, n_arc=32, max_frac_next=None,
               tol_r=0.05):
    """Arco tangente REAL de una esquina curva (CV) — el mismo que genera
    ImportarRed.cs: puntos de tangencia sobre cada recta vecina a
    T = r·tan(Δ/2) de la esquina (Δ = giro), centro del círculo y los puntos
    del arco para dibujarlo. `max_frac` es el tope sobre la recta ANTERIOR y
    `max_frac_next` sobre la SIGUIENTE (None = el mismo). Si T no entra se
    recorta a ese tope y el radio baja en proporción; `clamped` solo si el radio
    pedido supera el máximo en más de `tol_r` (mismas unidades que `r_px`).
    Devuelve dict {t1, t2, center, r, T, arc: [pts], clamped} o None si la
    esquina es recta/degenerada."""
    d1x, d1y = prev[0] - corner[0], prev[1] - corner[1]
    d2x, d2y = nxt[0] - corner[0], nxt[1] - corner[1]
    L1 = math.hypot(d1x, d1y); L2 = math.hypot(d2x, d2y)
    if L1 < 1e-6 or L2 < 1e-6 or not r_px or r_px <= 0:
        return None
    d1x, d1y, d2x, d2y = d1x / L1, d1y / L1, d2x / L2, d2y / L2
    cos_phi = max(-1.0, min(1.0, d1x * d2x + d1y * d2y))
    phi = math.acos(cos_phi)                       # ángulo interior entre las patas
    if phi > math.radians(178.0) or phi < math.radians(1.0):
        return None
    r = float(r_px)
    T = r / math.tan(phi / 2.0)
    clamped = False
    f_next = max_frac if max_frac_next is None else max_frac_next
    t_max = min(L1 * max_frac, L2 * f_next)
    if T > t_max:
        # Un exceso de hasta `tol_r` en el radio es redondeo: la tangencia cae
        # sobre el vértice vecino y no cuenta como recorte.
        r_max = t_max * math.tan(phi / 2.0)
        clamped = r > r_max + tol_r
        T = t_max; r = r_max
    t1 = (corner[0] + d1x * T, corner[1] + d1y * T)
    t2 = (corner[0] + d2x * T, corner[1] + d2y * T)
    bx, by = d1x + d2x, d1y + d2y
    bl = math.hypot(bx, by)
    if bl < 1e-9:
        return None
    dist_c = r / math.sin(phi / 2.0)
    cx, cy = corner[0] + bx / bl * dist_c, corner[1] + by / bl * dist_c
    a1 = math.atan2(t1[1] - cy, t1[0] - cx); a2 = math.atan2(t2[1] - cy, t2[0] - cx)
    sweep = (a2 - a1 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi       # camino corto (< 180°)
    arc = [(cx + r * math.cos(a1 + sweep * k / n_arc), cy + r * math.sin(a1 + sweep * k / n_arc))
           for k in range(n_arc + 1)]
    return {"t1": t1, "t2": t2, "center": (cx, cy), "r": r, "T": T, "arc": arc, "clamped": clamped}


def red_de(pipe):
    """Red de Civil 3D a la que irá la utilidad: el plugin agrupa por NOMBRE de
    red si lo tiene y, si no, por capa (RED-AGUA, RED-DRENAJE…). Dos utilidades
    de redes distintas nunca se unen con un accesorio."""
    return (pipe.get("name") or "").strip() or (pipe.get("layer") or "")


def red_civil_de_union(pipes, ia, ib):
    """Nombre de la red de Civil 3D donde quedan DOS tuberías de la misma
    utilidad que se tocan. El plugin las mete siempre en la misma red aunque
    tengan nombres distintos (`RedesUnidasPorContacto` en ImportarRed.cs): toma
    el nombre de la de menor índice que lo tenga; sin nombres, «RED-<capa>»."""
    for i in sorted((ia, ib)):
        nombre = (pipes[i].get("name") or "").strip()
        if nombre:
            return nombre
    return "RED-" + (pipes[ia].get("layer") or "")


def accesorio_en_punto(polilineas, pt, tol):
    """Accesorio que el plugin pondrá donde se juntan tramos de UNA red a
    presión: mira las salidas (direcciones) que parten de `pt` por cada tramo
    que lo toca y aplica la misma regla que RedesPresionJunturas.cs:
    2 salidas → «codo» si giran más de 1°, «recto» si no, 3 → «tee» si dos son
    colineales (≥160°) y el ramal va a 90° ±20°, si no «wye», 4 → «cruz»,
    5+ → None (no hay accesorio)."""
    px, py = pt
    salidas = []

    def _agregar(dx, dy):
        L = math.hypot(dx, dy)
        if L <= tol:
            return
        ang = math.atan2(dy, dx)
        if all(abs((ang - a + math.pi) % (2 * math.pi) - math.pi) > math.radians(1) for a in salidas):
            salidas.append(ang)

    for pts in polilineas:
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 <= 1e-12:
                continue
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            if math.hypot(ax + dx * t - px, ay + dy * t - py) > tol:
                continue
            _agregar(ax - px, ay - py)
            _agregar(bx - px, by - py)
    n = len(salidas)

    def _entre(a, b):
        return math.degrees(abs((a - b + math.pi) % (2 * math.pi) - math.pi))

    pares = [(i, j) for i in range(n) for j in range(i + 1, n) if _entre(salidas[i], salidas[j]) >= 160]
    if n == 2:
        # DecidirTipoFitting: codo desde 1° de giro; menos es una unión recta
        # (antes «recto» llegaba hasta 20° y el lienzo decía «conflicto»).
        giro = 180.0 - _entre(salidas[0], salidas[1])
        return "codo" if giro > 1.0 else "recto"
    if n == 3:
        # DecidirTeeOWye: Tee solo con tronco recto Y ramal a 90° ±20°; si no, Wye.
        for i, j in pares:
            ramal = _entre(salidas[3 - i - j], salidas[i])
            if min(ramal, 180 - ramal) >= 70:
                return "tee"
        return "wye"
    if n == 4:
        return "cruz"
    return None


def largo_min_entre_codos_ft(diam_in):
    """Largo mínimo de un tramo entre dos codos de una red a presión (misma
    regla que `LargoMinEntreCodosFt` del plugin): 3 diámetros, mínimo 1 ft."""
    try:
        d_ft = float(diam_in) / 12.0
    except (TypeError, ValueError):
        d_ft = 0.0
    return max(1.0, 3.0 * d_ft)


def tramos_cortos_entre_codos(pipes, ft_per_px):
    """Tramos de tuberías a presión entre DOS quiebres (giro ≥5°) más cortos que
    `largo_min_entre_codos_ft`: ahí no entran dos codos y el plugin los
    reemplaza por UNO solo (`FusionarCodosSeguidos`).
    Devuelve [{"x", "y", "pipe", "tramo", "largo_ft", "min_ft"}] (x, y en px =
    punto medio del tramo; tramo 1 = T1)."""
    salida = []
    for ip, p in enumerate(pipes):
        if network_kind(p.get("layer") or "") != "pressure":
            continue
        pts = p.get("pts") or []
        lmin = largo_min_entre_codos_ft(p.get("diam"))
        for k in range(1, len(pts) - 2):
            (ax, ay), (bx, by), (cx, cy), (dx, dy) = pts[k - 1], pts[k], pts[k + 1], pts[k + 2]
            largo = math.hypot(cx - bx, cy - by) * ft_per_px
            if largo <= 1e-9 or largo >= lmin - 1e-6:
                continue
            if _giro_deg((ax, ay), (bx, by), (cx, cy)) < 5 or _giro_deg((bx, by), (cx, cy), (dx, dy)) < 5:
                continue
            salida.append({"x": (bx + cx) / 2, "y": (by + cy) / 2, "pipe": ip, "tramo": k + 1,
                           "largo_ft": largo, "min_ft": lmin})
    return salida


def _codo_solido_ft(d, ang):
    """(T, alcance, cerrado) del codo sólido del plugin (WyeSolido.CurvaCodo /
    Brazo.AlcanceTuboFt): diámetro `d` en pies y ángulo ENTRE ejes `ang` (rad).
    T = vértice → tangencia; alcance = vértice → donde muere el tubo."""
    giro = math.pi - ang
    cerrado = giro > math.radians(135.0)
    tan_phi = math.tan(ang / 2.0)
    if abs(tan_phi) < 1e-9 or math.degrees(ang) < 2.0:   # ejes casi superpuestos: manguito recto
        return math.inf, math.inf, True
    r = d * 1.0
    t = r / tan_phi
    if t > d * 0.85:
        r_min = (d / 2.0 + 0.02 + 0.04 + 0.10 / 2.0) if cerrado else d * 1.0
        t = max(d * 0.85, r_min / tan_phi)
        if t * tan_phi < r_min - 1e-9:
            t = r_min / tan_phi
    alcance = (t + d * 0.12) + d * 0.45 * 0.75 - 0.12
    return t, alcance, cerrado


def codos_de_retorno(pipes, ft_per_px):
    """Codos CERRADOS (giro > 135°) de redes a presión con un tramo vecino tan
    corto que la curva no cabe (E07: 170° con 2 ft). El plugin hace ahí un codo
    de RETORNO en el vértice y traslada el tramo corto de lado
    (`CodosDeRetorno` en ImportarRed.cs). Devuelve
    [{"x", "y", "pipe", "tramo", "giro", "largo_ft", "necesita_ft", "lateral_ft"}]
    (x, y en px = vértice; tramo 1 = T1, el tramo corto)."""
    salida = []
    if not ft_per_px:
        return salida
    for ip, p in enumerate(pipes):
        if network_kind(p.get("layer") or "") != "pressure":
            continue
        pts = p.get("pts") or []
        try:
            d = float(p.get("diam") or 0) / 12.0
        except (TypeError, ValueError):
            d = 0.0
        if d <= 0:
            continue
        for k in range(1, len(pts) - 1):
            (ax, ay), (px, py), (bx, by) = pts[k - 1], pts[k], pts[k + 1]
            la = math.hypot(ax - px, ay - py) * ft_per_px
            lb = math.hypot(bx - px, by - py) * ft_per_px
            if la < 1e-9 or lb < 1e-9:
                continue
            giro = _giro_deg((ax, ay), (px, py), (bx, by))
            ang = math.radians(180.0 - giro)
            t, alcance, cerrado = _codo_solido_ft(d, ang)
            if not cerrado or math.isinf(t):
                continue
            necesita = alcance + 0.05
            if min(la, lb) >= necesita:
                continue
            corto_es_b = lb <= la
            salida.append({"x": px, "y": py, "pipe": ip, "tramo": k + 1 if corto_es_b else k,
                           "giro": giro, "largo_ft": min(la, lb), "necesita_ft": necesita,
                           "lateral_ft": t * math.sin(ang)})
    return salida


def desnivel_min_dos_codos_ft(diam_in):
    """Desnivel mínimo (entre ejes) para bajar con dos codos sólidos de 90°:
    2 × boca del codo + 0.05 ft; la boca de un codo de 90° mide 1.57·D
    (WyeSolido: radio 1·D + collar 0.12·D + campana 0.45·D)."""
    return 2 * 1.57 * (float(diam_in) / 12.0) + 0.05


def union_con_pendiente(pa, pb, pt, za, zb, tol, ft_per_px, z_tol=0.10):
    """EXTREMO CON EXTREMO de la misma utilidad a presión, a distinta cota
    (> z_tol, la app sugiere una vertical) pero sin altura para una conexión
    vertical (dos codos de 90° + vertical: `desnivel_min_dos_codos_ft`). El
    plugin no arma la vertical: la tubería más larga toma pendiente hasta la otra
    y se unen (con un codo si giran); si miden lo mismo (±2 %), las dos van al
    punto medio (`UnionConPendiente` en ImportarRed.cs).
    «Largo» = el tramo que llega al punto (es el que toma la pendiente).
    `za`/`zb` son soleras en el punto. Devuelve None o
    {"dz", "min", "iguales", "larga" ("a"|"b"|None), "z_union", "tramo_a",
     "tramo_b", "largo_a", "largo_b", "codo"}."""
    if za is None or zb is None or abs(za - zb) <= z_tol:
        return None
    if (pa.get("layer") or "") != (pb.get("layer") or "") or network_kind(pa.get("layer") or "") != "pressure":
        return None

    def _extremo(p):
        """(índice del tramo que llega, largo px, dirección saliente) o None."""
        pts = p.get("pts") or []
        if len(pts) < 2:
            return None
        for k_pt, k_seg, k_otro in ((0, 0, 1), (len(pts) - 1, len(pts) - 2, len(pts) - 2)):
            x, y = pts[k_pt]
            if math.hypot(x - pt[0], y - pt[1]) <= tol:
                ox, oy = pts[k_otro]
                return k_seg, math.hypot(ox - x, oy - y), (ox - x, oy - y)
        return None

    ea, eb = _extremo(pa), _extremo(pb)
    if ea is None or eb is None:
        return None
    try:
        da, db = float(pa.get("diam") or 0) / 12.0, float(pb.get("diam") or 0) / 12.0
    except (TypeError, ValueError):
        return None
    if da <= 0 or db <= 0:
        return None
    dz_eje = abs((za + da / 2.0) - (zb + db / 2.0))
    minimo = desnivel_min_dos_codos_ft(min(da, db) * 12.0)
    if dz_eje >= minimo:
        return None
    la, lb = ea[1] * ft_per_px, eb[1] * ft_per_px
    iguales = abs(la - lb) <= 0.02 * max(la, lb)
    larga = None if iguales else ("a" if la > lb else "b")
    z_union = (za + zb) / 2.0 if iguales else (zb if larga == "a" else za)
    (ux, uy), (vx, vy) = ea[2], eb[2]
    nu, nv = math.hypot(ux, uy), math.hypot(vx, vy)
    entre = math.degrees(math.acos(max(-1.0, min(1.0, (ux * vx + uy * vy) / (nu * nv))))) if nu and nv else 180.0
    return {"dz": abs(za - zb), "min": minimo, "iguales": iguales, "larga": larga, "z_union": z_union,
            "tramo_a": ea[0] + 1, "tramo_b": eb[0] + 1, "largo_a": la, "largo_b": lb,
            "codo": entre < 179.0}


def conexion_vertical_inclinada(pa, pb, pt, za, zb, tol):
    """Conexión vertical APROBADA entre una utilidad que pasa por `pt` con un
    QUIEBRE y otra que termina ahí (diseño Wye + tubo aux + codo + vertical +
    codo), cuando el desnivel no alcanza para los dos codos de 90°. El plugin
    pone entonces la Wye con el ramal inclinado y le da pendiente a la tubería
    que termina (`CrearCruceConWye`). Devuelve {"dz", "min", "termina"} o None."""
    def _extremo(p):
        pts = p.get("pts") or []
        return any(math.hypot(q[0] - pt[0], q[1] - pt[1]) <= tol for q in pts[:1] + pts[-1:])

    def _quiebre(p):
        pts = p.get("pts") or []
        return any(math.hypot(pts[k][0] - pt[0], pts[k][1] - pt[1]) <= tol
                   and _giro_deg(pts[k - 1], pts[k], pts[k + 1]) >= 5
                   for k in range(1, len(pts) - 1))

    if za is None or zb is None or network_kind(pa.get("layer") or "") != "pressure":
        return None
    ea, eb = _extremo(pa), _extremo(pb)
    if ea == eb:
        return None
    pasa, termina = (pb, pa) if ea else (pa, pb)
    if not _quiebre(pasa):
        return None
    da, db = float(pa.get("diam") or 4), float(pb.get("diam") or 4)
    dz = abs((za + da / 24.0) - (zb + db / 24.0))
    minimo = desnivel_min_dos_codos_ft(min(da, db))
    if dz >= minimo:
        return None
    return {"dz": dz, "min": minimo, "termina": termina}


def _giro_deg(a, b, c):
    ux, uy, wx, wy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
    lu, lw = math.hypot(ux, uy), math.hypot(wx, wy)
    if lu < 1e-12 or lw < 1e-12:
        return 0.0
    cos = max(-1.0, min(1.0, (ux * wx + uy * wy) / (lu * lw)))
    return math.degrees(math.acos(cos))


def escalones_en_vertices(pipes, z_at, tol=0.01):
    """Vértices de una MISMA utilidad a presión donde el tramo que llega y el
    que sale tienen soleras distintas (un escalón, p. ej. editado en «Cotas por
    tramo»). El plugin no puede dibujar ese escalón en una red a presión: une
    los dos extremos en la cota PROMEDIO (ver «[COTAS] cotas unificadas» en
    ImportarRed). En gravedad no se avisa: ahí es una caída en el buzón.

    `z_at(i_pipe, i_tramo, x, y)` da la solera del tramo en ese punto.
    Devuelve [{"x", "y", "pipe", "llega", "sale", "z_llega", "z_sale", "z_civil"}]
    con `llega`/`sale` = número de tramo (1 = T1) como en la tabla."""
    salida = []
    for i, p in enumerate(pipes):
        if network_kind(p.get("layer") or "") != "pressure":
            continue
        pts = p.get("pts") or []
        for v in range(1, len(pts) - 1):
            x, y = pts[v]
            z_llega, z_sale = z_at(i, v - 1, x, y), z_at(i, v, x, y)
            if z_llega is None or z_sale is None or abs(z_llega - z_sale) <= tol:
                continue
            salida.append({"x": x, "y": y, "pipe": i, "llega": v, "sale": v + 1,
                           "z_llega": z_llega, "z_sale": z_sale,
                           "z_civil": (z_llega + z_sale) / 2.0})
    return salida


# Máximo de tramos que el plugin une con UN accesorio (la Cruz). Con más, el
# plugin no dibuja ninguna pieza y deja la juntura sin resolver.
MAX_TRAMOS_POR_ACCESORIO = 4


def junturas_excedidas(pipes, z_at, tol_px, z_tol=0.10, maximo=MAX_TRAMOS_POR_ACCESORIO):
    """Puntos donde se juntan MÁS de `maximo` tramos que el plugin intentaría
    unir con un solo accesorio. Replica la regla del plugin
    (ProcesarJunturasPresion + agrupación por cota de ImportarRed):

      - solo redes de PRESIÓN: en gravedad/conduit un buzón o una estructura
        nula acepta los tubos que haga falta;
      - cuenta TRAMOS (un tubo que pasa por un vértice aporta dos), que es lo
        que cuenta el plugin: el caso de 3 polilíneas en cruz + ramal son 5;
      - misma red (nombre de red o, si no hay, la capa) y misma cota: cada
        utilidad promedia su cota en el punto y utilidades distintas solo se
        juntan a ≤ `z_tol`.

    `z_at(i_pipe, i_tramo, x, y)` da la solera del tramo en ese punto.
    Devuelve [{"x", "y", "n", "red"}] con n > maximo."""
    extremos = []                                   # (x, y, red, i_pipe, z)
    for i, p in enumerate(pipes):
        capa = p.get("layer") or ""
        if network_kind(capa) != "pressure":
            continue
        red = red_de(p)
        pts = p.get("pts") or []
        for k in range(len(pts) - 1):
            for (x, y) in (pts[k], pts[k + 1]):
                z = z_at(i, k, x, y)
                extremos.append((x, y, red, i, 0.0 if z is None else float(z)))

    tol2 = tol_px * tol_px
    usado = [False] * len(extremos)
    salida = []
    for a in range(len(extremos)):
        if usado[a]:
            continue
        usado[a] = True
        grupo = [a]
        sx, sy = extremos[a][0], extremos[a][1]
        for b in range(a + 1, len(extremos)):
            if usado[b] or extremos[b][2] != extremos[a][2]:
                continue
            cx, cy = sx / len(grupo), sy / len(grupo)
            if (extremos[b][0] - cx) ** 2 + (extremos[b][1] - cy) ** 2 > tol2:
                continue
            usado[b] = True
            grupo.append(b)
            sx += extremos[b][0]; sy += extremos[b][1]
        if len(grupo) <= maximo:
            continue
        # Por utilidad: cada una su cota media; luego se encadenan por cota.
        por_pipe = {}
        for e in grupo:
            por_pipe.setdefault(extremos[e][3], []).append(e)
        sub = sorted(((len(v), sum(extremos[e][4] for e in v) / len(v)) for v in por_pipe.values()),
                     key=lambda s: s[1])
        cadenas = [[sub[0]]]
        for s in sub[1:]:
            if abs(s[1] - cadenas[-1][-1][1]) <= z_tol:
                cadenas[-1].append(s)
            else:
                cadenas.append([s])
        for c in cadenas:
            n = sum(cuantos for cuantos, _z in c)
            if n > maximo:
                salida.append({"x": sx / len(grupo), "y": sy / len(grupo), "n": n,
                               "red": extremos[a][2]})
    return salida


def choques_sin_conexion(pipes, z_at, tol_px, structures=(), z_tol=0.10):
    """Cruces COMPLETOS a la misma cota que Civil 3D no conecta, cuando al menos
    una de las dos tuberías NO es a presión (los cruces entre dos redes a
    presión los clasifica `Main._draw_pipe_conflicts`: accesorio, conflicto o
    «redes distintas»). Pedido del usuario 2026-09-29: dos utilidades
    cualesquiera que se atraviesan a la misma cota sin conexión se avisan para
    que corrija el dibujo o las cotas.

      - cruce completo: las DOS pasan por el punto (ninguna termina ahí, a
        ≤ `tol_px` de su primer o último vértice); un extremo que llega a otra
        tubería es una unión (buzón, caja) o se ve en otro aviso;
      - misma cota: soleras en el punto a ≤ `z_tol` (sin cota no se puede
        confirmar el choque: no se avisa);
      - sin conexión: utilidades distintas nunca se conectan; la MISMA de
        gravedad se une si las dos tienen un vértice ahí (el buzón del
        vértice); la misma de conduit, solo si además hay una CAJA ahí (sin
        caja el plugin no pone estructura en el vértice).

    `z_at(i_pipe, i_tramo, x, y)` da la solera del tramo en ese punto.
    Devuelve [{"x", "y", "ia", "ib", "za", "zb"}], uno por punto."""
    tol2 = tol_px * tol_px

    def _cerca(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= tol2

    def _inter(p1, p2, p3, p4):
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p1, p2, p3, p4
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-9:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
        if not (-1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6):
            return None
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    datos = []
    for i, p in enumerate(pipes):
        pts = p.get("pts") or []
        if p.get("world") or len(pts) < 2:
            continue
        datos.append((i, p.get("layer") or "", network_kind(p.get("layer") or ""), pts))
    cajas = [(float(s.get("x", 1e12)), float(s.get("y", 1e12))) for s in structures or ()
             if (s.get("net") or "") == "conduit" and not s.get("curve") and not s.get("world")]
    salida = []
    for a in range(len(datos)):
        ia, la, na, pa = datos[a]
        for b in range(a + 1, len(datos)):
            ib, lb, nb, pb = datos[b]
            if na == "pressure" and nb == "pressure":
                continue
            for ka in range(len(pa) - 1):
                for kb in range(len(pb) - 1):
                    cp = _inter(pa[ka], pa[ka + 1], pb[kb], pb[kb + 1])
                    if cp is None:
                        continue
                    if any(_cerca(cp, q) for q in (pa[0], pa[-1], pb[0], pb[-1])):
                        continue                         # una termina ahí: no atraviesa
                    if any(_cerca(cp, (e["x"], e["y"])) for e in salida):
                        continue
                    za, zb = z_at(ia, ka, cp[0], cp[1]), z_at(ib, kb, cp[0], cp[1])
                    if za is None or zb is None or abs(za - zb) > z_tol:
                        continue
                    if la == lb and any(_cerca(cp, q) for q in pa) and any(_cerca(cp, q) for q in pb):
                        if na == "gravity":
                            continue                     # el buzón del vértice las une
                        if na == "conduit" and any(_cerca(cp, c) for c in cajas):
                            continue                     # la caja las une
                    salida.append({"x": cp[0], "y": cp[1], "ia": ia, "ib": ib,
                                   "za": float(za), "zb": float(zb)})
    return salida


# ── SÓLIDOS: cajas cuadradas reconocidas del PDF (conduit) ──────────────────
# Una caja de eléctrico/telecom reconocida con su contorno RECTANGULAR no es una
# estructura del catálogo: se lista en «Buzones» como SÓLIDO-N, sin familia ni
# tamaño de catálogo, con largo × ancho (del plano, editables) y altura
# (`solid_height_ft`, por defecto 2 m); en Civil 3D se dibuja como Solid3d.
SOLID_DEFAULT_H_FT = 6.56168
SOLID_PREFIX = "SÓLIDO-"


def is_solid(s):
    """¿La estructura es un SÓLIDO? (caja conduit con contorno rectangular)."""
    return (not s.get("curve") and not s.get("world")
            and (s.get("net") or "") == "conduit"
            and (s.get("shape") or "") == "rect"
            and bool(s.get("outline")) and len(s.get("outline") or []) >= 4)


def normalize_solids(structures):
    """Marca los sólidos (`solid=True`), les quita familia/tamaño de catálogo,
    pone la altura por defecto y los renombra de CAJA-N a SÓLIDO-N (un código
    puesto a mano por el usuario se respeta). Idempotente."""
    used = {s.get("cod", "") for s in structures if s.get("cod")}
    n = 1
    for s in structures:
        if not is_solid(s):
            s.pop("solid", None)
            continue
        s["solid"] = True
        s["part"] = ""; s["part_size"] = ""
        if not s.get("solid_height_ft"):
            s["solid_height_ft"] = SOLID_DEFAULT_H_FT
        cod = s.get("cod") or ""
        if not cod or cod.startswith("CAJA-"):
            used.discard(cod)
            while f"{SOLID_PREFIX}{n}" in used:
                n += 1
            s["cod"] = f"{SOLID_PREFIX}{n}"; used.add(s["cod"]); n += 1
    return structures


def solid_center(s):
    """Centro del contorno del sólido (px)."""
    o = s.get("outline") or []
    return (sum(x for x, _ in o) / len(o), sum(y for _, y in o) / len(o))


def solid_axes(s):
    """(u_largo, u_ancho): vectores unitarios de los lados del contorno (px)."""
    o = s["outline"]
    e1 = (o[1][0] - o[0][0], o[1][1] - o[0][1])
    e2 = (o[2][0] - o[1][0], o[2][1] - o[1][1])
    l1, l2 = math.hypot(*e1), math.hypot(*e2)
    if l1 < 1e-9 or l2 < 1e-9:
        return (1.0, 0.0), (0.0, 1.0)
    a, b = ((e1[0] / l1, e1[1] / l1), (e2[0] / l2, e2[1] / l2))
    return (a, b) if l1 >= l2 else (b, a)


def resize_solid(s, length_ft, width_ft, px_per_ft):
    """Cambia largo × ancho del sólido y rehace su contorno a escala, con el
    mismo centro y giro (lo que se ve en el lienzo)."""
    length_ft = max(float(length_ft), 0.01); width_ft = max(float(width_ft), 0.01)
    cx, cy = solid_center(s)
    ul, uw = solid_axes(s)
    hl = length_ft * px_per_ft / 2.0; hw = width_ft * px_per_ft / 2.0
    s["outline"] = [(cx + sl * hl * ul[0] + sw * hw * uw[0], cy + sl * hl * ul[1] + sw * hw * uw[1])
                    for sl, sw in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    s["length_ft"] = length_ft; s["width_ft"] = width_ft
