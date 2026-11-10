"""Dibujo del PERFIL LONGITUDINAL (pedido del usuario 2026-10-31, referencia «PROFILE 8 - 12 INCH MAIN»).

Como la vista de perfil de Civil 3D que arma `CREAR_PERFIL_RED`: marco con rejilla (cotas a los dos lados,
estaciones abajo), fila de tramos arriba («INSTALL … LF OF / NEW 8" … PIPE») con sus verticales de límite,
tubería con sus paredes, estructuras, terreno (EX. GRADE) a trazos, cruces como elipses con su rótulo y el
claro, callouts verticales en los nodos (arriba accesorios/estructuras/puntas, abajo codos y deflexiones) y el
título bajo la vista. Los datos los arma `nucleo/perfil_datos` (puro); aquí solo se dibuja.

Siempre completo y a su escala (2026-11-06): 1" de ploteo = los ppp de la pantalla (`_ppp`) × zoom, con la
exageración vertical del perfil; si no cabe, `AreaPerfil` pone barras. Lo que se pinta está en
`perfil_vista_dibujo` y el ratón/teclado en `perfil_vista_raton` (partido el 2026-11-08, tal cual).
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t
from ui.comun.perfil_vista_base import HUECO, LETRA_PT, M_ABA, M_ARR, M_DER, M_IZQ, PX_POR_PULGADA
from ui.comun.perfil_vista_dibujo import DibujoPerfilMixin
from ui.comun.perfil_vista_flujo import FlujoPerfilMixin
from ui.comun.perfil_vista_raton import RatonPerfilMixin
from ui.comun.theme import THEME_BUS, tokens


class VistaPerfil(DibujoPerfilMixin, RatonPerfilMixin, FlujoPerfilMixin, QtWidgets.QWidget):
    cotaCambiada = QtCore.Signal(int, float)      # índice de nodo, solera nueva (ft)
    flujoCambiado = QtCore.Signal(int, int, bool)  # paso, hacia (1 = B, -1 = A, 0 = automático), todo el perfil
    nodoElegido = QtCore.Signal(int)              # -1 = ninguno
    pasoElegido = QtCore.Signal(int)
    estacionHover = QtCore.Signal(float)          # NaN = el ratón salió del dibujo
    nodoHover = QtCore.Signal(int)                # -1 = ninguno
    ramalPedido = QtCore.Signal(int)              # clic en el rótulo de una T/Y/cruz: ver el perfil de su ramal

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMinimumHeight(160)
        self.p = None
        self.color = QtGui.QColor("#4f6bed")
        self.color_de = lambda j: QtGui.QColor("#888888")
        self.ve = None                            # exageración vertical (None = la del perfil: s / v)
        self._zoom = 1.0
        self._dx = 0.0                            # el perfil más angosto que el panel va centrado
        self._sel_nodo, self._sel_paso, self._hover = -1, -1, -1
        self._hover_flujo = -1                    # flecha del flujo bajo el ratón (`perfil_vista_flujo`)
        self._arrastre = None                     # (nodo, z) mientras se arrastra
        self._desplazando = None
        self._geo = None
        self._cursor_e = None                     # estación que llega del plano
        self.aviso_vacio = ""                     # texto del estado vacío (lo pone la ventana)
        self.alertas = []                         # nucleo/perfil_validar.Alerta
        self.con_ramal = set()                    # nodos cuyo rótulo abre el perfil de su ramal (enlace)
        self._zonas = []                          # [(QRectF del rótulo, nodo)] del último dibujo
        self.setAccessibleName(t("Perfil longitudinal"))
        THEME_BUS.changed.connect(self.update)

    # ------------------------------------------------------------------ datos

    def set_perfil(self, perfil, color=None, color_de=None, encuadrar=False):
        self.p = perfil
        if color is not None:
            self.color = QtGui.QColor(color)
        if color_de is not None:
            self.color_de = color_de
        if encuadrar:
            self._zoom = 1.0
        if perfil is None or not (0 <= self._sel_nodo < len(perfil.nodos)):
            self._sel_nodo = -1
        self._arrastre = None
        self._ajustar_tam()

    def exageracion(self):
        if self.ve:
            return self.ve
        return (self.p.s / self.p.v) if self.p else 1.0

    def set_exageracion(self, ve):
        self.ve = ve
        self._zoom = 1.0
        self._ajustar_tam()

    def encuadrar(self):
        self._zoom = 1.0
        self._ajustar_tam()

    def _area(self):
        """La QScrollArea que contiene la vista (o None)."""
        w = self.parentWidget()
        while w is not None and not isinstance(w, QtWidgets.QScrollArea):
            w = w.parentWidget()
        return w

    def _ajustar_tam(self):
        """Mínimo = el tamaño natural del perfil: si el panel es más chico, aparecen las barras."""
        if self.p and self.p.pasos:
            self._calcular()
            w, h = self._tam_natural
        else:
            w, h = 0, 160
        self.setMinimumSize(w, max(160, h))
        area = self._area()
        if area is not None:
            vp = area.viewport().size()
            self.resize(max(w, vp.width()), max(h, 160, vp.height()))
        self.update()

    def set_alertas(self, alertas):
        self.alertas = list(alertas or [])
        self.update()

    def alertas_de_nodo(self, k):
        return [a for a in self.alertas if a.nodo == k]

    def alertas_de_paso(self, i):
        return [a for a in self.alertas if a.paso == i and a.nodo < 0 and a.cruce < 0]


    def set_cursor(self, e):
        """Estación que señala el ratón en el PLANO (None = ninguna)."""
        if e != self._cursor_e:
            self._cursor_e = e
            self.update()

    def elegir_nodo(self, k):
        self._sel_nodo = k
        self.nodoElegido.emit(k)
        self.update()

    # ------------------------------------------------------------------ geometría

    def _ppp(self):
        """Píxeles por pulgada de ploteo en pantalla: los ppp lógicos de la pantalla del widget (siguen al
        escalado de Windows, como el resto de la interfaz); 96 si no los da."""
        try:
            d = float(self.logicalDpiX())
        except Exception:
            d = 0.0
        return d if d > 0 else PX_POR_PULGADA

    def _fuente(self, negrita=False, pt=LETRA_PT):
        f = QtGui.QFont(self.font())
        f.setPointSizeF(pt)
        f.setBold(negrita)
        return f

    def _bloque(self, lineas, fm):
        """(ancho, alto) de un callout VERTICAL (se lee de abajo arriba)."""
        largo = max((fm.horizontalAdvance(s) for s in lineas), default=0)
        return len(lineas) * fm.lineSpacing(), largo

    def _calcular(self):
        p = self.p
        fm = QtGui.QFontMetricsF(self._fuente())
        cm, cmen, em, emen = p.intervalos
        pad = max(5.0, (p.e_fin - p.e_ini) * 0.04)
        # sin estaciones antes del inicio (0+00): como en Civil 3D, la vista no empieza antes que el eje (2026-11-09)
        e_lo = max(math.floor((p.e_ini - pad) / emen) * emen, math.floor(p.e_ini / emen + 1e-9) * emen)
        e_hi = math.ceil((p.e_fin + pad) / emen) * emen
        z_lo = math.floor((p.z_min - 1.0) / cmen) * cmen
        z_hi = math.ceil((p.z_max + 1.0) / cmen) * cmen
        filas = max((len(c.lineas) for c in p.celdas), default=0)
        alto_fila = filas * fm.lineSpacing() + 2 * HUECO if filas else 0
        W = max(100.0, self.width() - M_IZQ - M_DER)
        H = max(60.0, self.height() - M_ARR - M_ABA)

        arriba = [self._bloque(n.lineas, fm)[1] for n in p.nodos if n.lineas and n.arriba]
        arriba += [self._bloque(v.lineas, fm)[1] for v in getattr(p, "valvulas", ())]
        arriba += [self._bloque(c.lineas, fm)[1] for c in p.cruces if c.encima]
        abajo = [self._bloque(n.lineas, fm)[1] for n in p.nodos if n.lineas and not n.arriba]
        abajo += [self._bloque(c.lineas, fm)[1] for c in p.cruces if not c.encima]
        h_arr = alto_fila + (max(arriba) + 3 * HUECO if arriba else HUECO)
        h_aba = max(abajo) + 3 * HUECO if abajo else HUECO
        ve = self.exageracion()
        # TAMAÑO FIJO (2026-11-06, pedido del usuario: «el perfil debe seguir siendo del mismo tamaño, activa
        # scroll»): la escala del perfil (1" = s ft) en la pantalla y su exageración; el panel no lo achica ni lo
        # cambia: si no cabe, la ventana pone barras de desplazamiento (`_ajustar_tam`).
        kx = self._ppp() / max(float(p.s or 20.0), 1e-6)
        self._ve_efectiva = ve
        kz = kx * ve
        kxz, kzz = kx * self._zoom, kz * self._zoom
        alto_d = (z_hi - z_lo) * kzz
        alto = h_arr + alto_d + h_aba
        self._tam_natural = (int(math.ceil((e_hi - e_lo) * kxz + M_IZQ + M_DER)),
                             int(math.ceil(alto + M_ARR + M_ABA)))
        self._dx = max(0.0, (W - (e_hi - e_lo) * kxz) / 2)   # más angosto: centrado
        marco = QtCore.QRectF(M_IZQ + self._dx, M_ARR, (e_hi - e_lo) * kxz, alto)
        vista = QtCore.QRectF(M_IZQ, M_ARR, W, H)
        self._geo = dict(e_lo=e_lo, e_hi=e_hi, z_lo=z_lo, z_hi=z_hi, kx=kx, kz=kz, marco=marco, vista=vista,
                         base=marco.top() + h_arr + alto_d, alto_fila=alto_fila, fm=fm, h_arr=h_arr)
        return self._geo

    def X(self, e):
        g = self._geo
        return g["marco"].left() + (e - g["e_lo"]) * g["kx"] * self._zoom

    def Z(self, z):
        g = self._geo
        return g["base"] - (z - g["z_lo"]) * g["kz"] * self._zoom

    def z_de(self, y):
        g = self._geo
        return g["z_lo"] + (g["base"] - y) / (g["kz"] * self._zoom)

    def e_de(self, x):
        g = self._geo
        return g["e_lo"] + (x - g["marco"].left()) / (g["kx"] * self._zoom)

    def _z_nodo(self, k):
        """Solera del recorrido en el nodo k (la del arrastre si se está moviendo)."""
        if self._arrastre and self._arrastre[0] == k:
            return self._arrastre[1]
        p = self.p
        if k < len(p.pasos):
            return p.pasos[k].z0
        return p.pasos[k - 1].z1

    def _z_paso(self, i):
        p = self.p
        z0, z1 = p.pasos[i].z0, p.pasos[i].z1
        if self._arrastre:
            k, z = self._arrastre
            if k == i:
                z0 = z
            if k == i + 1:
                z1 = z
        return z0, z1

    # ------------------------------------------------------------------ pintar

    def paintEvent(self, _ev):
        tk = tokens()
        pt = QtGui.QPainter(self)
        pt.setRenderHint(QtGui.QPainter.Antialiasing)
        pt.fillRect(self.rect(), QtGui.QColor(tk.grid_bg))
        if not self.p or not self.p.pasos:
            self._vacio(pt, tk)
            return
        g = self._calcular()
        marco = g["marco"]
        pt.setFont(self._fuente())
        self._rejilla(pt, tk, g)
        pt.save()
        pt.setClipRect(marco.intersected(g["vista"]))
        self._terreno(pt, tk)
        self._tuberia(pt, tk)
        self._cruces(pt, tk)
        self._flujo(pt, tk)
        self._alertas(pt, tk)
        self._fila(pt, tk, g)
        self._callouts(pt, tk, g)
        self._cursor(pt, tk, g)
        pt.restore()
        pt.save()
        pt.setClipRect(g["vista"].adjusted(-1, -1, 1, 1))
        pt.setPen(QtGui.QPen(QtGui.QColor(tk.text), 1.2))
        pt.setBrush(QtCore.Qt.NoBrush)
        pt.drawRect(marco)
        self._marcas_ab(pt, tk, marco)
        pt.restore()
        self._titulo(pt, tk, g)
        if self.hasFocus():                           # foco visible (teclado)
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.accent), 2))
            pt.setBrush(QtCore.Qt.NoBrush)
            pt.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)


class AreaPerfil(QtWidgets.QScrollArea):
    """El perfil a su tamaño natural con barras de desplazamiento (2026-11-06): el panel no lo achica."""

    def __init__(self, vista, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setWidget(vista)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.widget()._ajustar_tam()
