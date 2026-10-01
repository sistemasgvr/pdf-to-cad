"""recognition_vault_snap.py — IMÁN de puntas a bóvedas (PURO: sin Qt ni fitz).

Pedido del usuario (2026-10-01, captura de un SÓLIDO eléctrico de 6.3 × 8.3 ft con
dos líneas que llegan a sus lados y quedan a un pelo del borde): «en cada buzón las
líneas quedan separadas… que cuando esté muy cerca se haga snap y se una solito»,
«sin alterar el reconocimiento», «solo cuando la línea esté bien cerca al buzón».

Es un paso ADICIONAL al final de `recognize_page`: no cambia ninguna decisión del
núcleo (qué línea llega a qué bóveda, nodos, codos), solo cierra el hueco que queda
entre la punta de una línea y el contorno DIBUJADO de la bóveda.

Por qué hay hueco: el núcleo (`recognition_geom._vault_entry`) corta la llegada en el
recuadro del CLÚSTER del símbolo con 1 pt de margen (`v.bbox(1.0)`) o en el círculo
+ 1 pt, y el clúster puede ser más grande que el contorno (rejillas, textos del
símbolo). Medido en los 4 PDFs × 4 utilidades con bóvedas: de 955 puntas «stop» junto
a una bóveda, 512 quedan a 0.8–1.25 pt FUERA del contorno y 85 a 1.25–3 pt. Con el zoom
del editor (3.5) son 3.5–10 px: `model_ops.attach_vault_geometry` no veía la llegada
(busca el vértice dentro del contorno ±2 px) y la caja quedaba SUELTA en el centro,
sin unirse a la línea (235 de 604 bóvedas con llegada).

Reglas (la de oro del núcleo: un extremo solo se desliza por SU recta):
  · Solo puntas «stop» (el núcleo ya decidió que la línea llega a la bóveda) y «end»
    (punta libre). Nunca tee/junction/cut/edge/vault ni vértices interiores. Una punta
    que coincide con otra línea está unida a ella: se mueve solo si las que coinciden
    son puntas que van al MISMO punto del contorno (la misma línea en dos capas, DU06
    h.14), y van juntas; si toca el interior de otra línea, no.
  · Una punta que ya está DENTRO de un contorno no se toca (ya está unida).
  · El punto nuevo es el cruce MÁS CERCANO de la recta de la punta con el contorno de
    alguna bóveda: hacia adelante (prolongar) o, solo en «stop», hacia atrás (la línea
    pasó por encima de la bóveda y el núcleo la cortó 1 pt después). Nunca más atrás
    que el vértice anterior ni dentro del arco de un codo vecino.
  · Distancia máxima `SNAP_STOP_PT`=3 en «stop» y `SNAP_END_PT`=1.5 en «end» (solo
    hacia adelante: no se borra tinta). A 4–5 pt quedan planos enredados (otra caja de
    otra capa entre la punta y el contorno).
  · Si la recta de la punta no corta el contorno (corre por el costado de la caja,
    llega a una esquina) no se mueve: no se inventa un quiebre.
  · La punta queda «stop» → en conduit la caja de la bóveda va en ese vértice y en
    gravedad la BZ de la punta se lleva la geometría (una sola estructura por bóveda).
"""
import math
from typing import List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

SNAP_STOP_PT = 3.0        # punta «stop»: hueco máximo hasta el contorno (pt)
SNAP_END_PT = 1.5         # punta libre «end»: «bien cerca», solo hacia adelante (pt)
SNAP_KINDS = ("stop", "end")
DIR_MIN_PT = 2.0          # largo de recta mínimo para tomar el rumbo de la punta
DIR_COLLINEAR_PT = 0.25   # vértices intermedios a ≤ esto de esa recta (si no, no hay rumbo fiable)
SHARED_END_PT = 0.5       # otra línea con un vértice aquí = punta unida a ella
SAME_TARGET_PT = 0.05     # …y se mueven juntas solo si van a este mismo punto del contorno
_EPS = 1e-6


def boundary(vg: dict):
    """Contorno de la bóveda en px: ("poly", [esquinas]) o ("circle", (cx, cy, r)); None si
    no hay geometría (círculo sin `circle` de una versión vieja)."""
    corners = vg.get("corners")
    if corners and len(corners) >= 3:
        return "poly", [(float(x), float(y)) for x, y in corners]
    circ = vg.get("circle")
    if circ and circ[2] > 0:
        return "circle", (float(circ[0]), float(circ[1]), float(circ[2]))
    return None


def contains(b, q: Pt) -> bool:
    """¿`q` está dentro del contorno (sin contar el borde)?"""
    kind, g = b
    if kind == "circle":
        return math.hypot(q[0] - g[0], q[1] - g[1]) < g[2] - _EPS
    inside = False
    n = len(g)
    for i in range(n):
        a, c = g[i], g[(i + 1) % n]
        if (a[1] > q[1]) != (c[1] > q[1]):
            x = a[0] + (q[1] - a[1]) * (c[0] - a[0]) / (c[1] - a[1])
            if x > q[0] + _EPS:
                inside = not inside
    return inside


def crossings(q: Pt, u: Pt, b) -> List[float]:
    """Parámetros t (px) donde la recta q + t·u corta el contorno."""
    kind, g = b
    if kind == "circle":
        dx, dy = q[0] - g[0], q[1] - g[1]
        bb = dx * u[0] + dy * u[1]
        disc = bb * bb - (dx * dx + dy * dy - g[2] * g[2])
        if disc < 0:
            return []
        sq = math.sqrt(disc)
        return [-bb - sq, -bb + sq]
    out = []
    n = len(g)
    for i in range(n):
        a, c = g[i], g[(i + 1) % n]
        ex, ey = c[0] - a[0], c[1] - a[1]
        den = u[0] * ey - u[1] * ex
        if abs(den) < 1e-12:
            continue                                   # lado paralelo a la recta
        wx, wy = a[0] - q[0], a[1] - q[1]
        t = (wx * ey - wy * ex) / den
        s = (wx * u[1] - wy * u[0]) / den
        if -_EPS <= s <= 1 + _EPS:
            out.append(t)
    return out


def end_direction(pts: Sequence[Pt], end: int, min_len: float, tol: float) -> Optional[Pt]:
    """Rumbo (unitario) hacia afuera de la punta `end` (0 o -1): de la recta que llega a
    ella con al menos `min_len` de largo y sus vértices intermedios a ≤ `tol` de ella.
    None si la punta es un trozo corto que gira (no hay recta fiable)."""
    seq = list(pts) if end == -1 else list(reversed(pts))
    q = seq[-1]
    for k in range(len(seq) - 2, -1, -1):
        a = seq[k]
        L = math.hypot(q[0] - a[0], q[1] - a[1])
        if L < min_len and k > 0:
            continue
        if L < _EPS:
            return None
        u = ((q[0] - a[0]) / L, (q[1] - a[1]) / L)
        for m in seq[k + 1:-1]:                        # los de en medio, sobre esa recta
            if abs((m[0] - a[0]) * u[1] - (m[1] - a[1]) * u[0]) > tol:
                return None
        return u
    return None


def _fillet_limit(pl, end: int) -> Optional[float]:
    """Si el vecino de la punta es la esquina C de un codo: distancia de C a su
    tangencia de ese lado (la punta no puede quedar más cerca de C que eso)."""
    pts = pl.pts_pdf
    n = 1 if end == 0 else len(pts) - 2
    f = (getattr(pl, "fillets", None) or {}).get(n)
    if not f or n <= 0 or n >= len(pts) - 1:
        return None
    C, q = pts[n], pts[end]
    tps = [p for p in (f.get("a"), f.get("b")) if p is not None]
    if not tps:
        return None
    tp = min(tps, key=lambda p: math.hypot(p[0] - q[0], p[1] - q[1]))
    return math.hypot(tp[0] - C[0], tp[1] - C[1])


def snap_ends_to_vaults(polylines: Sequence, vaults_geo: Sequence[dict], zoom: float,
                        stop_pt: float = SNAP_STOP_PT, end_pt: float = SNAP_END_PT) -> List[dict]:
    """Lleva al contorno de su bóveda las puntas «stop»/«end» que quedaron cerca (ver el
    docstring del módulo). Muta `pl.pts_pdf` y `pl.kinds` de cada polilínea movida (la
    punta queda «stop»). Devuelve [{"pl", "end", "from", "to", "move_pt", "vault"}]."""
    z = max(float(zoom), 1e-9)
    bounds = [(vi, b) for vi, vg in enumerate(vaults_geo or ()) if (b := boundary(vg))]
    if not bounds:
        return []
    lines = [pl for pl in polylines if len(getattr(pl, "pts_pdf", None) or ()) >= 2]
    # 1) destino de cada punta candidata, con las posiciones ORIGINALES
    cand = {}                                          # (li, end) → (p, t, vi)
    for li, pl in enumerate(lines):
        pts, kinds = pl.pts_pdf, pl.kinds
        if not kinds or len(kinds) != len(pts):
            continue
        for end in (0, -1):
            k = kinds[end]
            if k not in SNAP_KINDS:
                continue
            q = pts[end]
            if any(contains(b, q) for _vi, b in bounds):
                continue                               # ya dentro: unida
            u = end_direction(pts, end, DIR_MIN_PT * z, DIR_COLLINEAR_PT * z)
            if u is None:
                continue
            lim = (stop_pt if k == "stop" else end_pt) * z
            best = None
            for vi, b in bounds:
                for t in crossings(q, u, b):
                    if k != "stop" and t <= 0:
                        continue                       # punta libre: solo prolongar
                    if abs(t) <= lim and (best is None or abs(t) < abs(best[0])):
                        best = (t, vi)
            if best is None or abs(best[0]) < 1e-3:
                continue
            t, vi = best
            p = (q[0] + t * u[0], q[1] + t * u[1])
            nb = pts[1] if end == 0 else pts[-2]
            if t < 0:
                if -t >= math.hypot(q[0] - nb[0], q[1] - nb[1]) - _EPS:
                    continue                           # recortaría más que el último tramo
                fl = _fillet_limit(pl, end)
                if fl is not None and math.hypot(p[0] - nb[0], p[1] - nb[1]) < fl - _EPS:
                    continue                           # se comería el arco del codo
            cand[(li, end)] = (p, t, vi)

    # 2) una punta que coincide con un vértice de OTRA línea está unida a ella: solo se
    #    mueve si ese vértice es también una punta candidata que va al MISMO punto del
    #    contorno (la misma línea en dos capas, dos líneas que llegan juntas), y entonces
    #    todas van exactamente al mismo punto. Si toca el interior de otra línea, o alguna
    #    de las que coinciden no se mueve igual, no se mueve ninguna.
    share = SHARED_END_PT * z
    grid = {}
    for li, pl in enumerate(lines):
        n = len(pl.pts_pdf)
        for i, v in enumerate(pl.pts_pdf):
            e = 0 if i == 0 else (-1 if i == n - 1 else None)
            grid.setdefault((int(v[0] // share), int(v[1] // share)), []).append((li, e, v))

    def touching(li, q):
        cx, cy = int(q[0] // share), int(q[1] // share)
        return [(lj, e) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                for lj, e, v in grid.get((cx + dx, cy + dy), ())
                if lj != li and math.hypot(v[0] - q[0], v[1] - q[1]) <= share]

    groups, seen = [], set()
    for key in cand:
        if key in seen:
            continue
        group, stack, ok = [], [key], True
        while stack:                                   # puntas que se tocan, en cadena
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            group.append(k)
            for other in touching(k[0], lines[k[0]].pts_pdf[k[1]]):
                if other[1] is None or other not in cand:
                    ok = False                         # interior de otra línea / punta que no se mueve
                elif other not in seen:
                    stack.append(other)
        if not ok:
            continue
        tx = sum(cand[k][0][0] for k in group) / len(group)
        ty = sum(cand[k][0][1] for k in group) / len(group)
        if all(math.hypot(cand[k][0][0] - tx, cand[k][0][1] - ty) <= SAME_TARGET_PT * z for k in group):
            groups.append((group, (tx, ty)))

    out = []
    for group, p in groups:
        for li, end in group:
            pl = lines[li]
            _p, t, vi = cand[(li, end)]
            out.append({"pl": pl, "end": end, "from": pl.pts_pdf[end], "to": p,
                        "move_pt": t / z, "vault": vi})
    for o in out:                                      # recién ahora se mueven (orden indistinto)
        o["pl"].pts_pdf[o["end"]] = o["to"]
        o["pl"].kinds[o["end"]] = "stop"
    return out


def vault_centroid(vg: dict) -> Pt:
    """Centro del contorno (o del círculo) de la bóveda; su `center` si no hay geometría."""
    b = boundary(vg)
    if b is None:
        return tuple(vg["center"])
    kind, g = b
    if kind == "circle":
        return g[0], g[1]
    return sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g)


def vault_contains(vg: dict, q: Pt, pad: float = 0.0) -> bool:
    """¿`q` cae dentro de la bóveda (contorno o círculo) con `pad` px de margen?"""
    b = boundary(vg)
    if b is None:
        return False
    kind, g = b
    if kind == "circle":
        return math.hypot(q[0] - g[0], q[1] - g[1]) <= g[2] + pad
    if contains(b, q):
        return True
    n = len(g)
    for i in range(n):
        a, c = g[i], g[(i + 1) % n]
        vx, vy = c[0] - a[0], c[1] - a[1]
        L2 = vx * vx + vy * vy
        s = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
        if math.hypot(q[0] - a[0] - s * vx, q[1] - a[1] - s * vy) <= pad:
            return True
    return False
