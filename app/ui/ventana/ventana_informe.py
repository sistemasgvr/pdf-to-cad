"""Herramientas → «Informe automático…» (pedido del usuario 2026-10-23): un Word con los conflictos y/o
avisos de normativa del proyecto, agrupados en zonas, con capturas 2D, 3D o ambas y cada uno explicado.

Pasos (todos con la barra precisa `barras_carga.informe`): opciones (`informe_dialog`) → fichas y zonas
(`nucleo/informe_datos`) → mapa general y capturas (`informe_capturas`) → redacción (`nucleo/informe_redaccion`
o la IA) → Word (`exportar/informe_word`). Nada cambia en el proyecto.

EN SEGUNDO PLANO (pedido del usuario 2026-10-23: la barra no dejaba seguir trabajando): `trabajo_pasos.
TrabajoPasos` corre los pasos entre evento y evento (las capturas, una por vuelta) y en hilos la IA y el Word;
la barra va en una tarjeta abajo a la derecha que no tapa nada (`tarjeta_avance`), también en la Vista 3D
mientras toma sus capturas, con «Cancelar». Abrir otro proyecto lo cancela (`_ia_soltar`).
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

    def generar_informe(self, ruta=None, opciones=None, esperar=None):
        """Arma el informe en segundo plano. `ruta`/`opciones` = sin preguntar (pruebas); con `ruta` (o
        `esperar=True`) espera el final y devuelve la ruta (o None si se canceló)."""
        from nucleo import informe_datos
        from ui.comun import tarjeta_avance
        from ui.comun.trabajo_pasos import TrabajoPasos
        from ui.comun.ui_common import DOWNLOADS
        from ui.dialogos import informe_dialog
        from ui.ventana import barras_carga as BC
        esperar = ruta is not None if esperar is None else esperar
        if getattr(self, "_informe_en_curso", None) is not None:
            self._info(_tr("Ya se está armando un informe: espera a que termine o cancélalo."))
            return None
        if not self.pipes:
            self._info(_tr("No hay utilidades: no hay nada que informar."))
            return None
        self._resultados_al_dia()
        conflictos = list(getattr(self, "_conflictos", None) or [])
        avisos = list(getattr(self, "_normas_avisos", None) or [])
        if opciones is None:
            rec = informe_datos.CLASE_RECONOCIMIENTO
            opciones = informe_dialog.pedir(self, len(conflictos),
                                            sum(1 for a in avisos if a.clase not in ("tipo", rec)),
                                            sum(1 for a in avisos if a.clase == rec))
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
        capa = tarjeta_avance.CapaTarjetas(self, cancel=self.cancelar_informe)
        av = BC.informe(self, inf, opciones, len(self.pipes), lista3d, con_ia=con_ia,
                        paralelo=getattr(redactor, "paralelo", 1), capa=capa)
        notas = [motivo] if motivo else []
        av.abrir(_tr("Armando el informe…"))
        pasos = self._pasos_informe(inf, opciones, ft, redactor, con_ia, ruta, notas, av, capa)

        def al_terminar(res, error):
            av.cerrar()
            self._informe_en_curso = None
            if error is not None:
                QtWidgets.QMessageBox.warning(self, _tr("Informe automático"),
                                              _tr("No se pudo armar el informe: {e}").format(e=error))
            elif res:
                self._ofrecer_abrir_informe(res, inf)
        trabajo = self._informe_en_curso = TrabajoPasos(self, pasos, avance=av.recibir, al_terminar=al_terminar)
        trabajo.empezar()
        return trabajo.esperar() if esperar else None

    def cancelar_informe(self):
        """«Cancelar» de la tarjeta (o se abrió otro proyecto): el informe no se guarda."""
        trabajo = getattr(self, "_informe_en_curso", None)
        if trabajo is not None:
            trabajo.cancelar()
            self._info(_tr("Se canceló el informe."))

    def _pasos_informe(self, inf, opciones, ft, redactor, con_ia, ruta, notas, av, capa):
        """El informe paso a paso (`trabajo_pasos`): entre paso y paso la ventana atiende al usuario."""
        av.recibir("informe_datos", 1, 1)
        yield
        imagenes = yield from self._capturas_informe(inf, opciones, ft, av, notas, capa)
        if con_ia:
            redactor = yield from self._redactar_con_ia(redactor, inf, notas)
        from exportar import informe_word
        try:
            yield ("hilo", lambda: informe_word.escribir(inf, redactor, ruta, imagenes, notas))
        except PermissionError:
            QtWidgets.QMessageBox.warning(self, _tr("Informe automático"), _tr(
                "No se pudo guardar el informe: ¿está abierto en Word? Ciérralo y vuelve a intentar."))
            return None
        return ruta

    def _redactar_con_ia(self, redactor, inf, notas):
        """La IA redacta todo ANTES del Word, en otro hilo (la red no traba la ventana). Si el servidor no
        responde, lo ya redactado (memoria del proyecto) y plantillas."""
        from ia import proveedor as P
        from nucleo.informe_redaccion import RedactorPlantilla

        def trabajo():
            redactor.verificar()
            return redactor.preparar(inf)
        try:
            yield ("hilo", trabajo)
        except P.ErrorIA as e:
            redactor.preparar(inf, sin_red=True)          # lo que ya redactó antes (memoria del proyecto) sirve
            notas.append(_tr("La IA no está disponible ({e}): se usó lo ya redactado y plantillas.").format(e=e))
            if not redactor.cuenta["memoria"]:
                return RedactorPlantilla()
            notas.append(redactor.nota())
            return redactor
        except GeneratorExit:
            redactor.cancelar()                           # informe cancelado: que el hilo deje de pedir
            raise
        notas.append(redactor.nota())
        return redactor

    def _capturas_informe(self, inf, opciones, ft, av, notas, capa=None):
        from ui.ventana import informe_capturas as IC
        imagenes = {}
        if not inf.zonas:
            return imagenes
        n = len(inf.zonas)
        c2 = IC.Captura2D(self)
        try:
            av.recibir("informe_mapa")
            yield
            if inf.caja_total:
                imagenes["mapa"] = c2.mapa(inf.caja_total, inf.zonas)
            if opciones.capturas_2d:
                for k, z in enumerate(inf.zonas, 1):
                    av.recibir("informe_2d", k, n)
                    yield
                    imagenes[("2d", z.numero)] = c2.zona(z.caja)
        finally:
            c2.cerrar()
        if opciones.capturas_3d:
            c3 = IC.Captura3D(self)
            av.recibir("informe_3d_armar")
            motivo = c3.abrir()
            if not motivo:
                if capa is not None:
                    capa.agregar(c3.dlg)                  # la barra del informe también en la Vista 3D
                yield ("esperar", c3.lista, IC.ESPERA_3D_S)
                motivo = c3.comprobar()
            if motivo:
                notas.append(_tr("El informe no lleva capturas 3D: {m}.").format(m=motivo))
            else:
                try:
                    for k, z in enumerate(inf.zonas, 1):
                        av.recibir("informe_3d", k, n)
                        yield
                        if not c3.lista():                # el usuario cambió algo: esperar la escena nueva
                            yield ("esperar", c3.lista, IC.ESPERA_3D_S)
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
        caja.setModal(False)                             # el usuario puede estar trabajando: no lo detiene
        caja.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        def al_pulsar(boton):
            if boton is abrir:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(ruta))
        caja.buttonClicked.connect(al_pulsar)
        caja.show()
