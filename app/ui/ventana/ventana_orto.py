"""Modo ortogonal (F8) y rastreo polar (F10) al dibujar a mano, como en Civil 3D.

Recomendación 3 de la revisión (2026-11-13): «para el trazado manual, la opción de hacer trazos
ortogonales y con ángulos como lo hace el Civil 3D (F8)». En la barra de estado, junto a las
coordenadas, dos botones conmutables:

  • ORTO (F8): cada tramo nuevo va solo en horizontal o vertical (`trazo_asistido.ortogonales`).
    Llegar EXACTO al extremo o vértice de otra utilidad sigue mandando (como el «osnap» de AutoCAD).
  • POLAR (F10): los imanes de ángulo (seguir recto y girar N°, 2·N°… y los mismos desde los
    ejes de la hoja). Clic derecho = el incremento (5°…90°). Encendido a 45° = lo de siempre;
    apagado, el tramo solo queda en el paso de 0.25° (sin imanes).

Los dos se recuerdan (QSettings «pdf-to-cad»/«app», `trazo/*`). ORTO y POLAR se excluyen, como
en AutoCAD. Lo usa `TrazoMixin._resolver_trazo`. Clase mezcla de `Main`.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from nucleo import trazo_asistido as TA
from traduccion.i18n import LANG_BUS
from ui.comun.icons import icono_conmutable


def _ajustes():
    return QtCore.QSettings("pdf-to-cad", "app")


def _leer_bool(clave, defecto):
    v = _ajustes().value(clave, defecto)
    return v in (True, "true", "1", 1) if not isinstance(v, bool) else v


def _texto_inc(v):
    return f"{v:g}°"


class OrtoPolarMixin:
    def _armar_orto_polar(self):
        """Botones ORTO / POLAR en la barra de estado + atajos F8 / F10."""
        self._orto = _leer_bool("trazo/orto", False)
        self._polar = _leer_bool("trazo/polar", True)
        try:
            self._polar_inc = float(_ajustes().value("trazo/polar_inc", TA.POLAR_INC_DEG))
        except (TypeError, ValueError):
            self._polar_inc = TA.POLAR_INC_DEG
        if self._polar_inc not in TA.POLAR_INCREMENTOS:
            self._polar_inc = TA.POLAR_INC_DEG
        if self._orto:
            self._polar = False

        self.act_orto = QtGui.QAction(self)
        _bind(self.act_orto, "setText", "Modo ortogonal")
        self.act_orto.setCheckable(True); self.act_orto.setChecked(self._orto)
        self.act_orto.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_F8))
        self.act_orto.setShortcutContext(QtCore.Qt.WindowShortcut)
        self.act_orto.toggled.connect(self._poner_orto)
        self.act_polar = QtGui.QAction(self)
        _bind(self.act_polar, "setText", "Rastreo polar")
        self.act_polar.setCheckable(True); self.act_polar.setChecked(self._polar)
        self.act_polar.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_F10))
        self.act_polar.setShortcutContext(QtCore.Qt.WindowShortcut)
        self.act_polar.toggled.connect(self._poner_polar)
        for a in (self.act_orto, self.act_polar):
            self.addAction(a)                          # el atajo vive con la barra de menús oculta
        acc = getattr(self, "_acc", None)
        if acc is not None:                            # paleta de comandos (Ctrl+K)
            acc["Modo ortogonal"] = self.act_orto
            acc["Rastreo polar"] = self.act_polar

        # Botones SOLO con icono, como la barra de estado de Civil 3D (pedido del usuario 2026-11-13):
        # escuadra = ortogonal, rayos con arco = polar; el nombre y el atajo van en el globo.
        self.act_orto.setIcon(icono_conmutable("mdi:trazo-orto"))
        self.act_polar.setIcon(icono_conmutable("mdi:trazo-polar"))
        self.btn_orto = self._boton_estado(self.act_orto)
        self.btn_polar = self._boton_estado(self.act_polar)
        self.btn_polar.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_polar.customContextMenuRequested.connect(self._menu_polar)
        self._textos_orto_polar()
        LANG_BUS.changed.connect(self._textos_orto_polar)
        return self.btn_orto, self.btn_polar

    def _boton_estado(self, accion):
        b = QtWidgets.QToolButton()
        b.setDefaultAction(accion)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        b.setIconSize(QtCore.QSize(18, 18))
        b.setFixedSize(30, 24)
        b.setProperty("toggleTool", True)
        b.setAutoRaise(True)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        return b

    def _textos_orto_polar(self, *_):
        self.act_orto.setToolTip(_tr("<b>ORTO</b> — Modo ortogonal (F8)<br>Al dibujar, cada tramo solo en horizontal o vertical."))
        self.act_polar.setToolTip(_tr("<b>POLAR</b> — Rastreo polar (F10)<br>La línea se pega a los ángulos múltiplos de {inc}.<br>"
                                      "Clic derecho para cambiar el incremento.").format(inc=_texto_inc(self._polar_inc)))

    def _menu_polar(self, pos):
        m = QtWidgets.QMenu(self)
        m.addSection(_tr("Incremento del rastreo polar"))
        grupo = QtGui.QActionGroup(m)
        for v in TA.POLAR_INCREMENTOS:
            a = m.addAction(_texto_inc(v))
            a.setCheckable(True); a.setChecked(abs(v - self._polar_inc) < 1e-9)
            grupo.addAction(a)
            a.triggered.connect(lambda _c=False, v=v: self._poner_polar_inc(v))
        m.exec(self.btn_polar.mapToGlobal(pos))

    def _poner_polar_inc(self, v):
        self._polar_inc = float(v)
        _ajustes().setValue("trazo/polar_inc", self._polar_inc)
        if not self.act_polar.isChecked():
            self.act_polar.setChecked(True)            # elegir un incremento lo enciende
        self._textos_orto_polar()
        self._info(_tr("Rastreo polar cada {inc}.").format(inc=_texto_inc(self._polar_inc)))

    def _poner_orto(self, on):
        self._orto = bool(on)
        _ajustes().setValue("trazo/orto", self._orto)
        if on and self.act_polar.isChecked():
            self.act_polar.setChecked(False)           # como en AutoCAD: no van juntos
        self._info(_tr("Modo ortogonal: activado.") if on else _tr("Modo ortogonal: desactivado."))
        self._refrescar_trazo_en_curso()

    def _poner_polar(self, on):
        self._polar = bool(on)
        _ajustes().setValue("trazo/polar", self._polar)
        if on and self.act_orto.isChecked():
            self.act_orto.setChecked(False)
        self._info((_tr("Rastreo polar: activado ({inc}).").format(inc=_texto_inc(self._polar_inc))) if on
                   else _tr("Rastreo polar: desactivado."))
        self._refrescar_trazo_en_curso()

    def _refrescar_trazo_en_curso(self):
        """Con una utilidad a medio dibujar, la línea elástica se rehace en el modo nuevo."""
        if not getattr(self, "cur_pts", None):
            return
        try:
            p = self.canvas.mapToScene(self.canvas.mapFromGlobal(QtGui.QCursor.pos()))
            self._update_pipe_snap_hint(p.x(), p.y())
        except Exception:
            pass
