"""recognition_grosor_cruces.py — los CRUCES de los perfiles de laterales llevados a la planta (PURO;
ver `recognition_grosor_perfiles`).

Cada utilidad se reconoce aparte (a veces en procesos distintos); este paso corre cuando ya están
TODAS (`recognition_trabajo.reconocer_hoja` y la unión de las partes en `RecognitionWorker`). Por
cada perfil «CB-208 LATERAL» de la hoja:

  1. su LATERAL en la planta: la línea de drenaje cuyo rótulo nombra «CB-208» («LAT CB-208 / 18"
     RCP, LACFCD»), si es una sola; su extremo sobre la principal (STA 1+00.00 del perfil = el eje
     de la principal) es el que cae en el medio de otra línea de drenaje más larga, o el claramente
     más cerca de una. Si esa línea es solo un TROZO corto del lateral, su recta prolongada.
  2. cada cruce del perfil («EX. 4" GAS, SCG» a 41.4 ft): la línea de ESA utilidad que corta al
     lateral a esa distancia de la principal, con un estado compatible si el rótulo lo dice (EX =
     capa existente, PROP = propuesta, ABND = abandonada; D = a abandonar, vale por las dos), y sin
     otra de esa utilidad cerca (`UNICO_PIES`): si no, no se sabe y no se usa. Cada lateral llega a
     la principal a su manera (a su eje, al borde de un pozo, a otro sumidero): las distancias se
     comparan con un CORRIMIENTO común (`_desfase`), directo a ≤`DIRECTO_PIES` o, si dos o más
     cruces coinciden con el mismo corrimiento, hasta `DESFASE_MAX_PIES`.
  3. el propio lateral toma el diámetro del perfil («L=65.54', 18" RCP SD»).

Lo que encuentra se suma a lo que ya dijo la planta (`grosor`): una línea sin dato toma el diámetro
(fuente «perfil»); si coincide con su rótulo, lo confirma; si no coincide, queda dudosa (y sin
diámetro). Los avisos de la vista previa se recuentan.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from traduccion.i18n_core import t as _tr

Pt = Tuple[float, float]

AJUSTE_PIES = 1.0        # el corte en la planta a ≤ esto de la estación del cruce (ya corrida)
UNICO_PIES = 3.0         # … y ninguna OTRA línea de esa utilidad a menos de esto
DESFASE_MAX_PIES = 6.0   # corrimiento máximo entre las estaciones del perfil y la planta (con ≥2 cruces)
DIRECTO_PIES = 1.5       # sin corrimiento (o un solo cruce): a ≤ esto
HUECO_MAX_PIES = 10.0    # el lateral termina a ≤ esto de la principal
TROZO_FRAC = 0.6         # la línea con el nombre mide menos que esto del perfil: es un trozo del lateral
EN_PRINCIPAL_PX = 2.0    # la punta del lateral sobre la principal (× zoom: px de la vista por pt)


def _corte(a: Pt, b: Pt, c: Pt, d: Pt) -> Optional[float]:
    """t ∈ [0, 1] sobre a→b donde corta a c→d, o None."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den
    u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return t
    return None


def cortes(lateral: Sequence[Pt], otra: Sequence[Pt]) -> List[float]:
    """Distancias (px, a lo largo de `lateral` desde su primer punto) donde `otra` lo corta."""
    out, acum = [], 0.0
    for a, b in zip(lateral, lateral[1:]):
        L = math.dist(a, b)
        for c, d in zip(otra, otra[1:]):
            t = _corte(a, b, c, d)
            if t is not None:
                out.append(acum + t * L)
        acum += L
    return out


def _dist_interior(p: Pt, pts: Sequence[Pt]) -> float:
    """Distancia de p a la polilínea, sin contar sus puntas (p sobre su MEDIO)."""
    mejor = math.inf
    n = len(pts)
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        if L2 < 1e-12:
            continue
        t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2
        lo = 0.0 if k > 0 else 0.02
        hi = 1.0 if k < n - 2 else 0.98
        t = max(lo, min(hi, t))
        mejor = min(mejor, math.hypot(a[0] + t * vx - p[0], a[1] + t * vy - p[1]))
    return mejor


def _largo(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def estado_linea(pl) -> str:
    """E / N / A / D de la capa de la línea (la letra de estado del nombre NCS), "" si no se sabe."""
    if getattr(pl, "abandoned", False):
        return "A"
    corto = (getattr(pl, "layer_ocg", "") or "").split("|")[-1].upper()
    ult = corto.rsplit("-", 1)[-1] if "-" in corto else ""
    return ult[:1] if len(ult) <= 2 and ult[:1] in ("E", "N", "A", "D") else ""


# el estado del rótulo del perfil → los de la capa que le corresponden: «D» (a abandonar) hoy
# existe y luego queda abandonada
COMPATIBLES = {"E": ("E", "D"), "A": ("A", "D"), "N": ("N",)}


def _lineas(res, variante: str):
    return [p for p in (getattr(res, variante, None) or []) if (getattr(p, "grosor", None) or {}).get("estado")]


def _recta(p: Pt, u: Pt, pts: Sequence[Pt]) -> List[float]:
    """Parámetros k (p + k·u, u unitario) donde la recta infinita corta a la polilínea."""
    out = []
    for c, d in zip(pts, pts[1:]):
        sx, sy = d[0] - c[0], d[1] - c[1]
        den = u[0] * sy - u[1] * sx
        if abs(den) < 1e-12:
            continue
        k = ((c[0] - p[0]) * sy - (c[1] - p[1]) * sx) / den
        w = ((c[0] - p[0]) * u[1] - (c[1] - p[1]) * u[0]) / den
        if -1e-9 <= w <= 1 + 1e-9:
            out.append(k)
    return out


def _prolongado(lat, dren, largo_pies: float, ppf: float):
    """El lateral cuando la línea con su nombre es solo un TROZO (partido en una caja o un quiebre):
    su recta, desde donde corta a la principal (la línea de drenaje más cercana y larga que la
    recta cruza a menos del largo del perfil) hacia el trozo, con el largo del perfil. Solo si el
    trozo es recto: los laterales de DU06 lo son (tabla de líneas: un rumbo por lateral)."""
    pts = [tuple(q) for q in lat.pts_pdf]
    a, b = pts[0], pts[-1]
    L = math.dist(a, b)
    if L < 1e-6 or any(_dist_interior(q, [a, b]) > 0.5 * ppf for q in pts[1:-1]):
        return None
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    alcance = (largo_pies + HUECO_MAX_PIES) * ppf
    cortes_k = [k for o in dren if o is not lat and _largo(o.pts_pdf) > 2.0 * largo_pies * ppf
                for k in _recta(a, u, o.pts_pdf) if (k < -1e-6 or k > L + 1e-6) and abs(k) <= alcance]
    antes = [k for k in cortes_k if k < 0]
    despues = [k for k in cortes_k if k > L]
    if bool(antes) == bool(despues):
        return None                    # la principal a los dos lados, o a ninguno: no se sabe
    if antes:
        k0, s = max(antes), 1.0        # la más cercana por detrás: el lateral va hacia +u
    else:
        k0, s = min(despues), -1.0
    m = (a[0] + k0 * u[0], a[1] + k0 * u[1])
    fin = (m[0] + s * u[0] * (largo_pies + 2.0) * ppf, m[1] + s * u[1] * (largo_pies + 2.0) * ppf)
    return [m, fin], 0.0, lat


def _lateral(dren, nombre: str, zoom: float, ppf: float, largo_pies: float = 0.0):
    """(puntos desde la principal, hueco hasta ella en px, línea) del lateral «nombre», o None. El
    extremo de la principal es el que cae sobre el medio de una línea de drenaje más larga, o el
    claramente más cerca de una (el lateral puede terminar en el borde de un pozo). Si la línea
    con su nombre es un trozo corto del lateral, su recta prolongada (`_prolongado`)."""
    suyas = [p for p in dren if nombre in ((p.grosor or {}).get("nombres") or ())]
    if len(suyas) > 1:
        suyas = [p for p in suyas if list((p.grosor or {}).get("nombres") or ()) == [nombre]]
    if len(suyas) != 1:
        return None
    lat = suyas[0]
    pts = [tuple(q) for q in lat.pts_pdf]
    if len(pts) < 2:
        return None
    largo = _largo(pts)
    if largo_pies and largo > max(3.0 * largo_pies, largo_pies + 60.0) * ppf:
        return None                    # mucho más larga que el lateral del perfil: no es él
    if largo_pies and largo < TROZO_FRAC * largo_pies * ppf:
        return _prolongado(lat, dren, largo_pies, ppf)
    otras = [o for o in dren if o is not lat and _largo(o.pts_pdf) > largo]
    if not otras:
        return None
    d0, d1 = (min(_dist_interior(e, o.pts_pdf) for o in otras) for e in (pts[0], pts[-1]))
    if min(d0, d1) > HUECO_MAX_PIES * ppf:
        return None
    if d0 <= EN_PRINCIPAL_PX * zoom < d1 or (d1 > EN_PRINCIPAL_PX * zoom and d1 >= 2.0 * d0):
        return pts, d0, lat
    if d1 <= EN_PRINCIPAL_PX * zoom < d0 or (d0 > EN_PRINCIPAL_PX * zoom and d0 >= 2.0 * d1):
        return pts[::-1], d1, lat
    return None


def _desfase(por_cruce: List[List[float]], estaciones: List[float]) -> Optional[Tuple[float, int]]:
    """El corrimiento (pies) entre las estaciones del perfil y las distancias de la planta que más
    cruces explica (cada lateral llega a la principal a su manera: a su eje, al borde de un pozo),
    y cuántos explica; None si ninguno sirve."""
    mejor = None
    for planos, s in zip(por_cruce, estaciones):
        for p in planos:
            d = p - s
            if abs(d) > DESFASE_MAX_PIES:
                continue
            apoyo = [min((q - s2 - d for q in qs), key=abs) for qs, s2 in zip(por_cruce, estaciones)
                     if qs and min(abs(q - s2 - d) for q in qs) <= AJUSTE_PIES]
            clave = (len(apoyo), -abs(d))
            if mejor is None or clave > mejor[0]:
                mejor = (clave, d + sum(apoyo) / len(apoyo), len(apoyo))
    if mejor is None:
        return None
    _clave, d, n = mejor
    if abs(d) > DIRECTO_PIES and n < 2:
        return None                # un solo cruce corrido: no se sabe si es el corrimiento o otra tubería
    return d, n


def _sumar(pl, hallados: List[Tuple[float, str]]) -> None:
    """Lo que dicen los perfiles de una línea, sobre lo que ya dijo la planta."""
    g = pl.grosor
    vals = sorted({d for d, _t in hallados})
    textos = list(dict.fromkeys(t for _d, t in hallados))
    estado = g.get("estado")
    g["perfil_in"] = vals
    g["perfil_textos"] = textos
    if estado == "sin_dato":
        if len(vals) == 1:
            g.update(estado="leido", diam_in=vals[0], fuente="perfil")
            if pl.diam_in is None:
                pl.diam_in = vals[0]
        else:
            g.update(estado="dudoso", fuente="perfil", candidatos=vals)
    elif estado == "leido":
        if vals != [g.get("diam_in")]:
            d0 = g.get("diam_in")
            g.update(estado="dudoso", fuente="plano≠perfil", candidatos=sorted(set(vals) | {d0}), diam_in=None)
            if pl.diam_in == d0:
                pl.diam_in = None
    else:
        g["candidatos"] = sorted(set(g.get("candidatos") or ()) | set(vals))


def aplicar(results: Sequence) -> int:
    """Lleva los perfiles de laterales de la hoja a las líneas de todas las utilidades. Devuelve
    cuántas líneas toman o confirman algo de un perfil."""
    # los de la hoja (iguales en todas las utilidades) y, en una compuesta, los de sus hojas de origen
    # (solo en la utilidad que los leyó)
    perfiles = list({pv.nombre: pv for r in reversed(list(results)) for pv in (getattr(r, "perfiles", None) or [])}
                    .values())
    por_util = {r.utility: r for r in results}
    if not perfiles or "DRENAJE" not in por_util:
        return 0
    n = 0
    escala = getattr(por_util["DRENAJE"], "scale_ft_per_pt", 0.0) or 0.0
    for variante in ("polylines_joined", "polylines_raw"):
        dren = _lineas(por_util["DRENAJE"], variante)
        hallados: Dict[int, Tuple[object, List[Tuple[float, str]]]] = {}
        for pv in perfiles:
            ppf = getattr(pv, "planta_px_por_pie", 0.0) or 0.0
            if ppf <= 0 or escala <= 0:
                continue
            got = _lateral(dren, pv.nombre, ppf * escala, ppf, pv.largo_pies)   # zoom = px por pie × pies por pt
            if got is None:
                continue
            pts, hueco, lat = got
            if pv.diam_in:
                hallados.setdefault(id(lat), (lat, []))[1].append((pv.diam_in, pv.texto))
            # cada cruce: las líneas de su utilidad (y su estado, si el rótulo lo dice) que cortan al
            # lateral, a cuántos pies de la principal
            cands = []
            for c in pv.cruces:
                res = por_util.get(c.utilidad)
                lst = []
                for pl in (_lineas(res, variante) if res is not None else []):
                    est = estado_linea(pl)
                    if c.estado and est and est not in COMPATIBLES.get(c.estado, (c.estado,)):
                        continue
                    lst += [((s + hueco) / ppf, pl) for s in cortes(pts, pl.pts_pdf)]
                cands.append(lst)
            des = _desfase([[p for p, _pl in lst] for lst in cands], [c.pies for c in pv.cruces])
            if des is None:
                continue
            d = des[0]
            tol = AJUSTE_PIES if abs(d) > DIRECTO_PIES else DIRECTO_PIES
            for c, lst in zip(pv.cruces, cands):
                cerca = {id(pl): pl for p, pl in lst if abs(p - c.pies - d) <= tol}
                if len(cerca) != 1:
                    continue
                pl = next(iter(cerca.values()))
                if any(abs(p - c.pies - d) < UNICO_PIES for p, o in lst if o is not pl):
                    continue                         # otra de esa utilidad casi ahí: no se sabe cuál
                hallados.setdefault(id(pl), (pl, []))[1].append((c.diam_in, c.texto))
        for pl, lst in hallados.values():
            _sumar(pl, lst)
            n += 1
    if n:
        for r in results:
            recontar(r)
    return n


# ── avisos de la vista previa (los mismos en `recognize_page` y al recontar) ──────────────
def _plantillas():
    return (_tr("Diámetros del plano (rótulos con flecha y paredes dibujadas): {n} tubería(s) los toman; {m} "
                "dudosa(s) quedan con el diámetro por defecto y un aviso en el editor."),
            _tr("Tuberías sin diámetro en el plano: {n} — ningún rótulo con flecha llega a ellas ni tienen "
                "paredes dibujadas; quedan con el diámetro por defecto y un aviso en el editor."))


def avisos_grosor(con: int, revisar: int, sin: int) -> List[str]:
    leidos, sin_dato = _plantillas()
    out = []
    if con or revisar:
        out.append(leidos.format(n=con, m=revisar))
    if sin:
        out.append(sin_dato.format(n=sin))
    return out


def recontar(res) -> None:
    """Rehace los avisos del grosor de un resultado con el estado de sus líneas de ahora."""
    prefijos = tuple(p.split("{n}")[0] for p in _plantillas())
    viejos = [k for k, w in enumerate(res.warnings) if w.startswith(prefijos)]
    if not viejos:
        return
    estados = [(getattr(p, "grosor", None) or {}).get("estado") for p in res.polylines]
    nuevos = avisos_grosor(estados.count("leido"), estados.count("dudoso"), estados.count("sin_dato"))
    k0 = viejos[0]
    res.warnings[:] = [w for k, w in enumerate(res.warnings) if k not in viejos]
    res.warnings[k0:k0] = nuevos
