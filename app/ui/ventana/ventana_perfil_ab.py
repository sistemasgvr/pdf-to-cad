"""Elegir el tramo del perfil con DOS CLICS: inicio A y fin B (pedido del usuario 2026-11-06: «elegir el tramo está
raro… no se entiende cuál es el inicio y el fin; debería ser más didáctico»; propuesta revisada con el plugin design).

- Una FRANJA guía arriba del perfil dice qué hacer: «① Haz clic donde EMPIEZA el perfil (A)» → «② Ahora haz clic
  donde TERMINA (B)… o Enter para dejar el recorrido automático». Esc la cierra.
- En la cabecera, dos fichas «A 1+00» y «B 3+45»: clic en una = cambiar SOLO esa punta con el siguiente clic en el
  plano; «⇄» invierte el sentido (A pasa a ser la otra punta); «↺» vuelve a elegir A y B.
- En el plano, una bandera A (verde) y B (roja) en las puntas del recorrido, y las mismas letras en el perfil.
- El perfil va de A a B: las estaciones empiezan en A (`perfil_recorrido.invertir` si la regla automática lo da al
  revés). `_perfil_a` = el ancla de A (utilidad, x, y); los perfiles guardados la llevan en `ini`.
Reemplaza al botón «Limitar hasta…» (las opciones «Extender/Acortar» un tramo del menú ⋯ se quitaron el 2026-11-09).
Mientras se espera A o B, el clic en el plano viene DIRECTO aquí (`_perfil_clic_directo`, desde `on_click`), con el
punto del imán: antes pasaba por la selección y un clic sobre un buzón (que el imán prioriza) o un accesorio elegía
ESE objeto y A/B quedaba esperando hasta el siguiente redibujo (2026-11-09).
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import perfil_recorrido as PR
from nucleo.model import Z_MARK
from traduccion.i18n import bind as _bind, t as _tr
from ui.comun import rediseno as R
from ui.comun.theme import tokens

N_ = lambda s: s          # noqa: E731  (marca para la traducción)
GUIAS = {
    "a": N_("① Haz clic en el plano donde EMPIEZA el perfil (A)."),
    "b": N_("② Ahora haz clic donde TERMINA el perfil (B), o Enter para dejar el recorrido automático."),
    "mover_a": N_("Haz clic en el plano donde debe EMPEZAR el perfil (nuevo A)."),
    "mover_b": N_("Haz clic en el plano donde debe TERMINAR el perfil (nuevo B)."),
}
GUIA_FLUJO = N_("Haz clic en el perfil donde LLEGA el fluido: un buzón, un vértice o un punto de la tubería. Los dos "
                "lados irán hacia ese punto.")
COLOR_A, COLOR_B = "success", "danger"        # tokens del tema
AGARRE_PX = 14                                # radio para agarrar una bandera A/B (px de pantalla)


class PerfilABMixin:
    # ------------------------------------------------------------------ interfaz

    def _perfil_ab_cabecera(self, lay):
        """Fichas «A 1+00 ⟷ B 3+45», invertir y elegir de nuevo (dentro del segmentado de la cabecera)."""
        self._perfil_paso = None
        self._perfil_a = None
        self.btn_perfil_ab = {}
        for clave, tip in (("a", "Inicio del perfil (A). Clic: elegir otro inicio en el plano"),
                           ("b", "Fin del perfil (B). Clic: elegir otro fin en el plano")):
            b = QtWidgets.QPushButton()
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setAutoDefault(False)
            _bind(b, "setToolTip", tip)
            b.clicked.connect(lambda _=False, c=clave: self.perfil_elegir("mover_" + c))
            lay.addWidget(b)
            self.btn_perfil_ab[clave] = b
            if clave == "a":
                flecha = QtWidgets.QLabel("⟷")
                flecha.setProperty("rol", "t2")
                lay.addWidget(flecha)
        lay.addWidget(R.boton_icono("swap-horizontal", "Invertir: el perfil empieza en la otra punta",
                                    lambda: self.perfil_invertir()))
        lay.addWidget(R.boton_icono("refresh", "Elegir de nuevo el inicio (A) y el fin (B)",
                                    lambda: self.perfil_elegir("a")))

    def _perfil_ab_guia(self, v):
        """La franja que dice qué hacer mientras se eligen A y B."""
        self.lbl_perfil_guia = QtWidgets.QLabel()
        self.lbl_perfil_guia.setWordWrap(True)
        self.lbl_perfil_guia.hide()
        v.addWidget(self.lbl_perfil_guia)

    def _perfil_ab_fichas(self):
        d = getattr(self, "_perfil_datos", None)
        from nucleo import perfil_textos as T
        tk = tokens()
        for clave, e in (("a", d.e_ini if d else None), ("b", d.e_fin if d else None)):
            b = self.btn_perfil_ab[clave]
            b.setText(f"{clave.upper()}  {T.estacion(e)}" if e is not None else f"{clave.upper()}  —")
            b.setChecked(self._perfil_paso in (clave, "mover_" + clave))
            col = getattr(tk, COLOR_A if clave == "a" else COLOR_B)
            b.setStyleSheet(f"QPushButton {{ color: {col}; font-weight: 600; }}")
        paso = self._perfil_paso
        if getattr(self, "lbl_perfil_guia", None) is None:
            return
        vista = getattr(self, "perfil_vista", None)
        flujo = vista is not None and vista.eligiendo_flujo()      # elegir hacia dónde va el fluido (ventana_flujo_perfil)
        if paso or flujo:
            texto = (_tr(GUIAS[paso]) + "  " + _tr("(Esc = dejarlo así)")) if paso else                 (_tr(GUIA_FLUJO) + "  " + _tr("(Esc = cancelar)"))
            self.lbl_perfil_guia.setText(texto)
            self.lbl_perfil_guia.setStyleSheet(
                f"background: {tk.accent_soft}; color: {tk.accent_text}; border-radius: 6px; padding: 6px 10px;"
                "font-weight: 600;")
            self.lbl_perfil_guia.show()
        else:
            self.lbl_perfil_guia.hide()

    # ------------------------------------------------------------------ acciones

    def perfil_elegir(self, paso):
        """Pide el siguiente clic en el plano: 'a' (nuevo perfil: A y luego B), 'b', 'mover_a', 'mover_b' o None."""
        if paso in ("mover_a", "mover_b") and getattr(self, "_perfil_rec", None) is None:
            paso = "a"
        if paso and getattr(self, "perfil_vista", None) is not None:
            self.perfil_vista.elegir_flujo(False)       # A/B y el punto de llegada del fluido no se eligen a la vez
        self._perfil_paso = paso
        if not paso:
            self._perfil_quitar_pista()
        self._perfil_ab_fichas()

    def perfil_nuevo(self):
        """«Nuevo perfil»: en blanco (sin recorrido ni nombre) y pide A y B."""
        if not self._perfil_visible():
            self._perfil_panel().show()
        self._perfil_pila = []
        self._perfil_poner(None, encuadrar=True, a=None)
        self.perfil_elegir("a")

    def perfil_limpiar(self):
        """«Limpiar» (menú ⋯): borra el borrador a la vista (no los guardados) y vuelve a elegir A y B."""
        self.perfil_nuevo()

    def perfil_invertir(self):
        rec = getattr(self, "_perfil_rec", None)
        if rec is None or not rec.pasos:
            return False
        self._perfil_poner(PR.invertir(rec), encuadrar=True, nombre=self._perfil_nombre, a=None)
        return True

    def _perfil_clic_ab(self, i, clic):
        """Un clic en la utilidad `i` del plano (x, y). True si lo usó para A/B o para un perfil nuevo."""
        paso = self._perfil_paso
        if paso:                                      # el punto del imán (vértice, buzón, válvula o la tubería)
            r = self._perfil_snap(clic[0], clic[1])
            if r is not None:
                i, clic = r[0], r[1]
        punto = [i, clic[0], clic[1]]
        anclas = getattr(self, "_perfil_anclas", None)
        if paso == "b" and self._perfil_a is not None:
            r = self._rec_de_anclas(self._perfil_a, punto)
            if r is not None:
                self._perfil_poner(r, encuadrar=True, nombre=self._perfil_nombre, a=self._perfil_a)
            self.perfil_elegir(None)
            return True
        if paso == "mover_a" and anclas:
            r = self._rec_de_anclas(punto, anclas[1])
            if r is not None:
                self._perfil_poner(r, encuadrar=True, nombre=self._perfil_nombre, a=punto)
            self.perfil_elegir(None)
            return True
        if paso == "mover_b" and anclas:
            r = self._rec_de_anclas(anclas[0], punto)
            if r is not None:
                self._perfil_poner(r, encuadrar=True, nombre=self._perfil_nombre, a=anclas[0])
            self.perfil_elegir(None)
            return True
        if paso == "a" or not self._en_el_recorrido(i, clic):
            self.perfil_desde(i, clic[0], clic[1])     # vista previa automática mientras se elige B
            self._perfil_a = punto
            self.perfil_elegir("b")
            return True
        return False

    def _perfil_clic_directo(self, x, y):
        """Clic en el plano mientras se espera A o B: va directo al perfil con el punto del imán (vértice, buzón,
        válvula o la tubería), sin elegir el buzón o el accesorio que haya ahí. True si lo usó."""
        if not getattr(self, "_perfil_paso", None) or not self._perfil_visible():
            return False
        r = self._perfil_snap(x, y)
        if r is None:
            return False                              # lejos de toda utilidad: el clic de siempre
        j, q, _que = r
        self._perfil_clic_visto = getattr(self, "_perfil_clic", None)   # un clic anterior pendiente ya no vale
        self._perfil_clic_ab(j, q)
        self._perfil_quitar_pista()
        return True

    def _perfil_ab_tecla(self, enter):
        """Enter / Esc mientras se eligen A y B: se queda el recorrido que hay. True si había algo que cerrar."""
        if not getattr(self, "_perfil_paso", None) or not self._perfil_visible():
            return False
        self.perfil_elegir(None)
        return True

    # ------------------------------------------------------------------ pista con imán (como Buzón / Válvula)

    def _perfil_quitar_pista(self):
        sc = self.canvas.scene()
        for it in getattr(self, "_perfil_pista_items", None) or []:
            try:
                sc.removeItem(it)
            except (RuntimeError, ValueError):
                pass
        self._perfil_pista_items = []

    def _perfil_pista(self, x, y):
        """Mientras se eligen A o B: un círculo con la letra donde quedará el clic (pegado a la tubería más cercana
        a ≤14 px de pantalla), verde si sirve y rojo si es de otra red. Devuelve (utilidad, punto) o None."""
        self._perfil_quitar_pista()
        paso = getattr(self, "_perfil_paso", None)
        if not paso or not self._perfil_visible():
            return None
        s = self._perfil_snap(x, y)
        if s is None:
            return None
        j, q, que = s
        letra = "A" if paso in ("a", "mover_a") else "B"
        ok = True
        rec = getattr(self, "_perfil_rec", None)
        if paso != "a" and rec is not None and not any(ar.pipe == j for ar in rec.grafo.aristas):
            ok = False                                # otra red: no se puede unir con A
        tk = tokens()
        col = QtGui.QColor(30, 200, 60) if ok else QtGui.QColor(tk.danger)
        sc = self.canvas.scene()
        pen = QtGui.QPen(col, 2.0)
        pen.setCosmetic(True)
        rel = QtGui.QColor(col)
        rel.setAlpha(60)
        # en un punto (vértice, buzón, válvula) un cuadrado, como el imán de AutoCAD; sobre la tubería, un círculo
        c = (sc.addRect(-8, -8, 16, 16, pen, QtGui.QBrush(rel)) if que != "tuberia"
             else sc.addEllipse(-8, -8, 16, 16, pen, QtGui.QBrush(rel)))
        txt = QtWidgets.QGraphicsSimpleTextItem(letra)
        f = txt.font()
        f.setBold(True)
        txt.setFont(f)
        txt.setBrush(col)
        txt.setParentItem(c)                          # la letra al lado del círculo, del tamaño de la pantalla
        txt.setPos(10, -22)
        c.setPos(q[0], q[1])
        c.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        c.setZValue(Z_MARK + 20)
        self._perfil_pista_items = [c]
        from nucleo import model_ops
        nombre = model_ops.nombre_por_defecto(self.pipes[j], j)
        donde = {"buzon": _tr("en el buzón de {u}"), "valvula": _tr("en la válvula de {u}"),
                 "vertice": _tr("en un vértice de {u}")}.get(que, _tr("sobre {u}")).format(u=nombre)
        self._info(_tr("Clic para poner {l} aquí, {d} (Esc para dejarlo así).").format(l=letra, d=donde) if ok
                   else _tr("{u} es de otra red: el perfil solo puede seguir la red de A.").format(u=nombre))
        return j, q

    def _perfil_snap(self, x, y):
        """El imán al elegir A o B: (utilidad, punto, qué). Primero un PUNTO a ≤14 px de pantalla —buzón o válvula,
        si no un vértice de la tubería (también sus puntas)—, el más cercano; si no hay, el pie sobre la tubería más
        cercana. `qué` = "buzon" | "valvula" | "vertice" | "tuberia". None = nada cerca (pedido 2026-11-08)."""
        r = 14.0 / max(1e-6, self.canvas.transform().m11())
        cerca = list(self._utilidades_cerca(x, y, r))

        def tuberia_de(px, py):
            """La utilidad que pasa por el punto (la más cercana a él)."""
            mejor = None
            for j in self._utilidades_cerca(px, py, r) or cerca:
                pts = self.pipes[j].get("pts") or []
                d = min((PR._dist_seg((px, py), a, b) for a, b in zip(pts, pts[1:])), default=math.inf)
                if d <= r and (mejor is None or d < mejor[0]):
                    mejor = (d, j)
            return None if mejor is None else mejor[1]

        puntos = []                                   # (prioridad, distancia, utilidad, punto, qué)
        for s in getattr(self, "structures", None) or []:
            if s.get("hidden") or "x" not in s or "y" not in s:
                continue
            d = math.hypot(float(s["x"]) - x, float(s["y"]) - y)
            if d <= r:
                j = tuberia_de(float(s["x"]), float(s["y"]))
                if j is not None:
                    puntos.append((0, d, j, (float(s["x"]), float(s["y"])), "buzon"))
        for lug in getattr(self, "_valv_lugares", None) or []:
            if getattr(lug, "ok", False) and 0 <= lug.pipe < len(self.pipes):
                d = math.hypot(lug.x - x, lug.y - y)
                if d <= r:
                    puntos.append((0, d, lug.pipe, (lug.x, lug.y), "valvula"))
        for j in cerca:
            for p in self.pipes[j].get("pts") or []:
                d = math.hypot(p[0] - x, p[1] - y)
                if d <= r:
                    puntos.append((1, d, j, (p[0], p[1]), "vertice"))
        if puntos:
            _pr, _d, j, q, que = min(puntos, key=lambda t: (t[0], t[1]))
            return j, q, que
        mejor = None
        for j in cerca:
            pts = self.pipes[j].get("pts") or []
            for a, b in zip(pts, pts[1:]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy
                t = 0.0 if L2 <= 1e-12 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
                q = (a[0] + dx * t, a[1] + dy * t)
                d = math.hypot(q[0] - x, q[1] - y)
                if d <= r and (mejor is None or d < mejor[0]):
                    mejor = (d, j, q)
        if mejor is None:
            return None
        return mejor[1], mejor[2], "tuberia"

    # ------------------------------------------------------------------ arrastrar las banderas del plano

    def _perfil_agarra_bandera(self, x, y):
        """Clic sobre la bandera A o B (a ≤ `AGARRE_PX` de pantalla) sin otra herramienta activa: empieza a
        arrastrarla. Mientras, la pista con imán dice dónde caerá; al soltar se cambia SOLO esa punta."""
        d = getattr(self, "_perfil_datos", None)
        if (d is None or not d.pasos or not self._perfil_visible() or getattr(self, "mode", "idle") != "idle"
                or self._perfil_paso):
            return False
        escala = max(1e-6, self.canvas.transform().m11())
        for clave, p in (("a", d.pasos[0].puntos[0]), ("b", d.pasos[-1].puntos[-1])):
            if math.hypot(x - p[0], y - p[1]) * escala <= AGARRE_PX:
                self.perfil_elegir("mover_" + clave)
                self._perfil_pista(x, y)
                return True
        return False

    def _perfil_soltar_bandera(self, x, y):
        """Suelta la bandera: la punta va a la tubería bajo el imán; fuera de una, se queda como estaba."""
        r = self._perfil_pista(x, y)
        if r is None:
            self.perfil_elegir(None)
            return False
        j, q = r
        return self._perfil_clic_ab(j, q)

    # ------------------------------------------------------------------ sentido A → B

    def _perfil_orientar(self, rec, a):
        """El recorrido con las estaciones empezando del lado de A (ancla utilidad, x, y)."""
        if rec is None or not rec.pasos or not a:
            return rec
        g = rec.grafo
        x, y = float(a[1]), float(a[2])

        def dist(paso):
            ar = g.aristas[paso.arista]
            return PR._dist_seg((x, y), ar.pa, ar.pb)
        if len(rec.pasos) == 1:
            ar = g.aristas[rec.pasos[0].arista]
            n0, n1 = g.nodos[rec.nodos[0]], g.nodos[rec.nodos[-1]]
            if math.hypot(x - n1[0], y - n1[1]) < math.hypot(x - n0[0], y - n0[1]) and ar is not None:
                return PR.invertir(rec)
            return rec
        return PR.invertir(rec) if dist(rec.pasos[-1]) < dist(rec.pasos[0]) - 1e-9 else rec

    # ------------------------------------------------------------------ banderas en el plano

    def _perfil_banderas(self, sc):
        """Bandera A (verde) en el inicio y B (roja) en el fin del recorrido, del tamaño de la pantalla."""
        rec, d = self._perfil_rec, getattr(self, "_perfil_datos", None)
        if rec is None or d is None or not d.pasos:
            return []
        tk = tokens()
        out = []
        for letra, p, color in (("A", d.pasos[0].puntos[0], COLOR_A), ("B", d.pasos[-1].puntos[-1], COLOR_B)):
            col = QtGui.QColor(getattr(tk, color))
            grupo = QtWidgets.QGraphicsItemGroup()
            asta = QtWidgets.QGraphicsLineItem(0, 0, 0, -26)
            asta.setPen(QtGui.QPen(col, 2))
            tela = QtWidgets.QGraphicsPathItem()
            camino = QtGui.QPainterPath()
            camino.addRoundedRect(QtCore.QRectF(0, -27, 18, 15), 3, 3)
            tela.setPath(camino)
            tela.setBrush(col)
            tela.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            txt = QtWidgets.QGraphicsSimpleTextItem(letra)
            f = txt.font()
            f.setBold(True)
            f.setPointSizeF(8.5)
            txt.setFont(f)
            txt.setBrush(QtGui.QColor(tk.text_on_accent))
            br = txt.boundingRect()
            txt.setPos(9 - br.width() / 2, -19.5 - br.height() / 2)
            pie = QtWidgets.QGraphicsEllipseItem(-4, -4, 8, 8)
            pie.setBrush(col)
            pie.setPen(QtGui.QPen(QtGui.QColor(tk.surface), 1.5))
            for it in (asta, tela, txt, pie):
                grupo.addToGroup(it)
            grupo.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            grupo.setPos(*p)
            grupo.setZValue(Z_MARK + 0.6)
            grupo.setToolTip(_tr("Inicio del perfil (A)") if letra == "A" else _tr("Fin del perfil (B)"))
            sc.addItem(grupo)
            out.append(grupo)
        return out
