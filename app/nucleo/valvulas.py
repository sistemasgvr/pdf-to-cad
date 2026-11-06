"""Válvulas de compuerta en redes a PRESIÓN (agua y gas), pedido del usuario 2026-11-04. PURO (sin Qt).

El usuario pone la válvula con un clic sobre una tubería (como el buzón) y la app decide todo lo demás:
diámetro (el de la tubería), pieza del catálogo, largo y dónde cabe. Solo en un TRAMO RECTO: entre dos vértices
de la tubería (o entre la tangencia de una curva y el vértice siguiente), nunca encima de un codo, Tee, Wye,
cruz ni curva. Lo que la app indica, el plugin lo cumple: el DXF lleva el punto EXACTO del centro, la dirección
del tramo y la pieza (`PDFCAD_VALVULA`).

Pieza = `valvula_receta` (2026-11-05: la forma del catálogo del plugin de válvulas del equipo como fórmulas del
diámetro, para CUALQUIER diámetro de `N_MIN` a `N_MAX`; fuera de la tabla de normas queda «estimada»): válvula de
compuerta AWWA C509/C515; RG (junta mecánica) hasta 16"; desde 18" con bridas y operador de engranes. Medidas
representativas (no certificadas por un fabricante), como dice ese plugin.

Cada válvula del proyecto = {"x", "y" (px del lienzo, centro sobre la tubería), "union" ("FLG"|"RG"),
"material" ("" = el de la tubería | "DI-A" | "CI" | "PVC")}. Sin índices de utilidades: borrar o unir
utilidades no las desordena; en cada redibujo y al exportar se vuelve a ubicar sobre su tubería
(`ubicar(..., libre=False)`) y, si ya no está en un tramo recto donde quepa, queda marcada con el motivo y no
va al DXF.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from nucleo import limpieza_tramos, model_ops
from nucleo import valvula_receta as VR
from nucleo.accesorios import GIRO_CODO_MIN_DEG, TOL_UNION_FT, red_de
from nucleo.model import network_kind
from traduccion.i18n_core import t as _tr

SERIE = VR.SERIE                       # diámetros de la tabla de normas (los demás, «estimados»)
RG_MAX_IN = VR.RG_MAX_IN               # la junta mecánica (RG) llega hasta 16"
ENGRANES_MIN_IN = VR.ENGRANES_MIN_IN   # ≥ 18": bridas + operador de engranes
UNIONES = ("FLG", "RG")
MATERIALES = ("DI-A", "CI", "PVC")

ALCANCE_ACC_D = 1.70           # brazo 1.25·D + campana 0.45·D de un codo/Tee/Wye/cruz (`accesorios3d`)
TUBO_MIN_FT = limpieza_tramos.TRAMO_MIN_FT   # tubo libre entre la válvula y lo que haya a cada lado (1 ft)
SOBRE_TOL_FT = 0.05            # una válvula guardada sigue «en su lugar» si se corre menos que esto
EPS = 1e-9


def diametro_valido(d_in):
    """El diámetro (pulgadas, redondeado a 0.01") si hay válvula para él, o None."""
    d = round(float(d_in or 0), 2)
    return d if VR.N_MIN - 1e-9 <= d <= VR.N_MAX + 1e-9 else None


def pieza(n, union="FLG"):
    """(bloque, unión efectiva, largo in, OD del extremo in, avisos) de la válvula de n pulgadas."""
    rec = VR.receta(n, union)
    avisos = []
    u = "RG" if rec.tipo == "RG" else "FLG"
    if union == "RG" and u != "RG":
        avisos.append(_tr("La junta mecánica (RG) llega hasta 16\": va con bridas (FLG)."))
    if rec.estimada:
        avisos.append(_tr("{d}\" no está en la tabla de normas: medidas estimadas (interpoladas).").format(d=f"{n:g}"))
    return rec.bloque, u, rec.largo, rec.od_extremo, avisos


def material_de(elegido, material_tuberia):
    """El material de la válvula: el elegido o, sin elegir, el que sugiere la tubería (DI-A si no dice)."""
    if elegido in MATERIALES:
        return elegido
    m = (material_tuberia or "").upper()
    if "PVC" in m or "C900" in m or "C905" in m:
        return "PVC"
    if "CAST" in m or m.startswith("CI") or " CI" in m or "FUNDIDO" in m:
        return "CI"
    return "DI-A"


@dataclass
class Lugar:
    """Dónde queda (o por qué no) una válvula."""
    ok: bool = False
    motivo: str = ""
    pipe: int = -1
    tramo: int = -1
    x: float = 0.0
    y: float = 0.0
    ux: float = 1.0                # dirección del tramo (px del lienzo, unitaria)
    uy: float = 0.0
    diam_in: float = 0.0
    bloque: str = ""
    union: str = "FLG"
    material: str = ""
    largo_ft: float = 0.0
    brida_ft: float = 0.0
    movida: bool = False           # se corrió para caber
    estimada: bool = False         # diámetro fuera de la tabla de normas
    avisos: list = field(default_factory=list)


def es_presion(p):
    return network_kind(p.get("layer") or "") == "pressure"


def _dist_seg(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
    return math.hypot(x - (a[0] + u * dx), y - (a[1] + u * dy))


def _cruce(a, b, c, d):
    """Parámetros (t, u) del cruce de a–b con c–d dentro de los dos tramos, o None."""
    r = (b[0] - a[0], b[1] - a[1]); s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < EPS:
        return None
    q = (c[0] - a[0], c[1] - a[1])
    t = (q[0] * s[1] - q[1] * s[0]) / den
    u = (q[0] * r[1] - q[1] * r[0]) / den
    return (t, u) if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS else None


def _giro(pts, k):
    """Deflexión (°) en el vértice interior k."""
    a, c, b = pts[k - 1], pts[k], pts[k + 1]
    u = (c[0] - a[0], c[1] - a[1]); w = (b[0] - c[0], b[1] - c[1])
    nu, nw = math.hypot(*u), math.hypot(*w)
    if nu < EPS or nw < EPS:
        return 0.0
    cs = max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (nu * nw)))
    return math.degrees(math.acos(cs))


def _otras_tocan(pipes, i, q, tol, cerca):
    """¿Otra utilidad (cualquier capa) pasa o termina en q? (ahí va un accesorio o una unión)."""
    for j in cerca(q[0], q[1], tol):
        if j == i:
            continue
        pts = pipes[j].get("pts") or ()
        for a, b in zip(pts, pts[1:]):
            if _dist_seg(q[0], q[1], a, b) <= tol:
                return True
    return False


def _tramo_libre(pipes, structures, i, k, ft, otras_valvulas, cerca, diam_in):
    """(a, b, lo, hi, prohibidos) del tramo recto k de la utilidad i: a/b = sus puntas, [lo, hi] = dónde puede
    ir el CENTRO de una válvula medido desde a (ft, sin el largo de la válvula), prohibidos = [(s, medio)] de lo
    que hay en medio (otras utilidades que llegan o cruzan, otras válvulas)."""
    p = pipes[i]
    pts = p["pts"]
    cv, geos = limpieza_tramos.curvas(pipes, structures, i, ft)
    _k, a, b = limpieza_tramos.rectos(pts, geos)[k]
    L = math.hypot(b[0] - a[0], b[1] - a[1]) * ft
    alcance = ALCANCE_ACC_D * diam_in / 12.0
    tol = TOL_UNION_FT / ft
    n = len(pts)

    def margen(v, en_curva):
        if en_curva:                                   # tangencia de una curva: solo tubo libre
            return TUBO_MIN_FT
        hay_acc = (0 < v < n - 1 and _giro(pts, v) > GIRO_CODO_MIN_DEG) or _otras_tocan(pipes, i, pts[v], tol, cerca)
        return (alcance if hay_acc else 0.0) + TUBO_MIN_FT

    lo = margen(k, k in geos)
    hi = L - margen(k + 1, (k + 1) in geos)
    prohibidos = []
    if L > EPS:
        ux, uy = (b[0] - a[0]) / (L / ft), (b[1] - a[1]) / (L / ft)
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        red = red_de(p)
        for j in cerca(cx, cy, L / ft / 2 + tol):
            if j == i:
                continue
            q = pipes[j]
            qp = q.get("pts") or ()
            for v in qp:                               # otra utilidad que llega a este tramo: Tee/Wye
                if _dist_seg(v[0], v[1], a, b) <= tol:
                    s = ((v[0] - a[0]) * ux + (v[1] - a[1]) * uy) * ft
                    prohibidos.append((s, alcance + TUBO_MIN_FT))
            if es_presion(q) and red_de(q) == red:     # cruce en X de la misma red: cruz
                for c, d in zip(qp, qp[1:]):
                    tu = _cruce(a, b, c, d)
                    if tu is not None:
                        prohibidos.append((tu[0] * L, alcance + TUBO_MIN_FT))
        for o in otras_valvulas:                       # otra válvula en el mismo tramo
            if _dist_seg(o["x"], o["y"], a, b) <= tol:
                s = ((o["x"] - a[0]) * ux + (o["y"] - a[1]) * uy) * ft
                prohibidos.append((s, o["largo_ft"] / 2 + TUBO_MIN_FT))
    return a, b, L, lo, hi, prohibidos


def _intervalos(lo, hi, prohibidos, medio):
    """Tramos [i, f] (ft desde la punta a) donde puede ir el centro de una válvula de medio largo `medio`."""
    libres = [(lo + medio, hi - medio)]
    for s, m in prohibidos:
        r0, r1 = s - m - medio, s + m + medio
        nuevos = []
        for i0, i1 in libres:
            if r1 <= i0 or r0 >= i1:
                nuevos.append((i0, i1))
                continue
            if r0 > i0:
                nuevos.append((i0, r0))
            if r1 < i1:
                nuevos.append((r1, i1))
        libres = nuevos
    return [(i0, i1) for i0, i1 in libres if i1 >= i0 - EPS]


def _todas(pipes):
    return lambda _x, _y, _r: range(len(pipes))


def ubicar(pipes, structures, x, y, ft, radio_px, union="FLG", material="", otras=(), libre=True, cerca=None):
    """Dónde queda una válvula con el clic (o el centro guardado) en (x, y). `ft` = pies por px del lienzo,
    `radio_px` = cuánto se busca la tubería, `otras` = las demás válvulas YA ubicadas ({"x", "y", "largo_ft"}),
    `libre` = puede correrse a lo largo del tramo para caber (al poner); sin `libre` (una guardada) solo vale
    donde está. `cerca(x, y, r)` = índices de utilidades con un tramo a ≤ r (por defecto todas)."""
    cerca = cerca or _todas(pipes)
    if not ft or ft <= 0:
        return Lugar(motivo=_tr("Falta la escala de la hoja."))
    mejor = None                                       # (dist, i, k) de presión
    otra = None                                        # la más cercana que no es de presión (para el motivo)
    for i in cerca(x, y, radio_px):
        p = pipes[i]
        pts = p.get("pts") or ()
        if len(pts) < 2:
            continue
        for k in range(len(pts) - 1):
            d = _dist_seg(x, y, pts[k], pts[k + 1])
            if d > radio_px:
                continue
            if es_presion(p):
                if mejor is None or d < mejor[0]:
                    mejor = (d, i, k)
            elif otra is None or d < otra[0]:
                otra = (d, i)
    if mejor is None:
        if otra is not None:
            return Lugar(motivo=_tr("{u} no es de agua ni de gas: las válvulas van en redes a presión.").format(
                u=model_ops.nombre_por_defecto(pipes[otra[1]], otra[1])))
        return Lugar(motivo=_tr("Acércate a una tubería de agua o gas: la válvula se pone sobre ella."))
    _d, i, k = mejor
    p = pipes[i]
    nombre = model_ops.nombre_por_defecto(p, i)
    d_in = model_ops.diametro(p)[0]
    n = diametro_valido(d_in)
    if n is None:
        return Lugar(pipe=i, tramo=k, motivo=_tr(
            "{u} es de {d}\": hay válvulas de {a}\" a {b}\".").format(
            u=nombre, d=f"{d_in:g}", a=f"{VR.N_MIN:g}", b=f"{VR.N_MAX:g}"))
    bloque, u_ef, largo_in, od_in, avisos = pieza(n, union)
    largo_ft = largo_in / 12.0
    lug = Lugar(pipe=i, tramo=k, diam_in=float(n), bloque=bloque, union=u_ef,
                material=material_de(material, p.get("material")), largo_ft=largo_ft, brida_ft=od_in / 12.0,
                avisos=avisos, estimada=n not in VR.TABLA)
    pts = p["pts"]
    try:
        a, b, L, lo, hi, prohibidos = _tramo_libre(pipes, structures, i, k, ft, otras, cerca, n)
    except (IndexError, KeyError):
        lug.motivo = _tr("No se pudo leer el tramo de {u}.").format(u=nombre)
        return lug
    if L <= EPS or ((b[0] - a[0]) * (pts[k + 1][0] - pts[k][0]) + (b[1] - a[1]) * (pts[k + 1][1] - pts[k][1])) <= 0:
        lug.motivo = _tr("Ahí {u} va en curva: la válvula va solo en un tramo recto.").format(u=nombre)
        return lug
    ux, uy = (b[0] - a[0]) / (L / ft), (b[1] - a[1]) / (L / ft)
    lug.ux, lug.uy = ux, uy
    s0 = ((x - a[0]) * ux + (y - a[1]) * uy) * ft      # el clic, en ft desde la punta a del tramo recto
    libres = _intervalos(lo, hi, prohibidos, largo_ft / 2)
    if not libres:
        necesita = largo_ft + (L - (hi - lo))
        lug.motivo = _tr("El tramo recto de {u} mide {L} ft: la válvula de {d}\" necesita {n} ft "
                         "(su largo y el espacio para el codo, la T o la curva de cada lado).").format(
            u=nombre, L=f"{L:.1f}", d=f"{n:g}", n=f"{necesita:.1f}")
        return lug
    if not libre:
        sobre = _dist_seg(x, y, a, b) * ft <= SOBRE_TOL_FT
        dentro = any(i0 - SOBRE_TOL_FT <= s0 <= i1 + SOBRE_TOL_FT for i0, i1 in libres)
        if not sobre or not dentro:
            lug.motivo = _tr("La válvula ya no cabe aquí: {u} cambió (codo, curva, T o el tramo). "
                             "Quítala y vuelve a ponerla.").format(u=nombre)
            return lug
        s = s0                                         # donde está (pie sobre el tramo)
    else:
        s = min((min(max(s0, i0), i1) for i0, i1 in libres), key=lambda v: abs(v - s0))
        lug.movida = abs(s - s0) > SOBRE_TOL_FT
    lug.x, lug.y = a[0] + ux * s / ft, a[1] + uy * s / ft
    lug.ok = True
    return lug


def ubicar_todas(pipes, structures, valvulas, ft, cerca=None):
    """[Lugar] de cada válvula guardada, en orden (cada una con las anteriores ya ubicadas como obstáculo)."""
    tol = TOL_UNION_FT / ft if ft else 3.0
    out, ya = [], []
    for v in valvulas or ():
        lug = ubicar(pipes, structures, float(v["x"]), float(v["y"]), ft, tol, v.get("union") or "FLG",
                     v.get("material") or "", ya, libre=False, cerca=cerca)
        out.append(lug)
        if lug.ok:
            ya.append({"x": lug.x, "y": lug.y, "largo_ft": lug.largo_ft})
    return out


def en(valvulas, lugares, x, y, tol):
    """Índice de la válvula a ≤ tol de (x, y) (o -1)."""
    mejor = (-1, tol)
    for idx, v in enumerate(valvulas or ()):
        lug = lugares[idx] if lugares and idx < len(lugares) else None
        px, py = (lug.x, lug.y) if lug is not None and lug.ok else (float(v["x"]), float(v["y"]))
        d = math.hypot(px - x, py - y)
        if d <= mejor[1]:
            mejor = (idx, d)
    return mejor[0]


def nueva(lug, union="FLG", material=""):
    """La válvula a guardar en el proyecto para un `Lugar` válido."""
    return {"x": float(lug.x), "y": float(lug.y), "union": union if union in UNIONES else "FLG",
            "material": material if material in MATERIALES else ""}
