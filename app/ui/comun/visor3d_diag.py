"""Diagnóstico de la Vista 3D (reporte del cliente 2026-11-16: con su equipo —Intel Arc 140V integrado— la Vista 3D
daba «OverflowError» al subir la escena a la GPU, el aviso volvía a salir en bucle al cerrarlo y en el registro no
había nada para saber por qué).

- `info_gl(ctx, f)`: lo que dice el contexto OpenGL que obtuvo la app (versión pedida y obtenida, perfil, fabricante,
  GPU, versión del driver, GLSL, si hay instancing, si Qt usa el OpenGL por software).
- `registrar_inicio`: una entrada en el registro de la sesión (`nucleo.diagnostico`) al iniciar la Vista 3D, con el
  modo elegido (instancing o respaldo) y el MOTIVO si no hay instancing.
- `registrar_fallo`: el error al dibujar, con el contexto, el tamaño de lo que se intentó subir y la pila; un mismo
  error se anota UNA vez (los demás solo se cuentan).
- `mensaje(e)`: el texto para el usuario, según el error.
"""
from __future__ import annotations

import os
import traceback

from nucleo import diagnostico
from traduccion.i18n import t as _tr

GL_VENDOR, GL_RENDERER, GL_VERSION, GL_SHADING_LANGUAGE_VERSION = 0x1F00, 0x1F01, 0x1F02, 0x8B8C
LIMITE_QT_BYTES = 2 ** 31 - 1                  # Qt recibe el tamaño de cada bloque como entero de 32 bits
SOFTWARE = ("llvmpipe", "software", "gdi generic", "basic render")   # GPU que en realidad es el procesador

_anotados = {}                                  # firma del error → veces que se repitió


def _cadena(f, nombre):
    try:
        v = f.glGetString(nombre)
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("latin-1", "replace")
        return str(v or "").strip() or "?"
    except Exception as e:                      # noqa: BLE001
        return f"? ({type(e).__name__})"


def info_gl(ctx, f, pedido=None):
    """{campo: valor} del contexto OpenGL. `pedido` = el QSurfaceFormat que pidió la app."""
    out = {}
    try:
        fmt = ctx.format()
        out["versión obtenida"] = f"{fmt.majorVersion()}.{fmt.minorVersion()}"
        perfil = {0: "ninguno", 1: "core", 2: "compatibilidad"}.get(int(getattr(fmt.profile(), "value", fmt.profile())), "?")
        out["perfil"] = perfil
        out["muestras (antialias)"] = fmt.samples()
    except Exception as e:                      # noqa: BLE001
        out["versión obtenida"] = f"? ({type(e).__name__})"
    if pedido is not None:
        try:
            out["versión pedida"] = f"{pedido.majorVersion()}.{pedido.minorVersion()}"
        except Exception:                       # noqa: BLE001
            pass
    out["fabricante"] = _cadena(f, GL_VENDOR)
    out["GPU"] = _cadena(f, GL_RENDERER)
    out["GL_VERSION (incluye el driver)"] = _cadena(f, GL_VERSION)
    out["GLSL"] = _cadena(f, GL_SHADING_LANGUAGE_VERSION)
    try:
        from PySide6 import QtCore
        out["GL_ARB_instanced_arrays"] = "sí" if ctx.hasExtension(QtCore.QByteArray(b"GL_ARB_instanced_arrays")) else "no"
    except Exception:                           # noqa: BLE001
        out["GL_ARB_instanced_arrays"] = "?"
    gpu = out["GPU"].lower()
    out["OpenGL por software"] = "sí" if any(s in gpu for s in SOFTWARE) else "no"
    for var in ("QT_OPENGL", "PDFCAD_SIN_INSTANCING"):
        if os.environ.get(var):
            out[var] = os.environ[var]
    return out


def _texto(info):
    return "\n".join(f"  {k}: {v}" for k, v in info.items())


def registrar_inicio(info, instancing, motivo=""):
    modo = "instancing (rápido)" if instancing else "respaldo: todos los triángulos (sin instancing)"
    detalle = f"Contexto OpenGL de la Vista 3D\n{_texto(info)}\n  modo: {modo}"
    if motivo:
        detalle += f"\n  motivo: {motivo}"
    return diagnostico.registrar(detalle, "Vista 3D · OpenGL")


def tamanos(escena, inst):
    """Lo que la Vista 3D sube a la GPU: {bloque: bytes}."""
    import numpy as np
    out = {}
    if escena is None:
        return out
    for clave in ("opacos", "transparentes", "suelo"):
        fuente = escena.base if (clave == "opacos" and inst is not None) else getattr(escena, clave, None)
        if fuente is not None:
            out[clave] = int(np.asarray(fuente).size) * 4
    if inst is not None:
        out["instancias"] = sum(int(np.asarray(v).nbytes) for v in (getattr(escena, "instancias", None) or {}).values())
    return out


def registrar_fallo(error, info, tam, instancing):
    """Anota el error al dibujar UNA vez por firma (tipo + último lugar del código). Devuelve (ruta, primera_vez)."""
    tb = traceback.extract_tb(error.__traceback__)
    lugar = f"{os.path.basename(tb[-1].filename)}:{tb[-1].lineno}" if tb else "?"
    firma = (type(error).__name__, lugar)
    _anotados[firma] = _anotados.get(firma, 0) + 1
    if _anotados[firma] > 1:
        return diagnostico.ruta(), False
    mb = {k: f"{v / 2 ** 20:,.1f} MB" for k, v in tam.items()}
    detalle = (f"La Vista 3D no pudo dibujar: {type(error).__name__}: {error}\n"
               f"  modo: {'instancing' if instancing else 'respaldo (sin instancing)'}\n"
               f"  a subir a la GPU: {mb}\n"
               + f"{_texto(info)}\n" + "".join(traceback.format_exception(type(error), error, error.__traceback__)))
    return diagnostico.registrar(detalle, "Vista 3D · error al dibujar"), True


def mensaje(error, tam, instancing):
    """Lo que ve el usuario dentro de la Vista 3D (sin jerga; el detalle va al registro)."""
    grande = any(v > LIMITE_QT_BYTES for v in tam.values())
    if isinstance(error, OverflowError) or grande:
        cuerpo = _tr("El proyecto es demasiado grande para dibujarlo en 3D con la tarjeta de video de este equipo "
                     "en modo compatible (más de 2 GB de geometría).")
        if not instancing:
            cuerpo += " " + _tr("El modo rápido no está disponible en este equipo: actualizar el driver de video "
                                "suele activarlo.")
    elif isinstance(error, MemoryError):
        cuerpo = _tr("No hay memoria suficiente para dibujar este proyecto en 3D.")
    else:
        cuerpo = _tr("La tarjeta de video no pudo dibujar la vista 3D.")
    return (cuerpo + "\n\n" + _tr("El resto de la app sigue funcionando con normalidad. Prueba apagando utilidades "
                                  "en el panel o abriendo un proyecto más chico.") + "\n\n"
            + _tr("Detalle guardado en: {r}").format(r=diagnostico.ruta()))
