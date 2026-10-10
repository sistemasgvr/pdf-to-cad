"""Visor 3D (QOpenGLWidget + shaders de Qt; sin dependencias nuevas).

Dibuja una `modelo3d.Escena`: opacos, transparentes (abandonadas, bancoductos) y el
suelo semitransparente. Navegación como Civil 3D: rueda = zoom, botón central =
desplazar, Shift + central = girar; además, para quien no tiene botón central,
arrastrar con el izquierdo = girar y con el derecho (o Ctrl + izquierdo) = desplazar.
Clic = elegir, doble clic = encuadrar lo que hay bajo el cursor (o todo).

El resaltado (selección y lo que está bajo el cursor) va por uniformes: cada vértice
lleva el id de su objeto, así elegir no reconstruye nada.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from nucleo import mallas3d as M
from ui.comun.cubo_vistas import CuboVistas

GL_TRIANGLES = 0x0004
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_ZERO = 0
GL_ONE = 1
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100
GL_FLOAT = 0x1406
GL_MULTISAMPLE = 0x809D
PASO = M.CAMPOS * 4

_VERT = """
#version 120
attribute vec3 aPos; attribute vec3 aNor; attribute vec4 aCol; attribute float aId;
attribute vec3 aEje; attribute float aRadio;
uniform mat4 uMvp; uniform float uSel; uniform float uHov;
uniform vec3 uOjo; uniform float uPxMundo; uniform float uMinPx;
varying vec4 vCol; varying vec3 vNor; varying float vEstado;
void main() {
    vec3 p = aPos;
    if (aRadio > 0.0) {    // tubería: nunca más fina que uMinPx de radio en pantalla
        float minimo = uMinPx * uPxMundo * distance(uOjo, aEje);
        p = aEje + (aPos - aEje) * max(1.0, minimo / aRadio);
    }
    gl_Position = uMvp * vec4(p, 1.0);
    vNor = aNor;
    vCol = aCol;
    vEstado = 0.0;
    if (aId > 0.5 && abs(aId - uHov) < 0.5) vEstado = 1.0;
    if (aId > 0.5 && abs(aId - uSel) < 0.5) vEstado = 2.0;
}
"""
_FRAG = """
#version 120
uniform vec3 uLuz; uniform vec4 uResalte; uniform float uAlfa;
varying vec4 vCol; varying vec3 vNor; varying float vEstado;
void main() {
    vec3 n = normalize(vNor);
    float l = 0.38 + 0.62 * abs(dot(n, normalize(uLuz)));
    vec3 c = vCol.rgb * l;
    if (vEstado > 1.5) c = mix(c, uResalte.rgb, 0.6);
    else if (vEstado > 0.5) c = mix(c, vec3(1.0), 0.35);
    gl_FragColor = vec4(c, vCol.a * uAlfa);
}
"""

RADIO_MIN_PX = 1.0      # tuberías: radio mínimo en pantalla (~2 px de ancho; no desaparecen al alejar)
DIST_MIN_FT = 1.0       # la cámara no se acerca más que esto a su objetivo: de ahí en más AVANZA
ZOOM_PASO = 0.95        # cada «clic» de la rueda acerca un 5 % (8 % y 15 % eran muy sensibles)
GIRO_DEG_PX = (0.22, 0.16)   # grados de giro por píxel arrastrado (horizontal, vertical)
DESPLAZAR = 0.6         # el modelo se mueve el 60 % de lo que se mueve el ratón (1:1 era muy sensible)
PISO_DESPLAZAR = 0.005  # de muy cerca, desplazar nunca baja de esta fracción del modelo
ANIM_MS, ANIM_PASOS = 240, 12   # giro animado del cubo de vistas

VISTAS = {"arriba": (-90.0, 89.5), "frente": (-90.0, 0.0), "lateral": (0.0, 0.0), "iso": (-55.0, 30.0)}


def _np(m):
    """QMatrix4x4 → numpy 4×4 (fila-mayor)."""
    return np.array(m.data(), float).reshape(4, 4).T


class Camara:
    def __init__(self):
        self.objetivo = np.zeros(3)
        self.dist = 100.0
        self.yaw, self.pitch = VISTAS["arriba"]        # por defecto: planta, como el plano
        self.fov = 40.0

    def ojo(self):
        y, p = math.radians(self.yaw), math.radians(self.pitch)
        return self.objetivo + self.dist * np.array([math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)])

    def ejes(self):
        """(derecha, arriba) de la pantalla en el mundo."""
        f = self.objetivo - self.ojo(); f /= np.linalg.norm(f)
        der = np.cross(f, [0.0, 0.0, 1.0])
        if np.linalg.norm(der) < 1e-6:
            y = math.radians(self.yaw)
            der = np.array([-math.sin(y), math.cos(y), 0.0])
        der /= np.linalg.norm(der)
        return der, np.cross(der, f)

    def matriz(self, aspecto, radio):
        proj = QtGui.QMatrix4x4()
        cerca = max(self.dist * 0.002, 0.05)
        proj.perspective(self.fov, max(aspecto, 1e-3), cerca, self.dist + radio * 4.0 + 100.0)
        vista = QtGui.QMatrix4x4()
        o, t = self.ojo(), self.objetivo
        _der, arriba = self.ejes()
        vista.lookAt(QtGui.QVector3D(*o), QtGui.QVector3D(*t), QtGui.QVector3D(*arriba))
        return proj * vista

    def encuadrar(self, lo, hi):
        lo, hi = np.asarray(lo, float), np.asarray(hi, float)
        self.objetivo = (lo + hi) / 2.0
        radio = max(float(np.linalg.norm(hi - lo)) / 2.0, 2.0)
        self.dist = radio / math.sin(math.radians(self.fov) / 2.0) * 1.05


class Visor3D(QOpenGLWidget):
    elegido = QtCore.Signal(int)        # id del objeto (0 = nada)
    doble = QtCore.Signal(int)
    sobre = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        fmt = QtGui.QSurfaceFormat(); fmt.setSamples(4); fmt.setDepthBufferSize(24)
        self.setFormat(fmt)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.cam = Camara()
        self.escena = None
        self.ver_suelo, self.opacidad_suelo = True, 0.18
        self.sel_id = 0
        self.hov_id = 0
        self.fondo = QtGui.QColor(40, 44, 52)
        self.resalte = QtGui.QColor(255, 214, 51)
        self.error = ""
        self._prog = None
        self._vbos = {}
        self._sucio = False
        self._press = None
        self._arrastre = False
        self._t_hover = QtCore.QTimer(self, singleShot=True, interval=40, timeout=self._hover)
        self.cubo = CuboVistas()
        self.oscuro = True
        self._cubo_press = None
        self._anim = None
        self._t_anim = QtCore.QTimer(self, interval=ANIM_MS // ANIM_PASOS, timeout=self._animar_paso)
        self._pos_hover = None

    # ── datos ──
    def set_escena(self, escena, encuadrar=False):
        self.escena = escena
        self._sucio = True
        if encuadrar and escena is not None and not escena.vacia:
            self.encuadrar()
        self.update()

    def radio(self):
        if self.escena is None:
            return 100.0
        lo, hi = np.asarray(self.escena.caja[0], float), np.asarray(self.escena.caja[1], float)
        return max(float(np.linalg.norm(hi - lo)) / 2.0, 10.0)

    def encuadrar(self, caja=None):
        if caja is None:
            if self.escena is None or self.escena.vacia:
                return
            caja = self.escena.caja
        self.cam.encuadrar(caja[0], caja[1])
        self.update()

    def vista(self, nombre):
        self.cam.yaw, self.cam.pitch = VISTAS[nombre]
        self.encuadrar()

    def reiniciar(self):
        """Vista inicial: isométrica y todo encuadrado."""
        self.cam = Camara()
        self.sel_id = self.hov_id = 0
        self.encuadrar()

    def set_seleccion(self, ident):
        self.sel_id = int(ident or 0)
        self.update()

    # ── OpenGL ──
    def initializeGL(self):
        try:
            self.f = self.context().functions()
            p = QOpenGLShaderProgram(self)
            if not (p.addShaderFromSourceCode(QOpenGLShader.Vertex, _VERT)
                    and p.addShaderFromSourceCode(QOpenGLShader.Fragment, _FRAG)):
                raise RuntimeError(p.log())
            for k, nombre in enumerate(("aPos", "aNor", "aCol", "aId", "aEje", "aRadio")):
                p.bindAttributeLocation(nombre, k)
            if not p.link():
                raise RuntimeError(p.log())
            self._prog = p
            self._vao = QOpenGLVertexArrayObject(self)
            self._vao.create()                   # se enlaza solo mientras se dibuja el modelo
            self.f.glEnable(GL_DEPTH_TEST)
            self.f.glEnable(GL_MULTISAMPLE)
            # El alfa del framebuffer queda en 1: si no, Qt compone el widget con el fondo de
            # la ventana y lo semitransparente (suelo, abandonadas) cambia de color.
            self.f.glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ONE)
        except Exception as e:                                # sin OpenGL 2.1: lo dice la ventana
            self.error = str(e) or "OpenGL"
            self._prog = None

    def _subir(self):
        for b, _n in self._vbos.values():
            b.destroy()
        self._vbos = {}
        if self.escena is None:
            return
        for clave in ("opacos", "transparentes", "suelo"):
            datos = np.ascontiguousarray(getattr(self.escena, clave), np.float32)
            if not len(datos):
                continue
            b = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            b.create(); b.bind()
            b.allocate(datos.tobytes(), datos.nbytes)
            b.release()
            self._vbos[clave] = (b, len(datos))
        self._sucio = False

    def _dibujar(self, clave, alfa):
        if clave not in self._vbos:
            return
        b, n = self._vbos[clave]
        p = self._prog
        b.bind()
        for k, (off, tam) in enumerate(((0, 3), (12, 3), (24, 4), (40, 1), (44, 3), (56, 1))):
            p.enableAttributeArray(k)
            p.setAttributeBuffer(k, GL_FLOAT, off, tam, PASO)
        p.setUniformValue1f("uAlfa", float(alfa))
        self.f.glDrawArrays(GL_TRIANGLES, 0, n)
        b.release()

    def paintGL(self):
        c = self.fondo
        if self._prog is None:
            return
        f = self.f
        # QPainter (cubo de vistas) cambia el estado de OpenGL: se repone en cada cuadro.
        f.glEnable(GL_DEPTH_TEST)
        f.glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ONE)
        f.glClearColor(c.redF(), c.greenF(), c.blueF(), 1.0)
        f.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self.escena is None or self.escena.vacia:
            return
        if self._sucio:
            self._subir()
        p = self._prog
        if self._vao.isCreated():
            self._vao.bind()
        p.bind()
        dpr = self.devicePixelRatioF()
        f.glViewport(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        p.setUniformValue("uMvp", self.cam.matriz(self.width() / max(self.height(), 1), self.radio()))
        p.setUniformValue1f("uSel", float(self.sel_id))
        p.setUniformValue1f("uHov", float(self.hov_id))
        p.setUniformValue("uOjo", QtGui.QVector3D(*self.cam.ojo()))
        p.setUniformValue1f("uPxMundo", 2.0 * math.tan(math.radians(self.cam.fov) / 2.0) / max(self.height(), 1))
        p.setUniformValue1f("uMinPx", RADIO_MIN_PX)
        luz = self.cam.ojo() - self.cam.objetivo + np.array([0.0, 0.0, self.cam.dist * 0.6])
        p.setUniformValue("uLuz", QtGui.QVector3D(*luz))
        r = self.resalte
        p.setUniformValue("uResalte", QtGui.QVector4D(r.redF(), r.greenF(), r.blueF(), 1.0))
        f.glDisable(GL_BLEND)
        self._dibujar("opacos", 1.0)
        f.glEnable(GL_BLEND)
        f.glDepthMask(False)
        self._dibujar("transparentes", 1.0)
        if self.ver_suelo:
            self._dibujar("suelo", self.opacidad_suelo)
        f.glDepthMask(True)
        for k in range(6):                       # QPainter (cubo) no debe heredar nuestros atributos
            p.disableAttributeArray(k)
        p.release()
        if self._vao.isCreated():
            self._vao.release()
        f.glDisable(GL_DEPTH_TEST)                       # el cubo va ENCIMA del modelo
        pintor = QtGui.QPainter(self)
        self.cubo.dibujar(pintor, self.width(), self.cam, self.oscuro)
        pintor.end()

    # ── elegir ──
    def rayo(self, x, y):
        """(origen, dirección) del rayo bajo el punto (x, y) del widget."""
        m = _np(self.cam.matriz(self.width() / max(self.height(), 1), self.radio()))
        inv = np.linalg.inv(m)
        nx, ny = 2.0 * x / max(self.width(), 1) - 1.0, 1.0 - 2.0 * y / max(self.height(), 1)
        a = inv @ [nx, ny, -1.0, 1.0]; b = inv @ [nx, ny, 1.0, 1.0]
        a, b = a[:3] / a[3], b[:3] / b[3]
        return a, b - a

    def id_en(self, x, y):
        if self.escena is None or not len(self.escena.picks) or not len(self.escena.picks[3]):
            return 0
        o, d = self.rayo(x, y)
        return M.elegir(self.escena.picks, o, d, r_min=self.cam.dist * 0.006)

    def _hover(self):
        if self._pos_hover is None:
            return
        i = self.id_en(self._pos_hover.x(), self._pos_hover.y())
        if i != self.hov_id:
            self.hov_id = i
            self.update()
            self.sobre.emit(i)

    # ── ratón y teclado ──
    def mousePressEvent(self, e):
        obj = self.cubo.que_hay(e.position()) if self.escena is not None else None
        if obj and e.button() == QtCore.Qt.LeftButton:
            self._cubo_press = obj
            self._press = (e.position(), e.button(), e.modifiers())
            self._ultimo = e.position()
            self._arrastre = False
            return
        self._cubo_press = None
        self._press = (e.position(), e.button(), e.modifiers())
        self._ultimo = e.position()
        self._arrastre = False
        self.setFocus()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._press is None or e.buttons() == QtCore.Qt.NoButton:
            obj = self.cubo.que_hay(pos)
            if obj != self.cubo.sobre:
                self.cubo.sobre = obj
                self.setCursor(QtCore.Qt.PointingHandCursor if obj else QtCore.Qt.ArrowCursor)
                self.update()
            if obj:                                       # sobre el cubo: nada del modelo
                if self.hov_id:
                    self.hov_id = 0
                    self.sobre.emit(0)
                return
            self._pos_hover = pos
            self._t_hover.start()
            return
        if not self._arrastre and (pos - self._press[0]).manhattanLength() < 4:
            return
        self._arrastre = True
        dx, dy = pos.x() - self._ultimo.x(), pos.y() - self._ultimo.y()
        self._ultimo = pos
        b, mods = e.buttons(), e.modifiers()
        girar = (b & QtCore.Qt.LeftButton and not mods & QtCore.Qt.ControlModifier) or \
                (b & QtCore.Qt.MiddleButton and mods & QtCore.Qt.ShiftModifier) or self._cubo_press
        if girar:
            self.cam.yaw -= dx * GIRO_DEG_PX[0]
            self.cam.pitch = max(-89.5, min(89.5, self.cam.pitch + dy * GIRO_DEG_PX[1]))
        else:
            der, arriba = self.cam.ejes()
            k = self._pies_por_px()
            self.cam.objetivo = self.cam.objetivo - der * dx * k + arriba * dy * k
        self.update()

    def mouseReleaseEvent(self, e):
        if self._cubo_press is not None:
            if not self._arrastre:
                destino = self.cubo.vista_de(self._cubo_press, self.cam.pitch)
                if destino:
                    self.animar(*destino)
            self._cubo_press = self._press = None
            return
        if self._press is not None and not self._arrastre and self._press[1] == QtCore.Qt.LeftButton:
            self.elegido.emit(self.id_en(e.position().x(), e.position().y()))
        self._press = None

    def animar(self, yaw, pitch):
        """Gira la cámara hasta (yaw, pitch) en un instante (por el camino más corto)."""
        dy = (yaw - self.cam.yaw + 180.0) % 360.0 - 180.0
        self._anim = (self.cam.yaw, self.cam.pitch, dy, pitch - self.cam.pitch, 0)
        self._t_anim.start()

    def _animar_paso(self):
        y0, p0, dy, dp, k = self._anim
        k += 1
        t = k / ANIM_PASOS
        t = t * t * (3 - 2 * t)                         # suave al empezar y al terminar
        self.cam.yaw, self.cam.pitch = y0 + dy * t, p0 + dp * t
        self._anim = (y0, p0, dy, dp, k)
        if k >= ANIM_PASOS:
            self._t_anim.stop()
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self.cubo.que_hay(e.position()):
            return
        if e.button() == QtCore.Qt.LeftButton:
            self.doble.emit(self.id_en(e.position().x(), e.position().y()))
        elif e.button() == QtCore.Qt.MiddleButton:            # como AutoCAD: doble clic en la rueda
            self._press = None
            self.encuadrar()

    def _pies_por_px(self):
        """Cuánto se mueve el objetivo por píxel al desplazar: el tamaño de un píxel a la
        distancia de la cámara, pero nunca menos que una fracción del modelo (de muy
        cerca el desplazamiento dejaba de moverse)."""
        d = max(self.cam.dist, self.radio() * PISO_DESPLAZAR)
        return DESPLAZAR * d * math.tan(math.radians(self.cam.fov) / 2.0) * 2.0 / max(self.height(), 1)

    def zoom(self, pasos, x=None, y=None):
        """Acercar (pasos > 0) / alejar hacia el punto bajo el cursor (x, y), como Civil 3D.
        Al llegar a `DIST_MIN_FT` la cámara AVANZA (lleva el objetivo hacia adelante) en vez
        de quedarse trabada."""
        f = ZOOM_PASO ** pasos
        cam = self.cam
        if x is not None and y is not None:
            o, d = self.rayo(x, y)
            d = d / np.linalg.norm(d)
            adelante = cam.objetivo - cam.ojo()
            adelante /= np.linalg.norm(adelante)
            den = float(np.dot(d, adelante))
            if abs(den) > 1e-6:                  # punto del cursor en el plano del objetivo
                p = o + d * float(np.dot(cam.objetivo - o, adelante)) / den
                cam.objetivo = cam.objetivo + (p - cam.objetivo) * (1.0 - f)
        nueva = cam.dist * f
        if nueva < DIST_MIN_FT:
            adelante = cam.objetivo - cam.ojo()
            adelante /= np.linalg.norm(adelante)
            avance = max(cam.dist - nueva, self.radio() * 0.01) if pasos > 0 else 0.0
            cam.objetivo = cam.objetivo + adelante * avance
            nueva = DIST_MIN_FT
        cam.dist = nueva
        self.update()

    def wheelEvent(self, e):
        self.zoom(e.angleDelta().y() / 120.0, e.position().x(), e.position().y())

    def leaveEvent(self, e):
        self._pos_hover = None
        if self.hov_id:
            self.hov_id = 0
            self.update()
            self.sobre.emit(0)
        super().leaveEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (QtCore.Qt.Key_Home, QtCore.Qt.Key_F):
            self.encuadrar()
        elif k in (QtCore.Qt.Key_Plus, QtCore.Qt.Key_Equal):
            self.zoom(1)
        elif k == QtCore.Qt.Key_Minus:
            self.zoom(-1)
        else:
            super().keyPressEvent(e)
