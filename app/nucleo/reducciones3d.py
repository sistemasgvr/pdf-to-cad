"""Reducciones de presión en 3D como las arma el plugin (`ReduccionSolida.cs`) (PURO).

Pedido del usuario 2026-10-16: dos utilidades de presión de DISTINTO diámetro unidas a la
misma cota no mostraban la reducción (rectas) y el codo con reducción no se veía como en
Civil 3D. Espejo del plugin:

  • Codo reductor (giran): CODO uniforme del diámetro MAYOR (las dos campanas del mayor) +
    REDUCCIÓN que nace donde moriría un tubo del mayor dentro de la campana del codo (`r0`) y
    termina sobre el EJE del tubo chico (`r1`, `LARGO_REDUCCION_D` = 1.25 · D mayor): cono
    D mayor → D menor + campana del menor. El tubo chico muere dentro de esa campana. Si el
    tubo chico no alcanza, queda el codo solo (como el plugin).
  • Unión recta: la misma reducción, desde la junta (eje del tubo grande, con su campana)
    hacia el tubo chico.
"""
from __future__ import annotations

import math

import numpy as np

from nucleo import accesorios3d as A3
from nucleo import mallas3d as M

LARGO_REDUCCION_D = 1.25          # espejo de ReduccionSolida.cs
LARGO_MIN_LIBRE_FT = 0.05


def reduccion(r0, cerca, u, d1, d2, largo_chico, color, ident):
    """Cono desde `r0` (Ø d1) hasta el eje del tubo chico + su campana. `cerca` = eje del tubo
    chico en la junta, `u` = hacia el tubo chico. (malla, recorte desde `cerca` sobre `u`) o
    None si el tubo chico es más corto que lo que necesita la reducción."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    r0, cerca = np.asarray(r0, float), np.asarray(cerca, float)
    s0 = float(np.dot(r0 - cerca, u))
    r1 = cerca + u * (s0 + d1 * LARGO_REDUCCION_D)
    punta = r1 + u * (d2 * A3.LARGO_CAMPANA_D * A3.CALADO_EN_CAMPANA - A3.SOLAPE_EXTRA_FT)
    recorte = float(np.dot(punta - cerca, u))
    if recorte > largo_chico - LARGO_MIN_LIBRE_FT:
        return None
    chico = A3.Brazo(dir=u, d=d2)
    malla = M.juntar([M.tronco(r0, r1, u, d1 / 2.0, d2 / 2.0, color, ident, A3.LADOS),
                      A3._campana(r1, u, chico, color, ident)])
    return malla, recorte


def recta(centro, u, d1, d2, cerca_chico, largo_chico, color, ident):
    """Reducción en una unión RECTA: campana del tubo grande en la junta (hacia −u) + cono
    hacia el chico. (malla, alcance del grande, recorte del chico) o None."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    c = np.asarray(centro, float)
    r = reduccion(c, cerca_chico, u, d1, d2, largo_chico, color, ident)
    if r is None:
        return None
    malla, recorte = r
    grande = A3.Brazo(dir=-u, d=d1)                   # sin cuerpo: solo la campana del grande
    return M.juntar([malla, A3._campana(c, -u, grande, color, ident)]), max(grande.alcance, 0.0), recorte


def codo_reductor(ar, pipes, nodo, centro, chico, d1, d2, ident):
    """Reducción del codo reductor (el codo ya se armó con `chico.d` = d1). Devuelve el recorte
    3D del tubo chico desde la junta, o None (queda el codo solo)."""
    p = pipes[chico.pipe]
    cerca = np.array([*chico.extra["xy"], chico.eje_z])
    largo = largo_hasta_fin(p["pts"], chico.extra["k"], nodo["x"], nodo["y"], *chico.extra["pxy"], ar.ft, chico.dir)
    r = reduccion(np.asarray(centro, float) + chico.dir * chico.alcance, cerca, chico.dir, d1, d2, largo,
                  ar.claro(p.get("layer")), ident)
    if r is None:
        return None
    ar.op.append(r[0])
    return r[1]


def rectas(ar, pipes, rectos, base, direcciones, seccion, diametro_ft, z_en_tramo, tol, id_acc):
    """Reducción en cada unión recta de dos utilidades de DISTINTO diámetro. Devuelve
    (cantidad, {utilidad: cortes}) como `modelo3d._accesorios`."""
    cortes, n = {}, 0
    for r in rectos:
        if len(r.get("pipes") or []) != 2:
            continue
        lados = []
        for i in r["pipes"]:
            p = pipes[i]
            dirs = direcciones(p, r["x"], r["y"], tol)
            if len(dirs) != 1:
                continue
            ux, uy, k = dirs[0]
            alto = seccion(p)[1]
            z = z_en_tramo(p, k, r["x"], r["y"]) + alto / 2.0
            z1 = z_en_tramo(p, k, r["x"] + ux / ar.ft, r["y"] + uy / ar.ft) + alto / 2.0
            u = np.array([ux, -uy, z1 - z])
            lados.append(dict(pipe=i, d=diametro_ft(p), z=z, u=u / np.linalg.norm(u), k=k, pxy=(ux, uy)))
        if len(lados) != 2 or abs(lados[0]["d"] - lados[1]["d"]) < 1e-6:
            continue
        grande, chico = sorted(lados, key=lambda s: -s["d"])
        xy = ar.mundo(r["x"], r["y"], 0)[:2]
        c = np.array([*xy, grande["z"]])
        cerca = np.array([*xy, chico["z"]])
        largo = largo_hasta_fin(pipes[chico["pipe"]]["pts"], chico["k"], r["x"], r["y"], *chico["pxy"], ar.ft,
                                chico["u"])
        n += 1
        ident = base + n
        res = recta(c, chico["u"], grande["d"], chico["d"], cerca, largo, ar.claro(r.get("capa")), ident)
        if res is None:
            n -= 1
            continue
        malla, alc_g, rec_c = res
        ar.op.append(malla)
        fin = cerca + chico["u"] * rec_c
        ar.picks.capsula(tuple(c), tuple(fin), chico["d"] / 2.0 + A3.HOLGURA_FT + A3.PARED_FT, ident)
        for s, alc in ((grande, alc_g), (chico, rec_c)):
            u_mundo = (s["pxy"][0], -s["pxy"][1])
            cortes.setdefault(s["pipe"], []).append((xy, u_mundo, alc * math.hypot(s["u"][0], s["u"][1])))
        ar.registrar(ident, "accesorio", ident - id_acc - 1, [c, fin], acc_tipo="reduccion", angulo=None, capa=r.get("capa"),
                     pipes=list(r["pipes"]), eje_z=float(c[2]), x=r["x"], y=r["y"])
    return n, cortes


def largo_hasta_fin(pts, k, x, y, ux, uy, ft, dir3d):
    """Largo 3D (ft) del tubo desde la junta (x, y) hasta el extremo del tramo k que queda hacia
    (ux, uy) (px del lienzo); `dir3d` = su dirección 3D unitaria (para pasar de planta a 3D)."""
    a, b = pts[k], pts[k + 1]
    fin = b if (b[0] - a[0]) * ux + (b[1] - a[1]) * uy >= 0 else a
    h = math.hypot(dir3d[0], dir3d[1])
    return math.hypot(fin[0] - x, fin[1] - y) * ft / max(h, 1e-9)
