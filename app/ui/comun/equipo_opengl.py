"""Prueba de OpenGL para el diagnóstico del equipo (pedido del usuario 2026-11-17: comprobar ANTES lo que hizo fallar la
Vista 3D en el equipo de un cliente —Intel Arc 140V, sin el modo rápido, «OverflowError» al subir 2.5 GB—).

Abre un contexto SIN ventana con el MISMO formato que pide la Vista 3D (`visor3d.GL_PEDIDO`, compatibilidad, 4
muestras, profundidad 24) y otro con el formato por defecto de Qt (lo que pedía la app antes de 2.1.0) y comprueba,
con el mismo código de la Vista 3D:
- lo que informa el contexto (`visor3d_diag.info_gl`: versión, GPU, driver, GLSL, instancing, software);
- que compilan y enlazan el programa de siempre y el de instancias (`visor3d_instancias.Instanciador`);
- un dibujo REAL a un framebuffer con los dos programas, y subir un bloque de `visor3d.BLOQUE_MAX_BYTES` (el tamaño de
  cada parte en el modo de respaldo), mirando `glGetError`;
- límites que informa el driver (textura, atributos, memoria de video si la dice NVIDIA/AMD).

`probar()` → (filas [(campo, valor)], veredicto) con veredicto en {"rapido", "respaldo", "no", "software"}.
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtGui
from PySide6.QtOpenGL import (QOpenGLBuffer, QOpenGLFramebufferObject, QOpenGLShader,
                              QOpenGLShaderProgram, QOpenGLVertexArrayObject)

GL_NO_ERROR, GL_OUT_OF_MEMORY = 0, 0x0505
ERRORES = {0x0500: "GL_INVALID_ENUM", 0x0501: "GL_INVALID_VALUE", 0x0502: "GL_INVALID_OPERATION",
           0x0505: "GL_OUT_OF_MEMORY", 0x0506: "GL_INVALID_FRAMEBUFFER_OPERATION"}
LIMITES = (("Textura máx. (px)", 0x0D33), ("Atributos de vértice máx.", 0x8869),
           ("Renderbuffer máx. (px)", 0x84E8), ("Muestras máx.", 0x8D57))
# memoria de video que informan algunos drivers (KB): NVIDIA y AMD; Intel no la da
MEMORIA = (("Memoria de video total (NVIDIA)", 0x9048), ("Memoria de video libre (NVIDIA)", 0x9049),
           ("Memoria de video libre (AMD)", 0x87FB))


def _formato_vista3d():
    from ui.comun import visor3d as V
    fmt = QtGui.QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setVersion(*V.GL_PEDIDO)
    fmt.setProfile(QtGui.QSurfaceFormat.CompatibilityProfile)
    return fmt


def _contexto(fmt):
    sup = QtGui.QOffscreenSurface()
    sup.setFormat(fmt)
    sup.create()
    ctx = QtGui.QOpenGLContext()
    ctx.setFormat(fmt)
    if not ctx.create():
        raise RuntimeError("no se pudo crear el contexto OpenGL")
    if not ctx.makeCurrent(sup):
        raise RuntimeError("no se pudo activar el contexto OpenGL")
    return ctx, sup


def _errores(f):
    out = []
    for _ in range(10):
        e = f.glGetError()
        if e == GL_NO_ERROR:
            break
        out.append(ERRORES.get(e, hex(e)))
    return out


def _entero(f, nombre):
    try:
        v = f.glGetIntegerv(nombre)
        v = v[0] if isinstance(v, (list, tuple)) else v
        _errores(f)                                      # un nombre que el driver no conoce deja INVALID_ENUM
        return int(v)
    except Exception:                                    # noqa: BLE001
        _errores(f)
        return None


def _programa_base():
    from ui.comun import visor3d_shaders as SH
    p = QOpenGLShaderProgram()
    if not (p.addShaderFromSourceCode(QOpenGLShader.Vertex, SH.VERT)
            and p.addShaderFromSourceCode(QOpenGLShader.Fragment, SH.FRAG)):
        raise RuntimeError(p.log().strip() or "no compiló")
    for k, nombre in enumerate(("aPos", "aNor", "aCol", "aId", "aEje", "aRadio")):
        p.bindAttributeLocation(nombre, k)
    if not p.link():
        raise RuntimeError(p.log().strip() or "no enlazó")
    return p


def _dibujar_base(f, p):
    """Un triángulo con el programa de siempre (15 floats por vértice, como la Vista 3D)."""
    tri = np.zeros((3, 15), np.float32)
    tri[:, :3] = [(-1, -1, 0), (1, -1, 0), (0, 1, 0)]
    tri[:, 5] = 1.0
    b = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
    b.create(); b.bind(); b.allocate(tri.tobytes(), tri.nbytes)
    p.bind()
    for k, (off, tam) in enumerate(((0, 3), (12, 3), (24, 3), (36, 1), (40, 4), (56, 1))):
        p.enableAttributeArray(k)
        p.setAttributeBuffer(k, 0x1406, off, tam, 60)
    f.glDrawArrays(0x0004, 0, 3)
    for k in range(6):
        p.disableAttributeArray(k)
    p.release(); b.release(); b.destroy()


def _probar_contexto(fmt, completo):
    from ui.comun import visor3d as V, visor3d_diag as DG, visor3d_instancias as VI
    from ui.comun import visor3d_shaders as SH
    from nucleo import instancias3d as I3
    filas, res = [], {"rapido": False, "base": False}
    ctx, sup = _contexto(fmt)
    try:
        f = ctx.functions()
        info = DG.info_gl(ctx, f, fmt)
        filas += list(info.items())
        res["software"] = info.get("OpenGL por software") == "sí"
        if not completo:
            res["version"] = info.get("versión obtenida")
            return filas, res
        try:
            exts = list(ctx.extensions())
            filas.append(("Extensiones", str(len(exts))))
        except Exception:                                # noqa: BLE001
            pass
        for nombre, n in LIMITES:
            v = _entero(f, n)
            if v is not None:
                filas.append((nombre, str(v)))
        for nombre, n in MEMORIA:
            v = _entero(f, n)
            if v:
                filas.append((nombre, f"{v / 1024:.0f} MB"))
        fbo = QOpenGLFramebufferObject(256, 256, QOpenGLFramebufferObject.CombinedDepthStencil)
        fbo.bind()
        f.glViewport(0, 0, 256, 256)
        vao = QOpenGLVertexArrayObject()            # como la Vista 3D: enlazado mientras dibuja
        vao.create(); vao.bind()
        _errores(f)
        # programa de siempre
        try:
            p = _programa_base()
            _dibujar_base(f, p)
            e = _errores(f)
            res["base"] = not e
            filas.append(("Programa de la Vista 3D", "compila, enlaza y dibuja" if not e else f"error: {', '.join(e)}"))
        except Exception as ex:                          # noqa: BLE001
            filas.append(("Programa de la Vista 3D", f"FALLA: {ex}"))
        # instancias (el modo rápido)
        filas.append(("Instancing según el contexto", "sí" if VI.soportado(ctx) else f"no: {VI.motivo_no_soportado(ctx)}"))
        if VI.soportado(ctx):
            try:
                inst = VI.Instanciador(None, ctx, SH.FRAG)
                fila = np.zeros((1, I3.CAMPOS_INST), np.float32)
                inst.subir({(I3.SEG, 8): fila, (I3.ESFERA, (6, 8)): fila})
                inst.dibujar(lambda prog: None)
                e = _errores(f)
                inst.liberar()
                res["rapido"] = not e
                filas.append(("Programa de instancias (modo rápido)",
                              "compila, enlaza y dibuja" if not e else f"error al dibujar: {', '.join(e)}"))
            except Exception as ex:                      # noqa: BLE001
                filas.append(("Programa de instancias (modo rápido)", f"FALLA: {type(ex).__name__}: {ex}"))
        # un bloque del modo de respaldo
        try:
            b = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            b.create(); b.bind()
            n = V.BLOQUE_MAX_BYTES
            b.allocate(bytes(n), n)
            e = _errores(f)
            b.release(); b.destroy()
            res["bloque"] = not e
            filas.append((f"Subir un bloque de {n // 2 ** 20} MB", "sí" if not e else f"no: {', '.join(e)}"))
        except Exception as ex:                          # noqa: BLE001
            res["bloque"] = False
            filas.append(("Subir un bloque", f"FALLA: {type(ex).__name__}: {ex}"))
        vao.release(); vao.destroy()
        fbo.release()
        return filas, res
    finally:
        ctx.doneCurrent()
        del ctx, sup


def probar():
    """(filas, veredicto). Necesita una QGuiApplication creada (plataforma de verdad, no «offscreen»)."""
    filas = []
    try:
        app = QtGui.QGuiApplication.instance()
        filas.append(("Plataforma de Qt", app.platformName() if app else "?"))
        filas.append(("Qt", __import__("PySide6").__version__))
    except Exception:                                    # noqa: BLE001
        pass
    try:
        f, res = _probar_contexto(_formato_vista3d(), completo=True)
        filas += [("— Formato de la Vista 3D —", "")] + f
    except Exception as ex:                              # noqa: BLE001
        filas.append(("Contexto de la Vista 3D", f"FALLA: {type(ex).__name__}: {ex}"))
        return filas, "no"
    try:
        f2, r2 = _probar_contexto(QtGui.QSurfaceFormat(), completo=False)
        filas += [("— Formato por defecto de Qt (versiones anteriores a 2.1.0) —", "")] + f2
    except Exception as ex:                              # noqa: BLE001
        filas.append(("Contexto por defecto", f"FALLA: {type(ex).__name__}: {ex}"))
    if res.get("software"):
        return filas, "software"
    if res.get("rapido"):
        return filas, "rapido"
    if res.get("base"):
        return filas, "respaldo"
    return filas, "no"


def pantallas():
    out = []
    for k, s in enumerate(QtGui.QGuiApplication.screens(), 1):
        g = s.geometry()
        out.append((f"Pantalla {k}", f"{s.name()} · {g.width()}×{g.height()} lógicos · escala {s.devicePixelRatio():g} · "
                                     f"{s.logicalDotsPerInch():.0f} ppp · {s.refreshRate():.0f} Hz"))
    return out
