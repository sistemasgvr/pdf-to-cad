"""Vista 3D de `Main` (mezcla): abrirla (Ver → «Vista 3D», F3, botón de la barra),
«Ver en 3D» de una utilidad (clic derecho) y mantenerla al día con el plano
(`_vista3d_al_dia`, al final de cada redibujo). La ventana y el modelo viven en
`ui/dialogos/vista3d_dialog.py` y `nucleo/modelo3d.py`.

Al abrirla se guarda el proyecto por si acaso (pedido del usuario 2026-10-10): con
archivo y cambios sin guardar, se guarda; sin archivo todavía, copia de recuperación
del autoguardado (no se abre «Guardar como» cada vez)."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr


class _PuntoAbierta(QtWidgets.QWidget):
    """Punto en la esquina del botón del riel: «esta ventana sigue abierta» (como el de una app abierta en la
    barra de tareas). Color de acento con un anillo del color del riel, para que se separe del icono."""
    LADO = 9

    def __init__(self, boton):
        super().__init__(boton)
        self.setObjectName("puntoAbierta")
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(self.LADO, self.LADO)
        boton.installEventFilter(self)
        self._colocar()
        from ui.comun import theme
        theme.al_tema(self, lambda *_a: self.update())

    def _colocar(self):
        b = self.parentWidget()
        self.move(b.width() - self.LADO - 4, 4)

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.Resize:
            self._colocar()
        return False

    def paintEvent(self, _e):
        from ui.comun import theme
        t = theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(QtGui.QColor(t.surface), 2))
        p.setBrush(QtGui.QColor(t.accent))
        p.drawEllipse(QtCore.QRectF(1, 1, self.LADO - 2, self.LADO - 2))


class Vista3DMixin:
    def abrir_vista3d(self):
        from ui.dialogos import vista3d_dialog
        self.terminar_trazo_en_curso()              # la línea a medias también pasa a 3D (2026-11-09)
        # Sin esperar al cálculo de fondo (2026-11-18, estrés con 29 mil utilidades: `_resultados_al_dia`
        # rehacía el plano aquí y la ventana quedaba ~20 s sin responder, ni al cierre). La vista se arma con lo
        # que hay y se rehace sola cuando llegan los conflictos y avisos (`_vista3d_al_dia` tras el redibujo).
        if not getattr(self, "_provisional", False):
            self._resultados_al_dia()
        self._guardar_antes_de_3d()
        return vista3d_dialog.abrir(self)

    def ver_en_3d(self):
        """Clic derecho → «Ver en 3D»: abre la vista y encuadra la utilidad elegida."""
        from ui.dialogos import vista3d_dialog
        self.terminar_trazo_en_curso()
        self._guardar_antes_de_3d()
        if 0 <= getattr(self, "sel_pipe", -1) < len(self.pipes):
            return vista3d_dialog.abrir(self, ver=self.sel_pipe + 1)
        return vista3d_dialog.abrir(self)

    def _guardar_antes_de_3d(self):
        """Guarda por si acaso antes de abrir la vista 3D. Devuelve "proyecto",
        "recuperacion" o "" (nada que guardar)."""
        if self.canvas.pixmap_item is None or not self._has_real_changes():
            return ""
        if self.project_path:
            self._write_project(self.project_path)
            return "proyecto"
        ag = getattr(self, "autoguardado", None)
        if ag is not None and ag.activo and ag.guardar_ahora():
            self._info(_tr("El proyecto aún no tiene archivo: se hizo una copia de recuperación. "
                           "Guárdalo con Ctrl+S."))
            return "recuperacion"
        return ""

    def _cerrar_vista3d(self):
        """El proyecto se cierra o cambia: la vista 3D se cierra con él. No tiene padre Qt (ver
        `vista3d_dialog._duenio`), así que nadie más la cierra: quedaba abierta mostrando el
        proyecto anterior (reporte del usuario 2026-11-10). La próxima vez arma la escena de cero."""
        dlg = self.__dict__.get("_vista3d_dlg")
        if dlg is None:
            return
        if dlg.isVisible():
            dlg.close()
        dlg._firma = None
        dlg._parcheada = False

    def _riel_vista3d_al_dia(self):
        """El botón «Vista 3D» del riel con un punto mientras la ventana sigue abierta, también minimizada
        (2026-11-18: minimizada no tiene botón en la barra de tareas y no se sabía que seguía ahí). No se usa el
        estado «marcado» del riel: ése dice qué página del panel está a la vista."""
        boton = self._boton_riel_vista3d()
        if boton is None:
            return
        dlg = self.__dict__.get("_vista3d_dlg")
        abierta = dlg is not None and dlg.isVisible()
        minimizada = abierta and dlg.isMinimized()
        punto = boton.findChild(QtWidgets.QWidget, "puntoAbierta")
        if punto is None:
            punto = _PuntoAbierta(boton)
        punto.setVisible(abierta)
        if minimizada:
            tip = _tr("Vista 3D: minimizada. Clic para volver a ella (F3).")
        elif abierta:
            tip = _tr("Vista 3D: abierta. Clic para traerla al frente (F3).")
        else:
            tip = _tr("Vista 3D")
        boton.setToolTip(tip)
        boton.setAccessibleDescription(tip)

    def _boton_riel_vista3d(self):
        from ui.ventana import ventana_shell
        for k, b in getattr(self, "_riel_btn", None) or []:
            item = ventana_shell.RIEL[k]
            if item is not None and item[3] == "abrir_vista3d":
                return b
        return None

    def _vista3d_al_dia(self):
        """El plano cambió (o la selección): si la vista 3D está abierta, que lo siga."""
        dlg = getattr(self, "_vista3d_dlg", None)
        if dlg is not None and dlg.isVisible():
            dlg.seleccion_del_plano()
            dlg.programar()
