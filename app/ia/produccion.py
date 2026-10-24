"""«Pasar a producción» (PURO). Pedido del usuario 2026-10-24: de lo que el equipo enseñó en DESARROLLO
(`entrenamiento_ia/desarrollo.json`) se eligen las enseñanzas buenas y se copian a `produccion.json`, el archivo
que viaja en el instalador y que el programa del cliente solo lee (`ia.memoria`).

Se copian solo ENSEÑANZAS (notas, correcciones, valoraciones útiles, soluciones aplicadas), con su mismo `id`:
repetir no duplica y se sabe cuáles ya están. Las conversaciones nunca pasan (son pruebas). Opcional: los textos ya
redactados que no dependen de un proyecto —reglas explicadas («normas») y respuestas del manual («ayuda»)—, así el
cliente no espera a la IA en lo que ya se respondió. «Quitar de producción» saca enseñanzas por id.
"""
from __future__ import annotations

import os

from ia import memoria as M

AMBITOS_GENERALES = ("normas", "ayuda")          # redacción que no depende de un proyecto


def almacenes():
    """(desarrollo, producción): los dos archivos del repo, sea cual sea el entorno elegido."""
    esc, leer = M.rutas(M.DESARROLLO)
    prod = leer[0] if leer else os.path.join(os.path.dirname(esc), M.ARCHIVO_PRODUCCION)
    return M.Almacen.de(esc), M.Almacen.de(prod)


def lista(dev, prod):
    """Las enseñanzas de desarrollo, la más nueva primero, cada una con `en_produccion`."""
    dev.recargar()
    prod.recargar()
    en_prod = {r.get("id") for r in prod.datos[M.ENSENANZAS]}
    regs = sorted(dev.datos[M.ENSENANZAS], key=lambda r: (str(r.get("fecha") or ""), str(r.get("id"))),
                  reverse=True)
    return [(r, r.get("id") in en_prod) for r in regs]


def redaccion_general(dev, prod):
    """Claves de textos generales (normas, ayuda) de desarrollo que producción aún no tiene."""
    dev.recargar()
    prod.recargar()
    return [k for k, v in dev.datos[M.REDACCION].items()
            if v.get("ambito") in AMBITOS_GENERALES and k not in prod.datos[M.REDACCION]]


def pasar(dev, prod, ids, con_redaccion=False):
    """Copia a producción las enseñanzas `ids` (y, si se pide, la redacción general). Devuelve
    (enseñanzas nuevas, textos nuevos) o lanza OSError/ValueError si no se pudo escribir."""
    ids = set(ids)
    claves = redaccion_general(dev, prod) if con_redaccion else []
    with prod.lock:
        prod.recargar()
        ya = {r.get("id") for r in prod.datos[M.ENSENANZAS]}
        nuevas = [dict(r) for r in dev.datos[M.ENSENANZAS] if r.get("id") in ids and r.get("id") not in ya]
        prod.datos[M.ENSENANZAS] += nuevas
        for k in claves:
            prod.datos[M.REDACCION][k] = dict(dev.datos[M.REDACCION][k])
        if (nuevas or claves) and not prod.escribir():
            raise OSError(prod.error)
    return len(nuevas), len(claves)


def quitar(prod, ids):
    """Saca de producción las enseñanzas `ids`. Devuelve cuántas salieron."""
    ids = set(ids)
    with prod.lock:
        prod.recargar()
        if prod.error:
            raise ValueError(prod.error)
        antes = len(prod.datos[M.ENSENANZAS])
        prod.datos[M.ENSENANZAS] = [r for r in prod.datos[M.ENSENANZAS] if r.get("id") not in ids]
        n = antes - len(prod.datos[M.ENSENANZAS])
        if n and not prod.escribir(juntar=False):        # juntar con el disco las volvería a traer
            raise OSError(prod.error)
    return n
