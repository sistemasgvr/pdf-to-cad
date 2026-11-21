"""`resolve_nodes` con y sin índices da EXACTAMENTE lo mismo (2026-11-21).

Reporte del usuario (monitor): reconocer el drenaje en imagen de 32 mapas de Phoenix tardó 20 min, casi todo en
`resolve_nodes`: cada bóveda revisaba TODAS las puntas libres contra TODOS los puntos de corte del clip, y la bóveda
más cercana de cada punta recorría todas las bóvedas. Ahora: índice de cortes (`en_corte`), de recuadros de bóveda
(`IndiceCajas`) y de las puntas libres de la Fase B. Aquí se compara contra el recorrido completo
(`SIN_INDICES = True`) en redes sintéticas densas con cortes, bóvedas con contorno y letras, con todas las opciones.
"""
import copy
import dataclasses
import math
import random

import pytest

from reconocimiento import recognition_geom as G
from reconocimiento import recognition_geom_indice as GI


def _canon(x):
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return (type(x).__name__, tuple((f.name, _canon(getattr(x, f.name))) for f in dataclasses.fields(x)))
    if isinstance(x, (list, tuple)):
        return tuple(_canon(v) for v in x)
    return x


def _red(semilla: int, n_lineas: int = 120, n_bovedas: int = 70):
    rng = random.Random(semilla)
    runs, extremos = [], []
    for _ in range(n_lineas):
        x, y = rng.uniform(0, 500), rng.uniform(0, 500)
        ang = rng.choice([0.0, math.pi / 2, rng.uniform(0, math.pi)])
        ux, uy = math.cos(ang), math.sin(ang)
        for _tramo in range(rng.randint(1, 4)):        # tramos separados por huecos (esquinas, T, cortes…)
            dashes = []
            for _g in range(rng.randint(1, 5)):
                a = (x, y)
                b = (x + 10 * ux, y + 10 * uy)
                dashes.append(G.Dash(a, b))
                x, y = b[0] + 5 * ux, b[1] + 5 * uy
            r = G.Run(dashes[0].a, dashes[-1].b, ux, uy, dashes)
            if rng.random() < 0.15:                    # algunas curvas
                m = ((r.a[0] + r.b[0]) / 2 + rng.uniform(-2, 2), (r.a[1] + r.b[1]) / 2 + rng.uniform(-2, 2))
                r.mid = [m]
            if rng.random() < 0.1:
                r.continuous = True
            runs.append(r)
            extremos += [r.a, r.b]
            x, y = x + rng.uniform(-3, 9) * ux, y + rng.uniform(-3, 9) * uy
            if rng.random() < 0.4:                     # gira
                ang += rng.choice([math.pi / 2, -math.pi / 2, rng.uniform(-1.2, 1.2)])
                ux, uy = math.cos(ang), math.sin(ang)
    vaults = []
    for _ in range(n_bovedas):
        cx, cy = rng.choice(extremos) if rng.random() < 0.7 else (rng.uniform(0, 500), rng.uniform(0, 500))
        cx, cy = cx + rng.uniform(-6, 6), cy + rng.uniform(-6, 6)
        w, h = rng.uniform(4, 22), rng.uniform(4, 22)
        v = G.Vault(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if rng.random() < 0.6:
            g = rng.uniform(-0.3, 0.3)
            c, s = math.cos(g), math.sin(g)
            v.outline = [(cx + c * dx - s * dy, cy + s * dx + c * dy)
                         for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
        v.round_entry = rng.random() < 0.2
        v.width = min(w, h)
        vaults.append(v)
    vaults.sort(key=lambda v: (v.y0, v.x0))
    cortes = [rng.choice(extremos) for _ in range(60)]
    cortes = [(p[0] + rng.uniform(-0.6, 0.6), p[1] + rng.uniform(-0.6, 0.6)) for p in cortes]
    cortes += [(rng.uniform(0, 500), rng.uniform(0, 500)) for _ in range(30)]
    letras = [G.Glyph(rng.uniform(0, 500), rng.uniform(0, 500), rng.uniform(2, 5)) for _ in range(80)]
    contactos = [rng.choice(extremos) for _ in range(10)]
    pat = G.Pattern(dash_long=10.0, dash_short=None, gap_max=5.0, letter=3.0, join_gap=8.0,
                    glyph_bridge=20.0, vault_bridge=30.0, corner_tol=8.0)
    return runs, pat, vaults, cortes, letras, contactos


OPCIONES = [
    dict(nearest=True),                                            # perfil DRENAJE
    dict(nearest=False),
    dict(nearest=True, touching=True, precise_junctions=True, manhole_bend=True),
    dict(touching=True, continuation_before_vault=True, corner_before_vault=True),
]


@pytest.mark.parametrize("semilla", range(6))
@pytest.mark.parametrize("opciones", range(len(OPCIONES)))
def test_resolve_nodes_con_y_sin_indices_da_lo_mismo(semilla, opciones, monkeypatch):
    runs, pat, vaults, cortes, letras, contactos = _red(semilla)
    kw = dict(OPCIONES[opciones])

    def correr(sin):
        monkeypatch.setattr(G, "SIN_INDICES", sin)
        rs = copy.deepcopy(runs)
        nodes, orphans = G.resolve_nodes(rs, pat, copy.deepcopy(vaults), list(cortes), glyphs=list(letras),
                                         contact_pts=list(contactos), **kw)
        return _canon((nodes, orphans, rs))

    viejo = correr(True)
    assert correr(False) == viejo


@pytest.mark.parametrize("semilla", range(4))
def test_cobertura_con_y_sin_indices_da_lo_mismo(semilla, monkeypatch):
    """`coverage` y `_polylines_from_uncovered`: cada muestra contra los segmentos cercanos = contra todos."""
    rng = random.Random(semilla)
    polys = []
    for _ in range(60):
        x, y = rng.uniform(0, 400), rng.uniform(0, 400)
        pts = [(x, y)]
        for _k in range(rng.randint(1, 5)):
            x, y = x + rng.uniform(-40, 40), y + rng.uniform(-40, 40)
            pts.append((x, y))
        polys.append(G.Polyline(pts, ["end"] + ["bend"] * (len(pts) - 2) + ["end"]))
    dashes = []
    for pl in polys:                                   # guiones encima de las líneas, corridos un poco
        for a, b in zip(pl.pts, pl.pts[1:]):
            for t in (0.1, 0.5, 0.8):
                off = rng.choice([0.0, 0.3, 1.0, 3.0])
                p = (a[0] + t * (b[0] - a[0]) + off, a[1] + t * (b[1] - a[1]))
                dashes.append(G.Dash(p, (p[0] + rng.uniform(-6, 6), p[1] + rng.uniform(-6, 6))))
    dashes += [G.Dash((rng.uniform(0, 400), rng.uniform(0, 400)), (rng.uniform(0, 400), rng.uniform(0, 400)))
               for _ in range(40)]
    pat = G.Pattern(dash_long=10.0, dash_short=None, gap_max=5.0, letter=3.0, join_gap=8.0,
                    glyph_bridge=20.0, vault_bridge=30.0, corner_tol=8.0)

    def correr(sin):
        monkeypatch.setattr(G, "SIN_INDICES", sin)
        cov, missing = G.coverage(dashes, polys)
        extra = G._polylines_from_uncovered(missing, polys[: len(polys) // 2], pat)
        return _canon((cov, missing, extra))

    viejo = correr(True)
    assert correr(False) == viejo


def test_indice_de_cajas_da_las_que_contienen_el_punto_en_orden():
    rng = random.Random(3)
    cajas = []
    for _ in range(500):
        x, y = rng.uniform(-200, 200), rng.uniform(-200, 200)
        cajas.append(None if rng.random() < 0.1 else (x, y, x + rng.uniform(0, 60), y + rng.uniform(0, 60)))
    idx = GI.IndiceCajas(cajas, 25.0)
    for _ in range(400):
        p = (rng.uniform(-220, 260), rng.uniform(-220, 260))
        if rng.random() < 0.2:                         # justo en un borde
            b = rng.choice([c for c in cajas if c])
            p = (b[0], rng.uniform(b[1], b[3]))
        todas = [i for i, b in enumerate(cajas) if b and b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]]
        c = idx.contienen(p)
        assert c == sorted(c)
        assert set(todas) <= set(c)


def test_puntos_en_caja_incluye_los_del_borde():
    rng = random.Random(4)
    pts = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(300)]
    idx = GI.IndicePuntos(pts, 7.0)
    for _ in range(200):
        x0, y0 = rng.choice(pts)
        caja = (x0, y0, x0 + rng.uniform(0, 30), y0 + rng.uniform(0, 30))
        dentro = [i for i, q in enumerate(pts) if caja[0] <= q[0] <= caja[2] and caja[1] <= q[1] <= caja[3]]
        c = idx.en_caja(caja)
        assert c == sorted(c) and set(dentro) <= set(c)
