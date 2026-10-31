"""Perfil longitudinal en la app (mezcla de `Main`; pedido del usuario 2026-10-31: «el perfil no siempre es de
una utilidad, sino de un tramo… la manera más fácil y automática»).

Panel acoplado DEBAJO del plano (Ver → «Perfil longitudinal», F4, o el riel). Con el panel abierto, hacer clic en
una utilidad del plano arma el recorrido AUTOMÁTICO que pasa por ese tramo, con la regla de `CREAR_PERFIL_RED`
(`nucleo/perfil_recorrido`: sigue de frente en cada nodo, ≤45°; corta en un empate). «Inicio −/+» y «Fin −/+»
lo acortan o lo extienden un tramo; «Limitar hasta…» = el siguiente clic fija el final (camino más corto).
El dibujo (`ui/comun/perfil_vista`) es el de la vista de perfil de Civil 3D; arrastrar un punto cambia la cota
de ese nodo en TODAS las utilidades que llegan ahí (las mismas cotas de «Cotas por tramo», un paso de deshacer).
Los perfiles se pueden guardar con nombre (`Main.perfiles`, van al .digproj y al DXF: `PDFCAD_PERFIL`).
"""
from __future__ import annotations

import copy
import math

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import edicion3d, model_ops, perfil_datos as PD, perfil_recorrido as PR, perfil_textos as PT
from nucleo.model import Z_MARK
from traduccion.i18n import bind as _bind, t as _tr
from ui.comun import rediseno as R
from ui.comun.perfil_vista import VistaPerfil
from ui.comun.theme import THEME_BUS, tokens
from ui.comun.icons import icon
from ui.comun.ui_common import layer_qcolor

VE_OPCIONES = (None, 1.0, 2.0, 2.5, 5.0, 10.0, 20.0)


class PerfilMixin:
    # ------------------------------------------------------------------ panel

    def abrir_perfil(self):
        """Muestra u oculta el panel del perfil. Si hay una utilidad elegida, arranca con ella."""
        dock = self._perfil_panel()
        if dock.isVisible():
            self.cerrar_perfil()
            return dock
        dock.show()
        if self._perfil_rec is None and 0 <= self.sel_pipe < len(self.pipes):
            pts = self.pipes[self.sel_pipe]["pts"]
            m = pts[len(pts) // 2]
            self.perfil_desde(self.sel_pipe, m[0], m[1])
        self._perfil_al_dia(forzar=True)
        return dock

    def cerrar_perfil(self):
        dock = getattr(self, "_perfil_dock", None)
        if dock is not None:
            dock.hide()
        self._perfil_quitar_resalte()

    def _perfil_visible(self):
        dock = getattr(self, "_perfil_dock", None)
        return dock is not None and not dock.isHidden()

    def _perfil_panel(self):
        dock = getattr(self, "_perfil_dock", None)
        if dock is not None:
            return dock
        self._perfil_rec = None
        self._perfil_anclas = None
        self._perfil_nombre = None
        self._perfil_datos = None
        self._perfil_firma = None
        self._perfil_clic_visto = getattr(self, "_perfil_clic", None)
        self._perfil_resalte = []
        self._perfil_marca = None                  # punto en el plano de la estación bajo el ratón del perfil
        self._perfil_pila = []                     # perfiles desde los que se abrió un ramal: [(anclas, nombre)]
        dock = QtWidgets.QDockWidget(self)
        dock.setObjectName("perfilDock")
        _bind(dock, "setWindowTitle", "Perfil longitudinal")
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QtWidgets.QWidget())
        cuerpo = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(cuerpo)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(4)
        v.addLayout(self._perfil_cabecera())
        # por qué se cortó el recorrido (empate en una unión): aviso discreto con la salida
        self.lbl_perfil_corte = QtWidgets.QLabel()
        self.lbl_perfil_corte.setProperty("rol", "t2")
        self.lbl_perfil_corte.setWordWrap(True)
        self.lbl_perfil_corte.hide()
        v.addWidget(self.lbl_perfil_corte)
        self.perfil_vista = VistaPerfil()
        _bind(self.perfil_vista, "setToolTip",
              "Arrastra un punto (o ↑ ↓) para cambiar su cota · ← → Inicio Fin = nodos · rueda = acercar · "
              "botón derecho = desplazar · doble clic = encuadrar")
        self.perfil_vista.cotaCambiada.connect(self._perfil_cota)
        self.perfil_vista.nodoElegido.connect(lambda _k: (self._perfil_resaltar(), self._perfil_barra()))
        self.perfil_vista.pasoElegido.connect(lambda _i: self._perfil_resaltar())
        self.perfil_vista.nodoHover.connect(lambda _k: self._perfil_barra())
        self.perfil_vista.estacionHover.connect(self._perfil_marcar_estacion)
        self.perfil_vista.ramalPedido.connect(lambda k: self.perfil_ramal(k))
        v.addWidget(self.perfil_vista, 1)
        # barra de datos FIJA: el nodo señalado (o el elegido)
        self.lbl_perfil_datos = QtWidgets.QLabel()
        self.lbl_perfil_datos.setProperty("rol", "t2")
        self.lbl_perfil_datos.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        v.addWidget(self.lbl_perfil_datos)
        self.canvas.moved.connect(self._perfil_raton)
        dock.setWidget(cuerpo)
        self.setCorner(QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        dock.hide()
        self._perfil_dock = dock
        self.resizeDocks([dock], [max(300, int(self.height() * 0.4))], QtCore.Qt.Vertical)
        THEME_BUS.changed.connect(lambda _n: self._perfil_resaltar())
        return dock

    def _perfil_cabecera(self):
        """Título · [− Inicio + | − Fin + | Limitar] · [Básico | Completo] · VE · ⋯ · cerrar."""
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(8)
        self.btn_perfil_volver = QtWidgets.QToolButton()
        self.btn_perfil_volver.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btn_perfil_volver.setIcon(icon("mdi:arrow-left"))
        self.btn_perfil_volver.clicked.connect(lambda: self.perfil_volver())
        self.btn_perfil_volver.hide()
        h.addWidget(self.btn_perfil_volver)
        self.lbl_perfil = QtWidgets.QLabel()
        self.lbl_perfil.setProperty("rol", "h3")
        h.addWidget(self.lbl_perfil, 1)

        seg = QtWidgets.QFrame()
        seg.setObjectName("segmentado")
        lay = QtWidgets.QHBoxLayout(seg)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)

        def boton(texto, tip, fn):
            b = QtWidgets.QPushButton(texto)
            b.setProperty("kind", "seg")
            b.setAutoDefault(False)
            _bind(b, "setToolTip", tip)
            b.clicked.connect(fn)
            lay.addWidget(b)
            return b
        for nombre, al_final in (("Inicio", False), ("Fin", True)):
            boton("−", "Acortar un tramo", lambda _=False, f=al_final: self.perfil_acortar(f))
            lbl = QtWidgets.QLabel()
            lbl.setProperty("rol", "t2")
            _bind(lbl, "setText", nombre)
            lay.addWidget(lbl)
            boton("+", "Extender un tramo", lambda _=False, f=al_final: self.perfil_extender(f))
            sep = QtWidgets.QFrame()
            sep.setFrameShape(QtWidgets.QFrame.VLine)
            lay.addWidget(sep)
        self.btn_perfil_limitar = R.boton_icono("map-marker-path", "Limitar hasta…: el siguiente clic en el plano "
                                                "fija el final del perfil", checkable=True)
        lay.addWidget(self.btn_perfil_limitar)
        h.addWidget(seg)

        self.btn_perfil_alertas = QtWidgets.QToolButton()
        self.btn_perfil_alertas.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        _bind(self.btn_perfil_alertas, "setToolTip", "Ir a la siguiente alerta del perfil")
        self.btn_perfil_alertas.clicked.connect(lambda: self.perfil_siguiente_alerta())
        self.btn_perfil_alertas.hide()
        h.addWidget(self.btn_perfil_alertas)

        det = QtWidgets.QFrame()
        det.setObjectName("segmentado")
        ld = QtWidgets.QHBoxLayout(det)
        ld.setContentsMargins(3, 3, 3, 3)
        ld.setSpacing(2)
        grupo = QtWidgets.QButtonGroup(det)
        self.btn_perfil_detalle = {}
        for clave, texto, tip in (("auto", "Auto", "Rótulos completos si caben; si no, básicos"),
                                  ("basico", "Básico", "Rótulos cortos: solo qué es cada punto"),
                                  ("completo", "Completo", "Rótulos completos, como en Civil 3D")):
            b = QtWidgets.QPushButton()
            _bind(b, "setText", texto)
            _bind(b, "setToolTip", tip)
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setChecked(clave == "auto")
            b.clicked.connect(lambda _=False, c=clave: self.perfil_vista.set_detalle(c))
            grupo.addButton(b)
            ld.addWidget(b)
            self.btn_perfil_detalle[clave] = b
        h.addWidget(det)

        self.cmb_perfil_ve = QtWidgets.QComboBox()
        _bind(self.cmb_perfil_ve, "setToolTip", "Exageración vertical")
        for ve in VE_OPCIONES:
            self.cmb_perfil_ve.addItem(_tr("Automática") if ve is None else _tr("VE ×{v}").format(v=f"{ve:g}"), ve)
        self.cmb_perfil_ve.currentIndexChanged.connect(
            lambda _k: self.perfil_vista.set_exageracion(self.cmb_perfil_ve.currentData()))
        h.addWidget(self.cmb_perfil_ve)

        self.btn_perfil_mas = R.boton_icono("dots-horizontal", "Perfiles guardados, guardar y encuadrar")
        self.btn_perfil_mas.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.btn_perfil_mas.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.menu_perfil = QtWidgets.QMenu(self.btn_perfil_mas)
        self.btn_perfil_mas.setMenu(self.menu_perfil)
        h.addWidget(self.btn_perfil_mas)
        h.addWidget(R.boton_icono("close", "Cerrar el perfil", self.cerrar_perfil))
        return h

    # ------------------------------------------------------------------ recorrido

    def _ft(self):
        return self.scale / self.zoom if self.scale and self.zoom else 0.0

    def perfil_desde(self, i, x, y):
        """Recorrido automático por el tramo de la utilidad `i` más cercano a (x, y)."""
        ft = self._ft()
        rec = PR.desde(self.pipes, i, x, y, ft) if ft else None
        self._perfil_pila = []                         # un perfil nuevo desde el plano: sin «Volver»
        self._perfil_poner(rec, encuadrar=True)
        return rec

    # ------------------------------------------------------------------ ramales

    def _perfil_ramales(self, k):
        rec = self._perfil_rec
        if rec is None or not (0 <= k < len(rec.nodos)):
            return []
        return PR.ramales(rec, k)

    def _es_origen(self, k):
        """¿El nodo `k` es la T desde la que se abrió este ramal? (su rótulo = volver)."""
        pila = getattr(self, "_perfil_pila", None)
        rec = self._perfil_rec
        if not pila or rec is None or not (0 <= k < len(rec.nodos)):
            return False
        x, y = rec.grafo.nodos[rec.nodos[k]]
        ox, oy = pila[-1][3]
        return math.hypot(x - ox, y - oy) <= max(PR.TOL_FT / max(self._ft(), 1e-9), 1.0)

    def perfil_ramal(self, k, indice=None):
        """Abre el perfil del ramal que sale del nodo `k` (con varios, un menú para elegir; `indice` lo elige).
        El perfil de ahora queda en la pila de «Volver». En el perfil de un ramal, su T de origen vuelve."""
        if self._es_origen(k):
            return self.perfil_volver()
        es = self._perfil_ramales(k)
        if not es:
            return None
        if indice is None and len(es) > 1:
            g = self._perfil_rec.grafo
            m = QtWidgets.QMenu(self)
            for j, e in enumerate(es):
                ar = g.aristas[e]
                p = self.pipes[ar.pipe]
                m.addAction(_tr("Ramal {n}").format(n=p.get("name") or model_ops.nombre_por_defecto(p, ar.pipe)),
                            lambda j=j: self.perfil_ramal(k, j))
            m.exec(QtGui.QCursor.pos())
            return None
        e = es[indice or 0]
        rec = PR.ramal(self._perfil_rec.grafo, self._perfil_rec.nodos[k], e)
        PR.marcar_soleras(rec.grafo, self.pipes)
        rec = PR.rehacer(rec)
        origen = self._perfil_rec.grafo.nodos[self._perfil_rec.nodos[k]]
        self._perfil_pila.append((self._perfil_anclas, getattr(self, "_perfil_nombre", None),
                                  self._perfil_titulo_corto(), origen))
        self._perfil_poner(rec, encuadrar=True)
        return rec

    def perfil_volver(self):
        """Vuelve al perfil desde el que se abrió el ramal."""
        if not self._perfil_pila:
            return False
        anclas, nombre, _t, _o = self._perfil_pila.pop()
        rec = self._rec_de_anclas(*anclas) if anclas else None
        if rec is None:
            self._perfil_pila = []
            return False
        self._perfil_poner(rec, encuadrar=True, nombre=nombre)
        return True

    def _perfil_titulo_corto(self):
        d = getattr(self, "_perfil_datos", None)
        return (getattr(self, "_perfil_nombre", None) or (d.red if d else "")) or _tr("Perfil")

    def _perfil_poner(self, rec, encuadrar=False, nombre=None):
        self._perfil_rec = rec
        self._perfil_nombre = nombre
        self._perfil_anclas = self._anclas_de(rec) if rec else None
        self._perfil_firma = None
        self._perfil_refrescar(encuadrar)

    def _anclas_de(self, rec):
        g = rec.grafo
        a, b = g.aristas[rec.pasos[0].arista], g.aristas[rec.pasos[-1].arista]
        return ([a.pipe, (a.pa[0] + a.pb[0]) / 2, (a.pa[1] + a.pb[1]) / 2],
                [b.pipe, (b.pa[0] + b.pb[0]) / 2, (b.pa[1] + b.pb[1]) / 2])

    def _rec_de_anclas(self, ini, fin):
        """El recorrido entre dos tramos (utilidad, x, y), o None si ya no existe."""
        ft = self._ft()
        if not ft:
            return None
        i0 = self._utilidad_de_ancla(ini)
        i1 = self._utilidad_de_ancla(fin)
        if i0 is None or i1 is None:
            return None
        g = PR.marcar_soleras(PR.construir_grafo(self.pipes, i0, ft), self.pipes)
        e0 = PR.arista_cerca(g, ini[1], ini[2], i0)
        e1 = PR.arista_cerca(g, fin[1], fin[2], i1)
        if e0 is None or e1 is None:
            return None
        return PR.entre(g, e0, e1)

    def _utilidad_de_ancla(self, ancla):
        i, x, y = int(ancla[0]), float(ancla[1]), float(ancla[2])
        tol = max(PR.TOL_FT / self._ft(), 3.0)

        def dist(j):
            pts = self.pipes[j].get("pts") or []
            return min((PR._dist_seg((x, y), a, b) for a, b in zip(pts, pts[1:])), default=math.inf)
        if 0 <= i < len(self.pipes) and dist(i) <= tol:
            return i
        mejor = min(range(len(self.pipes)), key=dist, default=None)
        return mejor if mejor is not None and dist(mejor) <= tol else None

    def perfil_extender(self, al_final=True):
        if self._perfil_rec is not None:
            r = PR.extender(self._perfil_rec, al_final)
            if r is not None:
                self._perfil_poner(PR.rehacer(r), encuadrar=True, nombre=self._perfil_nombre)

    def perfil_acortar(self, al_final=True):
        if self._perfil_rec is not None:
            r = PR.acortar(self._perfil_rec, al_final)
            if r is not None:
                self._perfil_poner(PR.rehacer(r), encuadrar=True, nombre=self._perfil_nombre)

    # ------------------------------------------------------------------ al día con el plano

    def _perfil_al_dia(self, forzar=False):
        """Al final de cada redibujo: el clic nuevo en el plano y los cambios del modelo."""
        if not self._perfil_visible():
            return
        clic = getattr(self, "_perfil_clic", None)
        i = self.sel_pipe
        # solo cuando la utilidad elegida es la del clic (un redibujo intermedio llega antes de elegirla)
        if clic is not self._perfil_clic_visto and (clic is None or self._cerca_de(i, clic)):
            self._perfil_clic_visto = clic
            if clic is not None and 0 <= i < len(self.pipes):
                if self.btn_perfil_limitar.isChecked() and self._perfil_rec is not None:
                    self.btn_perfil_limitar.setChecked(False)
                    ini = self._perfil_anclas[0]
                    r = self._rec_de_anclas(ini, [i, clic[0], clic[1]])
                    if r is not None:
                        self._perfil_poner(r, encuadrar=True, nombre=self._perfil_nombre)
                        return
                elif not self._en_el_recorrido(i, clic):
                    self.perfil_desde(i, clic[0], clic[1])
                    return
        if forzar or self._perfil_firma != self._firma_modelo():
            self._perfil_refrescar()
        else:
            self._perfil_alertas()                    # los avisos pueden llegar después (cálculo de fondo)

    def _cerca_de(self, i, clic):
        if not (0 <= i < len(self.pipes)):
            return False
        pts = self.pipes[i].get("pts") or []
        thr = 14.0 / max(1e-6, self.canvas.transform().m11())
        return any(PR._dist_seg(clic, a, b) <= thr for a, b in zip(pts, pts[1:]))

    def _en_el_recorrido(self, i, clic):
        rec = self._perfil_rec
        if rec is None:
            return False
        g = rec.grafo
        for p in rec.pasos:
            a = g.aristas[p.arista]
            if a.pipe == i and PR._dist_seg(clic, a.pa, a.pb) <= max(10.0, PR.TOL_FT / max(self._ft(), 1e-9)):
                return True
        return False

    def _perfil_refrescar(self, encuadrar=False):
        """Rearma los datos (la geometría puede haber cambiado: se rehace desde sus dos tramos de punta)."""
        if not self._perfil_visible() and not encuadrar:
            return
        self._perfil_firma = self._firma_modelo()
        rec = self._perfil_rec
        if rec is not None and self._perfil_anclas is not None and not encuadrar:
            rec = self._rec_de_anclas(*self._perfil_anclas)
            self._perfil_rec = rec
        datos = None
        if rec is not None and rec.pasos:
            numero = self._perfil_numero()
            try:
                datos = PD.armar(self.pipes, self.structures, getattr(self, "_accs_todos", None) or [],
                                 rec, self._ft(), numero)
            except Exception:                         # nunca tumbar el redibujo por el perfil
                import traceback
                traceback.print_exc()
                datos = None
        self._perfil_datos = datos
        capa = self.pipes[rec.grafo.aristas[rec.pasos[0].arista].pipe].get("layer") if datos else ""
        self.perfil_vista.set_perfil(datos, layer_qcolor(capa) if datos else None,
                                     lambda j: layer_qcolor(self.pipes[j].get("layer") or "")
                                     if 0 <= j < len(self.pipes) else QtGui.QColor("#888"), encuadrar)
        self._perfil_titulo()
        self._perfil_lista()
        self._perfil_corte()
        rec = self._perfil_rec
        self.perfil_vista.con_ramal = ({k for k in range(len(rec.nodos)) if PR.ramales(rec, k) or self._es_origen(k)}
                                       if datos else set())
        pila = getattr(self, "_perfil_pila", [])
        self.btn_perfil_volver.setVisible(bool(pila))
        if pila:
            self.btn_perfil_volver.setText(_tr("Volver a {n}").format(n=pila[-1][2]))
        self._perfil_alertas()
        self._perfil_barra()
        self._perfil_resaltar()

    def _perfil_numero(self):
        nombre = getattr(self, "_perfil_nombre", None)
        for k, p in enumerate(self.perfiles):
            if p.get("nombre") == nombre:
                return k + 1
        return len(self.perfiles) + 1

    def _perfil_titulo(self):
        d = self._perfil_datos
        if d is None:
            self.lbl_perfil.setText(_tr("Perfil longitudinal"))
            return
        from nucleo import perfil_textos as T
        nombre = getattr(self, "_perfil_nombre", None) or d.red
        if getattr(self, "_perfil_pila", None):
            nombre = _tr("Ramal de {n}").format(n=self._perfil_pila[-1][2])
        self.lbl_perfil.setText(_tr("{n} · {a} → {b} ({l} ft)").format(
            n=nombre, a=T.estacion(d.e_ini), b=T.estacion(d.e_fin), l=f"{d.e_fin - d.e_ini:.1f}"))

    # ------------------------------------------------------------------ resalte en el plano

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
        for p in d.pasos:
            camino.moveTo(*p.p0)
            camino.lineTo(*p.p1)
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
            c2.moveTo(*d.pasos[i].p0)
            c2.lineTo(*d.pasos[i].p1)
            pen2 = QtGui.QPen(QtGui.QColor(tk.accent), 4)
            pen2.setCosmetic(True)
            it2 = sc.addPath(c2, pen2)
            it2.setZValue(Z_MARK + 0.4)
            self._perfil_resalte.append(it2)
        if 0 <= k < len(d.nodos):
            n = d.nodos[k]
            m = QtWidgets.QGraphicsEllipseItem(-7, -7, 14, 14)
            m.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            m.setPos(n.x, n.y)
            m.setPen(QtGui.QPen(QtGui.QColor(tk.text_on_accent), 2))
            m.setBrush(QtGui.QColor(tk.accent))
            m.setZValue(Z_MARK + 0.5)
            sc.addItem(m)
            self._perfil_resalte.append(m)

    # ------------------------------------------------------------------ editar cotas

    def _perfil_cota(self, k, z):
        """La cota del nodo `k` en todas las utilidades que llegan ahí, en UN paso de deshacer."""
        d = getattr(self, "_perfil_datos", None)
        if d is None or not (0 <= k < len(d.nodos)):
            return False
        cambios = {}
        for i, tramo, lado in d.nodos[k].editable:
            cambios.setdefault(i, []).append((tramo, lado, float(z)))
        if not any(any([edicion3d.aplicar_cota(copy.deepcopy(self.pipes[i]), t, lado, v) for t, lado, v in c])
                   for i, c in cambios.items()):
            return False
        self._push()
        for i, c in cambios.items():
            for t, lado, v in c:
                edicion3d.aplicar_cota(self.pipes[i], t, lado, v)
        sel = self.sel_pipe if self.sel_pipe in cambios else next(iter(cambios))
        self._tras_editar_3d(sel)                     # panel del plano al día + redibujo (y este perfil)
        self.perfil_vista.elegir_nodo(k)
        return True

    # ------------------------------------------------------------------ guardados

    def _perfil_lista(self):
        """Menú ⋯: perfiles guardados (el abierto marcado), guardar, quitar y encuadrar."""
        m = getattr(self, "menu_perfil", None)
        if m is None:
            return
        m.clear()
        titulo = m.addAction(_tr("Perfiles guardados ({n})").format(n=len(self.perfiles)))
        titulo.setEnabled(False)
        actual = getattr(self, "_perfil_nombre", None)
        for k, p in enumerate(self.perfiles):
            a = m.addAction(p.get("nombre") or "")
            a.setCheckable(True)
            a.setChecked(p.get("nombre") == actual)
            a.triggered.connect(lambda _=False, i=k: self.perfil_abrir(i))
        m.addSeparator()
        a = m.addAction(icon("mdi:content-save-outline"), _tr("Guardar este perfil…"))
        a.setEnabled(self._perfil_rec is not None)
        a.triggered.connect(lambda: self.perfil_guardar())
        k = next((i for i, p in enumerate(self.perfiles) if p.get("nombre") == actual), -1)
        a = m.addAction(icon("mdi:delete-outline"), _tr("Quitar «{n}» de los guardados").format(n=actual or "")
                        if k >= 0 else _tr("Quitar de los guardados"))
        a.setEnabled(k >= 0)
        a.triggered.connect(lambda: self.perfil_borrar(k))
        m.addSeparator()
        a = m.addAction(icon("mdi:fit-to-page-outline"), _tr("Encuadrar el perfil"))
        a.triggered.connect(lambda: self.perfil_vista.encuadrar())

    def _perfil_corte(self):
        """Por qué el recorrido termina donde termina (empate en una unión)."""
        rec = self._perfil_rec
        ini = rec is not None and rec.ambiguo_ini
        fin = rec is not None and rec.ambiguo_fin
        lados = (_tr("el inicio y el final") if ini and fin else _tr("el inicio") if ini
                 else _tr("el final") if fin else "")
        if not lados:
            self.lbl_perfil_corte.hide()
            return
        self.lbl_perfil_corte.setText(
            _tr("El recorrido se detiene en {l}: en esa unión hay dos caminos casi igual de rectos. "
                       "Usa «+» para seguir por el más recto o «Limitar hasta…» para elegir.").format(l=lados))
        self.lbl_perfil_corte.setStyleSheet(f"color: {tokens().warning};")
        self.lbl_perfil_corte.show()

    def _perfil_barra(self):
        """Barra de datos: el nodo bajo el ratón o, si no, el elegido."""
        lbl = getattr(self, "lbl_perfil_datos", None)
        if lbl is None:
            return
        d, v = getattr(self, "_perfil_datos", None), self.perfil_vista
        k = v._hover if v._hover >= 0 else v._sel_nodo
        if d is None:
            lbl.setText("")
            return
        if not (0 <= k < len(d.nodos)):
            lbl.setText(_tr("{n} tramos · {c} cruces · elige un punto (clic o ← →) para ver sus datos").format(
                n=len(d.pasos), c=len(d.cruces)))
            return
        from nucleo import perfil_textos as T
        n = d.nodos[k]
        llega = d.pasos[k - 1] if k > 0 else None
        sale = d.pasos[k] if k < len(d.pasos) else None
        ref = llega or sale
        z = llega.z1 if llega else sale.z0
        partes = [T.estacion(n.e)]
        if n.cod:
            partes.append(n.cod)
        partes.append(_tr("solera {z}").format(z=T.cota(z)))
        partes.append(_tr("corona {z}").format(z=T.cota(z + ref.alto_ft)))
        if n.rim is not None:
            partes.append(_tr("tapa {z}").format(z=T.cota(n.rim)))
        if llega:
            partes.append(_tr("llega {p}").format(p=f"{llega.pendiente * 100:+.2f} %"))
        if sale:
            partes.append(_tr("sale {p}").format(p=f"{sale.pendiente * 100:+.2f} %"))
        if not n.editable:
            partes.append(_tr("(cota no editable aquí: es una T a mitad de tramo)"))
        texto = "  ·  ".join(partes)
        al = v.alertas_de_nodo(k) + [a for i in (k - 1, k) if 0 <= i < len(d.pasos) for a in v.alertas_de_paso(i)]
        if al:
            texto += "<br><span style='color:%s'>%s</span>" % (
                tokens().danger, "  ·  ".join(dict.fromkeys(a.mensaje for a in al)))
            lbl.setText("<span>" + texto + "</span>")
        else:
            lbl.setText(texto)

    def _perfil_alertas(self):
        """Alertas del perfil (normativa del plano, recubrimiento, contrapendiente) y el botón que las cuenta."""
        d = getattr(self, "_perfil_datos", None)
        alertas = []
        if d is not None:
            from nucleo import perfil_validar
            from nucleo.model import COVER_MIN_FT
            capa = self.pipes[d.pasos[0].pipe].get("layer") or "" if d.pasos else ""
            ft = self._ft()
            tol = max(2.0 / ft, 3.0) if ft else 3.0
            try:
                alertas = perfil_validar.validar(d, getattr(self, "_normas_avisos", None) or [],
                                                 COVER_MIN_FT.get(capa), tol)
            except Exception:
                import traceback
                traceback.print_exc()
        self.perfil_vista.set_alertas(alertas)
        b = self.btn_perfil_alertas
        if alertas:
            error = any(a.nivel == "ERROR" for a in alertas)
            b.setIcon(icon("mdi:alert-outline", color=tokens().danger if error else tokens().warning))
            b.setText(_tr("{n} alertas").format(n=len(alertas)) if len(alertas) != 1 else _tr("1 alerta"))
            b.show()
        else:
            b.hide()
        self._perfil_alerta_k = -1

    def perfil_siguiente_alerta(self):
        """Elige el punto de la siguiente alerta y la explica en la barra de datos."""
        v = self.perfil_vista
        al = v.alertas
        if not al:
            return None
        self._perfil_alerta_k = (getattr(self, "_perfil_alerta_k", -1) + 1) % len(al)
        a = al[self._perfil_alerta_k]
        d = self._perfil_datos
        k = a.nodo if a.nodo >= 0 else min(range(len(d.nodos)), key=lambda i: abs(d.nodos[i].e - a.e))
        v.elegir_nodo(k)
        v.set_cursor(a.e)
        self.lbl_perfil_datos.setText(
            "<span style='color:%s'>%s</span>" % (tokens().danger if a.nivel == "ERROR" else tokens().warning,
                                                  _tr("Alerta {i} de {n} · {e} · {m}").format(
                                                      i=self._perfil_alerta_k + 1, n=len(al),
                                                      e=PT.estacion(a.e),
                                                      m=a.mensaje)))
        return a

    # ------------------------------------------------------------------ plano ↔ perfil

    def _perfil_raton(self, x, y):
        """Ratón en el PLANO → la estación en el perfil (sobre su recorrido)."""
        if not self._perfil_visible():
            return
        d = getattr(self, "_perfil_datos", None)
        e = None
        if d is not None:
            thr = 14.0 / max(1e-6, self.canvas.transform().m11())
            mejor = thr
            for p in d.pasos:
                dx, dy = p.p1[0] - p.p0[0], p.p1[1] - p.p0[1]
                L2 = dx * dx + dy * dy
                if L2 <= 1e-12:
                    continue
                t = max(0.0, min(1.0, ((x - p.p0[0]) * dx + (y - p.p0[1]) * dy) / L2))
                dist = math.hypot(p.p0[0] + dx * t - x, p.p0[1] + dy * t - y)
                if dist <= mejor:
                    mejor, e = dist, p.e0 + (p.e1 - p.e0) * t
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
        f = (e - p.e0) / max(p.e1 - p.e0, 1e-9)
        x, y = p.p0[0] + (p.p1[0] - p.p0[0]) * f, p.p0[1] + (p.p1[1] - p.p0[1]) * f
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

    def perfil_guardar(self, nombre=None):
        """Guarda el perfil a la vista con un nombre (si existe, lo reemplaza). Devuelve el nombre."""
        if self._perfil_rec is None or self._perfil_anclas is None:
            return None
        if nombre is None:
            sugerido = getattr(self, "_perfil_nombre", None) or _tr("Perfil {n}").format(n=len(self.perfiles) + 1)
            nombre, ok = QtWidgets.QInputDialog.getText(self, _tr("Guardar perfil"), _tr("Nombre del perfil:"),
                                                        text=sugerido)
            if not ok:
                return None
        nombre = (nombre or "").strip()
        if not nombre:
            return None
        ini, fin = self._perfil_anclas
        dato = {"nombre": nombre, "ini": list(ini), "fin": list(fin)}
        for k, p in enumerate(self.perfiles):
            if p.get("nombre") == nombre:
                self.perfiles[k] = dato
                break
        else:
            self.perfiles.append(dato)
        self._perfil_nombre = nombre
        self._dirty = True
        self._perfil_refrescar()
        return nombre

    def perfil_abrir(self, k):
        if not (0 <= k < len(self.perfiles)):
            return False
        p = self.perfiles[k]
        rec = self._rec_de_anclas(p["ini"], p["fin"])
        if rec is None:
            self.statusBar().showMessage(_tr("Ese perfil ya no existe en el plano: sus utilidades cambiaron."), 6000)
            return False
        if not self._perfil_visible():
            self._perfil_panel().show()
        self._perfil_pila = []
        self._perfil_poner(rec, encuadrar=True, nombre=p.get("nombre"))
        return True

    def perfil_borrar(self, k):
        if not (0 <= k < len(self.perfiles)):
            return False
        if self.perfiles[k].get("nombre") == getattr(self, "_perfil_nombre", None):
            self._perfil_nombre = None
        del self.perfiles[k]
        self._dirty = True
        self._perfil_refrescar()
        return True
