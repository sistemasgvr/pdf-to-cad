"""Avisos de normativa REVISADOS Y APROBADOS (PURO: sin Qt).

Pedido del usuario 2026-10-12: los avisos se revisan y se aprueban de forma fácil y
queda REGISTRO de que existen pero están aprobados (quién, cuándo y por qué). Un
aviso aprobado sigue en la lista de avisos y en la Tabla de datos (con su estado,
fecha y nota) pero ya no se marca en el plano ni en la Vista 3D ni cuenta en «⚠ N
avisos de normativa».

La aprobación se guarda en el proyecto (`.digproj`, `normas_aprobados`) con una
CLAVE del aviso: clase + utilidad + lugar + una huella de lo que la normativa revisa
de esa utilidad (tipo, tamaño, amperaje, estado). Si algo de eso cambia —otro
diámetro, otro tipo, la utilidad se movió— la clave ya no coincide y el aviso vuelve
a quedar pendiente: lo aprobado fue OTRA situación. El registro viejo se conserva
(«ya no aplica») hasta que el usuario lo quite.
"""
from __future__ import annotations

import datetime as _dt
import getpass

LUGAR_PX = 2.0           # redondeo del lugar del aviso (px del lienzo)


def huella(p):
    """Lo que la normativa revisa de una utilidad (si cambia, la aprobación ya no vale)."""
    if not p:
        return ""
    return "|".join(str(p.get(k) or "") for k in ("layer", "tipo", "pipe_family", "pipe_size", "amperaje")) \
        + ("|ab" if p.get("ab") else "")


def clave(aviso, pipes):
    p = pipes[aviso.pipe] if aviso.pipe is not None and 0 <= aviso.pipe < len(pipes or []) else None
    x, y = (round(aviso.x / LUGAR_PX) * LUGAR_PX, round(aviso.y / LUGAR_PX) * LUGAR_PX)
    return f"{aviso.clase}|{aviso.pipe}|{x:g}|{y:g}|{huella(p)}"


def marcar(avisos, pipes, aprobados):
    """Pone en cada aviso su registro de aprobación (`aviso.aprobado`, o None).
    Devuelve las claves de los registros que ya no corresponden a ningún aviso."""
    por_clave = {r.get("clave"): r for r in aprobados or []}
    usadas = set()
    for a in avisos or []:
        r = por_clave.get(clave(a, pipes))
        a.aprobado = r
        if r is not None:
            usadas.add(r["clave"])
    return [k for k in por_clave if k not in usadas]


def aprobar(aprobados, avisos, pipes, nota="", usuario=None, ahora=None):
    """Agrega (o actualiza) el registro de cada aviso. Devuelve cuántos se aprobaron."""
    usuario = usuario if usuario is not None else _usuario()
    fecha = (ahora or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
    n = 0
    for a in avisos:
        if a.info:
            continue                                   # solo información: no hay nada que aprobar
        k = clave(a, pipes)
        reg = dict(clave=k, clase=a.clase, utilidad=a.pipe, mensaje=a.mensaje, nota=(nota or "").strip(),
                   usuario=usuario, fecha=fecha)
        for j, r in enumerate(aprobados):
            if r.get("clave") == k:
                aprobados[j] = reg
                break
        else:
            aprobados.append(reg)
        a.aprobado = reg
        n += 1
    return n


def quitar(aprobados, avisos, pipes):
    """Quita la aprobación de esos avisos (vuelven a quedar pendientes)."""
    claves = {clave(a, pipes) for a in avisos}
    antes = len(aprobados)
    aprobados[:] = [r for r in aprobados if r.get("clave") not in claves]
    for a in avisos:
        a.aprobado = None
    return antes - len(aprobados)


def pendientes(avisos):
    """Avisos que hay que revisar: ni informativos ni aprobados."""
    return [a for a in avisos or [] if not a.info and not getattr(a, "aprobado", None)]


def reindexar(aprobados, borrada):
    """Al borrar la utilidad `borrada` las siguientes bajan un número: su registro y su
    clave siguen a la utilidad; los de la borrada se quitan."""
    out = []
    for r in aprobados or []:
        u = r.get("utilidad")
        if u == borrada:
            continue
        if isinstance(u, int) and u > borrada:
            partes = str(r.get("clave", "")).split("|")
            if len(partes) > 1:
                partes[1] = str(u - 1)
            r = dict(r, utilidad=u - 1, clave="|".join(partes))
        out.append(r)
    aprobados[:] = out


def _usuario():
    try:
        return getpass.getuser()
    except Exception:                                  # sin variables de entorno de usuario
        return ""
