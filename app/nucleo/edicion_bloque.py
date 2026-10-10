"""Editar varias utilidades DEL MISMO TIPO a la vez y copiar propiedades (PURO: sin Qt).

Pedido del usuario 2026-10-08 (cliente ferroviario: mapea lo existente y lo reubica,
no diseña; lo que importa es modelar rápido): poner familia y diámetro (tamaño del
catálogo de Civil 3D), tipo de tubería, material y estado a muchas utilidades de una
vez, o copiarlos de una utilidad a otras. Solo entre utilidades del MISMO tipo (misma
capa: ELECTRICO, AGUA…): las familias y los tamaños dependen de la red (gravedad,
presión o conducto) y una familia de agua no sirve para una línea eléctrica.

`cambios` = {campo: valor} SOLO con lo que cambia (lo que no está queda igual):
  familia  → `pipe_family` (id del catálogo; "" = por defecto)
  tamano   → `pipe_size`   ("" = el diámetro por defecto); el diámetro sale de aquí
  net_type → tipo de tubería ("" automático, "pipe", "pressure")
  material → material
  ab       → abandonada (True/False)
  datos    → campos de los datos extendidos del usuario (se suman; uno con el mismo
             nombre se reemplaza, los demás se conservan)
  tipo     → tipo de la utilidad para las normativas («» = sin tipo; normas_catalogo)
  amperaje → amperaje en A (None = sin dato; solo tiene sentido en eléctrico)
"""
from __future__ import annotations

import re

from nucleo import xdata
from nucleo.model_ops import DIAM_DEFECTO_IN

CAMPOS = ("familia", "tamano", "net_type", "material", "ab", "datos", "tipo", "amperaje")


def tipos(pipes, filas):
    """Capas (tipos) de esas utilidades, sin repetir y en el orden de la lista."""
    out = []
    for r in filas:
        if 0 <= r < len(pipes):
            capa = pipes[r].get("layer") or ""
            if capa not in out:
                out.append(capa)
    return out


def mismo_tipo(pipes, filas):
    return len(tipos(pipes, filas)) == 1


def diam_de_tamano(tamano):
    """Primer número del tamaño del catálogo («24 in» → 24.0, «12 in x 8 in» → 12.0);
    sin tamaño, el diámetro por defecto. Mismo criterio que el panel de propiedades."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(tamano or ""))
    return float(m.group(1)) if m and float(m.group(1)) > 0 else DIAM_DEFECTO_IN


def valores_de(p):
    """Propiedades copiables de una utilidad, con las mismas claves que `cambios`."""
    return {
        "familia": p.get("pipe_family") or "",
        "tamano": p.get("pipe_size") or "",
        "net_type": p.get("net_type") or "",
        "material": p.get("material") or "",
        "ab": bool(p.get("ab")),
        "datos": dict(xdata.get(p)[xdata.USER]),
        "tipo": p.get("tipo") or "",
        "amperaje": p.get("amperaje"),
    }


def familia_comun(pipes, filas):
    """La familia que comparten todas esas utilidades, o None si tienen distintas
    (entonces no se puede elegir un tamaño sin elegir antes la familia)."""
    fams = {pipes[r].get("pipe_family") or "" for r in filas if 0 <= r < len(pipes)}
    return fams.pop() if len(fams) == 1 else None


def aplicar(pipes, filas, cambios, sin_familia=()):
    """Escribe `cambios` en las utilidades `filas`. Las de `sin_familia` (llevan
    bancoducto: su sección la define el bancoducto) no cambian familia ni tamaño.
    Cambiar la familia sin decir el tamaño deja el diámetro por defecto, como el
    panel. Devuelve cuántas utilidades cambiaron."""
    sin_familia = set(sin_familia)
    n = 0
    for r in filas:
        if not 0 <= r < len(pipes):
            continue
        p = pipes[r]
        antes = valores_de(p), p.get("diam")
        if r not in sin_familia and ("familia" in cambios or "tamano" in cambios):
            if "familia" in cambios:
                p["pipe_family"] = cambios["familia"] or ""
                p["pipe_size"] = ""
            if "tamano" in cambios:
                p["pipe_size"] = cambios["tamano"] or ""
            p["diam"] = diam_de_tamano(p.get("pipe_size"))
            p["diam_unit"] = "in"
        if "net_type" in cambios:
            p["net_type"] = cambios["net_type"] or ""
        if "material" in cambios and cambios["material"]:
            p["material"] = cambios["material"]
        if "ab" in cambios:
            p["ab"] = bool(cambios["ab"])
        if "tipo" in cambios:
            p["tipo"] = cambios["tipo"] or ""
        if "amperaje" in cambios:
            p["amperaje"] = cambios["amperaje"] or None
        if cambios.get("datos"):
            user = xdata.get(p)[xdata.USER]
            user.update({str(k): str(v) for k, v in cambios["datos"].items()})
            xdata.set_user(p, user)
        if (valores_de(p), p.get("diam")) != antes:
            n += 1
    return n
