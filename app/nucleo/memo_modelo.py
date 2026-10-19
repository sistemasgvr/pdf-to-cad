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
import io
import pickle


def firma(*partes):
    """Huella del contenido (bytes) o None si no se puede calcular (entonces no se reusa nada).
    Por VALOR: `pickle` en modo `fast` (sin memoria de referencias) escribe cada objeto entero
    aunque se repita, así dos modelos iguales dan la misma huella aunque compartan objetos de
    otra manera (lo que deja deshacer: mismos valores, otros objetos)."""
    try:
        buf = io.BytesIO()
        p = pickle.Pickler(buf, protocol=pickle.HIGHEST_PROTOCOL)
        p.fast = True
        p.dump(partes)
        datos = buf.getvalue()
    except Exception:
        return None
    return hashlib.blake2b(datos, digest_size=20).digest()


def copia(v):
    """Copia de listas, diccionarios y dataclases anidados (lo que devuelven los cálculos del
    redibujo: puntos, avisos, accesorios). Con `pickle` (en C: miles de accesorios en una
    fracción de lo que tardaba recorrerlos); si algo no se puede, la copia recursiva."""
    try:
        return pickle.loads(pickle.dumps(v, pickle.HIGHEST_PROTOCOL))
    except Exception:
        return _copia(v)


def _copia(v):
    """Copia recursiva (tuplas, números y textos no se copian: no cambian)."""
    if isinstance(v, list):
        return [_copia(x) for x in v]
    if isinstance(v, dict):
        return {k: _copia(x) for k, x in v.items()}
    if isinstance(v, tuple):
        return tuple(_copia(x) for x in v) if any(isinstance(x, (list, dict)) or dataclasses.is_dataclass(x)
                                                for x in v) else v
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return dataclasses.replace(v, **{f.name: _copia(getattr(v, f.name)) for f in dataclasses.fields(v)
                                         if isinstance(getattr(v, f.name), (list, dict))})
    if isinstance(v, (int, float, str, bytes, bool, type(None))):
        return v
    return copy.deepcopy(v)


PREVIOS = 2      # modelos anteriores que se recuerdan (deshacer / rehacer vuelven a uno de ellos)


class Memo:
    def __init__(self):
        self.firma = None
        self.datos = {}
        self.previos = []           # [(firma, datos)] de los modelos anteriores, el más reciente al final

    def usar(self, f):
        """La firma del redibujo que empieza. Si cambió, lo de la firma anterior se guarda aparte
        (hasta `PREVIOS`) y, si la nueva es una de las guardadas —deshacer, rehacer: el modelo
        VUELVE a ser exactamente uno anterior—, se retoma lo suyo; si no, se empieza de cero."""
        if f is not None and f == self.firma:
            return
        if self.firma is not None and self.datos:
            self.previos.append((self.firma, self.datos))
        datos = {}
        if f is not None:
            for k, (fp, dp) in enumerate(self.previos):
                if fp == f:
                    datos = dp
                    del self.previos[k]
                    break
        del self.previos[:-PREVIOS or len(self.previos)]
        self.datos = datos
        self.firma = f

    def obtener(self, clave, fn, copiar=True):
        """`fn()` la primera vez con esta firma; después, lo guardado (copiado si `copiar`)."""
        if self.firma is None:
            return fn()
        if clave not in self.datos:
            self.datos[clave] = fn()
        valor = self.datos[clave]
        return copia(valor) if copiar else valor
