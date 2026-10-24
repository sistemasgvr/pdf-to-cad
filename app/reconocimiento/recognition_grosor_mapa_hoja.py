"""recognition_grosor_mapa_hoja.py — el grosor de un mapa sin capas en `recognize_page` (PURO; lo
decide `recognition_grosor_mapa`).

  · `aplicar_variantes`: las dos variantes del reconocimiento (rutas unidas y tramos sin unir); los
    tramos sin unir HEREDAN el grosor de su ruta (`heredar`): un tramo sin rótulo sabe su diámetro
    por sus vecinos solo dentro de la ruta, así «Unir tramos» no cambia lo que se lee.
  · `partir_al_final`: las rutas con dos diámetros se parten DESPUÉS de los pasos que mueven
    vértices (imán a bóvedas, ángulos a 0.25°): esos pasos ven la ruta entera y la geometría queda
    idéntica a la de antes (partir antes cambiaba la solución de los ángulos hasta 1.8 pt).
  · `avisos`: los de la vista previa.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Callable, List, Optional, Sequence

from reconocimiento import recognition_grosor_mapa as G
from reconocimiento import recognition_grosor_partir as P
from reconocimiento import recognition_indice as indice_mod

HEREDAR_PT = 0.25            # el tramo sin unir cae sobre la ruta unida (mismos vértices)


def aplicar_variantes(unidas: list, sueltas: list, rots: Sequence, del_mapa: Callable[[object], bool],
                      es_acometida: Callable[[object], bool], zoom: float, diam_acometida_in: Optional[float],
                      importan_unidas: bool = True) -> dict:
    """`recognition_grosor_mapa.aplicar` en las dos variantes (solo las líneas `del_mapa`) y `heredar`.
    Devuelve la cuenta de la variante que se importa, con "partir" = lo que hay que partir de las DOS
    (para `partir_al_final`)."""
    cuentas = [G.aplicar([p for p in v if del_mapa(p)], rots, es_acometida, zoom, diam_acometida_in)
               for v in (unidas, sueltas)]
    heredar([p for p in sueltas if del_mapa(p)], [p for p in unidas if del_mapa(p)], es_acometida, zoom,
            cuentas[0]["partir"])
    pendientes = {**cuentas[0]["partir"], **cuentas[1]["partir"]}
    if importan_unidas:
        return dict(cuentas[0], partir=pendientes)
    cuenta = dict(cuentas[1], con=0, revisar=0, sin=0, acometidas=Counter(), partir=pendientes)
    llave = {"leido": "con", "dudoso": "revisar", "sin_dato": "sin"}
    for p in sueltas:
        if not del_mapa(p):
            continue
        gs = pendientes[id(p)][2] if id(p) in pendientes else [getattr(p, "grosor", None) or {}]
        for g in gs:
            if g.get("estado"):
                if es_acometida(p):
                    cuenta["acometidas"][g["estado"]] += 1
                else:
                    cuenta[llave[g["estado"]]] += 1
    return cuenta


def partir_al_final(variantes: Sequence[list], cuenta: Optional[dict]) -> None:
    """Parte en cada lista las rutas pendientes (`aplicar_variantes`)."""
    for v in variantes:
        G.partir(v, (cuenta or {}).get("partir") or {})


def heredar(lineas: Sequence, origen: Sequence, es_acometida: Callable[[object], bool], zoom: float,
            pendientes: Optional[dict] = None) -> int:
    """Cada tramo sin unir de la red cuyo punto medio cae sobre UNA ruta de `origen` (≤ `HEREDAR_PT`,
    mismo rumbo) copia el grosor de esa ruta en ese punto (de su pieza, si se parte) y su `diam_in`;
    los demás quedan como los dejó `aplicar`. Devuelve cuántos heredaron."""
    pendientes = pendientes or {}
    tol = HEREDAR_PT * zoom
    fuente = [q for q in origen if len(q.pts_pdf) >= 2 and not es_acometida(q)
              and (getattr(q, "grosor", None) or id(q) in pendientes)]
    if not fuente:
        return 0
    indice = indice_mod.IndiceTramos([list(zip(q.pts_pdf, q.pts_pdf[1:])) for q in fuente], tol)
    n = 0
    for pl in lineas:
        if len(pl.pts_pdf) < 2 or es_acometida(pl) or id(pl) in pendientes:
            continue
        m, d = _medio(pl.pts_pdf)
        if m is None:
            continue
        hits = {}
        for k, j in indice.cerca(m):
            a, b = fuente[k].pts_pdf[j], fuente[k].pts_pdf[j + 1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L > 1e-9 and P._dist_seg(m, a, b) <= tol and abs((b[0] - a[0]) * d[0] + (b[1] - a[1]) * d[1]) / L >= 0.99:
                hits.setdefault(id(fuente[k]), (fuente[k], j))
        if len(hits) != 1:
            continue
        q, j = next(iter(hits.values()))
        g = G.grosor_en(q, j, pendientes)
        if not g:
            continue
        pl.grosor = {k: v for k, v in g.items() if k != "partida"}
        pl.diam_in = g.get("diam_in")
        n += 1
    return n


def _medio(pts):
    """(punto a la mitad del largo, dirección del tramo ahí) o (None, None)."""
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    if total <= 1e-9:
        return None, None
    s = total / 2.0
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > 1e-9 and s <= L:
            t = s / L
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        s -= L
    return None, None


def avisos(cuenta: Optional[dict]) -> List[str]:
    """Avisos de la vista previa (las acometidas dudosas o sin dato se cuentan con la red: el
    editor les pone el mismo aviso)."""
    from traduccion.i18n_core import t as _tr
    if not cuenta:
        return []
    tap = cuenta.get("acometidas") or {}
    con, revisar = cuenta["con"], cuenta["revisar"] + tap.get("dudoso", 0)
    sin = cuenta["sin"] + tap.get("sin_dato", 0)
    out = []
    if con or revisar:
        out.append(_tr("Diámetros del plano (rótulos junto a la tubería): {n} tubería(s) los toman; {m} "
                       "dudosa(s) quedan con el diámetro por defecto y un aviso en el editor.").format(n=con, m=revisar))
    if sin:
        out.append(_tr("Tuberías sin diámetro en el plano: {n} — ningún rótulo de diámetro va junto a ellas; "
                       "quedan con el diámetro por defecto y un aviso en el editor.").format(n=sin))
    if cuenta["partidas"]:
        out.append(_tr("Tuberías partidas donde el plano cambia de diámetro: {n} — sus rótulos "
                       "dicen un diámetro hasta un nodo (pozo, unión o esquina) y otro "
                       "después.").format(n=cuenta["partidas"]))
    return out
