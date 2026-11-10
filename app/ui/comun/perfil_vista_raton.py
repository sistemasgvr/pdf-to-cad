"""Ratón y teclado del perfil (mezcla de `VistaPerfil`): elegir y arrastrar nodos, escribir cotas, fijar
pendientes, desplazar con las barras, Ctrl + rueda = zoom. Movido tal cual de `perfil_vista` (2026-11-08)."""
from __future__ import annotations

import math

from PySide6 import QtCore, QtWidgets


from nucleo import perfil_textos as T
from traduccion.i18n import t
from ui.comun.perfil_vista_base import ATRAPAR_PX


class RatonPerfilMixin:
    # ---- edición precisa

    def editar_cota_nodo(self, k, z=None):
        """Escribir la solera del nodo `k` (sin `z`: la pregunta)."""
        if not self.p or not (0 <= k < len(self.p.nodos)) or not self.p.nodos[k].editable:
            return False
        if z is None:
            z, ok = QtWidgets.QInputDialog.getDouble(
                self, t("Cota del punto"), t("Solera (invert) en {e}, ft:").format(e=T.estacion(self.p.nodos[k].e)),
                round(self._z_nodo(k), 2), -100000.0, 100000.0, 2)
            if not ok:
                return False
        self.cotaCambiada.emit(k, round(float(z), 2))
        return True

    def fijar_pendiente(self, i, pct=None):
        """Fija la pendiente (%) del paso `i`: se mueve la cota de su FINAL (el nodo i + 1)."""
        p = self.p
        if not p or not (0 <= i < len(p.pasos)) or not p.nodos[i + 1].editable:
            return False
        ps = p.pasos[i]
        if pct is None:
            pct, ok = QtWidgets.QInputDialog.getDouble(
                self, t("Pendiente del tramo"),
                t("Pendiente de {a} a {b}, en % (se mueve la cota del final):").format(
                    a=T.estacion(ps.e0), b=T.estacion(ps.e1)),
                round(ps.pendiente * 100, 2), -100.0, 100.0, 2)
            if not ok:
                return False
        self.cotaCambiada.emit(i + 1, round(ps.z0 + float(pct) / 100.0 * (ps.e1 - ps.e0), 2))
        return True

    def _menu(self, pos, global_pos):
        k = self._nodo_en(pos)
        i = self._paso_en(pos)
        m = QtWidgets.QMenu(self)
        if k >= 0:
            m.addAction(t("Escribir la cota…"), lambda: self.editar_cota_nodo(k))
        if i >= 0 and self.p.nodos[i + 1].editable:
            m.addAction(t("Fijar la pendiente de este tramo…"), lambda: self.fijar_pendiente(i))
        if i < 0:
            i = self.flujo_en(pos)                    # sobre la flecha (puede ir encima de la corona)
        if i >= 0:
            self._menu_flujo(m, i)                    # «Sentido del flujo» (gravedad, `perfil_vista_flujo`)
        if m.isEmpty():
            return
        m.exec(global_pos)

    def alertas_en(self, pos):
        """Las alertas de la marca «!» que está bajo el ratón (su círculo de 8 px + 2 de margen). Antes bastaba la estación (±10 px):
        toda la columna vertical era «la alerta» y su globo tapaba el de los nodos."""
        if not self._geo:
            return []
        for c, lst in self._marcas_alerta():
            if math.hypot(c.x() - pos.x(), c.y() - pos.y()) <= 10:
                return lst
        return []

    # ------------------------------------------------------------------ ratón y teclado

    def _nodo_en(self, pos):
        if not self.p or not self._geo:
            return -1
        mejor = (ATRAPAR_PX, -1)
        for k, n in enumerate(self.p.nodos):
            if not n.editable:
                continue
            d = math.hypot(self.X(n.e) - pos.x(), self.Z(self._z_nodo(k)) - pos.y())
            if d <= mejor[0]:
                mejor = (d, k)
        return mejor[1]

    def _paso_en(self, pos):
        if not self.p or not self._geo:
            return -1
        for i, ps in enumerate(self.p.pasos):
            x0, x1 = self.X(ps.e0), self.X(ps.e1)
            if x0 <= pos.x() <= x1:
                f = (pos.x() - x0) / max(x1 - x0, 1e-6)
                z0, z1 = self._z_paso(i)
                z = z0 + (z1 - z0) * f
                if self.Z(z + ps.alto_ft) - 4 <= pos.y() <= self.Z(z) + 4:
                    return i
        return -1

    def mousePressEvent(self, e):
        pos = e.position()
        if e.button() in (QtCore.Qt.MiddleButton, QtCore.Qt.RightButton):
            area = self._area()
            self._desplazando = (e.globalPosition(), (area.horizontalScrollBar().value(),
                                                      area.verticalScrollBar().value()) if area else (0, 0))
            self._movido = False
            self._boton = e.button()
            return
        if e.button() != QtCore.Qt.LeftButton:
            return
        kr = self.ramal_en(pos)
        if kr >= 0 and self._nodo_en(pos) < 0:
            self.ramalPedido.emit(kr)
            return
        k = self._nodo_en(pos)
        if k < 0 and self._clic_flujo(pos):           # flecha del flujo: invertir el sentido
            return
        if k >= 0:
            self.elegir_nodo(k)
            self._arrastre = (k, self._z_nodo(k))
            self._agarre_y = pos.y()
            self._z_ini = self._arrastre[1]
            return
        i = self._paso_en(pos)
        self._sel_paso = i
        self.elegir_nodo(-1)
        self.pasoElegido.emit(i)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._desplazando:
            a, (h0, v0) = self._desplazando
            d = e.globalPosition() - a
            if not self._movido and d.manhattanLength() < 4:
                return
            if not self._movido:
                self._movido = True
                self.setCursor(QtCore.Qt.ClosedHandCursor)
            area = self._area()
            if area is not None:                      # desplazar = mover las barras
                area.horizontalScrollBar().setValue(int(h0 - d.x()))
                area.verticalScrollBar().setValue(int(v0 - d.y()))
            return
        if self._arrastre:
            dz = (self._agarre_y - pos.y()) / (self._geo["kz"] * self._zoom)
            self._arrastre = (self._arrastre[0], round(self._z_ini + dz, 2))
            self.update()
            return
        if self._geo and self.p and self.p.pasos and self._geo["vista"].contains(pos):
            est = self.e_de(pos.x())                 # no `e`: es el evento (su globalPosition va abajo)
            self.estacionHover.emit(est if self.p.e_ini <= est <= self.p.e_fin else float("nan"))
        k = self._nodo_en(pos)
        kr = self.ramal_en(pos) if k < 0 else -1
        kf = self._hover_flecha(pos) if k < 0 else -1
        if k != self._hover:
            self.nodoHover.emit(k)
            self._hover = k
            self.update()
        self.setCursor(QtCore.Qt.SizeVerCursor if k >= 0 else
                       QtCore.Qt.PointingHandCursor if (kr >= 0 or kf >= 0) else QtCore.Qt.ArrowCursor)
        texto = self._texto_globo(pos)
        if texto:
            QtWidgets.QToolTip.showText(e.globalPosition().toPoint(), texto, self)

    def _texto_globo(self, pos):
        """El ÚNICO texto del globo en `pos`, por prioridad: el icono de una alerta → solo su texto; un ramal; un nodo;
        nada ("" → la ayuda general de la vista). Antes el movimiento del ratón y el globo de ayuda de Qt competían
        y el globo saltaba entre la alerta y «Arrastra un punto…» (2026-11-08)."""
        if not self.p:
            return ""
        al = self.alertas_en(pos)
        if al:
            return "\n".join("• " + a.mensaje for a in al)
        k = self._nodo_en(pos)
        if k < 0 and self.ramal_en(pos) >= 0:
            return t("Clic: ver el perfil de este ramal")
        kf = self.flujo_en(pos) if k < 0 else -1
        if kf >= 0:
            return self._globo_flujo(kf)
        if k >= 0 and self.p.nodos[k].lineas:
            return "\n".join(self.p.nodos[k].lineas)
        return ""

    def event(self, ev):
        """El globo que Qt pide al quedarse quieto el ratón: el de `_texto_globo`; solo sin nada, la ayuda general."""
        if ev.type() == QtCore.QEvent.ToolTip:
            texto = self._texto_globo(QtCore.QPointF(ev.pos()))
            if texto:
                QtWidgets.QToolTip.showText(ev.globalPos(), texto, self)
            elif self.toolTip():
                QtWidgets.QToolTip.showText(ev.globalPos(), self.toolTip(), self)
            else:
                QtWidgets.QToolTip.hideText()
            return True
        return super().event(ev)

    def mouseReleaseEvent(self, e):
        if self._desplazando:
            self._desplazando = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            if not self._movido and self._boton == QtCore.Qt.RightButton and self.p:
                self._menu(e.position(), e.globalPosition().toPoint())
            return
        if self._arrastre:
            k, z = self._arrastre
            self._arrastre = None
            if abs(z - self._z_ini) >= 0.005:
                self.cotaCambiada.emit(k, z)
            self.update()

    def mouseDoubleClickEvent(self, e):
        k = self._nodo_en(e.position())
        if k >= 0 and e.button() == QtCore.Qt.LeftButton:
            self._arrastre = None
            self.editar_cota_nodo(k)
            return
        self.encuadrar()

    def wheelEvent(self, e):
        """Ctrl + rueda = acercar/alejar (el punto bajo el cursor se queda quieto); rueda sola = desplazar."""
        area = self._area()
        if not self._geo or (area is not None and not (e.modifiers() & QtCore.Qt.ControlModifier)):
            e.ignore()                                # la QScrollArea desplaza
            return
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        nz = min(40.0, max(0.1, self._zoom * f))
        pos = e.position()
        e_c, z_c = self.e_de(pos.x()), self.z_de(pos.y())
        en_vp = self.mapTo(area.viewport(), pos.toPoint()) if area is not None else None
        self._zoom = nz
        self._ajustar_tam()
        if area is not None:
            self._calcular()
            area.horizontalScrollBar().setValue(int(self.X(e_c) - en_vp.x()))
            area.verticalScrollBar().setValue(int(self.Z(z_c) - en_vp.y()))
        e.accept()

    def keyPressEvent(self, e):
        k = self._sel_nodo
        if k >= 0 and e.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down) and self.p.nodos[k].editable:
            paso = 1.0 if e.modifiers() & QtCore.Qt.ShiftModifier else 0.10
            z = self._z_nodo(k) + (paso if e.key() == QtCore.Qt.Key_Up else -paso)
            self.cotaCambiada.emit(k, round(z, 2))
            return
        if k >= 0 and e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.editar_cota_nodo(k)
            return
        if e.key() in (QtCore.Qt.Key_Home, QtCore.Qt.Key_End) and self.p and self.p.nodos:
            self.elegir_nodo(0 if e.key() == QtCore.Qt.Key_Home else len(self.p.nodos) - 1)
            return
        if e.key() in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right) and self.p and self.p.nodos:
            n = len(self.p.nodos)
            k = 0 if k < 0 else (k + (1 if e.key() == QtCore.Qt.Key_Right else -1)) % n
            self.elegir_nodo(k)
            return
        super().keyPressEvent(e)

    def leaveEvent(self, _e):
        self.estacionHover.emit(float("nan"))
        if self._hover_flujo >= 0:
            self._hover_flujo = -1
            self.update()
        if self._hover >= 0:
            self._hover = -1
            self.nodoHover.emit(-1)
            self.update()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.update()
