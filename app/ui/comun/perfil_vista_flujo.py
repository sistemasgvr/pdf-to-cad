"""Flechas del FLUJO en el perfil (mezcla de `VistaPerfil`; pedido del usuario 2026-11-09: indicar hacia dónde va el
fluido «de una manera fácil»). En gravedad y presión (no en conductos: eléctrico, telecom): una flecha redonda a la
mitad de cada tramo que apunta hacia donde va el fluido. Rellena = la indicó el usuario; con borde = automática
(gravedad). A presión, sin indicar = la misma marca con una doble flecha (↔). Clic = invertir el sentido de esa
utilidad (sin indicar → hacia B); clic derecho = «Sentido del flujo» (esta utilidad o todo el perfil, hacia A, hacia
B o automático / sin indicar). La vista solo avisa (`flujoCambiado`); el cambio lo hace la ventana (`ventana_flujo`)."""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui

from nucleo import flujo as FL
from traduccion.i18n import t

R_FLECHA = 9.0                    # radio de la flecha (px)
TRAMO_MIN_PX = 3 * R_FLECHA       # un paso más corto en pantalla no lleva flecha


class FlujoPerfilMixin:
    def _con_flujo(self):
        return bool(self.p) and self.p.tipo in FL.REDES

    def _flechas_flujo(self):
        """[(paso, centro, ángulo en radianes)] de las flechas a la vista (gravedad y presión). Sin indicar, el ángulo
        es el del tramo (la doble flecha va a lo largo de él)."""
        p = self.p
        if not self._con_flujo() or not self._geo:
            return []
        out = []
        for i, ps in enumerate(p.pasos):
            hacia = getattr(ps, "flujo", 0) or 1
            x0, x1 = self.X(ps.e0), self.X(ps.e1)
            if x1 - x0 < TRAMO_MIN_PX:
                continue
            z0, z1 = self._z_paso(i)
            zm = (z0 + z1) / 2
            alto = self.Z(zm) - self.Z(zm + ps.alto_ft)
            y = self.Z(zm + ps.alto_ft / 2) if alto >= 2 * R_FLECHA + 2 else self.Z(zm + ps.alto_ft) - R_FLECHA - 3
            ang = math.atan2((self.Z(z1) - self.Z(z0)) * hacia, (x1 - x0) * hacia)
            out.append((i, QtCore.QPointF((x0 + x1) / 2, y), ang))
        return out

    def flujo_en(self, pos):
        """Paso de la flecha bajo el ratón, o -1."""
        for i, c, _a in self._flechas_flujo():
            if math.hypot(c.x() - pos.x(), c.y() - pos.y()) <= R_FLECHA + 2:
                return i
        return -1

    def _flujo(self, pt, tk):
        hover = getattr(self, "_hover_flujo", -1)
        acento = QtGui.QColor(tk.accent)
        for i, c, ang in self._flechas_flujo():
            ps = self.p.pasos[i]
            fijo = ps.flujo_fijo
            r = R_FLECHA + (1.5 if i == hover else 0.0)
            pt.setPen(QtGui.QPen(acento, 1.4))
            pt.setBrush(acento if fijo else QtGui.QColor(tk.surface))
            pt.drawEllipse(c, r, r)
            ca, sa = math.cos(ang), math.sin(ang)

            def q(x, y):
                return QtCore.QPointF(c.x() + x * ca - y * sa, c.y() + x * sa + y * ca)
            pt.setPen(QtCore.Qt.NoPen)
            if not ps.flujo:                          # presión sin indicar: doble flecha a lo largo del tramo
                pt.setBrush(QtGui.QColor(tk.text_muted))
                pt.drawPolygon(QtGui.QPolygonF([q(5.5, 0.0), q(1.5, -3.5), q(1.5, 3.5)]))
                pt.drawPolygon(QtGui.QPolygonF([q(-5.5, 0.0), q(-1.5, -3.5), q(-1.5, 3.5)]))
                continue
            pt.setBrush(QtGui.QColor(tk.text_on_accent) if fijo else acento)
            pt.drawPolygon(QtGui.QPolygonF([q(5.0, 0.0), q(-3.5, -4.5), q(-1.5, 0.0), q(-3.5, 4.5)]))

    def _globo_flujo(self, i):
        ps = self.p.pasos[i]
        if not ps.flujo:
            return (t("Sentido del flujo sin indicar.") + "\n"
                    + t("Clic: el fluido va hacia B · Clic derecho: más opciones"))
        hacia = "A" if ps.flujo < 0 else "B"
        modo = t("indicado") if ps.flujo_fijo else t("automático: hacia el extremo más bajo")
        return (t("El fluido va hacia {x} ({m}).").format(x=hacia, m=modo) + "\n"
                + t("Clic: invertir el sentido · Clic derecho: más opciones"))

    def _menu_flujo(self, m, i):
        """Submenú «Sentido del flujo» del clic derecho sobre el paso `i` (gravedad y presión)."""
        if not self._con_flujo() or not (0 <= i < len(self.p.pasos)):
            return
        ps = self.p.pasos[i]
        presion = self.p.tipo == "pressure"
        sub = m.addMenu(t("Sentido del flujo"))
        for texto, hacia, marcado in ((t("Esta utilidad: hacia A"), -1, ps.flujo_fijo and ps.flujo < 0),
                                      (t("Esta utilidad: hacia B"), 1, ps.flujo_fijo and ps.flujo > 0),
                                      (t("Esta utilidad: sin indicar") if presion else t("Esta utilidad: automático"),
                                       0, not ps.flujo_fijo)):
            a = sub.addAction(texto, lambda h=hacia: self.flujoCambiado.emit(i, h, False))
            a.setCheckable(True)
            a.setChecked(bool(marcado))
        sub.addSeparator()
        sub.addAction(t("Todo el perfil: hacia A"), lambda: self.flujoCambiado.emit(i, -1, True))
        sub.addAction(t("Todo el perfil: hacia B"), lambda: self.flujoCambiado.emit(i, 1, True))
        sub.addAction(t("Todo el perfil: sin indicar") if presion else t("Todo el perfil: automático"),
                      lambda: self.flujoCambiado.emit(i, 0, True))

    def _clic_flujo(self, pos):
        """Clic izquierdo: invierte el sentido de la utilidad de esa flecha (sin indicar → hacia B). True si había
        una flecha."""
        i = self.flujo_en(pos)
        if i < 0:
            return False
        f = self.p.pasos[i].flujo
        self.flujoCambiado.emit(i, -f if f else FL.ADELANTE, False)
        return True

    def _hover_flecha(self, pos):
        i = self.flujo_en(pos)
        if i != getattr(self, "_hover_flujo", -1):
            self._hover_flujo = i
            self.update()
        return i
