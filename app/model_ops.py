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
import math

from model import network_kind, LEADER_TEXT_FT

_TOL = 14.0   # tolerancia de coincidencia de coordenadas (px), compartida por ambas


def pipe_at_vertex(pipes, x, y, tol=14.0):
    """Tubería (dict, no 'world') cuyo pts tiene un vértice a distancia <= tol
    de (x,y), o None. La familia/tamaño de un elemento curvo se hereda de esta
    tubería — nunca se elige aparte, para que la curva calce con los tramos rectos."""
    tol2 = tol * tol
    for p in pipes:
        if p.get("world") or not p.get("pts"): continue
        for (vx, vy) in p["pts"]:
            if (vx - x) ** 2 + (vy - y) ** 2 <= tol2:
                return p
    return None


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
      - Conduit (eléctrico/telecom) → prefijo CAJA- (cajas de registro/vaults).
      - Presión (agua/gas) → sin nodos automáticos.
    Preserva ediciones (cod/rim/sump/part/part_size/covered) por coincidencia
    de coordenada. Los buzones importados de Excel (world) se conservan aparte.
    Devuelve la lista nueva de estructuras (world + detectadas)."""
    tol = _TOL
    def near(a, b): return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
    # Descarta buzones espurios de versiones previas con net inválida (p.ej. "pressure").
    old = [s for s in structures
           if not s.get("world") and (s.get("net") or "gravity") in ("gravity", "conduit")]
    world = [s for s in structures if s.get("world")]
    detected = []
    for p in pipes:
        if p.get("world"): continue
        kind = network_kind(p.get("layer") or "")
        if kind not in ("gravity", "conduit"): continue    # presión no lleva nodos automáticos
        pts = p.get("pts")
        if not pts or len(pts) < 2: continue
        for pt in pts:                              # todos los vértices (extremos + intermedios)
            if not any(near(pt, (s["x"], s["y"])) for s in detected):
                detected.append({"cod": "", "x": pt[0], "y": pt[1], "rim": None,
                                 "sump": None, "part": "", "part_size": "",
                                 "net": kind, "covered": True, "world": False,
                                 "hidden": False})
    for s in detected:                                 # reasigna ediciones previas por coordenada
        for o in old:
            if near((s["x"], s["y"]), (o.get("x", -1e9), o.get("y", -1e9))):
                s.update(cod=o.get("cod", ""), rim=o.get("rim"), sump=o.get("sump"),
                         part=o.get("part", ""), part_size=o.get("part_size", ""),
                         covered=bool(o.get("covered", True)),
                         height_ft=o.get("height_ft", 0.0),
                         curve=bool(o.get("curve", False)),
                         radius_ft=o.get("radius_ft", 0.0),
                         hidden=bool(o.get("hidden", False))); break
    # Códigos únicos: BZ-N gravedad, CAJA-N conduit, CV-N esquina de elemento curvo
    # (curve=True manda sobre el prefijo por red: no es un buzón/caja real).
    used = {s.get("cod", "") for s in world + detected if s.get("cod")}
    cnt_bz = cnt_caja = cnt_cv = 1
    for s in detected:
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
    return world + detected


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
