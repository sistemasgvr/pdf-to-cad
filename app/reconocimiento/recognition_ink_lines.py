"""recognition_ink_lines.py — líneas CONTINUAS de una capa por estilo: la tinta es el eje (PURO).

El núcleo (`recognition_geom.reconstruct`) está hecho para el tipo de línea CAD
«explotado»: guiones + letras + huecos, que arma en rectas y une por intersecciones.
Un mapa SIG aplanado (Quarter Section de Phoenix, pedido del usuario 2026-10-10) dibuja
cada tubería como UN trazo continuo de buzón a buzón, con las curvas en cuerdas cortas;
ahí el núcleo partía la curva en rectas y la esquina caía hasta 5 pt FUERA de la tinta
(«no inventar»). En esas capas la tinta YA es la línea:

  · `continuous_layer(paths)`: la capa es de trazos continuos si casi ninguna punta
    tiene enfrente, a un hueco de guion, otra punta en su misma recta (un linetype a
    guiones las tiene casi todas) y la mayor parte de la tinta va en trazos largos.
  · `ink_reconstruct(paths, vault_paths, opts)`: un `GeomResult` cuyas polilíneas son
    los trazos tal cual (curvas Bézier en puntos), sin mover nada: los vértices
    interiores «bend», las puntas «junction» (la comparte otro trazo), «tee» (muere
    sobre otro trazo), «cut» (cortada por el clip del PDF) o «end». Las bóvedas
    salen del núcleo como siempre (sin líneas). Unir trazos (rutas), codos desde la
    tinta, imán a bóvedas… siguen igual río abajo.
Solo se usa en capas por ESTILO (`pdf_styles`): las capas CAD con nombre no cambian.
"""
from __future__ import annotations

import bisect
import math
from typing import List, Sequence, Tuple

from reconocimiento import recognition_geom as geom
from reconocimiento import recognition_indice as indice_mod

Pt = Tuple[float, float]

NODE_TOL_PT = 0.6            # puntas a ≤ esto: el mismo nodo
TEE_TOL_PT = 0.5             # punta a ≤ esto del interior de otro trazo: T
LONG_CHAIN_PT = 25.0         # trazo «largo»
GAP_MIN_PT, GAP_MAX_PT = 0.8, 20.0   # hueco de guion: otra punta enfrente a esta distancia…
GAP_DIR_DEG = 10.0           # …en la misma recta (±)
MAX_GAP_SHARE = 0.25         # continua: ≤ esto de las puntas con hueco de guion enfrente
MIN_LONG_SHARE = 0.6         # …y ≥ esto de la tinta en trazos largos
SYMBOL_MAX_PT = 20.0         # trazo CERRADO más chico que esto: símbolo, no tubería
BEZIER_STEP_PT = 2.0         # muestreo de una curva Bézier
SIMPLIFY_PT = 0.5            # tolerancia MÁXIMA del trazo simplificado (= núcleo, SOFT_SIMPLIFY_PT)
SIMPLIFY_MIN_PT = 0.15       # …y mínima (la tinta viene cuantizada a 0.1875 pt: menos es ruido)
# Costura de una hoja COMPUESTA de mapas (`_soldar_costuras`, reporte del usuario 2026-10-19)
COSTURA_HUECO_PT = 2.5       # hueco máximo entre las dos puntas de la misma tubería en la costura
COSTURA_DIR_DEG = 20.0       # se miran: rumbos opuestos (± esto)…
COSTURA_ADELANTE_DEG = 35.0  # …y la otra punta va ADELANTE de la cortada (± esto de su rumbo)
COSTURA_LADO_PT = 0.5        # o las dos cortadas sobre la costura, una al lado de la otra
COSTURA_DOBLE_PT = 0.3       # trozo de una pieza todo a ≤ esto de la línea de OTRA: la misma tinta dos veces
COSTURA_T_DEG = 30.0         # un ramal llega a la línea de la otra pieza cruzándola (no casi paralelo)


def _p(q) -> Pt:
    return float(q[0]), float(q[1])


def _bezier(p0, p1, p2, p3, n: int) -> List[Pt]:
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def chains(path: dict) -> List[List[Pt]]:
    """Ristras CONECTADAS de un trazo (un trazo puede traer varios subtrazos)."""
    out: List[List[Pt]] = []
    cur: List[Pt] = []
    for it in path.get("items") or ():
        kind = it[0]
        if kind not in ("l", "c"):
            if len(cur) >= 2:
                out.append(cur)
            cur = []
            continue
        a = _p(it[1])
        if cur and math.dist(cur[-1], a) > 0.05:
            if len(cur) >= 2:
                out.append(cur)
            cur = []
        if not cur:
            cur.append(a)
        if kind == "l":
            cur.append(_p(it[2]))
        else:
            p0, p1, p2, p3 = a, _p(it[2]), _p(it[3]), _p(it[4])
            n = max(2, math.ceil((math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)) / BEZIER_STEP_PT))
            cur.extend(_bezier(p0, p1, p2, p3, n))
    if len(cur) >= 2:
        out.append(cur)
    return out


def _length(pts: Sequence[Pt]) -> float:
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


def _closed_symbol(ch: Sequence[Pt]) -> bool:
    if math.dist(ch[0], ch[-1]) > NODE_TOL_PT:
        return False
    xs, ys = [p[0] for p in ch], [p[1] for p in ch]
    return max(max(xs) - min(xs), max(ys) - min(ys)) < SYMBOL_MAX_PT


def _unit(a: Pt, b: Pt):
    L = math.dist(a, b)
    return None if L < 1e-9 else ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def _end_dirs(ch: Sequence[Pt]):
    """[(punta, dirección hacia AFUERA)] de una ristra abierta."""
    return [(ch[0], _unit(ch[1], ch[0])), (ch[-1], _unit(ch[-2], ch[-1]))]


def layer_chains(paths: Sequence[dict]) -> List[List[Pt]]:
    """Ristras de la capa sin símbolos cerrados chicos (válvulas, hidrantes)."""
    return [ch for p in paths for ch in chains(p) if not _closed_symbol(ch)]


def continuous_layer(paths: Sequence[dict]) -> bool:
    """¿Trazos continuos (mapa SIG / línea continua) y no un tipo de línea a guiones?"""
    chs = layer_chains(paths)
    total = sum(_length(c) for c in chs)
    if not chs or total <= 0:
        return False
    long_share = sum(_length(c) for c in chs if _length(c) >= LONG_CHAIN_PT) / total
    ends = [(p, d) for ch in chs for p, d in _end_dirs(ch) if d is not None]
    cos_tol = math.cos(math.radians(GAP_DIR_DEG))
    grid = {}
    for i, (p, _d) in enumerate(ends):
        grid.setdefault((int(p[0] // GAP_MAX_PT), int(p[1] // GAP_MAX_PT)), []).append(i)
    facing = 0
    for i, (p, d) in enumerate(ends):
        gx, gy = int(p[0] // GAP_MAX_PT), int(p[1] // GAP_MAX_PT)
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j == i:
                        continue
                    q, e = ends[j]
                    gap = math.dist(p, q)
                    if not GAP_MIN_PT <= gap <= GAP_MAX_PT:
                        continue
                    u = _unit(p, q)
                    # la otra punta está ADELANTE de esta, en su recta, y mira hacia acá
                    if u and d[0] * u[0] + d[1] * u[1] >= cos_tol and e[0] * u[0] + e[1] * u[1] <= -cos_tol:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        facing += hit
    return facing <= MAX_GAP_SHARE * len(ends) and long_share >= MIN_LONG_SHARE


def _douglas_peucker(pts: List[Pt], tol: float) -> List[Pt]:
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        worst, k = -1.0, -1
        for m in range(i + 1, j):
            d = _seg_dist(pts[m], a, b)[1]
            if d > worst:
                worst, k = d, m
        if worst > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, k in zip(pts, keep) if k]


def simplify_tol(paths: Sequence[dict]) -> float:
    """Tolerancia de la simplificación: la MITAD del grosor del trazo (el eje nunca sale de
    la línea dibujada), entre `SIMPLIFY_MIN_PT` y `SIMPLIFY_PT`. Con 0.5 fijo la tubería de
    agua de Phoenix (0.38 pt) cortaba las curvas por cuerdas a 0.45 pt de su tinta: fuera
    del trazo (reporte del usuario 2026-10-14, «los quiebres no son precisos»)."""
    from hoja import pdf_styles
    ws = sorted(w for w in (p.get("width") or pdf_styles.style_width(p.get("layer") or "") for p in paths) if w)
    if not ws:
        return SIMPLIFY_PT
    return min(SIMPLIFY_PT, max(SIMPLIFY_MIN_PT, 0.5 * ws[len(ws) // 2]))


def _thin(pts: List[Pt], tol: float = SIMPLIFY_PT) -> List[Pt]:
    """Sin puntos repetidos y sin el ZIGZAG del trazo: un mapa SIG mete cuerdas de
    0.4–1.5 pt que van y vuelven ±0.3 pt alrededor de la línea (Phoenix 17-10: una
    tubería recta con 11 cuerdas y giros de ±17°). Douglas–Peucker a `tol`
    (`simplify_tol`): la línea queda a ≤ esto de su tinta."""
    out = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, out[-1]) > 1e-6:
            out.append(p)
    if len(out) <= 2:
        return out
    if math.dist(out[0], out[-1]) <= NODE_TOL_PT:          # cerrada: partir en el punto más lejano
        far = max(range(len(out)), key=lambda m: math.dist(out[0], out[m]))
        return _douglas_peucker(out[:far + 1], tol)[:-1] + _douglas_peucker(out[far:], tol)
    return _douglas_peucker(out, tol)


def _seg_dist(p: Pt, a: Pt, b: Pt) -> Tuple[float, float]:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 < 1e-12:
        return 0.0, math.dist(p, a)
    t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2
    t = min(1.0, max(0.0, t))
    return t, math.dist(p, (a[0] + t * vx, a[1] + t * vy))


def _soldar_costuras(chs: List[List[Pt]], piezas: list, cut_pts: List[Pt], i_cut) -> int:
    """Hoja COMPUESTA de mapas (reporte del usuario 2026-10-19: «deben tener continuidad»): la
    punta de una tubería CORTADA por el recorte de su pieza y la punta de la MISMA tubería en la
    pieza vecina quedan separadas hasta un par de pt —cada mapa termina su línea
    donde termina su cuarto de sección y la costura cae entre los dos—, así que nunca se unían.
    Se unen en un punto común si se miran (rumbos opuestos ± `COSTURA_DIR_DEG`), a ≤
    `COSTURA_HUECO_PT`, y: la otra punta va ADELANTE de la cortada (la tinta de la pieza cortada
    sigue bajo la vecina hasta ahí) → la cortada se prolonga hasta ella; o las dos están cortadas
    sobre la costura una al lado de la otra → las dos van al punto medio. Una vez cada punta, de
    la pareja más cercana a la más lejana. Devuelve cuántas."""
    ends = []
    for i, ch in enumerate(chs):
        for j in (0, -1):
            p = ch[j]
            d = _unit(ch[1] if j == 0 else ch[-2], p)          # hacia AFUERA
            cut = any(math.dist(p, cut_pts[k]) <= NODE_TOL_PT for k in i_cut.cerca(p))
            ends.append((i, j, p, d, cut))
    idx = indice_mod.IndicePuntos([e[2] for e in ends], COSTURA_HUECO_PT)
    mira = math.cos(math.radians(COSTURA_DIR_DEG))
    adelante = math.cos(math.radians(COSTURA_ADELANTE_DEG))
    parejas = []
    for a, (i, _j, p, d, cut) in enumerate(ends):
        if not cut or d is None:
            continue
        for b in idx.cerca(p):
            o, _k, q, e, cut_q = ends[b]
            if o == i or piezas[o] == piezas[i] or e is None:
                continue
            g = math.dist(p, q)
            if not NODE_TOL_PT < g <= COSTURA_HUECO_PT or d[0] * e[0] + d[1] * e[1] > -mira:
                continue
            along = ((q[0] - p[0]) * d[0] + (q[1] - p[1]) * d[1])
            if along >= adelante * g:
                parejas.append((g, a, b, q))
            elif cut_q and abs(along) <= COSTURA_LADO_PT:
                parejas.append((g, a, b, ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)))
    usados: set = set()
    n = 0

    def alargar(e, w):
        i, j, p, _d, _c = ends[e]
        if math.dist(p, w) <= 1e-9:
            return
        if j == 0:
            chs[i].insert(0, w)
        else:
            chs[i].append(w)
    for g, a, b, w in sorted(parejas, key=lambda t: (t[0], t[1], t[2])):
        if a in usados or b in usados:
            continue
        usados |= {a, b}
        alargar(a, w)
        alargar(b, w)
        n += 1
    # …o la punta cortada llega, por su recta, a la LÍNEA de la otra pieza (un ramal cortado en
    # la costura justo antes de la principal que dibuja la hoja vecina): T en el cruce. Solo si
    # la cruza (≥ `COSTURA_T_DEG`): casi paralela es la misma línea, y esa va punta con punta
    sen_t = math.sin(math.radians(COSTURA_T_DEG))
    tramos = [(o, a, b) for o, ch in enumerate(chs) for a, b in zip(ch, ch[1:])]
    i_tr = indice_mod.IndiceTramos([[(a, b)] for _o, a, b in tramos], COSTURA_HUECO_PT)
    for e, (i, _j, p, d, cut) in enumerate(ends):
        if e in usados or not cut or d is None:
            continue
        best = None
        for m in sorted({k for s in (0.0, 0.5, 1.0) for k, _t in
                         i_tr.cerca((p[0] + s * COSTURA_HUECO_PT * d[0], p[1] + s * COSTURA_HUECO_PT * d[1]))}):
            o, a, b = tramos[m]
            if o == i or piezas[o] == piezas[i]:
                continue
            L = math.dist(a, b)
            if L < 1e-9 or abs(d[0] * (b[1] - a[1]) - d[1] * (b[0] - a[0])) / L < sen_t:
                continue
            t = _cruce(p, d, a, b)
            if t is not None and 1e-6 < t <= COSTURA_HUECO_PT and (best is None or t < best):
                best = t
        if best is not None:
            alargar(e, (p[0] + best * d[0], p[1] + best * d[1]))
            usados.add(e)
            n += 1
    return n


def _cruce(p: Pt, d: Pt, a: Pt, b: Pt):
    """Distancia por el rayo p + t·d hasta el tramo a–b (None si no lo corta)."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = d[0] * ey - d[1] * ex
    if abs(den) < 1e-9:
        return None
    wx, wy = a[0] - p[0], a[1] - p[1]
    t = (wx * ey - wy * ex) / den
    s = (wx * d[1] - wy * d[0]) / den
    return t if -1e-9 <= s <= 1 + 1e-9 else None


def _sin_dobles(chs: List[List[Pt]], recortes: list, piezas: list):
    """Hoja COMPUESTA: dos mapas vecinos dibujan la misma tubería en su franja común; una que
    corre PEGADA a la costura queda con trocitos de las dos piezas (los trazos largos repetidos
    ya los quitó `recognition_dupink`). Sale el trozo que va todo a ≤ `COSTURA_DOBLE_PT` de la
    línea de OTRA pieza (la más larga se queda)."""
    largos = [_length(c) for c in chs]
    tramos = [list(zip(c, c[1:])) for c in chs]
    idx = indice_mod.IndiceTramos(tramos, COSTURA_DOBLE_PT)
    fuera = set()
    for i, ch in enumerate(chs):
        muestras = list(ch) + [((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0) for a, b in tramos[i]]
        cand = {o for q in muestras[:1] for o, _k in idx.cerca(q)}
        for o in sorted(cand):
            if (o == i or o in fuera or piezas[o] == piezas[i]
                    or (largos[o], -o) < (largos[i], -i)):
                continue
            if all(min(_seg_dist(q, a, b)[1] for a, b in tramos[o]) <= COSTURA_DOBLE_PT for q in muestras):
                fuera.add(i)
                break
    if not fuera:
        return chs, recortes, piezas
    keep = [k for k in range(len(chs)) if k not in fuera]
    return [chs[k] for k in keep], [recortes[k] for k in keep], [piezas[k] for k in keep]


def ink_reconstruct(paths: Sequence[dict], vault_paths: Sequence[dict] = (),
                    opts: "geom.GeomOptions" = None, stats: dict = None,
                    inicios: Sequence[int] = None) -> "geom.GeomResult":
    """`GeomResult` con la TINTA como polilíneas (ver el docstring del módulo). `stats` (dict):
    suma en «costuras» las tuberías unidas en la costura de una hoja compuesta. `inicios`: en una
    hoja COMPUESTA, dónde empieza cada pieza en el orden de dibujo (`inicios_de_piezas`)."""
    base = geom.reconstruct([], vault_paths, opts or geom.GeomOptions())
    cut_pts = [_p(q) for p in paths for q in (p.get("cut_pts") or ())]
    tol = simplify_tol(paths)
    # cada ristra con los RECORTES de su trazo: en una hoja compuesta cada pieza trae el suyo
    chs, recortes, piezas = [], [], []
    for p in paths:
        clave = tuple(p.get("clip_polys") or ())
        for ch in chains(p):
            if _closed_symbol(ch):
                continue
            t = _thin(ch, tol)
            if len(t) >= 2 and _length(t) > 0:
                chs.append(t)
                recortes.append(clave)
                seq = p.get("seqno")
                piezas.append(bisect.bisect_right(inicios, int(seq)) - 1 if inicios and seq is not None else -1)
    # hoja COMPUESTA de verdad (piezas del compositor): una hoja suelta también trae trazos con
    # recortes distintos (el marco de la vista y lo que va fuera), y ahí nada de esto aplica
    compuesta = bool(inicios) and len(set(piezas)) > 1
    if compuesta:
        chs, recortes, piezas = _sin_dobles(chs, recortes, piezas)
    # índices espaciales (`recognition_indice`): cada punta mira solo lo que tiene cerca, no
    # todas las de la hoja (una hoja compuesta de mapas trae decenas de miles); mismo resultado
    i_cut = indice_mod.IndicePuntos(cut_pts, NODE_TOL_PT)
    n_costuras = _soldar_costuras(chs, piezas, cut_pts, i_cut) if compuesta else 0
    if stats is not None:
        stats["costuras"] = stats.get("costuras", 0) + n_costuras
    ends = [(i, 0, ch[0]) for i, ch in enumerate(chs)] + [(i, -1, ch[-1]) for i, ch in enumerate(chs)]
    i_ends = indice_mod.IndicePuntos([q for _o, _s, q in ends], NODE_TOL_PT)
    tramos = [list(zip(oc, oc[1:])) for oc in chs]
    i_tramos = indice_mod.IndiceTramos(tramos, TEE_TOL_PT)
    polylines = []
    for i, ch in enumerate(chs):
        kinds = ["bend"] * len(ch)
        for j in (0, len(ch) - 1):
            p = ch[j]
            cerca = [ends[k] for k in i_ends.cerca(p)]
            if any(math.dist(p, cut_pts[k]) <= NODE_TOL_PT for k in i_cut.cerca(p)):
                # Costura de una hoja COMPUESTA (pedido del usuario 2026-10-14, mapas de Phoenix
                # unidos solos): ahí llega la punta de la misma tubería desde OTRA pieza (otro
                # recorte) → la línea sigue. En una hoja suelta todos los trazos comparten su
                # recorte: el corte en el borde de la vista sigue siendo «cut».
                # Hoja compuesta (2026-10-19): también sigue si ahí termina otro trazo de la
                # MISMA pieza (una tubería pegada a la costura, a ≤ 0.25 pt, queda con cada
                # vértice marcado como corte: el SIG exporta cada tramo aparte) o si la punta
                # cae sobre la línea de la pieza vecina (llega a ella: T).
                if any(o != i and math.dist(p, q) <= NODE_TOL_PT and (compuesta or recortes[o] != recortes[i])
                       for o, _s, q in cerca):
                    kinds[j] = "junction"
                elif compuesta and any(o != i and piezas[o] != piezas[i]
                                       and _seg_dist(p, *tramos[o][k])[1] <= TEE_TOL_PT
                                       for o, k in i_tramos.cerca(p)):
                    kinds[j] = "tee"
                else:
                    kinds[j] = "cut"
            elif any(o != i and math.dist(p, q) <= NODE_TOL_PT for o, _s, q in cerca):
                kinds[j] = "junction"
            elif any(o != i and _seg_dist(p, *tramos[o][k])[1] <= TEE_TOL_PT for o, k in i_tramos.cerca(p)):
                kinds[j] = "tee"
            else:
                kinds[j] = "end"
        polylines.append(geom.Polyline(list(ch), kinds))
    n = len(chs)
    return geom.GeomResult(polylines=polylines, nodes=base.nodes, vaults=base.vaults, pattern=None,
                           coverage=1.0, uncovered=[], vault_orphans=base.vault_orphans,
                           offpattern=[], n_dashes=n, n_glyphs=0, n_curves=0, n_noise=0,
                           markers=[], glyphs=[])
