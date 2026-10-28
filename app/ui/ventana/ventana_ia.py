"""La IA en la ventana (pedido del usuario 2026-10-23): menú IA → «Pregúntale al proyecto…» y «Configurar IA…».

- `_config_ia()`: proveedor, url, modelo y pedidos a la vez (QSettings «pdf-to-cad»/«app», `ia/*`).
- `_ia_memoria()`: la `ia.memoria.Memoria` vista desde el proyecto abierto. Lo aprendido va a UN JSON
  compartido en el repo (`entrenamiento_ia/entrenamiento_ia.json`, se pasa por Git); lo de antes de guardar el
  proyecto pasa a él al guardar (`_ia_al_guardar`); la carpeta vieja «<proyecto> - IA» se importa al abrir.
- `_ia_datos()`: `ia.contexto.DatosProyecto` con los conflictos y avisos al día; se rehace solo si el modelo
  cambió (`_firma_modelo`), así preguntar seguido no recalcula nada.
- `_ia_ir_a(codigo)`: C-12 / N-3 / AGUA-5 → al lugar en el plano.
La lógica está en `app/ia/` (pura); aquí solo lo que toca la ventana.
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr


class IAMixin:
    # ── configuración ──
    def _config_ia(self):
        s = QtCore.QSettings("pdf-to-cad", "app")
        from ia import memoria as M
        from ia import proveedor as P
        entorno = s.value("ia/entorno", M.entorno_por_defecto())
        M.configurar(entorno)                            # dónde lee y escribe lo aprendido (ia.memoria.rutas)
        return {"proveedor": s.value("ia/proveedor", P.PLANTILLA), "url": s.value("ia/url", P.URL_OLLAMA),
                "modelo": s.value("ia/modelo", P.MODELO_OLLAMA), "paralelo": s.value("ia/paralelo", 2),
                "entorno": entorno}

    def configurar_ia(self):
        from ui.dialogos import ia_config_dialog
        if ia_config_dialog.pedir(self):
            self._ia_config_guardada()

    def _ia_config_guardada(self):
        """Tras guardar la configuración (aquí o en Ajustes → Asistente IA)."""
        self._config_ia()
        self._ia_mem = None                              # el entorno pudo cambiar: otro archivo de aprendizaje
        dlg = getattr(self, "_ia_chat", None)
        if dlg is not None:
            dlg.actualizar_estado()

    # ── lo aprendido (UN JSON compartido en el repo: `ia.memoria`) ──
    def _ia_memoria(self):
        from ia import memoria as M
        ruta = getattr(self, "project_path", None)
        mem = getattr(self, "_ia_mem", None)
        if mem is None:
            self._config_ia()
            mem = self._ia_mem = M.Memoria(ruta)
            mem.importar_carpeta(M.carpeta_de(ruta))     # la carpeta vieja «<proyecto> - IA», si la hay
        elif ruta and mem.proyecto != M.nombre_proyecto(ruta):
            mem.vincular(ruta)
        return mem

    def _ia_al_guardar(self, path):
        """Tras guardar (o «Guardar como…»): lo aprendido sin proyecto pasa a ser de este proyecto."""
        mem = getattr(self, "_ia_mem", None)
        if mem is not None:
            mem.vincular(path)

    def _ia_soltar(self):
        """Otro proyecto: otros datos; un informe a medias se cancela."""
        if getattr(self, "_informe_en_curso", None) is not None:
            self.cancelar_informe()
        self._ia_mem = None
        self._ia_cache_datos = None
        dlg = getattr(self, "_ia_chat", None)
        if dlg is not None:
            dlg.proyecto_cambiado()

    def abrir_carpeta_ia(self):
        mem = self._ia_memoria()
        os.makedirs(mem.carpeta, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(mem.carpeta))

    def pasar_a_produccion(self):
        """IA → «Pasar a producción…»: enseñanzas de desarrollo → el archivo del instalador."""
        from ui.dialogos import ia_produccion_dialog
        ia_produccion_dialog.abrir(self)
        self._ia_mem = None                              # producción cambió: releer

    # ── datos del proyecto ──
    def _ia_datos(self):
        from ia.contexto import DatosProyecto
        from nucleo import informe_datos
        self._resultados_al_dia()
        firma = (self._firma_modelo(), getattr(self, "project_path", None))
        cache = getattr(self, "_ia_cache_datos", None)
        if cache is not None and cache[0] == firma:
            return cache[1]
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        conflictos = list(getattr(self, "_conflictos", None) or [])
        avisos = list(getattr(self, "_normas_avisos", None) or [])
        fichas, _sin_tipo = informe_datos.fichas(conflictos, avisos, self.pipes, informe_datos.Opciones())
        informe_datos.zonas(fichas, ft)                 # las mismas zonas (y números N-n) que el informe
        datos = DatosProyecto.armar(self.pipes, fichas, ft, self._titulo_informe())
        self._ia_cache_datos = (firma, datos)
        return datos

    def _ia_ir_a(self, codigo):
        datos = getattr(self, "_ia_cache_datos", None)
        ref = datos[1].ref(codigo) if datos else None
        if ref is None:
            return False
        objeto = "pipe" if ref["objeto"] == "pipe" else None
        self._ir_a_elemento(ref["x"], ref["y"], objeto, ref["indice"], activar=False)
        return True

    # ── «Pregúntale al proyecto» ──
    def abrir_pregunta(self):
        if getattr(self, "_incrustar_ok", lambda: False)():    # 2.0.0: en el panel del Asistente
            self.mostrar_asistente(True, "chat")
            dlg = self._ia_chat
            dlg.enfocar()
            return dlg
        from ui.dialogos.ia_chat import PreguntaDialog
        dlg = getattr(self, "_ia_chat", None)
        if dlg is None:
            dlg = self._ia_chat = PreguntaDialog(self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.enfocar()
        return dlg
