"""Un aro que gira en el control que el usuario pulsó mientras lo que lanzó sigue en marcha (2026-11-21, pedido del
usuario: «cada botoncito, cada acción tiene que mostrar un loader… si no, pienso que ya se bloqueó»).

Cómo funciona (un solo filtro de eventos para TODA la aplicación, sin tocar cada botón):
  · al soltar el ratón (o Espacio/Enter) sobre un botón activo se abre una «ventana de clic»: lo que empiece en
    `nucleo.actividad` durante el manejador del clic (la capa «Cargando…», un trabajo en otro proceso o hilo…) queda
    ligado a ese botón;
  · si el manejador bloquea la ventana más de `QUIETA_S`, el vigía (`vigia_carga`) pinta el aro aunque no corra
    ningún evento; si el trabajo sigue en otro proceso, el aro gira solo;
  · el aro se va cuando termina lo ligado (con `GRACIA_MS` de margen: un paso que acaba y lanza el siguiente no
    parpadea) o a los `MAX_S` (por si alguien olvidó avisar que terminó).
Solo se marca la acción de verdad: no las casillas, selectores ni botones con menú desplegable."""
from __future__ import annotations

import functools
import threading
import time
import weakref

import shiboken6
from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import actividad
from ui.comun import theme as _theme
from ui.comun import vigia_carga

QUIETA_S = vigia_carga.QUIETA_S      # el manejador bloquea tanto → el vigía pinta el aro
GRACIA_MS = 450                      # lo ligado terminó: se espera por si lanza el siguiente paso
MAX_S = 900.0                        # tope: un aviso de fin que nunca llegó
GIRO_MS = 16
SIN_ARO = "sinAro"                   # propiedad True en un botón que nunca lleva aro
CON_ARO = "conAro"                   # propiedad True en un botón conmutable que sí lo lleva


def sin_aro_por(w, estado: bool = True):
    """Por qué NO lleva aro (texto corto), o None si es un botón de acción. `estado=False` ignora si ahora está
    activo/visible (para inventariar los botones de paneles que aún no se ven)."""
    if not isinstance(w, QtWidgets.QAbstractButton):
        return "no es un botón"
    if w.objectName().startswith("qt_"):
        return "control del sistema (cerrar, flotar…)"
    if estado and not w.isEnabled():
        return "apagado"
    if estado and not w.isVisible():
        return "oculto"
    if isinstance(w, QtWidgets.QCheckBox):
        return "casilla (cambia un ajuste al instante)"
    if isinstance(w, QtWidgets.QRadioButton):
        return "selector (cambia un ajuste al instante)"
    if w.property(SIN_ARO):
        return "marcado sin aro"
    if w.isCheckable() and not w.property(CON_ARO):
        return "conmutador (alterna un modo)"
    if isinstance(w, QtWidgets.QToolButton) and w.popupMode() == QtWidgets.QToolButton.InstantPopup and w.menu():
        return "abre un menú (la acción es la del menú)"
    return None


def marcable(w) -> bool:
    """¿Es un botón de ACCIÓN (el que merece un aro)?"""
    return sin_aro_por(w) is None


def _seguro(f):
    """Un widget que Qt ya borró (la barra se rehízo, el diálogo se cerró) no debe romper la acción del usuario:
    el aro es un adorno y nunca puede ser la causa de un «Acción interrumpida» (2026-11-21)."""
    @functools.wraps(f)
    def envoltura(*a, **k):
        try:
            return f(*a, **k)
        except RuntimeError:                           # «Internal C++ object (…) already deleted»
            return None
    return envoltura


class _Aro(QtWidgets.QWidget):
    """Hijo transparente del botón: dibuja el aro y no come el ratón."""

    def __init__(self, boton):
        super().__init__(boton)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self._angulo = 0.0
        self.setGeometry(boton.rect())
        boton.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def avanzar(self):
        self._angulo = (self._angulo + 14.0) % 360.0
        self.update()

    @_seguro
    def paintEvent(self, _ev):
        b = self.parent()
        r = self.rect()
        if r.isEmpty():
            return
        solo_icono = isinstance(b, QtWidgets.QToolButton) and not b.text().strip()
        d = min(r.width(), r.height())
        if solo_icono or d <= 40 or r.width() <= 60:
            lado = max(12.0, min(d - 4.0, 30.0))
            centro = QtCore.QPointF(r.center())
        else:                                          # botón con texto: un aro chico a la derecha
            lado = 16.0
            centro = QtCore.QPointF(r.right() - 14.0, r.center().y())
        caja = QtCore.QRectF(centro.x() - lado / 2, centro.y() - lado / 2, lado, lado)
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        velo = QtGui.QColor(t.surface)
        velo.setAlpha(150)
        p.fillRect(r, velo)                            # el control se ve «ocupado»
        pista = QtGui.QColor(t.accent)
        pista.setAlpha(60)
        p.setPen(QtGui.QPen(pista, 2.4))
        p.drawEllipse(caja)
        p.setPen(QtGui.QPen(QtGui.QColor(t.accent), 2.4, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        p.drawArc(caja, int(-self._angulo * 16), 100 * 16)
        p.end()


class _Marca:
    """El aro de UN botón y lo que lo mantiene."""

    def __init__(self, boton):
        self.boton = weakref.ref(boton)
        self.aro = None
        self.t0 = time.perf_counter()
        self.latido = self.t0
        self.fichas = set()
        self.ventana = True                            # aún dentro del manejador del clic
        self.fin_gracia = None

    # ── lo que el vigía necesita (`vigia_carga.vigilar`) ─────────────────
    def boton_vivo(self):
        b = self.boton()
        return b if b is not None and shiboken6.isValid(b) else None

    def aro_vivo(self):
        if self.aro is not None and not shiboken6.isValid(self.aro):
            self.aro = None
        return self.aro

    def vigilada(self) -> bool:
        return self.boton_vivo() is not None and self.ventana

    @_seguro
    def pintar_desde_el_vigia(self):
        if time.perf_counter() - self.latido < QUIETA_S or not self.ventana:
            return
        if threading.current_thread() is not threading.main_thread() or vigia_carga.pintando_en_la_pila():
            return                                     # (a mitad de un import o de un pintado: no se toca nada)
        self.mostrar(repintar=True)

    @_seguro
    def mostrar(self, repintar=False):
        b = self.boton_vivo()
        if b is None:
            return
        aro = self.aro_vivo()
        if aro is None:
            aro = self.aro = _Aro(b)
        if not aro.isVisible():
            aro.show()
            aro.raise_()
        self.latido = time.perf_counter()
        if repintar:
            aro.repaint()

    def quitar(self):
        aro, self.aro = self.aro_vivo(), None
        if aro is not None:
            try:
                aro.hide()
                aro.deleteLater()
            except RuntimeError:
                pass


class AccionCargando(QtCore.QObject):
    _desde_otro_hilo = QtCore.Signal(str, int, str)

    def __init__(self, app):
        super().__init__(app)
        self._marcas = {}                              # id(boton) → _Marca
        self._ventana = None                           # la marca cuyo manejador de clic corre ahora
        self._giro = QtCore.QTimer(self, interval=GIRO_MS)
        self._giro.timeout.connect(self._girar)
        self._desde_otro_hilo.connect(self._actividad, QtCore.Qt.QueuedConnection)
        self._dejar = actividad.escuchar(self._oir)
        app.installEventFilter(self)

    @_seguro
    def _oir(self, que, ficha, nombre):
        if threading.current_thread() is threading.main_thread():
            self._actividad(que, ficha, nombre)        # en el acto: así cae dentro de la ventana del clic
        else:
            self._desde_otro_hilo.emit(que, ficha, nombre)

    # ── clic ─────────────────────────────────────────────────────────────
    @_seguro
    def eventFilter(self, obj, ev):
        et = ev.type()
        if et == QtCore.QEvent.MouseButtonRelease and ev.button() == QtCore.Qt.LeftButton:
            self._clic(obj, ev.position().toPoint())
        elif et == QtCore.QEvent.KeyPress and ev.key() in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Return,
                                                            QtCore.Qt.Key_Enter) and not ev.isAutoRepeat():
            self._clic(obj, None)
        return False

    @_seguro
    def _clic(self, w, pos):
        if not isinstance(w, QtWidgets.QWidget):
            return
        b = w
        while b is not None and not isinstance(b, QtWidgets.QAbstractButton):
            b = b.parentWidget()
        if b is None or not marcable(b):
            return
        if pos is not None and b is w and not b.rect().contains(pos):
            return                                     # soltó fuera: no es un clic
        previa = self._marcas.get(id(b))
        if previa is not None:
            self._soltar(previa)
        marca = _Marca(b)
        self._marcas[id(b)] = marca
        self._ventana = marca
        vigia_carga.vigilar(marca)
        QtCore.QTimer.singleShot(0, self, lambda m=marca: self._fin_de_ventana(m))

    @_seguro
    def _fin_de_ventana(self, marca):
        """El manejador del clic ya volvió (o está dentro de un bucle local: lo ligado sigue contando)."""
        marca.ventana = False
        if self._ventana is marca:
            self._ventana = None
        self._revisar(marca)

    # ── actividad ligada ─────────────────────────────────────────────────
    @_seguro
    def _actividad(self, que, ficha, _nombre):
        if que == "inicia":
            marca = self._ventana
            if marca is None:                          # empezó tras el clic: va al último botón con aro vivo
                vivas = [m for m in self._marcas.values() if m.boton_vivo() is not None
                         and (m.aro_vivo() is not None or m.fichas)]
                marca = max(vivas, key=lambda m: m.t0, default=None)
            if marca is not None:
                marca.fichas.add(ficha)
                marca.fin_gracia = None
                marca.mostrar(repintar=True)
                self._arrancar_giro()
        else:
            for m in list(self._marcas.values()):
                if ficha in m.fichas:
                    m.fichas.discard(ficha)
                    self._revisar(m)

    @_seguro
    def _revisar(self, marca):
        if marca.boton_vivo() is None:
            self._soltar(marca)
            return
        if marca.ventana or marca.fichas:
            if marca.fichas:
                marca.mostrar()
                self._arrancar_giro()
            return
        if marca.aro_vivo() is None:                   # el manejador volvió pronto y nada quedó en marcha
            self._soltar(marca)
            return
        if marca.fin_gracia is None:
            marca.fin_gracia = time.perf_counter() + GRACIA_MS / 1000.0
        self._arrancar_giro()

    def _arrancar_giro(self):
        if not self._giro.isActive():
            self._giro.start()

    @_seguro
    def _girar(self):
        ahora = time.perf_counter()
        for marca in list(self._marcas.values()):
            if marca.boton_vivo() is None:
                self._soltar(marca)
                continue
            aro = marca.aro_vivo()
            if aro is not None:
                aro.avanzar()
            if marca.fin_gracia is not None and not marca.fichas and ahora >= marca.fin_gracia:
                self._soltar(marca)
            elif ahora - marca.t0 > MAX_S:
                self._soltar(marca)
        if not self._marcas:
            self._giro.stop()

    def _soltar(self, marca):
        marca.quitar()
        for k, m in list(self._marcas.items()):
            if m is marca:
                del self._marcas[k]


_instancia = None


def instalar(app) -> AccionCargando:
    """Una vez por aplicación (`app_window.main`)."""
    global _instancia
    if _instancia is None:
        _instancia = AccionCargando(app)
    return _instancia
