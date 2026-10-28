"""2.0.0 — «Recientes» en el menú de la «P» (prototipo «faltante», aprobado por el usuario 2026-10-27).

Los últimos proyectos (.digproj) abiertos o guardados, con su fecha. La lista vive en
%APPDATA%/pdf-to-cad/recientes.json (variable `PDFCAD_RECIENTES` para las pruebas: `tests/conftest.py`).
Abrir uno = `Main._open_project_path` de siempre (pregunta antes si hay cambios sin guardar, como «Abrir
proyecto…»). Las copias de recuperación (autoguardado) nunca entran.
"""
import json
import os
import time

from PySide6 import QtWidgets

from traduccion.i18n import t as _tr
from ui.comun.icons import icon as _icon

MAX_RECIENTES = 8


def ruta() -> str:
    env = os.environ.get("PDFCAD_RECIENTES")
    if env:
        return env
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pdf-to-cad", "recientes.json")


def leer() -> list:
    try:
        with open(ruta(), encoding="utf-8") as f:
            datos = json.load(f)
        return [d for d in datos if isinstance(d, dict) and d.get("ruta")]
    except (OSError, ValueError):
        return []


def anotar(path: str):
    """Pone `path` primero en la lista (sin repetir; máximo `MAX_RECIENTES`)."""
    if not path:
        return
    from ui.ventana import autoguardado
    try:
        rec = os.path.normcase(os.path.abspath(autoguardado.carpeta_base()))
        if os.path.normcase(os.path.abspath(path)).startswith(rec):
            return                                  # copia de recuperación: no es un proyecto del usuario
    except Exception:  # noqa: BLE001
        pass
    clave = os.path.normcase(os.path.abspath(path))
    lista = [d for d in leer() if os.path.normcase(os.path.abspath(d["ruta"])) != clave]
    lista.insert(0, {"ruta": os.path.abspath(path), "fecha": time.time()})
    try:
        os.makedirs(os.path.dirname(ruta()), exist_ok=True)
        tmp = ruta() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(lista[:MAX_RECIENTES], f, ensure_ascii=False, indent=1)
        os.replace(tmp, ruta())
    except OSError:
        pass                                        # sin permiso de escritura: la lista no es imprescindible


def hace(fecha: float, ahora: float = None) -> str:
    s = max(0, (ahora or time.time()) - float(fecha or 0))
    if s < 3600:
        return _tr("Hace {n} min").format(n=max(1, int(s // 60)))
    if s < 86400:
        return _tr("Hace {n} h").format(n=int(s // 3600))
    if s < 2 * 86400:
        return _tr("Ayer")
    return _tr("Hace {n} días").format(n=int(s // 86400))


class RecientesMixin:
    """Sección «Recientes» del menú Archivo (la «P» de la barra superior)."""

    def _armar_recientes(self, menu):
        self._menu_recientes = menu.addMenu(_icon("mdi:history"), _tr("Recientes"))
        self._menu_recientes.aboutToShow.connect(self._llenar_recientes)
        self._llenar_recientes()

    def _llenar_recientes(self):
        m = getattr(self, "_menu_recientes", None)
        if m is None:
            return
        m.clear()
        lista = [d for d in leer() if os.path.isfile(d["ruta"])]
        if not lista:
            a = m.addAction(_tr("Sin proyectos recientes"))
            a.setEnabled(False)
            return
        for d in lista:
            a = m.addAction(_icon("mdi:file-document-outline"),
                            f"{os.path.basename(d['ruta'])}  ·  {hace(d.get('fecha'))}")
            a.setToolTip(d["ruta"])
            a.setStatusTip(d["ruta"])
            a.triggered.connect(lambda _=False, p=d["ruta"]: self.abrir_reciente(p))
        m.setToolTipsVisible(True)

    def abrir_reciente(self, path: str):
        if not os.path.isfile(path):
            QtWidgets.QMessageBox.information(self, _tr("Recientes"),
                                              _tr("Ese proyecto ya no está en su carpeta:\n{p}").format(p=path))
            return
        self._open_project_path(path)          # pregunta por los cambios sin guardar, como siempre

    def _anotar_reciente(self, path):
        anotar(path)


