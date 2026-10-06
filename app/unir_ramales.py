"""Unir utilidades que se cruzan en una T (PURO: sin Qt). Lo usa `unir_utilidades`.

Una utilidad es UNA polilínea: si una seleccionada nace a mitad de otra
seleccionada (ramal), la de paso se PARTE en la T (en su vértice, o en un vértice
nuevo sobre el tramo). Después se busca el recorrido punta con punta que pasa por
todas las seleccionadas (de cada una partida basta un trozo); los trozos que no
entran quedan como utilidades aparte, con los datos de su original. Las
utilidades NO seleccionadas nunca se tocan.

Ejemplo: 15 y 14 se tocan en la punta y 16 nace a mitad de la 14 → 15 → 14 (hasta
la T) → 16; el resto de la 14 queda como otra utilidad.
"""
from __future__ import annotations

import copy
import math

from model_ops import snapshot_seg_values

MAX_NODOS_BUSQUEDA = 50000


def _ints(d):
    return {int(k): float(v) for k, v in (d or {}).items()}


def _tiene_cotas(p):
    return (p.get("inv_start") is not None or p.get("inv_end") is not None
            or bool(p.get("vertex_inv_out")) or bool(p.get("vertex_inv_in")))


def punto_interior(q, pts, tol):
    """¿Dónde cae q en el INTERIOR de pts? ("v", i) sobre un vértice interior,
    ("s", i, t) sobre el tramo i→i+1 (lejos de sus puntas), o None."""
    n = len(pts)
    for i in range(1, n - 1):
        if math.dist(q, pts[i]) <= tol:
            return ("v", i)
    for i, ((ax, ay), (bx, by)) in enumerate(zip(pts, pts[1:])):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 <= 1e-12:
            continue
        t = ((q[0] - ax) * dx + (q[1] - ay) * dy) / L2
        L = math.sqrt(L2)
        if t * L <= tol or (1 - t) * L <= tol or not 0 < t < 1:
            continue
        if math.hypot(ax + dx * t - q[0], ay + dy * t - q[1]) <= tol:
            return ("s", i, t)
    return None


def _insertar_vertice(p, i, t):
    """Vértice nuevo sobre el tramo i→i+1 (en la fracción t); corre los datos
    por vértice. La cota del vértice nuevo es la del tramo en ese punto."""
    pts = p["pts"]
    a, b = pts[i], pts[i + 1]
    q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    n = len(pts)
    if _tiene_cotas(p):
        snapshot_seg_values(p)
        vout, vin = _ints(p.get("vertex_inv_out")), _ints(p.get("vertex_inv_in"))
        za = vout.get(i, p.get("inv_start") or 0.0) if i > 0 else (p.get("inv_start") or 0.0)
        zb = vin.get(i + 1, p.get("inv_end") or 0.0) if i + 1 < n - 1 else (p.get("inv_end") or 0.0)
        z = float(za) + (float(zb) - float(za)) * t
        corre = lambda d: {(k + 1 if k > i else k): v for k, v in d.items()}  # noqa: E731
        vout, vin = corre(vout), corre(vin)
        vout[i + 1] = vin[i + 1] = z
        p["vertex_inv_out"], p["vertex_inv_in"] = vout, vin
    if isinstance(p.get("vertex_kinds"), list) and len(p["vertex_kinds"]) == n:
        p["vertex_kinds"] = p["vertex_kinds"][:i + 1] + ["tee"] + p["vertex_kinds"][i + 1:]
    if p.get("fillets"):
        p["fillets"] = {(int(k) + 1 if int(k) > i else int(k)): r for k, r in p["fillets"].items()}
    p["pts"] = pts[:i + 1] + [q] + pts[i + 1:]
    return i + 1


def _partir(p, k):
    """Dos trozos de p en su vértice interior k (copias, con sus datos)."""
    n = len(p["pts"])
    a, b = copy.deepcopy(p), copy.deepcopy(p)
    a["pts"], b["pts"] = list(p["pts"][:k + 1]), list(p["pts"][k:])
    if _tiene_cotas(p):
        q = copy.deepcopy(p)
        snapshot_seg_values(q)
        vout, vin = _ints(q.get("vertex_inv_out")), _ints(q.get("vertex_inv_in"))
        a["inv_end"], b["inv_start"] = vin.get(k), vout.get(k)
        a["vertex_inv_out"] = {i: v for i, v in vout.items() if 0 < i < k}
        a["vertex_inv_in"] = {i: v for i, v in vin.items() if 0 < i < k}
        b["vertex_inv_out"] = {i - k: v for i, v in vout.items() if k < i < n - 1}
        b["vertex_inv_in"] = {i - k: v for i, v in vin.items() if k < i < n - 1}
    vk = p.get("vertex_kinds")
    if isinstance(vk, list) and len(vk) == n:
        nodo = vk[k] if vk[k] in ("vault", "stop") else "tee"
        a["vertex_kinds"] = list(vk[:k]) + [nodo]
        b["vertex_kinds"] = [nodo] + list(vk[k + 1:])
    if p.get("fillets"):
        fil = {int(i): r for i, r in p["fillets"].items()}
        a["fillets"] = {i: r for i, r in fil.items() if i < k}
        b["fillets"] = {i - k: r for i, r in fil.items() if i > k}
    return a, b


def partir_en_tes(piezas, tol):
    """piezas = [(índice original, pipe)] (copias). Parte cada una donde nace otra
    a mitad de ella. Devuelve (piezas, partidas = {índice original}) o
    (None, índice) si la T cae justo en un codo (no se puede partir ahí)."""
    piezas = list(piezas)
    partidas = set()
    cambio = True
    vueltas = 0
    while cambio and vueltas < 200:
        cambio, vueltas = False, vueltas + 1
        for x, (_ox, px) in enumerate(piezas):
            for q in (px["pts"][0], px["pts"][-1]):
                for y, (oy, py) in enumerate(piezas):
                    if y == x:
                        continue
                    donde = punto_interior(q, py["pts"], tol)
                    if donde is None:
                        continue
                    py = copy.deepcopy(py)
                    k = donde[1] if donde[0] == "v" else _insertar_vertice(py, donde[1], donde[2])
                    if k in {int(i) for i in (py.get("fillets") or {})}:
                        return None, oy
                    a, b = _partir(py, k)
                    piezas[y:y + 1] = [(oy, a), (oy, b)]
                    partidas.add(oy)
                    cambio = True
                    break
                if cambio:
                    break
            if cambio:
                break
    return piezas, partidas


def _rumbo(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _giro(p_in, p_out):
    """Giro (rad) al pasar del final de la polilínea p_in al inicio de p_out."""
    if len(p_in) < 2 or len(p_out) < 2:
        return 0.0
    d = _rumbo(p_in[-2], p_in[-1]) - _rumbo(p_out[0], p_out[1])
    return abs((d + math.pi) % (2 * math.pi) - math.pi)


def mejor_recorrido(piezas, tol, hueco_max):
    """El recorrido punta con punta [(i, al_revés, hueco_px)] que pasa por todas
    las originales (de cada partida basta un trozo); con menos
    hueco, más trozos y menos giro. Devuelve (recorrido, originales que faltan)."""
    n = len(piezas)
    origs = {o for o, _p in piezas}

    def pts_de(i, rev):
        p = piezas[i][1]["pts"]
        return list(reversed(p)) if rev else list(p)

    # Un hueco solo se cierra entre puntas LIBRES (que no tocan otro trozo): si no,
    # el recorrido «saltaría» de vuelta a la T por un tramo inventado.
    puntas = [(i, e, piezas[i][1]["pts"][0 if e == 0 else -1]) for i in range(n) for e in (0, 1)]
    libre = {(i, e): not any(j != i and math.dist(q, r) <= tol for j, _f, r in puntas)
             for i, e, q in puntas}
    mejor = {"clave": None, "camino": None, "faltan": origs}
    nodos = [0]

    def evaluar(camino, hueco_tot, giro_tot):
        cubiertas = {piezas[i][0] for i, _r, _h in camino}
        faltan = origs - cubiertas
        clave = (-len(faltan), -round(hueco_tot, 6), len(camino), -giro_tot)
        if mejor["clave"] is None or clave > mejor["clave"]:
            mejor.update(clave=clave, camino=list(camino), faltan=faltan)

    def extender(camino, usados, hueco_tot, giro_tot):
        nodos[0] += 1
        if nodos[0] > MAX_NODOS_BUSQUEDA:
            return
        evaluar(camino, hueco_tot, giro_tot)
        i, rev, _h = camino[-1]
        cola = pts_de(i, rev)
        for j in range(n):
            if j in usados:
                continue
            for rj in (False, True):
                pj = pts_de(j, rj)
                d = math.dist(cola[-1], pj[0])
                if d > hueco_max:
                    continue
                if d > tol and (piezas[i][0] == piezas[j][0]           # dos trozos de la misma: lazo
                                or not (libre[(i, 0 if rev else 1)] and libre[(j, 1 if rj else 0)])):
                    continue
                h = d if d > tol else 0.0
                camino.append((j, rj, h)); usados.add(j)
                extender(camino, usados, hueco_tot + h, giro_tot + _giro(cola, pj))
                camino.pop(); usados.discard(j)

    for i in range(n):
        for rev in (False, True):
            extender([(i, rev, 0.0)], {i}, 0.0, 0.0)
    return mejor["camino"], sorted(mejor["faltan"])
