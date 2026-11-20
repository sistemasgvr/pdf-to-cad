"""recognition_imagen_nudos.py — continuidad de la red en IMAGEN (PURO, sin Qt ni fitz): nudos, puntas que no llegan
a su buzón y llegadas en T. Lo llama `recognition_imagen_rectas.enderezar`.

Reporte del usuario (2026-11-20, QS SD North de Phoenix, cinco capturas): «si te digo que tiene que ser continua,
tiene que ser continua… no podemos tener dobles innecesarios, quiebres innecesarios». Lo que se veía en las 18 hojas:

  1. NUDOS: el esqueleto de la banda deja, donde la línea pasa por un símbolo de contorno fino (la cajita «J» de una
     estructura, la caja del sumidero), donde termina la banda (una «horquilla» de dos ramalitos) o bajo un rótulo,
     un enredo de trozos cortos con puntas sueltas. Un grupo de trozos cortos (< `NUDO_PT`) que se tocan, con al
     menos una punta suelta y que cabe en `NUDO_CAJA_PT`, es un nudo: sus trozos se van y lo que las líneas largas
     tenían dentro de su caja también. Las que entraban se vuelven a unir: dos de frente = la misma tubería que
     PASA RECTO; las demás llegan en T a la que pasa, o se juntan en un punto; una sola = la punta de la banda.
     Un trozo que va de un símbolo a OTRO (la conexión del buzón «M» al sumidero) o que llega a un buzón no es nudo.
  2. PUNTA QUE NO LLEGA A SU BUZÓN: una punta suelta cuyo rumbo entra en un buzón a ≤ `BOVEDA_EXT_PT` de su borde
     (el sumidero «P», el «DW», el «M») llega a su centro (vértice «vault»), si ninguna otra línea se cruza antes.
  3. LLEGADA EN T TORCIDA: el último tramo corto de un ramal que tuerce para caer en un vértice de la principal se
     cambia por la prolongación RECTA del tramo anterior hasta la principal.

Todo se busca por celdas (`Rejilla`); el orden de recorrido es el de la lista (mismos desempates).
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from reconocimiento import recognition_imagen_rectas as RR
from reconocimiento import recognition_vault_snap as vault_snap
from reconocimiento.recognition_imagen_indice import Rejilla, dist_en

Pt = Tuple[float, float]

NUDO_PT = 12.0              # trozo corto (pt): ≈ 3.5 anchos de banda; los ramalitos de una horquilla miden 5–12 pt
NUDO_CAJA_PT = 16.0         # el nudo cabe en un cuadrado de este lado (la cajita «J» ≈ 7 pt, el sumidero ≈ 10 pt)
NUDO_PAD_PT = 1.0           # margen de la caja del nudo
NUDO_JUNTO_PT = 3.0         # una punta suelta a ≤ esto de la caja del nudo también entra a él
FRENTE_DEG = 25.0           # dos líneas que entran al nudo de frente (± esto) son la misma que pasa recto …
FRENTE_LADO_PT = 3.0        # … si una cae a ≤ esto de la recta de la otra
BOVEDA_EXT_PT = 8.0         # una punta suelta que mira a un buzón a ≤ esto de su borde llega a él …
BOVEDA_LADO_FRAC = 0.5      # … si su recta pasa a ≤ esta fracción de su medio lado (+ ½ margen) del centro …
BOVEDA_GIRO_DEG = 20.0      # … y llegar al centro no la tuerce más que esto
LLEGADA_PT = 15.0           # último tramo de un ramal en T, más corto que esto …
LLEGADA_GIRO_DEG = 10.0     # … que tuerce más que esto respecto del anterior (al menos 2× más largo): se endereza


# ── utilidades ───────────────────────────────────────────────────────────────────────────────────────────────────
def _liang(a: Pt, b: Pt, caja) -> Optional[Tuple[float, float]]:
    """Parámetros (t0, t1) del tramo a–b dentro de la caja (x0, y0, x1, y1), o None."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - caja[0]), (dx, caja[2] - a[0]), (-dy, a[1] - caja[1]), (dy, caja[3] - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return t0, t1


def _dentro(q: Pt, caja) -> bool:
    """¿`q` está ESTRICTAMENTE dentro de la caja? (un vértice sobre el borde cuenta como fuera)"""
    return caja[0] < q[0] < caja[2] and caja[1] < q[1] < caja[3]


def _recortar(pl, caja):
    """Lo de `pl` dentro de la caja fuera: (pts, kinds, codos, ¿entraba por el inicio?, ¿por el final?, cuerdas);
    None si no pasa por dentro de la caja; "todo" si queda entera dentro. Un paso de lado a lado queda como CUERDA
    recta entre el punto donde entra y donde sale (los dos «bend»; `cuerdas` = sus índices)."""
    pts, kinds, fil = pl.pts_pdf, pl.kinds, dict(pl.fillets or {})
    ins = [_dentro(q, caja) for q in pts]
    if all(ins):
        return "todo"
    out: list = []
    ks: list = []
    nuevo: dict = {}
    cuerdas = []
    toco = False
    entrada = None
    if not ins[0]:
        out.append(tuple(pts[0])); ks.append(kinds[0]); nuevo[0] = 0
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        c = _liang(a, b, caja)
        if c is not None and c[1] - c[0] > 1e-9 and (ins[i - 1] or ins[i] or _dentro(
                (a[0] + (c[0] + c[1]) / 2 * (b[0] - a[0]), a[1] + (c[0] + c[1]) / 2 * (b[1] - a[1])), caja)):
            toco = True
            t0, t1 = c
            if not ins[i - 1]:
                out.append((a[0] + t0 * (b[0] - a[0]), a[1] + t0 * (b[1] - a[1]))); ks.append("bend")
                entrada = len(out) - 1
            if not ins[i]:
                out.append((a[0] + t1 * (b[0] - a[0]), a[1] + t1 * (b[1] - a[1]))); ks.append("bend")
                if entrada is not None:
                    cuerdas.append((entrada, len(out) - 1))
                entrada = None
                out.append(tuple(b)); ks.append(kinds[i]); nuevo[i] = len(out) - 1
        elif not ins[i]:
            out.append(tuple(b)); ks.append(kinds[i]); nuevo[i] = len(out) - 1
    if not toco:
        return None
    lim, lk, mapa = [], [], {}
    for j, (q, k) in enumerate(zip(out, ks)):
        if lim and math.dist(lim[-1], q) < 1e-9:
            mapa[j] = len(lim) - 1
            if k != "bend":
                lk[-1] = k
            continue
        mapa[j] = len(lim)
        lim.append(q); lk.append(k)
    if len(lim) < 2:
        return "todo"
    if ins[0]:
        lk[0] = "end"
    if ins[-1]:
        lk[-1] = "end"
    codos = {mapa[nuevo[i]]: f for i, f in fil.items() if i in nuevo}
    cuerdas = [(mapa[x], mapa[y]) for x, y in cuerdas if mapa[x] != mapa[y]]
    return lim, lk, codos, ins[0], ins[-1], cuerdas


def _poner_punta(pl, end: int, p: Pt, kind: str, rumbo=None) -> None:
    """La punta `end` de `pl` pasa a `p` (con su clase). Si el último tramo sigue el `rumbo` dado (±3°), la punta se
    corre; si no, se agrega un vértice."""
    pts, kinds, fil = list(pl.pts_pdf), list(pl.kinds), dict(pl.fillets or {})
    i, j = (0, 1) if end == 0 else (len(pts) - 1, len(pts) - 2)
    q, v = pts[i], pts[j]
    recto = False
    if rumbo is not None and i not in fil:
        L = math.dist(q, v)
        recto = L > 1e-9 and ((q[0] - v[0]) * rumbo[0] + (q[1] - v[1]) * rumbo[1]) / L >= math.cos(math.radians(3.0))
    if recto or math.dist(q, p) < 1e-9:
        pts[i], kinds[i] = tuple(p), kind
    elif end == 0:
        kinds[0] = "bend"
        pts.insert(0, tuple(p)); kinds.insert(0, kind)
        fil = {k + 1: f for k, f in fil.items()}
    else:
        kinds[-1] = "bend"
        pts.append(tuple(p)); kinds.append(kind)
    pl.pts_pdf, pl.kinds, pl.fillets = pts, kinds, fil


def _rumbo_lejos(pts, end: int, desde: float, hasta: float):
    """Rumbo hacia AFUERA de la punta `end` medido entre los puntos de la línea a `desde` y a `hasta` de ella (sin el
    último trocito, que en un nudo es el rodeo del esqueleto); el de `RR._rumbo` si la línea es más corta."""
    seq = pts if end == 0 else pts[::-1]
    def en(d):
        acc = 0.0
        for a, b in zip(seq, seq[1:]):
            L = math.dist(a, b)
            if acc + L >= d and L > 1e-12:
                t = (d - acc) / L
                return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            acc += L
        return None
    p, q = en(desde), en(hasta)
    if p is None or q is None:
        return RR._rumbo(pts, end, hasta)
    L = math.dist(p, q)
    return None if L < 1e-9 else ((p[0] - q[0]) / L, (p[1] - q[1]) / L)


# ── 1. nudos ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _nudos(imgs: list, zoom: float, rej: Rejilla, simbolos) -> List[Tuple[list, tuple]]:
    """[(trozos, caja)] de los nudos: grupos de trozos cortos que se tocan, con alguna punta suelta, que caben en
    `NUDO_CAJA_PT`."""
    tol = RR.T_SOBRE_PT * zoom
    pad_s = RR.SIMBOLO_PAD_PT * zoom
    cortos = []
    for pl in imgs:
        if RR._largo(pl.pts_pdf) >= NUDO_PT * zoom or "vault" in (pl.kinds[0], pl.kinds[-1]):
            continue
        if _conector(pl, simbolos, pad_s):
            continue
        cortos.append(pl)
    ids = {id(pl): k for k, pl in enumerate(cortos)}
    padre = list(range(len(cortos)))

    def raiz(k):
        while padre[k] != k:
            padre[k] = padre[padre[k]]
            k = padre[k]
        return k
    for k, pl in enumerate(cortos):
        for end in (0, -1):
            q = pl.pts_pdf[end]
            for o, ks in rej.cerca(q, tol):
                j = ids.get(id(o))
                if j is not None and j != k and dist_en(q, o.pts_pdf, ks)[0] <= tol:
                    padre[raiz(k)] = raiz(j)
    grupos: dict = {}
    for k in range(len(cortos)):
        grupos.setdefault(raiz(k), []).append(cortos[k])
    out = []
    lado = NUDO_CAJA_PT * zoom
    pad = NUDO_PAD_PT * zoom
    for g in grupos.values():
        xs = [q[0] for pl in g for q in pl.pts_pdf]
        ys = [q[1] for pl in g for q in pl.pts_pdf]
        if max(xs) - min(xs) > lado or max(ys) - min(ys) > lado:
            continue
        if not any(RR._libre(pl, e, rej, tol) and pl.kinds[e] not in ("tee", "junction", "cut")
                   for pl in g for e in (0, -1)):
            continue                     # sin ninguna punta suelta: tramos cortos de verdad entre otras líneas
        out.append((g, (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)))
    return out


def _conector(pl, simbolos, pad: float) -> bool:
    """¿Sus DOS puntas están en símbolos? Es una conexión entre estructuras (el buzón «M» al sumidero, F–F–rejilla),
    no un nudo; el marco de un símbolo lo quita `quitar_marcos`."""
    def en(q):
        return any(x0 - pad <= q[0] <= x1 + pad and y0 - pad <= q[1] <= y1 + pad for x0, y0, x1, y1 in simbolos)
    return en(pl.pts_pdf[0]) and en(pl.pts_pdf[-1])


def _punto_medio(pts) -> Pt:
    L = RR._largo(pts) / 2
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if acc + d >= L and d > 1e-12:
            t = (L - acc) / d
            return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
        acc += d
    return tuple(pts[-1])


def limpiar_nudos(imgs: list, zoom: float, simbolos=(), bovedas=None, pad: float = 0.0) -> list:
    """Los nudos fuera y las líneas que entraban vueltas a unir (ver el módulo). Devuelve las líneas que se fueron."""
    rej = Rejilla(imgs, RR.CELDA_PT * zoom)
    fuera: list = []
    ids_fuera: set = set()
    for trozos, caja in _nudos(imgs, zoom, rej, simbolos):
        if any(id(t) in ids_fuera for t in trozos):
            continue
        c = ((caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2)
        if bovedas is not None and RR._boveda_de(c, bovedas, pad) is not None:
            continue                     # junto a un buzón manda `_punta_al_centro`
        quitar = list(trozos)
        tocadas = []
        entradas, cuerdas = [], []
        r = math.hypot(caja[2] - caja[0], caja[3] - caja[1])
        for pl, _ks in rej.cerca(c, r):
            if any(pl is t for t in trozos) or id(pl) in ids_fuera:
                continue
            rc = _recortar(pl, caja)
            if rc is None:
                continue
            if rc == "todo":
                quitar.append(pl)
                continue
            pts, kinds, codos, e0, e1, cu = rc
            pl.pts_pdf, pl.kinds, pl.fillets = pts, kinds, codos
            tocadas.append(pl)
            if e0:
                entradas.append([pl, 0])
            if e1:
                entradas.append([pl, -1])
            cuerdas += [(pl, a, b) for a, b in cu]
        for pl in quitar:
            ids_fuera.add(id(pl))
        RR._sacar(imgs, quitar, rej)
        fuera += quitar
        for pl in tocadas:                       # (sus tramos de antes ya no existen)
            if id(pl) not in ids_fuera:
                rej.poner(pl)
        # puntas sueltas que quedan JUSTO afuera de la caja (el esqueleto cortó la línea al salir del símbolo)
        cerca_pt = NUDO_JUNTO_PT * zoom
        ya = {(id(pl), e) for pl, e in entradas}
        for pl, _ks in rej.cerca(c, r + cerca_pt):
            if id(pl) in ids_fuera:
                continue
            for e in (0, -1):
                q = pl.pts_pdf[e]
                if (id(pl), e) not in ya and pl.kinds[e] not in ("vault", "tee", "junction", "cut")                         and _dist_caja(q, caja) <= cerca_pt and RR._libre(pl, e, rej, RR.T_SOBRE_PT * zoom):
                    entradas.append([pl, e])
                    ya.add((id(pl), e))
        for pl, _e in entradas:
            rej.poner(pl)
        puntos = [q for t in quitar for q in t.pts_pdf]
        _volver_a_unir(imgs, entradas, cuerdas, caja, zoom, rej, fuera, ids_fuera, puntos)
    return fuera


def _volver_a_unir(imgs, entradas, cuerdas, caja, zoom, rej, fuera, ids_fuera, puntos=()) -> None:
    """Las líneas que entraban al nudo: de frente = la misma que pasa recto; las demás en T a la que pasa, o juntas."""
    cos_f = math.cos(math.radians(FRENTE_DEG))
    lado = FRENTE_LADO_PT * zoom
    datos = []
    for pl, e in entradas:
        u = _rumbo_lejos(pl.pts_pdf, e, NUDO_PAD_PT * 3 * zoom, RR.RUMBO_PT * zoom)
        if u is not None:
            datos.append((pl, e, tuple(pl.pts_pdf[e]), u))
    pares = []
    for i in range(len(datos)):
        for j in range(i + 1, len(datos)):
            a, b = datos[i], datos[j]
            if a[0] is b[0]:
                continue
            frente = -(a[3][0] * b[3][0] + a[3][1] * b[3][1])
            de_lado = abs((b[2][0] - a[2][0]) * a[3][1] - (b[2][1] - a[2][1]) * a[3][0])
            adelante = (b[2][0] - a[2][0]) * a[3][0] + (b[2][1] - a[2][1]) * a[3][1]
            if frente >= cos_f and de_lado <= lado and adelante > -1e-9:
                pares.append((-frente, de_lado, i, j))
    pares.sort()
    usados: set = set()
    pasan = []                           # tramos rectos por donde pasa una línea (para las T)
    for _f, _l, i, j in pares:
        if i in usados or j in usados:
            continue
        usados |= {i, j}
        a, b = datos[i], datos[j]
        if RR._unibles(a[0], b[0]):
            RR._concatenar(a[0], a[1], b[0], b[1], hueco=True)
            RR._sacar(imgs, [b[0]], rej)
            fuera.append(b[0])
            ids_fuera.add(id(b[0]))
            rej.poner(a[0])
            # las otras entradas de b ahora son de a: ya no se usan (b se fue)
            for k, d in enumerate(datos):
                if d[0] is b[0]:
                    usados.add(k)
        else:
            m = ((a[2][0] + b[2][0]) / 2, (a[2][1] + b[2][1]) / 2)
            _poner_punta(a[0], a[1], m, "junction")
            _poner_punta(b[0], b[1], m, "junction")
            rej.poner(a[0]); rej.poner(b[0])
        pasan.append((a[2], b[2]))
    pasan += [(pl.pts_pdf[x], pl.pts_pdf[y]) for pl, x, y in cuerdas if id(pl) not in ids_fuera
              and max(x, y) < len(pl.pts_pdf)]
    resto = [d for k, d in enumerate(datos) if k not in usados and id(d[0]) not in ids_fuera]
    sueltas = []
    alcance = 2 * math.hypot(caja[2] - caja[0], caja[3] - caja[1])
    for pl, e, p, u in resto:
        mejor = None
        for a, b in pasan:
            hit = RR._cruce_rayo(p, u, a, b)
            if hit is not None and hit[0] <= alcance and (mejor is None or hit[0] < mejor):
                mejor = hit[0]
        if mejor is not None:
            _poner_punta(pl, e, (p[0] + u[0] * mejor, p[1] + u[1] * mejor), "tee", u)
            rej.poner(pl)
        else:
            sueltas.append((pl, e, p, u))
    if not sueltas:
        return
    c = ((caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2)
    if len(sueltas) == 1:                # la punta de la banda: por su rumbo, hasta donde llegaba lo del nudo
        pl, e, p, u = sueltas[0]
        s = max([(q[0] - p[0]) * u[0] + (q[1] - p[1]) * u[1] for q in puntos] or
                [(c[0] - p[0]) * u[0] + (c[1] - p[1]) * u[1]])
        if s > 1e-9:
            _poner_punta(pl, e, (p[0] + u[0] * s, p[1] + u[1] * s), pl.kinds[e], u)
            rej.poner(pl)
        return
    punto = c
    if len(sueltas) == 2:                # una esquina dentro del nudo: el cruce de las dos rectas
        (_, _, p1, u1), (_, _, p2, u2) = sueltas
        den = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(den) > 1e-9:
            s1 = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / den
            s2 = ((p2[0] - p1[0]) * u1[1] - (p2[1] - p1[1]) * u1[0]) / den
            if 0 < s1 <= alcance and 0 < s2 <= alcance:
                punto = (p1[0] + u1[0] * s1, p1[1] + u1[1] * s1)
    for pl, e, p, u in sueltas:
        _poner_punta(pl, e, punto, "junction", u)
        rej.poner(pl)


# ── 2. puntas que no llegan a su buzón ───────────────────────────────────────────────────────────────────────────
def a_su_boveda(imgs: list, zoom: float, vaults_geo: Sequence[dict], pad: float) -> int:
    """Una punta suelta cuyo rumbo entra en un buzón a ≤ `BOVEDA_EXT_PT` de su borde llega a su centro. Devuelve
    cuántas."""
    vs = [vg for vg in vaults_geo or () if vg.get("importable", True) and vault_snap.boundary(vg) is not None]
    if not vs:
        return 0
    celda = 16.0 * zoom
    grid: dict = {}
    for i, vg in enumerate(vs):
        cx, cy = vault_snap.vault_centroid(vg)
        grid.setdefault((int(math.floor(cx / celda)), int(math.floor(cy / celda))), []).append(i)
    rej = Rejilla(imgs, RR.CELDA_PT * zoom)
    tol = RR.T_SOBRE_PT * zoom
    ext = BOVEDA_EXT_PT * zoom
    hechas = 0
    for pl in imgs:
        for end in (0, -1):
            if pl.kinds[end] in ("vault", "tee", "junction", "cut") or not RR._libre(pl, end, rej, tol):
                continue
            q = tuple(pl.pts_pdf[end])
            u = RR._rumbo(pl.pts_pdf, end, RR.RUMBO_PT * zoom)
            if u is None:
                continue
            gx, gy = int(math.floor(q[0] / celda)), int(math.floor(q[1] / celda))
            mejor = None
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    for i in grid.get((gx + dx, gy + dy), ()):
                        vg = vs[i]
                        c = vault_snap.vault_centroid(vg)
                        r0 = RR._medio_lado(vg)
                        r = r0 + pad
                        f = (c[0] - q[0]) * u[0] + (c[1] - q[1]) * u[1]
                        lat = abs((c[0] - q[0]) * u[1] - (c[1] - q[1]) * u[0])
                        if f <= 0 or lat > min(BOVEDA_LADO_FRAC * r0 + pad / 2, f * math.tan(math.radians(BOVEDA_GIRO_DEG))):
                            continue             # (mira al CENTRO del buzón, no lo roza: si no, quedaba torcida)
                        hueco = f - math.sqrt(max(0.0, r * r - lat * lat))
                        if hueco <= ext and (mejor is None or (hueco, i) < (mejor[0], mejor[1])):
                            mejor = (hueco, i, c)
            if mejor is None:
                continue
            hueco, _i, c = mejor
            if _cruza_otra(pl, q, c, rej):
                continue                 # otra línea antes: llega a ella (`_prolongar_ramales`), no al buzón
            _poner_punta(pl, end, c, "vault", u)
            rej.poner(pl)
            hechas += 1
    return hechas


def _cruza_otra(pl, q: Pt, c: Pt, rej: Rejilla) -> bool:
    L = math.dist(q, c)
    if L < 1e-9:
        return False
    u = ((c[0] - q[0]) / L, (c[1] - q[1]) / L)
    for o, ks in rej.cerca(((q[0] + c[0]) / 2, (q[1] + c[1]) / 2), L / 2 + 1):
        if o is pl:
            continue
        for k in ks:
            hit = RR._cruce_rayo(q, u, o.pts_pdf[k], o.pts_pdf[k + 1])
            if hit is not None and 1e-3 * L < hit[0] < L * (1 - 1e-3):   # (las que nacen o mueren en sus puntas no)
                return True
    return False


# ── 3. llegada en T torcida ──────────────────────────────────────────────────────────────────────────────────────
def llegar_recto(imgs: list, zoom: float) -> int:
    """El último tramo corto de un ramal en T que tuerce para caer en la principal → la prolongación recta del tramo
    anterior hasta la principal (sin pasar de 2× el tramo que se quita). Devuelve cuántas."""
    rej = Rejilla(imgs, RR.CELDA_PT * zoom)
    tol = RR.T_SOBRE_PT * zoom
    cos_giro = math.cos(math.radians(LLEGADA_GIRO_DEG))
    hechas = 0
    for pl in imgs:
        for end in (0, -1):
            pts = pl.pts_pdf
            if len(pts) < 3 or pl.kinds[end] not in ("tee", "junction"):
                continue
            seq = pts if end == 0 else pts[::-1]
            a, b, c = seq[0], seq[1], seq[2]
            fil = pl.fillets or {}
            ib = 1 if end == 0 else len(pts) - 2
            if ib in fil or pl.kinds[ib] == "vault":
                continue
            l1, l2 = math.dist(a, b), math.dist(b, c)
            if l1 >= LLEGADA_PT * zoom or l2 < 2 * l1 or l1 < 1e-9:
                continue
            u = ((b[0] - c[0]) / l2, (b[1] - c[1]) / l2)
            v = ((a[0] - b[0]) / l1, (a[1] - b[1]) / l1)
            if u[0] * v[0] + u[1] * v[1] >= cos_giro:
                continue
            anfitrionas = [(o, ks) for o, ks in rej.cerca(a, tol) if o is not pl and dist_en(a, o.pts_pdf, ks)[0] <= tol]
            if len(anfitrionas) != 1:
                continue
            o = anfitrionas[0][0]
            mejor = None
            for k in range(len(o.pts_pdf) - 1):
                hit = RR._cruce_rayo(b, u, o.pts_pdf[k], o.pts_pdf[k + 1])
                if hit is not None and hit[0] <= 2 * l1 and (mejor is None or hit[0] < mejor):
                    mejor = hit[0]
            if mejor is None:
                continue
            p = (b[0] + u[0] * mejor, b[1] + u[1] * mejor)
            nuevos = list(pts)
            kinds = list(pl.kinds)
            if end == 0:
                del nuevos[0], kinds[0]
                nuevos[0], kinds[0] = p, "tee"
                pl.fillets = {k - 1: f for k, f in fil.items()}
            else:
                del nuevos[-1], kinds[-1]
                nuevos[-1], kinds[-1] = p, "tee"
            pl.pts_pdf, pl.kinds = nuevos, kinds
            rej.poner(pl)
            hechas += 1
    return hechas


# ── 4. el marco de un símbolo ────────────────────────────────────────────────────────────────────────────────────
MARCO_PT = 7.0              # una línea toda a ≤ esto de la caja de un símbolo y que no lo cruza es su marco
MARCO_MAX_LADO_PT = 16.0    # (solo símbolos chicos: sumidero, cajita)


def _dist_caja(q: Pt, caja) -> float:
    dx = max(caja[0] - q[0], 0.0, q[0] - caja[2])
    dy = max(caja[1] - q[1], 0.0, q[1] - caja[3])
    return math.hypot(dx, dy)


def _por_celdas(cajas, celda: float) -> dict:
    grid: dict = {}
    for i, s in enumerate(cajas):
        for gx in range(int(math.floor(s[0] / celda)), int(math.floor(s[2] / celda)) + 1):
            for gy in range(int(math.floor(s[1] / celda)), int(math.floor(s[3] / celda)) + 1):
                grid.setdefault((gx, gy), []).append(i)
    return grid


def _prolongado(a: Pt, b: Pt, L: float):
    """El tramo a–b alargado `L` por cada lado (su recta, para ver si apunta a una caja)."""
    d = math.dist(a, b)
    u = ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
    return (a[0] - u[0] * L, a[1] - u[1] * L), (b[0] + u[0] * L, b[1] + u[1] * L)


def quitar_marcos(imgs: list, zoom: float, simbolos=()) -> list:
    """El contorno fino de la caja de un símbolo (el sumidero hexagonal entre dos buzones: sus bordes salían como dos
    rayas o una «U» con puntas sueltas) no es red: una línea sin punta en un buzón, toda a ≤ `MARCO_PT` de la caja
    de UN símbolo chico y que no pasa por dentro de él, se va. Devuelve las que se fueron."""
    lado = MARCO_MAX_LADO_PT * zoom
    cajas = [s for s in simbolos if s[2] - s[0] <= lado and s[3] - s[1] <= lado]
    if not cajas:
        return []
    celda = 16.0 * zoom
    grid = _por_celdas(cajas, celda)
    d = MARCO_PT * zoom
    fuera = []
    for pl in imgs:
        if "vault" in (pl.kinds[0], pl.kinds[-1]):
            continue
        q = pl.pts_pdf[0]
        gx0, gy0 = int(math.floor(q[0] / celda)), int(math.floor(q[1] / celda))
        cand: set = set()
        for gx in (-1, 0, 1):
            for gy in (-1, 0, 1):
                cand.update(grid.get((gx0 + gx, gy0 + gy), ()))
        for i in sorted(cand):
            s = cajas[i]
            if all(_dist_caja(p, s) <= d for p in pl.pts_pdf):
                dentro = (s[0] + zoom, s[1] + zoom, s[2] - zoom, s[3] - zoom)
                if dentro[0] < dentro[2] and dentro[1] < dentro[3] and any(
                        _liang(*_prolongado(a, b, 4 * lado), dentro) is not None
                        for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:]) if math.dist(a, b) > 1e-9):
                    continue                 # apunta al símbolo (la línea, la conexión F–F): no corre por su borde
                fuera.append(pl)
                break
    ids = {id(pl) for pl in fuera}
    imgs[:] = [pl for pl in imgs if id(pl) not in ids]
    return fuera


# ── 5. la línea que cruza un símbolo ─────────────────────────────────────────────────────────────────────────────
PUENTE_PT = 10.0            # a ≤ esto del borde del símbolo: lo que está a un lado y al otro …
PUENTE_LADO_PT = 5.0        # … a ≤ esto de la recta que pasa por su centro …
PUENTE_GIRO_DEG = 25.0      # … y opuestos (± esto)
PUENTE_MIRA_DEG = 60.0      # la punta suelta mira hacia el otro lado (± esto)


def cruzar_simbolos(imgs: list, zoom: float, simbolos=(), vaults_geo=(), pad: float = 0.0) -> int:
    """Una punta suelta a un lado de un símbolo chico (el sumidero) y del otro lado un buzón u otra punta suelta, en
    recta por el centro del símbolo: la línea PASA por el símbolo (la tinta de la red no se ve bajo él) y llega
    allá. Solo con al menos una punta suelta (no se inventa una línea entre dos buzones sueltos). Devuelve cuántas."""
    lado = MARCO_MAX_LADO_PT * zoom
    cajas = [s for s in simbolos if s[2] - s[0] <= lado and s[3] - s[1] <= lado]
    if not cajas or not imgs:
        return 0
    rej = Rejilla(imgs, RR.CELDA_PT * zoom)
    tol = RR.T_SOBRE_PT * zoom
    vs = [vg for vg in vaults_geo or () if vg.get("importable", True) and vault_snap.boundary(vg) is not None]
    centros = [vault_snap.vault_centroid(vg) for vg in vs]
    # una caja que ya es un buzón (su centro dentro) no: ahí manda `_punta_al_centro`
    cajas = [s for s in cajas if not any(s[0] <= c[0] <= s[2] and s[1] <= c[1] <= s[3] for c in centros)]
    celda = 16.0 * zoom

    def celda_de(q):
        return int(math.floor(q[0] / celda)), int(math.floor(q[1] / celda))
    g_bov: dict = {}
    for i, c in enumerate(centros):
        g_bov.setdefault(celda_de(c), []).append(i)
    cos_op = math.cos(math.radians(PUENTE_GIRO_DEG))
    cos_mira = math.cos(math.radians(PUENTE_MIRA_DEG))
    alcance = PUENTE_PT * zoom
    hechas = 0
    for s in cajas:
        c = ((s[0] + s[2]) / 2, (s[1] + s[3]) / 2)
        gx, gy = celda_de(c)
        cands = []                              # (tipo, objeto, punto)
        vistos: set = set()
        for pl, _ks in rej.cerca(c, alcance + (s[2] - s[0] + s[3] - s[1])):
            for e in (0, -1):
                q = tuple(pl.pts_pdf[e])
                if (id(pl), e) in vistos or pl.kinds[e] in ("vault", "tee", "junction", "cut"):
                    continue
                vistos.add((id(pl), e))
                if _dist_caja(q, s) <= alcance and RR._libre(pl, e, rej, tol):
                    cands.append(("punta", (pl, e), q))
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for i in g_bov.get((gx + dx, gy + dy), ()):
                    if _dist_caja(centros[i], s) <= alcance + RR._medio_lado(vs[i]):
                        cands.append(("boveda", i, centros[i]))
        mejor = None
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                a, b = cands[i], cands[j]
                if a[0] == "boveda" and b[0] == "boveda":
                    continue
                if a[0] == "punta" and b[0] == "punta" and a[1][0] is b[1][0]:
                    continue
                ua = (a[2][0] - c[0], a[2][1] - c[1])
                ub = (b[2][0] - c[0], b[2][1] - c[1])
                la, lb = math.hypot(*ua), math.hypot(*ub)
                L = math.dist(a[2], b[2])
                if la < 1e-9 or lb < 1e-9 or L < 1e-9:
                    continue
                if (ua[0] * ub[0] + ua[1] * ub[1]) / (la * lb) > -cos_op:
                    continue
                lat = abs((c[0] - a[2][0]) * (b[2][1] - a[2][1]) - (c[1] - a[2][1]) * (b[2][0] - a[2][0])) / L
                if lat > PUENTE_LADO_PT * zoom:
                    continue
                ok = True
                for x, y in ((a, b), (b, a)):    # la punta MIRA al otro lado, no pasa de costado
                    if x[0] == "punta":
                        u = RR._rumbo(x[1][0].pts_pdf, x[1][1], RR.RUMBO_PT * zoom)
                        v = ((y[2][0] - x[2][0]) / L, (y[2][1] - x[2][1]) / L)
                        if u is None or u[0] * v[0] + u[1] * v[1] < cos_mira:
                            ok = False
                if ok and (mejor is None or (lat, L) < mejor[0]):
                    mejor = ((lat, L), a, b)
        if mejor is None:
            continue
        _m, a, b = mejor
        if a[0] != "punta":
            a, b = b, a
        pl, e = a[1]
        if _cruza_otra(pl, a[2], b[2], rej) or (b[0] == "punta" and not RR._libre(b[1][0], b[1][1], rej, tol)) \
                or not RR._libre(pl, e, rej, tol):
            continue
        u = RR._rumbo(pl.pts_pdf, e, RR.RUMBO_PT * zoom)
        if b[0] == "boveda":
            _poner_punta(pl, e, b[2], "vault", u)
        else:
            o, eo = b[1]
            if RR._unibles(pl, o):
                RR._concatenar(pl, e, o, eo, hueco=True)
                RR._sacar(imgs, [o], rej)
            else:
                m = ((a[2][0] + b[2][0]) / 2, (a[2][1] + b[2][1]) / 2)
                _poner_punta(pl, e, m, "junction")
                _poner_punta(o, eo, m, "junction")
                rej.poner(o)
        rej.poner(pl)
        hechas += 1
    return hechas


# ── 6. símbolos apilados unidos por un taquito de banda ─────────────────────────────────────────────────────────
TAQUITO_PT = 7.0            # un símbolo de a lo sumo esto por lado entre otros dos es el trozo de banda que los une
TAQUITO_TOCA_PT = 2.0       # … si los toca (hueco ≤ esto) …
TAQUITO_GIRO_DEG = 25.0     # … por lados opuestos (± esto)
SIMBOLO_PUNTA_PT = 1.5      # una punta suelta a ≤ esto de la caja de un símbolo de la cadena llega a su centro


def _hueco_cajas(a, b) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def _centro(s) -> Pt:
    return (s[0] + s[2]) / 2, (s[1] + s[3]) / 2


def cadenas_de_simbolos(imgs: list, zoom: float, simbolos=(), vaults_geo=(), pad: float = 0.0) -> list:
    """Buzón, rejilla y sumidero apilados en columna (QS SD North, captura 12 del usuario: «debe pasar recto»): entre
    uno y otro, el trocito de banda que los une sale como un SÍMBOLO chico (6×6 pt), no como línea, y la columna
    quedaba sin tramo. Un símbolo de ≤ `TAQUITO_PT` que toca a otros dos por lados opuestos los une: si ninguna
    línea va ya de uno al otro, se agrega la recta centro a centro (al centro del buzón si lo hay). Las puntas
    sueltas pegadas a un símbolo de la cadena llegan a su centro. Devuelve las líneas nuevas (ya en `imgs`)."""
    import copy
    if not simbolos or not imgs:
        return []
    lado = MARCO_MAX_LADO_PT * zoom
    cajas = [tuple(s[:4]) for s in simbolos if s[2] - s[0] <= lado and s[3] - s[1] <= lado]
    tac = TAQUITO_PT * zoom
    toca = TAQUITO_TOCA_PT * zoom
    cos_op = math.cos(math.radians(TAQUITO_GIRO_DEG))
    celda = 16.0 * zoom
    grid = _por_celdas(cajas, celda)
    vs = [vg for vg in vaults_geo or () if vg.get("importable", True) and vault_snap.boundary(vg) is not None]

    def punto(s):
        """Centro de la caja, o el del buzón que la contiene."""
        c = _centro(s)
        for vg in vs:
            if vault_snap.vault_contains(vg, c, pad):
                return tuple(vault_snap.vault_centroid(vg)), "vault"
        return c, "junction"
    pares = []
    for i, s in enumerate(cajas):
        if s[2] - s[0] > tac or s[3] - s[1] > tac:
            continue
        c = _centro(s)
        g = (int(math.floor(c[0] / celda)), int(math.floor(c[1] / celda)))
        vec = sorted({j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((g[0] + dx, g[1] + dy), ())
                      if j != i and _hueco_cajas(cajas[j], s) <= toca
                      and max(cajas[j][2] - cajas[j][0], cajas[j][3] - cajas[j][1]) > tac})
        # (los dos vecinos son ESTRUCTURAS, más grandes que el taquito: una línea a guiones de cuadritos no se encadena)
        mejor = None
        for x in range(len(vec)):
            for y in range(x + 1, len(vec)):
                a, b = cajas[vec[x]], cajas[vec[y]]
                ua = (_centro(a)[0] - c[0], _centro(a)[1] - c[1])
                ub = (_centro(b)[0] - c[0], _centro(b)[1] - c[1])
                la, lb = math.hypot(*ua), math.hypot(*ub)
                if la < 1e-9 or lb < 1e-9:
                    continue
                cos = (ua[0] * ub[0] + ua[1] * ub[1]) / (la * lb)
                if cos <= -cos_op and (mejor is None or cos < mejor[0]):
                    mejor = (cos, vec[x], vec[y])
        if mejor is not None:
            pares.append((mejor[1], mejor[2]))
    if not pares:
        return []
    rej = Rejilla(imgs, RR.CELDA_PT * zoom)
    tol = 2.0 * zoom
    nuevas = []
    usadas: set = set()
    for ia, ib in pares:
        (pa, ka), (pb, kb) = punto(cajas[ia]), punto(cajas[ib])
        if math.dist(pa, pb) < 1e-6:
            continue
        ya = False                       # ¿ya hay una línea que vaya de uno al otro?
        for pl, ks in rej.cerca(pa, tol):
            if dist_en(pa, pl.pts_pdf, ks)[0] <= tol and dist_en(pb, pl.pts_pdf, range(len(pl.pts_pdf) - 1))[0] <= tol:
                ya = True
                break
        usadas |= {ia, ib}
        if ya:
            continue
        modelo = min(imgs, key=lambda pl: dist_en(pa, pl.pts_pdf, range(len(pl.pts_pdf) - 1))[0])
        nueva = copy.copy(modelo)
        nueva.pts_pdf, nueva.kinds, nueva.fillets = [pa, pb], [ka, kb], {}
        nueva.grosor = dict(getattr(modelo, "grosor", None) or {})
        imgs.append(nueva)
        nuevas.append(nueva)
        rej.poner(nueva)
    # las puntas sueltas pegadas a un símbolo de la cadena llegan a su centro
    cerca = SIMBOLO_PUNTA_PT * zoom
    for i in sorted(usadas):
        s = cajas[i]
        p, k = punto(s)
        for pl, _ks in rej.cerca(_centro(s), lado):
            for e in (0, -1):
                q = pl.pts_pdf[e]
                if pl.kinds[e] in ("vault", "tee", "junction", "cut") or _dist_caja(q, s) > cerca \
                        or math.dist(q, p) < 1e-9 or not RR._libre(pl, e, rej, RR.T_SOBRE_PT * zoom):
                    continue
                _poner_punta(pl, e, p, k)
                rej.poner(pl)
    return nuevas


# ── 7. la línea que llega a la unión vecina de un buzón ─────────────────────────────────────────────────────────
SATELITE_PT = 16.0          # unión unida a un buzón por un tramito de a lo sumo esto


def a_su_buzon(imgs: list, zoom: float) -> int:
    """«No debería desviarse» (captura 12): una línea que va de un buzón a una UNIÓN que está pegada a otro buzón (un
    tramito ≤ `SATELITE_PT` las une) llega a ese buzón, no a la unión: la rejilla de arriba bajaba en diagonal hasta
    la unión de la curva, a 14 pt del «M». Devuelve cuántas."""
    rej = Rejilla(imgs, RR.CELDA_PT * zoom)
    tol = RR.T_SOBRE_PT * zoom
    sat = SATELITE_PT * zoom
    hechas = 0
    tramitos = [pl for pl in imgs if len(pl.pts_pdf) == 2 and RR._largo(pl.pts_pdf) <= sat
                and sorted(pl.kinds) == ["junction", "vault"]]
    for t in tramitos:
        j = t.pts_pdf[0] if t.kinds[0] == "junction" else t.pts_pdf[-1]
        b = t.pts_pdf[-1] if t.kinds[0] == "junction" else t.pts_pdf[0]
        for pl, _ks in rej.cerca(j, tol):
            if pl is t:
                continue
            for e in (0, -1):
                if math.dist(pl.pts_pdf[e], j) > tol or pl.kinds[e] != "junction":
                    continue
                otra = -1 if e == 0 else 0
                if pl.kinds[otra] != "vault" or len(pl.pts_pdf) != 2 or RR._largo(pl.pts_pdf) > 2 * sat:
                    continue                 # solo la conexión corta de buzón a buzón
                a = pl.pts_pdf[otra]
                if _cruza_otra(pl, a, b, rej) or math.dist(a, b) < 1e-6:
                    continue
                pl.pts_pdf = [a, b] if otra == 0 else [b, a]
                pl.kinds = ["vault", "vault"]
                rej.poner(pl)
                hechas += 1
    return hechas
