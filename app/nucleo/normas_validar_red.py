"""Reglas que miran OTRA utilidad (PURO): separaciones y «diámetro menor que la tubería a la que llega».

  • En paralelo (REVISAR «Separación horizontal…»): tramos casi paralelos (≤ `PARALELO_DEG`) que corren uno al
    lado del otro (se solapan a lo largo ≥ `SOLAPE_MIN_FT`) sin cruzarse; la distancia entre bordes descuenta
    medio diámetro de cada una (entre ejes, no).
  • En el cruce (REVISAR «Separación vertical…», «Por encima…», «Por debajo…»): donde se cruzan en planta, con la
    cota de cada una en ese punto (solera + alto interior). Sin cotas en alguna de las dos: no se mide.
  • CON UTILIDAD = CUALQUIERA: cualquier OTRA utilidad (otra capa). Con la misma utilidad, dos tuberías que se
    tocan (unidas) no cuentan. Las conexiones verticales aprobadas tampoco.
  • Un aviso por pareja (tubería, otra tubería, regla): el peor punto.

Para no recorrer todo con todo, los tramos de las otras utilidades van en una rejilla (`_Rejilla`).
"""
from __future__ import annotations

import math

from nucleo import model_ops
from nucleo import normas_catalogo as nc
from nucleo import normas_reglas as NR
from nucleo import normas_validar as V
from traduccion.i18n_core import t

PARALELO_DEG = 20.0
SOLAPE_MIN_FT = 1.0
HORIZONTAL = ("sep_h", "sep_h_ejes")
VERTICAL = ("sep_v", "encima", "debajo")


class _Rejilla:
    def __init__(self, tramos, celda):
        self.tramos, self.celda, self.celdas = tramos, max(celda, 1.0), {}
        for k, (_j, _s, a, b) in enumerate(tramos):
            for c in self._celdas(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])):
                self.celdas.setdefault(c, []).append(k)

    def _celdas(self, x0, y0, x1, y1):
        c = self.celda
        return [(cx, cy) for cx in range(math.floor(x0 / c), math.floor(x1 / c) + 1)
                for cy in range(math.floor(y0 / c), math.floor(y1 / c) + 1)]

    def cerca(self, a, b, r):
        vistos = set()
        for c in self._celdas(min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r):
            for k in self.celdas.get(c, ()):
                if k not in vistos:
                    vistos.add(k)
                    yield self.tramos[k]


def _tramos(pipes, indices):
    out = []
    for j in indices:
        pts = pipes[j].get("pts") or []
        out += [(j, s, pts[s], pts[s + 1]) for s in range(len(pts) - 1)]
    return out


def _dist_pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    q = (a[0] + dx * u, a[1] + dy * u)
    return math.dist(p, q), q


def _cruce(a, b, c, d):
    r = (b[0] - a[0], b[1] - a[1]); s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    u = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    w = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if -1e-9 <= u <= 1 + 1e-9 and -1e-9 <= w <= 1 + 1e-9:
        return a[0] + r[0] * u, a[1] + r[1] * u
    return None


def _paralelos(a, b, c, d, ft_px):
    """Distancia (px) y punto en a–b si los tramos van uno al lado del otro; si no, None."""
    ua, uc = math.atan2(b[1] - a[1], b[0] - a[0]), math.atan2(d[1] - c[1], d[0] - c[0])
    dif = abs((ua - uc + math.pi / 2) % math.pi - math.pi / 2)
    if math.degrees(dif) > PARALELO_DEG or _cruce(a, b, c, d) is not None:
        return None
    L = math.dist(a, b)
    if L < 1e-9:
        return None
    ex, ey = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    t0, t1 = sorted(((c[0] - a[0]) * ex + (c[1] - a[1]) * ey, (d[0] - a[0]) * ex + (d[1] - a[1]) * ey))
    if (min(L, t1) - max(0.0, t0)) * ft_px < SOLAPE_MIN_FT:
        return None
    mejor = None
    for p, (q0, q1), de_cd in ((a, (c, d), False), (b, (c, d), False), (c, (a, b), True), (d, (a, b), True)):
        dist, q = _dist_pt_seg(p, q0, q1)
        en_ab = q if de_cd else p
        if mejor is None or dist < mejor[0]:
            mejor = (dist, en_ab)
    return mejor


UNIDAS_FT = 0.1                    # una punta a menos de esto de la otra tubería = unidas


def _unidas(pa, pb, tol):
    """¿Dos tuberías de la misma utilidad se tocan (una punta sobre la otra, a ≤ tol px)?"""
    for p, q in ((pa, pb), (pb, pa)):
        qp = q.get("pts") or []
        for v in (p["pts"][0], p["pts"][-1]):
            if any(_dist_pt_seg(v, x, y)[0] <= tol for x, y in zip(qp, qp[1:])):
                return True
    return False


def _nombre(pipes, j):
    p = pipes[j]
    nombre = (p.get("name") or "").strip()
    return f"{p.get('layer') or ''} #{j + 1}" + (f" ({nombre})" if nombre else "")


def _alto(p):
    return model_ops.alto_interior_ft(p)


def _ancho(p):
    return model_ops.diametro(p)[0] / 12.0


def revisar(por_util, pipes, todos, ft_px, conexiones, out):
    if not ft_px:
        return
    unidas_cache = {}
    excluir = set()
    for c in conexiones or ():
        try:
            excluir.add(frozenset((int(c["pipe_a"]), int(c["pipe_b"]))))
        except (KeyError, TypeError, ValueError):
            pass
    por_capa = {}
    for dt in todos:
        if dt is not None:
            por_capa.setdefault(nc.clave(dt.p.get("layer")), []).append(dt)
    for u, reglas in por_util.items():
        red = [r for r in reglas if NR.POR_CLAVE[r["revisar"]].con or r["revisar"] == "llega_menos"]
        if u not in por_capa or not red:
            continue
        for grupo in V.agrupar(red):
            r0 = grupo[0]
            otros = []
            if r0["revisar"] != "llega_menos":        # primero las otras: sin ellas no hay nada que medir
                cu, ct = r0["con_utilidad"], r0.get("con_tipo")
                capas = [c for c in por_capa if c != u] if cu == NR.CUALQUIERA else [cu] if cu in por_capa else []
                otros = sorted(dt.i for c in capas for dt in por_capa[c] if not ct or dt.tipo == ct)
                if not otros:
                    continue
            duenos = [dt for dt in por_capa[u] if V.aplica(r0, dt)]
            if not duenos:
                continue
            if r0["revisar"] == "llega_menos":
                _llega(grupo, duenos, pipes, por_capa[u], out)
                continue
            req = min((r.get("min") or 0.0) for r in grupo)
            if r0["revisar"] in HORIZONTAL:
                w_max = max(_ancho(pipes[j]) for j in otros) + max(_ancho(dt.p) for dt in duenos)
                radio = (req + w_max) / ft_px
            else:
                radio = model_ops._TOL
            rej = _Rejilla(_tramos(pipes, otros), max(radio * 2, 50.0))
            for dt in duenos:
                _pareja(grupo, dt, pipes, rej, radio, ft_px, excluir, unidas_cache, out)


def _pareja(grupo, dt, pipes, rej, radio, ft_px, excluir, unidas_cache, out):
    i, p, rv = dt.i, dt.p, grupo[0]["revisar"]
    peor = {}
    pts = p["pts"]
    for s in range(len(pts) - 1):
        a, b = pts[s], pts[s + 1]
        for j, sj, c, d in rej.cerca(a, b, radio):
            if j == i or frozenset((i, j)) in excluir:
                continue
            q = pipes[j]
            if nc.clave(q.get("layer")) == nc.clave(p.get("layer")):
                k = (min(i, j), max(i, j))
                if k not in unidas_cache:
                    unidas_cache[k] = _unidas(p, q, UNIDAS_FT / ft_px)
                if unidas_cache[k]:
                    continue
            if rv in HORIZONTAL:
                par = _paralelos(a, b, c, d, ft_px)
                if par is None:
                    continue
                v = par[0] * ft_px - ((_ancho(p) + _ancho(q)) / 2.0 if rv == "sep_h" else 0.0)
                xy = par[1]
            else:
                xy = _cruce(a, b, c, d)
                if xy is None or not (V.tiene_cotas(p) and V.tiene_cotas(q)):
                    continue
                zo, zt = model_ops.z_en_tramo(p, s, *xy), model_ops.z_en_tramo(q, sj, *xy)
                if zo is None or zt is None:
                    continue
                ho, ht = _alto(p), _alto(q)
                v = {"sep_v": max(zo - (zt + ht), zt - (zo + ho)), "encima": zo - (zt + ht),
                     "debajo": zt - (zo + ho)}[rv]
            if not V.cumple_grupo(grupo, v) and (j not in peor or v < peor[j][0]):
                peor[j] = (v, xy)
    for j, (v, xy) in sorted(peor.items()):
        otra = _nombre(pipes, j)
        req = V.requisito_grupo(grupo)
        if rv in HORIZONTAL:
            como = t("entre bordes") if rv == "sep_h" else t("entre ejes")
            msg = t("A {v} de «{otra}» en paralelo ({como}): {req}").format(
                v=V.unidad(rv, max(v, 0.0)), otra=otra, como=como, req=req)
        elif rv == "sep_v":
            msg = t("Cruce con «{otra}»: {v} libres en vertical: {req}").format(
                otra=otra, v=V.unidad(rv, v), req=req)
        elif rv == "encima":
            msg = t("Cruce con «{otra}»: pasa {v} por encima: {req}").format(otra=otra, v=V.unidad(rv, v), req=req)
        else:
            msg = t("Cruce con «{otra}»: pasa {v} por debajo: {req}").format(otra=otra, v=V.unidad(rv, v), req=req)
        out.append(V.aviso(xy[0], xy[1], "separacion", V.con_condiciones(msg, grupo[0]), i, grupo))


def _llega(grupo, duenos, pipes, de_la_capa, out):
    """La tubería que llega (por una punta) a otra de la misma utilidad: diferencia de diámetros."""
    otros = [dt.i for dt in de_la_capa]
    rej = _Rejilla(_tramos(pipes, otros), 50.0)
    tol = model_ops._TOL
    for dt in duenos:
        pts = dt.p["pts"]
        for v in (pts[0], pts[-1]):
            mayor = None
            for j, _s, a, b in rej.cerca(v, v, tol):
                if j != dt.i and _dist_pt_seg(v, a, b)[0] <= tol:
                    d = model_ops.diametro(pipes[j])[0]
                    if mayor is None or d > mayor[1]:
                        mayor = (j, d)
            if mayor is None:
                continue
            dif = mayor[1] - dt.diam
            if V.cumple_grupo(grupo, dif):
                continue
            msg = t("Llega a «{otra}» de {d}: es {v} menor: {req}").format(
                otra=_nombre(pipes, mayor[0]), d=nc.texto_pulgadas(mayor[1]), v=nc.texto_pulgadas(dif),
                req=V.requisito_grupo(grupo))
            out.append(V.aviso(v[0], v[1], "diametro", V.con_condiciones(msg, grupo[0]), dt.i, grupo))
