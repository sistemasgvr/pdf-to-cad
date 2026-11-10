"""El perfil en el PLANO (mezcla de `PerfilMixin`): resalte del recorrido, banderas, ratón del plano → estación y estación del perfil → punto en el plano.

Movido tal cual de `ventana_perfil` (2026-11-08)."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo.model import Z_MARK
from ui.comun.theme import tokens


class PlanoPerfilMixin:
    def _perfil_quitar_resalte(self):
        marca = getattr(self, "_perfil_marca", None)
        if marca is not None:
            try:
                marca.hide()
            except RuntimeError:
                self._perfil_marca = None
        for it in getattr(self, "_perfil_resalte", []) or []:
            try:
                if it.scene() is not None:
                    it.scene().removeItem(it)
            except RuntimeError:
                pass
        self._perfil_resalte = []

    def _perfil_resaltar(self):
        self._perfil_quitar_resalte()
        rec, d = self._perfil_rec, getattr(self, "_perfil_datos", None)
        if rec is None or d is None or not self._perfil_visible():
            return
        tk = tokens()
        sc = self.canvas.scene()
        camino = QtGui.QPainterPath()
        for p in d.pasos:                             # tal como se dibuja la utilidad (con sus curvas)
            pts = p.puntos
            camino.moveTo(*pts[0])
            for q in pts[1:]:
                camino.lineTo(*q)
        col = QtGui.QColor(tk.accent)
        col.setAlpha(110)
        pen = QtGui.QPen(col, 9)
        pen.setCosmetic(True)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        it = sc.addPath(camino, pen)
        it.setZValue(Z_MARK - 0.1)
        self._perfil_resalte.append(it)
        k = self.perfil_vista._sel_nodo
        i = self.perfil_vista._sel_paso
        if 0 <= i < len(d.pasos):
            c2 = QtGui.QPainterPath()
            pts = d.pasos[i].puntos
            c2.moveTo(*pts[0])
            for q in pts[1:]:
                c2.lineTo(*q)
            pen2 = QtGui.QPen(QtGui.QColor(tk.accent), 4)
            pen2.setCosmetic(True)
            it2 = sc.addPath(c2, pen2)
            it2.setZValue(Z_MARK + 0.4)
            self._perfil_resalte.append(it2)
        if 0 <= k < len(d.nodos):
            n = d.nodos[k]
            m = QtWidgets.QGraphicsEllipseItem(-7, -7, 14, 14)
            m.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            m.setPos(*self._perfil_punto_nodo(d, k))
            m.setPen(QtGui.QPen(QtGui.QColor(tk.text_on_accent), 2))
            m.setBrush(QtGui.QColor(tk.accent))
            m.setZValue(Z_MARK + 0.5)
            sc.addItem(m)
            self._perfil_resalte.append(m)
        self._perfil_resalte += self._perfil_banderas(sc)

    def _perfil_raton(self, x, y):
        """Ratón en el PLANO → la estación en el perfil (sobre su recorrido)."""
        if not self._perfil_visible():
            return
        self._perfil_pista(x, y)                      # eligiendo A o B: imán y letra donde caerá el clic
        d = getattr(self, "_perfil_datos", None)
        e = None
        if d is not None:
            thr = 14.0 / max(1e-6, self.canvas.transform().m11())
            mejor = thr
            for p in d.pasos:
                r = p.proyectar(x, y)                 # sobre el paso tal como se dibuja (con sus curvas)
                if r is not None and r[0] <= mejor:
                    mejor, e = r
        self.perfil_vista.set_cursor(e)

    def _perfil_marcar_estacion(self, e):
        """Ratón en el PERFIL → un punto en el plano en esa estación."""
        it = getattr(self, "_perfil_marca", None)
        d = getattr(self, "_perfil_datos", None)
        if d is None or e != e:                       # NaN = salió
            if it is not None:
                it.hide()
            return
        p = next((q for q in d.pasos if q.e0 <= e <= q.e1), None)
        if p is None:
            if it is not None:
                it.hide()
            return
        x, y = p.punto_en(e)
        try:
            vivo = it is not None and it.scene() is not None
        except RuntimeError:
            vivo = False
        if not vivo:
            tk = tokens()
            it = QtWidgets.QGraphicsEllipseItem(-6, -6, 12, 12)
            it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            it.setPen(QtGui.QPen(QtGui.QColor(tk.text_on_accent), 2))
            it.setBrush(QtGui.QColor(tk.accent))
            it.setZValue(Z_MARK + 0.6)
            self.canvas.scene().addItem(it)
            self._perfil_marca = it
        it.setPos(x, y)
        it.show()

    @staticmethod
    def _perfil_punto_nodo(d, k):
        """Dónde está en el plano el nodo k del perfil: sobre la utilidad tal como se dibuja (el nodo de una curva cae
        en el punto medio de su arco, no en la esquina)."""
        if 0 <= k < len(d.pasos):
            return d.pasos[k].puntos[0]
        if k == len(d.pasos) and d.pasos:
            return d.pasos[-1].puntos[-1]
        n = d.nodos[k]
        return n.x, n.y
