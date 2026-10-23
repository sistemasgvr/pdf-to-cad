"""La IA en la ventana (pedido del usuario 2026-10-23): menú IA → «Pregúntale al proyecto…» y «Configurar IA…».

- `_config_ia()`: proveedor, url, modelo y pedidos a la vez (QSettings «pdf-to-cad»/«app», `ia/*`).
- `_ia_memoria()`: la `ia.memoria.Memoria` del proyecto, en la carpeta «<proyecto> - IA» junto al .digproj (sin
  proyecto guardado queda en memoria y se escribe al guardar: `_ia_al_guardar`; al abrir otro: `_ia_soltar`).
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
        from ia import proveedor as P
        return {"proveedor": s.value("ia/proveedor", P.PLANTILLA), "url": s.value("ia/url", P.URL_OLLAMA),
                "modelo": s.value("ia/modelo", P.MODELO_OLLAMA), "paralelo": s.value("ia/paralelo", 2)}

    def configurar_ia(self):
        from ui.dialogos import ia_config_dialog
        if ia_config_dialog.pedir(self):
            dlg = getattr(self, "_ia_chat", None)
            if dlg is not None:
                dlg.actualizar_estado()

    # ── memoria del proyecto ──
    def _ia_memoria(self):
        from ia import memoria as M
        carpeta = M.carpeta_de(getattr(self, "project_path", None))
        mem = getattr(self, "_ia_mem", None)
        if mem is None:
            mem = self._ia_mem = M.Memoria(carpeta)
        elif carpeta and mem.carpeta != carpeta:
            mem.vincular(carpeta)
        return mem

    def _ia_al_guardar(self, path):
        """Tras guardar: lo aprendido sin proyecto se escribe junto a él; con «Guardar como…», se copia."""
        from ia import memoria as M
        mem = getattr(self, "_ia_mem", None)
        if mem is None:
            return
        nueva = M.carpeta_de(path)
        if mem.carpeta and mem.carpeta != nueva:
            mem.copiar_a(nueva)
        elif mem.carpeta != nueva:
            mem.vincular(nueva)

    def _ia_soltar(self):
        """Otro proyecto: otra memoria (y otros datos)."""
        self._ia_mem = None
        self._ia_cache_datos = None
        dlg = getattr(self, "_ia_chat", None)
        if dlg is not None:
            dlg.proyecto_cambiado()

    def abrir_carpeta_ia(self):
        mem = self._ia_memoria()
        if not mem.carpeta:
            QtWidgets.QMessageBox.information(self, _tr("Carpeta de aprendizaje"), _tr(
                "Guarda el proyecto: lo que la IA aprenda quedará en una carpeta junto al archivo del proyecto."))
            return
        os.makedirs(mem.carpeta, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(mem.carpeta))

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
        from ui.dialogos.ia_chat import PreguntaDialog
        dlg = getattr(self, "_ia_chat", None)
        if dlg is None:
            dlg = self._ia_chat = PreguntaDialog(self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.enfocar()
        return dlg
