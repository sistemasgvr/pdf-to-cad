"""Limpieza del dibujo antes de exportar (PURO: sin Qt).

Pedido del usuario 2026-10-08 (cliente ferroviario: lo que cuenta es el tiempo de
modelado en Civil 3D). Arregla lo que en Civil 3D sale como basura o hay que corregir
a mano:

  • tramo recto diminuto (< 1 ft): una tubería diminuta en Civil 3D. Ver
    `limpieza_tramos` (quitar el vértice que sobra, o que la curva vecina arranque
    justo en el vértice).
  • puntas casi unidas: el extremo libre de una utilidad a ≤1 ft de otra del mismo
    tipo y estado se lleva EXACTO a su vértice (o, si no hay, a su línea). El plugin
    solo junta en una red lo que está a ≤0.5 ft. Nunca de costado contra una línea
    paralela (bancos de líneas juntas).
  • utilidades sobrantes: más cortas que 1 ft, o repetidas (misma geometría).
  • aviso, sin tocar: utilidades cortas (<5 ft) que no tocan ninguna otra de su tipo.

`ft_per_px` = escala/zoom de la ventana (pies por px del lienzo). Las utilidades a
borrar NO se borran aquí: las borra la ventana (`_delete_pipes`) para correr los
índices de bancoductos y conexiones.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from nucleo import limpieza_tramos as LT
from nucleo import model_ops, xdata
from nucleo.limpieza_tramos import Cambio, TRAMO_MIN_FT  # noqa: F401  (API pública)

PUNTA_MAX_FT = 1.0          # extremo a esta distancia de otra del mismo tipo: se une
UNIDA_FT = 0.01             # ya unidas
LATERAL_FT = 0.1            # la punta se mueve por su propia recta (T, continuación)
LATERAL_PARALELA_FT = 0.25  # continuación casi alineada con una paralela (no de costado)
UTILIDAD_MIN_FT = 1.0       # utilidad entera más corta: sobra
SUELTA_MAX_FT = 5.0         # aviso: corta y sin tocar ninguna otra de su tipo
DUPLICADA_FT = 0.05         # vértice a vértice: la misma utilidad dos veces
CONTACTO_FT = 0.5           # RedesUnidasPorContacto del plugin

ARREGLABLES = ("tramo", "punta", "corta", "duplicada")
TIPOS = ARREGLABLES + ("suelta",)


@dataclass
class Resultado:
    cambios: list = field(default_factory=list)
    borrar: list = field(default_factory=list)

    def de(self, tipo, arreglado=True):
        return [c for c in self.cambios if c.tipo == tipo and c.arreglado == arreglado]

    @property
    def arreglos(self):
        return [c for c in self.cambios if c.arreglado]

    @property
    def avisos(self):
        return [c for c in self.cambios if not c.arreglado]


def limpiar(pipes, structures, ft_per_px, tipos=TIPOS, protegidas=()):
    """Arregla EN SITIO (`pipes`, `structures`) lo de `tipos` y devuelve qué se hizo,
    qué queda como aviso y qué utilidades borrar. `protegidas` (con bancoducto o
    conexión vertical) nunca se proponen para borrar."""
    res = Resultado()
    if not ft_per_px or ft_per_px <= 0:
        return res
    tipos = set(tipos)
    protegidas = set(protegidas)
    if "duplicada" in tipos:
        _duplicadas(pipes, ft_per_px, protegidas, res)
    if "corta" in tipos:
        for i in _vivas(pipes, res.borrar):
            largo = _largo(pipes[i]["pts"]) * ft_per_px
            if largo < UTILIDAD_MIN_FT and i not in protegidas:
                x, y = _medio(pipes[i]["pts"])
                res.borrar.append(i)
                res.cambios.append(Cambio("corta", i, x, y, largo, True, "borrar"))
    if "punta" in tipos:
        _unir_puntas(pipes, structures, ft_per_px, res)
    if "tramo" in tipos:
        for i in _vivas(pipes, res.borrar):
            res.cambios.extend(LT.arreglar(pipes, structures, i, ft_per_px))
    if "suelta" in tipos:
        _sueltas(pipes, ft_per_px, res)
    res.borrar.sort()
    return res


def _vivas(pipes, borrar=()):
    return [i for i, p in enumerate(pipes)
            if i not in borrar and not p.get("world") and len(p.get("pts") or []) >= 2]


def _largo(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _medio(pts):
    """Punto a mitad del recorrido (para ir a verlo)."""
    falta = _largo(pts) / 2.0
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        if L >= falta and L > 0:
            t = falta / L
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        falta -= L
    return tuple(pts[0])


# ─────────────────────────── utilidades sobrantes ───────────────────────────

def _peso(p, i, protegidas):
    """Cuál de dos repetidas se queda: la protegida, la que tiene más datos y, a
    igualdad, la primera de la lista."""
    return (i in protegidas, bool(p.get("pipe_size")), bool(p.get("pipe_family")),
            bool((p.get("name") or "").strip()), bool(xdata.get(p)[xdata.USER]), -i)


def _duplicadas(pipes, ft, protegidas, res):
    tol = DUPLICADA_FT / ft
    vivas = _vivas(pipes)
    for a_pos, a in enumerate(vivas):
        if a in res.borrar:
            continue
        pa = pipes[a]["pts"]
        for b in vivas[a_pos + 1:]:
            if b in res.borrar or pipes[b].get("layer") != pipes[a].get("layer"):
                continue
            pb = pipes[b]["pts"]
            if len(pa) != len(pb):
                continue
            if not (all(math.dist(u, v) <= tol for u, v in zip(pa, pb))
                    or all(math.dist(u, v) <= tol for u, v in zip(pa, reversed(pb)))):
                continue
            sale = min((a, b), key=lambda k: _peso(pipes[k], k, protegidas))
            if sale in protegidas:
                continue
            x, y = _medio(pipes[sale]["pts"])
            res.borrar.append(sale)
            res.cambios.append(Cambio("duplicada", sale, x, y, _largo(pipes[sale]["pts"]) * ft, True, "borrar"))
            if sale == a:
                break


# ─────────────────────────── puntas casi unidas ───────────────────────────

def _rumbos_en(pts, q, tol):
    """Rumbos (unitarios) de los tramos de pts que pasan por q."""
    out = []
    for a, b in zip(pts, pts[1:]):
        if math.dist(q, LT.proyeccion(q, a, b)[0]) <= tol:
            u = LT.unit(a, b)
            if u:
                out.append(u)
    return out


def _destino_valido(q, vecino, dest, rumbos_dest, ft):
    """La punta se mueve por su propia recta (T, continuación, se pasó de largo) o
    hacia una línea que la cruza; nunca de costado contra una paralela (dos líneas
    juntas de un banco). Contra una paralela solo vale la continuación casi alineada:
    el destino ADELANTE, con un desfase lateral chico."""
    u = LT.unit(vecino, q)
    m = (dest[0] - q[0], dest[1] - q[1])
    if u is None:
        return False
    lateral = abs(u[0] * m[1] - u[1] * m[0])
    if lateral * ft <= LATERAL_FT:
        return True
    if any(abs(u[0] * t[1] - u[1] * t[0]) < 0.5 for t in rumbos_dest):   # < 30°: paralela
        adelante = u[0] * m[0] + u[1] * m[1]
        return lateral * ft <= LATERAL_PARALELA_FT and adelante >= 2.0 * lateral
    return lateral <= math.sin(math.radians(60.0)) * math.hypot(*m)


def _unir_puntas(pipes, structures, ft, res):
    tol_max, tol_unida = PUNTA_MAX_FT / ft, UNIDA_FT / ft
    vivas = _vivas(pipes, res.borrar)
    for i in vivas:
        p = pipes[i]
        for e in (0, -1):
            pts = p["pts"]
            q = pts[e]
            mismas = [j for j in vivas if j != i and pipes[j].get("layer") == p.get("layer")]
            if any(LT.toca(q, pipes[j]["pts"], tol_unida) for j in mismas):
                continue                                     # ya está unida
            otras = [j for j in mismas if bool(pipes[j].get("ab")) == bool(p.get("ab"))]
            # Primero un VÉRTICE de la otra (extremo o quiebre); si no hay, su línea.
            mejor = None
            for j in otras:
                for v in pipes[j]["pts"]:
                    d = math.dist(q, v)
                    if d <= tol_max and (mejor is None or d < mejor[0]):
                        mejor = (d, (float(v[0]), float(v[1])), j)
            if mejor is None:
                for j in otras:
                    for a, b in zip(pipes[j]["pts"], pipes[j]["pts"][1:]):
                        c, _t = LT.proyeccion(q, a, b)
                        d = math.dist(q, c)
                        if d <= tol_max and (mejor is None or d < mejor[0]):
                            mejor = (d, (float(c[0]), float(c[1])), j)
            if mejor is None:
                continue
            d, dest, j = mejor
            vecino = pts[1] if e == 0 else pts[-2]
            if not _destino_valido(q, vecino, dest, _rumbos_en(pipes[j]["pts"], dest, tol_unida), ft):
                continue                                     # paralela de al lado: no es una unión
            # El tramo propio no puede quedar diminuto ni darse vuelta.
            ida = (q[0] - vecino[0], q[1] - vecino[1])
            nueva = (dest[0] - vecino[0], dest[1] - vecino[1])
            if math.hypot(*nueva) * ft < TRAMO_MIN_FT or ida[0] * nueva[0] + ida[1] * nueva[1] <= 0:
                res.cambios.append(Cambio("punta", i, q[0], q[1], d * ft, False))
                continue
            vi = 0 if e == 0 else len(pts) - 1
            for s in model_ops.structures_at_vertex(pipes, structures, i, vi):
                model_ops.translate_structure(s, dest[0] - q[0], dest[1] - q[1])
            pts[e] = dest
            res.cambios.append(Cambio("punta", i, dest[0], dest[1], d * ft, True, "punta"))


# ─────────────────────────── avisos ───────────────────────────

def _sueltas(pipes, ft, res):
    tol = CONTACTO_FT / ft
    vivas = _vivas(pipes, res.borrar)
    for i in vivas:
        pts = pipes[i]["pts"]
        largo = _largo(pts) * ft
        if not UTILIDAD_MIN_FT <= largo < SUELTA_MAX_FT:
            continue
        mismas = [j for j in vivas if j != i and pipes[j].get("layer") == pipes[i].get("layer")]
        toca = any(LT.toca(q, pipes[j]["pts"], tol) for j in mismas for q in (pts[0], pts[-1]))
        toca = toca or any(LT.toca(q, pts, tol) for j in mismas
                           for q in (pipes[j]["pts"][0], pipes[j]["pts"][-1]))
        if not toca:
            x, y = _medio(pts)
            res.cambios.append(Cambio("suelta", i, x, y, largo, False))
