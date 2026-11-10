"""Validaciones del PLANO según el sentido del flujo que indicó el usuario (pedido 2026-11-10: «según ese fluido que
se hagan las validaciones correspondientes»). PURO (sin Qt).

- CONTRAPENDIENTE en gravedad: un tramo (o la parte de un tramo, si el punto de llegada cae dentro) que SUBE hacia
  donde va el fluido → aviso clase «flujo», nivel ERROR, a un cuarto de esa parte (en la mitad va la flecha del
  flujo y la insignia la taparía). Solo en utilidades con cotas y
  con el sentido indicado (`flujo.tiene`): en automático no se avisa nada nuevo.
La caída en los buzones (`normas_validar`, regla «caida») también usa este sentido; el perfil revisa su propia
contrapendiente por paso (`perfil_validar`), así que este aviso no se repite allí.
"""
from __future__ import annotations

import math

from nucleo import flujo as FL, model_ops
from nucleo.model import network_kind
from nucleo.normas_validar import Aviso, tiene_cotas
from traduccion.i18n_core import t

CLASE = "flujo"
PENDIENTE_CERO = 1e-4


def contrapendientes(p, ft_px):
    """[(x, y, tramo, pendiente en %)] de las partes de la utilidad que suben hacia donde va el fluido."""
    if network_kind(p.get("layer") or "") != "gravity" or not FL.tiene(p) or not tiene_cotas(p) or not ft_px:
        return []
    pts = p.get("pts") or []
    out = []
    for k, t0, t1, s in FL.partes(p):
        if not s:
            continue
        c = model_ops.cotas_tramo(p, k)
        if c is None or c[0] is None or c[1] is None:
            continue
        (ax, ay), (bx, by) = pts[k][:2], pts[k + 1][:2]
        largo = math.hypot(bx - ax, by - ay) * ft_px
        if largo <= 1e-9:
            continue
        pend = (c[1] - c[0]) / largo                    # en el sentido de los vértices
        if pend * s > PENDIENTE_CERO:
            tm = t0 + (t1 - t0) * 0.25
            out.append((ax + (bx - ax) * tm, ay + (by - ay) * tm, k, abs(pend) * 100.0))
    return out


def avisos(pipes, ft_px):
    """Un aviso «flujo» (ERROR) por cada parte en contrapendiente de las utilidades con el sentido indicado."""
    out = []
    for i, p in enumerate(pipes or ()):
        if p.get("world"):
            continue
        for x, y, k, pct in contrapendientes(p, ft_px):
            msg = t("Contrapendiente {p} en T{n}: el tramo sube hacia donde va el fluido.").format(
                p=f"{pct:.2f} %", n=k + 1)
            out.append(Aviso(x, y, CLASE, msg, i, nivel="ERROR"))
    return out
