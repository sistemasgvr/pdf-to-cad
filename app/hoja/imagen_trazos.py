"""De la máscara de UN color: líneas (ejes), símbolos y rellenos (PURO: numpy + cv2 + skimage, sin Qt).

Entrada: la máscara booleana de un color (`imagen_paleta.mascara`) en px de la imagen pintada a
`escala` px/pt. Salida (`Piezas`), en px de esa máscara. Por cada componente conexa (8-vecinos):

1. Se rellenan los huecos que la PROPIA tinta encierra si son chicos y rectangulares
   (`imagen_huecos.rellenar`): la tubería «en caja» de Phoenix SD (contorno de 1 px con bloques rellenos y
   cajitas blancas) queda como UNA banda maciza → UN eje continuo; una rejilla de sumidero queda
   como un cuadro macizo. No se une nada que la tinta no una ya (nada de cierres morfológicos).
2. El eje lo da `imagen_esqueleto`: esqueleto podado, tramos entre puntas y nudos (un nudo = un
   punto que comparten sus tramos), centrado de lado a lado, Douglas–Peucker (0.25·w, tope 0.5 pt)
   y cada punta libre alargada hasta el borde de su tinta.
3. SÍMBOLOS: componente no alargada (largo < `ALARGADA_K`·w); o, pegados a una línea, una
   rejilla (≥ `MALLA_HUECOS` huecos parecidos juntos), una zona densa en nudos o el aro con letra
   (hueco que no se rellena); la línea sigue hasta el borde del símbolo. Guiones compactos SUELTOS
   en fila (otros planos, sin contorno) son líneas, cada uno la suya (`_en_fila`: nunca une).
4. RELLENO: ≥ `RAYADO_MIN` trazos rectos paralelos (±5°) a paso regular = rayado; sus
   componentes no dan líneas, y si son la mayoría (por área) del color, `relleno=True` y no se
   devuelve ninguna línea.

Determinista: todo se recorre en orden de filas y columnas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from skimage.morphology import skeletonize

from hoja import imagen_bandas as B
from hoja import imagen_esqueleto as E
from hoja import imagen_huecos as H
from hoja import imagen_puentes as P

ALARGADA_K = 3.0       # largo < K·w → símbolo compacto
ESPOLON_W = E.ESPOLON_W
RUIDO_PX = 12          # componentes de menos píxeles = ruido
RAYADO_MIN = 8         # mínimo de trazos paralelos a paso regular para que sea rayado
DP_W = 0.25            # Douglas–Peucker = DP_W·w …
DP_MAX_PT = 0.5        # … con tope de 0.5 pt
NUDOS_DENSOS = 4       # nudos dentro de un círculo de 2·w para que sea zona de símbolo
RAYADO_VECINO_PT = 6.0 # paralela vecina de un rayado: a ≤ esto (pt) de costado
RAYADO_ANG = 5.0       # tolerancia de paralelas (grados)
FILA_MIN = 3           # compactos parecidos en fila a partir de cuántos son guiones
FILA_DIST = 3.0        # vecino de fila: centro a ≤ esto·largo por su eje
PASO_MALLA_PT = 3.0    # tramo entre nudos más corto que esto (pt) = malla de un símbolo


@dataclass
class Simbolo:
    cx: float
    cy: float
    ancho: float
    alto: float
    forma: str


@dataclass
class Piezas:
    lineas: list[list[tuple[float, float]]]
    grosores: list[float]
    simbolos: list[Simbolo]
    relleno: bool


# ── una componente ───────────────────────────────────────────────────────────────────────────

def _forma(ancho: float, alto: float, relleno: float, circ: float, escala: float) -> str:
    a, b = ancho / escala, alto / escala
    cuadrado = max(a, b) <= 1.15 * min(a, b)
    if cuadrado and circ >= 0.85 and relleno < 0.9:
        return "círculo {}".format(round((a + b) / 2))
    if relleno >= 0.85:
        return "cuadro {}×{}".format(round(a), round(b))
    return "otro {}×{}".format(round(a), round(b))


def _simbolo(sub, x0, y0, escala) -> Simbolo | None:
    ys, xs = np.nonzero(sub)
    if not len(xs):
        return None
    u8 = sub.astype(np.uint8)
    cont, _ = cv2.findContours(u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cont, key=cv2.contourArea)
    area = cv2.contourArea(c)
    per = cv2.arcLength(cv2.convexHull(c), True)          # sin la escalera de los píxeles
    xa, xb, ya, yb = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    ancho, alto = float(xb - xa), float(yb - ya)
    relleno = (area + per / 2) / (ancho * alto) if ancho * alto else 0.0
    circ = 4 * math.pi * (area + per / 2) / (per + math.pi) ** 2 if per else 0.0
    return Simbolo(float(x0 + (xa + xb - 1) / 2), float(y0 + (ya + yb - 1) / 2), ancho, alto,
                   _forma(ancho, alto, relleno, circ, escala))


def _zonas_densas(centros, w, tramos, nudo, escala) -> list[list[int]]:
    """Zonas de símbolo dentro de una componente: nudos que forman una malla. Un nudo es denso si
    tiene ≥ NUDOS_DENSOS nudos en un círculo de 2·w, o si sus tramos CORTOS (< max(2·w, 3 pt)) a
    otros nudos juntan ≥ NUDOS_DENSOS (rejilla de líneas finas pegada a una línea gruesa)."""
    if len(centros) < NUDOS_DENSOS:
        return []
    c = np.array(centros)
    r = 2 * w
    dist = np.hypot(c[:, None, 0] - c[None, :, 0], c[:, None, 1] - c[None, :, 1])
    corto = max(2 * w, PASO_MALLA_PT * escala)
    lazos = {i: set() for i in range(len(c))}
    for cam in tramos:
        a, b = cam[0], cam[-1]
        if a in nudo and b in nudo and nudo[a] != nudo[b] and E.largo_px(cam) < corto:
            lazos[nudo[a]].add(nudo[b]); lazos[nudo[b]].add(nudo[a])
    malla, vistos = set(), set()
    for i in range(len(c)):                           # nudos de mallas de ≥ NUDOS_DENSOS
        if i in vistos:
            continue
        grupo, pila = [], [i]
        vistos.add(i)
        while pila:
            j = pila.pop()
            grupo.append(j)
            for k in sorted(lazos[j]):
                if k not in vistos:
                    vistos.add(k)
                    pila.append(k)
        aristas = sum(len(lazos[j]) for j in grupo) // 2
        ciclos = aristas - len(grupo) + 1             # una malla es muy cíclica; una hilera de «T» no
        if len(grupo) >= NUDOS_DENSOS and ciclos >= max(2, len(grupo) / 3):
            malla.update(grupo)
    densos = {i for i in range(len(c)) if int((dist[i] <= r).sum()) >= NUDOS_DENSOS} | malla
    zonas, asignado = [], set()
    for i in sorted(densos):
        if i in asignado:
            continue
        zona, pila = [], [i]
        asignado.add(i)
        while pila:
            j = pila.pop()
            zona.append(j)
            vecinos = set(int(k) for k in np.nonzero(dist[j] <= r)[0]) | lazos[j]
            for k in sorted(vecinos):
                if k not in asignado:
                    asignado.add(k)
                    if k in densos:
                        pila.append(k)
                    else:
                        zona.append(k)
        zonas.append(sorted(zona))
    return zonas


def _componente(sub: np.ndarray, x0: int, y0: int, escala: float, extra=()):
    """(líneas [(puntos, grosor_px)], símbolos, guion) de una componente recortada con 1 px de
    margen. `guion` = (cx, cy, largo, ancho, rumbo) si es compacta (para `_en_fila`)."""
    sub, cajas = H.rellenar(sub, escala)
    cajas += [list(c) for c in extra]
    area = int(sub.sum())
    pix = set(zip(*[a.tolist() for a in np.nonzero(skeletonize(sub))]))
    if not pix:
        return [], [], None
    pix = E.podar(pix, lambda _p, cam, ady: E.ancho_medio(area, cam, ady))
    caminos, ady, nudo, centros = E.tramos(pix)
    w = max(1.0, E.ancho_medio(area, caminos, ady))
    ys, xs = np.nonzero(sub)
    rect = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    if max(rect[1]) + 1 < ALARGADA_K * w or H.es_aro(sub, escala):
        s = _simbolo(sub, x0, y0, escala)
        (cx, cy), (rw, rh), ang = rect
        if rw < rh:
            rw, rh, ang = rh, rw, ang + 90.0
        guion = (cx + x0, cy + y0, rw + 1.0, rh + 1.0, ang % 180.0)
        return [], [s] if s else [], guion if s else None
    for zona in _zonas_densas(centros, w, caminos, nudo, escala):
        yy = [p[0] for p, k in nudo.items() if k in zona] + [centros[k][1] for k in zona]
        xx = [p[1] for p, k in nudo.items() if k in zona] + [centros[k][0] for k in zona]
        cajas.append([math.floor(min(xx)) - 2, math.floor(min(yy)) - 2,
                      math.ceil(max(xx)) + 2, math.ceil(max(yy)) + 2])
    cajas += H.huecos(sub, w)
    simbolos, cortado = [], np.zeros(sub.shape, bool)
    for xa, ya, xb, yb in H.juntar(cajas):
        xa, ya = max(xa, 0), max(ya, 0)
        cortado[ya:yb + 1, xa:xb + 1] = True
        s = _simbolo(sub[ya:yb + 1, xa:xb + 1], x0 + xa, y0 + ya, escala)
        if s:
            simbolos.append(s)
    original = ady
    if cortado.any():
        caminos, ady, nudo, centros = E.tramos({p for p in pix if not cortado[p]})
    eps = min(DP_W * w, DP_MAX_PT * escala)
    lineas = [([(x + x0, y + y0) for x, y in pts], g)
              for pts, g in E.ejes(sub, w, caminos, original, nudo, centros, eps)]
    return lineas, simbolos, None


def _en_fila(compactos) -> list:
    """Los compactos que son GUIONES: ≥ FILA_MIN piezas parecidas (lados ±25 %, rumbo ±15°) una
    tras otra a lo largo de su lado largo (la línea «en caja» de Phoenix: guiones de 20 × 13 px).
    Un compacto suelto sigue siendo símbolo."""
    return [compactos[i] for gr in _filas(compactos) for i in gr]


def _filas(compactos) -> list[list[int]]:
    """Grupos (índices, en orden) de compactos en fila, como `_en_fila`."""
    n = len(compactos)
    if n < FILA_MIN:
        return []
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    g = [c[1] for c in compactos]
    centros = np.array([(c[0], c[1]) for c in g])
    for i in range(n):
        cx, cy, li, wi, ai = g[i]
        if li < 1.3 * wi:                              # sin lado largo claro no hay rumbo
            continue
        d = np.array([math.cos(math.radians(ai)), math.sin(math.radians(ai))])
        rel = centros - centros[i]
        a_lo = rel @ d
        de_lado = np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0])
        for j in np.nonzero((np.abs(a_lo) <= FILA_DIST * li) & (de_lado <= 0.5 * wi))[0]:
            j = int(j)
            lj, wj, aj = g[j][2], g[j][3], g[j][4]
            da = abs(ai - aj) % 180.0
            if j != i and min(da, 180 - da) <= 15 and abs(lj - li) <= 0.25 * li                     and abs(wj - wi) <= 0.25 * wi:
                padre[raiz(j)] = raiz(i)
    grupos = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(i)
    return [sorted(gr) for gr in grupos.values() if len(gr) >= FILA_MIN]


def _sin_lo_de_adentro(lineas, simbolos):
    """Lo que cae entero dentro de la caja de un símbolo (la letra suelta dentro del aro) es del
    símbolo: no da líneas ni otro símbolo."""
    if not simbolos:
        return lineas, simbolos
    cj = np.array([(s.cx - s.ancho / 2, s.cy - s.alto / 2, s.cx + s.ancho / 2, s.cy + s.alto / 2)
                   for s in simbolos])
    area = np.array([s.ancho * s.alto for s in simbolos])
    quedan = []
    for l in lineas:
        p = np.array(l[0])
        x0, y0 = p.min(axis=0)
        x1, y1 = p.max(axis=0)
        if not ((cj[:, 0] <= x0) & (cj[:, 1] <= y0) & (cj[:, 2] >= x1) & (cj[:, 3] >= y1)).any():
            quedan.append(l)
    salen = []
    for i, s in enumerate(simbolos):
        dentro = ((cj[:, 0] <= s.cx) & (cj[:, 2] >= s.cx) & (cj[:, 1] <= s.cy) & (cj[:, 3] >= s.cy)
                  & (area > area[i]))
        if not dentro.any():
            salen.append(s)
    return quedan, salen


# ── rayado ───────────────────────────────────────────────────────────────────────────────────

def _recta(pts) -> bool:
    """Casi recta: ningún punto se aparta de la cuerda más de max(1.5 px, 10 % de su largo)."""
    a, b = np.array(pts[0]), np.array(pts[-1])
    d = b - a
    nd = math.hypot(*d)
    if nd < 1e-9:
        return False
    p = np.array(pts) - a
    desvio = np.abs(p[:, 0] * d[1] - p[:, 1] * d[0]) / nd
    return float(desvio.max()) <= max(1.5, 0.1 * nd)


def _rayados(lineas, escala) -> set[int]:
    """Índices de las líneas rectas que forman un rayado: grupos de ≥ RAYADO_MIN paralelas (±5°)
    vecinas DE COSTADO (se solapan a lo largo y están a ≤ `RAYADO_VECINO_PT`) con paso regular:
    la distancia a la vecina más cercana es la misma (±30 %) en ≥ 70 % de ellas. Solo cuentan las
    vecinas que se solapan: dos rayados lejanos de igual rumbo no se mezclan."""
    rectas = [i for i, (pts, _g, _c) in enumerate(lineas) if _recta(pts)]
    if len(rectas) < RAYADO_MIN:
        return set()
    a = np.array([lineas[i][0][0] for i in rectas], float)
    b = np.array([lineas[i][0][-1] for i in rectas], float)
    d = b - a
    largo = np.hypot(d[:, 0], d[:, 1])
    u = d / largo[:, None]
    ang = np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 180.0
    n = len(rectas)
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    lim = RAYADO_VECINO_PT * escala
    cercana = np.full(n, np.inf)
    for i in range(n):
        da = np.abs(ang - ang[i])
        rel_a, rel_b = a - a[i], b - a[i]
        lado = np.abs((rel_a[:, 0] + rel_b[:, 0]) / 2 * u[i, 1] - (rel_a[:, 1] + rel_b[:, 1]) / 2 * u[i, 0])
        ta, tb = rel_a @ u[i], rel_b @ u[i]
        solape = np.minimum(np.maximum(ta, tb), largo[i]) - np.maximum(np.minimum(ta, tb), 0.0)
        ok = ((np.minimum(da, 180 - da) <= RAYADO_ANG) & (lado > 1.0) & (lado <= lim)
              & (solape >= 0.3 * np.minimum(largo, largo[i])))
        ok[i] = False
        for j in np.nonzero(ok)[0]:
            padre[raiz(int(j))] = raiz(i)
        if ok.any():
            cercana[i] = float(lado[ok].min())
    grupos = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(i)
    salida = set()
    for g in grupos.values():
        pasos = cercana[g][np.isfinite(cercana[g])]
        if len(g) < RAYADO_MIN or len(pasos) < RAYADO_MIN:
            continue
        paso = float(np.median(pasos))
        if paso >= 2.0 and float((np.abs(pasos - paso) <= 0.3 * paso).mean()) >= 0.7:
            salida.update(rectas[i] for i in g)
    return salida


def _sub(lab: np.ndarray, st, k: int) -> np.ndarray:
    x, y, w, h = (int(v) for v in st[:4])
    sub = np.zeros((h + 2, w + 2), bool)
    sub[1:-1, 1:-1] = lab[y:y + h, x:x + w] == k
    return sub


def _duena(lab: np.ndarray, caja) -> int:
    """La componente con más píxeles dentro de la caja de una rejilla (0 = ninguna)."""
    a, b, c, d = (max(int(v), 0) for v in caja)
    zona = lab[b:d + 1, a:c + 1]
    if zona.size == 0:
        return 0
    cuenta = np.bincount(zona.ravel())
    cuenta[0] = 0
    return int(cuenta.argmax())


# ── entrada ──────────────────────────────────────────────────────────────────────────────────

def trazos(mask: np.ndarray, escala: float, familia: np.ndarray | None = None) -> Piezas:
    """Líneas, símbolos y relleno de la máscara de un color (coordenadas en px de `mask`;
    grosores en pt = px / escala). `familia` (`imagen_paleta.familia`) = su antialias: con ella
    se cierran los contornos finos (`imagen_huecos.cerrar_con_familia`) antes de todo lo demás."""
    rejillas, simbolos = [], []
    mask = np.asarray(mask, bool).copy()
    # Bandas «en caja» PEGADAS (`imagen_bandas`), sobre la máscara tal cual: con el cierre por la familia se funden en
    # una mancha que salía como símbolo. Una línea por banda; su tinta sale de la máscara y de la familia.
    lineas, quitar = B.bandas(mask, escala)
    lineas = [(pts, g, -1) for pts, g in lineas]
    if quitar is not None:
        mask &= ~quitar
        if familia is not None:
            familia = np.asarray(familia, bool) & ~cv2.dilate(quitar.view(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if familia is not None:
        familia = np.asarray(familia, bool).copy()
        # Rejillas fuera de las líneas: lo grueso se mira con las bandas ya unidas (su contorno no
        # pega la rejilla a la banda); la máscara sigue SIN puentes hasta cerrar sus huecos.
        for x, y, sub, (xa, ya, xb, yb) in P.rejillas(P.puentes(mask, familia, escala), familia,
                                                      escala, RUIDO_PX):
            mask[y:y + sub.shape[0], x:x + sub.shape[1]] &= ~sub
            familia[y:y + sub.shape[0], x:x + sub.shape[1]] &= ~sub
            simbolos.append(_simbolo(np.ones((yb - ya + 1, xb - xa + 1), bool), xa, ya, escala))
        mask, rejillas = H.cerrar_con_familia(mask, familia, escala, RUIDO_PX)
        mask = P.puentes(mask, familia, escala)                         # bandas con el contorno cortado
    m = np.ascontiguousarray(mask, dtype=np.uint8)
    if not m.any():
        return Piezas([l[0] for l in lineas], [l[1] / escala for l in lineas], simbolos, False)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    compactos = []
    duenas = [_duena(lab, caja) for caja in rejillas]       # cada rejilla, UNA componente
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[k])
        if area < RUIDO_PX:
            continue
        sub = np.zeros((h + 2, w + 2), bool)
        sub[1:-1, 1:-1] = lab[y:y + h, x:x + w] == k
        extra = [[a - x + 1, b - y + 1, c - x + 1, d - y + 1]
                 for (a, b, c, d), kk in zip(rejillas, duenas) if kk == k]
        ls, ss, guion = _componente(sub, x - 1, y - 1, escala, extra)
        lineas += [(pts, g, k) for pts, g in ls]
        simbolos += ss
        if guion:
            compactos.append((ss[0], guion, k))
    for s, (cx, cy, largo, corto, ang), k in _en_fila(compactos):
        d = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))]) * largo / 2
        lineas.append(([(cx - d[0], cy - d[1]), (cx + d[0], cy + d[1])], corto, k))
        simbolos = [t for t in simbolos if t is not s]
    lineas, simbolos = _sin_lo_de_adentro(lineas, simbolos)
    rayado = _rayados(lineas, escala)
    if rayado:
        # El rayado y lo FINO que va con él (su contorno, del mismo grosor) no son líneas; una
        # tubería gruesa que cruza la zona rayada sí. Relleno = el rayado es la mayoría de la tinta.
        fino = 1.5 * float(np.median([lineas[i][1] for i in rayado]))
        comps = {lineas[i][2] for i in rayado}
        fuera = {i for i, l in enumerate(lineas) if i in rayado or (l[2] in comps and l[1] <= fino)}
        tinta = [E.largo_px(l[0]) * l[1] for l in lineas]
        relleno = sum(tinta[i] for i in fuera) > 0.5 * sum(tinta)
        lineas = [] if relleno else [l for i, l in enumerate(lineas) if i not in fuera]
    else:
        relleno = False
    return Piezas([l[0] for l in lineas], [l[1] / escala for l in lineas], simbolos, relleno)
