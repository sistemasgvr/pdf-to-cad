"""Herramientas → «Informe automático…» (pedido del usuario 2026-10-23): un Word con los conflictos y/o
avisos de normativa del proyecto, agrupados en zonas, con capturas 2D, 3D o ambas y cada uno explicado.

Pasos (todos con la barra precisa `barras_carga.informe`): opciones (`informe_dialog`) → fichas y zonas
(`nucleo/informe_datos`) → mapa general y capturas (`informe_capturas`) → redacción (`nucleo/informe_redaccion`:
hoy plantillas; la IA, después) → Word (`exportar/informe_word`). Nada cambia en el proyecto.
"""
from __future__ import annotations

import datetime as _dt
import os

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr

_FILTRO_DOCX = "Word (*.docx)"              # filtro de archivo (igual en ambos idiomas)


class InformeMixin:
    def _titulo_informe(self):
        ruta = getattr(self, "project_path", None) or getattr(self, "pdf_path", None) or ""
        return os.path.splitext(os.path.basename(ruta))[0] if ruta else ""

    def generar_informe(self, ruta=None, opciones=None):
        """Arma el informe y devuelve su ruta (o None si se canceló). `ruta`/`opciones` = sin preguntar
        (pruebas)."""
        from nucleo import informe_datos
        from ui.comun.ui_common import DOWNLOADS
        from ui.dialogos import informe_dialog
        from ui.ventana import barras_carga as BC
        if not self.pipes:
            self._info(_tr("No hay utilidades: no hay nada que informar."))
            return None
        self._resultados_al_dia()
        conflictos = list(getattr(self, "_conflictos", None) or [])
        avisos = list(getattr(self, "_normas_avisos", None) or [])
        if opciones is None:
            opciones = informe_dialog.pedir(self, len(conflictos), sum(1 for a in avisos if a.clase != "tipo"))
            if opciones is None:
                return None
        if ruta is None:
            nombre = "{t}Informe {f}.docx".format(t=(self._titulo_informe() + " - ") if self._titulo_informe() else "",
                                                 f=_dt.datetime.now().strftime("%Y-%m-%d"))
            ruta, _ = QtWidgets.QFileDialog.getSaveFileName(self, _tr("Guardar informe"), os.path.join(DOWNLOADS, nombre),
                                                            _FILTRO_DOCX)
            if not ruta:
                return None
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        inf = informe_datos.armar(conflictos, avisos, self.pipes, ft, opciones, titulo=self._titulo_informe())
        from ia import redactor_ia
        redactor, motivo = redactor_ia.crear(self._config_ia(), self._ia_memoria())
        dlg3d = getattr(self, "_vista3d_dlg", None)
        lista3d = bool(dlg3d is not None and dlg3d.isVisible() and dlg3d._trabajo is None and dlg3d.escena is not None)
        con_ia = isinstance(redactor, redactor_ia.RedactorIA)
        av = BC.informe(self, inf, opciones, len(self.pipes), lista3d, con_ia=con_ia,
                        paralelo=getattr(redactor, "paralelo", 1))
        notas = [motivo] if motivo else []
        try:
            with av.abrir(_tr("Armando el informe…")):
                av.recibir("informe_datos", 1, 1, pump=True)
                imagenes = self._capturas_informe(inf, opciones, ft, av, notas)
                if con_ia:
                    redactor = self._redactar_con_ia(redactor, inf, av, notas)
                from exportar import informe_word
                with av.escuchar():
                    informe_word.escribir(inf, redactor, ruta, imagenes, notas)
        except PermissionError:
            QtWidgets.QMessageBox.warning(self, _tr("Informe automático"), _tr(
                "No se pudo guardar el informe: ¿está abierto en Word? Ciérralo y vuelve a intentar."))
            return None
        self._ofrecer_abrir_informe(ruta, inf)
        return ruta

    def _redactar_con_ia(self, redactor, inf, av, notas):
        """La IA redacta todo ANTES del Word, en otro hilo (la red no traba la ventana) y con «Cancelar»: lo que
        no alcanzó a redactar sale con la plantilla. Si el servidor no responde, todo con plantilla."""
        from ia import proveedor as P
        from nucleo.informe_redaccion import RedactorPlantilla
        from ui.comun import en_hilo

        def trabajo():
            redactor.verificar()
            return redactor.preparar(inf)
        try:
            _r, _err, cancelado = en_hilo.ejecutar(self, trabajo, _tr("La IA redacta el informe…"), cancelable=True,
                                                   avance=av.recibir, relanzar=True)
        except P.ErrorIA as e:
            redactor.preparar(inf, sin_red=True)          # lo que ya redactó antes (memoria del proyecto) sirve
            notas.append(_tr("La IA no está disponible ({e}): se usó lo ya redactado y plantillas.").format(e=e))
            if not redactor.cuenta["memoria"]:
                return RedactorPlantilla()
            notas.append(redactor.nota())
            return redactor
        if cancelado:
            redactor.cancelar()
            notas.append(_tr("Se canceló la redacción con IA: lo que faltaba salió con plantilla."))
        notas.append(redactor.nota())
        return redactor

    def _capturas_informe(self, inf, opciones, ft, av, notas):
        from ui.ventana import informe_capturas as IC
        imagenes = {}
        if not inf.zonas:
            return imagenes
        n = len(inf.zonas)
        c2 = IC.Captura2D(self)
        try:
            av.recibir("informe_mapa", pump=True)
            if inf.caja_total:
                imagenes["mapa"] = c2.mapa(inf.caja_total, inf.zonas)
            if opciones.capturas_2d:
                for k, z in enumerate(inf.zonas, 1):
                    av.recibir("informe_2d", k, n, pump=True)
                    imagenes[("2d", z.numero)] = c2.zona(z.caja)
        finally:
            c2.cerrar()
        if opciones.capturas_3d:
            c3 = IC.Captura3D(self)
            av.recibir("informe_3d_armar", pump=True)
            motivo = c3.preparar(lambda: av.recibir("informe_3d_armar", pump=True))
            if motivo:
                notas.append(_tr("El informe no lleva capturas 3D: {m}.").format(m=motivo))
            else:
                try:
                    for k, z in enumerate(inf.zonas, 1):
                        av.recibir("informe_3d", k, n, pump=True)
                        imagenes[("3d", z.numero)] = c3.zona(z.caja, ft)
                finally:
                    c3.terminar()
        return imagenes

    def _ofrecer_abrir_informe(self, ruta, inf):
        caja = QtWidgets.QMessageBox(self)
        caja.setWindowTitle(_tr("Informe automático"))
        caja.setText(_tr("Informe guardado: {n} conflictos y avisos en {z} zonas.\n{ruta}").format(
            n=len(inf.fichas), z=len(inf.zonas), ruta=ruta))
        abrir = caja.addButton(_tr("Abrir el informe"), QtWidgets.QMessageBox.AcceptRole)
        caja.addButton(_tr("Cerrar"), QtWidgets.QMessageBox.RejectRole)
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return                                       # (pruebas)
        caja.exec()
        if caja.clickedButton() is abrir:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(ruta))
