"""Sentido del FLUJO en gravedad y presión (mezcla de `Main`; pedidos del usuario 2026-11-09 y 2026-11-10). Nunca en
eléctrico ni telecom. El dato: `pipe["flujo"]` / `pipe["flujo_hacia"]` (`nucleo/flujo`).

Se elige con un PUNTO DE LLEGADA (2026-11-10: «ya no todo a la izquierda o a la derecha: puede llegar a un buzón del
medio»), no con dos flechas:
- Propiedades de la utilidad, sección «Cotas», fila «Flujo»: [Elegir en el plano] [Auto] … [ojo] y debajo cómo va.
  «Elegir en el plano» = modo «flujo_punto»: el ratón se pega a un buzón, un vértice, una punta o un punto de la línea
  de ESA utilidad (diana verde + flechas de vista previa); clic = el fluido llega ahí (un paso de deshacer) y 5 s de
  flechas que corren hacia ese punto (`ui/comun/flujo_animacion`). Esc o clic derecho = cancelar.
- El ojo: ver u ocultar en el plano las flechas (y la diana de llegada) de TODAS las utilidades con el sentido
  indicado (QSettings `flujo/ver_plano`).
- [⇄ Por tramos]: personalizado tramo por tramo, en el lienzo y con una ficha por tramo (`ventana_flujo_tramos`).
- Perfil: `ventana_flujo_perfil`.
La contrapendiente y la caída en los buzones se validan con este sentido (`nucleo/flujo_validar`, `normas_validar`).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import flujo as FL, model_ops
from nucleo.model import Z_MARK, network_kind
from traduccion.i18n import bind as _bind, t as _tr
from ui.comun import rediseno as R
from ui.comun.icons import icon
from ui.comun.responsive import GridAdaptable, WrapButton
from ui.comun.theme import tokens
from ui.comun.ui_common import layer_qcolor
from ui.ventana.ventana_flujo_perfil import PerfilFlujoMixin
from ui.ventana.ventana_flujo_tramos import MODO_TRAMOS, TramosFlujoMixin

N_ = lambda s: s          # noqa: E731  (marca para la traducción)
VER_PLANO = "flujo/ver_plano"
IMAN_PX = 14.0                                    # radio del imán al elegir (px de pantalla)
MODO = "flujo_punto"
QUE = {"buzon": N_("este buzón"), "punta": N_("esta punta"), "vertice": N_("este vértice"),
       "linea": N_("este punto de la línea")}


def ajuste(clave, defecto=True):
    v = QtCore.QSettings("pdf-to-cad", "app").value(clave, defecto)
    return v not in (False, "false", "False", "0", 0)


def guardar_ajuste(clave, valor):
    QtCore.QSettings("pdf-to-cad", "app").setValue(clave, bool(valor))


def texto_estado(p):
    """Cómo va el fluido en la utilidad, en una frase (debajo de los botones)."""
    if FL.por_tramos(p):
        st = FL.sentidos_tramos(p)
        return _tr("Personalizado por tramos: {a} hacia el fin del tramo, {b} hacia el inicio, {c} automáticos.").format(
            a=st.count(FL.ADELANTE), b=st.count(FL.ATRAS), c=st.count(FL.AUTO))
    if FL.punto(p) is not None:
        return _tr("Llega a un punto intermedio: las dos partes van hacia él.")
    f = FL.fijo(p)
    if f == FL.ADELANTE:
        return _tr("Llega al fin de la utilidad (el último vértice que se dibujó).")
    if f == FL.ATRAS:
        return _tr("Llega al inicio de la utilidad (el primer vértice que se dibujó).")
    if network_kind(p.get("layer") or "") == "pressure":
        return _tr("Sin indicar: a presión la app no deduce hacia dónde va el fluido.")
    return _tr("Automático: en el perfil, hacia el extremo más bajo del recorrido.")


class _CajaFlujo(QtWidgets.QWidget):
    """El QFormLayout del inspector reparte mal el alto de una fila que depende de su ancho (botones que parten su texto,
    fichas en rejilla): su mínimo es siempre lo que pide su contenido (como `ventana_diametro_ia._TarjetaIA`)."""

    def _ajustar_minimo(self):
        lay = self.layout()
        if lay is not None and self.width() > 0:
            alto = lay.totalHeightForWidth(self.width())
            if alto > 0 and alto != self.minimumHeight():
                self.setMinimumHeight(alto)

    def event(self, evento):
        if evento.type() == QtCore.QEvent.LayoutRequest:
            self._ajustar_minimo()
        return super().event(evento)

    def resizeEvent(self, evento):  # noqa: N802
        super().resizeEvent(evento)
        self._ajustar_minimo()


class FlujoMixin(PerfilFlujoMixin, TramosFlujoMixin):
    # ------------------------------------------------------------------ propiedades de la utilidad

    def _flujo_construir(self):
        """La fila «Flujo» (la pone `ventana_inspector_campos.reorganizar` en la sección Cotas)."""
        caja = _CajaFlujo()
        v = QtWidgets.QVBoxLayout(caja)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.lbl_flujo = QtWidgets.QLabel()             # la fila ocupa todo el ancho: el título va adentro
        _bind(self.lbl_flujo, "setText", "Flujo")
        v.addWidget(self.lbl_flujo)
        fila = QtWidgets.QWidget()                      # [Elegir en el plano] [Por tramos]: 2 columnas o 1 si no caben
        h = GridAdaptable(fila, max_cols=2, spacing=6)
        b = WrapButton()                                # el texto se parte en líneas si el panel es angosto
        b.setIcon(icon("mdi:arrow-collapse-horizontal"))
        _bind(b, "setText", "Elegir en el plano")
        _bind(b, "setToolTip", "Haz clic en el plano donde llega el fluido: un buzón, un vértice, una punta o un punto "
                               "de esta utilidad")
        b.setCheckable(True)
        b.setAutoDefault(False)
        b.clicked.connect(lambda _=False: self.flujo_elegir_en_plano())
        self.btn_flujo_elegir = b
        h.addWidget(b)
        tb = WrapButton()
        tb.setIcon(icon("mdi:swap-horizontal"))
        _bind(tb, "setText", "Por tramos")
        _bind(tb, "setToolTip", "Personalizar el sentido tramo por tramo: clic en cada tramo (o en su ficha) para "
                                "cambiarlo")
        tb.setCheckable(True)
        tb.setAutoDefault(False)
        tb.clicked.connect(lambda _=False: self.flujo_tramos_en_plano())
        self.btn_flujo_tramos = tb
        h.addWidget(tb)
        v.addWidget(fila)
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(6)
        a = QtWidgets.QPushButton()
        a.setProperty("kind", "ghost")
        _bind(a, "setText", "Auto")
        a.setAutoDefault(False)
        a.clicked.connect(lambda _=False: self.poner_flujo([self.sel_pipe], FL.AUTO))
        self.btn_flujo_auto = a
        h.addWidget(a)
        h.addStretch(1)
        self.btn_flujo_ver = R.boton_icono("eye-outline", "Ocultar el sentido del flujo en el plano",
                                           lambda: self.ver_flujo_plano())
        h.addWidget(self.btn_flujo_ver)
        v.addLayout(h)
        self.lbl_flujo_estado = QtWidgets.QLabel()
        self.lbl_flujo_estado.setProperty("rol", "t2")
        self.lbl_flujo_estado.setWordWrap(True)
        v.addWidget(self.lbl_flujo_estado)
        self._flujo_tramos_construir(v)                 # una ficha por tramo (ventana_flujo_tramos)
        self.box_flujo = caja
        return None, caja

    def _flujo_refrescar(self):
        """Al elegir otra utilidad: la fila solo en gravedad y presión, con su estado."""
        caja = getattr(self, "box_flujo", None)
        if caja is None:
            return
        i = getattr(self, "sel_pipe", -1)
        p = self.pipes[i] if 0 <= i < len(self.pipes) else None
        ver = FL.aplica(p)
        form = self.gprop.layout()
        if isinstance(form, QtWidgets.QFormLayout) and form.indexOf(caja) >= 0:
            form.setRowVisible(caja, ver)
        self._flujo_ojo(self.btn_flujo_ver, self._ver_flujo_plano(), "plano")
        if not ver:
            return
        eligiendo = self.mode == MODO
        tramos = self.mode == MODO_TRAMOS
        for b, on in ((self.btn_flujo_elegir, eligiendo), (self.btn_flujo_tramos, tramos)):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        presion = network_kind(p.get("layer") or "") == "pressure"
        tip = (_tr("Volver a «sin indicar»") if presion
               else _tr("Volver a automático: hacia el extremo más bajo del recorrido"))
        self.btn_flujo_auto.setToolTip(tip)
        self.btn_flujo_auto.setAccessibleName(tip)
        self.btn_flujo_auto.setEnabled(FL.tiene(p))
        self.lbl_flujo_estado.setText(
            _tr("Haz clic en el plano donde llega el fluido (Esc cancela).") if eligiendo else
            _tr("Haz clic en cada tramo (o en su ficha) para cambiar su sentido. Esc o Enter terminan.") if tramos
            else texto_estado(p))
        self._flujo_fichas_refrescar(i, p)

    @staticmethod
    def _flujo_ojo(boton, visible, donde):
        """El ojo de ver/ocultar: icono, globo y nombre accesible según el estado."""
        if boton is None:
            return
        boton.setIcon(icon("mdi:eye-outline" if visible else "mdi:eye-off-outline"))
        if donde == "plano":
            tip = (_tr("Ocultar el sentido del flujo en el plano") if visible
                   else _tr("Ver el sentido del flujo en el plano"))
        else:
            tip = (_tr("Ocultar el sentido del flujo en el perfil") if visible
                   else _tr("Ver el sentido del flujo en el perfil"))
        boton.setToolTip(tip)
        boton.setAccessibleName(tip)

    def poner_flujo(self, indices, sentido):
        """Toda la utilidad hacia su fin (1) / su inicio (-1) o automático (0), en UN paso de deshacer. True si
        cambió algo."""
        meta = ((sentido if sentido in (FL.ADELANTE, FL.ATRAS) else FL.AUTO), None)
        cambios = [j for j in dict.fromkeys(indices) if 0 <= j < len(self.pipes)
                   and FL.aplica(self.pipes[j]) and FL.estado(self.pipes[j]) != meta]
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

    # ------------------------------------------------------------------ elegir el punto en el lienzo

    def flujo_elegir_en_plano(self):
        """Modo «flujo_punto» para la utilidad elegida (otro clic en el botón lo cancela)."""
        if self.mode == MODO:
            self._cancelar_flujo_plano()
            return False
        i = getattr(self, "sel_pipe", -1)
        if not (0 <= i < len(self.pipes)) or not FL.aplica(self.pipes[i]) or len(self.pipes[i].get("pts") or []) < 2:
            self._info(_tr("Elige primero una utilidad de alcantarillado, drenaje, agua o gas."))
            self._flujo_refrescar()
            return False
        self._flujo_pipe = i
        self.set_mode(MODO)
        self._flujo_refrescar()
        self._info(_tr("Haz clic donde llega el fluido: un buzón, un vértice, una punta o un punto de {u} "
                       "(Esc cancela).").format(u=model_ops.nombre_por_defecto(self.pipes[i], i)))
        return True

    def _flujo_iman(self, x, y):
        """(x, y, tipo) donde llegaría el fluido con el cursor en (x, y), o None si queda lejos de la utilidad."""
        i = getattr(self, "_flujo_pipe", -1)
        if not (0 <= i < len(self.pipes)):
            return None
        pts = self.pipes[i].get("pts") or []
        r = IMAN_PX / max(1e-6, self.canvas.transform().m11())
        tol = model_ops._TOL
        buzones = [(s["x"], s["y"]) for s in self.structures or ()
                   if not s.get("hidden") and not s.get("curve") and s.get("x") is not None
                   and any(abs(s["x"] - q[0]) <= tol and abs(s["y"] - q[1]) <= tol for q in pts)]
        return FL.iman(pts, x, y, r, buzones)

    def _quitar_pista_flujo(self):
        sc = self.canvas.scene()
        for it in getattr(self, "_pista_flujo_items", None) or []:
            try:
                sc.removeItem(it)
            except (RuntimeError, ValueError):
                pass
        self._pista_flujo_items = []

    def _pista_flujo(self, x, y):
        """Al mover el ratón en «flujo_punto»: la diana donde caerá el clic y las flechas de cómo quedará."""
        self._quitar_pista_flujo()
        if self.mode == MODO_TRAMOS:
            self._pista_tramos(x, y)                    # personalizado por tramos (ventana_flujo_tramos)
            return
        if self.mode != MODO:
            return
        iman = self._flujo_iman(x, y)
        if iman is None:
            self._info(_tr("Acércate a la utilidad elegida: el punto se pega a sus buzones, vértices y a su línea."))
            return
        i = self._flujo_pipe
        prueba = dict(self.pipes[i])
        FL.poner_hacia(prueba, iman[0], iman[1], self._flujo_tol())
        verde = QtGui.QColor(tokens().success)
        items = self._flechas_flujo_plano(prueba, self._pipe_display_pts(prueba), verde, Z_MARK + 19)
        items += self._diana_plano(iman[0], iman[1], verde, Z_MARK + 20)
        self._pista_flujo_items = items
        self._info(_tr("Clic: el fluido llega a {que} (Esc cancela).").format(que=_tr(QUE[iman[2]])))

    def _flujo_tol(self):
        """Tolerancia (px) para tomar el punto como una punta de la utilidad: medio pie."""
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        return 0.5 / ft if ft else 0.5

    def _clic_flujo_plano(self, x, y):
        iman = self._flujo_iman(x, y)
        if iman is None:
            self._info(_tr("Acércate a la utilidad elegida: el punto se pega a sus buzones, vértices y a su línea."))
            return False
        i = self._flujo_pipe
        prueba = dict(self.pipes[i])
        cambia = FL.poner_hacia(prueba, iman[0], iman[1], self._flujo_tol())
        self._quitar_pista_flujo()
        if cambia:
            self._push()
            FL.poner_hacia(self.pipes[i], iman[0], iman[1], self._flujo_tol())
            self._dirty = True
        self.set_mode("idle")                           # redibuja (con las flechas, si el ojo está abierto)
        self._flujo_refrescar()
        self.animar_flujo(i)
        self._info(_tr("Listo: el fluido llega a {que}. Las flechas muestran cómo corre.").format(
            que=_tr(QUE[iman[2]])))
        return True

    def _cancelar_flujo_plano(self):
        self._quitar_pista_flujo()
        if self.mode == MODO:
            self.set_mode("idle")
        self._flujo_refrescar()
        self._info(_tr("Elegir hacia dónde va el fluido: cancelado."))

    def animar_flujo(self, i, duracion_ms=None):
        """5 s de flechas que corren hacia donde va el fluido en la utilidad i (`ui/comun/flujo_animacion`)."""
        from ui.comun import flujo_animacion as FA
        previa = getattr(self, "_flujo_anim", None)
        if previa is not None and previa.activa():
            previa.detener()
        if not (0 <= i < len(self.pipes)):
            return None
        p = self.pipes[i]
        ramas = FL.ramas(p, self._pipe_display_pts(p))
        if not ramas:
            return None
        anim = FA.AnimacionFlujo(self.canvas, ramas, layer_qcolor(p.get("layer")), Z_MARK + 3,
                                 duracion_ms or FA.DURACION_MS)
        self._flujo_anim = anim
        anim.iniciar()
        return anim

    # ------------------------------------------------------------------ ver / ocultar en el plano

    def _ver_flujo_plano(self):
        """¿El ojo del plano está abierto? Se lee de QSettings UNA vez (el redibujo lo pregunta cada vez)."""
        v = getattr(self, "_flujo_ver_plano", None)
        if v is None:
            v = self._flujo_ver_plano = ajuste(VER_PLANO)
        return v

    def ver_flujo_plano(self, on=None):
        """El ojo: ver u ocultar las flechas del flujo en el plano (todas las utilidades con el sentido indicado)."""
        on = (not self._ver_flujo_plano()) if on is None else bool(on)
        self._flujo_ver_plano = on
        guardar_ajuste(VER_PLANO, on)
        self._redraw()
        self._flujo_refrescar()
        self._info(_tr("Sentido del flujo en el plano: visible.") if on
                   else _tr("Sentido del flujo en el plano: oculto."))
        return on

    def _flujo_en_plano_todas(self):
        """Al final del redibujo: flechas y diana de llegada de cada utilidad con el sentido indicado (ojo abierto)."""
        en_tramos = getattr(self, "_flujo_pipe", -1) if self.mode == MODO_TRAMOS else -1
        if 0 <= en_tramos < len(self.pipes):                # por tramos: la utilidad con una flecha en cada tramo
            self._overlay += self._flujo_tramos_dibujar(en_tramos)
        if not self._ver_flujo_plano():
            return
        apagadas = self._lineas_apagadas() if hasattr(self, "_lineas_apagadas") else set()
        llegadas = set()
        for i, p in enumerate(self.pipes):
            if p.get("world") or not FL.aplica(p) or not FL.tiene(p) or p.get("layer") in apagadas or i == en_tramos:
                continue
            col = layer_qcolor(p.get("layer"))
            dibujo = self._memo(("dibujo", i), lambda p=p: self._pipe_display_pts(p), copiar=False)
            self._overlay += self._flechas_flujo_plano(p, dibujo, col, Z_MARK + 2)
            q = FL.llegada(p)
            if q is not None and (round(q[0], 1), round(q[1], 1)) not in llegadas:
                llegadas.add((round(q[0], 1), round(q[1], 1)))
                self._overlay += self._diana_plano(q[0], q[1], col, Z_MARK + 2)

    def _flechas_flujo_plano(self, p, dibujo, color, z):
        """Ítems de las flechas (círculo del color con la flecha blanca, de tamaño fijo en pantalla)."""
        sc = self.canvas.scene()
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
        minimo = 30.0 / max(1e-6, self.canvas.transform().m11())
        out = []
        for x, y, ang in FL.flechas(p, dibujo, minimo):
            for forma, pluma, relleno in ((circulo, borde, QtGui.QBrush(color)), (punta, sin_borde, blanco)):
                it = sc.addPath(forma, pluma, relleno)
                it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
                it.setPos(x, y)
                it.setRotation(ang)
                it.setZValue(z)
                it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                out.append(it)
        return out

    def _diana_plano(self, x, y, color, z):
        """Diana de LLEGADA (anillo del color con punto al centro, tamaño fijo en pantalla)."""
        sc = self.canvas.scene()
        anillo = QtGui.QPainterPath()
        anillo.addEllipse(QtCore.QPointF(0, 0), 8, 8)
        centro = QtGui.QPainterPath()
        centro.addEllipse(QtCore.QPointF(0, 0), 3, 3)
        pluma = QtGui.QPen(color, 2.5)
        pluma.setCosmetic(True)
        out = []
        for forma, pl, relleno in ((anillo, pluma, QtGui.QBrush(QtGui.QColor(255, 255, 255, 220))),
                                   (centro, QtGui.QPen(QtCore.Qt.NoPen), QtGui.QBrush(color))):
            it = sc.addPath(forma, pl, relleno)
            it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
            it.setPos(x, y)
            it.setZValue(z)
            it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            out.append(it)
        return out
