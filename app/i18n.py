"""i18n.py — Sistema de internacionalización simple y sin fricción.

Diseño:
  - Todos los textos originales de la app siguen escritos en **español** en el
    código (no rompemos nada). Cada texto que queramos traducir se envuelve con
    ``t("Texto en español")``.
  - Cuando el idioma activo es "es", ``t()`` devuelve el texto tal cual → cero
    overhead, cero cambio visible.
  - Cuando el idioma es "en", ``t()`` busca la traducción en el diccionario
    ``TRANSLATIONS["en"]``. Si no la encuentra, devuelve el original (así
    strings sin traducir siguen apareciendo en español en vez de romper la UI).
  - Preferencia persistida en ``QSettings``.
  - Bus de señales (``LANG_BUS.changed``) para que widgets con textos ya
    materializados se puedan re-traducir en vivo (menús, toolbars, docks). Los
    widgets creados después del cambio ya salen en el idioma nuevo sin más.

Uso típico:
    from i18n import t, set_lang, get_lang, LANG_BUS

    lbl = QtWidgets.QLabel(t("Buzones"))     # etiqueta traducible
    LANG_BUS.changed.connect(self._retranslate)   # para restilar cuando cambia

Términos de ingeniería civil (US imperial workflow) — traducidos con la
terminología que usa Civil 3D en inglés, no traducción literal:
    tubería/utilidad  → Pipe/Utility        buzón      → Manhole
    invert            → Invert              alineamiento → Alignment
    familia/tamaño    → Family/Size         parts list → Parts List
    bancoducto        → Duct Bank           conducto   → Conduit
    envolvente        → Envelope            rejilla    → Grid
    cota/elevación    → Elevation           georref.   → Georeference

Widgets de vida larga (ventana principal): usar ``bind(widget, "setText",
"Clave")`` en vez de ``setText(t("Clave"))`` para que se re-traduzcan solos al
cambiar el idioma (ver «Textos vivos»).

Textos con datos: la clave es una PLANTILLA, ``t("Utilidad #{n}").format(n=i)``;
nunca ``t(f"Utilidad #{i}")`` (esa clave no puede estar en el diccionario).

Textos en constantes de módulo (tablas de etiquetas): marcarlos con ``N_("…")``
(no traduce, solo los señala como claves) y traducir al mostrarlos con ``t()``.

Documentos largos (manual): ``load_doc("manual")`` lee
``docs/manual.<idioma>.html``.

Módulos de lógica PURA (sin Qt): ``from i18n_core import t`` — mismo motor,
sin la capa Qt de este archivo (preferencia, señal, ``bind``).

Las traducciones viven en ``i18n_en.py`` (interfaz) e ``i18n_en_changelog.py``
(historial). ``tests/test_i18n.py`` falla si un texto visible queda sin envolver
o sin traducir.
"""
from __future__ import annotations
import os
from typing import Optional
from PySide6 import QtCore

import i18n_core as _core
# El motor puro (sin Qt) vive en i18n_core; aquí se reexporta para la UI.
from i18n_core import (SUPPORTED_LANGS, DEFAULT_LANG, TRANSLATIONS,  # noqa: F401
                       get_lang, t, N_, tr_text)


class _LangBus(QtCore.QObject):
    """Señal global emitida cuando el usuario cambia el idioma en vivo."""
    changed = QtCore.Signal(str)   # nuevo código de idioma ("es" | "en")


LANG_BUS = _LangBus()

_settings_key = "app/language"


# ─────────────────────────────────────────────────────────────────────────────
def _settings():
    return QtCore.QSettings("pdfcad", "app")


def load_lang() -> str:
    """Lee la preferencia guardada (o el default) y la activa. Se llama una vez
    al arrancar la app, ANTES de construir la UI."""
    saved = _settings().value(_settings_key, DEFAULT_LANG)
    _core.activate(saved if saved in SUPPORTED_LANGS else DEFAULT_LANG)
    return get_lang()


def set_lang(lang: str) -> None:
    """Cambia el idioma activo, lo guarda en preferencias y emite la señal
    ``LANG_BUS.changed`` para que la UI se re-traduzca en vivo."""
    if not _core.activate(lang):
        return
    _settings().setValue(_settings_key, lang)
    LANG_BUS.changed.emit(lang)


# ── Textos vivos ─────────────────────────────────────────────────────────────
# Un widget creado al arrancar conserva el texto con el que nació: cambiar el
# idioma después no lo toca. ``bind`` aplica la traducción Y la registra, y
# ``retranslate_all`` (conectado a LANG_BUS) reaplica todas las registradas.
# Así cada texto se registra donde se crea el widget, en vez de en una lista
# aparte que se desactualiza. Es para widgets de VIDA LARGA (ventana principal,
# docks, barras); un diálogo modal se crea después del cambio y le basta ``t()``.
#
# Referencias FUERTES a propósito: con ``weakref`` se perdería el registro de
# un widget cuyo envoltorio Python se libera mientras el objeto C++ sigue vivo
# (hijo de otro widget). Los objetos C++ destruidos se podan en cada pasada.
_bindings: dict = {}


def bind(obj, setter: str, key, *args, fmt: Optional[dict] = None,
         pre: str = "", post: str = "", guard=None):
    """Llama ``obj.<setter>(*args, texto)`` con la traducción de ``key`` y lo
    recuerda para re-traducirlo en vivo. ``args`` son los argumentos previos al
    texto (índice de un ítem, de una pestaña…). Volver a llamarlo con el mismo
    (obj, setter, args) reemplaza el registro anterior (p. ej. texto dinámico).

        i18n.bind(lbl, "setText", "Escala")
        i18n.bind(combo, "setItemText", "Agua (W)", 0)
        i18n.bind(lbl, "setText", "Lienzo {n}", fmt={"n": nombre})

    ``guard`` (opcional): función sin argumentos; si devuelve False al
    re-traducir, el registro se descarta (el ítem ya no es el mismo).
    """
    getattr(obj, setter)(*args, tr_text(key, fmt, pre, post))
    _bindings[(id(obj), setter, args)] = (obj, setter, args, key, fmt, pre, post, guard)
    return obj


def bind_item(combo, key, data=None, icon=None, fmt: Optional[dict] = None):
    """``combo.addItem`` con el texto traducible en vivo. El registro se
    invalida solo si el combo se vacía y ese índice pasa a ser otro ítem."""
    if icon is None:
        combo.addItem("", data)
    else:
        combo.addItem(icon, "", data)
    idx = combo.count() - 1
    return bind(combo, "setItemText", key, idx, fmt=fmt,
                guard=lambda: combo.count() > idx and combo.itemData(idx) == data)


def retranslate_all() -> None:
    """Reaplica todos los textos registrados con ``bind`` en el idioma activo."""
    import shiboken6
    for k, (obj, setter, args, key, fmt, pre, post, guard) in list(_bindings.items()):
        if not shiboken6.isValid(obj) or (guard is not None and not guard()):
            del _bindings[k]
            continue
        try:
            getattr(obj, setter)(*args, tr_text(key, fmt, pre, post))
        except RuntimeError:
            del _bindings[k]


LANG_BUS.changed.connect(lambda _lang: retranslate_all())


_DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


def load_doc(name: str) -> str:
    """Documento largo (manual…) en el idioma activo: ``docs/<name>.<lang>.html``,
    con vuelta al español si ese idioma no lo tiene. Los textos de varias
    páginas NO van como clave de ``t()``: cualquier retoque del original
    rompería la clave sin avisar."""
    for lang in (get_lang(), DEFAULT_LANG):
        ruta = os.path.join(_DOCS_DIR, f"{name}.{lang}.html")
        if os.path.isfile(ruta):
            with open(ruta, encoding="utf-8") as f:
                return f.read()
    return ""


def display_lang(code: str) -> str:
    """Nombre humano del idioma en el idioma activo (para desplegables)."""
    if code == "es":
        return t("Español")
    if code == "en":
        return t("Inglés")
    return code
