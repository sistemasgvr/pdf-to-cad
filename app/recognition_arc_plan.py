"""Plan de codos de la 2.ª pasada (tinta): rectas, nodos, círculo tangente y anclas.

Recibe los arcos de tinta de UNA polilínea (`recognition_arcs.group_arcs`) y sus
rectas de tinta, y devuelve entradas del plan de `recognition.fit_fillets` (mismo
formato que la 1.ª pasada) más las posiciones nuevas de los anclas. PURO (sin Qt ni
fitz). Reglas y medidas: ver `recognition_arcs.py` y CLAUDE.md.
"""
from __future__ import annotations

import math
from typing import Sequence

import recognition_arc_chain as chain_mod
from recognition_arcs import (ARC_CORRIDOR_PT, ARC_R_MIN_PT, STRAIGHT_MIN_PT, ArcGroup, Pt,
                              _cumlen, _seg_dist, _tangent_at, _unit, arc_cover,
                              fit_circle_line_node, fit_circle_two_nodes, project)

LEG_INK_SEG_MIN_PT = 3.0     # recta de tinta que sirve de recta del codo (no el palito de una letra)
LEG_SEARCH_PT = 80.0         # se busca hasta aquí del fin del arco (hueco + letra del linetype)
LEG_ALIGN_DEG = 10.0         # con el rumbo de la polilínea ahí
INK_FIT_TOL_PT = 0.5         # RMS del círculo TANGENTE a las rectas contra la tinta del arco
INK_FIT_MAX_PT = 0.75        # …y ningún punto de esa tinta más lejos que esto
INK_LOOSE_TOL_PT = 1.0       # = FILLET_FIT_TOL_PT: hasta aquí el codo se acepta APROXIMADO
INK_LOOSE_MAX_PT = 1.5       # (`loose`: se dibuja a trazos y se avisa con el desvío)
INK_MIN_TURN_DEG = 3.0       # curvas muy abiertas: el plugin y el editor dibujan desde 2°
INK_EDGE_IN_PT = 1.5         # la tangencia puede caer así de DENTRO de la tinta del arco
INK_EDGE_SLIP_PT = 12.0      # = FILLET_TANGENT_SLIP_PX: …o así de lejos del fin de la tinta (hueco)
INK_COVER = 0.45             # = FILLET_INK_COVER
ON_ARC_TOL_PT = 0.25         # cuerda de OTRO trozo de tinta que va SOBRE el círculo (extremos y medio)
END_DASH_LEAVE_PT = 1.0      # …y la recta de su guión se APARTA del círculo al menos esto (en su punta):
                             # en un arco muy abierto (r ≈ 900 pt) un guión recto no se distingue del arco
DROP_TOL_PT = 1.5            # un vértice que el codo quita está a ≤ esto de recta–arco–recta
ANCHOR_NODE_TOL_PT = 0.5     # un ancla que no se mueve (nodo) tiene que estar así de cerca de la recta
LINE_REFINE_OFF_PT = 0.3     # guiones de la MISMA recta (su rumbo se ajusta con todos)
SHARED_LEG_TOL_PT = 1.0      # la recta de un codo de la 1.ª pasada es «la misma» a ≤ esto
NODE_TERMINAL_KINDS = ("tee", "junction", "vault", "stop", "edge", "end", "cut")
SOFT_DROP_KINDS = ("bend", "corner", "curve")


def ink_fillet_plan(pts, kinds, groups: Sequence[ArcGroup], straights, taken, through_dirs,
                    f: float = 1.0, debug=None, all_groups: Sequence[ArcGroup] = None,
                    arc_ends=None):
    """Codos de los arcos de tinta que la 1.ª pasada no cubrió: (entradas del plan
    de `fit_fillets`, mismo formato; {índice: posición nueva} de los anclas).
    Rectas de cada lado = RECTAS DE TINTA (todos sus guiones), la línea que PASA por
    el extremo, el NODO donde muere el arco, o —si el arco sigue en OTRO arco que gira
    al revés sin tinta recta entre medio (curva en «S»)— la tangente común a los dos
    círculos (`recognition_arc_chain`, vecinos entre `all_groups`); gana el círculo
    de menor RMS contra la tinta que cumple tangencias y cobertura. Ancla = último
    vértice antes de la tangencia (primero después), llevado sobre la recta de tinta;
    dos codos con la misma recta comparten ancla entre sus tangencias (también con un
    codo de la 1.ª pasada, `taken` = [(ia, ib, C, A, B)], cuyos vértices no se tocan
    salvo ese). `arc_ends` = [(cuerda corta, cuerda larga)] de los guiones rectos donde
    un arco nace o muere (`recognition_arcs.dash_arc_ends`): la corta cuenta como tinta
    del arco si va sobre su círculo y la larga sirve de recta del codo en el lado sin
    ninguna otra recta de tinta (DU10 h.3, codo chico a guiones)."""
    import recognition as R        # perezoso: recognition importa este módulo
    n = len(pts)
    if n < 2 or not groups:
        return [], {}
    S = _cumlen(pts)
    slip = INK_EDGE_SLIP_PT * f
    edge_in = INK_EDGE_IN_PT * f
    tol = INK_FIT_TOL_PT * f
    through_dirs = through_dirs or {}
    p1_legs = [tuple(t) for t in taken if len(t) >= 5]
    busy = [(t[0], t[1]) for t in taken]
    locked = {m for a, b in busy for m in range(a, b + 1)}

    def _dist_line(q, P, u):
        return abs((q[0] - P[0]) * u[1] - (q[1] - P[1]) * u[0])

    def _arc_dir(g, side):
        """Tangente del arco de tinta en su inicio/fin, en el sentido de avance."""
        E = g.E0 if side < 0 else g.E1
        t = _tangent_at(E, g.cx, g.cy)
        return t if g.sign > 0 else (-t[0], -t[1])

    def _ink_lines(g, side):
        """Rectas de tinta antes (side<0) / después (side>0) del arco, las más cercanas
        primero, alineadas con la TANGENTE del arco en su extremo."""
        cands = []
        tan = _arc_dir(g, side)
        for a, b in straights:
            L = math.dist(a, b)
            if L < LEG_INK_SEG_MIN_PT * f:
                continue
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            sm, d, _k = project(pts, S, m)
            if d > ARC_CORRIDOR_PT * f:
                continue
            sa, sb = project(pts, S, a)[0], project(pts, S, b)[0]
            if side < 0:
                if max(sa, sb) > g.s0 + edge_in or sm < g.s0 - LEG_SEARCH_PT * f:
                    continue
                dist_arc = g.s0 - max(sa, sb)
                near = a if sa > sb else b                   # punta de la recta del lado del arco
            else:
                if min(sa, sb) < g.s1 - edge_in or sm > g.s1 + LEG_SEARCH_PT * f:
                    continue
                dist_arc = min(sa, sb) - g.s1
                near = a if sa < sb else b
            u = _unit(b[0] - a[0], b[1] - a[1])
            if u[0] * tan[0] + u[1] * tan[1] < 0:
                u = (-u[0], -u[1])
            allow = LEG_ALIGN_DEG + math.degrees(max(0.0, dist_arc) / max(g.r, 1e-6))
            if u[0] * tan[0] + u[1] * tan[1] < math.cos(math.radians(min(allow, 60.0))):
                continue
            cands.append((dist_arc, -L, a, u, near))
        if not cands and arc_ends:
            cands = _end_dash_lines(g, side, tan)          # la recta DENTRO del guión donde muere el arco
        cands.sort(key=lambda c: (c[0], c[1]))
        lines = []
        for _d, _L, a, u, near in cands:
            if any(abs(u[0] * w[1] - u[1] * w[0]) < 0.005
                   and abs((a[0] - p[0]) * w[1] - (a[1] - p[1]) * w[0]) < 0.2 * f for p, w, _n in lines):
                continue                                   # misma recta (otro guión)
            if (a, near) not in end_dash:
                a, u = _refine_line(a, u, g, side)
            lines.append((a, u, near))
            if len(lines) >= 3:
                break
        return lines

    end_dash = set()

    def _end_dash_lines(g, side, tan):
        """Cuerda LARGA de un guión cuya cuerda corta va sobre el círculo del arco g, del
        lado pedido y con el rumbo de su tangente: la recta del plano después (antes) de
        un arco que muere (nace) dentro de ese guión."""
        out = []
        for short, (a, b) in _end_dashes((g.cx, g.cy), g.r):
            L = math.dist(a, b)
            if L < LEG_INK_SEG_MIN_PT * f:
                continue
            j = a if a in short else b                      # punta pegada al arco
            far = b if j is a else a
            if min(math.dist(far, pts[0]), math.dist(far, pts[-1])) > 1.0 * f:
                continue                                    # solo la recta que llega al FIN de la línea
            sj, dj, _k = project(pts, S, j)
            if dj > ARC_CORRIDOR_PT * f or (sj < g.s1 - edge_in if side > 0 else sj > g.s0 + edge_in):
                continue
            u = _unit(far[0] - j[0], far[1] - j[1]) if side > 0 else _unit(j[0] - far[0], j[1] - far[1])
            dist_arc = (sj - g.s1) if side > 0 else (g.s0 - sj)
            allow = LEG_ALIGN_DEG + math.degrees(max(0.0, dist_arc) / max(g.r, 1e-6))   # = `_ink_lines`
            if u[0] * tan[0] + u[1] * tan[1] < math.cos(math.radians(min(allow, 60.0))):
                continue
            end_dash.add((far if side > 0 else j, j))
            out.append((dist_arc, -L, far if side > 0 else j, u, j))
        return out

    def _end_dashes(ctr, r):
        """Pares de `arc_ends` de ESTE arco: la cuerda corta va sobre el círculo y la
        recta de su guión se aparta de él (es la recta que sale del arco, no un arco
        tan abierto que un guión recto ya no se distingue)."""
        out = []
        for short, long_ in arc_ends or ():
            if any(abs(math.hypot(q[0] - ctr[0], q[1] - ctr[1]) - r) > ON_ARC_TOL_PT * f for q in short):
                continue
            far = long_[1] if long_[0] in short else long_[0]
            if abs(math.hypot(far[0] - ctr[0], far[1] - ctr[1]) - r) < END_DASH_LEAVE_PT * f:
                continue
            out.append((short, long_))
        return out

    def _refine_line(a, u, g, side):
        """Recta ajustada (mínimos cuadrados, pesos = largo) a TODOS los guiones de esta
        polilínea sobre ella (≤0.3 pt, ±1°) y fuera del tramo del arco: el rumbo de UN
        guión corto trae ±0.25° de cuantización (0.06 pt), casi 2 pt a 450 pt."""
        tol_off, sin_par = LINE_REFINE_OFF_PT * f, math.sin(math.radians(1.0))
        sw = sx = sy = 0.0
        pts_w = []
        for p, q in straights:
            L = math.dist(p, q)
            if L < 1e-9 or abs((q[0] - p[0]) * u[1] - (q[1] - p[1]) * u[0]) > sin_par * L:
                continue
            if max(_dist_line(p, a, u), _dist_line(q, a, u)) > tol_off:
                continue
            sp, sq = project(pts, S, p)[0], project(pts, S, q)[0]
            if (side < 0 and max(sp, sq) > g.s0 + edge_in) or (side > 0 and min(sp, sq) < g.s1 - edge_in):
                continue
            for w in (p, q):
                pts_w.append((w, L))
                sw += L; sx += L * w[0]; sy += L * w[1]
        if len(pts_w) < 4:
            return a, u
        mx, my = sx / sw, sy / sw
        sxx = sum(L * (w[0] - mx) ** 2 for w, L in pts_w)
        syy = sum(L * (w[1] - my) ** 2 for w, L in pts_w)
        sxy = sum(L * (w[0] - mx) * (w[1] - my) for w, L in pts_w)
        ang = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
        v = (math.cos(ang), math.sin(ang))
        if v[0] * u[0] + v[1] * u[1] < 0:
            v = (-v[0], -v[1])
        return (mx, my), v

    def _through(i):
        if i not in (0, n - 1):
            return None
        return through_dirs.get((round(pts[i][0], 1), round(pts[i][1], 1)))

    def _options(g, side):
        """[('line', P, u, libre, índice|None, punta) | ('node', Q, None, False, k, None)];
        u = sentido de avance; punta = extremo de la recta de tinta del lado del arco
        (None en la TANGENTE COMÚN con el arco vecino: curva en «S»)."""
        res = [("line", P, u, False, None, near) for P, u, near in _ink_lines(g, side)]
        h = neigh.get(id(g), (None, None))[0 if side < 0 else 1]
        if h is not None:
            ct = chain_mod.common_tangent(h, g, f) if side < 0 else chain_mod.common_tangent(g, h, f)
            if ct is not None:
                u, T1, T2 = ct
                res.append(("line", T2 if side < 0 else T1, u, False, None, None))
        end = 0 if side < 0 else n - 1
        E = g.E0 if side < 0 else g.E1
        d = _through(end)
        if d is not None and math.dist(pts[end], E) <= LEG_SEARCH_PT * f:
            nb = pts[1] if end == 0 else pts[n - 2]
            if d[0] * (nb[0] - pts[end][0]) + d[1] * (nb[1] - pts[end][1]) < 0:
                d = (-d[0], -d[1])                           # del nodo hacia el arco
            res.append(("line", pts[end], d if side < 0 else (-d[0], -d[1]), True, end, None))
        for k in range(n):
            if kinds[k] in NODE_TERMINAL_KINDS and math.dist(pts[k], E) <= slip:
                if (side < 0 and S[k] <= g.s0 + slip) or (side > 0 and S[k] >= g.s1 - slip):
                    # muere en el nodo solo si no hay tinta RECTA entre el arco y el nodo
                    s_lo, s_hi = sorted((S[k], g.s0 if side < 0 else g.s1))
                    if _straight_between(s_lo, s_hi) < STRAIGHT_MIN_PT * f:
                        res.append(("node", pts[k], None, False, k, None))
        return res

    def _straight_off_arc(g, ctr, r):
        """¿Tinta RECTA de esta línea (sobre la polilínea y con su rumbo) entre el
        inicio y el fin del arco que se aparta del círculo? = línea POLIGONAL, no arco."""
        m = 2.0 * f
        cos_par = math.cos(math.radians(10.0))
        for a, b in straights:
            L = math.dist(a, b)
            if L < STRAIGHT_MIN_PT * f:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            bad = 0
            for t in range(9):
                q = (a[0] + (b[0] - a[0]) * t / 8, a[1] + (b[1] - a[1]) * t / 8)
                s, d, k = project(pts, S, q)
                if d > 1.0 * f or not (g.s0 + m < s < g.s1 - m):
                    continue
                sx, sy = pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]
                sl = math.hypot(sx, sy)
                if sl < 1e-9 or abs(ux * sx + uy * sy) < cos_par * sl:
                    continue
                if abs(math.hypot(q[0] - ctr[0], q[1] - ctr[1]) - r) > INK_FIT_MAX_PT * f:
                    bad += 1
            if bad >= 2:
                return True
        return False

    def _straight_between(s_lo, s_hi):
        """Largo de tinta recta de esta polilínea entre los parámetros s_lo y s_hi."""
        tot = 0.0
        for a, b in straights:
            sa, da, _ = project(pts, S, a)
            sb, db, _ = project(pts, S, b)
            if max(da, db) > ARC_CORRIDOR_PT * f:
                continue
            lo, hi = max(min(sa, sb), s_lo), min(max(sa, sb), s_hi)
            if hi > lo:
                tot += hi - lo
        return tot

    def _ends_ok(g, ctr, r, A, B, ua, ub, near_a, near_b, max_dev):  # None = bien; si no, el motivo
        """Cada tangencia cae ENTRE el fin de la tinta curva y la punta de la recta de
        tinta de su lado (hueco con letra: DU10 h.27, 15 pt con una «E»); sin recta, a
        ≤ slip. Tinta del otro lado de la tangencia: desvío d²/2r ≤ `max_dev`."""
        a0 = math.atan2(A[1] - ctr[1], A[0] - ctr[0])

        def ang_to(Q):
            d = math.atan2(Q[1] - ctr[1], Q[0] - ctr[0]) - a0
            return ((d + 3.0 * math.pi) % (2.0 * math.pi) - math.pi) * g.sign   # + = avanzando

        def dev(d):                                  # separación recta↔círculo a d de la tangencia
            return d * d / (2.0 * r) if d > 0 else 0.0
        if near_a is None:
            if math.dist(A, g.E0) > slip:
                return "A lejos del arco"
        elif dev(-((A[0] - near_a[0]) * ua[0] + (A[1] - near_a[1]) * ua[1])) > max_dev:
            return "A dentro de la recta"           # la recta de tinta sigue después de la tangencia
        if near_b is None:
            if math.dist(B, g.E1) > slip:
                return "B lejos del arco"
        elif dev(-((near_b[0] - B[0]) * ub[0] + (near_b[1] - B[1]) * ub[1])) > max_dev:
            return "B dentro de la recta"
        sw = ang_to(B)
        if sw <= 0:
            return "giro al revés"
        if dev(-ang_to(g.E0) * r) > max_dev:         # la tinta curva empieza ANTES de A
            return "tinta curva antes de A (%.1f pt)" % (-ang_to(g.E0) * r / f)
        if dev((ang_to(g.E1) - sw) * r) > max_dev:   # …o sigue DESPUÉS de B
            return "tinta curva después de B (%.1f pt)" % ((ang_to(g.E1) - sw) * r / f)
        return None

    def _geometry(g):
        best = []
        opts_a, opts_b = _options(g, -1), _options(g, +1)
        for oa in opts_a:
            for ob in opts_b:
                ka, P, ua, _fa, ia0, near_a = oa
                kb, N, ub, _fb, ib0, near_b = ob
                node_a, node_b = ka == "node", kb == "node"
                if node_a and node_b and ia0 >= ib0:
                    continue
                if not node_a and not node_b:
                    turn = math.degrees(math.atan2(ua[0] * ub[1] - ua[1] * ub[0], ua[0] * ub[0] + ua[1] * ub[1]))
                    if turn * g.sign <= 0 or not (INK_MIN_TURN_DEG <= abs(turn) <= 178.0):
                        if debug is not None: debug.append(("tinta", "giro", round(turn, 1)))
                        continue
                    C = R._isect_lines(P, ua, N, ub)
                    if C is None:
                        continue
                    phi = math.pi - math.radians(abs(turn))
                    fit = R._fit_circle_tangent(g.pts, C, ua, ub, g.r / max(1e-6, math.sin(phi / 2.0)))
                    if fit is None:
                        continue
                    cx, cy, r, rms = fit
                    T = r * math.tan(math.radians(abs(turn)) / 2.0)
                    A = (C[0] - ua[0] * T, C[1] - ua[1] * T); B = (C[0] + ub[0] * T, C[1] + ub[1] * T)
                elif node_a and node_b:
                    fit = fit_circle_two_nodes(g.pts, P, N)
                    if fit is None:
                        continue
                    cx, cy, r, rms = fit
                    A, B = P, N
                    ta, tb = _tangent_at(A, cx, cy), _tangent_at(B, cx, cy)
                    if g.sign < 0:
                        ta, tb = (-ta[0], -ta[1]), (-tb[0], -tb[1])
                    C = R._isect_lines(A, ta, B, tb)
                    if C is None:
                        continue
                    ua, ub = ta, tb
                else:
                    # una recta + el nodo donde muere el arco: círculo tangente a la
                    # recta que pasa por el nodo (dirección HACIA el arco)
                    if node_b:
                        Lp, Lu, Q = P, ua, N
                    else:
                        Lp, Lu, Q = N, (-ub[0], -ub[1]), P
                    fq = fit_circle_line_node(g.pts, Lp, Lu, Q, (g.cx, g.cy, g.r))
                    if fq is None:
                        continue
                    cx, cy, r, rms, Tp = fq
                    C = R._isect_lines(Lp, Lu, Q, _tangent_at(Q, cx, cy))
                    if C is None:
                        continue
                    if node_b:
                        A, B = Tp, Q
                        ub = _unit(Q[0] - C[0], Q[1] - C[1])
                    else:
                        A, B = Q, Tp
                        ua = _unit(C[0] - Q[0], C[1] - Q[1])
                dmax = max(abs(math.hypot(q[0] - cx, q[1] - cy) - r) for q in g.pts)
                if rms > INK_LOOSE_TOL_PT * f or dmax > INK_LOOSE_MAX_PT * f or r < ARC_R_MIN_PT * f:
                    if debug is not None: debug.append(("tinta", "no ajusta", round(rms / f, 2)))
                    continue
                loose = rms > tol or dmax > INK_FIT_MAX_PT * f     # aproximado: a trazos + aviso
                ctr = (cx, cy)
                why = _ends_ok(g, ctr, r, A, B, ua, ub, near_a, near_b,
                               (INK_LOOSE_MAX_PT if loose else INK_FIT_MAX_PT) * f)
                if why:
                    if debug is not None: debug.append(("tinta", "tangencia: " + why))
                    continue
                a0 = math.atan2(A[1] - cy, A[0] - cx); a1 = math.atan2(B[1] - cy, B[0] - cx)
                sweep = (a1 - a0 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
                if abs(math.degrees(sweep)) < INK_MIN_TURN_DEG or sweep * g.sign <= 0:
                    continue
                cover = arc_cover(g.chords, ctr, r, a0, sweep, 1.0 * f)
                if cover < INK_COVER and arc_ends:
                    extra = _chords_on_arc([sh for sh, _lg in _end_dashes(ctr, r)], ctr, r, a0, sweep,
                                           ON_ARC_TOL_PT * f)
                    if extra:
                        cover = arc_cover(list(g.chords) + extra, ctr, r, a0, sweep, 1.0 * f)
                if cover < INK_COVER:
                    if debug is not None: debug.append(("tinta", "poca tinta sobre el arco", round(cover, 2)))
                    continue
                if _straight_off_arc(g, ctr, r):
                    if debug is not None: debug.append(("tinta", "tinta recta dentro del arco"))
                    continue
                best.append({"C": C, "A": A, "B": B, "ctr": ctr, "r": r, "rms": rms, "a0": a0,
                             "sweep": sweep, "ua": ua, "ub": ub, "oa": oa, "ob": ob, "loose": loose})
        # todos los que cumplen, el mejor primero: si el de menor RMS no tiene anclas
        # (un nodo cae apenas dentro del arco), el siguiente —p. ej. el arco que pasa
        # por ese nodo— puede tenerlas (DU10 h.9/10)
        return sorted(best, key=lambda c: (c["loose"], c["rms"]))

    def _anchor(geo, side):
        """(índice, posición) del ancla de la recta de ese lado, o None."""
        kind, P, u, free, idx, _near = geo["oa"] if side < 0 else geo["ob"]
        T = geo["A"] if side < 0 else geo["B"]
        C = geo["C"]
        if kind == "node":
            return idx, pts[idx]
        if free:
            # línea que pasa por el extremo: si la tangencia cae más allá del nodo, el
            # vértice va a la tangencia (sigue sobre esa misma línea)
            q = pts[idx]
            far = math.dist(C, T) > math.dist(C, q) and (T[0] - C[0]) * (q[0] - C[0]) + (T[1] - C[1]) * (q[1] - C[1]) > 0
            return idx, (T if far else q)
        sT = project(pts, S, T)[0]
        if side < 0:
            ks = [k for k in range(n) if S[k] <= sT + edge_in]
            k = ks[-1] if ks else None
        else:
            ks = [k for k in range(n) if S[k] >= sT - edge_in]
            k = ks[0] if ks else None
        if k is None:
            return None
        q = pts[k]
        off = abs((q[0] - P[0]) * u[1] - (q[1] - P[1]) * u[0])
        t = (q[0] - T[0]) * u[0] + (q[1] - T[1]) * u[1]      # >0: después de T en el avance
        if any(a < k < b for a, b in busy[:len(taken)]):
            return None                                  # vértice que el codo viejo ya quitó
        if k in locked or kinds[k] not in SOFT_DROP_KINDS:
            # nodo / ancla de otro codo: no se mueve; tiene que estar sobre la recta y
            # del lado de afuera de la tangencia
            if off > ANCHOR_NODE_TOL_PT * f or (t > 0.05 * f if side < 0 else t < -0.05 * f):
                if debug is not None: debug.append(("tinta", "ancla-nodo", k, round(off / f, 2), round(t / f, 2)))
                return None
            return k, q
        if off > DROP_TOL_PT * f:
            if debug is not None: debug.append(("tinta", "ancla fuera de la recta", k, round(off / f, 2)))
            return None
        if (side < 0 and t > 0) or (side > 0 and t < 0):
            return k, T                                 # caía dentro del arco: a la tangencia
        return k, (T[0] + u[0] * t, T[1] + u[1] * t)    # sobre la recta de tinta

    def _anchor_shared_p1(geo, side):
        """Respaldo: la recta de este lado es la MISMA que la de un codo de la 1.ª
        pasada (curva en «S», DU08 h.26). Su ancla se comparte, deslizado sobre esa
        recta entre las dos tangencias: el codo viejo no cambia (mismo rumbo)."""
        kind, P, u, free, _idx, _near = geo["oa"] if side < 0 else geo["ob"]
        if kind != "line" or free:
            return None
        T = geo["A"] if side < 0 else geo["B"]
        tol_on = SHARED_LEG_TOL_PT * f
        for (a1, b1, C1, A1, B1) in p1_legs:
            k1, T1 = (a1, A1) if side > 0 else (b1, B1)
            if kinds[k1] not in SOFT_DROP_KINDS:
                continue                                 # un nodo de la red no se mueve
            if max(_dist_line(C1, P, u), _dist_line(T1, P, u), _dist_line(T, C1, _unit(T1[0] - C1[0], T1[1] - C1[1]))) > tol_on:
                continue
            along = (T1[0] - T[0]) * u[0] + (T1[1] - T[1]) * u[1]
            if (side > 0 and along < -0.05 * f) or (side < 0 and along > 0.05 * f):
                continue
            # sobre la recta del codo VIEJO (esquina C1 → tangencia T1), entre las dos tangencias
            w = _unit(T1[0] - C1[0], T1[1] - C1[1])
            mid = ((T[0] + T1[0]) / 2, (T[1] + T1[1]) / 2)
            t = (mid[0] - C1[0]) * w[0] + (mid[1] - C1[1]) * w[1]
            return k1, (C1[0] + w[0] * t, C1[1] + w[1] * t)
        return None

    def _place(geo, prev):
        """Anclas y comprobaciones de un candidato: (ia, qa, ib, qb) o None."""
        an_a = _anchor(geo, -1) or _anchor_shared_p1(geo, -1)
        an_b = _anchor(geo, +1) or _anchor_shared_p1(geo, +1)
        if an_a is None or an_b is None:
            if debug is not None: debug.append(("tinta", "sin ancla sobre la recta", "a" if an_a is None else "b"))
            return None
        (ia, qa), (ib, qb) = an_a, an_b
        if ib <= ia:
            return None
        # recta compartida con el codo anterior (la misma recta de tinta)
        if prev is not None and ia <= prev["ib"]:
            u1 = prev["ub"]
            same = (abs(u1[0] * geo["ua"][1] - u1[1] * geo["ua"][0]) < math.sin(math.radians(1.0))
                    and abs((geo["A"][0] - prev["B"][0]) * u1[1] - (geo["A"][1] - prev["B"][1]) * u1[0]) <= 0.5 * f)
            m = prev["ib"]
            gap = (geo["A"][0] - prev["B"][0]) * u1[0] + (geo["A"][1] - prev["B"][1]) * u1[1]
            q = pts[m]
            # NODO compartido: no se mueve; vale si ya está entre las tangencias (DU08 h.39)
            node_ok = (m not in locked and kinds[m] not in SOFT_DROP_KINDS and ia == m
                       and _dist_line(q, prev["B"], u1) <= ANCHOR_NODE_TOL_PT * f
                       and (q[0] - prev["B"][0]) * u1[0] + (q[1] - prev["B"][1]) * u1[1] >= -0.05 * f
                       and (geo["A"][0] - q[0]) * u1[0] + (geo["A"][1] - q[1]) * u1[1] >= -0.05 * f)
            soft_ok = m not in locked and kinds[m] in SOFT_DROP_KINDS
            # tangente común de una curva en «S» sin recta entre medio: las dos
            # tangencias caen en el mismo punto y los ajustes pueden cruzarlas un poco
            # (el editor lo absorbe al recalcular con el ancla compartido)
            oa = geo["oa"]
            gap_min = (-chain_mod.TANGENT_OVERLAP_PT if oa[0] == "line" and oa[5] is None and not oa[3]
                       else -0.05) * f
            if not (same and gap >= gap_min and (soft_ok or node_ok) and m < ib):
                if debug is not None: debug.append(("tinta", "choca con el codo anterior"))
                return None
            ia = m
            qa = q if node_ok else ((prev["B"][0] + geo["A"][0]) / 2, (prev["B"][1] + geo["A"][1]) / 2)
        if not all(ib <= a or ia >= b for a, b in busy[:len(taken)]):
            if debug is not None: debug.append(("tinta", "choca con un codo de la 1.ª pasada"))
            return None
        if any(kinds[m] not in SOFT_DROP_KINDS or m in locked for m in range(ia + 1, ib)):
            if debug is not None: debug.append(("tinta", "quitaría un nodo"))
            return None
        cx, cy = geo["ctr"]; r = geo["r"]; a0, sweep = geo["a0"], geo["sweep"]
        shape = [qa, geo["A"]] + [(cx + r * math.cos(a0 + sweep * t / 24), cy + r * math.sin(a0 + sweep * t / 24))
                                  for t in range(25)] + [geo["B"], qb]
        if any(min(_seg_dist(pts[m], a, b) for a, b in zip(shape, shape[1:])) > DROP_TOL_PT * f
               for m in range(ia + 1, ib)):
            if debug is not None: debug.append(("tinta", "quitaría un quiebre"))
            return None
        return ia, qa, ib, qb

    neigh = chain_mod.neighbours(all_groups or groups, _straight_between, slip, LEG_INK_SEG_MIN_PT * f, f)
    entries, moves = [], {}
    prev = None
    for g in sorted(groups, key=lambda g: g.s0):
        placed = None
        for geo in _geometry(g):
            placed = _place(geo, prev)
            if placed:
                break
        if not placed:
            continue
        ia, qa, ib, qb = placed
        r = geo["r"]
        if qa != pts[ia]:
            moves[ia] = qa
        if qb != pts[ib]:
            moves[ib] = qb
        node_a, node_b = geo["oa"][0] == "node", geo["ob"][0] == "node"
        entries.append(([ia + 1, ib - 1, geo["C"], geo["A"], geo["B"], geo["ctr"], r, ia, ib,
                         node_a, node_b, geo["loose"], geo["rms"], False, False], g))
        busy.append((ia, ib))
        prev = {"ia": ia, "ib": ib, "ub": geo["ub"], "B": geo["B"]}
    out, used = [], set()      # con los anclas definitivos: como lo dibuja el editor + tinta
    for e, g in entries:
        C, r, ia, ib = e[2], e[6], e[7], e[8]
        geo2 = _editor_geo(C, moves.get(ia, pts[ia]), moves.get(ib, pts[ib]), r, f)
        if geo2 is None:
            if debug is not None: debug.append(("tinta", "no entra en sus rectas"))
            continue
        A, B, ctr, r = geo2
        rms = math.sqrt(sum((math.hypot(q[0] - ctr[0], q[1] - ctr[1]) - r) ** 2 for q in g.pts) / len(g.pts))
        dmax = max(abs(math.hypot(q[0] - ctr[0], q[1] - ctr[1]) - r) for q in g.pts)
        if rms > INK_LOOSE_TOL_PT * f or dmax > INK_LOOSE_MAX_PT * f:
            if debug is not None: debug.append(("tinta", "no ajusta con sus anclas", round(rms / f, 2)))
            continue
        e[3], e[4], e[5], e[6], e[12] = A, B, ctr, r, rms
        e[11] = e[11] or rms > INK_FIT_TOL_PT * f or dmax > INK_FIT_MAX_PT * f
        out.append(tuple(e))
        used.update((ia, ib))
    moves = {k: v for k, v in moves.items() if k in used}
    return out, moves


def _chords_on_arc(chords, ctr: Pt, r: float, a0: float, sweep: float, tol: float):
    """Cuerdas que van SOBRE el arco (extremos y punto medio a ≤ tol del círculo,
    punto medio dentro del sector A→B). Se usa con las cuerdas CORTAS de `arc_ends`:
    en un codo chico el linetype deja casi la mitad en huecos, y el aplanado empieza
    y termina DENTRO de los guiones rectos vecinos (DU10 h.3, r = 10.8 pt: cobertura
    0.35 → 0.6 con esas dos cuerdas)."""
    out = []
    for a, b in chords:
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if any(abs(math.hypot(q[0] - ctr[0], q[1] - ctr[1]) - r) > tol for q in (a, b, m)):
            continue
        da = (math.atan2(m[1] - ctr[1], m[0] - ctr[0]) - a0 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
        if 0.0 < da * (1.0 if sweep > 0 else -1.0) < abs(sweep):
            out.append((a, b))
    return out


def _editor_geo(C: Pt, qa: Pt, qb: Pt, r: float, f: float):
    """(A, B, centro, r) del arco en la esquina C con las rectas C→qa y C→qb, como
    `model_ops.fillet_geo`; si la tangencia se pasa del ancla ≤1 pt, el radio se
    ajusta para que caiga justo ahí. None si no cabe."""
    L1, L2 = math.dist(C, qa), math.dist(C, qb)
    if L1 < 1e-9 or L2 < 1e-9:
        return None
    d1 = ((qa[0] - C[0]) / L1, (qa[1] - C[1]) / L1)
    d2 = ((qb[0] - C[0]) / L2, (qb[1] - C[1]) / L2)
    phi = math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))
    if not (math.radians(1.0) < phi < math.radians(178.0)):
        return None
    T = r / math.tan(phi / 2.0)
    if T > min(L1, L2) + 1.0 * f:
        return None
    if T > min(L1, L2):
        T = min(L1, L2)
        r = T * math.tan(phi / 2.0)
    bx, by = d1[0] + d2[0], d1[1] + d2[1]
    bl = math.hypot(bx, by)
    dc = r / math.sin(phi / 2.0)
    return ((C[0] + d1[0] * T, C[1] + d1[1] * T), (C[0] + d2[0] * T, C[1] + d2[1] * T),
            (C[0] + bx / bl * dc, C[1] + by / bl * dc), r)
