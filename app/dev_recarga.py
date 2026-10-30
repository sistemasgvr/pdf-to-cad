"""dev_recarga.py — SOLO DESARROLLO: F5 recarga los módulos .py cambiados sin cerrar la app.

Lo carga `main.py` solo si NO es el .exe (`sys.frozen`), por nombre (`importlib`), así PyInstaller no lo
mete en el instalador. Qué hace F5:
  1. `importlib.reload` de cada módulo de `app/` (o la raíz) cuyo archivo cambió desde la última vez.
     Los objetos Qt del módulo (p. ej. `theme.THEME_BUS`) se conservan: las conexiones ya hechas siguen.
  2. Vuelve a aplicar el tema (estilos y colores nuevos).
  3. Redibuja el plano.
Lo que ya se construyó (ventana principal, barras, paneles, métodos de `Main` y sus mezclas) NO cambia hasta
reiniciar; los diálogos que se abren DESPUÉS sí usan el código nuevo. Ante un error raro: reiniciar.
"""
import importlib
import os
import sys
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

_APP = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_APP)
_PROPIO = os.path.abspath(__file__)
_vistos: dict = {}            # archivo → fecha de modificación de la última recarga


def _modulos():
    """(nombre, módulo, archivo) de los módulos del proyecto cargados (nunca este ni librerías)."""
    for nombre, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if not f or not f.endswith(".py"):
            continue
        f = os.path.abspath(f)
        if f == _PROPIO or "site-packages" in f or not f.startswith(_RAIZ):
            continue
        if nombre in ("__main__", "__mp_main__"):
            continue
        yield nombre, mod, f


def _fecha(f):
    try:
        return os.path.getmtime(f)
    except OSError:
        return None


def _anotar():
    for _n, _m, f in _modulos():
        _vistos.setdefault(f, _fecha(f))


def _recargar(mod):
    """Recarga conservando los objetos Qt del módulo (buses de señales) y el tema activo."""
    viejos = {k: v for k, v in vars(mod).items() if isinstance(v, QtCore.QObject)}
    actual = getattr(mod, "_current", None)
    importlib.reload(mod)
    for k, v in viejos.items():
        setattr(mod, k, v)
    if actual is not None and mod.__name__.endswith("theme"):
        mod._current = mod.LIGHT if getattr(actual, "name", "") == "light" else mod.DARK


def recargar(win):
    cambiados, errores = [], []
    for nombre, mod, f in sorted(_modulos(), key=lambda x: x[0]):
        fecha = _fecha(f)
        if fecha is None or fecha == _vistos.get(f):
            continue
        try:
            _recargar(mod)
            cambiados.append(nombre)
        except Exception:
            errores.append(nombre)
            traceback.print_exc()
        _vistos[f] = fecha
    try:
        from ui.comun import theme
        theme.apply_theme(QtWidgets.QApplication.instance(), theme.tokens().name)
    except Exception:
        traceback.print_exc()
    try:
        if hasattr(win, "_redraw"):
            win._redraw()
    except Exception:
        traceback.print_exc()
    texto = "Recargado: " + (", ".join(cambiados) if cambiados else "nada cambió")
    if errores:
        texto += " · ERROR en: " + ", ".join(errores) + " (ver consola)"
    print("[dev] " + texto)
    try:
        mostrar = win.statusBar().showMessage      # solo desarrollo: sin traducir a propósito
        mostrar("[dev] " + texto, 8000)
    except Exception:
        pass


def instalar(win):
    """Atajo F5 en la ventana principal."""
    _anotar()
    sc = QtGui.QShortcut(QtGui.QKeySequence("F5"), win)
    sc.setContext(QtCore.Qt.ApplicationShortcut)
    sc.activated.connect(lambda: recargar(win))
    win._dev_recarga = sc
    print("[dev] Modo desarrollo: F5 recarga los módulos cambiados.")


def activar():
    """Engancha `instalar` al crear la ventana principal (sin tocar app_window)."""
    from ui.ventana import app_window
    original = app_window.Main.__init__

    def __init__(self, *a, **k):
        original(self, *a, **k)
        try:
            instalar(self)
        except Exception:
            traceback.print_exc()
    app_window.Main.__init__ = __init__
