"""Panel «Reconocer» del riel: una fila por cosa que se puede reconocer de la hoja.

Solo MUESTRA un `nucleo.reconocer_estado.Estado` y emite señales; qué hace cada una lo decide la ventana
(`ui/ventana/ventana_reconocer.py`). Cada fila: color de la utilidad (o un icono), icono de estado, nombre y
una línea corta (cuántas capas/estilos/símbolos, el motivo si no se puede o lo reconocido), ▶, 👁 y ⋯.

El ▶ que no se puede usar NO se deshabilita: se ve apagado y el clic dice por qué (como
`ventana_dibujar._bloqueado`; un botón deshabilitado de Qt no muestra nada). Los colores de estado son
neutros, magenta o turquesa: nunca los de una utilidad (memoria «colores sin choque»).
"""
from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import reconocer_estado as RE
from traduccion.i18n import bind as _bind, t as _tr
from traduccion.i18n_core import N_
from ui.comun import rediseno as R
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon
from ui.comun.responsive import GridAdaptable
from ui.comun.ui_common import QA_OFFPATTERN, QA_UNCOVERED, layer_qcolor

ICONO_ESTADO = {"sin_interpretar": "circle-outline", "pendiente": "circle-outline",
                "bloqueada": "minus-circle-outline", "reconociendo": "progress-clock",
                "reconocida": "check-circle-outline", "desactualizada": "alert-circle-outline",
                "error": "close-octagon-outline"}
_BTN_PX = 28


def color_estado(estado, tema=None) -> str:
    """Color del icono de estado: neutro, turquesa (en curso / hecho) o magenta (cambió / error)."""
    t = tema or _theme.tokens()
    if estado in ("reconociendo", "reconocida"):
        return QA_OFFPATTERN
    if estado in ("desactualizada", "error"):
        return QA_UNCOVERED
    if estado == "pendiente":
        return t.text_muted
    return t.text3


def _cuenta(n, uno_es, varios_es):
    return _tr(uno_es) if n == 1 else _tr(varios_es).format(n=n)


def texto_motivo(clave, datos) -> str:
    """`t(clave).format(**datos)`; una lista de utilidades se muestra con sus nombres traducidos."""
    if not clave:
        return ""
    datos = dict(datos or {})
    for k, v in list(datos.items()):
        if isinstance(v, (list, tuple)):
            datos[k] = ", ".join(_tr(RE.ETIQUETAS.get(x, x)) for x in v)
    return _tr(clave).format(**datos)


def _boton(icono, tip_es):
    b = QtWidgets.QToolButton()
    b.setFixedSize(_BTN_PX, _BTN_PX)
    b.setIconSize(QtCore.QSize(18, 18))
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b._icono = icono
    _bind(b, "setToolTip", tip_es)
    _bind(b, "setAccessibleName", tip_es)
    return b


# La interpretación, punto por punto: las partes que avisa `interpretar_trabajo` y la etapa en que se leen.
PARTES_INTERP = RE.UTILIDADES + ("VALVULAS", "ROTULOS", "ESCALA")
ETAPA_PARTES = {0: RE.UTILIDADES, 1: RE.UTILIDADES, 2: ("VALVULAS",), 3: ("ROTULOS",), 4: ("ESCALA",)}
ICONO_INTERP = {"espera": "circle-outline", "curso": "progress-clock", "hecho": "check-circle-outline",
                "nada": "minus-circle-outline"}


def texto_interpretada(clave, estado, n=None) -> str:
    """Lo que dice cada punto de la lista de la interpretación."""
    if estado == "espera":
        return _tr("En espera")
    if estado == "curso":
        return _tr("Interpretando…")
    if clave == "ESCALA":
        return _tr("Escala 1\"={v}'").format(v="%g" % round(float(n) * 72.0, 2)) if n else _tr("Sin escala")
    if clave == "VALVULAS":
        return _cuenta(n, "1 símbolo", "{n} símbolos") if n else _tr("Sin válvulas")
    if clave == "ROTULOS":
        return _cuenta(n, "1 rótulo", "{n} rótulos") if n else _tr("Sin rótulos")
    if n is None:
        return _tr("Leída · sus estilos los asigna la leyenda")
    return _cuenta(n, "1 capa", "{n} capas") if n else _tr("Sin capas en la hoja")


class FilaInterpretacion(QtWidgets.QWidget):
    """Un punto de la lista: icono de estado, nombre y lo que se leyó."""

    def __init__(self, clave):
        super().__init__()
        self.clave, self.estado, self.n = clave, "espera", None
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)
        self.marca = QtWidgets.QLabel()
        self.marca.setFixedSize(4, 14)
        lay.addWidget(self.marca, 0, QtCore.Qt.AlignTop)
        self.ic = QtWidgets.QLabel()
        self.ic.setFixedSize(16, 16)
        lay.addWidget(self.ic, 0, QtCore.Qt.AlignTop)
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(0)
        self.nombre = QtWidgets.QLabel()
        self.nombre.setWordWrap(True)
        self.detalle = QtWidgets.QLabel()
        self.detalle.setProperty("rol", "t3")
        self.detalle.setWordWrap(True)                 # el panel nunca pide scroll horizontal
        tx.addWidget(self.nombre)
        tx.addWidget(self.detalle)
        lay.addLayout(tx, 1)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.poner("espera")

    def poner(self, estado, n=None):
        if estado == "hecho" and not n and n is not None:
            estado = "nada"                          # se leyó y no hay nada de esto en la hoja
        self.estado, self.n = estado, n
        t = _theme.tokens()
        self.nombre.setText(_tr("Escala del plano") if self.clave == "ESCALA" else _tr(RE.ETIQUETAS[self.clave]))
        self.detalle.setText(texto_interpretada(self.clave, "hecho" if estado == "nada" else estado, n))
        color = {"curso": QA_OFFPATTERN, "hecho": QA_OFFPATTERN}.get(estado, t.text3)
        self.ic.setPixmap(_icon("mdi:" + ICONO_INTERP[estado], color=color).pixmap(16, 16))
        self.nombre.setStyleSheet(f"color:{t.text if estado in ('curso', 'hecho') else t.text_muted};")
        if self.clave in RE.UTILIDADES:
            self.marca.setStyleSheet(f"background:{layer_qcolor(self.clave).name()}; border-radius:2px;"
                                     f" border:1px solid {t.border};")


class FilaParte(QtWidgets.QFrame):
    """Una fila del panel. `panel` recibe los clics (el panel decide si emite o explica)."""

    def __init__(self, panel, parte):
        super().__init__()
        self.panel, self.parte = panel, parte
        self.setObjectName("filaReconocer")
        self.fila = RE.Fila(parte)
        self.ok, self.clave, self.datos = False, "", {}
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(4, 6, 0, 6)
        lay.setSpacing(6)
        self.marca = QtWidgets.QLabel()                 # barrita con el color de la utilidad
        self.marca.setFixedSize(4, 16)
        lay.addWidget(self.marca, 0, QtCore.Qt.AlignTop)
        self.ic_estado = QtWidgets.QLabel()
        self.ic_estado.setFixedSize(16, 16)
        lay.addWidget(self.ic_estado, 0, QtCore.Qt.AlignTop)
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(0)
        self.nombre = QtWidgets.QLabel(_tr(RE.ETIQUETAS[parte]))
        self.nombre.setWordWrap(True)
        self.detalle = QtWidgets.QLabel()
        self.detalle.setProperty("rol", "t3")
        self.detalle.setWordWrap(True)
        tx.addWidget(self.nombre)
        tx.addWidget(self.detalle)
        lay.addLayout(tx, 1)
        self.btn_play = _boton("play", "Reconocer")
        self.btn_ver = _boton("eye-outline", "Vista previa")
        self.btn_mas = _boton("dots-horizontal", "Más opciones")
        self.btn_mas.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.btn_mas.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        bl = QtWidgets.QHBoxLayout()
        bl.setSpacing(0)
        for b in (self.btn_play, self.btn_ver, self.btn_mas):
            bl.addWidget(b)
        lay.addLayout(bl)
        lay.setAlignment(bl, QtCore.Qt.AlignTop)
        self.btn_play.clicked.connect(lambda: panel._clic_play(parte))
        self.btn_ver.clicked.connect(lambda: panel._clic_ver(parte))
        self.menu = self._armar_menu()
        self.btn_mas.setMenu(self.menu)

    def _armar_menu(self):
        m = QtWidgets.QMenu(self)
        p = self.panel
        a = m.addAction("")
        _bind(a, "setText", "Capas y estilos…")
        a.triggered.connect(lambda: p.capas.emit(self.parte))
        if self.parte in RE.UTILIDADES:
            # «Ajustar capas…» ya no va aparte: «Capas y estilos…» es la misma vista, con la hoja a la vista y
            # utilidad + rol de cada capa (2026-11-17)
            self.act_unir = m.addAction("")
            _bind(self.act_unir, "setText", "Unir tramos")
            self.act_unir.setCheckable(True)
            self.act_unir.setChecked(True)
            self.act_unir.triggered.connect(lambda on: p.unir_tramos.emit(self.parte, bool(on)))
        if self.parte == "ROTULOS":
            a = m.addAction("")
            _bind(a, "setText", "Leer rótulos ilegibles con la IA…")    # = IA → la misma acción
            a.triggered.connect(lambda: p.rotulos_ia.emit())
        return m

    def poner(self, fila, unidad_capas):
        self.fila = fila
        self.ok, self.clave, self.datos = RE.puede(self.panel._estado, self.parte)
        if getattr(self, "act_unir", None) is not None:
            self.act_unir.setChecked(bool(fila.unir_tramos))
        self.detalle.setText(self._texto(fila, unidad_capas))
        self.btn_play.setProperty("bloqueado", not self.ok)
        tip = texto_motivo(self.clave, self.datos) if not self.ok else _tr(
            "Reconocer de nuevo" if fila.estado in ("reconocida", "desactualizada") else "Reconocer")
        self.btn_play.setToolTip(tip)
        self.estilo()

    def _texto(self, fila, unidad_capas):
        e = fila.estado
        if e == "sin_interpretar":
            return _tr("Sin interpretar")
        if e == "reconociendo":
            return _tr("Reconociendo…")
        if e in ("reconocida", "desactualizada"):
            base = _tr("Reconocida · {n}").format(n=fila.hechos)
            if e == "desactualizada":
                base = _tr("Cambió · reconocer de nuevo")
            if self.parte == "DIAMETROS":
                base = " · ".join(x for x in (base, self._diametros()) if x)
            if fila.verificar:
                base += " · " + _tr("{n} por verificar").format(n=len(fila.verificar))
            return base
        if e == "error":
            return _tr(fila.motivo) if fila.motivo else _tr("No se pudo reconocer.")
        if not self.ok:
            return texto_motivo(self.clave, self.datos)
        n = fila.fuentes
        if self.parte == "VALVULAS":
            return _cuenta(n, "1 símbolo", "{n} símbolos")
        if self.parte == "ROTULOS":
            return _cuenta(n, "1 rótulo", "{n} rótulos")
        if self.parte == "DIAMETROS":
            faltan = RE.sin_reconocer(self.panel._estado)
            base = (texto_motivo(RE.M_DIAMETROS_FALTAN, {"faltan": faltan}) if faltan
                    else _tr("Con las utilidades reconocidas"))
            return " · ".join(x for x in (base, self._diametros()) if x)
        if unidad_capas == "estilos":
            return _cuenta(n, "1 estilo", "{n} estilos")
        return _cuenta(n, "1 capa", "{n} capas")

    def _diametros(self):
        """«N dudosas · M sin dato»: las tuberías cuyo diámetro el plano no dijo con certeza y siguen con el de por
        defecto (los avisos «Diámetro del plano» del editor)."""
        dudosas, sin_dato = self.panel._diametros or (0, 0)
        partes = []
        if dudosas:
            partes.append(_cuenta(dudosas, "1 dudosa", "{n} dudosas"))
        if sin_dato:
            partes.append(_tr("{n} sin dato").format(n=sin_dato))
        return " · ".join(partes)

    def estilo(self):
        t = _theme.tokens()
        if self.parte in RE.UTILIDADES:             # su color, como en «Capas» (no es color de estado)
            # con borde: el drenaje es blanco y en el tema claro no se vería
            self.marca.setStyleSheet(f"background:{layer_qcolor(self.parte).name()}; border-radius:2px;"
                                     f" border:1px solid {t.border};")
        e = self.fila.estado
        self.ic_estado.setPixmap(_icon("mdi:" + ICONO_ESTADO[e], color=color_estado(e, t)).pixmap(16, 16))
        self.ic_estado.setToolTip(_tr(_NOMBRE_ESTADO[e]))
        self.nombre.setStyleSheet(f"color:{t.text if e != 'bloqueada' else t.text_muted};")
        bloq = not self.ok
        self.btn_play.setIcon(_icon("mdi:play", color=t.text3 if bloq else t.accent))
        self.btn_ver.setIcon(_icon("mdi:eye-outline", color=t.text3 if self._ver_bloqueado() else t.text_muted))
        self.btn_mas.setIcon(_icon("mdi:dots-horizontal", color=t.text_muted))
        borde = f"1px dashed {t.border_soft}" if bloq else "1px solid transparent"
        self.btn_play.setStyleSheet(f"QToolButton {{ border:{borde}; border-radius:8px; background:transparent; }}"
                                    f" QToolButton:hover {{ border:1px solid {t.accent}; }}")
        self.setStyleSheet(f"QFrame#filaReconocer {{ background:transparent; border:none;"
                           f" border-bottom:1px solid {t.border_soft}; }}")

    def _ver_bloqueado(self):
        return not self.ok and self.fila.estado not in ("reconocida", "desactualizada")


_NOMBRE_ESTADO = {"sin_interpretar": N_("Sin interpretar"), "pendiente": N_("Pendiente"),
                  "bloqueada": N_("No se puede"), "reconociendo": N_("Reconociendo…"),
                  "reconocida": N_("Reconocida"), "desactualizada": N_("Desactualizada"), "error": N_("Error")}


class PanelReconocer(QtWidgets.QWidget):
    reproducir = QtCore.Signal(str)          # ▶ de una fila
    ver = QtCore.Signal(str)                 # 👁 de una fila
    capas = QtCore.Signal(object)            # «Capas y estilos…» (parte o None = general)
    ajustar = QtCore.Signal(str)             # «Ajustar capas…» de una utilidad
    unir_tramos = QtCore.Signal(str, bool)   # «Unir tramos» de una utilidad
    rotulos_ia = QtCore.Signal()             # «Leer rótulos ilegibles con la IA…» (fila Rótulos)
    todo = QtCore.Signal()
    cancelar = QtCore.Signal()
    interpretar = QtCore.Signal()
    por_verificar = QtCore.Signal()
    ir_a_verificar = QtCore.Signal(str, int)  # un «Para verificar» guardado: ir a su lugar (parte, posición)
    visto = QtCore.Signal(str, int, bool)     # ✔ revisado de ese punto
    aviso = QtCore.Signal(str)               # por qué un ▶ / 👁 no hace nada
    plano = QtCore.Signal(int)               # otro plano de la hoja (utilidades agregadas: ventana_reconocer_planos)

    def __init__(self, parent=None):
        super().__init__(parent)
        R.transparente(self)
        self._estado = RE.nuevo()
        self._unidad = "capas"
        self._diametros = None                   # (dudosas, sin dato) de las tuberías del editor
        raiz = QtWidgets.QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        cont, cl = R.columna((12, 6, 12, 12), 8)
        # el plano cuyas filas se ven (solo con utilidades agregadas desde otros PDF)
        self.caja_plano = R.transparente(QtWidgets.QWidget())
        pl = QtWidgets.QVBoxLayout(self.caja_plano)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)
        pl.addWidget(R.texto("Plano", "t3", False))
        self.cmb_plano = QtWidgets.QComboBox()
        self.cmb_plano.setMinimumHeight(32)
        self.cmb_plano.setToolTip(_tr("Cada plano de la hoja (cada PDF agregado) se reconoce en su propia hoja."))
        self.cmb_plano.activated.connect(self._al_elegir_plano)
        pl.addWidget(self.cmb_plano)
        self.caja_plano.hide()
        cl.addWidget(self.caja_plano)
        # cabecera: texto arriba, botones debajo (memoria «tarjetas»)
        self.lbl_resumen = R.texto("", "t2", True, traducir=False)
        cl.addWidget(self.lbl_resumen)
        botones = R.transparente(QtWidgets.QWidget())
        bl = GridAdaptable(botones, max_cols=3)       # una fila si caben; si no, uno debajo del otro
        self.btn_todo = QtWidgets.QPushButton()
        _bind(self.btn_todo, "setText", "Reconocer todo")
        self.btn_todo.setProperty("kind", "primary")
        self.btn_todo.clicked.connect(self.todo.emit)
        self.btn_cancelar = QtWidgets.QPushButton()
        _bind(self.btn_cancelar, "setText", "Cancelar")
        self.btn_cancelar.setProperty("soft", True)
        self.btn_cancelar.clicked.connect(self.cancelar.emit)
        self.btn_capas = QtWidgets.QPushButton()
        _bind(self.btn_capas, "setText", "Capas y estilos…")
        self.btn_capas.setProperty("options", True)
        self.btn_capas.clicked.connect(lambda: self.capas.emit(None))
        for b in (self.btn_todo, self.btn_cancelar, self.btn_capas):
            b.setMinimumHeight(34)
            bl.addWidget(b)
        cl.addWidget(botones)
        # sin interpretar / escaneo
        self.lbl_vacio = R.texto("", "t2", True, traducir=False)
        cl.addWidget(self.lbl_vacio)
        # mientras interpreta: la etapa, la barra y su porcentaje (lo mismo que la tarjeta de abajo a la derecha)
        self.caja_interp = R.transparente(QtWidgets.QWidget())
        il = QtWidgets.QVBoxLayout(self.caja_interp)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(6)
        self.lbl_interp = R.texto("", "t3", True, traducir=False)
        il.addWidget(self.lbl_interp)
        fila_b = QtWidgets.QHBoxLayout()
        fila_b.setSpacing(8)
        self.bar_interp = QtWidgets.QProgressBar()
        self.bar_interp.setRange(0, 1000)
        self.bar_interp.setTextVisible(False)
        self.bar_interp.setFixedHeight(8)
        fila_b.addWidget(self.bar_interp, 1)
        self.lbl_interp_pct = R.texto("0 %", "t3", False, traducir=False)
        fila_b.addWidget(self.lbl_interp_pct)
        il.addLayout(fila_b)
        # punto por punto: qué ya se interpretó (pedido 2026-11-17)
        self.lista_interp = {}
        for clave in PARTES_INTERP:
            f = FilaInterpretacion(clave)
            il.addWidget(f)
            self.lista_interp[clave] = f
        self.caja_interp.hide()
        cl.addWidget(self.caja_interp)
        self.btn_interpretar = QtWidgets.QPushButton()
        _bind(self.btn_interpretar, "setText", "Interpretar la hoja")
        self.btn_interpretar.setProperty("kind", "primary")
        self.btn_interpretar.setMinimumHeight(34)
        self.btn_interpretar.clicked.connect(self.interpretar.emit)
        cl.addWidget(self.btn_interpretar)
        # filas
        self.lista = R.transparente(QtWidgets.QWidget())
        ll = QtWidgets.QVBoxLayout(self.lista)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        self.filas = {}
        ll.addWidget(R.seccion("Utilidades"))
        for p in RE.UTILIDADES:
            self.filas[p] = FilaParte(self, p)
            ll.addWidget(self.filas[p])
        ll.addWidget(R.seccion("Más"))
        for p in RE.PARTES[len(RE.UTILIDADES):]:
            self.filas[p] = FilaParte(self, p)
            ll.addWidget(self.filas[p])
        cl.addWidget(self.lista)
        # pie: lo último reconocido y lo que queda por verificar
        self.lbl_ultimo = R.texto("", "t3", True, traducir=False)
        cl.addWidget(self.lbl_ultimo)
        self.btn_verificar = QtWidgets.QPushButton()
        self.btn_verificar.setProperty("kind", "ghost")
        self.btn_verificar.setIcon(_icon("mdi:eye-outline"))
        self.btn_verificar.clicked.connect(self.por_verificar.emit)
        cl.addWidget(self.btn_verificar)
        self.caja_verificar = R.transparente(QtWidgets.QWidget())      # la lista de «Para verificar» guardados
        self._vl = QtWidgets.QVBoxLayout(self.caja_verificar)
        self._vl.setContentsMargins(0, 0, 0, 0)
        self._vl.setSpacing(2)
        self.caja_verificar.hide()
        self._filtro_verificar = None
        cl.addWidget(self.caja_verificar)
        cl.addStretch(1)
        raiz.addWidget(R.AreaVertical(cont))
        self._ultimo, self._escaneo = None, False
        _theme.al_tema(self, lambda _n: self._estilo())
        from traduccion.i18n import LANG_BUS
        LANG_BUS.changed.connect(self._al_idioma)
        self.mostrar(self._estado)

    def reiniciar_interpretacion(self):
        """Una interpretación que empieza: todo «en espera»."""
        for f in self.lista_interp.values():
            f.poner("espera")
        self.avance_interpretacion(None, None)

    def etapa_interpretacion(self, k):
        """Empieza la etapa `k` de `interpretar_trabajo.ETAPAS`: sus partes pasan a «en curso»."""
        for clave in ETAPA_PARTES.get(int(k), ()):
            f = self.lista_interp.get(clave)
            if f is not None and f.estado == "espera":
                f.poner("curso")

    def parte_interpretada(self, clave, n):
        f = self.lista_interp.get(clave)
        if f is not None:
            f.poner("hecho", n)

    def avance_interpretacion(self, detalle, frac, medida="cuenta"):
        """La etapa y el porcentaje de la interpretación en curso (`frac` None = terminó). `medida` fuera de
        «cuenta» = la cifra es una estimación: «≈ 42 %» (`avance_aprendido.Seguidor.medida`)."""
        if frac is None:
            self.bar_interp.setValue(0)
            self.lbl_interp_pct.setText("0 %")
            self.lbl_interp.setText("")
            return
        frac = max(0.0, min(1.0, float(frac)))
        self.bar_interp.setValue(int(1000 * frac))
        from ui.comun.busy import cifra
        self.lbl_interp_pct.setText(cifra(frac, medida))
        self.lbl_interp.setText(detalle or "")

    # ── datos ─────────────────────────────────────────────────────────────
    def _al_elegir_plano(self, i):
        g = self.cmb_plano.itemData(i)
        if g is not None:
            self.plano.emit(int(g))

    def _poner_planos(self, planos, activo):
        planos = list(planos or ())
        self.caja_plano.setVisible(len(planos) > 1)
        self.cmb_plano.blockSignals(True)
        self.cmb_plano.clear()
        for g, nombre in planos:
            self.cmb_plano.addItem(nombre, int(g))
        i = self.cmb_plano.findData(int(activo or 0))
        self.cmb_plano.setCurrentIndex(max(0, i))
        self.cmb_plano.blockSignals(False)

    def mostrar(self, estado, ultimo=None, escaneo=False, unidad_capas="capas", interpretando=False,
                diametros=None, planos=(), plano=0):
        """`ultimo` = (parte, cuántos) de lo último reconocido; `unidad_capas` = «capas» o «estilos»
        (hoja sin capas: cada utilidad cuenta los estilos de trazo asignados); `interpretando` = la hoja se está
        interpretando en segundo plano (el panel se llena solo al terminar); `diametros` = (dudosas, sin dato) de
        las tuberías del editor (fila «Diámetros»)."""
        self._estado = estado or RE.nuevo()
        self._poner_planos(planos, plano)
        self._diametros = diametros
        self._ultimo, self._escaneo, self._unidad = ultimo, escaneo, unidad_capas
        self._interpretando = bool(interpretando)
        filas = self._estado.filas
        for p, w in self.filas.items():
            w.poner(filas.get(p) or RE.Fila(p), unidad_capas)
        sin_interp = all(f.estado == "sin_interpretar" for f in filas.values())
        vacio = escaneo or sin_interp
        self.lista.setVisible(not vacio)
        self.lbl_vacio.setVisible(vacio)
        self.lbl_vacio.setText(_tr("Hoja escaneada: no hay nada que reconocer.") if escaneo
                               else _tr("Interpretando la hoja…") if interpretando
                               else _tr("La hoja aún no está interpretada."))
        # también en un proyecto viejo: lo importado queda «reconocida» y el resto «sin interpretar» (Tarea 10)
        algo_sin_interp = any(f.estado == "sin_interpretar" for f in filas.values())
        self.btn_interpretar.setVisible(algo_sin_interp and not escaneo and not interpretando)
        self.caja_interp.setVisible(self._interpretando and vacio and not escaneo)
        corriendo = any(f.estado == "reconociendo" for f in filas.values())
        self.btn_cancelar.setVisible(corriendo)
        self.btn_todo.setVisible(not vacio and not corriendo)
        self.btn_capas.setVisible(not vacio)
        hechas = sum(1 for f in filas.values() if f.estado in ("reconocida", "desactualizada"))
        posibles = sum(1 for f in filas.values() if f.estado != "bloqueada")
        self.lbl_resumen.setVisible(not vacio)
        self.lbl_resumen.setText(_tr("{k} de {n} reconocidas").format(k=hechas, n=posibles))
        self.lbl_ultimo.setVisible(bool(ultimo) and not vacio)
        if ultimo:
            parte, n = ultimo
            self.lbl_ultimo.setText(_tr("Último: {p} · {n}").format(p=_tr(RE.ETIQUETAS.get(parte, parte)), n=n))
        k = sum(len(f.verificar) for f in filas.values())
        self.btn_verificar.setVisible(bool(k) and not vacio)
        self.btn_verificar.setText(_tr("{n} por verificar").format(n=k))
        if not k:
            self.caja_verificar.hide()
        if self.caja_verificar.isVisibleTo(self):
            self._llenar_verificar()
        self._estilo()

    # ── «Para verificar» guardados ─────────────────────────────────────────
    def abrir_verificar(self, parte=None, alternar=False):
        """Muestra (o con `alternar` oculta) la lista de los «Para verificar» guardados de todas las filas, o solo
        de `parte`. Cada punto: clic = ir a su lugar del plano; casilla = revisado."""
        if alternar and self.caja_verificar.isVisibleTo(self) and self._filtro_verificar == parte:
            self.caja_verificar.hide()
            return
        self._filtro_verificar = parte
        self._llenar_verificar()
        self.caja_verificar.setVisible(self.caja_verificar.layout().count() > 0)

    def _llenar_verificar(self):
        while self._vl.count():
            w = self._vl.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for p, f in self._estado.filas.items():
            if self._filtro_verificar and p != self._filtro_verificar or not f.verificar:
                continue
            self._vl.addWidget(R.seccion(RE.ETIQUETAS[p]))
            for i, v in enumerate(f.verificar):
                self._vl.addWidget(self._punto_verificar(p, i, v))

    def _punto_verificar(self, parte, i, v):
        w = R.transparente(QtWidgets.QWidget())
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        chk = QtWidgets.QCheckBox()
        chk.setChecked(bool(v.get("visto")))
        chk.setToolTip(_tr("Revisado"))
        chk.toggled.connect(lambda on, p=parte, k=i: self.visto.emit(p, k, bool(on)))
        h.addWidget(chk)
        b = QtWidgets.QToolButton()
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        b.setProperty("kind", "ghost")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        texto = str(v.get("texto") or v.get("etiqueta") or "")
        b.setText(texto if len(texto) <= 60 else texto[:57] + "…")
        b.setToolTip(texto)
        b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        b.clicked.connect(lambda _=False, p=parte, k=i: self.ir_a_verificar.emit(p, k))
        h.addWidget(b, 1)
        w.casilla = chk
        return w

    def motivo(self, parte) -> str:
        w = self.filas[parte]
        return texto_motivo(w.clave, w.datos)

    # ── clics ─────────────────────────────────────────────────────────────
    def _clic_play(self, parte):
        w = self.filas[parte]
        if not w.ok:
            self._explicar(w)
            return
        self.reproducir.emit(parte)

    def _clic_ver(self, parte):
        w = self.filas[parte]
        if w._ver_bloqueado():
            self._explicar(w)
            return
        self.ver.emit(parte)

    def _explicar(self, w):
        motivo = texto_motivo(w.clave, w.datos)
        if motivo:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), motivo, w.btn_play)
            self.aviso.emit(motivo)

    # ── aspecto ───────────────────────────────────────────────────────────
    def _estilo(self):
        for w in self.filas.values():
            w.estilo()

    def _al_idioma(self, *_a):
        import shiboken6
        if not shiboken6.isValid(self):
            return
        for p, w in self.filas.items():
            w.nombre.setText(_tr(RE.ETIQUETAS[p]))
        self.mostrar(self._estado, self._ultimo, self._escaneo, self._unidad, getattr(self, "_interpretando", False),
                     self._diametros)
