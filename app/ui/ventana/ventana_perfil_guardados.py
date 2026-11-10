"""Perfiles guardados (mezcla de `PerfilMixin`): menú ⋯, guardar, abrir y quitar (`Main.perfiles`).

Movido tal cual de `ventana_perfil` (2026-11-08)."""
from __future__ import annotations

from PySide6 import QtWidgets

from traduccion.i18n import t as _tr
from ui.comun.icons import icon


class GuardadosPerfilMixin:
    def _perfil_numero(self):
        nombre = getattr(self, "_perfil_nombre", None)
        for k, p in enumerate(self.perfiles):
            if p.get("nombre") == nombre:
                return k + 1
        return len(self.perfiles) + 1

    def _perfil_lista(self):
        """Menú ⋯: perfiles guardados (el abierto marcado), guardar, quitar y encuadrar."""
        m = getattr(self, "menu_perfil", None)
        if m is None:
            return
        m.clear()
        titulo = m.addAction(_tr("Perfiles guardados ({n})").format(n=len(self.perfiles)))
        titulo.setEnabled(False)
        actual = getattr(self, "_perfil_nombre", None)
        for k, p in enumerate(self.perfiles):
            a = m.addAction(p.get("nombre") or "")
            a.setCheckable(True)
            a.setChecked(p.get("nombre") == actual)
            a.triggered.connect(lambda _=False, i=k: self.perfil_abrir(i))
        m.addSeparator()
        a = m.addAction(icon("mdi:file-plus-outline"), _tr("Nuevo perfil"))
        a.triggered.connect(lambda: self.perfil_nuevo())
        a = m.addAction(icon("mdi:eraser"), _tr("Limpiar (borrar este borrador y elegir los tramos)"))
        a.setEnabled(self._perfil_rec is not None)
        a.triggered.connect(lambda: self.perfil_limpiar())
        a = m.addAction(icon("mdi:content-save-outline"), _tr("Guardar este perfil…"))
        a.setEnabled(self._perfil_rec is not None)
        a.triggered.connect(lambda: self.perfil_guardar())
        k = next((i for i, p in enumerate(self.perfiles) if p.get("nombre") == actual), -1)
        a = m.addAction(icon("mdi:delete-outline"), _tr("Quitar «{n}» de los guardados").format(n=actual or "")
                        if k >= 0 else _tr("Quitar de los guardados"))
        a.setEnabled(k >= 0)
        a.triggered.connect(lambda: self.perfil_borrar(k))
        m.addSeparator()
        a = m.addAction(icon("mdi:fit-to-page-outline"), _tr("Encuadrar el perfil"))
        a.triggered.connect(lambda: self.perfil_vista.encuadrar())

    def perfil_guardar(self, nombre=None):
        """Guarda el perfil a la vista con un nombre (si existe, lo reemplaza). Devuelve el nombre."""
        if self._perfil_rec is None or self._perfil_anclas is None:
            return None
        if nombre is None:
            sugerido = getattr(self, "_perfil_nombre", None) or _tr("Perfil {n}").format(n=len(self.perfiles) + 1)
            nombre, ok = QtWidgets.QInputDialog.getText(self, _tr("Guardar perfil"), _tr("Nombre del perfil:"),
                                                        text=sugerido)
            if not ok:
                return None
        nombre = (nombre or "").strip()
        if not nombre:
            return None
        ini, fin = self._perfil_anclas
        dato = {"nombre": nombre, "ini": list(ini), "fin": list(fin)}
        for k, p in enumerate(self.perfiles):
            if p.get("nombre") == nombre:
                self.perfiles[k] = dato
                break
        else:
            self.perfiles.append(dato)
        self._perfil_nombre = nombre
        self._dirty = True
        self._perfil_refrescar()
        return nombre

    def perfil_abrir(self, k):
        if not (0 <= k < len(self.perfiles)):
            return False
        p = self.perfiles[k]
        rec = self._rec_de_anclas(p["ini"], p["fin"])
        if rec is None:
            self.statusBar().showMessage(_tr("Ese perfil ya no existe en el plano: sus utilidades cambiaron."), 6000)
            return False
        if not self._perfil_visible():
            self._perfil_panel().show()
        self._perfil_pila = []
        # empieza en su inicio A (`ini`), como lo crea Civil 3D (antes: el sentido automático, y salía al revés)
        self._perfil_poner(rec, encuadrar=True, nombre=p.get("nombre"), a=p["ini"])
        return True

    def perfil_borrar(self, k):
        if not (0 <= k < len(self.perfiles)):
            return False
        if self.perfiles[k].get("nombre") == getattr(self, "_perfil_nombre", None):
            self._perfil_nombre = None
        del self.perfiles[k]
        self._dirty = True
        self._perfil_refrescar()
        return True
