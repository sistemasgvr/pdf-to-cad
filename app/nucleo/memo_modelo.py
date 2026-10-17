"""Resultados del redibujo que dependen SOLO del modelo, reusados mientras no cambie (PURO).

Pedido del usuario 2026-10-16 («redibujar solo lo que cambia»): cada clic en el lienzo
—elegir otra utilidad, cambiar de pestaña, entrar en un modo— redibuja todo y recalculaba
cruces, choques, juntas, accesorios, normativas, ángulos y curvas aunque nada del modelo
hubiera cambiado. Al empezar cada redibujo la ventana calcula la FIRMA del modelo (todo lo
que esos cálculos leen: utilidades, estructuras, conexiones aprobadas, aprobaciones,
normativas, bancoductos, escala, zoom, idioma); con la misma firma, `Memo.obtener` devuelve
el resultado guardado (una COPIA: quien lo recibe puede cambiarlo). Con CUALQUIER cambio la
firma cambia y todo se recalcula: el resultado es siempre el mismo que calculándolo.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import pickle


def firma(*partes):
    """Huella del contenido (bytes) o None si no se puede calcular (entonces no se reusa nada)."""
    try:
        datos = pickle.dumps(partes, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        return None
    return hashlib.blake2b(datos, digest_size=20).digest()


def copia(v):
    """Copia de listas, diccionarios y dataclases anidados (lo que devuelven los cálculos del
    redibujo: puntos, avisos, accesorios); tuplas, números y textos no se copian (no cambian).
    Igual a `copy.deepcopy` para estos datos, varias veces más rápida."""
    if isinstance(v, list):
        return [copia(x) for x in v]
    if isinstance(v, dict):
        return {k: copia(x) for k, x in v.items()}
    if isinstance(v, tuple):
        return tuple(copia(x) for x in v) if any(isinstance(x, (list, dict)) or dataclasses.is_dataclass(x)
                                                for x in v) else v
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return dataclasses.replace(v, **{f.name: copia(getattr(v, f.name)) for f in dataclasses.fields(v)
                                         if isinstance(getattr(v, f.name), (list, dict))})
    if isinstance(v, (int, float, str, bytes, bool, type(None))):
        return v
    return copy.deepcopy(v)


class Memo:
    def __init__(self):
        self.firma = None
        self.datos = {}

    def usar(self, f):
        """La firma del redibujo que empieza: si cambió (o no hay), se olvida todo."""
        if f is None or f != self.firma:
            self.datos = {}
        self.firma = f

    def obtener(self, clave, fn, copiar=True):
        """`fn()` la primera vez con esta firma; después, lo guardado (copiado si `copiar`)."""
        if self.firma is None:
            return fn()
        if clave not in self.datos:
            self.datos[clave] = fn()
        valor = self.datos[clave]
        return copia(valor) if copiar else valor
