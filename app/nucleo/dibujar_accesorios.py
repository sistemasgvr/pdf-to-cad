"""Dibujar accesorios en redes a PRESIÓN (agua y gas), pedido del usuario 2026-11-06: «Dibujar → Accesorios»
(codo, Tee, Wye, cruz; la válvula sigue en `nucleo/valvulas`). PURO (sin Qt).

En la app un accesorio NO es un objeto aparte: sale de la forma de las tuberías (`accesorios.accesorios`, lo mismo
que hace el plugin). Por eso «dibujar un accesorio» = dibujar la forma que lo produce, ya validada:

  - CODO: desde la PUNTA LIBRE de una tubería, un tramo nuevo que gira el ángulo elegido (11.25°, 22.5°, 45° o
    90°, los de los codos AWWA). La tubería se alarga (mismo dato, misma red).
  - TEE: sobre un TRAMO RECTO, un ramal nuevo a 90°.
  - WYE: sobre un tramo recto, un ramal nuevo a 45° (hacia adelante o atrás, a un lado u otro).
  - CRUZ: sobre un tramo recto, una tubería nueva que lo cruza a 90° (sale a los dos lados).

Paso 1 = dónde (`punta` para el codo, `en_tramo` para los demás); paso 2 = hacia dónde y cuánto (`propuesta`, con el
cursor). La forma se valida: solo agua y gas, tramo recto con sitio para el cuerpo del accesorio (lejos de vértices,
curvas, otras uniones y válvulas, como la válvula), tramo nuevo de largo mínimo, sin tocar otra tubería de la MISMA
red (ahí saldría otro accesorio) y el ángulo exacto. Lo que dicen las normativas va como aviso (no bloquea: la app
nunca bloquea por normativa). El ramal nuevo es una copia de los datos de la principal (capa, red, diámetro,
familia, material, tipo) con su cota en ese punto: así queda en la misma red y a la misma cota (si no, no se uniría).
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

from nucleo import accesorios as A
from nucleo import model_ops
from nucleo import valvulas as V
from traduccion.i18n_core import t as _tr

TIPOS = ("codo", "tee", "wye", "cruz")
ANGULOS_CODO = (11.25, 22.5, 45.0, 90.0)
ANGULO = {"tee": 90.0, "wye": 45.0, "cruz": 90.0}
NOMBRE = {"codo": "Codo", "tee": "Tee", "wye": "Wye", "cruz": "Cruz"}
# Datos POR VÉRTICE de la principal que no pasan al ramal nuevo (es otra polilínea).
_NO_COPIAR = ("pts", "vertex_inv_out", "vertex_inv_in", "vertex_inv", "vertex_kinds", "fillets", "seg_edit_enabled",
              "xdata", "acometida", "diam_plano", "grosor", "review", "world", "letters")


@dataclass
class Base:
    """Paso 1: dónde nace el accesorio."""
    ok: bool = False
    motivo: str = ""
    pipe: int = -1
    tramo: int = -1                # tramo donde nace (codo: el último tramo hacia la punta)
    extremo: str = ""              # codo: "start" | "end"
    x: float = 0.0
    y: float = 0.0
    ux: float = 1.0                # codo: dirección HACIA FUERA de la punta; otros: dirección del tramo
    uy: float = 0.0
    diam_in: float = 0.0
    movida: bool = False


@dataclass
class Propuesta:
    """Paso 2: la forma nueva, validada."""
    ok: bool = False
    motivo: str = ""
    avisos: list = field(default_factory=list)
    tipo: str = ""
    angulo: float = 0.0
    lineas: list = field(default_factory=list)     # [[(x, y), …]] lo nuevo, para la vista previa
    nuevas: list = field(default_factory=list)     # utilidades nuevas (dicts)
    alargar: tuple = ()                             # codo: (pipe, extremo, punto nuevo, cota nueva)
    largo_ft: float = 0.0
    acc: dict = field(default_factory=dict)        # el accesorio que saldrá (como `accesorios.accesorios`)


def alcance_ft(diam_in):
    """Lo que ocupa el cuerpo de un codo/Tee/Wye/cruz a cada lado del nodo (brazo + campana)."""
    return V.ALCANCE_ACC_D * float(diam_in or 0) / 12.0


def largo_min_ft(diam_in):
    """Tramo nuevo más corto que se acepta: el cuerpo del accesorio y 1 ft de tubo libre."""
    return alcance_ft(diam_in) + V.TUBO_MIN_FT


def hay_presion(pipes):
    return any(len(p.get("pts") or ()) >= 2 and V.es_presion(p) for p in pipes or ())


def _todas(pipes):
    return lambda _x, _y, _r: range(len(pipes))


def _cerca_presion(pipes, x, y, r, cerca):
    """(dist, i, k) del tramo de presión más cercano, y (dist, i) del de otra red más cercano."""
    mejor = otra = None
    for i in cerca(x, y, r):
        p = pipes[i]
        pts = p.get("pts") or ()
        for k in range(len(pts) - 1):
            d = V._dist_seg(x, y, pts[k], pts[k + 1])
            if d > r:
                continue
            if V.es_presion(p):
                if mejor is None or d < mejor[0]:
                    mejor = (d, i, k)
            elif otra is None or d < otra[0]:
                otra = (d, i)
    return mejor, otra


def _sin_presion(pipes, otra):
    if otra is not None:
        return _tr("{u} no es de agua ni de gas: los accesorios se dibujan en redes a presión.").format(
            u=model_ops.nombre_por_defecto(pipes[otra[1]], otra[1]))
    return _tr("Acércate a una tubería de agua o gas.")


# ── paso 1 ──────────────────────────────────────────────────────────────────
def punta(pipes, structures, x, y, ft, radio_px, cerca=None):
    """Codo: la punta LIBRE de una tubería de agua o gas más cercana al clic."""
    cerca = cerca or _todas(pipes)
    if not ft or ft <= 0:
        return Base(motivo=_tr("Falta la escala de la hoja."))
    mejor = None
    otra = None
    for i in cerca(x, y, radio_px):
        p = pipes[i]
        pts = p.get("pts") or ()
        if len(pts) < 2:
            continue
        for extremo, q in (("start", pts[0]), ("end", pts[-1])):
            d = math.hypot(q[0] - x, q[1] - y)
            if d > radio_px:
                continue
            if V.es_presion(p):
                if mejor is None or d < mejor[0]:
                    mejor = (d, i, extremo)
            elif otra is None or d < otra[0]:
                otra = (d, i)
    if mejor is None:
        cerca_tramo, otra_t = _cerca_presion(pipes, x, y, radio_px, cerca)
        if cerca_tramo is not None:
            return Base(motivo=_tr("El codo se dibuja desde la PUNTA de la tubería: acércate a uno de sus extremos."))
        return Base(motivo=_sin_presion(pipes, otra or otra_t))
    _d, i, extremo = mejor
    p = pipes[i]
    pts = p["pts"]
    nombre = model_ops.nombre_por_defecto(p, i)
    q, r = (pts[0], pts[1]) if extremo == "start" else (pts[-1], pts[-2])
    k = 0 if extremo == "start" else len(pts) - 2
    tol = A.TOL_UNION_FT / ft
    if V._otras_tocan(pipes, i, q, tol, cerca):
        return Base(pipe=i, motivo=_tr("A la punta de {u} ya llega otra tubería: ahí no va un codo.").format(u=nombre))
    d_in = model_ops.diametro(p)[0]
    _cv, geos = V.limpieza_tramos.curvas(pipes, structures, i, ft)
    _k, a, b = V.limpieza_tramos.rectos(pts, geos)[k]
    L_ft = math.hypot(b[0] - a[0], b[1] - a[1]) * ft
    hace_falta = largo_min_ft(d_in) + (alcance_ft(d_in) if len(pts) > 2 else 0.0)
    if L_ft < hace_falta - 1e-6:
        return Base(pipe=i, motivo=_tr("El último tramo de {u} mide {L} ft: el codo de {d}\" necesita {n} ft "
                                       "rectos.").format(u=nombre, L=f"{L_ft:.1f}", d=f"{d_in:g}",
                                                         n=f"{hace_falta:.1f}"))
    L = math.hypot(q[0] - r[0], q[1] - r[1])
    return Base(ok=True, pipe=i, tramo=k, extremo=extremo, x=float(q[0]), y=float(q[1]),
                ux=(q[0] - r[0]) / L, uy=(q[1] - r[1]) / L, diam_in=d_in)


def en_tramo(pipes, structures, x, y, ft, radio_px, otras_valvulas=(), cerca=None):
    """Tee / Wye / cruz: el punto de un TRAMO RECTO de agua o gas donde cabe el cuerpo del accesorio (se corre
    a lo largo del tramo para caber, como la válvula)."""
    cerca = cerca or _todas(pipes)
    if not ft or ft <= 0:
        return Base(motivo=_tr("Falta la escala de la hoja."))
    mejor, otra = _cerca_presion(pipes, x, y, radio_px, cerca)
    if mejor is None:
        return Base(motivo=_sin_presion(pipes, otra))
    _d, i, k = mejor
    p = pipes[i]
    nombre = model_ops.nombre_por_defecto(p, i)
    d_in = model_ops.diametro(p)[0]
    pts = p["pts"]
    try:
        a, b, L, lo, hi, prohibidos = V._tramo_libre(pipes, structures, i, k, ft, otras_valvulas, cerca, d_in)
    except (IndexError, KeyError):
        return Base(pipe=i, motivo=_tr("No se pudo leer el tramo de {u}.").format(u=nombre))
    if L <= V.EPS or ((b[0] - a[0]) * (pts[k + 1][0] - pts[k][0]) + (b[1] - a[1]) * (pts[k + 1][1] - pts[k][1])) <= 0:
        return Base(pipe=i, motivo=_tr("Ahí {u} va en curva: el accesorio va en un tramo recto.").format(u=nombre))
    medio = alcance_ft(d_in)
    libres = V._intervalos(lo, hi, prohibidos, medio)
    if not libres:
        return Base(pipe=i, motivo=_tr("El tramo recto de {u} mide {L} ft: no cabe el cuerpo del accesorio de "
                                       "{d}\" ({n} ft) lejos de sus vértices, uniones y válvulas.").format(
            u=nombre, L=f"{L:.1f}", d=f"{d_in:g}", n=f"{2 * medio:.1f}"))
    ux, uy = (b[0] - a[0]) / (L / ft), (b[1] - a[1]) / (L / ft)
    s0 = ((x - a[0]) * ux + (y - a[1]) * uy) * ft
    s = min((min(max(s0, i0), i1) for i0, i1 in libres), key=lambda v: abs(v - s0))
    return Base(ok=True, pipe=i, tramo=k, x=a[0] + ux * s / ft, y=a[1] + uy * s / ft, ux=ux, uy=uy, diam_in=d_in,
                movida=abs(s - s0) > V.SOBRE_TOL_FT)


# ── paso 2 ──────────────────────────────────────────────────────────────────
def _rot(ux, uy, grados):
    c, s = math.cos(math.radians(grados)), math.sin(math.radians(grados))
    return ux * c - uy * s, ux * s + uy * c


def _toca_red(pipes, i0, seg, red, tol, cerca, salvo):
    """¿El tramo `seg` toca otra tubería de la misma red (salvo en el punto `salvo`)? Devuelve su índice o -1."""
    (ax, ay), (bx, by) = seg
    L = math.hypot(bx - ax, by - ay)
    if L <= V.EPS:
        return -1
    n = max(2, int(L / max(tol, 1e-6)) + 1)
    muestras = [(ax + (bx - ax) * m / n, ay + (by - ay) * m / n) for m in range(n + 1)]
    muestras = [q for q in muestras if math.hypot(q[0] - salvo[0], q[1] - salvo[1]) > 2 * tol]
    cx, cy = (ax + bx) / 2, (ay + by) / 2
    for j in cerca(cx, cy, L / 2 + tol):
        if j == i0:
            continue
        q = pipes[j]
        if not V.es_presion(q) or A.red_de(q) != red:
            continue
        qp = q.get("pts") or ()
        for c, d in zip(qp, qp[1:]):
            if any(V._dist_seg(m[0], m[1], c, d) <= tol for m in muestras):
                return j
    return -1


def _cruza_otras(pipes, seg, red, cerca):
    """Utilidades de OTRA red que el tramo nuevo cruza (solo aviso: lo revisa el conflicto)."""
    (ax, ay), (bx, by) = seg
    L = math.hypot(bx - ax, by - ay)
    out = []
    for j in cerca((ax + bx) / 2, (ay + by) / 2, L / 2):
        q = pipes[j]
        if V.es_presion(q) and A.red_de(q) == red:
            continue
        qp = q.get("pts") or ()
        if any(V._cruce(seg[0], seg[1], c, d) is not None for c, d in zip(qp, qp[1:])):
            out.append(j)
    return out


def ramal_de(p, pts, z):
    """Utilidad nueva con los datos de la principal `p` (misma red, diámetro, familia…) y los puntos `pts`."""
    q = {k: copy.deepcopy(v) for k, v in p.items() if k not in _NO_COPIAR}
    q["pts"] = [tuple(map(float, v)) for v in pts]
    if z is not None:
        q["inv_start"] = q["inv_end"] = float(z)
    else:
        q.pop("inv_start", None)
        q.pop("inv_end", None)
    return q


def pendiente_codo(s1, angulo):
    """Pendiente del tramo nuevo de un codo (pie por pie en planta) para que, con el tramo que llega a `s1`, el
    codo mida en 3D EXACTO el ángulo elegido (como lo mide `accesorios.clasificar` y el plugin) con ese mismo giro
    en planta. Está entre 0 y `s1` (a 90° es 0: a nivel)."""
    if abs(s1) < 1e-12:
        return 0.0
    c = math.cos(math.radians(angulo))

    def g(s2):
        return (c + s1 * s2) / math.sqrt((1 + s1 * s1) * (1 + s2 * s2)) - c
    lo, hi = 0.0, s1                                     # g(0) ≤ 0 ≤ g(s1)
    for _ in range(80):
        m = (lo + hi) / 2
        if g(m) > 0:
            hi = m
        else:
            lo = m
    return (lo + hi) / 2


def alargar(p, extremo, punto, z_nuevo=None):
    """El codo: la tubería sigue hasta `punto` por su `extremo` ("start" | "end"); el vértice viejo queda
    interior con la MISMA cota y la punta nueva con `z_nuevo` (sin dato: la misma; la propuesta sigue la pendiente
    del tramo que llega, así el codo mide en 3D el ángulo elegido)."""
    pts = list(p["pts"])
    con_cotas = p.get("inv_start") is not None or p.get("inv_end") is not None
    if con_cotas:
        model_ops.snapshot_seg_values(p)
    vout = {int(k): v for k, v in (p.get("vertex_inv_out") or {}).items()}
    vin = {int(k): v for k, v in (p.get("vertex_inv_in") or {}).items()}
    q = (float(punto[0]), float(punto[1]))
    if extremo == "end":
        viejo = len(pts) - 1
        if con_cotas:
            z = float(p.get("inv_end") or 0.0)
            vout[viejo] = vin[viejo] = z
            if z_nuevo is not None:
                p["inv_end"] = float(z_nuevo)
        p["pts"] = pts + [q]
    else:
        vout = {k + 1: v for k, v in vout.items()}
        vin = {k + 1: v for k, v in vin.items()}
        if con_cotas:
            z = float(p.get("inv_start") or 0.0)
            vout[1] = vin[1] = z
            if z_nuevo is not None:
                p["inv_start"] = float(z_nuevo)
        p["pts"] = [q] + pts
        if isinstance(p.get("vertex_kinds"), list):
            p["vertex_kinds"] = ["end"] + list(p["vertex_kinds"])
        if p.get("fillets"):
            p["fillets"] = {int(k) + 1: r for k, r in p["fillets"].items()}
    if extremo == "end" and isinstance(p.get("vertex_kinds"), list):
        p["vertex_kinds"] = list(p["vertex_kinds"]) + ["end"]
    if con_cotas:
        p["vertex_inv_out"], p["vertex_inv_in"] = vout, vin
    return p


def propuesta(tipo, base, cx, cy, pipes, ft, angulo=None, cerca=None, normas=None):
    """La forma del accesorio `tipo` desde `base` (paso 1) con el cursor en (cx, cy). `angulo` = el del codo.
    `normas` = las reglas activas (`normas_validar.activas(cat)`) para avisar lo que dicen de este accesorio."""
    cerca = cerca or _todas(pipes)
    pr = Propuesta(tipo=tipo, angulo=float(angulo if tipo == "codo" else ANGULO.get(tipo, 0.0)))
    if not base.ok or not (0 <= base.pipe < len(pipes)) or not ft:
        pr.motivo = base.motivo or _tr("Elige primero dónde va el accesorio.")
        return pr
    p = pipes[base.pipe]
    P = (base.x, base.y)
    ux, uy = base.ux, base.uy
    nx, ny = -uy, ux
    vx, vy = cx - P[0], cy - P[1]
    lado = 1.0 if vx * nx + vy * ny >= 0 else -1.0
    if tipo == "codo":
        if pr.angulo not in ANGULOS_CODO:
            pr.motivo = _tr("Ángulo de codo no válido.")
            return pr
        d = _rot(ux, uy, lado * pr.angulo)
    elif tipo == "tee" or tipo == "cruz":
        d = (nx * lado, ny * lado)
    elif tipo == "wye":
        adelante = 1.0 if vx * ux + vy * uy >= 0 else -1.0
        d = _rot(ux * adelante, uy * adelante, lado * adelante * 45.0)
    else:
        pr.motivo = _tr("Accesorio desconocido.")
        return pr
    L_px = abs(vx * d[0] + vy * d[1]) if tipo == "cruz" else max(0.0, vx * d[0] + vy * d[1])
    L_min = largo_min_ft(base.diam_in)
    pr.largo_ft = L_px * ft
    corto = pr.largo_ft < L_min - 1e-6
    L_px = max(L_px, L_min / ft)
    pr.largo_ft = max(pr.largo_ft, L_min)
    Q = (P[0] + d[0] * L_px, P[1] + d[1] * L_px)
    if tipo == "cruz":
        Q0 = (P[0] - d[0] * L_px, P[1] - d[1] * L_px)
        tramos = [(Q0, P), (P, Q)]
        pr.lineas = [[Q0, Q]]
    else:
        tramos = [(P, Q)]
        pr.lineas = [[P, Q]]
    nombre = model_ops.nombre_por_defecto(p, base.pipe)
    red = A.red_de(p)
    tol = A.TOL_UNION_FT / ft
    if corto:
        pr.motivo = _tr("Muy corto: el tramo nuevo debe medir al menos {n} ft (el cuerpo del accesorio y 1 ft de "
                        "tubo). Aleja el cursor.").format(n=f"{L_min:.1f}")
        return pr
    for seg in tramos:
        j = _toca_red(pipes, base.pipe, seg, red, tol, cerca, P)
        if j >= 0:
            pr.motivo = _tr("El tramo nuevo toca {u} (misma red): ahí saldría otro accesorio.").format(
                u=model_ops.nombre_por_defecto(pipes[j], j))
            return pr
    otras = sorted({j for seg in tramos for j in _cruza_otras(pipes, seg, red, cerca)})
    for j in otras[:3]:
        pr.avisos.append(_tr("Cruza {u}: revisa el conflicto.").format(u=model_ops.nombre_por_defecto(pipes[j], j)))
    z = model_ops.z_en_tramo(p, base.tramo, *P) if base.tramo >= 0 else None
    nuevo = len(pipes)
    if tipo == "codo":
        pts = p["pts"]
        ant = pts[1] if base.extremo == "start" else pts[-2]
        z_ant = model_ops.z_en_tramo(p, base.tramo, *ant)
        z_nuevo = None
        if z is not None and z_ant is not None:
            L_ant = math.hypot(P[0] - ant[0], P[1] - ant[1]) * ft
            s1 = (z - z_ant) / L_ant if L_ant > 1e-9 else 0.0
            z_nuevo = z + pendiente_codo(s1, pr.angulo) * pr.largo_ft
        pr.alargar = (base.pipe, base.extremo, Q, z_nuevo)
        ids = [base.pipe]
    elif tipo == "cruz":
        pr.nuevas = [ramal_de(p, [tramos[0][0], Q], z)]
        ids = sorted({base.pipe, nuevo})
    else:
        pr.nuevas = [ramal_de(p, [P, Q], z)]
        ids = sorted({base.pipe, nuevo})
    pr.acc = {"x": P[0], "y": P[1], "tipo": tipo, "angulo": pr.angulo, "capa": p.get("layer") or "", "red": red,
              "pipes": ids}
    if tipo in ("tee", "wye"):
        pr.acc["tronco"] = [base.pipe]
        pr.acc["ramal"] = nuevo
    if normas:
        pr.avisos += avisos_normativa(normas, pipes, pr)
    pr.ok = True
    return pr


def avisos_normativa(normas, pipes, pr):
    """Lo que dicen las normativas de la app de este accesorio (textos). Nunca bloquea."""
    from nucleo import normas_validar_acc
    tmp = list(pipes) + list(pr.nuevas)
    out = []
    try:
        normas_validar_acc.revisar(normas, tmp, [], pr.acc, out)
    except Exception:                                   # una regla rara no impide dibujar
        return []
    return [_tr("Normativa: {m}").format(m=a.mensaje) for a in out]


def aplicar(pipes, pr):
    """Pone la forma en `pipes` (en sitio). Devuelve los índices de las utilidades nuevas o alargadas."""
    if not pr.ok:
        return []
    if pr.alargar:
        i, extremo, Q, z_nuevo = pr.alargar
        alargar(pipes[i], extremo, Q, z_nuevo)
        return [i]
    n = len(pipes)
    pipes.extend(pr.nuevas)
    return list(range(n, len(pipes)))
