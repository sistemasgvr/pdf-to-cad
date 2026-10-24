"""Soluciones PROPUESTAS para un conflicto C-n (PURO: sin Qt). Pedido del usuario 2026-10-23 («sugerir la solución
de cada conflicto»).

La APP propone y calcula los números; la IA (`ia/soluciones_ia`) solo elige entre las que la app ya VALIDÓ y lo
explica. Cada `Propuesta` es un cambio concreto y reversible del modelo:

  - cruce / choque (dos utilidades a la misma cota): bajar o subir UNA de las dos ENTERA (todas sus cotas, así su
    pendiente no cambia) lo justo para que pasen una sobre otra sin tocarse — y, si las normativas piden una
    separación vertical entre esas dos utilidades, también con esa separación;
  - escalón (la tubería llega y sale de un vértice a cotas distintas): igualar la salida a la llegada o al revés.

Los demás conflictos (5+ tuberías, tramos cortos entre codos…) se arreglan cambiando el dibujo: no hay propuesta
automática, solo la explicación de qué hacer.

Quien valida (`ui/ventana/ventana_soluciones`) aplica cada propuesta a una COPIA y recalcula conflictos y avisos con
el MISMO código del plano; la propuesta vale si el conflicto desaparece y no aparece ningún problema nuevo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from nucleo import edicion3d, model_ops
from nucleo import normas_reglas as NR
from traduccion.i18n_core import t

CON_PROPUESTA = ("cruce", "choque", "escalon")
UNION_Z_TOL = 0.10          # ft: dos puntas de la misma red a esta diferencia estaban unidas (como el plano)


@dataclass
class Propuesta:
    id: str                         # «P1», «P2»…
    accion: str                     # bajar | subir | igualar_salida | igualar_llegada
    pipe: int                       # utilidad que cambia
    codigo: str                     # «AGUA-5»
    texto: str                      # lo que hace, con sus números (lo escribe la app)
    delta_ft: float = 0.0           # bajar/subir
    vertice: int = -1               # escalón
    valor_ft: float | None = None   # escalón: la cota que se pone
    separacion_ft: float = 0.0      # separación libre que deja (cruces)
    resuelve: bool | None = None    # tras validar
    nuevos: list = field(default_factory=list)      # problemas que aparecerían
    otros_resueltos: int = 0        # otros problemas que también desaparecen

    @property
    def valida(self):
        return bool(self.resuelve) and not self.nuevos

    def datos(self):
        """Lo que recibe la IA (sin nada del lienzo)."""
        return {"id": self.id, "accion": self.accion, "utilidad": self.codigo, "texto": self.texto,
                "delta_ft": round(self.delta_ft, 2), "separacion_ft": round(self.separacion_ft, 2),
                "valida": self.valida, "resuelve": bool(self.resuelve),
                "problemas_nuevos": list(self.nuevos), "otros_resueltos": self.otros_resueltos}


def _redondeo(x):
    """Arriba a 0.01 ft (así la separación queda cumplida, no un pelo corta)."""
    return math.copysign(math.ceil(abs(x) * 100.0 - 1e-6) / 100.0, x)


def codigo(pipes, i):
    return model_ops.nombre_por_defecto(pipes[i], i)


def separaciones(normas_cat, capa_a, capa_b):
    """Separaciones verticales en el cruce que piden las normativas entre esas dos utilidades (ft), de menor a
    mayor. Solo se mira utilidad y «con utilidad»: si una regla no aplica por sus condiciones, la validación lo
    dirá (no aparece un aviso nuevo)."""
    out = set()
    for r in (normas_cat or {}).get("reglas") or []:
        if not r.get("activa", True) or r.get("revisar") not in ("sep_v", "encima", "debajo") or r.get("min") is None:
            continue
        u, con = r.get("utilidad"), r.get("con_utilidad")
        if (u == capa_a and con in (capa_b, NR.CUALQUIERA)) or (u == capa_b and con in (capa_a, NR.CUALQUIERA)):
            out.add(float(r["min"]))
    return sorted(out)


def proponer(conflicto, pipes, z_at, normas_cat=None):
    """Las propuestas (sin validar) para `conflicto` (`nucleo.conflictos.Conflicto` + `hit` del plano)."""
    if conflicto.clave in ("cruce", "choque"):
        return _cruce(conflicto, pipes, normas_cat)
    if conflicto.clave == "escalon":
        return _escalon(conflicto, pipes, z_at)
    return []


def _cruce(c, pipes, normas_cat):
    ps = [i for i in c.pipes or [] if i is not None]
    zs = list(c.cotas or [])
    if len(ps) != 2 or len(zs) != 2 or None in zs:
        return []                                   # sin cotas no hay cómo calcular cuánto mover
    (ia, ib), (za, zb) = ps, zs
    ha, hb = model_ops.alto_interior_ft(pipes[ia]), model_ops.alto_interior_ft(pipes[ib])
    seps = [0.0] + separaciones(normas_cat, pipes[ia].get("layer"), pipes[ib].get("layer"))
    props = []
    for mov, zm, hm, otra, zo, ho in ((ia, za, ha, ib, zb, hb), (ib, zb, hb, ia, za, ha)):
        for s in seps:
            bajar = _redondeo((zo - s) - (zm + hm))   # su corona queda s por debajo de la solera de la otra
            subir = _redondeo((zo + ho + s) - zm)     # su solera queda s por encima de la corona de la otra
            for accion, d in (("bajar", bajar), ("subir", subir)):
                if (accion == "bajar" and d >= 0) or (accion == "subir" and d <= 0):
                    continue
                if any(p.pipe == mov and p.accion == accion and abs(p.delta_ft - d) < 0.005 for p in props):
                    continue
                cod, cod_o = codigo(pipes, mov), codigo(pipes, otra)
                txt = (t("Bajar {u} {d} ft (todas sus cotas: la pendiente no cambia) para pasar por debajo de {o}")
                       if accion == "bajar" else
                       t("Subir {u} {d} ft (todas sus cotas: la pendiente no cambia) para pasar por encima de {o}")
                       ).format(u=cod, d=f"{abs(d):.2f}", o=cod_o)
                if s:
                    txt += " " + t("dejando {s} ft libres (normativa)").format(s=f"{s:.2f}")
                props.append(Propuesta("", accion, mov, cod, txt + ".", delta_ft=d, separacion_ft=s))
    return _numerar(props)


def _escalon(c, pipes, z_at):
    ps = [i for i in c.pipes or [] if i is not None]
    if len(ps) != 1 or len(c.cotas or []) != 2 or None in c.cotas:
        return []
    i = ps[0]
    pts = pipes[i].get("pts") or []
    v = min(range(1, len(pts) - 1), default=-1,
            key=lambda k: (pts[k][0] - c.x) ** 2 + (pts[k][1] - c.y) ** 2)
    if v < 0:
        return []
    z_llega, z_sale = c.cotas
    cod = codigo(pipes, i)
    props = [Propuesta("", "igualar_salida", i, cod, t("En {u}, poner la cota de salida del vértice igual a la de "
                                                        "llegada: {z} ft.").format(u=cod, z=f"{z_llega:.2f}"),
                       vertice=v, valor_ft=z_llega),
             Propuesta("", "igualar_llegada", i, cod, t("En {u}, poner la cota de llegada del vértice igual a la de "
                                                         "salida: {z} ft.").format(u=cod, z=f"{z_sale:.2f}"),
                       vertice=v, valor_ft=z_sale)]
    return _numerar(props)


def _numerar(props):
    for k, p in enumerate(props, 1):
        p.id = f"P{k}"
    return props


# ── aplicar ──
def desplazar_cotas(p, delta):
    """Sube (delta > 0) o baja TODAS las cotas de la utilidad `p` (en sitio): mismo perfil, misma pendiente."""
    pts = p.get("pts") or []
    n = len(pts)
    if n < 2:
        return
    tramos = [model_ops.cotas_tramo(p, k) for k in range(n - 1)]
    if n > 2:
        model_ops.snapshot_seg_values(p)
        p["seg_edit_enabled"] = True
        for k in range(1, n - 1):
            p.setdefault("vertex_inv_out", {})[k] = tramos[k][0] + delta
            p.setdefault("vertex_inv_in", {})[k] = tramos[k - 1][1] + delta
    p["inv_start"] = tramos[0][0] + delta
    p["inv_end"] = tramos[-1][1] + delta


def aplicar(pipes, prop):
    """Aplica la propuesta a `pipes` (en sitio)."""
    p = pipes[prop.pipe]
    if prop.accion in ("bajar", "subir"):
        desplazar_cotas(p, prop.delta_ft)
    elif prop.accion == "igualar_salida":
        edicion3d.aplicar_cota(p, prop.vertice, "inicio", prop.valor_ft)
    elif prop.accion == "igualar_llegada":
        edicion3d.aplicar_cota(p, prop.vertice - 1, "fin", prop.valor_ft)


def uniones_rotas(antes, despues, movidas, tol_px):
    """Puntas de la MISMA capa que estaban unidas (misma cota ±`UNION_Z_TOL`) y quedan a cotas distintas por mover
    `movidas`: un cambio de cota que separa la red. [(codigo, codigo)]."""
    def puntas(pipes, i):
        p = pipes[i]
        pts = p.get("pts") or []
        if len(pts) < 2:
            return []
        z0, z1 = model_ops.cotas_tramo(p, 0)[0], model_ops.cotas_tramo(p, len(pts) - 2)[1]
        return [(pts[0], z0), (pts[-1], z1)]
    out = []
    t2 = tol_px * tol_px
    for i in movidas:
        capa = antes[i].get("layer")
        for j in range(len(antes)):
            if j == i or antes[j].get("layer") != capa:
                continue
            for (a, za0), (_a, za1) in zip(puntas(antes, i), puntas(despues, i)):
                for (b, zb0), (_b, zb1) in zip(puntas(antes, j), puntas(despues, j)):
                    if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 > t2:
                        continue
                    if abs(za0 - zb0) <= UNION_Z_TOL < abs(za1 - zb1):
                        out.append((codigo(antes, i), codigo(antes, j)))
    return out
