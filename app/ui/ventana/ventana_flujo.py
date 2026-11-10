"""Sentido del FLUJO en gravedad y presión (mezcla de `Main`; pedidos del usuario 2026-11-09: «indicar hacia dónde va
el fluido, de una manera fácil, en las propiedades de la utilidad y en el perfil»; también en presión, nunca en
eléctrico ni telecom). El dato: `pipe["flujo"]` (`nucleo/flujo`).

- Propiedades de una utilidad de GRAVEDAD o PRESIÓN, sección «Cotas»: «Flujo» = segmentado [Auto | ➜ | ➜] — las dos
  flechas apuntan como se ve la utilidad en el plano (de su inicio a su fin y al revés). «Auto» = en gravedad hacia el
  extremo más bajo; a presión, sin indicar. Con un sentido indicado, la utilidad elegida lleva flechas en el plano.
- Perfil: flecha redonda en cada tramo (`ui/comun/perfil_vista_flujo`); clic = invertir esa utilidad, clic derecho =
  hacia A / hacia B / automático (sin indicar), de esa utilidad o de todo el perfil.
Cada cambio es UN paso de deshacer. La contrapendiente del perfil (gravedad) se juzga con este sentido
(`perfil_validar`).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import flujo as FL
from nucleo.model import Z_MARK, network_kind
from traduccion.i18n import bind as _bind, t as _tr
from ui.comun.icons import icon
from ui.comun.theme import tokens
from ui.comun.ui_common import layer_qcolor

ICONO_PX = 18


def _flecha(angulo, color):
    """Icono de una flecha girada `angulo` grados (Y hacia abajo, como el lienzo)."""
    dpr = 2.0
    pm = QtGui.QPixmap(int(ICONO_PX * dpr), int(ICONO_PX * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    base = icon("mdi:arrow-right", color=color).pixmap(QtCore.QSize(ICONO_PX, ICONO_PX), dpr)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    p.translate(ICONO_PX / 2, ICONO_PX / 2)
    p.rotate(angulo)
    p.drawPixmap(QtCore.QRectF(-ICONO_PX / 2, -ICONO_PX / 2, ICONO_PX, ICONO_PX), base,
                 QtCore.QRectF(base.rect()))
    p.end()
    return pm


class FlujoMixin:
    # ------------------------------------------------------------------ propiedades de la utilidad

    def _flujo_construir(self):
        """El segmentado «Flujo» (lo pone `ventana_inspector_campos.reorganizar` en la sección Cotas)."""
        caja = QtWidgets.QFrame()
        caja.setObjectName("segmentado")
        lay = QtWidgets.QHBoxLayout(caja)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.btn_flujo = {}
        grupo = QtWidgets.QButtonGroup(caja)
        grupo.setExclusive(True)
        for sentido, texto, tip in (
                (FL.AUTO, "Auto", ""),                # su globo depende de la red (`_flujo_refrescar`)
                (FL.ADELANTE, "", "El fluido va del inicio al fin de la utilidad (en el sentido en que se dibujó)"),
                (FL.ATRAS, "", "El fluido va del fin al inicio de la utilidad")):
            b = QtWidgets.QPushButton()
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setAutoDefault(False)
            if texto:
                _bind(b, "setText", texto)
            if tip:
                _bind(b, "setToolTip", tip)
                _bind(b, "setAccessibleName", tip)
            b.setIconSize(QtCore.QSize(ICONO_PX, ICONO_PX))
            b.clicked.connect(lambda _=False, s=sentido: self.poner_flujo([self.sel_pipe], s))
            grupo.addButton(b)
            lay.addWidget(b)
            self.btn_flujo[sentido] = b
        lay.addStretch(1)
        self.box_flujo = caja
        self.lbl_flujo = QtWidgets.QLabel()
        _bind(self.lbl_flujo, "setText", "Flujo")
        return self.lbl_flujo, caja

    def _flujo_refrescar(self):
        """Al elegir otra utilidad: la fila solo en gravedad y presión, con su sentido y las flechas como se ve en el
        plano."""
        caja = getattr(self, "box_flujo", None)
        if caja is None:
            return
        i = getattr(self, "sel_pipe", -1)
        p = self.pipes[i] if 0 <= i < len(self.pipes) else None
        ver = FL.aplica(p)
        form = self.gprop.layout()
        if isinstance(form, QtWidgets.QFormLayout) and form.indexOf(caja) >= 0:
            form.setRowVisible(caja, ver)
        if not ver:
            return
        tk = tokens()
        auto = (_tr("Sin indicar: a presión la app no deduce hacia dónde va el fluido")
                if network_kind(p.get("layer") or "") == "pressure"
                else _tr("Automático: en el perfil, el fluido va hacia el extremo más bajo del recorrido"))
        self.btn_flujo[FL.AUTO].setToolTip(auto)
        self.btn_flujo[FL.AUTO].setAccessibleName(auto)
        ang = FL.rumbo_pantalla(p.get("pts") or []) or 0.0
        for sentido, giro in ((FL.ADELANTE, ang), (FL.ATRAS, ang + 180.0)):
            ico = QtGui.QIcon()
            ico.addPixmap(_flecha(giro, tk.text_muted), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            ico.addPixmap(_flecha(giro, tk.accent), QtGui.QIcon.Normal, QtGui.QIcon.On)
            self.btn_flujo[sentido].setIcon(ico)
        actual = FL.fijo(p)
        for sentido, b in self.btn_flujo.items():
            b.blockSignals(True)
            b.setChecked(sentido == actual)
            b.blockSignals(False)

    def poner_flujo(self, indices, sentido):
        """El sentido (1 / -1 / 0 = automático) en esas utilidades, en UN paso de deshacer. True si cambió algo."""
        cambios = [j for j in dict.fromkeys(indices) if 0 <= j < len(self.pipes)
                   and FL.aplica(self.pipes[j])
                   and FL.fijo(self.pipes[j]) != (sentido if sentido in (FL.ADELANTE, FL.ATRAS) else FL.AUTO)]
        if not cambios:
            self._flujo_refrescar()
            return False
        self._push()
        for j in cambios:
            FL.poner(self.pipes[j], sentido)
        self._dirty = True
        self._redraw()
        self._flujo_refrescar()
        return True

    # ------------------------------------------------------------------ perfil

    def perfil_flujo(self, i, hacia, todo=False):
        """Desde el perfil: el fluido va `hacia` B (1), A (-1) o automático (0) en la utilidad del paso `i` o, con
        `todo`, en todas las del recorrido (cada una según su sentido en el recorrido). UN paso de deshacer."""
        d = getattr(self, "_perfil_datos", None)
        if d is None or d.tipo not in FL.REDES:
            return False
        pasos = d.pasos if todo else ([d.pasos[i]] if 0 <= i < len(d.pasos) else [])
        valor = {}
        for ps in pasos:
            valor.setdefault(ps.pipe, FL.de_paso(hacia, ps.invertida))
        cambios = {j: v for j, v in valor.items() if 0 <= j < len(self.pipes) and FL.fijo(self.pipes[j]) != v}
        if not cambios:
            return False
        self._push()
        for j, v in cambios.items():
            FL.poner(self.pipes[j], v)
        self._dirty = True
        self._redraw()                                # el perfil se rehace solo (cambió el modelo)
        self._flujo_refrescar()
        return True

    # ------------------------------------------------------------------ plano

    def _flujo_en_plano(self, i):
        """Flechas en el plano de la utilidad elegida, si tiene un sentido indicado (a la mitad de cada tramo)."""
        p = self.pipes[i]
        sentido = FL.fijo(p)
        if not sentido or not FL.aplica(p):
            return
        sc = self.canvas.scene()
        col = layer_qcolor(p.get("layer"))
        # como en el perfil: un círculo del color de la utilidad con la flecha blanca (sobre la línea se lee)
        circulo = QtGui.QPainterPath()
        circulo.addEllipse(QtCore.QPointF(0, 0), 9, 9)
        punta = QtGui.QPainterPath()
        punta.moveTo(5, 0)
        punta.lineTo(-3.5, -4.5)
        punta.lineTo(-1.5, 0)
        punta.lineTo(-3.5, 4.5)
        punta.closeSubpath()
        borde = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5)
        borde.setCosmetic(True)
        sin_borde = QtGui.QPen(QtCore.Qt.NoPen)
        blanco = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        for x, y, ang in FL.flechas_plano(p.get("pts") or [], sentido):
            for forma, pluma, relleno in ((circulo, borde, QtGui.QBrush(col)), (punta, sin_borde, blanco)):
                it = sc.addPath(forma, pluma, relleno)
                it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
                it.setPos(x, y)
                it.setRotation(ang)
                it.setZValue(Z_MARK + 2)
                it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                self._overlay.append(it)
