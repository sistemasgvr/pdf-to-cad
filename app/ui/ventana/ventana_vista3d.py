"""Vista 3D de `Main` (mezcla): abrirla (Ver → «Vista 3D», F3, botón de la barra),
«Ver en 3D» de una utilidad (clic derecho) y mantenerla al día con el plano
(`_vista3d_al_dia`, al final de cada redibujo). La ventana y el modelo viven en
`ui/dialogos/vista3d_dialog.py` y `nucleo/modelo3d.py`.

Al abrirla se guarda el proyecto por si acaso (pedido del usuario 2026-10-10): con
archivo y cambios sin guardar, se guarda; sin archivo todavía, copia de recuperación
del autoguardado (no se abre «Guardar como» cada vez)."""
from __future__ import annotations

from traduccion.i18n import t as _tr


class Vista3DMixin:
    def abrir_vista3d(self):
        from ui.dialogos import vista3d_dialog
        self._guardar_antes_de_3d()
        return vista3d_dialog.abrir(self)

    def ver_en_3d(self):
        """Clic derecho → «Ver en 3D»: abre la vista y encuadra la utilidad elegida."""
        from ui.dialogos import vista3d_dialog
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

    def _vista3d_al_dia(self):
        """El plano cambió (o la selección): si la vista 3D está abierta, que lo siga."""
        dlg = getattr(self, "_vista3d_dlg", None)
        if dlg is not None and dlg.isVisible():
            dlg.seleccion_del_plano()
            dlg.programar()
