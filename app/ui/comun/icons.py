"""icons.py — Iconos SVG del proyecto (bajados de api.iconify.design).

Los SVG viven en `app/icons/<set>/<name>.svg` (por defecto set = `mdi` =
Material Design Icons). Vienen de Iconify con `fill="currentColor"`, así que
podemos re-tintarlos en runtime sustituyendo esa palabra por el color que
queramos — típicamente un token del tema activo, para que sigan el
modo claro/oscuro global.

Uso:
    from ui.comun.icons import icon
    btn.setIcon(icon("mdi:pencil-outline"))          # tinta = tokens().text
    act.setIcon(icon("mdi:magnify-plus-outline",
                     color=theme.tokens().accent))    # tinta explícita

Iconos que siguen al tema (pedido del usuario 2026-10-28: «si el icono es oscuro, al cambiar a modo
oscuro debe hacerse blanco y viceversa»): si el color es el de por defecto o un TOKEN de color de tinta del
tema activo (`tokens().text_muted`, `.danger`, `.text_on_accent`…), el QIcon devuelto lleva un motor
(`_IconoDelTema`) que se dibuja con el valor de ESE token en el tema activo AL PINTAR: al cambiar de tema
todo widget que lo muestra se repinta y el icono cambia solo, aunque nadie vuelva a llamar a `icon()`. Sin
cambiar de tema se ve EXACTAMENTE igual que antes (el motor delega en el mismo QIcon(pixmap) de siempre,
uno por color). Un color fijo que no es token del tema (los de cada utilidad, la bombilla…) da el QIcon de
siempre. Lo que se convierte a imagen fija (`icon(...).pixmap(...)` en un QLabel) no se entera: esos
sitios se vuelven a pintar con `al_cambiar_tema` (o en su `_restyle` / `_apply_theme_custom_styles`).

`preload()` opcional: rasteriza al inicio los iconos más usados para evitar el
primer parpadeo al abrir un diálogo.
"""
from __future__ import annotations

import ctypes
import os
import sys
from functools import lru_cache
from typing import Optional

from PySide6 import QtCore, QtGui, QtSvg


def _icons_base_dir() -> str:
    """Carpeta `icons/` junto a este módulo. En el .exe (PyInstaller) los SVG
    se empacan en `_MEIPASS/icons` vía PDF-a-CAD.spec."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "icons")
        if os.path.isdir(bundled):
            return bundled
    # Este módulo vive en app/ui/comun/ (2026-10-08): la carpeta `icons/` sigue en app/.
    _app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(_app, "icons")


_ICONS_DIR = _icons_base_dir()
_DEFAULT_SIZE = 24     # px del pixmap generado; QIcon se escala a lo que pida el widget
_MISSING_LOGGED: set = set()


def _resolve_path(name: str) -> str:
    """`mdi:pencil-outline` → `<app>/icons/mdi/pencil-outline.svg`. Fallback:
    si no lleva ':' (ej. `pencil-outline`), asume set `mdi`."""
    if ":" in name:
        set_name, icon_name = name.split(":", 1)
    else:
        set_name, icon_name = "mdi", name
    return os.path.join(_ICONS_DIR, set_name, f"{icon_name}.svg")


@lru_cache(maxsize=512)
def _read_svg(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _color_str(color) -> str:
    """Normaliza el color a un string CSS. Acepta QColor, str hex, str name."""
    if isinstance(color, QtGui.QColor):
        return color.name()
    return str(color)


def _fallback_icon(size: int) -> QtGui.QIcon:
    """Icono neutro (cuadrado transparente) para cuando falta el SVG. Evita que
    la app se caiga si un nombre está mal escrito."""
    pm = QtGui.QPixmap(size, size); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setPen(QtGui.QPen(QtGui.QColor(200, 60, 60), 1.5))
    p.drawRect(2, 2, size - 5, size - 5)
    p.drawLine(2, 2, size - 3, size - 3)
    p.drawLine(size - 3, 2, 2, size - 3); p.end()
    return QtGui.QIcon(pm)


def icon(name: str, color=None, size: int = _DEFAULT_SIZE) -> QtGui.QIcon:
    """Devuelve un QIcon a partir de un SVG local, tintado con `color`.

    `color` puede ser un `QColor`, un string hex (`"#1e2531"`) o None → usa
    `theme.tokens().text` (color del texto principal del tema activo).

    Si el color es el de por defecto o un token de tinta del tema activo, el icono SIGUE al tema (ver el
    docstring del módulo); un color fijo da un QIcon con el pixmap ya rasterizado, como siempre.
    """
    # Import diferido: evita ciclos y permite usar icons.py antes de que
    # el módulo theme se haya inicializado.
    from ui.comun import theme as _theme
    token = "text" if color is None else None
    if color is None:
        color = _theme.tokens().text
    color = _color_str(color)
    if token is None:
        token = _token_de(color, _theme.tokens())

    path = _resolve_path(name)
    if token is not None:
        base = _icono_fijo(path, getattr(_theme.tokens(), token), size)     # (el mismo color: es su token)
        if base is None:
            return _icono_sin_svg(name, path, size)
        return QtGui.QIcon(_IconoDelTema(path, token, size))
    return _icono_sin_svg(name, path, size) if _read_svg(path) is None else _render(path, color, size)


def _render(path: str, color: str, size: int) -> QtGui.QIcon:
    svg = _read_svg(path)
    # Iconify entrega los SVG con `fill="currentColor"`; algunos usan stroke.
    tinted = svg.replace("currentColor", color)

    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(tinted.encode("utf-8")))
    if not renderer.isValid():
        return _fallback_icon(size)

    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QtGui.QIcon(pm)


def _icono_sin_svg(name: str, path: str, size: int) -> QtGui.QIcon:
    if name not in _MISSING_LOGGED:
        _MISSING_LOGGED.add(name)
        print(f"[icons] SVG no encontrado: {name} → {path}")
    return _fallback_icon(size)


# ── Iconos que siguen al tema ───────────────────────────────────────────────
# Tokens que se usan como TINTA de iconos, en orden: si dos tienen el mismo valor en el tema activo
# (claro: accent = focus, soft_text = text_info…), gana el primero. Los de fondo no (en claro el blanco
# de `surface` es también `text_on_accent`: un icono blanco sobre un botón de color sigue blanco).
_TOKENS_TINTA = ("text", "text_muted", "text3", "text_on_accent", "soft_text", "accent", "success",
                 "warning", "danger", "options_text", "focus", "text_info", "text_disabled",
                 "accent_hover", "accent_pressed", "success_hover", "danger_hover", "invalid")
_TOKENS_POR_TEMA: dict = {}


def _token_de(color: str, tema) -> Optional[str]:
    """El token de tinta del tema activo que vale `color` (None = color fijo)."""
    tabla = _TOKENS_POR_TEMA.get(tema.name)
    if tabla is None:
        tabla = {}
        for tk in _TOKENS_TINTA:
            qc = QtGui.QColor(getattr(tema, tk))
            if qc.isValid():
                tabla.setdefault(qc.name(), tk)
        _TOKENS_POR_TEMA[tema.name] = tabla
    qc = QtGui.QColor(color)
    if not qc.isValid() or qc.alpha() != 255:
        return None
    return tabla.get(qc.name())


@lru_cache(maxsize=2048)
def _icono_fijo(path: str, color: str, size: int) -> Optional[QtGui.QIcon]:
    """El QIcon(pixmap) de siempre para ese color (uno por color: lo usa el motor al pintar)."""
    if _read_svg(path) is None:
        return None
    return _render(path, color, size)


_THEME_MOD = None


def _tema_activo():
    global _THEME_MOD
    if _THEME_MOD is None:
        from ui.comun import theme as _t
        _THEME_MOD = _t
    return _THEME_MOD.tokens()


class _IconoDelTema(QtGui.QIconEngine):
    """Motor del icono que sigue al tema: cada llamada de Qt va al QIcon(pixmap) del color que tiene el
    token en el tema activo, con las MISMAS llamadas que Qt le haría (mismos píxeles, mismo tamaño)."""

    def __init__(self, path: str, token: str, size: int):
        super().__init__()
        self._datos = (path, token, size)
        self._lado = size
        self._base = QtCore.QSize(size, size)
        self._tema = None                              # el tema (objeto) del QIcon guardado en `_ic`
        self._ic = None

    def _actual(self) -> QtGui.QIcon:
        tema = _tema_activo()
        if tema is not self._tema:                     # solo al cambiar de tema se busca otro QIcon
            path, token, size = self._datos
            self._ic = _icono_fijo(path, getattr(tema, token), size) or _fallback_icon(size)
            self._tema = tema
        return self._ic

    def clone(self):
        # Qt se queda con el clon y lo borra él al soltar su QIcon, pero PySide no le pasa la propiedad a C++:
        # Python lo liberaría en cuanto vuelve de aquí y Qt usaría memoria ya liberada (se caía). Una referencia
        # de más que nunca se suelta: Python no lo libera nunca (es diminuto y Qt casi nunca pide un clon: solo
        # al cambiar un QIcon compartido, p. ej. `addPixmap` sobre una copia).
        nuevo = _IconoDelTema(*self._datos)
        ctypes.pythonapi.Py_IncRef(ctypes.py_object(nuevo))
        return nuevo

    def isNull(self):
        return False

    def availableSizes(self, mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off):
        return self._actual().availableSizes(mode, state)

    def actualSize(self, size, mode, state):
        # = QPixmapIconEngine con UN pixmap cuadrado de `_lado` (verificado tamaño por tamaño): si no
        # cabe, el cuadrado más grande que cabe
        w, h = size.width(), size.height()
        n = self._lado
        if n > w or n > h:
            m = w if w < h else h
            return QtCore.QSize(m, m)
        return self._base

    def pixmap(self, size, mode, state):
        return self._actual().pixmap(size, 1.0, mode, state)

    def scaledPixmap(self, size, mode, state, scale):
        return self._actual().pixmap(size, scale, mode, state)

    def paint(self, painter, rect, mode, state):
        # QIcon::paint ya alineó `rect` al actualSize: el del QIcon(pixmap) da el mismo rect
        self._actual().paint(painter, rect, QtCore.Qt.AlignCenter, mode, state)


def icono_conmutable(name: str, color=None, size: int = _DEFAULT_SIZE) -> QtGui.QIcon:
    """Icono de un botón CONMUTABLE: normal con `color` (como `icon`) y, seleccionado (estado On), en
    `text_on_accent` del tema activo, para que contraste con el fondo oscuro del indicador (pedido
    2026-10-30). Los dos siguen al tema."""
    return QtGui.QIcon(_IconoConmutable(icon(name, color, size), _icono_on(name, size)))


def _icono_on(name: str, size: int) -> QtGui.QIcon:
    path = _resolve_path(name)
    if _read_svg(path) is None:
        return _icono_sin_svg(name, path, size)
    return QtGui.QIcon(_IconoDelTema(path, "text_on_accent", size))


class _IconoConmutable(QtGui.QIconEngine):
    """Delega en el icono normal (Off) o en el blanco (On); mismas llamadas que Qt le haría a cada uno."""

    def __init__(self, normal: QtGui.QIcon, encendido: QtGui.QIcon):
        super().__init__()
        self._n, self._e = normal, encendido

    def _de(self, state):
        return self._e if state == QtGui.QIcon.On else self._n

    def clone(self):
        nuevo = _IconoConmutable(self._n, self._e)
        ctypes.pythonapi.Py_IncRef(ctypes.py_object(nuevo))     # ver _IconoDelTema.clone
        return nuevo

    def isNull(self):
        return False

    def availableSizes(self, mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off):
        return self._de(state).availableSizes(mode, QtGui.QIcon.Off)

    def actualSize(self, size, mode, state):
        return self._de(state).actualSize(size, mode, QtGui.QIcon.Off)

    def pixmap(self, size, mode, state):
        return self._de(state).pixmap(size, 1.0, mode, QtGui.QIcon.Off)

    def scaledPixmap(self, size, mode, state, scale):
        return self._de(state).pixmap(size, scale, mode, QtGui.QIcon.Off)

    def paint(self, painter, rect, mode, state):
        self._de(state).paint(painter, rect, QtCore.Qt.AlignCenter, mode, QtGui.QIcon.Off)


def preload(names: list[str]) -> None:
    """Rasteriza y descarta los iconos indicados para calentar el `_read_svg`
    cache y evitar parpadeo al abrir la UI. Silencioso ante nombres inválidos."""
    for n in names:
        try:
            icon(n)
        except Exception:
            pass
