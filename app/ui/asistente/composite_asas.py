"""composite_asas.py — asas de ESCALA en el borde de la pieza elegida («Hoja compuesta»).

Pedido del usuario 2026-11-17: «a cada hoja hay que poner algo en los bordes para
arrastrar y que se escale». Antes la escala de una pieza solo se cambiaba escribiendo
«Escala pieza» en «Ajustes».

Ocho asas (cuatro esquinas y el medio de cada lado de lo VISIBLE de la pieza: su clip
o su cuadrilátero de esquinas libres, con su giro) sobre la pieza SELECCIONADA. Arrastrar
una cambia la escala de origen de la pieza (`Piece.src_scale`, la misma de «Escala
pieza») de forma uniforme dejando QUIETA la asa opuesta (`composite_scan.scale_piece`
con ese punto fijo). Como las demás herramientas de arrastre del compositor:

  - asas de tamaño fijo en pantalla (no crecen con el zoom) y cursor de redimensionar;
  - imán a las escalas notables (la de la hoja compuesta = 100 %, la de las demás
    piezas, la que leyó la hoja y la del comienzo) a ≤ `IMAN_PX` de pantalla;
  - Ctrl = fino (el ratón cuenta ×`FINO`, sin imán), Shift = pasos de `PASO` (5 %)
    del tamaño en la hoja compuesta;
  - doble clic = volver a la escala de la hoja compuesta (con una sola pieza, a la
    que leyó su hoja);
  - rótulo en vivo «1" = X' · N %» (N = tamaño respecto de la escala de la hoja compuesta).

Mientras se arrastra, la escala de la hoja compuesta queda FIJA (si no, con la pieza
que la define, todo cambiaría de tamaño a la vez y la pieza elegida no); al soltar
vuelve a «automática» si todas las piezas quedan con esa misma escala.

Las asas son ítems propios de la escena (no hijos de la pieza): `CompositeView.rebuild`
rehace las piezas y las asas siguen; se recolocan solas cuando la pieza cambia
(`QGraphicsScene.changed`), la selección o la vista.
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from hoja import composite as C
from hoja import composite_scan as CS
from traduccion.i18n import t as _tr

ASA_PX = 10           # lado de cada asa en pantalla
IMAN_PX = 8           # imán a una escala notable (px de pantalla)
FINO = 0.1            # Ctrl: el ratón cuenta 10 veces menos
PASO = 0.05           # Shift: pasos de 5 % del tamaño
MIN_PULGADA = 0.1     # 1" = 0.1' (el mínimo de «Escala pieza»)
DECIMALES = 2         # como «Escala pieza» (1" = X.XX')
Z_ASAS = 40           # sobre las piezas, anclajes (20) y puentes (19)
_COLOR = "#2b6fd1"    # el del contorno de la pieza elegida
_COLOR_IMAN = "#0b7a3b"


def _redondear(escala: float) -> float:
    return round(escala * 72.0, DECIMALES) / 72.0


class ArrastreEscala:
    """Lo que deja el ratón (sin Qt): `d` = distancia del punto fijo al ratón medida
    sobre la recta punto fijo → asa (pt de la hoja compuesta). La escala es
    proporcional a esa distancia. Se acumula el movimiento: cambiar Ctrl a mitad del
    arrastre no salta."""

    def __init__(self, s0: float, d0: float, d_raton: float, objetivo: float,
                 notables=(), px_por_pt: float = 1.0):
        self.s0, self.d0 = float(s0), max(float(d0), 1e-9)
        self.objetivo = float(objetivo)
        self.notables = [float(n) for n in notables if n and n > 0]
        self.px = float(px_por_pt)
        self.d = self.d0                     # distancia «virtual» (con la ganancia de Ctrl)
        self.ult = float(d_raton)

    def mover(self, d_raton: float, fino: bool = False, pasos: bool = False) -> Tuple[float, bool]:
        """(escala de origen pies/pt, ¿quedó en una escala notable?)."""
        self.d += (float(d_raton) - self.ult) * (FINO if fino else 1.0)
        self.ult = float(d_raton)
        minimo = MIN_PULGADA / 72.0
        escala = max(self.s0 * self.d / self.d0, minimo)
        if pasos:
            f = max(PASO, round(escala / self.objetivo / PASO) * PASO)
            return max(f * self.objetivo, minimo), any(abs(f * self.objetivo - n) < 1e-12 for n in self.notables)
        if not fino:
            mejor = None
            for n in self.notables:
                px = abs(self.d0 * n / self.s0 - self.d) * self.px
                if px <= IMAN_PX and (mejor is None or px < mejor[0]):
                    mejor = (px, n)
            if mejor is not None:
                return mejor[1], True
        return max(_redondear(escala), minimo), False


def _cursor(dx: float, dy: float) -> QtCore.Qt.CursorShape:
    """Cursor de redimensionar según el rumbo (en pantalla, y hacia abajo) punto fijo → asa."""
    a = math.degrees(math.atan2(dy, dx)) % 180.0
    if a < 22.5 or a >= 157.5:
        return QtCore.Qt.SizeHorCursor
    if a < 67.5:
        return QtCore.Qt.SizeFDiagCursor
    if a < 112.5:
        return QtCore.Qt.SizeVerCursor
    return QtCore.Qt.SizeBDiagCursor


class _Asa(QtWidgets.QGraphicsRectItem):
    def __init__(self, k: int, ctrl: "AsasEscala"):
        h = ASA_PX / 2.0
        super().__init__(-h, -h, ASA_PX, ASA_PX)
        self.k, self.ctrl = k, ctrl
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setZValue(Z_ASAS)
        pen = QtGui.QPen(QtGui.QColor(_COLOR), 1.5)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QtGui.QColor("#ffffff"))
        self.setAcceptHoverEvents(True)
        self.setToolTip(_tr("Arrastra para escalar la pieza (la asa opuesta queda quieta). "
                            "Ctrl: fino · Mayús: pasos de 5 % · doble clic: escala de la hoja compuesta"))

    def mousePressEvent(self, e):
        if e.button() != QtCore.Qt.LeftButton:
            e.ignore()
            return
        self.ctrl.empezar(self.k, e.scenePos())
        e.accept()

    def mouseMoveEvent(self, e):
        self.ctrl.mover(e.scenePos(), e.modifiers())
        e.accept()

    def mouseReleaseEvent(self, e):
        self.ctrl.soltar()
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.ctrl.restablecer(self.k)
        e.accept()


class _Rotulo(QtWidgets.QGraphicsItem):
    """«1" = X' · N %» junto a la asa que se arrastra (tamaño fijo en pantalla)."""

    def __init__(self):
        super().__init__()
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setZValue(Z_ASAS + 1)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self.texto, self.iman = "", False
        self._font = QtGui.QFont()
        self._font.setPixelSize(13)
        self._font.setBold(True)

    def poner(self, texto: str, iman: bool):
        self.prepareGeometryChange()
        self.texto, self.iman = texto, iman
        self.update()

    def _rect(self) -> QtCore.QRectF:
        fm = QtGui.QFontMetricsF(self._font)
        w, h = fm.horizontalAdvance(self.texto) + 16, fm.height() + 8
        return QtCore.QRectF(12, 12, w, h)          # abajo a la derecha del puntero

    def boundingRect(self):
        return self._rect().adjusted(-1, -1, 1, 1)

    def paint(self, painter, option, widget=None):
        r = self._rect()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(_COLOR_IMAN if self.iman else _COLOR))
        painter.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        painter.setFont(self._font)
        painter.setPen(QtGui.QColor("#ffffff"))
        painter.drawText(r, QtCore.Qt.AlignCenter, self.texto)


def etiqueta(escala: float, objetivo: float) -> str:
    return '1" = {v:g}\' · {p:g} %'.format(v=round(escala * 72.0, DECIMALES),
                                           p=round(escala / objetivo * 100.0, 1))


class AsasEscala(QtCore.QObject):
    """Asas de escala de la pieza elegida en `view` (`CompositeView`).

    `al_cambiar(idx, final)`: tras cada paso del arrastre (`final` False) y al soltar
    o restablecer (`final` True), para que el diálogo refresque «Escala pieza», el
    resumen y la lista de escalas. `escala_hoja(idx)`: la escala que leyó la hoja de
    esa pieza (opcional)."""

    def __init__(self, view, al_cambiar: Callable[[int, bool], None],
                 escala_hoja: Optional[Callable[[int], float]] = None):
        super().__init__(view)
        self.view = view
        self.al_cambiar = al_cambiar
        self.escala_hoja = escala_hoja
        self.asas: List[_Asa] = [_Asa(k, self) for k in range(8)]
        self.rotulo = _Rotulo()
        for it in self.asas + [self.rotulo]:
            view.scene().addItem(it)
            it.hide()
        self._drag = None          # dict del arrastre en curso
        self._pendiente = QtCore.QTimer(self)
        self._pendiente.setSingleShot(True)
        self._pendiente.setInterval(0)
        self._pendiente.timeout.connect(self.actualizar)
        view.selectionChangedIdx.connect(lambda _i: self.actualizar())
        view.viewChanged.connect(self._pendiente.start)
        view.scene().changed.connect(lambda _r: self._pendiente.start())

    # ── geometría ──────────────────────────────────────────────────────
    def _indice(self) -> int:
        v = self.view
        if getattr(v.measure, "mode", None):
            return -1                     # «Medir»/«Enderezar»: el clic es de la herramienta
        i = v.selected_index()
        if i < 0 or i >= len(v.items) or i >= len(v.comp.pieces) or v.items[i]._raw is None:
            return -1
        return i

    def puntos(self, idx: int) -> List[QtCore.QPointF]:
        """Esquinas 0, 2, 4, 6 y medio de cada lado 1, 3, 5, 7 de lo visible de la pieza;
        la opuesta de la asa k es la k + 4."""
        poly = self.view.items[idx].paper_polygon()
        esq = [poly[i] for i in range(4)]
        out = []
        for i in range(4):
            a, b = esq[i], esq[(i + 1) % 4]
            out += [a, (a + b) / 2.0]
        return out

    def actualizar(self):
        if self._drag is not None:
            return
        idx = self._indice()
        if idx < 0:
            for a in self.asas:
                a.hide()
            return
        pts = self.puntos(idx)
        t = self.view.transform()
        for k, a in enumerate(self.asas):
            if a.pos() != pts[k]:
                a.setPos(pts[k])
            p, q = t.map(pts[(k + 4) % 8]), t.map(pts[k])
            a.setCursor(_cursor(q.x() - p.x(), q.y() - p.y()))
            a.show()

    # ── arrastre ───────────────────────────────────────────────────────
    def _notables(self, idx: int, objetivo: float, s0: float) -> list:
        out = [objetivo, s0]
        out += [p.src_scale for i, p in enumerate(self.view.comp.pieces) if i != idx]
        if self.escala_hoja is not None:
            try:
                out.append(float(self.escala_hoja(idx)))
            except Exception:
                pass
        return out

    def empezar(self, k: int, pos: QtCore.QPointF) -> bool:
        if self._drag is not None:            # un arrastre sin «soltar» (se perdió el release)
            self.soltar()
        idx = self._indice()
        if idx < 0:
            return False
        v, comp = self.view, self.view.comp
        pts = self.puntos(idx)
        a, piv = pts[k], pts[(k + 4) % 8]
        dx, dy = a.x() - piv.x(), a.y() - piv.y()
        d0 = math.hypot(dx, dy)
        if d0 < 1e-6:
            return False
        u = (dx / d0, dy / d0)
        antes = comp.scale_ft_per_pt
        objetivo = comp.target_scale()
        comp.scale_ft_per_pt = objetivo          # fija mientras se arrastra (ver docstring)
        p = comp.pieces[idx]
        t = v.transform()
        px = math.hypot(t.m11(), t.m12()) or 1.0
        d_raton = (pos.x() - piv.x()) * u[0] + (pos.y() - piv.y()) * u[1]
        self._drag = dict(idx=idx, k=k, piv=(piv.x(), piv.y()), u=u, d0=d0, antes=antes,
                          objetivo=objetivo, s0=p.src_scale, cambio=False,
                          arr=ArrastreEscala(p.src_scale, d0, d_raton, objetivo,
                                             self._notables(idx, objetivo, p.src_scale), px))
        for i, asa in enumerate(self.asas):
            asa.setVisible(i == k)
        return True

    def _aplicar(self, escala: float, iman: bool):
        d = self._drag
        p = self.view.comp.pieces[d["idx"]]
        if abs(escala - p.src_scale) > 1e-15:
            CS.scale_piece(p, self.view.page_size(p), d["objetivo"], escala, d["piv"])
            d["cambio"] = abs(escala - d["s0"]) > 1e-15
            self.view.refresh_piece(d["idx"])
        piv, u = d["piv"], d["u"]
        r = d["d0"] * p.src_scale / d["s0"]
        punta = QtCore.QPointF(piv[0] + u[0] * r, piv[1] + u[1] * r)
        self.asas[d["k"]].setPos(punta)
        self.rotulo.setPos(punta)
        self.rotulo.poner(etiqueta(p.src_scale, d["objetivo"]), iman)
        self.rotulo.show()
        self.al_cambiar(d["idx"], False)

    def mover(self, pos: QtCore.QPointF, mods=QtCore.Qt.NoModifier):
        d = self._drag
        if d is None:
            return
        piv, u = d["piv"], d["u"]
        d_raton = (pos.x() - piv[0]) * u[0] + (pos.y() - piv[1]) * u[1]
        escala, iman = d["arr"].mover(d_raton, fino=bool(mods & QtCore.Qt.ControlModifier),
                                      pasos=bool(mods & QtCore.Qt.ShiftModifier))
        self._aplicar(escala, iman)

    def soltar(self):
        d = self._drag
        if d is None:
            return
        self._drag = None
        self.rotulo.hide()
        comp = self.view.comp
        if not d["cambio"]:
            comp.scale_ft_per_pt = d["antes"]
        elif all(abs(p.src_scale - d["objetivo"]) < 1e-12 for p in comp.pieces):
            comp.scale_ft_per_pt = None          # todas iguales: la escala automática es la misma
        self.actualizar()
        if d["cambio"]:
            self.al_cambiar(d["idx"], True)

    def destino_restablecer(self, idx: int) -> float:
        """La escala de la hoja compuesta sin contar esta pieza: la fijada, la de otra
        pieza o (sola) la que leyó su hoja."""
        comp = self.view.comp
        if comp.scale_ft_per_pt:
            return float(comp.scale_ft_per_pt)
        for i, p in enumerate(comp.pieces):
            if i != idx:
                return float(p.src_scale)
        if self.escala_hoja is not None:
            try:
                return float(self.escala_hoja(idx))
            except Exception:
                pass
        return float(comp.pieces[idx].src_scale)

    def restablecer(self, k: int):
        idx = self._indice()
        if idx < 0:
            return
        escala = self.destino_restablecer(idx)
        pts = self.puntos(idx)
        if not self.empezar(k, pts[k]):
            return
        self._aplicar(escala, True)
        self.soltar()
