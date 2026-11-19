"""Un color de la red en IMAGEN con DOS grosores (PURO, sin Qt): las bandas de la red y líneas finas.

Phoenix SD h.4/h.7/h.8: el #004DA8 trae las bandas de la red (~3.3 pt) y líneas FINAS a guiones (≤ 1 pt: el canal,
sobre una banda gris). En una sola capa, el patrón de guiones de lo fino mandaba la capa al núcleo, que inventaba
uniones entre bandas (cobertura 0.90–0.95, 4–12 tramos sin tinta). `partir_por_grosor` separa lo fino en su propia
capa de línea (`imagen_ejes.nombre("line", rgb, FINO)`); un color de un solo grosor queda como estaba.
"""

from __future__ import annotations

import math

FINO = "fino"                # 4.º elemento de la capa de LÍNEA fina de un color con dos grosores (`partir_por_grosor`)
FINO_FRAC = 0.35             # fino = grosor ≤ esto × el grosor típico (mediana por largo) del color …
FINO_RATIO = 0.25            # … el grosor típico de lo fino ≤ esto × el de lo grueso (dos grupos bien separados) …
FINO_MIN_PT = 100.0          # … lo fino es tinta real que forma LÍNEAS: al menos este largo (pt) en trazos largos
FINO_LINEA_FRAC = 0.25       # (≥ `FINO_LARGO_PT`) o en guiones seguidos, y esta fracción del largo de lo fino (en
                             # Phoenix SD h.1/h.3 lo fino son trocitos sueltos —contornos de símbolos y uniones—:
                             # 0.10 en líneas; en h.4/h.7/h.8, el canal a guiones: 0.37–0.58) …
FINO_MIN_TRAZOS = 15         # … y al menos estos trazos finos …
FINO_MIN_FRAC = 0.03         # … y esta fracción del largo del color
FINO_LARGO_PT = 25.0         # trazo fino largo = ya es una línea
GUION_HUECO_PT = (0.5, 12.0)  # dos trazos finos seguidos: punta con punta a esta distancia …
GUION_DIR_DEG = 20.0         # … mirándose (± esto) = guiones de una línea
CAJA_FINO_PT = 0.6           # lado de rejilla: fino si ≤ esto (pt) aunque el color sea casi todo fino (SD North h.4: 0.48)
CAJA_LADO_PT = (4.0, 14.0)   # lados de una rejilla: dos trazos finos paralelos a esta distancia …
CAJA_SOLAPE = 0.75           # … y uno frente al otro (el más corto, casi entero: un lado puede venir en trozos)


def _largo(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _unit(a, b):
    L = math.dist(a, b)
    return None if L < 1e-9 else ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def largo_en_lineas(lineas) -> float:
    """Largo de los trazos de `[(pts, grosor)]` que forman LÍNEAS: largos (≥ `FINO_LARGO_PT`) o guiones con otro
    trazo enfrente, en su recta (punta con punta a `GUION_HUECO_PT`, ± `GUION_DIR_DEG`). Rejilla de celdas del
    hueco máximo: cada punta mira solo las de su vecindad."""
    en_linea = _guiones(lineas)
    return sum(_largo(p) for k, (p, _w) in enumerate(lineas) if k in en_linea or _largo(p) >= FINO_LARGO_PT)


def _guiones(lineas) -> set:
    """Índices de los trazos con otro trazo enfrente en su recta (guiones de una línea)."""
    g0, g1 = GUION_HUECO_PT
    cos = math.cos(math.radians(GUION_DIR_DEG))
    puntas = []
    for k, (p, _w) in enumerate(lineas):
        if len(p) >= 2:
            puntas.append((k, p[0], _unit(p[1], p[0])))
            puntas.append((k, p[-1], _unit(p[-2], p[-1])))
    celdas: dict = {}
    for i, (_k, q, _d) in enumerate(puntas):
        celdas.setdefault((int(q[0] // g1), int(q[1] // g1)), []).append(i)
    en_linea = set()
    for i, (k, q, d) in enumerate(puntas):
        if d is None:
            continue
        cx, cy = int(q[0] // g1), int(q[1] // g1)
        for j in (j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in celdas.get((cx + dx, cy + dy), ())):
            k2, r, e = puntas[j]
            if k2 == k or e is None or not g0 <= math.dist(q, r) <= g1:
                continue
            u = _unit(q, r)
            if u and d[0] * u[0] + d[1] * u[1] >= cos and e[0] * u[0] + e[1] * u[1] <= -cos:
                en_linea.update((k, k2))
                break
    return en_linea


def _mediana_por_largo(lineas) -> float:
    pares = sorted((w, _largo(pts)) for pts, w in lineas)
    total, acum = sum(l for _w, l in pares), 0.0
    for w, l in pares:
        acum += l
        if acum >= total / 2:
            return w
    return pares[-1][0] if pares else 0.0


def partir_por_grosor(lineas) -> tuple[list, list]:
    """(gruesas, finas) de las líneas `[(pts, grosor)]` de UN color. Un color que trae dos grosores claramente
    distintos (Phoenix SD: bandas de la red ~3.3 pt y líneas finas a guiones ≤ 1 pt, el canal) se parte en dos
    capas: en una sola, el patrón de guiones de lo fino mandaba la capa al núcleo, que inventaba uniones entre
    bandas. Fino = grosor ≤ `FINO_FRAC` × el típico del color; se parte solo si lo fino es tinta real (≥
    `FINO_MIN_TRAZOS`, `FINO_MIN_FRAC` del largo) que forma LÍNEAS (`largo_en_lineas` ≥ `FINO_MIN_PT` y ≥
    `FINO_LINEA_FRAC` de lo fino: unos trocitos sueltos —contornos— no hacen otra capa), su grosor típico es ≤ `FINO_RATIO` × el de lo
    grueso y entre los dos grupos (hasta ½ del típico) hay menos tinta que en lo fino. Si no, (lineas, [])."""
    lineas = list(lineas)
    if not lineas:
        return lineas, []
    tope = FINO_FRAC * _mediana_por_largo(lineas)
    finas = [x for x in lineas if x[1] <= tope]
    gruesas = [x for x in lineas if x[1] > tope]
    if not finas or not gruesas:
        return lineas, []
    l_fin = sum(_largo(p) for p, _w in finas)
    l_tot = l_fin + sum(_largo(p) for p, _w in gruesas)
    m_gru = _mediana_por_largo(gruesas)
    valle = sum(_largo(p) for p, w in gruesas if w <= 0.5 * m_gru)
    if (len(finas) < FINO_MIN_TRAZOS or l_fin < FINO_MIN_FRAC * l_tot
            or _mediana_por_largo(finas) > FINO_RATIO * m_gru or valle >= l_fin):
        return lineas, []
    en_lineas = largo_en_lineas(finas)
    if en_lineas < FINO_MIN_PT or en_lineas < FINO_LINEA_FRAC * l_fin:
        return lineas, []
    return gruesas, finas


def sin_trocitos_finos(lineas) -> list:
    """Las líneas `[(pts, grosor)]` sin los LADOS de una rejilla que no se reconoce: dos trazos finos (grosor ≤
    `FINO_FRAC` × el típico del color o ≤ `CAJA_FINO_PT`), cortos (< `FINO_LARGO_PT`), paralelos, uno frente al otro (el más corto, en
    ≥ `CAJA_SOLAPE` de su largo: un lado puede venir en trozos) y a `CAJA_LADO_PT` uno del otro: los dos lados de la caja. Pedido del usuario
    (2026-11-19, Phoenix SD «si no se reconoce la rejilla, dejarlo sin reconocer»): el contorno de una rejilla de
    sumidero llega a la máscara del color solo en sus dos lados largos (≈0.25 pt contra 3.3 pt de la red; la malla de
    adentro es más clara) y salían como dos tuberías cortas a los lados. Las paredes finas de una tubería chica
    (0.3–3.5 pt entre sí, SD South h.3) y cualquier otro trazo fino se quedan. Mismo orden."""
    lineas = list(lineas)
    if not lineas:
        return lineas
    tope = max(FINO_FRAC * _mediana_por_largo(lineas), CAJA_FINO_PT)
    finas = [k for k, (p, w) in enumerate(lineas) if w <= tope and _largo(p) < FINO_LARGO_PT]
    if len(finas) < 2:
        return lineas
    fuera = {finas[k] for k in _lados_de_caja([lineas[k] for k in finas])}
    return [l for k, l in enumerate(lineas) if k not in fuera]


def _lados_de_caja(lineas) -> set:
    """Índices de los pares de trazos que son los dos lados de una caja (ver `sin_trocitos_finos`)."""
    seg = [(p[0], p[-1], _unit(p[0], p[-1]), math.dist(p[0], p[-1])) for p, _w in lineas]
    c0, c1 = CAJA_LADO_PT
    celdas: dict = {}
    for i, (a, b, _u, _l) in enumerate(seg):
        celdas.setdefault((int((a[0] + b[0]) / 2 // c1), int((a[1] + b[1]) / 2 // c1)), []).append(i)
    cos = math.cos(math.radians(GUION_DIR_DEG))    # (± 20°: la punta de un lado en trozos se tuerce)
    out = set()
    for i, (a, b, u, la) in enumerate(seg):
        if u is None or la <= 0:
            continue
        cx, cy = int((a[0] + b[0]) / 2 // c1), int((a[1] + b[1]) / 2 // c1)
        for j in (j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in celdas.get((cx + dx, cy + dy), ())):
            c, d, v, lc = seg[j]
            if j <= i or v is None or lc <= 0 or abs(u[0] * v[0] + u[1] * v[1]) < cos:
                continue
            mc = ((c[0] + d[0]) / 2 - a[0], (c[1] + d[1]) / 2 - a[1])
            lado = abs(mc[0] * u[1] - mc[1] * u[0])
            t0 = (c[0] - a[0]) * u[0] + (c[1] - a[1]) * u[1]
            t1 = (d[0] - a[0]) * u[0] + (d[1] - a[1]) * u[1]
            solape = min(max(t0, t1), la) - max(min(t0, t1), 0.0)
            if c0 <= lado <= c1 and solape >= CAJA_SOLAPE * min(la, lc):
                out.update((i, j))
    return out
