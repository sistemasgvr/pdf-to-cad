"""Dibujo de las INSTANCIAS de la vista 3D en la GPU (instancing, OpenGL 3.3).

Pedido del usuario 2026-10-16: los mismos resultados con menos recursos. La escena trae los
círculos barridos (tubos, accesorios, buzones redondos) y las esferas como filas de
`instancias3d` (34 floats por tramo en vez de 72–120 vértices de 15 floats). Aquí cada
grupo (tipo, lados) es UNA malla unidad + su arreglo de filas, y la GPU la repite por fila
(`glDrawArraysInstanced`, atributos con divisor 1). El vertex shader hace la MISMA cuenta
que `instancias3d.expandir` / `mallas3d.barrido_camino` (anillo = P + r·(cos θ·lado +
sen θ·arriba) + inglete), el grosor mínimo en pantalla de las tuberías y el resaltado por id.
El fragment shader es el de siempre.

Sin OpenGL 3.3 (ni `GL_ARB_instanced_arrays`), o si algo falla, `Visor3D` dibuja los
triángulos de siempre (`Escena.opacos`, rehechos en la CPU): mismo resultado, más memoria.
`PDFCAD_SIN_INSTANCING=1` fuerza ese camino (para comparar).
"""
from __future__ import annotations

import os

import numpy as np
from PySide6 import QtCore
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram

from nucleo import instancias3d as I3
from ui.comun import visor3d_shaders as SH

GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
PASO_INST = I3.CAMPOS_INST * 4
MODO = {I3.SEG: 0.0, I3.TAPA: 1.0, I3.ESFERA: 2.0}
ATRIBUTOS = ("aBase", "iP0", "iL0", "iA0", "iB0", "iP1", "iL1", "iA1", "iB1", "iCol", "iMisc")
# (byte, tamaño) de cada atributo de instancia dentro de una fila (ver `instancias3d`)
PUNTEROS = ((0, 3), (12, 3), (24, 3), (36, 4), (52, 3), (64, 3), (76, 3), (88, 4), (104, 4), (120, 4))

VERT = SH.VERT_INST


def soportado(ctx):
    """¿El contexto dibuja instancias? (OpenGL ≥ 3.3 o GL_ARB_instanced_arrays)."""
    if os.environ.get("PDFCAD_SIN_INSTANCING") == "1":
        return False
    try:
        fmt = ctx.format()
        if (fmt.majorVersion(), fmt.minorVersion()) >= (3, 3):
            return True
        return bool(ctx.hasExtension(QtCore.QByteArray(b"GL_ARB_instanced_arrays")))
    except Exception:
        return False


class Instanciador:
    """Programa + buffers de las instancias de la escena. `RuntimeError` si no se puede."""

    def __init__(self, padre, ctx, frag):
        self.ef = ctx.extraFunctions()
        p = QOpenGLShaderProgram(padre)
        if not (p.addShaderFromSourceCode(QOpenGLShader.Vertex, VERT)
                and p.addShaderFromSourceCode(QOpenGLShader.Fragment, frag)):
            raise RuntimeError(p.log())
        for k, nombre in enumerate(ATRIBUTOS):
            p.bindAttributeLocation(nombre, k)
        if not p.link():
            raise RuntimeError(p.log())
        self.prog = p
        self._unidad = {}                    # clave → (buffer, vértices)
        self._filas = {}                     # clave → (buffer, instancias)

    def _buffer(self, datos):
        datos = np.ascontiguousarray(datos, np.float32)
        b = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        b.create(); b.bind()
        b.allocate(datos.tobytes(), datos.nbytes)
        b.release()
        return b

    def subir(self, instancias):
        for b, _n in self._filas.values():
            b.destroy()
        self._filas = {}
        for clave, F in (instancias or {}).items():
            if not len(F):
                continue
            if clave not in self._unidad:
                u = I3.malla_unidad(*clave)
                self._unidad[clave] = (self._buffer(u), len(u))
            self._filas[clave] = (self._buffer(F), len(F))

    def liberar(self):
        for b, _n in list(self._filas.values()) + list(self._unidad.values()):
            b.destroy()
        self._filas, self._unidad = {}, {}

    def dibujar(self, uniformes):
        """Dibuja todo; `uniformes(prog)` pone los mismos uniformes que el programa de siempre."""
        if not self._filas:
            return
        p, ef = self.prog, self.ef
        p.bind()
        uniformes(p)
        p.setUniformValue1f("uAlfa", 1.0)
        try:
            for clave, (bf, n) in self._filas.items():
                bu, nv = self._unidad[clave]
                p.setUniformValue1f("uModo", MODO[clave[0]])
                bu.bind()
                p.enableAttributeArray(0)
                p.setAttributeBuffer(0, GL_FLOAT, 0, 3, 12)
                ef.glVertexAttribDivisor(0, 0)
                bf.bind()
                for k, (off, tam) in enumerate(PUNTEROS, start=1):
                    p.enableAttributeArray(k)
                    p.setAttributeBuffer(k, GL_FLOAT, off, tam, PASO_INST)
                    ef.glVertexAttribDivisor(k, 1)
                ef.glDrawArraysInstanced(GL_TRIANGLES, 0, nv, n)
                bf.release()
        finally:
            for k in range(len(ATRIBUTOS)):        # nada de esto queda para el resto del cuadro
                ef.glVertexAttribDivisor(k, 0)
                p.disableAttributeArray(k)
            p.release()
