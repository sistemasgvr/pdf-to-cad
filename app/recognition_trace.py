"""Bounded circular reconstruction of continuous PDF traces.

The fillet representation cannot encode a major arc with one corner. We
split it into minor arcs, keeping shared endpoints and bounding ink error.
Only continuous source ink is used here; gaps and network nodes remain under
the regular recognizer's control. Coordinates and tolerances are in pixels.
"""
from __future__ import annotations

import math

from recognition_arcs import _cumlen, _seg_dist, _unit, project

SOFT = {'curve', 'corner', 'bend'}
FIT_PT = 0.12


def _arc_distance(q, part):
    a, b, arc = part
    if arc is None:
        return _seg_dist(q, a, b)
    _, _, ctr, r, a0, sw = arc
    ang = (math.atan2(q[1] - ctr[1], q[0] - ctr[0]) - a0) * (1 if sw > 0 else -1)
    if ang % (2 * math.pi) <= abs(sw):
        return abs(math.dist(q, ctr) - r)
    return min(math.dist(q, a), math.dist(q, b))


def circular_trace(points, f=1.):
    """Fit endpoint-constrained circles, subdividing until ink error is bounded.

    Keeping each sweep below 120 degrees makes major arcs representable with
    the existing editor/DXF fillets. Both endpoints of every piece are shared.
    """
    from recognition_arcs import fit_circle_two_nodes, _sweep_deg
    tol = FIT_PT*f

    def fit(P):
        a, b = P[0], P[-1]
        if len(P) < 3 or max(_seg_dist(p, a, b) for p in P) <= 0.05*f:
            return [(a, b, None)]
        circle = fit_circle_two_nodes(P, a, b)
        if circle:
            cx, cy, r, rms = circle
            sw = math.radians(_sweep_deg(P, cx, cy))
            if (math.radians(2.1) < abs(sw) < math.radians(120)
                    and max(abs(math.hypot(q[0]-cx, q[1]-cy)-r) for q in P) <= tol):
                a0 = math.atan2(a[1]-cy, a[0]-cx)
                arc = (a, b, (cx, cy), r, a0, sw)
                count = max(8, math.ceil(abs(sw)/(2*math.acos(max(-1., 1-tol/(4*r))))))
                samples = [(cx+r*math.cos(a0+sw*k/count), cy+r*math.sin(a0+sw*k/count))
                           for k in range(count+1)]
                if all(min(_seg_dist(q, x, y) for x, y in zip(P, P[1:])) <= tol for q in samples):
                    return [(a, b, arc)]
        m = len(P)//2
        return fit(P[:m+1]) + fit(P[m:])

    cuts = [0]
    for i in range(1, len(points)-1):
        a, b, c = points[i-1:i+2]
        la, lb = math.dist(a, b), math.dist(b, c)
        ua, ub = _unit(b[0]-a[0], b[1]-a[1]), _unit(c[0]-b[0], c[1]-b[1])
        turn = abs(math.atan2(ua[0]*ub[1]-ua[1]*ub[0], ua[0]*ub[0]+ua[1]*ub[1]))
        if turn > math.radians(25) or max(la, lb) > max(8*f, 4*min(la, lb)):
            cuts.append(i)
    cuts.append(len(points)-1)
    return [part for lo, hi in zip(cuts, cuts[1:]) for part in fit(points[lo:hi+1])]


def _encode(parts, start_kind, end_kind):
    pts, kinds, fillets = [parts[0][0]], [start_kind], {}
    for a, b, arc in parts:
        if arc:
            _, _, ctr, r, a0, sw = arc
            am = a0 + sw/2
            corner = (ctr[0] + r / math.cos(sw/2) * math.cos(am),
                      ctr[1] + r / math.cos(sw/2) * math.sin(am))
            fillets[len(pts)] = dict(a=a, b=b, center=ctr, r_px=r, loose=False,
                                     dev_px=0., node_a=False, node_b=False)
            pts.append(corner); kinds.append('fillet')
        pts.append(b); kinds.append('bend')
    kinds[-1] = end_kind
    return pts, kinds, fillets


def _drawing(data):
    P, K, F = data
    parts = []
    prev = P[0]
    for i in range(1, len(P)):
        if i in F:
            g = F[i]
            a, b, c, r = g['a'], g['b'], g['center'], g['r_px']
            a0 = math.atan2(a[1]-c[1], a[0]-c[0])
            sw = (math.atan2(b[1]-c[1], b[0]-c[0])-a0+math.pi) % (2*math.pi)-math.pi
            parts.append((prev, a, None))
            parts.append((a, b, (a, b, c, r, a0, sw)))
            prev = b
        else:
            parts.append((prev, P[i], None))
            prev = P[i]
    return parts


def fit_continuous(pts, kinds, fitter, **kw):
    """Reconstruct inaccurate continuous traces; delegate the gaps to fitter.

    Source endpoints become explicit anchors. They need not coincide with a
    vertex left by simplification. Protected network nodes are never removed.
    """
    baseline = fitter(pts, kinds, **kw)
    if len(pts) < 2 or not any(k == 'curve' for k in kinds):
        return baseline
    f = kw.get('tol_px', 1.)
    S = _cumlen(pts)
    drawing = _drawing(baseline)
    candidates = []
    for st in kw.get('strokes') or []:
        if len(st) < 8:
            continue
        pr = [project(pts, S, p) for p in st]
        good = [i for i, p in enumerate(pr) if p[1] <= 1.5*f]
        if len(good) < 8:
            continue
        lo, hi = min(good), max(good)
        if any(pr[i][1] > 2.5*f for i in range(lo, hi+1)):
            continue
        chain = list(st)
        if pr[lo][0] > pr[hi][0]:
            chain.reverse(); pr.reverse()
            lo, hi = len(st)-1-hi, len(st)-1-lo
        T = _cumlen(chain)
        s0, s1 = pr[lo][0], pr[hi][0]
        t0, t1 = T[lo], T[hi]
        start, end = tuple(chain[lo]), tuple(chain[hi])
        ka = kb = 'bend'
        # Source traces can extend through a stop or a page cut. Clip exactly
        # at the route endpoint, rather than discarding the final source chord.
        for i in (0, len(pts)-1):
            t, d, _ = project(chain, T, pts[i])
            if d <= 0.15*f:
                if i == 0:
                    s0, t0, start, ka = 0., t, pts[i], kinds[i]
                else:
                    s1, t1, end, kb = S[-1], t, pts[i], kinds[i]
        if s1 <= s0 or t1 <= t0:
            continue
        # A protected node can also coincide with a patch boundary.
        boundary_bad = False
        for i, s in enumerate(S):
            if kinds[i] in SOFT:
                continue
            if abs(s-s0) <= 1e-6:
                if math.dist(start, pts[i]) > 0.15*f:
                    boundary_bad = True
                start, ka = pts[i], kinds[i]
            if abs(s-s1) <= 1e-6:
                if math.dist(end, pts[i]) > 0.15*f:
                    boundary_bad = True
                end, kb = pts[i], kinds[i]
        if boundary_bad:
            continue
        hard = [(s0, t0, start, ka)]
        invalid = False
        for i in range(1, len(pts)-1):
            if s0+1e-6 < S[i] < s1-1e-6 and kinds[i] not in SOFT:
                t, d, _ = project(chain, T, pts[i])
                if d > 0.15*f:
                    invalid = True
                    break
                hard.append((S[i], t, pts[i], kinds[i]))
        if invalid:
            continue
        hard.append((s1, t1, end, kb))
        for (a, ta, pa, ka), (b, tb, pb, kb) in zip(hard, hard[1:]):
            P = [pa] + [q for t, q in zip(T, chain) if ta+1e-6 < t < tb-1e-6] + [pb]
            if len(P) < 8 or not any(k == 'curve' and a <= s <= b for s, k in zip(S, kinds)):
                continue
            pp = [project(pts, S, q)[0] for q in P]
            if any(y < x-0.5*f for x, y in zip(pp, pp[1:])):
                continue
            if max(min(_arc_distance(q, p) for p in drawing) for q in P) <= FIT_PT*f:
                continue  # already precise: keep the simpler circle
            # A dash is only part of an existing circle. Replacing that dash
            # would destroy the larger fit when the remaining pieces are
            # processed separately. Replace only fully contained circles.
            partial = False
            for g in baseline[2].values():
                sa = project(pts, S, g['a'])[0]
                sb = project(pts, S, g['b'])[0]
                x, y = sorted((sa, sb))
                if a < y-0.2*f and b > x+0.2*f and (x < a-0.2*f or y > b+0.2*f):
                    partial = True
                    break
            if partial:
                continue
            parts = circular_trace(P, f)
            if any(p[2] for p in parts):
                patch = _encode(parts, ka, kb)
                error = max(min(_arc_distance(q, part) for part in parts) for q in P)
                for g in patch[2].values():
                    g['dev_px'] = round(error, 4)
                candidates.append((a, b, patch))
    chosen = []
    for a, b, patch in sorted(candidates, key=lambda c: -(c[1]-c[0])):
        if not any(a < y-1e-6 and b > x+1e-6 for x, y, _ in chosen):
            chosen.append((a, b, patch))
    if not chosen:
        return baseline
    out, kk, ff = [], [], {}

    def add(data):
        P, K, F = data
        offset = len(out) - (1 if out else 0)
        ff.update({offset+i: v for i, v in F.items()})
        out.extend(P[1:] if out else P); kk.extend(K[1:] if kk else K)

    def gap(a, b, pa, pb, ka, kb):
        P, K = [pa], [ka]
        for s, p, k in zip(S, pts, kinds):
            if a+1e-6 < s < b-1e-6:
                P.append(p); K.append(k)
        P.append(pb); K.append(kb)
        # Splice anchors are fixed. Do not let an adjacent gap's circle move
        # an endpoint already used by a validated source trace.
        locked = list(K)
        if ka in SOFT:
            locked[0] = 'end'
        if kb in SOFT:
            locked[-1] = 'end'
        data = fitter(P, locked, **kw)
        if math.dist(data[0][0], pa) > 1e-6 or math.dist(data[0][-1], pb) > 1e-6:
            data = P, K, {}
        else:
            data[1][0], data[1][-1] = ka, kb
        add(data)

    cursor, last, last_kind = 0., pts[0], kinds[0]
    for a, b, patch in sorted(chosen):
        P, K, _ = patch
        if a > cursor+1e-6:
            gap(cursor, a, last, P[0], last_kind, K[0])
        add(patch)
        cursor, last, last_kind = b, P[-1], K[-1]
    if cursor < S[-1]-1e-6:
        gap(cursor, S[-1], last, pts[-1], last_kind, kinds[-1])
    # A splice must not introduce a hairpin between the editor's tangent legs.
    # Such a join means overlapping source traces were assigned to this route.
    for i in range(1, len(out)-1):
        if kk[i] == 'fillet':
            continue
        u = _unit(out[i-1][0]-out[i][0], out[i-1][1]-out[i][1])
        v = _unit(out[i+1][0]-out[i][0], out[i+1][1]-out[i][1])
        if u[0]*v[0]+u[1]*v[1] > .5:
            return baseline
    # A locally correct circle must not reverse the route at a splice (e.g.
    # an overlapping source stroke whose start projects onto a neighbouring
    # leg). Validate the represented geometry, never the fillet corner polygon.
    progress = -1e-6
    for a, b, arc in _drawing((out, kk, ff)):
        if arc:
            _, _, c, r, a0, sw = arc
            count = max(4, math.ceil(abs(sw)/math.radians(10)))
            samples = [(c[0]+r*math.cos(a0+sw*k/count), c[1]+r*math.sin(a0+sw*k/count))
                       for k in range(count+1)]
        else:
            samples = [a, ((a[0]+b[0])/2, (a[1]+b[1])/2), b]
        for q in samples:
            station, distance, _ = project(pts, S, q)
            if station < progress-0.5*f or distance > 2.5*f:
                return baseline
            progress = max(progress, station)
    return out, kk, ff


# ─── Codos muy abiertos → dos codos (pedido del usuario 2026-09-30) ───────────
# Un codo cuyo giro se acerca a 180° (curva casi en «U», DU06 h.5 telecom: 178.7°,
# r = 28 px) tiene la esquina —intersección de las tangentes— a T = r·tan(Δ/2) del
# arco: 2514 px, fuera de la hoja. El arco es correcto, pero la esquina lejana se ve
# como un «trazo gigante» en la vista previa, y con Δ > 179° el editor ni lo dibuja
# (`fillet_geo` exige un ángulo interior ≥1°). Se escribe como DOS codos de Δ/2 sobre
# el MISMO círculo, unidos en el punto medio del arco por un vértice «bend» (mismo
# formato que `_encode`): el arco dibujado —A, B, centro y radio— no cambia.
# Foto 4 PDFs × 6 utilidades (1799 codos): 0 entre 120° y 170°, 1 ≥170° (ese caso).
WIDE_FILLET_DEG = 150.0


def _half_corners(f):
    """(C1, M, C2) de un codo partido en su punto medio M, o None. El sentido sale
    de la esquina C (la bisectriz apunta a ella), no de A/B: con Δ ≈ 180° el
    ángulo A→B es ambiguo."""
    a, c, r = f["a"], f["center"], float(f["r_px"])
    corner = f["_corner"]
    va = (a[0] - c[0], a[1] - c[1])
    vc = (corner[0] - c[0], corner[1] - c[1])
    half = math.atan2(va[0] * vc[1] - va[1] * vc[0], va[0] * vc[0] + va[1] * vc[1])   # A→bisectriz
    a0 = math.atan2(va[1], va[0])
    am = a0 + half                                     # punto medio del arco
    q = half / 2.0                                     # cada mitad gira Δ/2: su esquina a Δ/4
    d = r / math.cos(q)
    M = (c[0] + r * math.cos(am), c[1] + r * math.sin(am))
    C1 = (c[0] + d * math.cos(a0 + q), c[1] + d * math.sin(a0 + q))
    C2 = (c[0] + d * math.cos(am + q), c[1] + d * math.sin(am + q))
    return C1, M, C2


def split_wide_fillets(pts, kinds, fillets, f=1.0, max_deg=WIDE_FILLET_DEG):
    """Parte en dos cada codo de giro ≥ `max_deg` (ver arriba). Solo si el editor
    dibuja las dos mitades EXACTAMENTE sobre el arco reconocido (mismas tangencias
    A, M, B y centro, sin recorte); si no, el codo queda como estaba. No toca codos
    con otro codo pegado (recta compartida con tope 0.48). `f` = px por pt."""
    import model_ops as MO
    if not fillets:
        return pts, kinds, fillets
    tol = 0.05 * f
    out_p, out_k, out_f = [], [], {}
    for i, (p, k) in enumerate(zip(pts, kinds)):
        fl = fillets.get(i)
        parts = None
        if (fl is not None and 0 < i < len(pts) - 1
                and kinds[i - 1] != "fillet" and kinds[i + 1] != "fillet"):
            parts = _split_parts(pts[i - 1], p, pts[i + 1], fl, tol, max_deg, MO)
        if parts is None:
            if fl is not None:
                out_f[len(out_p)] = fl
            out_p.append(p); out_k.append(k)
            continue
        (C1, f1), M, (C2, f2) = parts
        out_f[len(out_p)] = f1; out_p.append(C1); out_k.append(k)
        out_p.append(M); out_k.append("bend")
        out_f[len(out_p)] = f2; out_p.append(C2); out_k.append(k)
    return out_p, out_k, out_f


def _split_parts(prev, corner, nxt, fl, tol, max_deg, MO):
    a, b, c, r = fl["a"], fl["b"], fl["center"], float(fl["r_px"])
    u = _unit(a[0] - corner[0], a[1] - corner[1])
    v = _unit(b[0] - corner[0], b[1] - corner[1])
    turn = 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))))
    if turn < max_deg:
        return None
    C1, M, C2 = _half_corners(dict(fl, _corner=corner))
    g1 = MO.fillet_geo(prev, C1, M, r, max_frac=MO.FILLET_CAP_RECTA, max_frac_next=MO.FILLET_CAP_RECTA,
                       tol_r=tol)
    g2 = MO.fillet_geo(M, C2, nxt, r, max_frac=MO.FILLET_CAP_RECTA, max_frac_next=MO.FILLET_CAP_RECTA,
                       tol_r=tol)
    if not g1 or not g2 or g1["clamped"] or g2["clamped"]:
        return None
    for got, want in ((g1["t1"], a), (g1["t2"], M), (g2["t1"], M), (g2["t2"], b),
                      (g1["center"], c), (g2["center"], c)):
        if math.dist(got, want) > tol:
            return None
    # mitad «split_*»: de ese lado no hay recta del plano; la tangente es la del arco
    f1 = dict(fl, b=M, node_b=False, split_b=True)
    f2 = dict(fl, a=M, node_a=False, split_a=True)
    return (C1, f1), M, (C2, f2)
