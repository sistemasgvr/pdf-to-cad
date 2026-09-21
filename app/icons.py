"""icons.py — Iconos SVG del proyecto (bajados de api.iconify.design).

Los SVG viven en `app/icons/<set>/<name>.svg` (por defecto set = `mdi` =
Material Design Icons). Vienen de Iconify con `fill="currentColor"`, así que
podemos re-tintarlos en runtime sustituyendo esa palabra por el color que
queramos — típicamente un token del tema activo, para que sigan el
modo claro/oscuro global.

Uso:
    from icons import icon
    btn.setIcon(icon("mdi:pencil-outline"))          # tinta = tokens().text
    act.setIcon(icon("mdi:magnify-plus-outline",
                     color=theme.tokens().accent))    # tinta explícita

Al alternar tema, los iconos que quieran actualizarse se reasignan en el
`_restyle` / `_apply_theme_custom_styles` correspondiente (los widgets no se
enteran solos de que el tema cambió — su QIcon guarda pixmaps ya rasterizados).

`preload()` opcional: rasteriza al inicio los iconos más usados para evitar el
primer parpadeo al abrir un diálogo.
"""
from __future__ import annotations

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
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


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

    Nota: el QIcon devuelto guarda un pixmap ya rasterizado. Si cambia el tema,
    hay que llamar de nuevo a `icon(...)` con el nuevo color para retintarlo.
    """
    if color is None:
        # Import diferido: evita ciclos y permite usar icons.py antes de que
        # el módulo theme se haya inicializado.
        import theme as _theme
        color = _theme.tokens().text
    color = _color_str(color)

    path = _resolve_path(name)
    svg = _read_svg(path)
    if svg is None:
        if name not in _MISSING_LOGGED:
            _MISSING_LOGGED.add(name)
            print(f"[icons] SVG no encontrado: {name} → {path}")
        return _fallback_icon(size)

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


def preload(names: list[str]) -> None:
    """Rasteriza y descarta los iconos indicados para calentar el `_read_svg`
    cache y evitar parpadeo al abrir la UI. Silencioso ante nombres inválidos."""
    for n in names:
        try:
            icon(n)
        except Exception:
            pass
