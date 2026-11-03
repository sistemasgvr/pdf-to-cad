"""Los rótulos con diámetro JUNTO a una tubería de un mapa SIN capas cuyo diámetro no quedó seguro (PURO).

Pedido del usuario 2026-11-02: la IA del diámetro (`ia/diametro_ia`), que ya revisaba las líneas dudosas o sin dato de
los PDF CON capas (`recognition_grosor_cerca`), también en los PDF vectoriales SIN capas (mapas SIG de Phoenix). Mismo
formato de `grosor["cerca"]`, para que el editor, la ficha y el recorte sirvan igual; solo agrega esa clave (ningún
estado, diámetro ni vértice cambia: la lectura segura sigue siendo la de `recognition_grosor_mapa`).

En un mapa no hay guías: el rótulo va PARALELO y pegado a su tubería. Cada rótulo lleva `mapa=True` y su «guía» dice
cómo queda respecto de ESTA línea (mismas medidas que `recognition_grosor_mapa.asignar`):
  «junto» = paralelo, pegado (≤ `DIST_MAX` letras) y esta es la línea paralela más cercana;
  «entre» = otra paralela está casi igual de cerca AL OTRO LADO del texto (dos tuberías pegadas);
  «otra»  = otra tubería del mapa le queda claramente más cerca (o igual de cerca del mismo lado);
  «lejos» = no corre paralelo a esta línea, o está a más de `DIST_MAX` letras.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence

from reconocimiento import recognition_grosor_mapa as G
from reconocimiento import recognition_indice as indice_mod
from reconocimiento.recognition_grosor_cerca import CERCA_PT, MAX_CERCA

CERCA_LETRAS = 25.0          # rótulos hasta esto × su letra (y nunca más de CERCA_PT): un mapa rotula chico


def caja(r: G.RotuloMapa) -> List[float]:
    """Caja (x0, y0, x1, y1) del texto, de su centro, rumbo, largo y letra."""
    d, up = r.dir, (r.dir[1], -r.dir[0])
    hu, hv = r.largo / 2.0, r.tam / 2.0
    esq = [(r.centro[0] + su * hu * d[0] + sv * hv * up[0], r.centro[1] + su * hu * d[1] + sv * hv * up[1])
           for su in (-1, 1) for sv in (-1, 1)]
    return [min(p[0] for p in esq), min(p[1] for p in esq), max(p[0] for p in esq), max(p[1] for p in esq)]


def _guia(k: int, hits: dict, r: G.RotuloMapa, zoom: float):
    """(guia, otra) del rótulo `r` respecto de la línea `k`; `hits` = {línea: `G._cerca`} de las que tiene a tiro."""
    pegado = {j: h for j, h in hits.items() if h[2] >= G.PARALELO_MIN and h[3] and h[1] <= G.DIST_MAX * r.tam}
    mio = pegado.get(k)
    d1 = mio[1] if mio else hits[k][0]
    margen = lambda a, b: max((G.AMBIGUO - 1.0) * min(a, b), G.AMBIGUO_MIN * r.tam)   # noqa: E731
    entre = False
    for j, h in pegado.items():
        if j == k:
            continue
        if mio is None:
            if h[1] < d1:                                 # pegado a otra tubería y no a esta
                return "otra", {"utilidad": None, "capa": None, "dist_pt": round(h[1] / zoom, 2), "mapa": True}
            continue
        cerca_igual = abs(h[1] - d1) < margen(h[1], d1)
        al_otro_lado = h[4] != mio[4] or h[4] == 0
        if h[1] < d1 and (not cerca_igual or not al_otro_lado):
            return "otra", {"utilidad": None, "capa": None, "dist_pt": round(h[1] / zoom, 2), "mapa": True}
        if cerca_igual and al_otro_lado:
            entre = True
    if mio is None:
        return "lejos", None
    return ("entre" if entre else "junto"), None


def poner_cerca(lineas: Sequence, rots: Sequence[G.RotuloMapa], es_acometida: Callable[[object], bool],
                zoom: float, diam_acometida_in: Optional[float] = None) -> int:
    """`grosor["cerca"]` en cada línea «dudoso» o «sin_dato» de `lineas` (px de la vista; `rots` con `a_px`).
    Devuelve en cuántas líneas se puso (vacía cuenta: la IA puede proponer por normativa)."""
    lineas = [pl for pl in lineas if len(pl.pts_pdf) >= 2]
    objetivo = [k for k, pl in enumerate(lineas) if (getattr(pl, "grosor", None) or {}).get("estado")
                in ("dudoso", "sin_dato")]
    if not objetivo:
        return 0
    pts = [pl.pts_pdf for pl in lineas]
    tap = [bool(es_acometida(pl)) for pl in lineas]
    lim_de = [min(CERCA_PT * zoom, CERCA_LETRAS * r.tam) for r in rots]
    indice = indice_mod.IndiceTramos([list(zip(p, p[1:])) for p in pts], max(lim_de, default=0.0))
    tope_plano = max(G.ACOMETIDA_PLANA_IN, diam_acometida_in or 0.0)
    # por línea: [(distancia, rótulo, {línea: medida})]; las medidas, una vez por rótulo
    de_linea = {k: [] for k in objetivo}
    for r, lim in zip(rots, lim_de):
        hits = {}
        for k in sorted({k for k, _j in indice.cerca(r.centro)}):
            if (not tap[k] and r.acometida) or (tap[k] and r.pulg > tope_plano and not r.acometida):
                continue
            got = G._cerca(r, pts[k])
            if got is not None and got[0] <= lim:
                hits[k] = got
        for k in hits:
            if k in de_linea:
                de_linea[k].append((hits[k][0], r, hits))
    for k in objetivo:
        cand = sorted(de_linea[k], key=lambda c: c[0])[:MAX_CERCA]
        out = []
        for n, (d, r, hits) in enumerate(cand):
            guia, otra = _guia(k, hits, r, zoom)
            out.append({
                "id": f"R{n + 1}", "texto": r.texto.strip(), "diam_in": float(r.pulg), "material": r.material or "",
                "util": "", "es_de": True, "dist_pt": round(d / zoom, 2), "guia": guia, "otra": otra,
                "caja": caja(r), "estacion": False, "union": False, "varios": 1, "puntas": [], "punta_pt": None,
                "mapa": True, "acometida": bool(r.acometida),
                "paralelo": bool(hits[k][2] >= G.PARALELO_MIN),
            })
        lineas[k].grosor = dict(lineas[k].grosor, cerca=out)
    return len(objetivo)


def poner_en_variantes(variantes: Sequence[list], rots, del_mapa, es_acometida, zoom, diam_acometida_in=None) -> None:
    """`poner_cerca` en cada variante del reconocimiento (rutas unidas y tramos sin unir), solo líneas `del_mapa`."""
    for v in variantes:
        poner_cerca([p for p in v if del_mapa(p)], rots, es_acometida, zoom, diam_acometida_in)

