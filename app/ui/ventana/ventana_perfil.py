"""Perfil longitudinal en la app (mezcla de `Main`; pedido del usuario 2026-10-31: «el perfil no siempre es de
una utilidad, sino de un tramo… la manera más fácil y automática»).

Panel acoplado DEBAJO del plano (Ver → «Perfil longitudinal», F4, o el riel). Con el panel abierto, hacer clic en
una utilidad del plano arma el recorrido AUTOMÁTICO que pasa por ese tramo, con la regla de `CREAR_PERFIL_RED`
(`nucleo/perfil_recorrido`: sigue de frente en cada nodo, ≤45°; corta en un empate). Inicio A y fin B con dos
clics: `ventana_perfil_ab` (`perfil_extender`/`perfil_acortar` quedan como funciones; sus opciones del menú ⋯ se
quitaron el 2026-11-09, pedido del usuario).
El dibujo (`ui/comun/perfil_vista`) es el de la vista de perfil de Civil 3D; arrastrar un punto cambia la cota
de ese nodo en TODAS las utilidades que llegan ahí (las mismas cotas de «Cotas por tramo», un paso de deshacer).
Los perfiles se pueden guardar con nombre (`Main.perfiles`, van al .digproj y al DXF: `PDFCAD_PERFIL`).
"""
from __future__ import annotations

import copy
import math

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import edicion3d, perfil_datos as PD, perfil_recorrido as PR
from traduccion.i18n import bind as _bind, t as _tr
from ui.comun import rediseno as R
from ui.comun.perfil_vista import AreaPerfil, VistaPerfil
from ui.comun.theme import al_tema as _theme_al_tema
from ui.comun.icons import icon
from ui.comun.ui_common import layer_qcolor
from ui.ventana.ventana_perfil_ab import PerfilABMixin
from ui.ventana.ventana_perfil_estado import EstadoPerfilMixin
from ui.ventana.ventana_perfil_guardados import GuardadosPerfilMixin
from ui.ventana.ventana_perfil_plano import PlanoPerfilMixin
from ui.ventana.ventana_perfil_ramales import RamalesPerfilMixin

VE_OPCIONES = (None, 1.0, 2.0, 2.5, 5.0, 10.0, 20.0)


class PerfilMixin(PerfilABMixin, RamalesPerfilMixin, GuardadosPerfilMixin, PlanoPerfilMixin,
                  EstadoPerfilMixin):
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
        if self._perfil_rec is None:
            self.perfil_elegir("a")                   # franja guía: «① Haz clic donde EMPIEZA el perfil (A)»
        self._perfil_al_dia(forzar=True)
        return dock

    def cerrar_perfil(self):
        dock = getattr(self, "_perfil_dock", None)
        if dock is not None:
            dock.hide()
        self._perfil_quitar_resalte()
        self._perfil_quitar_pista()

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
        self._perfil_ab_guia(v)                       # «① Haz clic donde EMPIEZA… ② donde TERMINA…»
        self._perfil_ab_fichas()
        # por qué se cortó el recorrido (empate en una unión): aviso discreto con la salida
        self.lbl_perfil_corte = QtWidgets.QLabel()
        self.lbl_perfil_corte.setProperty("rol", "t2")
        self.lbl_perfil_corte.setWordWrap(True)
        self.lbl_perfil_corte.hide()
        v.addWidget(self.lbl_perfil_corte)
        self.perfil_vista = VistaPerfil()
        _bind(self.perfil_vista, "setToolTip",
              "Arrastra un punto (o ↑ ↓) para cambiar su cota · ← → Inicio Fin = nodos · Ctrl + rueda = acercar · "
              "botón derecho = desplazar · doble clic = tamaño original")
        self.perfil_vista.cotaCambiada.connect(self._perfil_cota)
        self._perfil_flujo_conectar(self.perfil_vista)                # flujo: elegir el punto, ojo (ventana_flujo_perfil)
        self.perfil_vista.nodoElegido.connect(lambda _k: (self._perfil_resaltar(), self._perfil_barra()))
        self.perfil_vista.pasoElegido.connect(lambda _i: self._perfil_resaltar())
        self.perfil_vista.nodoHover.connect(lambda _k: self._perfil_barra())
        self.perfil_vista.estacionHover.connect(self._perfil_marcar_estacion)
        self.perfil_vista.ramalPedido.connect(lambda k: self.perfil_ramal(k))
        # el perfil a su tamaño (no se achica con el panel): si no cabe, barras de desplazamiento
        self.perfil_area = AreaPerfil(self.perfil_vista)
        v.addWidget(self.perfil_area, 1)
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
        _theme_al_tema(self, lambda _n: self._perfil_resaltar())
        return dock

    def _perfil_cabecera(self):
        """Título · [A 1+00 ⟷ B 3+45 | ⇄ | ↺] · Nuevo perfil · VE · ⋯ · cerrar."""
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

        self._perfil_ab_cabecera(lay)
        h.addWidget(seg)

        self.btn_perfil_alertas = QtWidgets.QToolButton()
        self.btn_perfil_alertas.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        _bind(self.btn_perfil_alertas, "setToolTip", "Ir a la siguiente alerta del perfil")
        self.btn_perfil_alertas.clicked.connect(lambda: self.perfil_siguiente_alerta())
        self.btn_perfil_alertas.hide()
        h.addWidget(self.btn_perfil_alertas)
        self._perfil_flujo_cabecera(h)                # [⇥⇤ Flujo] y el ojo (gravedad y presión)


        b = QtWidgets.QPushButton()
        b.setIcon(icon("mdi:file-plus-outline"))
        _bind(b, "setText", "Nuevo perfil")
        _bind(b, "setToolTip", "Un perfil en blanco: haz clic donde empieza (A) y donde termina (B)")
        b.setAutoDefault(False)
        b.clicked.connect(lambda: self.perfil_nuevo())
        self.btn_perfil_nuevo = b
        h.addWidget(b)

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
        self._perfil_poner(rec, encuadrar=True, a=None)
        return rec

    # ------------------------------------------------------------------ ramales

    def _perfil_poner(self, rec, encuadrar=False, nombre=None, a="actual"):
        """`a` = ancla del inicio A (las estaciones empiezan de ese lado); "actual" = la de ahora; None = el
        sentido automático. Después, A = la punta donde empieza."""
        if a == "actual":
            a = getattr(self, "_perfil_a", None)
        rec = self._perfil_orientar(rec, a) if a else rec
        self._perfil_rec = rec
        self._perfil_nombre = nombre
        self._perfil_anclas = self._anclas_de(rec) if rec else None
        self._perfil_a = self._perfil_anclas[0] if self._perfil_anclas else None
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
        r = PR.entre(g, e0, e1)
        if r is None:
            return None
        # A o B justo en un NODO (vértice, buzón, válvula: el imán): el perfil empieza/termina AHÍ; el tramo de la
        # punta que queda del otro lado del nodo (lo eligió `arista_cerca` por estar pegado a él) sobra
        tol = max(PR.TOL_FT / ft, 3.0)

        def en_nodo(k, ancla):
            nx, ny = g.nodos[r.nodos[k]]
            return math.hypot(nx - ancla[1], ny - ancla[2]) <= tol
        # cada punta con SU ancla (la del tramo que quedó en esa punta; `entre` puede dar el recorrido al revés)
        a_ini = ini if r.pasos[0].arista == e0 else fin
        a_fin = fin if r.pasos[-1].arista == e1 else ini
        if len(r.pasos) > 1 and en_nodo(1, a_ini):
            r = PR.acortar(r, al_final=False) or r
        if len(r.pasos) > 1 and en_nodo(len(r.nodos) - 2, a_fin):
            r = PR.acortar(r, al_final=True) or r
        return r

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
                if self._perfil_clic_ab(i, clic):     # A, B o un perfil nuevo (`ventana_perfil_ab`)
                    return
        if forzar or self._perfil_firma != self._firma_perfil():
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
        self._perfil_firma = self._firma_perfil()
        rec = self._perfil_rec
        if rec is not None and self._perfil_anclas is not None and not encuadrar:
            rec = self._perfil_orientar(self._rec_de_anclas(*self._perfil_anclas), self._perfil_anclas[0])
            self._perfil_rec = rec
        datos = None
        if rec is not None and rec.pasos:
            numero = self._perfil_numero()
            try:
                datos = PD.armar(self.pipes, self.structures, getattr(self, "_accs_todos", None) or [],
                                 rec, self._ft(), numero, valvulas=self._valvulas_perfil())
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
        self._perfil_ab_fichas()
        self._flujo_perfil_refrescar()



    # ------------------------------------------------------------------ resalte en el plano



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






    # ------------------------------------------------------------------ plano ↔ perfil





