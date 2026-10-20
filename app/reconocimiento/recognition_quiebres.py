"""Los quiebres que la IMPORTACIÓN hará curva, para verlos ya en la vista previa (sin Qt).

Regla de los ingenieros (`nucleo/quiebres_curvas`): en eléctrico, telecomunicaciones,
drenaje y alcantarillado cada quiebre del plano entra como curva de radio mínimo. La
vista previa los pintaba como un punto de quiebre (reporte del usuario 2026-10-19, DU06
UD-202: la «—SC—» gira 14° en el hueco de su rótulo y se veía una esquina), aunque al
importar ya eran curva. Aquí se repite, sobre COPIAS, lo que hace
`Main._import_recognized_pipes` con los datos —tuberías del reconocimiento, vértices de
bóveda, acometidas, estructuras, cajas, codos de la tinta y `curvas_en_quiebres`— y se
devuelve el arco de cada curva nueva tal como lo dibuja el editor: lo que se ve es lo
que se importa. Nada del resultado del reconocimiento cambia.
"""
from __future__ import annotations

import copy
import dataclasses
from typing import Dict, Sequence, Tuple

from nucleo import acometidas, model_ops, quiebres_curvas
from nucleo.model import NETWORK_KIND

# marca de un vértice que la importación quita (prácticamente recto junto a un quiebre)
QUITADO = "quitado"


def curvas_de_quiebres(results: Sequence, zoom: float) -> Dict[int, Dict[Tuple[float, float], dict]]:
    """{id(resultado): {(x, y) del vértice: codo}} de los quiebres que serán curva de radio
    mínimo al importar. Codo = el formato de `RecognizedPolyline.fillets` (a, b, center,
    r_px; px del lienzo) + `quiebre`; {QUITADO: True} = vértice prácticamente recto que la
    importación quita para que entre la curva (`dibujo_de`). `zoom` = el del editor (px por
    pt de los resultados)."""
    from reconocimiento import recognition as rec      # perezoso: recognition es pesado
    if not results or not zoom:
        return {}
    pipes, dueño, batches = [], [], []
    for result in results:
        utility = getattr(result, "utility", None) or "ELECTRICO"
        nuevas = rec.pipes_from_recognition(result, layer=utility, zoom=zoom)
        rec.inject_vault_vertices(nuevas, list(getattr(result, "vault_pts", None) or []))
        pipes.extend(nuevas)
        dueño += [id(result)] * len(nuevas)
        batches.append((result, utility))
    acometidas.unir_a_principal(pipes, range(len(pipes)), 0.8 * zoom)
    structures = model_ops.rebuild_structures(pipes, [])
    model_ops.hide_soft_vertex_structures(pipes, structures)
    for result, utility in batches:
        model_ops.attach_vault_geometry(
            structures, copy.deepcopy(getattr(result, "vaults_geo", None) or []),
            net=NETWORK_KIND.get(utility, "conduit"), utility=utility,
            pipes=[p for p in pipes if p.get("layer") == utility])
    model_ops.attach_fillets(pipes, structures)
    escala = getattr(results[0], "scale_ft_per_pt", None) or 0.0
    fpp = escala / zoom if escala else 0.0
    antes = [list(p.get("pts") or ()) for p in pipes]
    nuevas_cv, _sin_lugar = quiebres_curvas.curvas_en_quiebres(pipes, structures, fpp)
    if not nuevas_cv:
        return {}
    out: Dict[int, Dict[Tuple[float, float], dict]] = {}
    # vértices prácticamente rectos que se quitaron para que entre la curva de un quiebre
    for ip, p in enumerate(pipes):
        quedan = {(float(x), float(y)) for x, y in p.get("pts") or ()}
        for x, y in antes[ip]:
            if (float(x), float(y)) not in quedan:
                out.setdefault(dueño[ip], {})[(float(x), float(y))] = {QUITADO: True}
    # solo las tuberías que recibieron una curva (su CV está en uno de sus vértices)
    # (en gravedad la CV es el buzón oculto del quiebre: a ≤1 px del vértice, `_marcar_cv`)
    nuevas_ids = {id(s) for s in nuevas_cv}
    celdas = {(int(float(s["x"]) // 2), int(float(s["y"]) // 2)) for s in nuevas_cv}
    con_curva = [ip for ip, p in enumerate(pipes)
                 if any((int(x // 2) + dx, int(y // 2) + dy) in celdas
                        for x, y in p.get("pts") or () for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
    for ip in con_curva:
        p = pipes[ip]
        curvas = model_ops.curve_vertex_indices(p, structures, pipes, model_ops._TOL)
        for vi, s in curvas.items():
            if id(s) not in nuevas_ids or not (0 < vi < len(p["pts"]) - 1):
                continue
            g = quiebres_curvas._geo(p["pts"], vi, quiebres_curvas._radio_px(s, p, fpp), set(curvas), fpp)
            if g is None:
                continue
            x, y = p["pts"][vi]
            out.setdefault(dueño[ip], {})[(float(x), float(y))] = {
                "a": g["t1"], "b": g["t2"], "center": g["center"], "r_px": g["r"], "loose": False,
                "quiebre": True}
    return out


def codos_de(pl, curvas: Dict[Tuple[float, float], dict]) -> dict:
    """Codos de la polilínea `pl` para dibujarla: los suyos + las curvas de sus quiebres
    ({índice del vértice: codo})."""
    fil = dict(getattr(pl, "fillets", None) or {})
    if curvas:
        for i, q in enumerate(pl.pts_pdf):
            g = curvas.get((float(q[0]), float(q[1])))
            if g is not None and not g.get(QUITADO) and i not in fil:
                fil[i] = g
    return fil


def dibujo_de(pl, curvas: Dict[Tuple[float, float], dict]):
    """(polilínea, codos) para DIBUJAR `pl` como quedará al importar: sin los vértices
    prácticamente rectos que la importación quita para que entre la curva de un quiebre
    (`quiebres_curvas._enderezar`) y con esas curvas. Si nada se quita, la misma `pl`."""
    quitar = {i for i, q in enumerate(pl.pts_pdf)
              if (curvas or {}).get((float(q[0]), float(q[1])), {}).get(QUITADO)}
    if not quitar:
        return pl, codos_de(pl, curvas)
    nuevo = {i: k for k, i in enumerate(i for i in range(len(pl.pts_pdf)) if i not in quitar)}
    pl2 = dataclasses.replace(
        pl, pts_pdf=[q for i, q in enumerate(pl.pts_pdf) if i not in quitar],
        kinds=[k for i, k in enumerate(pl.kinds) if i not in quitar] if len(pl.kinds) == len(pl.pts_pdf) else pl.kinds,
        fillets={nuevo[i]: g for i, g in (getattr(pl, "fillets", None) or {}).items() if i in nuevo})
    return pl2, codos_de(pl2, curvas)
