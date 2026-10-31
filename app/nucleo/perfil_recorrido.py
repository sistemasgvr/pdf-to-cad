"""Recorrido del PERFIL LONGITUDINAL (pedido del usuario 2026-10-31). PURO (sin Qt).

Espejo de lo que hace el plugin en `CREAR_PERFIL_RED` (`PerfilGrafoCivil` + `PerfilRecorrido.cs`, ver
`API-CIVIL/proyecto1/docs/PERFIL_DISENO.md` C.1–C.5), sobre los datos de la app:

- Un perfil es de un TRAMO de una RED, no de una utilidad: las utilidades de la misma red (nombre de red o
  capa, `model_ops.red_de`) y el mismo tipo (gravedad / presión / conductos) que se tocan a ≤ `TOL_FT` forman
  un grafo. Nodos = puntas y vértices de los tramos (juntados a ≤ `TOL_FT`) y la punta de una utilidad que
  muere a mitad del tramo de otra (la parte: como `PartirTramosEnTes`). Aristas = tramos (o sus partes).
- Continuación (C.4): en cada nodo se sigue por la arista de MENOR deflexión si es ≤ `DEFLEXION_MAX_DEG` y la
  siguiente no le queda a < `EMPATE_DEG`; si no, el recorrido termina ahí (nodo «ambiguo» si fue por empate).
- Estaciones (1+00 al inicio): gravedad desde la punta de menor solera; presión y conductos desde la más al
  OESTE (o al SUR si el tramo va más norte–sur: |ΔX| < 0.3·|ΔY|). El lienzo tiene la Y hacia abajo: el sur es
  la Y MAYOR.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from nucleo import model_ops
from nucleo.model import network_kind

TOL_FT = 0.5
DEFLEXION_MAX_DEG = 45.0
EMPATE_DEG = 10.0
ESTACION_INICIAL_FT = 100.0          # «1+00»


@dataclass
class Arista:
    pipe: int
    tramo: int
    t0: float                         # parte del tramo [t0, t1] (0..1 a lo largo de pts[tramo] → pts[tramo+1])
    t1: float
    a: int                            # nodo en t0
    b: int                            # nodo en t1
    pa: tuple
    pb: tuple
    largo_px: float


@dataclass
class Grafo:
    red: str
    tipo: str                         # gravity | pressure | conduit
    nodos: list = field(default_factory=list)          # [(x, y)]
    aristas: list = field(default_factory=list)        # [Arista]
    de_nodo: dict = field(default_factory=dict)        # nodo → [índices de arista]


@dataclass
class Paso:
    arista: int
    invertida: bool                   # se recorre de b a a


@dataclass
class Recorrido:
    grafo: Grafo
    pasos: list                       # [Paso] en el sentido de las estaciones
    nodos: list                       # [índice de nodo] (len(pasos) + 1)
    estaciones: list                  # [ft] de cada nodo de `nodos`
    ambiguo_ini: bool = False         # el recorrido se cortó por un empate en ese extremo
    ambiguo_fin: bool = False

    @property
    def largo_ft(self):
        return self.estaciones[-1] - self.estaciones[0] if self.estaciones else 0.0


def texto_estacion(e):
    """1234.56 → «12+34.56»."""
    s = "-" if e < 0 else ""
    e = abs(e)
    c = int(e // 100)
    return f"{s}{c}+{e - 100 * c:05.2f}"


def _ang(dx, dy):
    return math.atan2(dy, dx)


def deflexion(d_llega, d_sale):
    """Ángulo (°) entre la dirección con que se llega al nodo y la de salida (0 = sigue recto)."""
    a = math.degrees(abs((d_sale - d_llega + math.pi) % (2 * math.pi) - math.pi))
    return a


def _tramo_pts(p, k):
    pts = p.get("pts") or []
    return pts[k], pts[k + 1]


def _punto(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def de_utilidad(pipes, i):
    """(red, tipo) de la utilidad `i`."""
    p = pipes[i]
    return model_ops.red_de(p), network_kind(p.get("layer") or "")


def construir_grafo(pipes, i, ft_per_px):
    """El grafo de la red de la utilidad `i` (las utilidades de su misma red y tipo)."""
    red, tipo = de_utilidad(pipes, i)
    tol = TOL_FT / ft_per_px if ft_per_px else 3.0
    g = Grafo(red=red, tipo=tipo)
    miembros = [j for j, p in enumerate(pipes)
                if len(p.get("pts") or []) >= 2 and not p.get("world")
                and model_ops.red_de(p) == red and network_kind(p.get("layer") or "") == tipo]
    # nodos: puntas de tramo juntadas a ≤ tol (celdas)
    celdas = {}

    def nodo(q):
        cx, cy = int(math.floor(q[0] / tol)), int(math.floor(q[1] / tol))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in celdas.get((cx + dx, cy + dy), ()):
                    x, y = g.nodos[n]
                    if (x - q[0]) ** 2 + (y - q[1]) ** 2 <= tol * tol:
                        return n
        g.nodos.append((float(q[0]), float(q[1])))
        celdas.setdefault((cx, cy), []).append(len(g.nodos) - 1)
        return len(g.nodos) - 1

    for j in miembros:
        for q in pipes[j]["pts"]:
            nodo(q)
    # T: la punta de una utilidad sobre el interior de un tramo de otra parte ese tramo
    cortes = {}                                   # (j, k) → [t]
    puntas = [(j, pipes[j]["pts"][0]) for j in miembros] + [(j, pipes[j]["pts"][-1]) for j in miembros]
    for j in miembros:
        pts = pipes[j]["pts"]
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            if L2 <= 1e-12:
                continue
            L = math.sqrt(L2)
            x0, x1 = min(a[0], b[0]) - tol, max(a[0], b[0]) + tol
            y0, y1 = min(a[1], b[1]) - tol, max(a[1], b[1]) + tol
            for jj, q in puntas:
                if jj == j or not (x0 <= q[0] <= x1 and y0 <= q[1] <= y1):
                    continue
                t = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2
                if t * L <= tol or (1 - t) * L <= tol:
                    continue
                c = _punto(a, b, t)
                if math.hypot(c[0] - q[0], c[1] - q[1]) <= tol:
                    cortes.setdefault((j, k), []).append(t)
    for j in miembros:
        pts = pipes[j]["pts"]
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            ts = [0.0] + sorted(set(round(t, 9) for t in cortes.get((j, k), ()))) + [1.0]
            for t0, t1 in zip(ts, ts[1:]):
                pa, pb = _punto(a, b, t0), _punto(a, b, t1)
                largo = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
                if largo <= 1e-9:
                    continue
                na, nb = nodo(pa), nodo(pb)
                if na == nb:
                    continue
                g.aristas.append(Arista(j, k, t0, t1, na, nb, pa, pb, largo))
                e = len(g.aristas) - 1
                g.de_nodo.setdefault(na, []).append(e)
                g.de_nodo.setdefault(nb, []).append(e)
    return g


def _dir_salida(g, e, n):
    """Rumbo con que la arista `e` SALE del nodo `n`."""
    ar = g.aristas[e]
    if ar.a == n:
        return _ang(ar.pb[0] - ar.pa[0], ar.pb[1] - ar.pa[1])
    return _ang(ar.pa[0] - ar.pb[0], ar.pa[1] - ar.pb[1])


def _otro(g, e, n):
    ar = g.aristas[e]
    return ar.b if ar.a == n else ar.a


def continuacion(g, n, e_llega, usadas):
    """(arista siguiente o None, ambiguo)."""
    d_llega = _dir_salida(g, e_llega, n) + math.pi       # se llega en sentido contrario a como «sale» hacia atrás
    cand = sorted(((deflexion(d_llega, _dir_salida(g, e, n)), e) for e in g.de_nodo.get(n, ())
                   if e != e_llega and e not in usadas), key=lambda t: (t[0], t[1]))
    if not cand:
        return None, False
    if cand[0][0] > DEFLEXION_MAX_DEG:
        return None, False
    if len(cand) > 1 and cand[1][0] - cand[0][0] < EMPATE_DEG:
        return None, True
    return cand[0][1], False


def _avanzar(g, e0, n0, usadas, visitados):
    """Desde la arista `e0` que llega al nodo `n0`: [(arista, nodo al que llega)], ambiguo al final."""
    out = []
    e, n = e0, n0
    while True:
        sig, amb = continuacion(g, n, e, usadas)
        if sig is None:
            return out, amb
        m = _otro(g, sig, n)
        usadas.add(sig)
        out.append((sig, m))
        if m in visitados:                        # lazo: termina al volver a un nodo ya visitado
            return out, False
        visitados.add(m)
        e, n = sig, m


def recorrer(g, e0):
    """Recorrido automático que pasa por la arista `e0` (ida y vuelta por sus dos puntas)."""
    ar = g.aristas[e0]
    usadas, visitados = {e0}, {ar.a, ar.b}
    adelante, amb_b = _avanzar(g, e0, ar.b, usadas, visitados)
    atras, amb_a = _avanzar(g, e0, ar.a, usadas, visitados)
    # secuencia de nodos y aristas de la punta «atrás» a la «adelante»
    nodos = [n for _e, n in reversed(atras)] + [ar.a, ar.b] + [n for _e, n in adelante]
    aristas = [e for e, _n in reversed(atras)] + [e0] + [e for e, _n in adelante]
    return _orientar(g, nodos, aristas, amb_a, amb_b)


def recorrer_desde_nodo(g, n):
    """Recorrido desde un nodo (buzón): el par de aristas más de frente; si se desvían > 45°, la más larga."""
    es = g.de_nodo.get(n, [])
    if not es:
        return None
    mejor = None
    for i, e1 in enumerate(es):
        for e2 in es[i + 1:]:
            d = deflexion(_dir_salida(g, e1, n) + math.pi, _dir_salida(g, e2, n))
            if mejor is None or d < mejor[0]:
                mejor = (d, e1)
    if mejor is not None and mejor[0] <= DEFLEXION_MAX_DEG:
        return recorrer(g, mejor[1])
    return recorrer(g, max(es, key=lambda e: g.aristas[e].largo_px))


def entre(g, e_ini, e_fin):
    """Recorrido por el camino más corto de la arista `e_ini` a la `e_fin` (las dos incluidas)."""
    if e_ini == e_fin:
        a = g.aristas[e_ini]
        return _orientar(g, [a.a, a.b], [e_ini], False, False)
    A, B = g.aristas[e_ini], g.aristas[e_fin]
    mejor = None
    for s in (A.a, A.b):
        dist, prev = {s: 0.0}, {}
        cola = [(0.0, s)]
        while cola:
            d, n = heapq.heappop(cola)
            if d > dist.get(n, math.inf):
                continue
            for e in g.de_nodo.get(n, ()):
                if e == e_ini:
                    continue
                m = _otro(g, e, n)
                nd = d + g.aristas[e].largo_px
                if nd < dist.get(m, math.inf):
                    dist[m], prev[m] = nd, (n, e)
                    heapq.heappush(cola, (nd, m))
        for t in (B.a, B.b):
            if t in dist and (mejor is None or dist[t] < mejor[0]):
                camino_n, camino_e, n = [t], [], t
                while n != s:
                    pn, pe = prev[n]
                    camino_e.append(pe)
                    camino_n.append(pn)
                    n = pn
                camino_n.reverse(); camino_e.reverse()
                otro_ini = A.b if s == A.a else A.a
                nodos = [otro_ini] + camino_n
                aristas = [e_ini] + camino_e
                if e_fin not in aristas:
                    nodos.append(B.b if t == B.a else B.a)
                    aristas.append(e_fin)
                mejor = (dist[t], nodos, aristas)
    if mejor is None:
        return None
    return _orientar(g, mejor[1], mejor[2], False, False)


def _orientar(g, nodos, aristas, amb_ini, amb_fin):
    """Sentido de las estaciones (como el plugin) y estaciones acumuladas."""
    if len(nodos) >= 2 and _al_reves(g, nodos, aristas):
        nodos, aristas = list(reversed(nodos)), list(reversed(aristas))
        amb_ini, amb_fin = amb_fin, amb_ini
    pasos = [Paso(e, g.aristas[e].a != nodos[k]) for k, e in enumerate(aristas)]
    return Recorrido(g, pasos, list(nodos), [], amb_ini, amb_fin)


def _al_reves(g, nodos, aristas):
    a, b = g.nodos[nodos[0]], g.nodos[nodos[-1]]
    if g.tipo == "gravity":
        za, zb = getattr(g, "_z_punta", {}).get(nodos[0]), getattr(g, "_z_punta", {}).get(nodos[-1])
        if za is not None and zb is not None and abs(za - zb) > 1e-6:
            return zb < za
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) < 0.3 * abs(dy):
        return dy > 0                                 # empieza en el SUR (Y del lienzo mayor)
    return dx < 0                                     # empieza en el OESTE (X menor)


def estaciones(rec, ft_per_px, largo_pasos_ft=None):
    """Llena `rec.estaciones` (ft) desde `ESTACION_INICIAL_FT`. `largo_pasos_ft` = largo de cada paso en
    planta (si no, la cuerda)."""
    e = ESTACION_INICIAL_FT
    out = [e]
    for k, p in enumerate(rec.pasos):
        largo = largo_pasos_ft[k] if largo_pasos_ft else rec.grafo.aristas[p.arista].largo_px * ft_per_px
        e += largo
        out.append(e)
    rec.estaciones = out
    return rec


def z_solera(pipes, ar, t):
    """Solera de la arista en su parámetro local t (0 = pa, 1 = pb) sobre el tramo de su utilidad."""
    p = pipes[ar.pipe]
    zz = model_ops.cotas_tramo(p, ar.tramo) or (0.0, 0.0)
    tt = ar.t0 + (ar.t1 - ar.t0) * t
    return float(zz[0]) + (float(zz[1]) - float(zz[0])) * tt


def marcar_soleras(g, pipes):
    """Solera más baja en cada nodo (para el sentido de las estaciones en gravedad)."""
    z = {}
    for ar in g.aristas:
        for n, t in ((ar.a, 0.0), (ar.b, 1.0)):
            v = z_solera(pipes, ar, t)
            if n not in z or v < z[n]:
                z[n] = v
    g._z_punta = z
    return g


def arista_cerca(g, x, y, i=None):
    """La arista más cercana a (x, y) (de la utilidad `i` si se da)."""
    mejor = None
    for e, ar in enumerate(g.aristas):
        if i is not None and ar.pipe != i:
            continue
        d = _dist_seg((x, y), ar.pa, ar.pb)
        if mejor is None or d < mejor[0]:
            mejor = (d, e)
    return mejor[1] if mejor else None


def nodo_cerca(g, x, y, tol_px):
    mejor = None
    for n, (nx, ny) in enumerate(g.nodos):
        d = math.hypot(nx - x, ny - y)
        if d <= tol_px and (mejor is None or d < mejor[0]):
            mejor = (d, n)
    return mejor[1] if mejor else None


def _dist_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(a[0] + dx * t - p[0], a[1] + dy * t - p[1])


def extender(rec, al_final=True):
    """Un paso más por la punta (aunque haya empate: la de menor deflexión)."""
    g = rec.grafo
    n = rec.nodos[-1] if al_final else rec.nodos[0]
    e_llega = rec.pasos[-1].arista if al_final else rec.pasos[0].arista
    usadas = {p.arista for p in rec.pasos}
    d_llega = _dir_salida(g, e_llega, n) + math.pi
    cand = sorted(((deflexion(d_llega, _dir_salida(g, e, n)), e) for e in g.de_nodo.get(n, ())
                   if e not in usadas), key=lambda t: (t[0], t[1]))
    if not cand:
        return None
    e = cand[0][1]
    m = _otro(g, e, n)
    nodos = list(rec.nodos)
    aristas = [p.arista for p in rec.pasos]
    if al_final:
        nodos.append(m); aristas.append(e)
    else:
        nodos.insert(0, m); aristas.insert(0, e)
    pasos = [Paso(a, g.aristas[a].a != nodos[k]) for k, a in enumerate(aristas)]
    return Recorrido(g, pasos, nodos, [], rec.ambiguo_ini, rec.ambiguo_fin)


def acortar(rec, al_final=True):
    if len(rec.pasos) <= 1:
        return None
    g = rec.grafo
    nodos = rec.nodos[:-1] if al_final else rec.nodos[1:]
    aristas = [p.arista for p in rec.pasos]
    aristas = aristas[:-1] if al_final else aristas[1:]
    pasos = [Paso(a, g.aristas[a].a != nodos[k]) for k, a in enumerate(aristas)]
    return Recorrido(g, pasos, nodos, [], False, False)


def desde(pipes, i, x, y, ft_per_px):
    """Recorrido automático que pasa por el tramo de la utilidad `i` más cercano a (x, y), o None."""
    if not (0 <= i < len(pipes)) or len(pipes[i].get("pts") or []) < 2:
        return None
    g = marcar_soleras(construir_grafo(pipes, i, ft_per_px), pipes)
    e = arista_cerca(g, x, y, i)
    return None if e is None else recorrer(g, e)


def rehacer(rec):
    """El mismo recorrido con el sentido de las estaciones recalculado (tras cambiar cotas)."""
    nodos = list(rec.nodos)
    aristas = [p.arista for p in rec.pasos]
    return _orientar(rec.grafo, nodos, aristas, rec.ambiguo_ini, rec.ambiguo_fin)


def ramales(rec, k):
    """Aristas que salen del nodo k del recorrido y no son parte de él (los ramales en ese punto)."""
    g = rec.grafo
    usadas = {p.arista for p in rec.pasos}
    return [e for e in g.de_nodo.get(rec.nodos[k], ()) if e not in usadas]


def ramal(g, n, e):
    """Recorrido de un RAMAL: arranca en el nodo `n` (la T de la principal) por la arista `e` y sigue de frente
    alejándose de la principal (sin volver a pasar por `n`)."""
    m = _otro(g, e, n)
    usadas, visitados = {e}, {n, m}
    adelante, amb = _avanzar(g, e, m, usadas, visitados)
    nodos = [n, m] + [x for _e, x in adelante]
    aristas = [e] + [x for x, _n in adelante]
    return _orientar(g, nodos, aristas, False, amb)
