"""recognition_unir_codos.py — varias CURVITAS seguidas → UNA curva (PURO, sin Qt).

Pedido del usuario 2026-10-19 (DU06 UD-205 en la hoja compuesta, la «—SC—» de telecom
junto a «CB-216 LAT»): la línea gira 44° con UN arco del PDF (r = 14.4 pt, tangente a la
horizontal y a la diagonal) y salían tres codos seguidos de r = 67.6, 18 y 13.5 pt —«con
una sola curva se podría manejar… en todas las utilidades»—. El codo de la 1.ª/2.ª pasada
era el bueno, pero la punta de la diagonal se aparta 0.17 pt de su recta (ahí empieza la
curva de abajo, bajo su rótulo) y `recognition_trace.fit_continuous` lo cambió por
círculos cada vez más chicos: `circular_trace` ajusta a 0.12 pt recta + arco + recta
como si todo fuera arco.

Aquí, al final de `fit_fillets` (todas las utilidades): una ristra de codos SEGUIDOS que
giran al mismo lado —entre ellos solo vértices blandos— se cambia por UN codo si ese arco
sigue la TINTA del PDF igual de bien: tangente a la recta que llega y a la que sale (la
esquina es su cruce), radio ajustado a la tinta, y en cada punto de tinta que las curvitas
seguían, el arco único a lo más igual de cerca (o a ≤ `PRECISION_PT`, la de
`fit_continuous`); en los huecos sin tinta (letras) a ≤ `UNIR_TOL_PT` del dibujo de antes.
Así no se pierde nada de precisión: una curva de radio VARIABLE (espiral, curva compuesta
de verdad) que necesita varios arcos para seguir su tinta no cambia, ni una «S». Si la
ristra entera no cabe en un arco se prueban sus tramos, los más largos primero. El codo nuevo
es exactamente el que dibuja el editor y genera el plugin (`model_ops.fillet_geo`, sin
recorte) y los codos vecinos no cambian. Coordenadas en px (`f` = px por pt).
"""
from __future__ import annotations

import math

from nucleo import model_ops as MO
from reconocimiento.recognition_trace import _arc_distance, _drawing

PRECISION_PT = 0.12        # el arco único sigue la tinta como las curvitas o a ≤ esto (= trace.FIT_PT)
SIGUE_PT = 0.25            # tinta que el dibujo de ahora SIGUE (lo demás: letras, otra línea…)
MARGEN_PT = 0.01           # redondeo al comparar con lo de ahora
TINTA_MIN = 6              # con menos puntos de tinta se compara con el dibujo (mismo círculo)
UNIR_TOL_PT = 0.5          # y en los huecos sin tinta el dibujo no se aparta más que esto
GIRO_MAX_DEG = 170.0       # más, la esquina se va lejísimos (`split_wide_fillets` parte ≥150° en dos)
GIRO_MIN_DEG = 1.0         # menos no es curva (`fillet_geo` no la dibuja)
RECTA_MIN_PT = 2.0         # recta exterior más corta: su rumbo no es fiable (coordenadas a 0.06 pt)
PASO_PT = 0.25             # muestreo del dibujo para medir el desvío…
MUESTRAS_MAX = 160         # …con a lo más tantas muestras (curvas largas)
NODO_PT = 0.05             # tangencia sobre un nodo duro: el arco MUERE ahí (no se mueve)
BLANDOS = ("bend", "corner", "curve")


def _unit(dx, dy):
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-12 else None


def _cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def _sentido(pts, i):
    """+1 / −1: hacia dónde gira la línea en el vértice i (0 = recta)."""
    c = _cross((pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]),
               (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
    return (c > 0) - (c < 0)


def _muestras(parts, paso):
    out = []
    for a, b, arc in parts:
        if arc is None:
            n = max(1, math.ceil(math.dist(a, b) / paso))
            out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
        else:
            _, _, c, r, a0, sw = arc
            n = max(2, math.ceil(abs(sw) * r / paso))
            out += [(c[0] + r * math.cos(a0 + sw * k / n), c[1] + r * math.sin(a0 + sw * k / n))
                    for k in range(n + 1)]
    return out


def _paso(partes, f):
    largo = sum(math.dist(a, b) if arc is None else abs(arc[5]) * arc[3] for a, b, arc in partes)
    return max(PASO_PT * f, largo / MUESTRAS_MAX)


def _desvio(muestras, parts):
    return max((min(_arc_distance(q, p) for p in parts) for q in muestras), default=0.0)


def _caps(kinds, i):
    """Topes del editor para el codo i: 0.48 del tramo si el vecino también es codo."""
    return tuple(MO.FILLET_CAP_CURVA if kinds[j] == "fillet" else MO.FILLET_CAP_RECTA for j in (i - 1, i + 1))


def _geo_vecino(pts, kinds, fillets, j):
    """Arco del codo j tal como lo dibuja el editor (None si no hay codo ahí)."""
    if j not in fillets or not (0 < j < len(pts) - 1):
        return None
    c1, c2 = _caps(kinds, j)
    return MO.fillet_geo(pts[j - 1], pts[j], pts[j + 1], fillets[j]["r_px"], max_frac=c1,
                         max_frac_next=c2, tol_r=0.0)


def _igual(a, b, tol=1e-6):
    if a is None or b is None:
        return a is b
    return (a["clamped"] == b["clamped"] and abs(a["r"] - b["r"]) <= tol
            and math.dist(a["t1"], b["t1"]) <= tol and math.dist(a["t2"], b["t2"]) <= tol)


def _rectas(pts, kinds, s, i0, f):
    """Opciones de recta que LLEGA a la ristra por el vértice s (el anterior a su primer
    codo i0): (dirección, ¿s queda sobre la recta y puede quitarse?). Primero la recta del
    tramo anterior (la tinta recta de antes: el primer codo puede venir torcido), luego la
    tangente del primer codo."""
    out = []
    if s >= 1 and kinds[s] != "fillet" and math.dist(pts[s - 1], pts[s]) >= RECTA_MIN_PT * f:
        u = _unit(pts[s][0] - pts[s - 1][0], pts[s][1] - pts[s - 1][1])
        if u:
            out.append((u, kinds[s] in BLANDOS))
    u = _unit(pts[i0][0] - pts[s][0], pts[i0][1] - pts[s][1])
    if u and not any(math.hypot(u[0] - v[0], u[1] - v[1]) < 1e-9 for v, _ in out):
        out.append((u, False))
    return out


def _tramo(pts, kinds, fillets, lo, hi):
    """Dibujo (rectas + arcos) de la polilínea entre los vértices lo y hi; si uno de ellos
    es codo, desde/hasta su tangencia (su esquina no está sobre el dibujo)."""
    F = {k - lo: fillets[k] for k in range(lo + 1, hi) if k in fillets}
    partes = _drawing((pts[lo:hi + 1], kinds[lo:hi + 1], F))
    if lo in fillets:
        partes[0] = (fillets[lo]["b"], partes[0][1], partes[0][2])
    if hi in fillets:
        partes[-1] = (partes[-1][0], fillets[hi]["a"], partes[-1][2])
    return partes


def _ajustar(costo, t_max):
    """T en (0, t_max] que hace mínimo `costo`: rejilla y sección áurea alrededor del mejor."""
    N = 24
    cand = [t_max * k / N for k in range(1, N + 1)]
    vals = [costo(T) for T in cand]
    k = min(range(N), key=vals.__getitem__)
    a_, b_ = cand[max(0, k - 1)], cand[min(N - 1, k + 1)]
    g = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = b_ - g * (b_ - a_), a_ + g * (b_ - a_)
    f1, f2 = costo(x1), costo(x2)
    for _ in range(30):
        if f1 <= f2:
            b_, x2, f2 = x2, x1, f1
            x1 = b_ - g * (b_ - a_)
            f1 = costo(x1)
        else:
            a_, x1, f1 = x1, x2, f2
            x2 = a_ + g * (b_ - a_)
            f2 = costo(x2)
    return min((vals[k], cand[k]), (f1, x1), (f2, x2))[1]


def _muestras_tinta(strokes, f):
    """Puntos de la tinta de la polilínea (trazos del PDF en px) cada `PASO_PT`."""
    out = []
    for st in strokes or ():
        for a, b in zip(st, st[1:]):
            n = max(1, math.ceil(math.dist(a, b) / (PASO_PT * f)))
            out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
        if st:
            out.append(tuple(st[-1]))
    return out


def _seguida(tinta, partes, f):
    """[(punto, tope)]: la tinta que el dibujo de ahora SIGUE (a ≤ `SIGUE_PT`) y lo más que
    puede apartarse de ella el arco único: lo de ahora o la precisión de siempre. Vacía si
    casi no hay tinta (entonces se compara con el dibujo)."""
    if not tinta:
        return []
    xs = [c for a, b, _ in partes for c in (a[0], b[0])]
    ys = [c for a, b, _ in partes for c in (a[1], b[1])]
    for _a, _b, arc in partes:
        if arc is not None:
            xs += [arc[2][0] - arc[3], arc[2][0] + arc[3]]
            ys += [arc[2][1] - arc[3], arc[2][1] + arc[3]]
    m = SIGUE_PT * f
    x0, x1, y0, y1 = min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m
    sigue = []
    for q in tinta:
        if x0 <= q[0] <= x1 and y0 <= q[1] <= y1:
            d = min(_arc_distance(q, p) for p in partes)
            if d <= m:
                sigue.append((q, max(d, PRECISION_PT * f)))
    if len(sigue) < TINTA_MIN:
        return []
    paso = math.ceil(len(sigue) / MUESTRAS_MAX)
    return sigue[::paso]


def _probar(pts, kinds, fillets, cadena, f, tinta=None):
    """UN codo para los codos `cadena` (índices seguidos de la polilínea), o None.
    `tinta` = puntos de la tinta de la polilínea (px). Devuelve (pts, kinds, fillets)."""
    n = len(pts)
    i0, ik = cadena[0], cadena[-1]
    s, e = i0 - 1, ik + 1
    if s < 0 or e > n - 1:
        return None
    tol = UNIR_TOL_PT * f
    fa, fb = fillets[i0], fillets[ik]
    sentido = _sentido(pts, i0)
    lle = _rectas(pts, kinds, s, i0, f)
    # la que sale: lo mismo con la polilínea al revés
    sal = [((-u[0], -u[1]), q) for u, q in _rectas(pts[::-1], kinds[::-1], n - 1 - e, n - 1 - ik, f)]
    viejos = {}
    for u, quita_s in lle:
        for w, quita_e in sal:
            den = _cross(u, w)
            giro = math.degrees(math.atan2(den, u[0] * w[0] + u[1] * w[1]))
            if not (GIRO_MIN_DEG <= abs(giro) <= GIRO_MAX_DEG) or (giro > 0) != (sentido > 0):
                continue
            # esquina = cruce de la recta que llega (por s) y la que sale (por e)
            t_in = _cross((pts[e][0] - pts[s][0], pts[e][1] - pts[s][1]), w) / den
            C = (pts[s][0] + u[0] * t_in, pts[s][1] + u[1] * t_in)
            t_out = (pts[e][0] - C[0]) * w[0] + (pts[e][1] - C[1]) * w[1]
            if t_in < -1e-6 or t_out < -1e-6:
                continue                                  # las rectas se cruzan fuera de la ristra
            quita_s = quita_s and t_in > 1e-6
            quita_e = quita_e and t_out > 1e-6
            lo = s - 1 if quita_s else s
            hi = e + 1 if quita_e else e
            if lo < 0 or hi > n - 1:
                continue
            n_pts = pts[:lo + 1] + [C] + pts[hi:]
            n_kinds = kinds[:lo + 1] + ["fillet"] + kinds[hi:]
            ic = lo + 1
            c1, c2 = _caps(n_kinds, ic)
            t_max = min(math.dist(C, pts[lo]) * c1, math.dist(C, pts[hi]) * c2)
            # el arco que MUERE en un nodo (tee, bóveda…) sigue muriendo en él
            nodo_a = (not quita_s and kinds[s] not in BLANDOS + ("fillet",)
                      and math.dist(fa["a"], pts[s]) <= NODO_PT * f)
            nodo_b = (not quita_e and kinds[e] not in BLANDOS + ("fillet",)
                      and math.dist(fb["b"], pts[e]) <= NODO_PT * f)
            fijo = [t for t, en_nodo in ((t_in, nodo_a), (t_out, nodo_b)) if en_nodo]
            if t_max <= 1e-6 or (fijo and (max(fijo) - min(fijo) > NODO_PT * f or max(fijo) > t_max + 1e-9)):
                continue
            phi = math.pi - math.radians(abs(giro))       # ángulo interior entre las rectas
            bis = _unit(w[0] - u[0], w[1] - u[1])
            if bis is None:
                continue
            X = fillets[lo]["b"] if lo in fillets else pts[lo]
            Y = fillets[hi]["a"] if hi in fillets else pts[hi]

            def dibujo(T, C=C, u=u, w=w, phi=phi, bis=bis, X=X, Y=Y):
                r = T * math.tan(phi / 2.0)
                d = r / math.sin(phi / 2.0)
                ctr = (C[0] + bis[0] * d, C[1] + bis[1] * d)
                A = (C[0] - u[0] * T, C[1] - u[1] * T)
                B = (C[0] + w[0] * T, C[1] + w[1] * T)
                a0 = math.atan2(A[1] - ctr[1], A[0] - ctr[0])
                sw = (math.atan2(B[1] - ctr[1], B[0] - ctr[0]) - a0 + math.pi) % (2 * math.pi) - math.pi
                return [(X, A, None), (A, B, (A, B, ctr, r, a0, sw)), (B, Y, None)], A, B, r

            if (lo, hi) not in viejos:
                partes_v = _tramo(pts, kinds, fillets, lo, hi)
                viejos[(lo, hi)] = (partes_v, _muestras(partes_v, _paso(partes_v, f)),
                                    _seguida(tinta, partes_v, f))
            partes_v, m_v, sigue = viejos[(lo, hi)]
            if sigue:
                # la TINTA manda: el radio por mínimos cuadrados sobre la tinta que seguían las
                # curvitas y, en cada uno de esos puntos, el arco único a lo más igual de cerca
                # (o dentro de la precisión de siempre)
                def ajuste(T):
                    partes = dibujo(T)[0]
                    return sum(min(_arc_distance(q, p) for p in partes) ** 2 for q, _t in sigue)

                def costo(T):
                    partes = dibujo(T)[0]
                    return max(min(_arc_distance(q, p) for p in partes) - tope for q, tope in sigue)
                limite = MARGEN_PT * f
            else:
                # sin tinta: solo un arco que ya era el mismo círculo
                def costo(T):
                    return _desvio(m_v, dibujo(T)[0])
                ajuste = costo
                limite = PRECISION_PT * f
            T = fijo[0] if fijo else _ajustar(ajuste, t_max)
            if costo(T) > limite:
                continue
            partes_n, A, B, r = dibujo(T)
            # y el dibujo no se va (huecos sin tinta): lo de antes sobre lo nuevo y al revés
            dev = max(_desvio(m_v, partes_n), _desvio(_muestras(partes_n, _paso(partes_n, f)), partes_v))
            if dev > (tol if sigue else PRECISION_PT * f):
                continue
            # el editor lo dibuja igual (sin recorte) y los codos vecinos no cambian
            geo = MO.fillet_geo(pts[lo], C, pts[hi], r, max_frac=c1, max_frac_next=c2, tol_r=0.0)
            if (geo is None or geo["clamped"] or math.dist(geo["t1"], A) > 1e-6 * max(1.0, r)
                    or math.dist(geo["t2"], B) > 1e-6 * max(1.0, r)):
                continue
            nf = {k: g_ for k, g_ in fillets.items() if k <= lo}
            nf.update({k - (hi - ic - 1): g_ for k, g_ in fillets.items() if k >= hi})
            if any(not _igual(_geo_vecino(pts, kinds, fillets, j), _geo_vecino(n_pts, n_kinds, nf, j2))
                   for j, j2 in ((lo, lo), (hi, ic + 1)) if j in fillets):
                continue
            miembros = [fillets[k] for k in cadena]
            d_tinta = max((min(_arc_distance(q, p) for p in partes_n) for q, _t in sigue), default=dev)
            nuevo = {"a": geo["t1"], "b": geo["t2"], "center": geo["center"], "r_px": geo["r"],
                     "loose": any(bool(g_.get("loose")) for g_ in miembros),
                     "dev_px": round(d_tinta if sigue else max(float(g_.get("dev_px") or 0.0)
                                                               for g_ in miembros) + dev, 4),
                     "node_a": bool(nodo_a), "node_b": bool(nodo_b), "unidos": len(cadena)}
            if any(g_.get("letters") for g_ in miembros):
                nuevo["letters"] = True
            nf[ic] = nuevo
            return n_pts, n_kinds, nf          # la primera que sirve: las rectas de la tinta van antes
    return None


def _ristras(pts, kinds, fillets):
    """Codos seguidos que giran al mismo lado, con solo vértices blandos entre ellos."""
    idx = sorted(i for i in fillets if 0 < i < len(pts) - 1 and kinds[i] == "fillet")
    out, cur = [], []
    for i in idx:
        if (cur and all(kinds[k] in BLANDOS for k in range(cur[-1] + 1, i))
                and _sentido(pts, i) == _sentido(pts, cur[-1]) != 0):
            cur.append(i)
        else:
            if len(cur) >= 2:
                out.append(cur)
            cur = [i]
    if len(cur) >= 2:
        out.append(cur)
    return out


def unir_codos(pts, kinds, fillets, f: float = 1.0, strokes=None):
    """Cada ristra de codos seguidos que cabe en UN arco que sigue la tinta (`strokes`, px)
    igual de bien pasa a ser ese codo; sin tinta, solo si ya era el mismo círculo. Devuelve
    (pts, kinds, fillets) — los mismos objetos si nada cambia."""
    if len(fillets) < 2:
        return pts, kinds, fillets
    tinta = _muestras_tinta(strokes, f)
    p2, k2, f2 = list(pts), list(kinds), dict(fillets)
    cambio = False
    while True:
        hecho = None
        for ristra in _ristras(p2, k2, f2):
            # la ristra entera; si no cabe, sus tramos más largos (de izquierda a derecha)
            for n in range(len(ristra), 1, -1):
                for k in range(len(ristra) - n + 1):
                    hecho = _probar(p2, k2, f2, ristra[k:k + n], f, tinta)
                    if hecho:
                        break
                if hecho:
                    break
            if hecho:
                break
        if not hecho:
            return (p2, k2, f2) if cambio else (pts, kinds, fillets)
        p2, k2, f2 = hecho
        cambio = True
