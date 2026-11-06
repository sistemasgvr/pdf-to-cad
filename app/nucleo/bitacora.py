"""Bitácora del Copiloto (PURO): qué hizo cada tanda o decisión, por qué, quién lo aprobó y cuándo.

La lista vive en el proyecto y NO se restaura al deshacer: un registro no se borra con Ctrl+Z. Cada paso de deshacer
guarda solo los ids vigentes en ese momento (`vigentes`) y al volver a él `marcar` deja `deshecha` a las demás.
"""
from __future__ import annotations

import datetime as _dt
import uuid

from nucleo import normas_aprobacion

TIPOS = ("tanda", "decision", "aprobacion", "conflictos")


def agregar(lista, tipo, resumen, detalle=(), usuario=None, ahora=None, paso=None):
    """Anota una entrada. `detalle` = dicts {codigo, antes, despues, por_que, evidencia}; `paso` = cuántos pasos de
    deshacer había justo después de hacerla (para saber si sigue siendo el último)."""
    e = dict(id=uuid.uuid4().hex[:12], tipo=tipo, resumen=resumen, detalle=[dict(d) for d in detalle],
             usuario=usuario if usuario is not None else normas_aprobacion.usuario(),
             fecha=(ahora or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M"), paso=paso, deshecha=False)
    lista.append(e)
    return e


def al_abrir(lista):
    """Al abrir un proyecto el deshacer empieza vacío: `paso` ya no apunta a nada."""
    return [dict(e, paso=None) for e in lista or []]


def vigentes(lista):
    return [e["id"] for e in lista or [] if not e.get("deshecha")]


def marcar(lista, ids):
    ids = set(ids or ())
    for e in lista or []:
        e["deshecha"] = e["id"] not in ids
