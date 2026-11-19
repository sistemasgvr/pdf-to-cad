"""Esqueleto de UNA componente y su eje (PURO: numpy + cv2, sin Qt). Lo usa `imagen_trazos`.

- `tramos(pix)`: caminos de píxeles del esqueleto entre puntas y nudos (un nudo = un punto que
  comparten sus tramos), con la adyacencia sin diagonales redundantes.
- `podar`: quita espolones cortos (punta → nudo).
- `ancho_medio`: w = área / largo, corregido por las puntas libres.
- `ejes`: cada tramo llevado al CENTRO de su tinta (medida de lado a lado), simplificado
  (Douglas–Peucker por índices: el punto del nudo queda exacto) y con cada punta libre ALARGADA
  hasta el borde de su tinta (como mucho w). Nada se une ni se cierra.
"""

from __future__ import annotations

import math

import numpy as np

ESPOLON_W = 1.5        # espolón (punta → nudo) más corto que esto·w = ruido del esqueleto
COLA_W = 0.6           # punta libre: lo que el esqueleto tuerce cerca del final (·w) no cuenta
PASO_MUESTRA = 0.25    # paso del muestreo de lado a lado (px)
_VEC = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


# ── grafo del esqueleto ──────────────────────────────────────────────────────────────────────

def _vecinos(pix: set) -> dict:
    """Adyacencia del esqueleto sin diagonales redundantes (una escalera queda como camino simple)."""
    ady = {}
    for (y, x) in pix:
        v = []
        for dy, dx in _VEC:
            q = (y + dy, x + dx)
            if q not in pix:
                continue
            if dy and dx and ((y + dy, x) in pix or (y, x + dx) in pix):
                continue
            v.append(q)
        ady[(y, x)] = sorted(v)
    return ady


def _grafo(pix: set):
    """(adyacencia, nudo de cada píxel nudo → id, centro de cada nudo, puntas)."""
    ady = _vecinos(pix)
    cruces = sorted(p for p, v in ady.items() if len(v) >= 3)
    nudo, centros = {}, []
    for p in cruces:                                   # cruces pegados = un solo nudo
        if p in nudo:
            continue
        k = len(centros)
        pila, grupo = [p], []
        nudo[p] = k
        while pila:
            q = pila.pop()
            grupo.append(q)
            for r in ady[q]:
                if r not in nudo and len(ady[r]) >= 3:
                    nudo[r] = k
                    pila.append(r)
        g = np.array(grupo, float)
        centros.append((float(g[:, 1].mean()), float(g[:, 0].mean())))
    puntas = sorted(p for p, v in ady.items() if len(v) == 1)
    return ady, nudo, centros, puntas


def _es_nodo(p, ady, nudo):
    return p in nudo or len(ady[p]) != 2


def tramos(pix: set):
    """Caminos de píxeles entre nodos (puntas o nudos) y lazos sin nodos."""
    ady, nudo, centros, puntas = _grafo(pix)
    vistos, salida = set(), []

    def recorrer(a, b):
        cam = [a, b]
        vistos.add((a, b)); vistos.add((b, a))
        prev, cur = a, b
        while not _es_nodo(cur, ady, nudo):
            sig = [q for q in ady[cur] if q != prev and (cur, q) not in vistos]
            if not sig:
                break
            vistos.add((cur, sig[0])); vistos.add((sig[0], cur))
            prev, cur = cur, sig[0]
            cam.append(cur)
            if cur == a:
                break
        return cam

    inicios = sorted(p for p in ady if _es_nodo(p, ady, nudo))
    for p in inicios:
        for q in ady[p]:
            if (p, q) in vistos:
                continue
            if p in nudo and q in nudo and nudo[p] == nudo[q]:
                continue
            salida.append(recorrer(p, q))
    for p in sorted(ady):                              # lazos cerrados sin nodos
        for q in ady[p]:
            if (p, q) not in vistos:
                salida.append(recorrer(p, q))
    return salida, ady, nudo, centros


def largo_px(cam) -> float:
    a = np.array(cam, float)
    return float(np.hypot(*np.diff(a, axis=0).T).sum()) if len(a) > 1 else 0.0


def podar(pix: set, w_de) -> set:
    """Quita espolones (punta → nudo) cortos, de a uno por vuelta, hasta que no quede ninguno."""
    for _ in range(8):
        caminos, ady, nudo, _c = tramos(pix)
        w = w_de(pix, caminos, ady)
        quitar = set()
        for cam in caminos:
            a, b = cam[0], cam[-1]
            punta_nudo = (len(ady[a]) == 1 and b in nudo) or (len(ady[b]) == 1 and a in nudo)
            if punta_nudo and largo_px(cam) < ESPOLON_W * w:
                quitar.update(q for q in cam if q not in nudo)
        if not quitar:
            return pix
        pix = pix - quitar
    return pix


def ancho_medio(area: int, caminos, ady) -> float:
    """w de la componente: área = w·L + (w²/2) por cada punta libre (el esqueleto no llega al final)."""
    largo = sum(largo_px(c) for c in caminos)
    n = sum(1 for v in ady.values() if len(v) == 1)
    if largo <= 0:
        return math.sqrt(area)
    if n == 0:
        return area / largo
    a = n / 2.0
    return (-largo + math.sqrt(largo * largo + 4 * a * area)) / (2 * a)


# ── eje centrado, simplificado y alargado ────────────────────────────────────────────────────

def _dentro(m, x, y) -> bool:
    xi, yi = math.floor(x + 0.5), math.floor(y + 0.5)
    return 0 <= yi < m.shape[0] and 0 <= xi < m.shape[1] and bool(m[yi, xi])


def _cortes(m, pts, nor, lim):
    """Por cada punto: (desplazamiento del centro, ancho) de la tinta de `m` que lo atraviesa en
    la dirección de su normal. Ancho 0 = no se llega al borde (zona ancha) o el punto no es tinta."""
    ts = np.arange(-lim, lim + 1e-9, PASO_MUESTRA) + PASO_MUESTRA / 2
    x = np.floor(pts[:, :1] + ts[None, :] * nor[:, :1] + 0.5).astype(int)
    y = np.floor(pts[:, 1:] + ts[None, :] * nor[:, 1:] + 0.5).astype(int)
    ok = (x >= 0) & (y >= 0) & (x < m.shape[1]) & (y < m.shape[0])
    dent = np.zeros(x.shape, bool)
    dent[ok] = m[y[ok], x[ok]]
    t, i0 = len(ts), int(np.argmin(np.abs(ts)))
    idx = np.arange(t)
    lo = np.where(~dent[:, :i0], idx[None, :i0], -1).max(axis=1) + 1
    hi = np.where(~dent[:, i0 + 1:], idx[None, i0 + 1:], t).min(axis=1) - 1
    valido = dent[:, i0] & (lo > 0) & (hi < t - 1)
    off = np.where(valido, (ts[lo] + ts[np.minimum(hi, t - 1)]) / 2, 0.0)
    anc = np.where(valido, ts[np.minimum(hi, t - 1)] - ts[lo] + PASO_MUESTRA, 0.0)
    return off, anc


def _centrar(m, cam_xy, w, fijos):
    """Cada punto al centro de su trazo. Los fijos (nudos) quedan tal cual y los puntos a menos
    de 2·w de un nudo se quitan: caen en la mancha del cruce, donde no hay «de lado a lado».
    Devuelve (puntos, anchos)."""
    pts = np.array(cam_xy, float)
    n = len(pts)
    fuera = set()
    for f in fijos:
        cerca = np.hypot(*(pts - pts[f]).T) < 2 * w + 1.0
        fuera.update(int(i) for i in np.nonzero(cerca)[0] if int(i) not in fijos)
    k = max(2, int(round(w)))
    i = np.arange(n)
    d = pts[np.minimum(n - 1, i + k)] - pts[np.maximum(0, i - k)]
    nd = np.hypot(d[:, 0], d[:, 1])
    nor = np.column_stack([-d[:, 1], d[:, 0]]) / np.maximum(nd, 1e-9)[:, None]
    off, anc = _cortes(m, pts, nor, 2 * w + 3)
    usar = (nd > 1e-9) & (anc > 0) & (anc <= 1.6 * w + 2)
    usar[list(fijos | fuera)] = False
    salida = pts + nor * np.where(usar, off, 0.0)[:, None]
    quedan = [j for j in range(n) if j not in fuera]
    return salida[quedan], [float(v) for v in anc[usar]]


def _dp(pts: np.ndarray, eps: float) -> list[int]:
    """Douglas–Peucker por índices (los puntos que quedan son EXACTAMENTE los de entrada)."""
    n = len(pts)
    if n <= 2:
        return list(range(n))
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    pila = [(0, n - 1)]
    while pila:
        i, j = pila.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        d = b - a
        nd = math.hypot(*d)
        seg = pts[i + 1:j] - a
        dist = np.abs(seg[:, 0] * d[1] - seg[:, 1] * d[0]) / nd if nd > 1e-12 else np.hypot(*seg.T)
        k = int(np.argmax(dist))
        if dist[k] > eps:
            keep[i + 1 + k] = True
            pila += [(i, i + 1 + k), (i + 1 + k, j)]
    return [int(i) for i in np.nonzero(keep)[0]]


def _alargar(m, punta, atras, w):
    """La punta libre sigue en su rumbo (de `atras` a ella) hasta el borde de su tinta (como mucho w)."""
    d = np.array(punta) - np.array(atras)
    nd = math.hypot(*d)
    if nd < 1e-9:
        return punta
    d /= nd
    t = 0.0
    while t + PASO_MUESTRA <= w and _dentro(m, punta[0] + d[0] * (t + PASO_MUESTRA),
                                            punta[1] + d[1] * (t + PASO_MUESTRA)):
        t += PASO_MUESTRA
    t = min(w, t + PASO_MUESTRA / 2) if t > 0 else 0.0
    return (float(punta[0] + d[0] * t), float(punta[1] + d[1] * t))


def _acumulado(pts) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])


def _sin_colas(pts, w, ini, fin):
    """Quita de cada punta libre los puntos a menos de `COLA_W`·w: ahí el esqueleto se tuerce hacia
    una esquina del trazo (la punta se rehace luego alargando por el rumbo de lo que queda)."""
    if len(pts) < 3:
        return pts
    s = _acumulado(pts)
    cola = COLA_W * w
    if s[-1] <= 2 * cola + 1.0:
        return pts
    keep = np.ones(len(pts), bool)
    if ini:
        keep &= s >= cola
    if fin:
        keep &= s <= s[-1] - cola
    return pts[keep] if keep.sum() >= 2 else pts


def _atras(pts, w):
    """Punto a ~w de la primera punta por el camino (para el rumbo de esa punta)."""
    s = _acumulado(pts)
    i = int(np.searchsorted(s, w))
    return pts[max(1, min(i, len(pts) - 1))]


def ejes(sub, w, caminos, original, nudo, centros, eps):
    """[(puntos (x, y) en px de `sub`, grosor px)] de los caminos del esqueleto. `original` =
    adyacencia antes de cortar símbolos: una punta es LIBRE si allí tenía un solo vecino."""
    lineas = []
    for cam in caminos:
        if len(cam) < 2:
            continue
        libre = [len(original.get(cam[0], ())) == 1, len(original.get(cam[-1], ())) == 1]
        if largo_px(cam) < 1.0 and not any(libre):
            continue
        xy = [(float(x), float(y)) for (y, x) in cam]
        fijos = set()
        for i, p in ((0, cam[0]), (len(cam) - 1, cam[-1])):
            if p in nudo:
                xy[i] = centros[nudo[p]]
                fijos.add(i)
        pts, anchos = _centrar(sub, xy, w, fijos)
        if len(pts) < 2:
            continue
        ini = libre[0] and 0 not in fijos
        fin = libre[1] and len(cam) - 1 not in fijos
        pts = _sin_colas(pts, w, ini, fin)
        sel = [(float(pts[i][0]), float(pts[i][1])) for i in _dp(pts, eps)]
        if ini:
            sel[0] = _alargar(sub, sel[0], tuple(_atras(pts, w)), 2 * w)
        if fin:
            sel[-1] = _alargar(sub, sel[-1], tuple(_atras(pts[::-1], w)), 2 * w)
        if len(sel) == 1 or (len(sel) == 2 and sel[0] == sel[1]):
            continue
        lineas.append((sel, float(np.median(anchos)) if anchos else w))
    return lineas
