"""Pasos de deshacer LIVIANOS (PURO): el mismo estado, mucha menos memoria.

Pedido del usuario 2026-10-16 («menos recursos de PC», sobre todo con mucha información):
cada paso de deshacer era una copia ENTERA del modelo (`copy.deepcopy`; hasta 400 pasos).
Con cientos de utilidades cada paso pesaba megas y la mayoría repetía lo mismo: un cambio
toca una utilidad, no las 400.

Aquí cada lista del estado (utilidades, estructuras, marcas…) se guarda ELEMENTO POR
ELEMENTO como bytes de `pickle` (una copia exacta e independiente, como `deepcopy`), y un
elemento que no cambió desde el paso anterior REUSA los mismos bytes: en memoria solo
queda una vez, aunque aparezca en todos los pasos. Al deshacer, `abrir` rehace el estado
con `pickle.loads`: los mismos valores que la copia de antes.

Lo único distinto de `deepcopy`: si dos elementos COMPARTÍAN un mismo objeto (la misma
lista en dos utilidades), por separado quedarían dos. `paso` lo revisa y, si pasa, guarda
el estado entero de una vez (como antes), así nada cambia.
"""
from __future__ import annotations

import pickle

_PROTO = pickle.HIGHEST_PROTOCOL


class Paso:
    """Un paso de deshacer: {clave: bytes | tuple[bytes, …]} (tupla = lista elemento a elemento)."""
    __slots__ = ("partes",)

    def __init__(self, partes):
        self.partes = partes

    def blobs(self):
        for v in self.partes.values():
            if isinstance(v, tuple):
                yield from v
            else:
                yield v

    def nbytes(self):
        return sum(len(b) for b in self.blobs())


def _comparte(estado):
    """True si dos partes del estado (dos elementos de una lista, o una lista y otra clave)
    comparten un objeto mutable: `deepcopy` del estado entero lo conserva compartido."""
    vistos = {}
    for clave, valor in estado.items():
        dueños = enumerate(valor) if isinstance(valor, list) else [(None, valor)]
        for k, el in dueños:
            dueño = (clave, k)
            pila = [el]
            while pila:
                o = pila.pop()
                if isinstance(o, tuple):
                    pila.extend(o)
                    continue
                if isinstance(o, dict):
                    hijos = list(o.keys()) + list(o.values())
                elif isinstance(o, (list, set)):
                    hijos = o
                elif hasattr(o, "__dict__") and not isinstance(o, type):
                    hijos = vars(o).values()
                else:
                    continue
                if vistos.setdefault(id(o), dueño) != dueño:
                    return True
                pila.extend(hijos)
    return False


def paso(estado, anterior=None):
    """`Paso` del estado {clave: valor}; las listas van elemento por elemento y reusan los
    bytes iguales del paso `anterior` (si se da). Con objetos compartidos entre partes, el
    estado entero va en un solo bloque (como la copia de antes)."""
    if _comparte(estado):
        return Paso({None: pickle.dumps(estado, _PROTO)})
    previos = {}
    if anterior is not None:
        for b in anterior.blobs():
            previos[b] = b
    partes = {}
    for clave, valor in estado.items():
        if isinstance(valor, list):
            partes[clave] = tuple(_reusar(pickle.dumps(el, _PROTO), previos) for el in valor)
        else:
            partes[clave] = _reusar(pickle.dumps(valor, _PROTO), previos)
    return Paso(partes)


def _reusar(b, previos):
    return previos.setdefault(b, b)


def abrir(p):
    """El estado {clave: valor} guardado en el paso (objetos nuevos, independientes)."""
    if None in p.partes:
        return pickle.loads(p.partes[None])
    out = {}
    for clave, v in p.partes.items():
        out[clave] = [pickle.loads(b) for b in v] if isinstance(v, tuple) else pickle.loads(v)
    return out
