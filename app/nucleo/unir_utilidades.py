"""Unir varias utilidades en UNA (PURO: sin Qt).

Una utilidad es una sola polilínea, así que solo se unen PUNTA con PUNTA:
  - las puntas a ≤ `TOL_UNION_FT` (0.5 ft, el snap) se empalman en un vértice;
  - un hueco de hasta `HUECO_MAX_FT` se cierra con un tramo recto (la ventana
    lo enseña en la vista previa y pide confirmación);
  - una punta que cae a MITAD de otra seleccionada es un ramal (T): la de paso
    se parte ahí y la unión sigue por las seleccionadas; el trozo que no entra
    queda como utilidad aparte (`unir_ramales.py`);
  - solo utilidades del mismo tipo (capa).
Se encadenan desde la utilidad BASE (la seleccionada; sus datos mandan:
nombre, diámetro, material, familia…); cada una se da vuelta si hace falta.

Datos por vértice/tramo que se conservan: cotas (inv_start/inv_end y
vertex_inv_out/in: en el empalme quedan explícitas la cota de llegada y la de
salida; si no coinciden se congelan antes las interpoladas para que ninguna
cambie), `vertex_kinds`, `fillets` (codos reconocidos) y `seg_edit_enabled`.
Los buzones/cajas/sólidos van por coordenada y no se tocan.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

from traduccion.i18n_core import N_, t
from nucleo import unir_ramales as R
from nucleo.model_ops import migrate_vertex_inv, snapshot_seg_values

TOL_UNION_FT = 0.5
HUECO_MAX_FT = 10.0
VAULT_KINDS = ("vault", "stop")
# Datos de la utilidad (no de su geometría): siempre los de la BASE.
DATOS_BASE = ("name", "diam", "diam_unit", "material", "ab", "pipe_family", "pipe_size",
              "net_type", "unit", "origen", "xdata", "layer")
CAMPOS_COMPARADOS = (("diam", N_("diámetro")), ("material", N_("material")), ("ab", N_("abandonada")),
                     ("pipe_family", N_("familia")), ("pipe_size", N_("tamaño")))


@dataclass
class Empalme:
    x: float
    y: float
    hueco_ft: float = 0.0          # > 0: se cierra con un tramo recto


@dataclass
class Plan:
    ok: bool
    error: str = ""
    pipe: dict = None              # utilidad resultante
    empalmes: list = field(default_factory=list)
    unidas: list = field(default_factory=list)       # índices que se absorben en la base
    avisos: list = field(default_factory=list)       # datos que cambian (ya traducidos)
    sobrantes: list = field(default_factory=list)    # trozos partidos en una T que quedan aparte


def _ints(d):
    return {int(k): float(v) for k, v in (d or {}).items()}


def _tiene_cotas(p):
    return (p.get("inv_start") is not None or p.get("inv_end") is not None
            or bool(p.get("vertex_inv_out")) or bool(p.get("vertex_inv_in")))


def _cotas_extremos(p):
    """(inicio, fin) como los toma el lienzo: None → 0, o el otro extremo."""
    zs, ze = p.get("inv_start"), p.get("inv_end")
    if zs is None:
        zs = 0.0 if ze is None else ze
    if ze is None:
        ze = zs
    return float(zs), float(ze)


def _kinds(p):
    n = len(p.get("pts") or [])
    vk = p.get("vertex_kinds")
    if isinstance(vk, list) and len(vk) == n:
        return list(vk)
    return ["end"] + ["bend"] * max(0, n - 2) + (["end"] if n > 1 else [])


def invertir(p):
    """La misma utilidad recorrida al revés (copia)."""
    q = copy.deepcopy(p)
    pts = q.get("pts") or []
    n = len(pts)
    q["pts"] = list(reversed(pts))
    q["inv_start"], q["inv_end"] = p.get("inv_end"), p.get("inv_start")
    vin, vout = _ints(p.get("vertex_inv_in")), _ints(p.get("vertex_inv_out"))
    if vin or vout:                       # al revés, la cota de llegada pasa a ser la de salida
        q["vertex_inv_out"] = {n - 1 - k: v for k, v in vin.items()}
        q["vertex_inv_in"] = {n - 1 - k: v for k, v in vout.items()}
    if isinstance(p.get("vertex_kinds"), list):
        q["vertex_kinds"] = list(reversed(p["vertex_kinds"]))
    if p.get("fillets"):
        q["fillets"] = {n - 1 - int(k): r for k, r in p["fillets"].items()}
    return q


def _concatenar(a, b, hueco):
    """a + b (a termina donde empieza b, o a `hueco` de distancia)."""
    na = len(a["pts"])
    r = copy.deepcopy(a)
    con_z = _tiene_cotas(a) or _tiene_cotas(b)
    if con_z:
        a_s, a_e = _cotas_extremos(a)
        b_s, b_e = _cotas_extremos(b)
        if abs(a_e - b_s) > 1e-6 or hueco:
            # Las interpoladas de cada una dependían de SU cota final/inicial:
            # se congelan para que el empalme no las mueva.
            for p, zs, ze in ((r, a_s, a_e), (b, b_s, b_e)):
                p["inv_start"], p["inv_end"] = zs, ze
                snapshot_seg_values(p)
    off = na - 1 if not hueco else na
    pts = list(a["pts"]) + list(b["pts"][1:] if not hueco else b["pts"])
    r["pts"] = pts
    if con_z:
        a_s, a_e = _cotas_extremos(r)
        b_s, b_e = _cotas_extremos(b)
        vout, vin = _ints(r.get("vertex_inv_out")), _ints(r.get("vertex_inv_in"))
        for k, v in _ints(b.get("vertex_inv_out")).items():
            vout[k + off] = v
        for k, v in _ints(b.get("vertex_inv_in")).items():
            vin[k + off] = v
        k = na - 1
        vin[k] = a_e                                   # llega la primera
        if hueco:
            vout[k] = a_e                              # el tramo nuevo sale a la cota de a…
            vin[k + 1] = b_s                           # …y llega a la de b
            vout[k + 1] = b_s
        else:
            vout[k] = b_s                              # sale la segunda
        n = len(pts)
        r["vertex_inv_out"] = {i: v for i, v in vout.items() if 0 < i < n - 1}
        r["vertex_inv_in"] = {i: v for i, v in vin.items() if 0 < i < n - 1}
        r["inv_start"], r["inv_end"] = a_s, b_e
    if isinstance(a.get("vertex_kinds"), list) or isinstance(b.get("vertex_kinds"), list):
        ka, kb = _kinds(a), _kinds(b)
        def _union(k):
            return k if k in VAULT_KINDS else "bend"
        if hueco:
            r["vertex_kinds"] = ka[:-1] + [_union(ka[-1]), _union(kb[0])] + kb[1:]
        else:
            junta = ka[-1] if ka[-1] in VAULT_KINDS else kb[0] if kb[0] in VAULT_KINDS else "bend"
            r["vertex_kinds"] = ka[:-1] + [junta] + kb[1:]
    if a.get("fillets") or b.get("fillets"):
        fil = {int(k): v for k, v in (a.get("fillets") or {}).items()}
        for k, v in (b.get("fillets") or {}).items():
            fil[int(k) + off] = v
        r["fillets"] = fil
    if b.get("seg_edit_enabled"):
        r["seg_edit_enabled"] = True
    return r


def _sobre_tramo(q, pts, tol):
    """¿El punto q cae en el INTERIOR de algún tramo de pts (no en sus puntas)?"""
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 <= 1e-12:
            continue
        tt = ((q[0] - ax) * dx + (q[1] - ay) * dy) / L2
        L = math.sqrt(L2)
        if tt * L <= tol or (1 - tt) * L <= tol:
            continue
        if 0 < tt < 1 and math.hypot(ax + dx * tt - q[0], ay + dy * tt - q[1]) <= tol:
            return True
    return False


def planificar(pipes, filas, base, ft_per_px, permitir_hueco=True):
    """Plan para unir las utilidades `filas` en `base` (índice de `pipes`)."""
    if not ft_per_px or ft_per_px <= 0:
        return Plan(False, t("El plano no tiene escala: fija la escala antes de unir utilidades."))
    filas = [i for i in dict.fromkeys(filas) if 0 <= i < len(pipes)]
    if base not in filas:
        filas.insert(0, base)
    if len(filas) < 2:
        return Plan(False, t("Selecciona al menos dos utilidades para unirlas."))
    capa = pipes[base].get("layer")
    for i in filas:
        p = pipes[i]
        if p.get("world") or len(p.get("pts") or []) < 2:
            return Plan(False, t("La utilidad #{n} no se puede unir (no está dibujada en el lienzo).").format(n=i + 1))
        if p.get("layer") != capa:
            return Plan(False, t("La utilidad #{n} es de otro tipo («{a}» y «{b}»): solo se unen utilidades del mismo tipo.").format(
                n=i + 1, a=capa, b=p.get("layer")))
    tol = TOL_UNION_FT / ft_per_px
    hueco_max = HUECO_MAX_FT / ft_per_px

    def _norm(p):
        q = copy.deepcopy(p)
        migrate_vertex_inv(q)
        return q

    piezas, partidas = R.partir_en_tes([(i, _norm(pipes[i])) for i in filas], tol)
    if piezas is None:
        return Plan(False, t("La #{n} se cruza en una T justo sobre un codo: no se puede partir ahí.").format(
            n=partidas + 1))
    if partidas:
        return _plan_con_ramales(pipes, filas, base, ft_per_px, piezas, partidas, tol,
                                 hueco_max if permitir_hueco else tol, _norm(pipes[base]))

    cadena = _norm(pipes[base])
    quedan = [i for i in filas if i != base]
    empalmes, unidas = [], []
    while quedan:
        mejor = None
        for j in quedan:
            pj = pipes[j]["pts"]
            S, E = cadena["pts"][0], cadena["pts"][-1]
            s, e = pj[0], pj[-1]
            for d, lado, rev in ((math.dist(E, s), "fin", False), (math.dist(E, e), "fin", True),
                                 (math.dist(S, e), "ini", False), (math.dist(S, s), "ini", True)):
                if mejor is None or d < mejor[0]:
                    mejor = (d, j, lado, rev)
        d, j, lado, rev = mejor
        if d > tol and (not permitir_hueco or d > hueco_max):
            # ¿Ramal (T)? Una punta sobre el interior de la otra.
            for jj in quedan:
                pj = pipes[jj]["pts"]
                if (any(_sobre_tramo(q, cadena["pts"], tol) for q in (pj[0], pj[-1]))
                        or any(_sobre_tramo(q, pj, tol) for q in (cadena["pts"][0], cadena["pts"][-1]))):
                    return Plan(False, t("La utilidad #{n} termina a mitad de otra: es un ramal (una T), no una "
                                         "continuación. Solo se unen utilidades punta con punta.").format(n=jj + 1))
            return Plan(False, t("La utilidad #{n} no toca a las demás: su punta más cercana está a {d:.2f} ft "
                                 "(se cierran huecos de hasta {m:g} ft).").format(
                n=j + 1, d=d * ft_per_px, m=HUECO_MAX_FT))
        pj = _norm(pipes[j])
        hueco = d > tol
        if lado == "fin":
            pj = invertir(pj) if rev else pj
            punto = cadena["pts"][-1]
            cadena = _concatenar(cadena, pj, hueco)
        else:
            # La punta inicial de la cadena toca el FIN de pj (o su inicio: al revés).
            previa = invertir(pj) if rev else pj
            punto = cadena["pts"][0]
            datos_base = {k: cadena.get(k) for k in DATOS_BASE}
            cadena = _concatenar(previa, cadena, hueco)
            for k, v in datos_base.items():                # los datos de la base mandan
                if v is None:
                    cadena.pop(k, None)
                else:
                    cadena[k] = v
        empalmes.append(Empalme(punto[0], punto[1], d * ft_per_px if hueco else 0.0))
        unidas.append(j)
        quedan.remove(j)

    return Plan(True, pipe=cadena, empalmes=empalmes, unidas=unidas, avisos=_avisos(pipes, unidas, base))


def _avisos(pipes, unidas, base):
    avisos = []
    pb = pipes[base]
    for i in unidas:
        for clave, nombre in CAMPOS_COMPARADOS:
            if pipes[i].get(clave) not in (None, "") and pipes[i].get(clave) != pb.get(clave):
                avisos.append(t("#{n}: {campo} «{v}» → «{w}» (como la #{b}).").format(
                    n=i + 1, campo=t(nombre), v=_fmt(pipes[i].get(clave)), b=base + 1, w=_fmt(pb.get(clave))))
    return avisos


def _plan_con_ramales(pipes, filas, base, ft_per_px, piezas, partidas, tol, hueco_max, datos_base):
    """Unión con ramales: las partidas en su T ya están en `piezas`; se toma el
    recorrido que pasa por todas y los trozos que sobran quedan aparte."""
    camino, faltan = R.mejor_recorrido(piezas, tol, hueco_max)
    if faltan:
        return Plan(False, t("Las utilidades seleccionadas se ramifican y no caben en una sola línea: "
                             "quedaría fuera la #{n}. Únelas por partes.").format(
            n=", #".join(str(i + 1) for i in faltan)))

    def orientada(i, rev):
        p = piezas[i][1]
        return invertir(p) if rev else copy.deepcopy(p)

    i0, r0, _h = camino[0]
    cadena = orientada(i0, r0)
    empalmes = []
    for i, rev, h in camino[1:]:
        punto = cadena["pts"][-1]
        cadena = _concatenar(cadena, orientada(i, rev), h > 0)
        empalmes.append(Empalme(punto[0], punto[1], h * ft_per_px))
    for k in DATOS_BASE:                                   # los datos de la base mandan
        if datos_base.get(k) is None:
            cadena.pop(k, None)
        else:
            cadena[k] = copy.deepcopy(datos_base[k])
    en_camino = {i for i, _r, _h in camino}
    sobrantes = [p for k, (_o, p) in enumerate(piezas) if k not in en_camino]
    unidas = [i for i in filas if i != base]
    avisos = [t("La #{n} se parte en la T: el trozo que no entra queda como utilidad aparte.").format(n=o + 1)
              for o in sorted(partidas)]
    return Plan(True, pipe=cadena, empalmes=empalmes, unidas=unidas,
                avisos=avisos + _avisos(pipes, unidas, base), sobrantes=sobrantes)


def _fmt(v):
    if isinstance(v, bool):
        return t("sí") if v else t("no")
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)
