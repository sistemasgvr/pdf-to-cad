"""Alertas del PERFIL LONGITUDINAL (pedido del usuario 2026-10-31: «validar en el perfil»). PURO (sin Qt).

Junta, sobre las estaciones del recorrido, lo que conviene ver en el perfil:
- los avisos de normativa del plano (`normas_validar.Aviso`, pendientes y aprobados fuera) de las utilidades del
  recorrido, llevados a su estación (pendiente, separación, diámetro, buzones…); la «separación» se pega al cruce
  más cercano;
- el RECUBRIMIENTO en cada nodo con tapa: tapa − corona < el mínimo de su utilidad (`model.COVER_MIN_FT`);
- en gravedad, la CONTRAPENDIENTE (un tramo que baja en el sentido de las estaciones: las estaciones empiezan en la
  solera más baja, así que el agua corre hacia el inicio) y la pendiente nula.
Solo avisa: nada se mueve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from traduccion.i18n_core import t

PENDIENTE_CERO = 1e-4
SIN_PERFIL = {"tipo"}                    # «sin tipo»: tampoco se dibuja en el plano (ruido)
CRUCE_FT = 5.0                           # una «separación» a ≤ esto de un cruce es de ese cruce


@dataclass
class Alerta:
    e: float
    clase: str                           # pendiente | separacion | recubrimiento | contrapendiente | … (las de normas)
    mensaje: str
    nivel: str = "AVISO"                 # ERROR | AVISO
    paso: int = -1                       # índice del paso (o -1)
    nodo: int = -1                       # índice del nodo (o -1)
    cruce: int = -1                      # índice del cruce (o -1)


def _sobre(pasos, x, y, tol_px):
    """(paso, estación) del punto (x, y) proyectado sobre el recorrido, o None si queda lejos."""
    mejor = None
    for i, p in enumerate(pasos):
        dx, dy = p.p1[0] - p.p0[0], p.p1[1] - p.p0[1]
        L2 = dx * dx + dy * dy
        if L2 <= 1e-12:
            continue
        u = max(0.0, min(1.0, ((x - p.p0[0]) * dx + (y - p.p0[1]) * dy) / L2))
        d = math.hypot(p.p0[0] + dx * u - x, p.p0[1] + dy * u - y)
        if d <= tol_px and (mejor is None or d < mejor[0]):
            mejor = (d, i, p.e0 + (p.e1 - p.e0) * u)
    return None if mejor is None else (mejor[1], mejor[2])


def _nodo_en(perfil, e, tol_ft=0.5):
    for k, n in enumerate(perfil.nodos):
        if abs(n.e - e) <= tol_ft:
            return k
    return -1


def validar(perfil, avisos, cover_min_ft, tol_px):
    """Alertas ordenadas por estación. `avisos` = los de normativa del plano; `cover_min_ft` = recubrimiento
    mínimo de la utilidad del recorrido (0/None = no se revisa)."""
    out = []
    pipes = {p.pipe for p in perfil.pasos}
    cruces_pipe = {c.pipe: k for k, c in enumerate(perfil.cruces)}
    for a in avisos or ():
        if getattr(a, "info", False) or getattr(a, "aprobado", None) is not None or a.clase in SIN_PERFIL:
            continue
        if a.pipe not in pipes and a.pipe not in cruces_pipe:
            continue
        r = _sobre(perfil.pasos, a.x, a.y, tol_px)
        if r is None:
            continue
        i, e = r
        al = Alerta(e, a.clase, a.mensaje, getattr(a, "nivel", "AVISO") or "AVISO", paso=i, nodo=_nodo_en(perfil, e))
        if a.clase == "separacion":
            cerca = [(abs(c.e - e), k) for k, c in enumerate(perfil.cruces) if abs(c.e - e) <= CRUCE_FT]
            if cerca:
                al.cruce = min(cerca)[1]
        out.append(al)
    # recubrimiento en los nodos con tapa
    if cover_min_ft:
        for k, n in enumerate(perfil.nodos):
            if n.rim is None:
                continue
            llega = perfil.pasos[k - 1] if k > 0 else None
            sale = perfil.pasos[k] if k < len(perfil.pasos) else None
            coronas = [llega.z1 + llega.alto_ft] if llega else []
            coronas += [sale.z0 + sale.alto_ft] if sale else []
            if not coronas:
                continue
            cov = n.rim - max(coronas)
            if cov < cover_min_ft - 1e-6:
                out.append(Alerta(n.e, "recubrimiento",
                                  t("Recubrimiento {c} ft, menor que el mínimo de {m} ft").format(
                                      c=f"{cov:.2f}", m=f"{cover_min_ft:g}"),
                                  "ERROR" if cov < 0 else "AVISO", nodo=k))
    # gravedad: contrapendiente / pendiente nula
    if perfil.tipo == "gravity":
        for i, p in enumerate(perfil.pasos):
            s = p.pendiente
            if s < -PENDIENTE_CERO:
                out.append(Alerta((p.e0 + p.e1) / 2, "contrapendiente",
                                  t("Contrapendiente {p}: este tramo baja en el sentido del perfil y el agua no corre "
                                    "hacia el inicio").format(p=f"{s * 100:.2f} %"), "ERROR", paso=i))
            elif abs(s) <= PENDIENTE_CERO:
                out.append(Alerta((p.e0 + p.e1) / 2, "pendiente", t("Pendiente nula: el agua no corre"), paso=i))
    out.sort(key=lambda a: a.e)
    return out
