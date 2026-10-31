"""Rehacer en la escena 3D SOLO lo que cambia al editar una utilidad (PURO; pedido del usuario 2026-10-20:
con 16 761 utilidades cada cambio de cota o diámetro rearmaba toda la escena, ~100 s).

Lo que depende de una utilidad `i`: su tubo, los accesorios de sus nodos (codo, Tee, Wye, cruz, reducción,
conexión vertical), el RECORTE de las vecinas en esos nodos y los buzones en sus vértices. Por eso:

  S1 = las editadas + sus vecinas (comparten nodo, se cruzan o tienen una conexión vertical o una curva a
       ≤ `tol` px) → se REEMPLAZAN sus tubos, los accesorios donde participa alguna de S1 y los buzones de
       sus vértices;
  S2 = S1 + las vecinas de S1 → se ARMAN (con `modelo3d.construir`, el mismo código) junto con S1: así cada
       nodo de una de S1 tiene todas sus utilidades y cada vecina se recorta en sus dos extremos como en la
       escena entera.
El resto de la escena no se toca. Mismo origen y suelo que la escena (`construir(origen=, suelo_z=)`):
mismos números que rearmarla entera (lo comprueba `tests/test_vista3d_parche.py`). Los accesorios nuevos
reciben ids libres (los del armado parcial empiezan de nuevo). Avisos y conflictos (vienen del plano) y el
suelo automático quedan como estaban hasta el próximo armado completo.
"""
from __future__ import annotations

import math

import numpy as np

from nucleo import accesorios as acc
from nucleo import instancias3d as I3
from nucleo import modelo3d
from nucleo import verticales3d as V

ID_COL = 10                     # columna del id en un vértice de malla (pos 3, normal 3, color 4, id)
_LIBRE = {"world": True}        # estructura que el armado parcial salta (conserva los índices)


def tolerancia_px(ft):
    """Distancia (px) hasta la que dos utilidades se influyen en 3D: nodos de accesorios, extremos de una
    conexión vertical, la curva que pertenece al vértice más cercano (14 px) y los buzones, con margen."""
    ft = ft or 1.0
    return max(2.0 * 14.0 + 2.0, 2.0 * acc.TOL_UNION_FT / ft + 2.0, 2.0 * V.TOL_EXTREMO_FT / ft + 2.0,
               2.0 * max(1.0, 0.5 / ft) + 2.0)


def _cajas(pipes):
    out = np.full((len(pipes), 4), np.nan)
    for k, p in enumerate(pipes):
        pts = p.get("pts") or []
        if len(pts) >= 2:
            a = np.asarray(pts, float)
            out[k] = (a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max())
    return out


def _segs(p):
    a = np.asarray(p.get("pts") or [], float)
    return (a[:-1], a[1:]) if len(a) >= 2 else (np.zeros((0, 2)), np.zeros((0, 2)))


def _dist_ps(P, A, B):
    """Distancias (len(P) × len(A)) de cada punto a cada segmento AB."""
    d = B - A
    L2 = np.maximum((d * d).sum(axis=1), 1e-18)
    t = np.clip(((P[:, None, :] - A[None]) * d[None]).sum(axis=2) / L2[None], 0.0, 1.0)
    q = A[None] + t[..., None] * d[None]
    return np.sqrt(((P[:, None, :] - q) ** 2).sum(axis=2))


def _cruzan(A1, B1, A2, B2):
    def lado(a, b, c):
        return (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0])
    a1, b1, a2, b2 = A1[:, None], B1[:, None], A2[None], B2[None]
    return ((np.sign(lado(a1, b1, a2)) * np.sign(lado(a1, b1, b2)) < 0)
            & (np.sign(lado(a2, b2, a1)) * np.sign(lado(a2, b2, b1)) < 0)).any()


def _cerca(p, q, tol):
    """¿Algún tramo de p a ≤ tol de algún tramo de q? (la distancia entre dos tramos está en una punta o se
    cruzan)."""
    A1, B1 = _segs(p)
    A2, B2 = _segs(q)
    if not len(A1) or not len(A2):
        return False
    P1 = np.concatenate([A1, B1[-1:]])
    P2 = np.concatenate([A2, B2[-1:]])
    return bool((_dist_ps(P1, A2, B2) <= tol).any() or (_dist_ps(P2, A1, B1) <= tol).any()
                or _cruzan(A1, B1, A2, B2))


def vecinas(pipes, indices, tol, cajas=None, cruces=(), duct_banks=()):
    """Utilidades a ≤ tol (px) de alguna de `indices` (sin ellas), las de sus conexiones verticales y las de
    su mismo bancoducto."""
    cajas = _cajas(pipes) if cajas is None else cajas
    indices = set(indices)
    out = set()
    for i in indices:
        if not (0 <= i < len(pipes)) or np.isnan(cajas[i, 0]):
            continue
        x0, y0, x1, y1 = cajas[i]
        cand = np.nonzero((cajas[:, 0] <= x1 + tol) & (cajas[:, 2] >= x0 - tol)
                          & (cajas[:, 1] <= y1 + tol) & (cajas[:, 3] >= y0 - tol))[0]
        for k in cand.tolist():
            if k not in indices and k not in out and _cerca(pipes[i], pipes[k], tol):
                out.add(k)
    for c in cruces or ():
        par = _par(c)
        if par and par & indices:
            out |= par - indices
    for db in duct_banks or ():
        grupo = set(db.get("pipes") or [])
        if grupo & indices:
            out |= grupo - indices
    return out


def _par(c):
    try:
        return {int(c["pipe_a"]), int(c["pipe_b"])}
    except (KeyError, TypeError, ValueError):
        return None


def _vertices(pipes, indices):
    pts = [q for i in indices for q in (pipes[i].get("pts") or [])]
    return np.asarray(pts, float).reshape(-1, 2)


def _estructuras_cerca(structures, verts, tol):
    if not len(verts):
        return set()
    out = set()
    for j, s in enumerate(structures or ()):
        if s.get("x") is None or s.get("y") is None:
            continue
        d = np.abs(verts - (float(s["x"]), float(s["y"]))).max(axis=1)
        if (d <= tol).any():
            out.add(j)
    return out


def _sin_ids(F, quitar, col):
    if not len(F) or not quitar:
        return F
    return F[~np.isin(F[:, col], np.fromiter(quitar, float))]


def _con_ids(F, dejar, col, mapa):
    if not len(F):
        return F
    F = F[np.isin(F[:, col], np.fromiter(dejar, float))] if dejar else F[:0]
    if mapa and len(F):
        ids = F[:, col].copy()
        for viejo, nuevo in mapa.items():
            ids[F[:, col] == viejo] = nuevo
        F = F.copy()
        F[:, col] = ids
    return F


def _indice_accesorios(escena):
    """({utilidad: ids de sus accesorios}, id de accesorio más alto) de la escena (se arma una vez y el
    parche lo deja al día en la escena nueva)."""
    if getattr(escena, "_acc_de", None) is None:
        acc_de, mx = {}, modelo3d.ID_ACCESORIO
        for ident, o in escena.objetos.items():
            if o["tipo"] == "accesorio":
                mx = max(mx, ident)
                for k in o.get("pipes") or ():
                    acc_de.setdefault(k, set()).add(ident)
        escena._acc_de, escena._max_acc = acc_de, mx
    return escena._acc_de, escena._max_acc


def parche(escena, pipes, structures, ft, cambiadas, colores=None, duct_banks=(), cruces=(), ocultas=(), ver=None,
           cajas=None, sin_accesorio=()):
    """Escena NUEVA = `escena` con las utilidades `cambiadas` (y lo que depende de ellas) rearmadas desde
    `pipes`/`structures` (el modelo YA cambiado). La escena de entrada no se modifica."""
    if escena is None or escena.vacia or not ft:
        return None
    tol = tolerancia_px(ft)
    cajas = _cajas(pipes) if cajas is None else cajas
    cambiadas = {i for i in cambiadas if 0 <= i < len(pipes)}
    s1 = cambiadas | vecinas(pipes, cambiadas, tol, cajas, cruces, duct_banks)
    s2 = s1 | vecinas(pipes, s1, tol, cajas, cruces, duct_banks)
    est = _estructuras_cerca(structures, _vertices(pipes, s1), tol)       # buzones y curvas de S1
    sub_est = [s if j in est else _LIBRE for j, s in enumerate(structures or ())]
    sub_cruces = [c for c in cruces or () if _par(c) and _par(c) <= s2]
    ver = dict(ver or {}, avisos=False)
    sub = modelo3d.construir(pipes, sub_est, ft, colores, duct_banks, sub_cruces, (), (), ocultas, ver,
                             escena.suelo_z, origen=escena.origen, solo=s2, foco=s1, sin_accesorio=sin_accesorio)
    # qué se reemplaza: tubos de S1, accesorios con alguna utilidad de S1, buzones en los vértices de S1
    est1 = {modelo3d.ID_ESTRUCTURA + j + 1 for j in est}
    tubos = {k + 1 for k in s1}
    acc_de, max_acc = _indice_accesorios(escena)
    quitar_acc = set().union(*(acc_de.get(k, ()) for k in s1)) if s1 else set()
    quitar = tubos | est1 | quitar_acc
    nuevos_acc = sorted(ident for ident, o in sub.objetos.items()
                        if o["tipo"] == "accesorio" and set(o.get("pipes") or ()) & s1)
    mapa = {viejo: float(max_acc + 1 + n) for n, viejo in enumerate(nuevos_acc)}
    dejar = (tubos | est1 | set(nuevos_acc)) & (set(sub.objetos) | tubos)

    out = modelo3d.Escena(origen=escena.origen, suelo_z=escena.suelo_z, suelo=escena.suelo,
                          etiquetas=list(escena.etiquetas))
    out.base = np.concatenate([_sin_ids(escena.base, quitar, ID_COL), _con_ids(sub.base, dejar, ID_COL, mapa)])
    out.transparentes = np.concatenate([_sin_ids(escena.transparentes, quitar, ID_COL),
                                        _con_ids(sub.transparentes, dejar, ID_COL, mapa)])
    inst = {}
    vacio = np.zeros((0, I3.CAMPOS_INST), np.float32)
    for clave in set(escena.instancias) | set(sub.instancias):
        F = np.concatenate([_sin_ids(escena.instancias.get(clave, vacio), quitar, I3.ID),
                            _con_ids(sub.instancias.get(clave, vacio), dejar, I3.ID, mapa)])
        if len(F):
            inst[clave] = F if F.dtype == np.float32 else F.astype(np.float32)
    out.instancias = inst
    A, B, R, I = escena.picks if len(escena.picks) else (np.zeros((0, 3)),) * 2 + (np.zeros(0),) * 2
    keep = ~np.isin(I, np.fromiter(quitar, float)) if quitar else np.ones(len(I), bool)
    sA, sB, sR, sI = sub.picks if len(sub.picks) else (np.zeros((0, 3)),) * 2 + (np.zeros(0),) * 2
    take = np.isin(sI, np.fromiter(dejar, float)) if dejar else np.zeros(len(sI), bool)
    sI = sI[take].copy()
    for viejo, nuevo in mapa.items():
        sI[sI == viejo] = nuevo
    out.picks = (np.concatenate([A[keep], sA[take]]), np.concatenate([B[keep], sB[take]]),
                 np.concatenate([R[keep], sR[take]]), np.concatenate([I[keep], sI]))
    objetos = dict(escena.objetos)
    quitados = [objetos.pop(k) for k in quitar if k in objetos]
    agregados = []
    for k, o in sub.objetos.items():
        if k in dejar:
            objetos[int(mapa.get(k, k))] = o
            agregados.append(o)
    out.objetos = objetos
    # índice de accesorios por utilidad, al día (el próximo parche no recorre los 36 mil objetos)
    nuevo_de = {k: set(v) for k, v in acc_de.items()}
    for k in s1:
        nuevo_de.pop(k, None)
    for v in nuevo_de.values():
        v -= quitar_acc
    for viejo in nuevos_acc:
        for k in sub.objetos[viejo].get("pipes") or ():
            nuevo_de.setdefault(k, set()).add(int(mapa[viejo]))
    out._acc_de, out._max_acc = nuevo_de, max([max_acc] + [int(v) for v in mapa.values()])
    rot = [(r, l) for r, l in zip(escena.rotulos, escena.rotulos_largos or [math.nan] * len(escena.rotulos))
           if r[0] not in tubos]
    rot += [(r, l) for r, l in zip(sub.rotulos, sub.rotulos_largos) if r[0] in tubos]
    out.rotulos, out.rotulos_largos = [r for r, _l in rot], [l for _r, l in rot]
    lo, hi = np.asarray(escena.caja[0], float), np.asarray(escena.caja[1], float)
    for o in agregados:                            # la caja solo crece (encuadrar y el radio de la cámara)
        lo, hi = np.minimum(lo, o["caja"][0]), np.maximum(hi, o["caja"][1])
    out.caja = (lo, hi)
    cuentas = dict(escena.cuentas)
    for tipo, clave in (("pipe", "utilidades"), ("struct", "estructuras"), ("accesorio", "accesorios")):
        if clave in cuentas:
            cuentas[clave] += (sum(1 for o in agregados if o["tipo"] == tipo)
                               - sum(1 for o in quitados if o["tipo"] == tipo))
    out.cuentas = cuentas
    out.vecinas = (s1, s2)                          # informativo (pruebas y medición)
    return out

