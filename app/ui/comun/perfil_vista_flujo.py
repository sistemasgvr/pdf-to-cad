"""Flujo en el perfil (mezcla de `VistaPerfil`). En gravedad y presión (no en conductos: eléctrico, telecom).

- Flechas redondas a la mitad de cada tramo, apuntando hacia donde va el fluido (pedido 2026-11-09). Rellena = lo
  indicó el usuario; con borde = automática (gravedad). A presión, sin indicar = doble flecha (↔). Si el fluido llega
  a un punto DENTRO de un tramo, ese tramo lleva dos flechas, una a cada lado del punto.
- Donde llega el fluido (un buzón, un vértice o un punto de la tubería) va una marca de LLEGADA (diana).
- ELEGIR EL PUNTO DE LLEGADA (pedido 2026-11-10: «ya no todo a la izquierda o a la derecha: puede llegar a un buzón
  del medio»): `elegir_flujo(True)` (botón «Flujo» de la cabecera, clic en una flecha o el menú del clic derecho).
  El ratón se pega a los nodos (buzones, vértices, uniones: a ≤ `IMAN_PX`) o a cualquier punto de la tubería; una
  línea guía, la diana y una etiqueta («Buzón MH-3 · 2+35») dicen dónde caerá, y las flechas muestran en vivo cómo
  quedará el flujo. Clic = `flujoPunto(estación, nodo o -1)`; Esc o clic derecho = cancelar (`flujoElegir(False)`).
- `ver_flujo` (ojo de la cabecera): ver u ocultar flechas y marcas (mientras se elige, se ven siempre).
La vista solo avisa; el cambio lo hace la ventana (`ventana_flujo`).
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui

from nucleo import flujo as FL, flujo_perfil as FP, perfil_textos as T
from traduccion.i18n import t

R_FLECHA = 9.0                    # radio de la flecha (px)
TRAMO_MIN_PX = 3 * R_FLECHA       # una parte más corta en pantalla no lleva flecha
IMAN_PX = 12.0                    # radio del imán a los nodos (px de pantalla, a lo largo de las estaciones)
R_LLEGADA = 7.0                   # radio de la diana de llegada

N_ = lambda s: s          # noqa: E731  (marca para la traducción)
_NOMBRE_NODO = {"estructura": N_("Buzón"), "extremo": N_("Punta"), "codo": N_("Codo"), "tee": N_("Tee"),
                "wye": N_("Wye"), "cruz": N_("Cruz"), "reduccion": N_("Reducción"), "union": N_("Unión")}


class FlujoPerfilMixin:
    ver_flujo = True
    _eligiendo_flujo = False
    _pista_flujo = None               # {"e", "nodo", "texto"} donde caería el clic

    def _con_flujo(self):
        return bool(self.p) and self.p.tipo in FL.REDES

    # ------------------------------------------------------------------ elegir el punto de llegada

    def elegir_flujo(self, on=True):
        """Entra (o sale) del modo «elegir hacia dónde va el fluido». Avisa con `flujoElegir`."""
        on = bool(on) and self._con_flujo()
        if on == self._eligiendo_flujo:
            return
        self._eligiendo_flujo = on
        self._pista_flujo = None
        self.setCursor(QtCore.Qt.CrossCursor if on else QtCore.Qt.ArrowCursor)
        if on:
            self.setFocus()
        self.update()
        self.flujoElegir.emit(on)

    def eligiendo_flujo(self):
        return self._eligiendo_flujo

    def _pista_en(self, pos):
        """Dónde llegaría el fluido con el ratón en `pos`: un nodo (imán) o el punto de la tubería en esa estación."""
        p = self.p
        if not self._geo or not p or not p.pasos:
            return None
        x = min(max(pos.x(), self.X(p.e_ini)), self.X(p.e_fin))
        mejor = None
        for k, n in enumerate(p.nodos):
            d = abs(self.X(n.e) - x)
            if d <= IMAN_PX and (mejor is None or d < mejor[0]):
                mejor = (d, k)
        if mejor is not None:
            n = p.nodos[mejor[1]]
            nombre = t(_NOMBRE_NODO.get(n.tipo) or N_("Vértice"))
            if n.tipo == "estructura" and n.cod:
                nombre += " " + n.cod
            return {"e": n.e, "nodo": mejor[1], "texto": nombre + " · " + T.estacion(n.e)}
        e = min(max(self.e_de(x), p.e_ini), p.e_fin)
        return {"e": e, "nodo": -1, "texto": t("Tubería") + " · " + T.estacion(e)}

    def _mover_eligiendo(self, pos):
        pista = self._pista_en(pos)
        if pista != self._pista_flujo:
            self._pista_flujo = pista
            self.update()
        return pista

    def _clic_eligiendo(self, pos, boton):
        """Clic mientras se elige: izquierdo = este punto; derecho = cancelar. True si lo atendió."""
        if not self._eligiendo_flujo:
            return False
        if boton == QtCore.Qt.LeftButton:
            pista = self._pista_en(pos)
            self.elegir_flujo(False)
            if pista is not None:
                self.flujoPunto.emit(float(pista["e"]), int(pista["nodo"]))
        else:
            self.elegir_flujo(False)
        return True

    # ------------------------------------------------------------------ flechas

    def _flujos(self):
        """[(sentido, corte, indicado)] de cada paso: los del perfil o, mientras se elige, la vista previa."""
        p = self.p
        if self._eligiendo_flujo and self._pista_flujo is not None:
            return [(f, c, True) for f, c in FP.objetivo(p, self._pista_flujo["e"])]
        return [(getattr(ps, "flujo", 0), getattr(ps, "flujo_corte", None), ps.flujo_fijo) for ps in p.pasos]

    def _z_en(self, i, e):
        ps = self.p.pasos[i]
        z0, z1 = self._z_paso(i)
        f = (e - ps.e0) / max(ps.e1 - ps.e0, 1e-9)
        return z0 + (z1 - z0) * f

    def _flechas_flujo(self):
        """[(paso, centro, ángulo en radianes, sentido, indicado)] de las flechas a la vista. Sin indicar, el ángulo
        es el del tramo (la doble flecha va a lo largo de él)."""
        p = self.p
        if not self._con_flujo() or not self._geo or not (self.ver_flujo or self._eligiendo_flujo):
            return []
        out = []
        for i, (ps, (f, corte, fijo)) in enumerate(zip(p.pasos, self._flujos())):
            partes = [(ps.e0, ps.e1, f)] if corte is None else [(ps.e0, ps.e_en(corte), 1), (ps.e_en(corte), ps.e1, -1)]
            z0, z1 = self._z_paso(i)
            for e0, e1, hacia in partes:
                x0, x1 = self.X(e0), self.X(e1)
                if x1 - x0 < TRAMO_MIN_PX:
                    continue
                zm = self._z_en(i, (e0 + e1) / 2)
                alto = self.Z(zm) - self.Z(zm + ps.alto_ft)
                y = self.Z(zm + ps.alto_ft / 2) if alto >= 2 * R_FLECHA + 2 else self.Z(zm + ps.alto_ft) - R_FLECHA - 3
                h = hacia or 1
                ang = math.atan2((self.Z(z1) - self.Z(z0)) * h, (self.X(ps.e1) - self.X(ps.e0)) * h)
                out.append((i, QtCore.QPointF((x0 + x1) / 2, y), ang, hacia, fijo))
        return out

    def flujo_en(self, pos):
        """Paso de la flecha bajo el ratón, o -1."""
        for i, c, *_ in self._flechas_flujo():
            if math.hypot(c.x() - pos.x(), c.y() - pos.y()) <= R_FLECHA + 2:
                return i
        return -1

    def _flujo(self, pt, tk):
        if not self._con_flujo() or not self._geo:
            return
        hover = getattr(self, "_hover_flujo", -1)
        acento = QtGui.QColor(tk.accent)
        for i, c, ang, hacia, fijo in self._flechas_flujo():
            r = R_FLECHA + (1.5 if i == hover else 0.0)
            pt.setPen(QtGui.QPen(acento, 1.4))
            pt.setBrush(acento if fijo else QtGui.QColor(tk.surface))
            pt.drawEllipse(c, r, r)
            ca, sa = math.cos(ang), math.sin(ang)

            def q(x, y):
                return QtCore.QPointF(c.x() + x * ca - y * sa, c.y() + x * sa + y * ca)
            pt.setPen(QtCore.Qt.NoPen)
            if not hacia:                             # presión sin indicar: doble flecha a lo largo del tramo
                pt.setBrush(QtGui.QColor(tk.text_muted))
                pt.drawPolygon(QtGui.QPolygonF([q(5.5, 0.0), q(1.5, -3.5), q(1.5, 3.5)]))
                pt.drawPolygon(QtGui.QPolygonF([q(-5.5, 0.0), q(-1.5, -3.5), q(-1.5, 3.5)]))
                continue
            pt.setBrush(QtGui.QColor(tk.text_on_accent) if fijo else acento)
            pt.drawPolygon(QtGui.QPolygonF([q(5.0, 0.0), q(-3.5, -4.5), q(-1.5, 0.0), q(-3.5, 4.5)]))
        self._llegadas(pt, tk)
        self._pista(pt, tk)

    def _punto_tuberia(self, e):
        """(x, y) en pantalla del eje de la tubería en la estación e."""
        p = self.p
        for i, ps in enumerate(p.pasos):
            if ps.e0 - 1e-6 <= e <= ps.e1 + 1e-6:
                z = self._z_en(i, e)
                return QtCore.QPointF(self.X(e), self.Z(z + ps.alto_ft / 2))
        return None

    def _diana(self, pt, c, color, fondo):
        pt.setPen(QtGui.QPen(color, 2.0))
        pt.setBrush(fondo)
        pt.drawEllipse(c, R_LLEGADA, R_LLEGADA)
        pt.setPen(QtCore.Qt.NoPen)
        pt.setBrush(color)
        pt.drawEllipse(c, 2.6, 2.6)

    def _llegadas(self, pt, tk):
        """Dianas donde llega el fluido indicado (no las del automático: ahí no eligió nadie)."""
        if self._eligiendo_flujo or not self.ver_flujo:
            return
        flujos = [(f, c) for f, c, fijo in self._flujos()]
        fijos = [fijo for _f, _c, fijo in self._flujos()]
        if not any(fijos):
            return
        for e in FP.llegadas(self.p, flujos):
            c = self._punto_tuberia(e)
            if c is not None:
                self._diana(pt, c, QtGui.QColor(tk.accent), QtGui.QColor(tk.surface))

    def _pista(self, pt, tk):
        """Mientras se elige: línea guía, diana y etiqueta donde caerá el clic."""
        pista = self._pista_flujo if self._eligiendo_flujo else None
        if pista is None:
            return
        c = self._punto_tuberia(pista["e"])
        if c is None:
            return
        g = self._geo
        col = QtGui.QColor(tk.success)
        guia = QtGui.QPen(col, 1.2, QtCore.Qt.DashLine)
        pt.setPen(guia)
        pt.drawLine(QtCore.QPointF(c.x(), g["marco"].top()), QtCore.QPointF(c.x(), g["marco"].bottom()))
        self._diana(pt, c, col, QtGui.QColor(tk.surface))
        fm = QtGui.QFontMetricsF(pt.font())
        texto = pista["texto"]
        w, h = fm.horizontalAdvance(texto) + 14, fm.height() + 6
        x = min(max(c.x() - w / 2, g["marco"].left() + 2), g["marco"].right() - w - 2)
        caja = QtCore.QRectF(x, max(g["marco"].top() + 2, c.y() - R_LLEGADA - 8 - h), w, h)
        pt.setPen(QtCore.Qt.NoPen)
        pt.setBrush(col)
        pt.drawRoundedRect(caja, h / 2, h / 2)
        pt.setPen(QtGui.QColor(tk.text_on_accent))
        pt.drawText(caja, QtCore.Qt.AlignCenter, texto)

    # ------------------------------------------------------------------ globo, menú y clic

    def _globo_flujo(self, i):
        ps = self.p.pasos[i]
        pie = t("Clic: elegir hacia dónde va el fluido · Clic derecho: más opciones")
        if getattr(ps, "flujo_corte", None) is not None:
            return t("El fluido llega a {e} desde los dos lados.").format(e=T.estacion(ps.e_en(ps.flujo_corte))) \
                + "\n" + pie
        if not ps.flujo:
            return t("Sentido del flujo sin indicar.") + "\n" + pie
        hacia = "A" if ps.flujo < 0 else "B"
        modo = t("indicado") if ps.flujo_fijo else t("automático: hacia el extremo más bajo")
        return t("El fluido va hacia {x} ({m}).").format(x=hacia, m=modo) + "\n" + pie

    def _menu_flujo(self, m, i):
        """Submenú «Sentido del flujo» del clic derecho sobre el paso `i` (gravedad y presión)."""
        if not self._con_flujo() or not (0 <= i < len(self.p.pasos)):
            return
        ps = self.p.pasos[i]
        presion = self.p.tipo == "pressure"
        sub = m.addMenu(t("Sentido del flujo"))
        sub.addAction(t("Elegir hacia dónde va el fluido…"), lambda: self.elegir_flujo(True))
        sub.addSeparator()
        a = sub.addAction(t("Esta utilidad: sin indicar") if presion else t("Esta utilidad: automático"),
                          lambda: self.flujoCambiado.emit(i, 0, False))
        a.setCheckable(True)
        a.setChecked(not ps.flujo_fijo)
        sub.addAction(t("Todo el perfil: sin indicar") if presion else t("Todo el perfil: automático"),
                      lambda: self.flujoCambiado.emit(i, 0, True))

    def _clic_flujo(self, pos):
        """Clic izquierdo en una flecha: elegir hacia dónde va el fluido. True si había una flecha."""
        if self.flujo_en(pos) < 0:
            return False
        self.elegir_flujo(True)
        return True

    def _hover_flecha(self, pos):
        i = self.flujo_en(pos)
        if i != getattr(self, "_hover_flujo", -1):
            self._hover_flujo = i
            self.update()
        return i
