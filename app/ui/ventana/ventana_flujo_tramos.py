"""Sentido del flujo PERSONALIZADO POR TRAMOS en el plano y en las propiedades (mezcla de `Main`, base de `FlujoMixin`;
pedido del usuario 2026-11-10: «una opción para que se haga de manera personalizada por tramos, y me permita cambiar
de manera fácil y visual el sentido de flujo de cada tramo por separado»).

- Fila «Flujo» del inspector: botón [⇄ Por tramos] = modo «flujo_tramos» en el lienzo y, debajo, una FICHA por tramo
  («T1 →», la flecha apunta como va ese tramo en el plano; gris = automático). Clic en una ficha o en el tramo en el
  lienzo = cambiar ese tramo (`nucleo/flujo.alternar_tramo`): automático → queda fijo tal como se ve (en gravedad,
  hacia su solera más baja); indicado → al revés. Un paso de deshacer por clic y 5 s de flechas que corren.
- En el modo, la utilidad muestra una flecha por tramo (rellena = indicada, con borde = automática, doble = sin
  indicar) y el tramo bajo el ratón se resalta. Esc, Enter, clic derecho u otro clic en el botón terminan.
Las validaciones (contrapendiente, caída en el buzón, perfil) leen el sentido de cada tramo (`FL.partes`).
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import flujo as FL, model_ops
from nucleo.model import Z_MARK
from traduccion.i18n import t as _tr
from ui.comun.icons import icon
from ui.comun.responsive import GridAdaptable
from ui.comun.theme import tokens
from ui.comun.ui_common import layer_qcolor

MODO_TRAMOS = "flujo_tramos"
ICONO_PX = 16


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
    p.drawPixmap(QtCore.QRectF(-ICONO_PX / 2, -ICONO_PX / 2, ICONO_PX, ICONO_PX), base, QtCore.QRectF(base.rect()))
    p.end()
    return QtGui.QIcon(pm)


class TramosFlujoMixin:
    # ------------------------------------------------------------------ fichas del inspector

    def _flujo_tramos_construir(self, v):
        caja = QtWidgets.QWidget()
        self._flujo_rejilla = GridAdaptable(caja, max_cols=4, spacing=4)
        caja.hide()
        v.addWidget(caja)
        self.box_flujo_tramos = caja
        self._flujo_fichas = []
        self._flujo_fichas_clave = None

    @staticmethod
    def _flujo_cotas(p):
        return lambda k: model_ops.cotas_tramo(p, k)

    def _flujo_fichas_refrescar(self, i, p):
        caja = getattr(self, "box_flujo_tramos", None)
        if caja is None:
            return
        ver = p is not None and FL.aplica(p) and (FL.por_tramos(p) or self.mode == MODO_TRAMOS)
        caja.setVisible(bool(ver))
        if not ver:
            return
        vista = FL.vista_tramos(p, self._flujo_cotas(p))
        pts = [tuple(q[:2]) for q in p.get("pts") or []]
        tk = tokens()
        clave = (i, tuple(vista), tuple(pts), tk.accent, tk.text_muted)
        if clave == self._flujo_fichas_clave:
            return
        self._flujo_fichas_clave = clave
        for b in self._flujo_fichas:                   # hide() antes: sin bucle de eventos, deleteLater solo no basta
            b.hide()
            self._flujo_rejilla.removeWidget(b)
            b.deleteLater()
        self._flujo_fichas = []
        for k, (s, indicado) in enumerate(vista):
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            ang = math.degrees(math.atan2(by - ay, bx - ax)) + (180.0 if s == FL.ATRAS else 0.0)
            b = QtWidgets.QToolButton()
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            b.setText(f"T{k + 1}")
            b.setIcon(icon("mdi:swap-horizontal", color=tk.text_muted) if not s
                      else _flecha(ang, tk.accent if indicado else tk.text_muted))
            b.setAutoRaise(False)
            hacia = (_tr("hacia el fin del tramo") if s == FL.ADELANTE else
                     _tr("hacia el inicio del tramo") if s == FL.ATRAS else _tr("sin indicar"))
            tip = (_tr("T{n}: {h}. Clic: invertirlo") if indicado else
                   _tr("T{n}: automático ({h}). Clic: dejarlo fijo así")).format(n=k + 1, h=hacia)
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            if indicado:
                b.setStyleSheet(f"QToolButton {{ color: {tk.accent}; font-weight: 600; }}")
            b.clicked.connect(lambda _=False, kk=k, ii=i: self.alternar_tramo_plano(kk, ii))
            self._flujo_rejilla.addWidget(b)
            self._flujo_fichas.append(b)

    # ------------------------------------------------------------------ modo en el lienzo

    def flujo_tramos_en_plano(self):
        """Modo «flujo_tramos» para la utilidad elegida (otro clic en el botón lo termina)."""
        if self.mode == MODO_TRAMOS:
            self._terminar_tramos_plano()
            return False
        i = getattr(self, "sel_pipe", -1)
        if not (0 <= i < len(self.pipes)) or not FL.aplica(self.pipes[i]) or len(self.pipes[i].get("pts") or []) < 2:
            self._info(_tr("Elige primero una utilidad de alcantarillado, drenaje, agua o gas."))
            self._flujo_refrescar()
            return False
        self._flujo_pipe = i
        self.set_mode(MODO_TRAMOS)
        self._flujo_refrescar()
        self._info(_tr("Haz clic en cada tramo (o en su ficha) para cambiar su sentido. Esc o Enter terminan."))
        return True

    def _terminar_tramos_plano(self):
        self._quitar_pista_flujo()
        if self.mode == MODO_TRAMOS:
            self.set_mode("idle")
        self._flujo_refrescar()
        self._info(_tr("Sentido por tramos: listo."))

    def alternar_tramo_plano(self, k, i=None):
        """Cambia el sentido del tramo k de la utilidad i (automático → fijo como se ve; indicado → al revés). UN paso
        de deshacer y 5 s de flechas. True si cambió."""
        if i is None:
            i = getattr(self, "_flujo_pipe", getattr(self, "sel_pipe", -1))
        if not (0 <= i < len(self.pipes)) or not FL.aplica(self.pipes[i]):
            return False
        p = self.pipes[i]
        prueba = dict(p)
        if not FL.alternar_tramo(prueba, k, self._flujo_cotas(prueba)):
            return False
        self._push()
        FL.alternar_tramo(p, k, self._flujo_cotas(p))
        self._dirty = True
        self._redraw()
        self._flujo_refrescar()
        self.animar_flujo(i)
        s = FL.sentidos_tramos(p)[k] if FL.por_tramos(p) else 0
        self._info(_tr("T{n}: el fluido va {h}.").format(
            n=k + 1, h=_tr("hacia el fin del tramo") if s == FL.ADELANTE else _tr("hacia el inicio del tramo")))
        return True

    def _tramo_bajo(self, x, y):
        """Tramo de la utilidad del modo bajo el ratón (o -1)."""
        i = getattr(self, "_flujo_pipe", -1)
        if not (0 <= i < len(self.pipes)):
            return -1
        pts = self.pipes[i].get("pts") or []
        r = 2.5 * 14.0 / max(1e-6, self.canvas.transform().m11())
        mejor = (r, -1)
        for k in range(len(pts) - 1):
            d = FL._dist_seg(x, y, pts[k][:2], pts[k + 1][:2])
            if d <= mejor[0]:
                mejor = (d, k)
        return mejor[1]

    def _pista_tramos(self, x, y):
        """Al mover el ratón en el modo: el tramo que cambiaría, resaltado."""
        k = self._tramo_bajo(x, y)
        if k < 0:
            self._info(_tr("Acércate a un tramo de la utilidad elegida para cambiar su sentido."))
            return
        i = self._flujo_pipe
        p = self.pipes[i]
        dibujo = self._pipe_display_pts(p)
        tramo = FL._tramo_en(dibujo, p["pts"][k], p["pts"][k + 1])
        col = QtGui.QColor(tokens().accent)
        col.setAlpha(110)
        pluma = QtGui.QPen(col, 12.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        pluma.setCosmetic(True)
        camino = QtGui.QPainterPath(QtCore.QPointF(*tramo[0]))
        for q in tramo[1:]:
            camino.lineTo(QtCore.QPointF(*q))
        it = self.canvas.scene().addPath(camino, pluma)
        it.setZValue(Z_MARK + 1)
        it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self._pista_flujo_items = [it]
        s, indicado = FL.vista_tramos(p, self._flujo_cotas(p))[k]
        self._info((_tr("Clic: invertir T{n}") if indicado else _tr("Clic: dejar T{n} fijo como se ve")).format(n=k + 1)
                   + "  " + _tr("(Esc termina)"))

    def _clic_tramo_plano(self, x, y):
        k = self._tramo_bajo(x, y)
        if k < 0:
            self._info(_tr("Acércate a un tramo de la utilidad elegida para cambiar su sentido."))
            return False
        self._quitar_pista_flujo()
        return self.alternar_tramo_plano(k)

    def _flujo_tramos_dibujar(self, i):
        """En el modo: una flecha por tramo de la utilidad (rellena = indicada, con borde = automática, doble = sin
        indicar). Devuelve los ítems."""
        p = self.pipes[i]
        sc = self.canvas.scene()
        col = layer_qcolor(p.get("layer"))
        blanco = QtGui.QColor(255, 255, 255)
        out = []
        circulo = QtGui.QPainterPath()
        circulo.addEllipse(QtCore.QPointF(0, 0), 10, 10)
        punta = QtGui.QPainterPath()
        punta.moveTo(5.5, 0)
        punta.lineTo(-4, -5)
        punta.lineTo(-1.5, 0)
        punta.lineTo(-4, 5)
        punta.closeSubpath()
        doble = QtGui.QPainterPath()
        for sg in (1, -1):
            doble.moveTo(6 * sg, 0)
            doble.lineTo(1.5 * sg, -4)
            doble.lineTo(1.5 * sg, 4)
            doble.closeSubpath()
        vista = FL.vista_tramos(p, self._flujo_cotas(p))
        for _k, x, y, ang, s, indicado in FL.flechas_vista(p, vista, self._pipe_display_pts(p)):
            borde = QtGui.QPen(blanco if indicado else col, 1.6)
            borde.setCosmetic(True)
            for forma, pluma, relleno in ((circulo, borde, col if indicado else blanco),
                                          (punta if s else doble, QtGui.QPen(QtCore.Qt.NoPen),
                                           blanco if indicado else col)):
                it = sc.addPath(forma, pluma, QtGui.QBrush(relleno))
                it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
                it.setPos(x, y)
                it.setRotation(ang)
                it.setZValue(Z_MARK + 3)
                it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                out.append(it)
        return out
