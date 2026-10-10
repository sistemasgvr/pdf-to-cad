"""Ventana «Vista 3D» (Ver → Vista 3D, F3): lo que Civil 3D va a construir, sin exportar.

No modal: se deja abierta al lado del plano y se actualiza sola al editar (con una
pausa corta y el cálculo en otro hilo: `modelo3d.construir`). Elegir en el plano
resalta en 3D (y encuadra si «Seguir la selección» está activo); clic en 3D elige en
el plano. Un solo panel de opciones (utilidades = leyenda, qué mostrar, suelo)
y una línea de estado (lo que hay bajo el cursor o el resumen).
Las opciones se recuerdan (QSettings «pdf-to-cad»/«vista3d»); la cámara NO: cada vez
que se abre arranca en isométrica con todo encuadrado.
"""
from __future__ import annotations

import copy
import json

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import accesorios as acc
from nucleo import ficha3d, model_ops, modelo3d, normas_validar
from traduccion.i18n import t as _tr
from ui.comun import theme
from ui.comun.icons import icon as _icon
from ui.comun.ui_common import layer_qcolor, swatch_icon
from ui.comun.visor3d import Visor3D
from ui.dialogos.vista3d_ficha import FichaPanel

_SIN_SUELO = -100000.0
OPACIDAD_SUELO = 18                          # % por defecto
_PIES = " ft"                                 # unidad (igual en ambos idiomas)
_CONTROLES = ("Rueda: zoom · Botón central: desplazar · Shift + botón central o arrastrar: girar · "
              "Clic: elegir · Doble clic: encuadrar")


class _CotaSuelo(QtWidgets.QDoubleSpinBox):
    """Cota del suelo con «Automática» (el mínimo). Las flechas desde «Automática» arrancan
    en la cota automática actual (`auto`), no en el mínimo (−100 000 ft)."""
    auto = 0.0

    def stepBy(self, pasos):
        if self.value() <= _SIN_SUELO:
            self.setValue(round(self.auto, 2))
            return
        super().stepBy(pasos)


def _ajustes():
    return QtCore.QSettings("pdf-to-cad", "vista3d")


class _Senales(QtCore.QObject):
    listo = QtCore.Signal(object, str)


class _Trabajo(QtCore.QRunnable):
    """Arma la escena en otro hilo (solo datos puros: copias del proyecto)."""

    def __init__(self, datos, firma):
        super().__init__()
        self.setAutoDelete(False)
        self.senales = _Senales()
        self.datos, self.firma = datos, firma

    def run(self):
        try:
            escena = modelo3d.construir(**self.datos)
        except Exception:                                   # nunca tumbar la app por la vista previa
            escena = modelo3d.Escena()
        self.senales.listo.emit(escena, self.firma)


class Vista3DDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_tr("Vista 3D"))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMinMaxButtonsHint)
        self.resize(1100, 720)
        self._firma = None
        self._trabajo = None
        self._pendiente = False
        self._primera = True
        self._capas = {}
        self.escena = modelo3d.Escena()
        self._sel_local = 0          # accesorio elegido en 3D (no existe en el plano)
        self._ficha_id = None
        self._t = QtCore.QTimer(self, singleShot=True, interval=350, timeout=self.actualizar)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self._barra())
        split = QtWidgets.QSplitter()
        self.visor = Visor3D()
        self.pila = QtWidgets.QStackedWidget()
        self.pila.addWidget(self.visor)
        self.lbl_vacio = QtWidgets.QLabel(_tr("Dibuja o importa utilidades para verlas en 3D."))
        self.lbl_vacio.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_vacio.setWordWrap(True)
        self.pila.addWidget(self.lbl_vacio)
        split.addWidget(self.pila)
        split.addWidget(self._panel())
        split.setStretchFactor(0, 1)
        split.setSizes([800, 280])
        lay.addWidget(split, 1)
        self.lbl_estado = QtWidgets.QLabel()
        self.lbl_estado.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_estado)
        self.visor.setToolTip(_tr(_CONTROLES))

        self.visor.elegido.connect(self._elegido)
        self.visor.doble.connect(self._doble)
        self.visor.sobre.connect(self._sobre)
        theme.THEME_BUS.changed.connect(self._tema)
        self._tema()
        self._leer_ajustes()

    # ── interfaz ──
    def _barra(self):
        tb = QtWidgets.QToolBar()
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        a = tb.addAction(_icon("mdi:fit-to-screen-outline"), _tr("Encuadrar todo"), lambda: self.visor.encuadrar())
        a.setShortcut(QtGui.QKeySequence("Home")); a.setToolTip(_tr("Ver todo el modelo (Inicio)"))
        tb.addSeparator()
        for clave, texto in (("arriba", "Arriba"), ("frente", "Frente"), ("lateral", "Lateral"),
                             ("iso", "Isométrica")):
            tb.addAction(_tr(texto), lambda c=clave: self.visor.vista(c))
        tb.addSeparator()
        self.act_seguir = tb.addAction(_tr("Seguir la selección"))
        self.act_seguir.setCheckable(True); self.act_seguir.setChecked(True)
        self.act_seguir.setToolTip(_tr("Al elegir una utilidad o un buzón en el plano, la vista 3D lo encuadra"))
        return tb

    def _panel(self):
        caja = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(caja)
        self.ficha = FichaPanel()
        self.ficha.ir_al_plano.connect(self._ficha_al_plano)
        v.addWidget(self.ficha)
        self.g_capas = QtWidgets.QGroupBox(_tr("Utilidades"))
        self.lay_capas = QtWidgets.QVBoxLayout(self.g_capas)
        v.addWidget(self.g_capas)
        g = QtWidgets.QGroupBox(_tr("Mostrar"))
        f = QtWidgets.QVBoxLayout(g)
        self.chk = {}
        for clave, texto in (("estructuras", "Buzones, cajas y sólidos"), ("accesorios", "Accesorios (codos, Tee, Wye…)"),
                             ("avisos", "Avisos de normativa y choques")):
            c = QtWidgets.QCheckBox(_tr(texto)); c.setChecked(True)
            c.toggled.connect(lambda _on: self.actualizar(forzar=True))
            f.addWidget(c); self.chk[clave] = c
        v.addWidget(g)
        g = QtWidgets.QGroupBox(_tr("Suelo"))
        f = QtWidgets.QFormLayout(g)
        self.chk_suelo = QtWidgets.QCheckBox(_tr("Mostrar el suelo")); self.chk_suelo.setChecked(True)
        self.chk_suelo.toggled.connect(self._suelo)
        f.addRow(self.chk_suelo)
        self.sld_suelo = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.sld_suelo.setRange(5, 90)
        self.sld_suelo.setValue(OPACIDAD_SUELO); self.sld_suelo.valueChanged.connect(self._suelo)
        f.addRow(_tr("Opacidad"), self.sld_suelo)
        self.spn_suelo = _CotaSuelo()
        self.spn_suelo.setRange(_SIN_SUELO, 100000.0); self.spn_suelo.setDecimals(2); self.spn_suelo.setSuffix(_PIES)
        self.spn_suelo.setSpecialValueText(_tr("Automática")); self.spn_suelo.setValue(_SIN_SUELO)
        self.spn_suelo.setToolTip(_tr("Automática: la tapa más alta de los buzones o, sin buzones, 3 ft sobre la "
                                      "tubería más alta"))
        self.spn_suelo.editingFinished.connect(lambda: self.actualizar(forzar=True))
        f.addRow(_tr("Cota"), self.spn_suelo)
        b = QtWidgets.QPushButton(_icon("mdi:restore"), _tr("Restablecer"))
        b.setToolTip(_tr("Volver a los valores por defecto del suelo: visible, opacidad 18 % y cota automática"))
        b.setProperty("secondary", True); b.setAutoDefault(False)
        b.clicked.connect(self.restablecer_suelo)
        f.addRow(b)
        v.addWidget(g)
        ayuda = QtWidgets.QLabel(_tr(_CONTROLES))
        ayuda.setWordWrap(True); ayuda.setObjectName("hint")
        v.addWidget(ayuda)
        v.addStretch(1)
        sc = QtWidgets.QScrollArea(); sc.setWidget(caja); sc.setWidgetResizable(True)
        sc.setMinimumWidth(240)
        return sc

    def _tema(self, *_a):
        tk = theme.tokens()
        self.visor.fondo = QtGui.QColor(tk.surface_alt if theme.is_dark() else "#dfe3ea")
        self.visor.resalte = QtGui.QColor("#ff4fd8")         # magenta: no es color de ninguna utilidad
        self.visor.oscuro = theme.is_dark()
        self.visor.update()

    # ── opciones ──
    def _suelo(self, *_a):
        self.visor.ver_suelo = self.chk_suelo.isChecked()
        self.visor.opacidad_suelo = self.sld_suelo.value() / 100.0
        self.sld_suelo.setEnabled(self.chk_suelo.isChecked())
        self.visor.update()

    def restablecer_suelo(self):
        """Suelo visible, opacidad por defecto y cota automática."""
        self.chk_suelo.setChecked(True)
        self.sld_suelo.setValue(OPACIDAD_SUELO)
        if self.spn_suelo.value() > _SIN_SUELO:
            self.spn_suelo.setValue(_SIN_SUELO)
            self.actualizar(forzar=True)
        self._suelo()

    def _capas_visibles(self, capas):
        """Una casilla por utilidad del proyecto (con su color: es la leyenda)."""
        if set(capas) == set(self._capas):
            return
        ocultas = {c for c, chk in self._capas.items() if not chk.isChecked()}
        for chk in self._capas.values():
            chk.deleteLater()
        self._capas = {}
        for capa in sorted(capas):
            chk = QtWidgets.QCheckBox(f"{self.win._tipo(capa)} ({capas[capa]})")
            chk.setIcon(swatch_icon(layer_qcolor(capa)))
            chk.setChecked(capa not in ocultas)
            chk.toggled.connect(lambda _on: self.actualizar(forzar=True))
            self.lay_capas.addWidget(chk)
            self._capas[capa] = chk

    def _leer_ajustes(self):
        s = _ajustes()
        try:
            self.sld_suelo.setValue(int(s.value("opacidad_suelo", OPACIDAD_SUELO)))
            self.chk_suelo.setChecked(str(s.value("ver_suelo", "true")) == "true")
            self.act_seguir.setChecked(str(s.value("seguir", "true")) == "true")
            geo = s.value("geometria")
            if geo is not None:
                self.restoreGeometry(geo)
        except (TypeError, ValueError):
            pass

    def _guardar_ajustes(self):
        s = _ajustes()
        s.setValue("opacidad_suelo", self.sld_suelo.value())
        s.setValue("ver_suelo", "true" if self.chk_suelo.isChecked() else "false")
        s.setValue("seguir", "true" if self.act_seguir.isChecked() else "false")
        s.setValue("geometria", self.saveGeometry())

    def closeEvent(self, e):
        self._guardar_ajustes()
        super().closeEvent(e)

    # ── modelo ──
    def _datos(self):
        w = self.win
        ft = w.scale / w.zoom if w.scale and w.zoom else 0.0
        colores = {}
        for p in w.pipes:
            c = layer_qcolor(p.get("layer"))
            colores[p.get("layer")] = (c.redF(), c.greenF(), c.blueF())
        dbs = [dict(name=d.name, width_in=d.width_in, height_in=d.height_in,
                    conduits=[c.to_dict() for c in d.conduits], pipes=list(d.assigned()))
               for d in getattr(w, "duct_banks", []) or []]
        avisos = [dict(x=a.x, y=a.y, clase=a.clase, mensaje=a.mensaje, pipe=a.pipe, info=a.info)
                  for a in getattr(w, "_normas_avisos", []) or []]
        choques = [dict(x=e["x"], y=e["y"]) for e in getattr(w, "_choque_hits", []) or []]
        suelo = None if self.spn_suelo.value() <= _SIN_SUELO else self.spn_suelo.value()
        return dict(pipes=copy.deepcopy(w.pipes), structures=copy.deepcopy(w.structures), ft=ft,
                    colores=colores, duct_banks=dbs, cruces=copy.deepcopy(getattr(w, "cross_connections", [])),
                    avisos=avisos, choques=choques,
                    ocultas=[c for c, chk in self._capas.items() if not chk.isChecked()],
                    ver={k: c.isChecked() for k, c in self.chk.items()}, suelo_z=suelo)

    def programar(self):
        """El plano cambió: actualizar en un momento (agrupa cambios seguidos)."""
        if self.isVisible():
            self._t.start()

    def actualizar(self, forzar=False):
        datos = self._datos()
        capas = {}
        for p in datos["pipes"]:
            capas[p.get("layer")] = capas.get(p.get("layer"), 0) + 1
        self._capas_visibles(capas)
        datos["ocultas"] = [c for c, chk in self._capas.items() if not chk.isChecked()]
        firma = json.dumps(datos, sort_keys=True, default=str)
        if firma == self._firma and not forzar:
            return
        if self._trabajo is not None:
            self._pendiente = True
            return
        self.lbl_estado.setText(_tr("Actualizando la vista 3D…"))
        self._trabajo = _Trabajo(datos, firma)
        self._trabajo.senales.listo.connect(self._listo, QtCore.Qt.QueuedConnection)
        QtCore.QThreadPool.globalInstance().start(self._trabajo)

    def _listo(self, escena, firma):
        self._trabajo = None
        self._firma = firma
        self.escena = escena
        self.spn_suelo.auto = float(escena.suelo_z or 0.0)
        self.pila.setCurrentIndex(1 if escena.vacia else 0)
        self.visor.set_escena(escena, encuadrar=self._primera and not escena.vacia)
        if not escena.vacia:
            self._primera = False
        self._ficha_id = None                                 # los datos pudieron cambiar
        self.seleccion_del_plano(encuadrar=False)
        self._resumen()
        if self.visor.error:
            self.lbl_vacio.setText(_tr("No se pudo iniciar la vista 3D (OpenGL 2.1): {e}").format(e=self.visor.error))
            self.pila.setCurrentIndex(1)
        if self._pendiente:
            self._pendiente = False
            self.actualizar()

    def _resumen(self):
        c = self.escena.cuentas or {}
        if self.escena.vacia:
            self.lbl_estado.setText("")
            return
        self.lbl_estado.setText(_tr("{u} utilidades · {e} buzones/cajas · {a} accesorios · suelo a {z} ft").format(
            u=c.get("utilidades", 0), e=c.get("estructuras", 0), a=c.get("accesorios", 0),
            z=f"{self.escena.suelo_z:.2f}"))

    # ── selección ──
    def _id_del_plano(self):
        w = self.win
        if getattr(w, "sel_pipe", -1) is not None and w.sel_pipe >= 0:
            return w.sel_pipe + 1
        if getattr(w, "sel_bz", -1) is not None and w.sel_bz >= 0:
            return modelo3d.ID_ESTRUCTURA + w.sel_bz + 1
        return 0

    def seleccion_del_plano(self, encuadrar=None):
        ident = self._id_del_plano()
        if ident:
            self._sel_local = 0                       # lo del plano manda sobre el accesorio elegido
        else:
            ident = self._sel_local
        cambio = ident != self.visor.sel_id
        self.visor.set_seleccion(ident)
        self._mostrar_ficha(ident)
        if encuadrar is None:
            encuadrar = cambio and self.act_seguir.isChecked() and not self._sel_local
        if encuadrar and ident in self.escena.objetos:
            self.visor.encuadrar(self._caja(ident))

    # ── ficha de atributos ──
    def _avisos_dicts(self):
        return [dict(x=a.x, y=a.y, clase=a.clase, mensaje=a.mensaje, pipe=a.pipe, info=a.info)
                for a in getattr(self.win, "_normas_avisos", []) or []]

    def _mostrar_ficha(self, ident):
        if ident == self._ficha_id:
            return
        self._ficha_id = ident
        tipo, k = modelo3d.objeto_de(ident)
        o = self.escena.objetos.get(ident)
        w = self.win
        titulo, filas = "", []
        try:
            if tipo == "pipe":
                titulo, filas = ficha3d.de_utilidad(w._tablas_de_datos(), w.pipes, self._avisos_dicts(), k)
            elif tipo == "struct":
                titulo, filas = ficha3d.de_estructura(w._tablas_de_datos(), k, (o or {}).get("z0"),
                                                      (o or {}).get("z1"))
            elif tipo == "accesorio" and o:
                ft = w.scale / w.zoom if w.scale and w.zoom else 1.0
                titulo, filas = ficha3d.de_accesorio(o, w.pipes, self._avisos_dicts(), w._tipo, tol_px=1.0 / ft)
        except Exception:                                    # la ficha nunca tumba la vista
            titulo, filas = "", []
        if filas:
            self.ficha.mostrar(titulo, filas)
        else:
            self.ficha.limpiar()

    def _ficha_al_plano(self):
        tipo, k = modelo3d.objeto_de(self.visor.sel_id)
        o = self.escena.objetos.get(self.visor.sel_id) or {}
        if tipo in ("pipe", "struct"):
            self._elegido(self.visor.sel_id)
        elif tipo == "accesorio" and o.get("x") is not None:
            self.win._ir_a_elemento(o["x"], o["y"])

    def deseleccionar(self):
        """Quita la selección (Esc): en 3D, en la ficha y en el plano."""
        hubo = bool(self.visor.sel_id or self._sel_local)
        self._sel_local = 0
        self.visor.set_seleccion(0)
        self._mostrar_ficha(0)
        if self._id_del_plano():
            self.win._deselect_all()
        return hubo

    def keyPressEvent(self, e):
        # Esc NO cierra la ventana (pedido del usuario): quita la selección, si hay; si no, nada.
        if e.key() == QtCore.Qt.Key_Escape:
            self.deseleccionar()
            e.accept()
            return
        super().keyPressEvent(e)

    def _caja(self, ident, minimo=15.0):
        lo, hi = self.escena.objetos[ident]["caja"]
        c = (lo + hi) / 2.0
        r = max(float(max(hi - lo)) / 2.0, minimo)
        return c - r, c + r

    def ver(self, ident):
        """Encuadra y resalta un objeto («Ver en 3D»)."""
        self.visor.set_seleccion(ident)
        if ident in self.escena.objetos:
            self.visor.encuadrar(self._caja(ident))

    def _elegido(self, ident):
        tipo, k = modelo3d.objeto_de(ident)
        w = self.win
        if not ident:                                         # clic en el vacío: quita la selección
            self.deseleccionar()
            return
        if tipo == "accesorio":                               # solo existe en 3D: ficha y resaltado
            if self._id_del_plano():
                w._deselect_all()
            self._sel_local = ident
            self.visor.set_seleccion(ident)
            self._mostrar_ficha(ident)
            return
        self.visor.set_seleccion(ident if tipo in ("pipe", "struct") else self.visor.sel_id)
        if tipo == "pipe" and 0 <= k < len(w.pipes):
            pts = w.pipes[k]["pts"]
            w._ir_a_elemento(pts[len(pts) // 2][0], pts[len(pts) // 2][1], "pipe", k)
        elif tipo == "struct" and 0 <= k < len(w.structures):
            s = w.structures[k]
            w._ir_a_elemento(s["x"], s["y"], "struct", k)
        elif tipo == "aviso" and 0 <= k < len(getattr(w, "_normas_avisos", [])):
            w._normas_ir_a(k)

    def _doble(self, ident):
        if ident in self.escena.objetos:
            self.visor.encuadrar(self._caja(ident))
        else:
            self.visor.encuadrar()

    def _sobre(self, ident):
        texto = self.texto_de(ident)
        if texto:
            self.lbl_estado.setText(texto)
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), texto, self.visor)
        else:
            QtWidgets.QToolTip.hideText()
            self._resumen()

    def texto_de(self, ident):
        """Texto corto del objeto bajo el cursor."""
        o = self.escena.objetos.get(ident)
        if not o:
            return ""
        w = self.win
        if o["tipo"] == "pipe" and 0 <= o["indice"] < len(w.pipes):
            p = w.pipes[o["indice"]]
            d, defecto = model_ops.diametro(p)
            partes = [f"#{o['indice'] + 1} {w._etq(p)}", f'Ø{d:g}"' + (" " + _tr("(por defecto)") if defecto else ""),
                      _tr("solera {a} → {b} ft").format(a=f"{o['z0']:.2f}", b=f"{o['z1']:.2f}")]
            if p.get("tipo"):
                partes.append(p["tipo"])
            if o.get("bancoducto") is not None:
                partes.append(_tr("Bancoducto «{n}»").format(n=o["bancoducto"]))
            if o.get("ab"):
                partes.append(_tr("Abandonada"))
            return " · ".join(partes)
        if o["tipo"] == "struct":
            return _tr("{cod} · fondo {a} ft · tapa {b} ft").format(cod=o.get("cod") or "?", a=f"{o['z0']:.2f}",
                                                                     b=f"{o['z1']:.2f}")
        if o["tipo"] == "accesorio":
            nombre = _tr(normas_validar.NOMBRE_ACC.get(o.get("acc_tipo"), "Accesorio"))
            ang = o.get("angulo")
            return f"{nombre} {acc.texto_angulo(ang)}" if ang is not None else nombre
        if o["tipo"] == "aviso":
            return o.get("mensaje") or _tr("Tuberías que chocan")
        return ""


def abrir(win, ver=None):
    """Abre (o trae al frente) la vista 3D. `ver` = id de objeto a encuadrar."""
    dlg = getattr(win, "_vista3d_dlg", None)
    if dlg is None:
        dlg = Vista3DDialog(win)
        win._vista3d_dlg = dlg
    elif not dlg.isVisible():
        # Cada vez que se abre arranca de cero: isométrica y todo encuadrado (no la
        # cámara de la vez anterior).
        dlg._primera = True
        dlg.visor.reiniciar()
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    dlg.actualizar()
    if ver:
        dlg._ver_pendiente = ver
        QtCore.QTimer.singleShot(0, lambda: _ver_cuando_listo(dlg, ver))
    return dlg


def _ver_cuando_listo(dlg, ident, intentos=40):
    if dlg._trabajo is None and ident in dlg.escena.objetos:
        dlg.ver(ident)
    elif intentos > 0:
        QtCore.QTimer.singleShot(100, lambda: _ver_cuando_listo(dlg, ident, intentos - 1))
