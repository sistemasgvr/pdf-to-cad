"""Conexiones VERTICALES aprobadas en la Vista 3D, como las construye el plugin (PURO).

Pedido del usuario 2026-10-14: la vista 3D dibujaba solo el tubo vertical, sin sus
accesorios. Espejo de `ImportarRed.CrearConexionesCruzadas` + `ColocarFittingSolido` +
`CrearCruceConWye` (con `FITTING_COMO_SOLIDO` = true):

  • Vertical del diámetro MENOR de las dos utilidades, de boca a boca de sus accesorios.
  • En cada utilidad horizontal (eje = solera + radio): CODO 90° si la utilidad TERMINA
    en el cruce (brazo horizontal hacia el resto de la tubería + brazo vertical) o TEE si
    PASA de largo (dos brazos sobre su tangente + ramal vertical). El tronco lleva el
    diámetro de su utilidad; el ramal, el de la vertical. La horizontal se recorta en su
    campana.
  • Caso Wye: una utilidad PASA con un QUIEBRE (ya lleva su codo) y la otra TERMINA. El
    codo del quiebre pasa a ser una WYE con un ramal hacia la otra, tubo auxiliar de
    `TUBO_AUX_CRUCE_FT`, codo 90°, vertical y codo 90° que entra en la otra utilidad. Si el
    desnivel no alcanza para dos codos de 90°, el ramal de la Wye va directo (inclinado)
    a la utilidad que termina, que sube/baja hasta la Wye.

Se usa en dos pasos desde `modelo3d.construir`: `planear` (antes de los accesorios: dice
qué codo del plano se vuelve Wye y con qué ramal) y `dibujar` (después: piezas, tubos y
recortes de las horizontales).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from nucleo import accesorios3d as A3
from nucleo import mallas3d as M

TOL_EXTREMO_FT = 0.5          # `EsExtremoDePipe`: la utilidad TERMINA en el cruce
TUBO_AUX_CRUCE_FT = 1.0       # `TUBO_AUX_CRUCE_FT` del plugin
DZ_MIN_FT = 0.01              # cotas iguales: no requiere vertical


@dataclass
class Plan:
    c: dict                                   # la conexión aprobada (x, y px, pipe_a/b, z_a/b)
    lo: int                                   # utilidad de abajo / de arriba (índices)
    hi: int
    z_lo: float                               # cota del EJE en el cruce (ft)
    z_hi: float
    d_v: float                                # diámetro de la vertical (ft)
    caso: str = "normal"                      # "normal" | "wye"
    pasa: int = -1                            # caso wye: la que pasa con quiebre / la que termina
    termina: int = -1
    inclinada: bool = False
    d_e: tuple = (0.0, 0.0)                   # en planta (px), hacia el resto de la que termina
    lejos: tuple = (0.0, 0.0, 0.0)            # vértice siguiente de la que termina (px, px, z eje)
    ramal: object = None                      # Brazo del ramal de la Wye (lo llena `_accesorios`)
    centro: object = None                     # centro de la Wye (mundo)
    extra: dict = field(default_factory=dict)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def termina_en(p, x, y, tol_px):
    pts = p.get("pts") or []
    return bool(pts) and min(_dist(pts[0], (x, y)), _dist(pts[-1], (x, y))) <= tol_px


def tangente(p, x, y):
    """Dirección (px, unitaria) del tramo de `p` más cercano a (x, y)."""
    pts = p.get("pts") or []
    mejor = None
    for a, b in zip(pts, pts[1:]):
        L = _dist(a, b)
        if L < 1e-9:
            continue
        t = max(0.0, min(1.0, ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / (L * L)))
        d = _dist((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), (x, y))
        if mejor is None or d < mejor[0]:
            mejor = (d, ((b[0] - a[0]) / L, (b[1] - a[1]) / L))
    return mejor[1] if mejor else (1.0, 0.0)


def alejandose(p, x, y, tol_px):
    """`DireccionAlejandoseDelCruce`: desde el cruce hacia el primer vértice que está
    realmente lejos (un tramito de pocas pulgadas al empezar no cuenta). Devuelve
    (dirección px unitaria, índice de ese vértice) o (tangente, -1)."""
    pts = p.get("pts") or []
    if not pts:
        return (1.0, 0.0), -1
    orden = range(len(pts)) if _dist(pts[0], (x, y)) <= _dist(pts[-1], (x, y)) else range(len(pts) - 1, -1, -1)
    for k in orden:
        d = _dist(pts[k], (x, y))
        if d > tol_px:
            return ((pts[k][0] - x) / d, (pts[k][1] - y) / d), k
    return tangente(p, x, y), -1


def _boca_codo90(d):
    rt = A3.curva_codo(d, math.pi / 2.0)
    T = rt[1] if rt else d
    return T + d * A3.COLLAR_CODO_D + d * A3.LARGO_CAMPANA_D


def planear(pipes, cruces, ft, diametro_ft, z_eje, hay_codo):
    """[Plan] de cada conexión que se puede dibujar. `diametro_ft(p)`; `z_eje(i, x, y)` =
    cota del eje de la utilidad i en ese punto; `hay_codo(i, x, y)` = ¿el plano pone un codo
    de esa utilidad ahí? (el quiebre del caso Wye)."""
    planes = []
    tol = TOL_EXTREMO_FT / ft if ft else 0.0
    for c in cruces or []:
        ia, ib = c.get("pipe_a"), c.get("pipe_b")
        if c.get("z_a") is None or c.get("z_b") is None or not all(
                isinstance(k, int) and 0 <= k < len(pipes) and pipes[k].get("pts") for k in (ia, ib)):
            continue
        za, zb = float(c["z_a"]), float(c["z_b"])
        if abs(za - zb) < DZ_MIN_FT:
            continue
        da, db = diametro_ft(pipes[ia]), diametro_ft(pipes[ib])
        hi, lo = (ia, ib) if za > zb else (ib, ia)
        ejes = {ia: za + da / 2.0, ib: zb + db / 2.0}
        plan = Plan(c=c, lo=lo, hi=hi, z_lo=ejes[lo], z_hi=ejes[hi], d_v=min(da, db))
        x, y = float(c["x"]), float(c["y"])
        t_lo, t_hi = termina_en(pipes[lo], x, y, tol), termina_en(pipes[hi], x, y, tol)
        if t_lo != t_hi:
            pasa, term = (hi, lo) if t_lo else (lo, hi)
            if hay_codo(pasa, x, y):
                d_e, k = alejandose(pipes[term], x, y, tol)
                pts = pipes[term]["pts"]
                q = pts[k] if k >= 0 else (x + d_e[0] / ft, y + d_e[1] / ft)
                z_lejos = z_eje(term, q[0], q[1])
                dz = ejes[term] - ejes[pasa]
                plan.caso, plan.pasa, plan.termina, plan.d_e = "wye", pasa, term, d_e
                plan.lejos = (q[0], q[1], ejes[term] if z_lejos is None else z_lejos)
                plan.inclinada = abs(dz) < 2.0 * _boca_codo90(plan.d_v) + 0.05
        planes.append(plan)
    return planes


def ramal_de(plan, ar, diametro_ft, pipes):
    """Brazo del ramal que `_accesorios` suma al codo del quiebre (que pasa a ser Wye)."""
    d_e = np.array([plan.d_e[0], -plan.d_e[1], 0.0])
    if not plan.inclinada:
        return A3.Brazo(dir=d_e, d=plan.d_v)
    x, y = float(plan.c["x"]), float(plan.c["y"])
    ejes = {plan.lo: plan.z_lo, plan.hi: plan.z_hi}
    cerca = np.array(ar.mundo(x, y, ejes[plan.pasa]))
    lejos = np.array(ar.mundo(*plan.lejos))
    u = lejos - cerca
    n = np.linalg.norm(u)
    u = u / n if n > 1e-9 else d_e
    return A3.Brazo(dir=u, d=diametro_ft(pipes[plan.termina]), pipe=plan.termina,
                    extra=dict(xy=tuple(cerca[:2]), u=(plan.d_e[0], -plan.d_e[1])))


# ─────────────────────────── dibujo ───────────────────────────

class _Dibujo:
    def __init__(self, ar, pipes, id_base, diametro_ft):
        self.ar, self.pipes, self.id, self.diam = ar, pipes, id_base, diametro_ft
        self.cortes, self.ajustes, self.n = {}, {}, 0

    def color(self, i):
        return self.ar.color(self.pipes[i].get("layer"))

    def pieza(self, tipo, centro, brazos, i, x, y, pipes_):
        self.n += 1
        ident = self.id + self.n
        malla, c = A3.pieza(tipo, np.asarray(centro, float), brazos, self.ar.claro(self.pipes[i].get("layer")), ident)
        self.ar.op.append(malla)
        for b in brazos:
            fin = c + b.dir * (b.largo + b.d * A3.LARGO_CAMPANA_D)
            self.ar.picks.capsula(tuple(c), tuple(fin), b.r_campana, ident)
        self.ar.registrar(ident, "accesorio", self.id - _ID_ACC + self.n - 1, [c], acc_tipo=tipo, angulo=90.0,
                          capa=self.pipes[i].get("layer"), pipes=list(pipes_), eje_z=float(c[2]), x=x, y=y,
                          vertical=True)
        return c

    def tubo(self, a, b, d, i, ident):
        a, b = np.asarray(a, float), np.asarray(b, float)
        if np.linalg.norm(b - a) < 1e-3:
            return
        self.ar.op.append(M.barrido(a, b, M.perfil_circulo(d / 2.0, A3.LADOS), self.color(i), ident))
        self.ar.picks.capsula(tuple(a), tuple(b), d / 2.0, ident)

    def corte(self, i, xy, u, alcance):
        self.cortes.setdefault(i, []).append((tuple(xy), tuple(u), max(alcance, 0.0)))


_ID_ACC = 200000              # = modelo3d.ID_ACCESORIO (sin importar modelo3d: evita el ciclo)


def _normal(dib, plan, accesorios_ok):
    ar, pipes = dib.ar, dib.pipes
    x, y = float(plan.c["x"]), float(plan.c["y"])
    tol = TOL_EXTREMO_FT / ar.ft
    bocas = {}
    for i, z, arriba in ((plan.lo, plan.z_lo, True), (plan.hi, plan.z_hi, False)):
        centro = np.array(ar.mundo(x, y, z))
        if not accesorios_ok:
            bocas[i] = (centro, 0.0)
            continue
        p = pipes[i]
        termina = termina_en(p, x, y, tol)
        dh = alejandose(p, x, y, tol)[0] if termina else tangente(p, x, y)
        h = np.array([dh[0], -dh[1], 0.0])
        dv = np.array([0.0, 0.0, 1.0 if arriba else -1.0])
        d = dib.diam(p)
        brazos = [A3.Brazo(dir=h, d=d)] + ([] if termina else [A3.Brazo(dir=-h, d=d)]) + [A3.Brazo(dir=dv, d=plan.d_v)]
        c = dib.pieza("codo" if termina else "tee", centro, brazos, i, x, y, [plan.lo, plan.hi])
        for b in brazos[:-1]:
            dib.corte(i, c[:2], (b.dir[0], b.dir[1]), b.alcance)
        bocas[i] = (c, brazos[-1].alcance)
    (c_lo, a_lo), (c_hi, a_hi) = bocas[plan.lo], bocas[plan.hi]
    dib.tubo(c_lo + [0, 0, a_lo], c_hi - [0, 0, a_hi], plan.d_v, plan.lo, plan.lo + 1)


def _wye(dib, plan):
    """Tubo auxiliar + codo + vertical + codo hacia la utilidad que termina (la Wye ya la
    dibujó `_accesorios` con el ramal de `ramal_de`)."""
    ar, pipes = dib.ar, dib.pipes
    x, y = float(plan.c["x"]), float(plan.c["y"])
    term = plan.termina
    if plan.inclinada:                       # la que termina sube/baja hasta la Wye y entra al ramal
        dib.ajustes.setdefault(term, []).append((tuple(np.asarray(plan.centro)[:2]), float(plan.centro[2])))
        return
    c = np.asarray(plan.centro, float)
    d_e = np.array([plan.d_e[0], -plan.d_e[1], 0.0])
    d, d_otra = plan.d_v, dib.diam(pipes[term])
    boca_ramal = plan.ramal.largo + d * A3.LARGO_CAMPANA_D
    s_v = boca_ramal + TUBO_AUX_CRUCE_FT + _boca_codo90(d)
    v1 = c + d_e * s_v
    ejes = {plan.lo: plan.z_lo, plan.hi: plan.z_hi}
    cerca = np.array(ar.mundo(x, y, ejes[term]))
    lejos = np.array(ar.mundo(*plan.lejos))
    h = float(np.linalg.norm((lejos - cerca)[:2]))
    t = s_v / h if h > 1e-9 else 0.0
    v2 = np.array([v1[0], v1[1], cerca[2] + (lejos[2] - cerca[2]) * t])
    d_v = np.array([0.0, 0.0, 1.0 if v2[2] > v1[2] else -1.0])
    d_e3 = lejos - cerca
    d_e3 = d_e3 / np.linalg.norm(d_e3) if np.linalg.norm(d_e3) > 1e-9 else d_e
    sup = [A3.Brazo(dir=-d_e, d=d), A3.Brazo(dir=d_v, d=d)]
    inf = [A3.Brazo(dir=-d_v, d=d), A3.Brazo(dir=d_e3, d=d_otra)]
    dib.pieza("codo", v1, sup, plan.pasa, x, y, [plan.pasa, term])
    dib.pieza("codo", v2, inf, term, x, y, [plan.pasa, term])
    ident = term + 1
    dib.tubo(c + d_e * plan.ramal.alcance, v1 - d_e * sup[0].alcance, d, term, ident)       # tubo auxiliar
    dib.tubo(v1 + d_v * sup[1].alcance, v2 - d_v * inf[0].alcance, d, term, ident)          # vertical
    horiz = math.hypot(d_e3[0], d_e3[1])
    dib.corte(term, cerca[:2], (d_e[0], d_e[1]), s_v + inf[1].alcance * horiz)                # la otra muere en su codo


def dibujar(ar, pipes, planes, id_base, diametro_ft, accesorios_ok=True):
    """Dibuja las conexiones en `ar`. Devuelve (cortes {utilidad: [(xy, u, alcance)]},
    ajustes {utilidad: [(xy mundo, z del eje)]}, cantidad de accesorios)."""
    dib = _Dibujo(ar, pipes, id_base, diametro_ft)
    for plan in planes:
        if plan.caso == "wye" and accesorios_ok and plan.ramal is not None:
            _wye(dib, plan)
        else:
            _normal(dib, plan, accesorios_ok)
    return dib.cortes, dib.ajustes, dib.n
