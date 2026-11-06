"""Qué pide el usuario al Copiloto (PURO, sin modelo): saber cómo va el proyecto, revisar avisos o resolver conflictos.

Lo que nombra un elemento (C-12, AGUA-5) o pregunta dónde está algo no es del Copiloto: va por el camino de siempre.
"""
from __future__ import annotations

import re

from ia.texto import normalizar

ESTADO, REVISION, CONFLICTOS = "estado", "revision", "conflictos"

_CODIGO = re.compile(r"\b[a-z]+-\d+\b")
_DONDE = re.compile(r"\b(donde|zona)\b")
_PREGUNTA = re.compile(r"^\W*(que|cual|cuales|por que|porque|como|cuando|quien)\b")   # pregunta, no un pedido
_RESOLVER = re.compile(r"\b(resuelv\w*|resolv\w*|soluciona\w*|solucion\w*|arregl\w*|corrig\w*|correg\w*|"
                       r"revis\w*|empez\w*|empiez\w*)\b")
_AVISOS = re.compile(r"\bavisos?\b")
_CONFLICTOS = re.compile(r"\bconflictos?\b")
_ESTADO = re.compile(r"\b(como vamos|como va el proyecto|que falta|cuantos avisos|cuantos conflictos)\b")


def intencion(texto):
    q = normalizar(texto)
    if _CODIGO.search(q) or _DONDE.search(q):
        return None
    if _RESOLVER.search(q) and not _PREGUNTA.search(q):
        if _AVISOS.search(q):
            return REVISION
        if _CONFLICTOS.search(q):
            return CONFLICTOS
    return ESTADO if _ESTADO.search(q) else None
