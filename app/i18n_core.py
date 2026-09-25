"""i18n_core.py — núcleo de traducción PURO (sin Qt).

Lo usan los módulos de lógica que no deben depender de Qt (``duct_bank``,
``recognition``, ``civil_catalog``, ``composite``…) para que sus mensajes al
usuario salgan en el idioma activo. La capa Qt (preferencia persistida, señal
de cambio en vivo, ``bind``) vive en ``i18n.py`` y reexporta todo lo de aquí:
la UI importa ``i18n``; la lógica pura, ``i18n_core``.
"""
from __future__ import annotations

from typing import Optional

# Datos de traducción, separados del motor: interfaz e historial de versiones.
from i18n_en import EN as _EN
from i18n_en_changelog import EN_CHANGELOG as _EN_CHANGELOG

SUPPORTED_LANGS = ("es", "en")
DEFAULT_LANG = "es"

TRANSLATIONS: dict[str, dict[str, str]] = {"en": {**_EN, **_EN_CHANGELOG}}

_current_lang: str = DEFAULT_LANG


def get_lang() -> str:
    """Código del idioma activo ("es" o "en")."""
    return _current_lang


def activate(lang: str) -> bool:
    """Activa ``lang`` sin persistir ni avisar a nadie (eso lo hace
    ``i18n.set_lang``). Devuelve True si el idioma cambió."""
    global _current_lang
    if lang not in SUPPORTED_LANGS or lang == _current_lang:
        return False
    _current_lang = lang
    return True


def t(text_es: str, en: Optional[str] = None) -> str:
    """Traduce ``text_es`` al idioma activo.

    Contrato:
      - Si idioma = "es" → devuelve ``text_es`` sin tocar. Rendimiento cero.
      - Si idioma = "en":
          * si se pasó ``en`` explícito, lo usa (útil para strings puntuales
            que no queremos meter al dict maestro).
          * si el string existe en ``TRANSLATIONS["en"]``, devuelve esa
            traducción.
          * si no, devuelve el original en español (así una UI sin traducir
            sigue visible; no se rompe nada).
    """
    if _current_lang == "es":
        return text_es
    if en is not None:
        return en
    return TRANSLATIONS.get(_current_lang, {}).get(text_es, text_es)


def N_(text_es: str) -> str:
    """Marca un texto como TRADUCIBLE sin traducirlo todavía (convención de
    gettext). Para tablas de datos cuyos textos se traducen después, al
    mostrarse: ``_KIND = {"x": N_("Líneas")}`` … ``t(_KIND[k])``. Devuelve el
    texto tal cual; sirve para que el test de i18n encuentre la clave."""
    return text_es


def tr_text(key, fmt: Optional[dict] = None, pre: str = "", post: str = ""):
    """``t(key)`` con plantilla y adornos. ``key`` puede ser una lista de claves
    (cabeceras de tabla, ``addItems``) y entonces devuelve una lista."""
    if isinstance(key, (list, tuple)):
        return [tr_text(k, fmt, pre, post) for k in key]
    s = t(key)
    if fmt:
        s = s.format(**fmt)
    return f"{pre}{s}{post}"
