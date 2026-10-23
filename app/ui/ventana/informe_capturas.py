"""Capturas AUTOMÁTICAS del informe (pedido del usuario 2026-10-23).

`Captura2D`: una vista del lienzo FUERA DE PANTALLA sobre la misma escena (líneas, buzones, marcas C-n,
insignias y etiquetas tal cual se ven), encuadrada en la caja de cada zona y dibujada en una imagen: no
toca la vista del usuario y cada captura tarda milisegundos. `mapa` = todo el dibujo con las zonas
numeradas encima.

`Captura3D`: usa la Vista 3D (la abre si hace falta y espera a que termine de armarse), pone la cámara en
isométrica sobre la zona, toma la imagen del framebuffer y deja la cámara como estaba. Sin OpenGL (o en
pruebas sin pantalla) no hay 3D: `preparar` devuelve el motivo y el informe sigue sin esas capturas.
"""
from __future__ import annotations

import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr

ANCHO, ALTO = 1400, 875            # px lógicos de cada captura (proporción = informe_datos.ASPECTO)
DENSIDAD = 1.5                     # px reales por px lógico: líneas y marcas más nítidas en el Word
CALIDAD_JPG = 75
ESPERA_3D_S = 600                  # tope para que la Vista 3D termine de armarse


def a_jpg(img, calidad=CALIDAD_JPG):
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)
    img.save(buf, "JPG", calidad)
    return bytes(buf.data())


class Captura2D:
    def __init__(self, win):
        self.win = win
        v = QtWidgets.QGraphicsView(win.canvas.scene())
        v.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        v.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        v.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        v.setFrameShape(QtWidgets.QFrame.NoFrame)
        v.setBackgroundBrush(QtGui.QColor(255, 255, 255))
        v.resize(ANCHO, ALTO)
        # Sin mostrarse, la vista no toma su tamaño (se queda en ~640 × 480 y el encuadre sale corrido): se
        # «muestra» sin pantalla y se cierra en `cerrar`.
        v.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        v.show()
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        self.vista = v

    def cerrar(self):
        self.vista.hide()
        self.vista.setScene(None)
        self.vista.deleteLater()

    def _dibujar(self, caja):
        x0, y0, x1, y1 = caja
        self.vista.fitInView(QtCore.QRectF(x0, y0, x1 - x0, y1 - y0), QtCore.Qt.KeepAspectRatio)
        img = QtGui.QImage(int(ANCHO * DENSIDAD), int(ALTO * DENSIDAD), QtGui.QImage.Format_RGB32)
        img.setDevicePixelRatio(DENSIDAD)
        img.fill(QtGui.QColor(255, 255, 255))
        p = QtGui.QPainter(img)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.vista.render(p, QtCore.QRectF(0, 0, ANCHO, ALTO), self.vista.viewport().rect())
        p.end()
        return img

    def zona(self, caja):
        return a_jpg(self._dibujar(caja))

    def mapa(self, caja_total, zonas):
        """Todo el dibujo con el recuadro y el número de cada zona."""
        x0, y0, x1, y1 = caja_total
        mx, my = (x1 - x0) * 0.04 + 1, (y1 - y0) * 0.04 + 1
        img = self._dibujar((x0 - mx, y0 - my, x1 + mx, y1 + my))
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        pluma = QtGui.QPen(QtGui.QColor(230, 90, 0), 3)
        f = QtGui.QFont("Arial"); f.setPixelSize(22); f.setBold(True)
        p.setFont(f)
        for z in zonas:
            a = self.vista.mapFromScene(QtCore.QPointF(z.caja[0], z.caja[1]))
            b = self.vista.mapFromScene(QtCore.QPointF(z.caja[2], z.caja[3]))
            r = QtCore.QRectF(QtCore.QPointF(a), QtCore.QPointF(b)).normalized()
            if r.width() < 14:
                r = QtCore.QRectF(r.center().x() - 7, r.center().y() - 7, 14, 14)
            p.setPen(pluma); p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(r)
            txt = str(z.numero)
            caja_txt = QtCore.QRectF(r.left(), r.top() - 30, max(30.0, 16.0 * len(txt) + 12), 28)
            p.fillRect(caja_txt, QtGui.QColor(230, 90, 0))
            p.setPen(QtGui.QColor(255, 255, 255))
            p.drawText(caja_txt, QtCore.Qt.AlignCenter, txt)
        p.end()
        return a_jpg(img)


class Captura3D:
    def __init__(self, win):
        self.win = win
        self.dlg = None
        self._cam = None

    def preparar(self, al_avanzar=None):
        """Abre la Vista 3D y espera la escena. Devuelve "" si se puede capturar, o el motivo."""
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.platformName() in ("offscreen", "minimal"):
            return _tr("sin pantalla no hay vista 3D")
        w = self.win
        self.dlg = w.abrir_vista3d()
        fin = time.perf_counter() + ESPERA_3D_S
        while (self.dlg._trabajo is not None or self.dlg.escena is None) and time.perf_counter() < fin:
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 100)
            if al_avanzar:
                al_avanzar()
            time.sleep(0.02)
        visor = self.dlg.visor
        if visor.error:
            return _tr("no se pudo iniciar OpenGL: {e}").format(e=visor.error)
        if self.dlg._trabajo is not None:
            return _tr("la vista 3D tardó demasiado en armarse")
        if self.dlg.escena is None or self.dlg.escena.vacia:
            return _tr("la escena 3D está vacía")
        c = visor.cam
        self._cam = (c.objetivo.copy(), c.dist, c.yaw, c.pitch)
        return ""

    def zona(self, caja, ft_per_px):
        from ui.comun.visor3d import VISTAS
        visor, esc = self.dlg.visor, self.dlg.escena
        o = np.asarray(esc.origen, float)
        x0, y0, x1, y1 = caja
        zlo, zhi = float(esc.caja[0][2]), float(esc.caja[1][2])
        lo = np.array([x0 * ft_per_px, -y1 * ft_per_px, zlo + o[2]]) - o
        hi = np.array([x1 * ft_per_px, -y0 * ft_per_px, zhi + o[2]]) - o
        visor.cam.yaw, visor.cam.pitch = VISTAS["iso"]
        visor.encuadrar((lo, hi))
        img = visor.grabFramebuffer()
        if img.width() > ANCHO * DENSIDAD:
            img = img.scaledToWidth(int(ANCHO * DENSIDAD), QtCore.Qt.SmoothTransformation)
        return a_jpg(img)

    def terminar(self):
        if self.dlg is not None and self._cam is not None:
            c = self.dlg.visor.cam
            c.objetivo, c.dist, c.yaw, c.pitch = self._cam
            self.dlg.visor.update()
