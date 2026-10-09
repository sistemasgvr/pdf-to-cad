"""Tramos rectos diminutos y curvas para `limpieza` (PURO: sin Qt).

El plugin crea un tubo por cada tramo RECTO de una utilidad: de un vértice (o de la
tangencia de salida de una curva) al siguiente (o a la tangencia de entrada de la
siguiente curva). Un tramo de menos de 1 ft sale como una tubería diminuta en Civil 3D
(proyecto de prueba: «ELECTRICO-47 (19)», una curva reconocida cuyo inicio quedó a
0.07 ft de la T de donde sale, y «ELECTRICO-47 (20)», 0.31 ft rectos entre dos curvas
seguidas de una curva compuesta). Arreglos, en este orden, y solo si BAJA la cantidad
de tramos diminutos de la utilidad sin cambiar ni recortar ninguna otra curva:

  1. quitar el vértice que sobra: sin otra utilidad, sin buzón/caja visible, sin curva
     y a ≤0.25 ft del dibujo;
  2. estirar la curva vecina hasta el vértice: misma esquina, radio apenas mayor, la
     tangencia cae justo en él (ese lado queda sin tramo recto: el plugin no crea
     tubos de largo cero);
  3. correr la ESQUINA de la curva (≤0.5 ft) por la recta del otro lado, dejando fija
     la otra tangencia: el arco tangente a esa recta que pasa por el vértice. La esquina
     es un punto virtual (el arco no pasa por ella): si cae sobre otra utilidad, se
     corre solo si sigue sobre ella;
  4. si el vértice que sobra es el ancla de una curva (su tangencia cae en él): quitarlo
     y correr la esquina como en 3, con la otra tangencia donde estaba.

Las curvas se calculan como el editor y el plugin (`model_ops.fillet_geo`, mismos
topes). `ft` = pies por px del lienzo.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from nucleo import model_ops

TRAMO_MIN_FT = 1.0          # tramo recto más corto = tubería diminuta en Civil 3D
DESVIO_MAX_FT = 0.25        # lo más que se aparta el dibujo al quitar un vértice
TRAMO_PLUGIN_MIN_FT = 0.02  # el plugin no crea tubos más cortos (CrearTuboRecto)
# Otra utilidad pasa por el vértice: es una unión, no se quita. Los nodos reconocidos y
# los dibujados con imán coinciden EXACTO; más tolerancia tomaba por unión el ancla de
# una curva a 0.07 ft de la T (justo el tramo diminuto a quitar).
COMPARTIDO_FT = 0.01
TANGENCIA_FT = 0.005        # la tangencia de la curva arreglada cae en el vértice
ESQUINA_MAX_FT = 0.5        # lo más que se corre la esquina de una curva
RADIO_TOL_FT = model_ops.FILLET_TOL_RADIO_FT + 0.001


@dataclass
class Cambio:
    tipo: str               # "tramo" | "punta" | "corta" | "duplicada" | "suelta"
    pipe: int               # índice de la utilidad (antes de borrar las sobrantes)
    x: float                # lugar en el lienzo (px), para ir a verlo
    y: float
    largo_ft: float = 0.0   # largo del tramo / del hueco / de la utilidad
    arreglado: bool = True  # False = solo aviso: no se pudo (o no se debe) arreglar solo
    como: str = ""          # "vertice" | "curva" | "esquina" | "ancla" | "punta" | "borrar"


# ─────────────────────────── geometría básica ───────────────────────────

def unit(a, b):
    """Vector unitario de a hacia b (None si coinciden)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-9 else None


def proyeccion(q, a, b):
    """(punto, t) de q sobre el tramo a→b (t en [0, 1])."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return (a[0], a[1]), 0.0
    t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
    return (a[0] + dx * t, a[1] + dy * t), t


def toca(q, pts, tol):
    """¿q está sobre la polilínea (vértice o tramo) a ≤ tol?"""
    return any(math.dist(q, proyeccion(q, a, b)[0]) <= tol for a, b in zip(pts, pts[1:]))


def compartido(pipes, i, q, tol):
    """¿Otra utilidad pasa por q (vértice o tramo)? Entonces es una unión."""
    return any(j != i and not o.get("world") and toca(q, o.get("pts") or [], tol)
               for j, o in enumerate(pipes))


def _angulo(c, a, b):
    """Ángulo interior en c entre c→a y c→b (rad), o None si es degenerado o recto."""
    u, w = unit(c, a), unit(c, b)
    if u is None or w is None:
        return None
    phi = math.acos(max(-1.0, min(1.0, u[0] * w[0] + u[1] * w[1])))
    return phi if math.radians(1.0) < phi < math.radians(178.0) else None


# ─────────────────────────── curvas ───────────────────────────

def _radio_ft(p, s):
    r = float(s.get("radius_ft") or 0.0)
    return r if r > 0.01 else model_ops.radio_auto_ft(p)


def _geo(p, cv, k, ft):
    """Arco de la curva del vértice k, con los topes del plugin."""
    pts = p["pts"]
    cap_a = model_ops.FILLET_CAP_CURVA if (k - 1) in cv else model_ops.FILLET_CAP_RECTA
    cap_b = model_ops.FILLET_CAP_CURVA if (k + 1) in cv else model_ops.FILLET_CAP_RECTA
    return model_ops.fillet_geo(pts[k - 1], pts[k], pts[k + 1], _radio_ft(p, cv[k]) / ft,
                                max_frac=cap_a, max_frac_next=cap_b,
                                tol_r=model_ops.FILLET_TOL_RADIO_FT / ft)


def curvas(pipes, structures, i, ft):
    """(cv, geos): estructura curva y arco de cada vértice curvo de la utilidad i."""
    p = pipes[i]
    n = len(p["pts"])
    cv = model_ops.curve_vertex_indices(p, structures, pipes) if n >= 3 else {}
    cv = {k: s for k, s in cv.items() if 0 < k < n - 1}
    geos = {}
    for k in cv:
        g = _geo(p, cv, k, ft)
        if g is not None:
            geos[k] = g
    return cv, geos


def _firma(pipes, structures, i, ft):
    """{id(estructura curva): (radio usado ft, recortada)} de la utilidad i."""
    cv, geos = curvas(pipes, structures, i, ft)
    return {id(cv[k]): (g["r"] * ft, g["clamped"]) for k, g in geos.items()}


def _intactas(antes, despues, salvo=None):
    """Ninguna curva (salvo `salvo`) desaparece, se recorta ni baja de radio."""
    for clave, (r, recortada) in antes.items():
        if clave == salvo:
            continue
        if clave not in despues:
            return False
        r2, recortada2 = despues[clave]
        if (recortada2 and not recortada) or r2 < r - RADIO_TOL_FT:
            return False
    return True


def rectos(pts, geos):
    """[(k, inicio, fin)]: tramo recto entre los vértices k y k+1 tal como lo arma el
    plugin (de la tangencia de salida de una curva a la de entrada de la siguiente)."""
    return [(k, geos[k]["t2"] if k in geos else pts[k], geos[k + 1]["t1"] if k + 1 in geos else pts[k + 1])
            for k in range(len(pts) - 1)]


def _diminuto(L_ft):
    return TRAMO_PLUGIN_MIN_FT <= L_ft < TRAMO_MIN_FT


def diminutos(pipes, structures, i, ft):
    """[(k, inicio, fin, largo_ft)] tramos rectos diminutos de la utilidad i. Entre dos
    curvas seguidas no cuenta: ahí el plugin deja su recto mínimo (1 × ancho)."""
    _cv, geos = curvas(pipes, structures, i, ft)
    out = []
    for k, ini, fin in rectos(pipes[i]["pts"], geos):
        L = math.dist(ini, fin) * ft
        if _diminuto(L) and not (k in geos and k + 1 in geos):
            out.append((k, ini, fin, L))
    return out


def _radio_ceil(T_px, phi, ft):
    """Radio (ft, 2 decimales HACIA ARRIBA) con tangencia T: el plugin y el editor
    toman el máximo del tramo sin recortar (FILLET_TOL_RADIO_FT)."""
    return math.ceil(T_px * math.tan(phi / 2.0) * ft * 100.0 - 1e-6) / 100.0


def _probar_curva(pipes, structures, i, c, a, ft, firma, n_antes, cambio):
    """Aplica `cambio()` (que devuelve cómo deshacerlo) y lo conserva solo si la curva
    de c arranca justo en el vértice a, sin recorte, con el recto mínimo del plugin si
    hay otra curva seguida, sin tocar otra curva y con menos tramos diminutos."""
    p = pipes[i]
    pts = p["pts"]
    otro = c + 1 if a == c - 1 else c - 1
    s = model_ops.curve_vertex_indices(p, structures, pipes).get(c)
    deshacer = cambio()
    if deshacer is None:
        return False
    _cv, geos = curvas(pipes, structures, i, ft)
    g = geos.get(c)
    lado = "t1" if a == c - 1 else "t2"
    ok = (g is not None and not g["clamped"] and math.dist(g[lado], pts[a]) * ft <= TANGENCIA_FT
          and _intactas(firma, _firma(pipes, structures, i, ft), salvo=id(s))
          and len(diminutos(pipes, structures, i, ft)) < n_antes)
    if ok and otro in geos:                  # dos curvas seguidas: recto mínimo del plugin
        ancho_px = model_ops.diametro(p)[0] / 12.0 / ft
        ok = g["T"] + geos[otro]["T"] <= math.dist(pts[c], pts[otro]) - ancho_px
    if not ok:
        deshacer()
        return False
    fil = p.get("fillets")
    if fil and s is not None:
        for k in list(fil):
            if int(k) == c:
                fil[k] = float(s.get("radius_ft") or 0.0)
    return True


def _estirar_curva(pipes, structures, i, c, a, ft, firma, n_antes):
    """2. La curva de c llega hasta el vértice vecino a, con la misma esquina."""
    p = pipes[i]
    pts = p["pts"]
    s = model_ops.curve_vertex_indices(p, structures, pipes).get(c)
    phi = _angulo(pts[c], pts[a], pts[c + 1 if a == c - 1 else c - 1])
    if s is None or phi is None:
        return False

    def cambio():
        antes = s.get("radius_ft")
        s["radius_ft"] = _radio_ceil(math.dist(pts[c], pts[a]), phi, ft)
        return lambda: s.__setitem__("radius_ft", antes)
    return _probar_curva(pipes, structures, i, c, a, ft, firma, n_antes, cambio)


def _correr_esquina(pipes, structures, i, c, a, ft, firma, n_antes, B=None):
    """3. La curva de c arranca justo en el vértice a corriendo la ESQUINA por la recta
    del otro lado, con la otra tangencia B fija (por defecto, la actual): la esquina
    queda a la misma distancia de a y de B."""
    p = pipes[i]
    pts = p["pts"]
    cv, geos = curvas(pipes, structures, i, ft)
    if c not in geos or c not in cv:
        return False
    s = cv[c]
    C, A = tuple(pts[c]), tuple(pts[a])
    if B is None:
        B = geos[c]["t2"] if a == c - 1 else geos[c]["t1"]
    d = unit(B, C)
    if d is None:
        return False
    tol = COMPARTIDO_FT / ft
    apoyos = [o.get("pts") or [] for j, o in enumerate(pipes)
              if j != i and not o.get("world") and toca(C, o.get("pts") or [], tol)]
    w = (B[0] - A[0], B[1] - A[1])
    den = 2.0 * (d[0] * w[0] + d[1] * w[1])
    if den >= -1e-9:
        return False
    u = -(w[0] * w[0] + w[1] * w[1]) / den
    Cn = (B[0] + d[0] * u, B[1] + d[1] * u)
    phi = _angulo(Cn, A, B)
    if phi is None or math.dist(Cn, C) * ft > ESQUINA_MAX_FT:
        return False
    if not all(toca(Cn, q, tol) for q in apoyos):
        return False                          # la esquina se saldría de otra utilidad

    def cambio():
        mover = model_ops.structures_at_vertex(pipes, structures, i, c)
        antes_r = s.get("radius_ft")
        dx, dy = Cn[0] - C[0], Cn[1] - C[1]
        pts[c] = Cn
        for o in mover:
            model_ops.translate_structure(o, dx, dy)
        s["radius_ft"] = _radio_ceil(u, phi, ft)

        def deshacer():
            pts[c] = C
            for o in mover:
                model_ops.translate_structure(o, -dx, -dy)
            s["radius_ft"] = antes_r
        return deshacer
    return _probar_curva(pipes, structures, i, c, a, ft, firma, n_antes, cambio)


# ─────────────────────────── vértices ───────────────────────────

def quitar_vertice(p, v):
    """Quita el vértice v y corre los datos por vértice (cotas, tipos, codos)."""
    pts = p["pts"]
    n = len(pts)
    vout = {int(k): z for k, z in (p.get("vertex_inv_out") or {}).items()}
    if v == 0 and 1 in vout:
        p["inv_start"] = vout[1]              # la cota de salida del nuevo inicio
    vin = {int(k): z for k, z in (p.get("vertex_inv_in") or {}).items()}
    if v == n - 1 and n - 2 in vin:
        p["inv_end"] = vin[n - 2]

    def corre(d):
        out = {}
        for k, z in (d or {}).items():
            k = int(k)
            if k == v:
                continue
            k = k - 1 if k > v else k
            if 0 < k < n - 2:                 # los extremos van en inv_start/inv_end
                out[k] = z
        return out
    for clave in ("vertex_inv_out", "vertex_inv_in", "vertex_inv"):
        if p.get(clave):
            p[clave] = corre(p[clave])
    if isinstance(p.get("vertex_kinds"), list) and len(p["vertex_kinds"]) == n:
        p["vertex_kinds"] = p["vertex_kinds"][:v] + p["vertex_kinds"][v + 1:]
    if p.get("fillets"):
        p["fillets"] = {(int(k) - 1 if int(k) > v else int(k)): r
                        for k, r in p["fillets"].items() if int(k) != v}
    pts.pop(v)


def _quitable(pipes, structures, i, v, cv, ft):
    """Desvío (ft) que deja quitar el vértice v, o None si no se puede: lo comparte otra
    utilidad, lleva buzón/caja visible o curva, o el dibujo se aparta más de DESVIO_MAX_FT."""
    pts = pipes[i]["pts"]
    n = len(pts)
    if n <= 2 or v in cv or compartido(pipes, i, pts[v], COMPARTIDO_FT / ft):
        return None
    if any(not s.get("hidden") and not s.get("curve")
           for s in model_ops.structures_at_vertex(pipes, structures, i, v)):
        return None
    if 0 < v < n - 1:
        desvio = math.dist(pts[v], proyeccion(pts[v], pts[v - 1], pts[v + 1])[0]) * ft
    else:
        desvio = math.dist(pts[v], pts[1 if v == 0 else n - 2]) * ft
    return desvio if desvio < DESVIO_MAX_FT else None


def _quitar_un_vertice(pipes, structures, i, candidatos, cv, ft, firma, n_antes):
    """1. Quita el candidato que menos cambia el dibujo."""
    p = pipes[i]
    opciones = sorted((d, v) for v in candidatos
                      for d in [_quitable(pipes, structures, i, v, cv, ft)] if d is not None)
    for _d, v in opciones:
        copia = copy.deepcopy(p)
        quitar_vertice(copia, v)
        prueba = [copia if k == i else o for k, o in enumerate(pipes)]
        if (_intactas(firma, _firma(prueba, structures, i, ft))
                and len(diminutos(prueba, structures, i, ft)) < n_antes):
            quitar_vertice(p, v)
            return True
    return False


def _quitar_ancla(pipes, structures, i, m, a, ft, firma, n_antes):
    """4. El vértice m es el ancla de una curva vecina (su tangencia cae en él): se quita
    y la esquina de esa curva se corre para que arranque en a, con la otra tangencia
    donde estaba."""
    p = pipes[i]
    cv, geos = curvas(pipes, structures, i, ft)
    for c in (m - 1, m + 1):
        if c not in geos or c == a:
            continue
        lado, otro_lado = ("t1", "t2") if m == c - 1 else ("t2", "t1")
        if math.dist(geos[c][lado], p["pts"][m]) * ft > TRAMO_PLUGIN_MIN_FT:
            continue
        if _quitable(pipes, structures, i, m, cv, ft) is None:
            continue
        B = geos[c][otro_lado]
        antes = copy.deepcopy(p)
        quitar_vertice(p, m)
        c2, a2 = (c - 1 if m < c else c), (a - 1 if m < a else a)
        if _correr_esquina(pipes, structures, i, c2, a2, ft, firma, n_antes, B=B):
            return True
        p.clear()
        p.update(antes)
    return False


def arreglar(pipes, structures, i, ft):
    """Arregla los tramos diminutos de la utilidad i. Devuelve [Cambio]: lo arreglado y,
    sin arreglar (aviso), lo que queda."""
    p = pipes[i]
    cambios = []
    for _vuelta in range(len(p["pts"]) + 5):         # cada arreglo baja la cantidad de diminutos
        pend = diminutos(pipes, structures, i, ft)
        if not pend:
            break
        cv, geos = curvas(pipes, structures, i, ft)
        firma = _firma(pipes, structures, i, ft)
        hecho = ""
        for k, ini, fin, L in pend:
            if _quitar_un_vertice(pipes, structures, i, [v for v in (k, k + 1) if v not in geos],
                                  cv, ft, firma, len(pend)):
                hecho = "vertice"
            elif k + 1 in geos or k in geos:
                c, a = (k + 1, k) if k + 1 in geos else (k, k + 1)
                if _estirar_curva(pipes, structures, i, c, a, ft, firma, len(pend)):
                    hecho = "curva"
                elif _correr_esquina(pipes, structures, i, c, a, ft, firma, len(pend)):
                    hecho = "esquina"
            else:
                for m, a in ((k + 1, k), (k, k + 1)):
                    if _quitar_ancla(pipes, structures, i, m, a, ft, firma, len(pend)):
                        hecho = "ancla"
                        break
            if hecho:
                cambios.append(Cambio("tramo", i, (ini[0] + fin[0]) / 2.0, (ini[1] + fin[1]) / 2.0, L, True, hecho))
                break
        if not hecho:
            break
    for _k, ini, fin, L in diminutos(pipes, structures, i, ft):
        cambios.append(Cambio("tramo", i, (ini[0] + fin[0]) / 2.0, (ini[1] + fin[1]) / 2.0, L, False))
    return cambios
