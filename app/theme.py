"""theme.py — Tema visual global (claro / oscuro) para toda la app.

Uso:
    from theme import apply_theme, tokens, THEME_BUS

    apply_theme(app, "dark")           # o "light"; carga la preferencia guardada
    color = tokens().accent             # colores del tema activo
    THEME_BUS.changed.connect(on_theme_changed)   # para restilar tus propios QSS

Diseño:
  - `Theme` es un dataclass con TOKENS de color (bg, surface, text, accent, …).
    Los widgets que usan estilos custom (btn_export, diálogos con QSS propio,
    header/footer del duct bank) leen `tokens().*` en vez de escribir colores.
  - `apply_theme(app, name)` fija la paleta Fusion + el stylesheet global de
    QApplication y emite `THEME_BUS.changed(name)` para que las vistas custom
    recompongan sus QSS.
  - La preferencia se persiste vía QSettings (organización "PDFCAD", app
    "AsistenteC3D") con la clave `ui/theme`. Se recupera con `load_preference()`.
  - No importa nada específico de la app (funciona en aislamiento) — cualquier
    widget puede pedir el color activo.

Regla de oro (misma que en el CSS original): NO tocamos propiedades sueltas de
`QCheckBox`/`QRadioButton` sin estilar su `::indicator` completo, o Fusion deja
de dibujar el chek visualmente. Ambos temas cumplen esto.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Literal, Optional

from PySide6 import QtCore, QtGui, QtWidgets


ThemeName = Literal["dark", "light"]


# ── Tokens de color ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Theme:
    name: ThemeName

    # Fondos y superficies
    window: str           # fondo global de la app
    surface: str          # fondo de paneles/dock/groupbox
    surface_alt: str      # fondo alterno (barra inferior, filas alternas)
    header: str           # cabecera de diálogos (Duct Bank)
    input_bg: str         # QLineEdit / QSpinBox / QComboBox

    # Textos
    text: str             # texto principal
    text_muted: str       # texto suave (leyendas, ayudas)
    text_on_accent: str   # texto sobre color acento (típicamente blanco)
    text_disabled: str
    text_info: str        # texto informativo con contraste (status bar, hints)

    # Acentos y estados
    accent: str           # botón primario / selección
    accent_hover: str
    accent_pressed: str
    danger: str
    danger_hover: str
    focus: str            # borde de foco
    success: str          # botón toggle activado
    success_hover: str

    # Bordes y separadores
    border: str
    border_soft: str
    hover: str            # fondo hover neutro
    grid_bg: str          # fondo del lienzo/grid en el Duct Bank
    grid_line_minor: str
    grid_line_major: str

    # Envolvente/conducto del Duct Bank (colores neutrales al tema)
    envelope_fill: str
    envelope_border: str
    conduit_fill: str
    conduit_border: str
    conduit_text: str         # texto dentro del conducto (contraste contra conduit_fill)
    selection: str
    invalid: str

    # Menús / scrollbars
    menu_bg: str
    menu_hover: str
    scrollbar_track: str
    scrollbar_thumb: str
    scrollbar_thumb_hover: str


# Tema oscuro — colores exactos del stylesheet original que teníamos hardcodeado.
DARK = Theme(
    name="dark",
    window="#2f2f2f", surface="#2f2f2f", surface_alt="#3a3a3a",
    header="#232a3a", input_bg="#242424",
    text="#ececec", text_muted="#c8ccd6", text_on_accent="#ffffff",
    text_disabled="#7d7d7d",
    text_info="#adc6ff",   # azul claro suave sobre fondos oscuros

    accent="#2f6ad9", accent_hover="#4a83e8", accent_pressed="#2657ad",
    danger="#d1352d", danger_hover="#e0453c",
    focus="#6ba3ff",
    success="#1f8f4a", success_hover="#26a758",
    border="#4d4d4d", border_soft="#3f3f3f",
    hover="#3a3a3a",
    grid_bg="#252525", grid_line_minor="#3a3a3a", grid_line_major="#4d4d4d",
    envelope_fill="#3c4a68", envelope_border="#6ba3ff",
    conduit_fill="#e5eaf3", conduit_border="#f0f0f0", conduit_text="#1e2531",
    selection="#f0a020", invalid="#ff6b6b",
    menu_bg="#333333", menu_hover="#2f6ad9",
    scrollbar_track="#2b2b2b", scrollbar_thumb="#5a5a5a", scrollbar_thumb_hover="#757575",
)

# Tema claro — paleta neutra sobre gris/blanco; acentos igual al azul del brand
# para que los reflejos/selecciones se mantengan reconocibles.
LIGHT = Theme(
    name="light",
    window="#f2f4f8", surface="#ffffff", surface_alt="#eef2f9",
    header="#2a67c4", input_bg="#ffffff",
    text="#1e2531", text_muted="#4a5568", text_on_accent="#ffffff",
    text_disabled="#a0a8b6",
    text_info="#0f3d78",   # azul marino oscuro para máximo contraste sobre fondos claros

    accent="#2f6ad9", accent_hover="#4a83e8", accent_pressed="#2657ad",
    danger="#c22a2a", danger_hover="#d43535",
    focus="#4d8eff",
    success="#218a4d", success_hover="#2ba85e",
    border="#d4dbe6", border_soft="#e6eaf1",
    hover="#e6ecf7",
    grid_bg="#fcfcff", grid_line_minor="#e4e6ec", grid_line_major="#c8ccd6",
    envelope_fill="#e6efff", envelope_border="#2a67c4",
    conduit_fill="#ffffff", conduit_border="#1e2531", conduit_text="#1e2531",
    selection="#e56b17", invalid="#dc3545",
    menu_bg="#ffffff", menu_hover="#2f6ad9",
    scrollbar_track="#eef1f6", scrollbar_thumb="#c1c8d4", scrollbar_thumb_hover="#a8b0be",
)


# ── Bus de cambios de tema ─────────────────────────────────────────────────
class _ThemeBus(QtCore.QObject):
    """Emite `changed(name)` cada vez que se aplica un tema. Los diálogos con
    QSS custom se conectan a esta señal para refrescar sus estilos."""
    changed = QtCore.Signal(str)


THEME_BUS = _ThemeBus()
_current: Theme = DARK        # se sobreescribe al llamar apply_theme()


def tokens() -> Theme:
    """Devuelve el `Theme` activo. Preferido sobre importar DARK/LIGHT directo."""
    return _current


def is_dark() -> bool:
    return _current.name == "dark"


# ── Persistencia ───────────────────────────────────────────────────────────
_SETTINGS_ORG = "PDFCAD"
_SETTINGS_APP = "AsistenteC3D"
_SETTINGS_KEY = "ui/theme"


def load_preference(default: ThemeName = "dark") -> ThemeName:
    """Lee el tema guardado por el usuario. Devuelve `default` si no hay nada."""
    s = QtCore.QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    v = s.value(_SETTINGS_KEY, default)
    if v not in ("dark", "light"):
        v = default
    return v  # type: ignore[return-value]


def save_preference(name: ThemeName) -> None:
    s = QtCore.QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    s.setValue(_SETTINGS_KEY, name)
    s.sync()


# ── Paletas Qt ─────────────────────────────────────────────────────────────
def _palette_dark() -> QtGui.QPalette:
    p = QtGui.QPalette()
    p.setColor(QtGui.QPalette.Window,          QtGui.QColor(43, 43, 43))
    p.setColor(QtGui.QPalette.WindowText,      QtGui.QColor(232, 232, 232))
    p.setColor(QtGui.QPalette.Base,            QtGui.QColor(51, 51, 51))
    p.setColor(QtGui.QPalette.AlternateBase,   QtGui.QColor(60, 60, 60))
    p.setColor(QtGui.QPalette.ToolTipBase,     QtGui.QColor(30, 30, 30))
    p.setColor(QtGui.QPalette.ToolTipText,     QtGui.QColor(232, 232, 232))
    p.setColor(QtGui.QPalette.Text,            QtGui.QColor(232, 232, 232))
    p.setColor(QtGui.QPalette.Button,          QtGui.QColor(60, 60, 60))
    p.setColor(QtGui.QPalette.ButtonText,      QtGui.QColor(232, 232, 232))
    p.setColor(QtGui.QPalette.BrightText,      QtGui.QColor(255, 80, 80))
    p.setColor(QtGui.QPalette.Highlight,       QtGui.QColor(60, 90, 153))
    p.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    p.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(160, 160, 160))
    p.setColor(QtGui.QPalette.Light,           QtGui.QColor(85, 85, 85))
    p.setColor(QtGui.QPalette.Midlight,        QtGui.QColor(70, 70, 70))
    p.setColor(QtGui.QPalette.Dark,            QtGui.QColor(30, 30, 30))
    p.setColor(QtGui.QPalette.Mid,             QtGui.QColor(45, 45, 45))
    p.setColor(QtGui.QPalette.Shadow,          QtGui.QColor(20, 20, 20))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text,       QtGui.QColor(130, 130, 130))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(130, 130, 130))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(130, 130, 130))
    return p


def _palette_light() -> QtGui.QPalette:
    p = QtGui.QPalette()
    p.setColor(QtGui.QPalette.Window,          QtGui.QColor(242, 244, 248))
    p.setColor(QtGui.QPalette.WindowText,      QtGui.QColor(30, 37, 49))
    p.setColor(QtGui.QPalette.Base,            QtGui.QColor(255, 255, 255))
    p.setColor(QtGui.QPalette.AlternateBase,   QtGui.QColor(238, 242, 249))
    p.setColor(QtGui.QPalette.ToolTipBase,     QtGui.QColor(255, 255, 232))
    p.setColor(QtGui.QPalette.ToolTipText,     QtGui.QColor(30, 37, 49))
    p.setColor(QtGui.QPalette.Text,            QtGui.QColor(30, 37, 49))
    p.setColor(QtGui.QPalette.Button,          QtGui.QColor(238, 242, 249))
    p.setColor(QtGui.QPalette.ButtonText,      QtGui.QColor(30, 37, 49))
    p.setColor(QtGui.QPalette.BrightText,      QtGui.QColor(194, 42, 42))
    p.setColor(QtGui.QPalette.Highlight,       QtGui.QColor(47, 106, 217))
    p.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    p.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(138, 146, 165))
    p.setColor(QtGui.QPalette.Light,           QtGui.QColor(255, 255, 255))
    p.setColor(QtGui.QPalette.Midlight,        QtGui.QColor(238, 242, 249))
    p.setColor(QtGui.QPalette.Dark,            QtGui.QColor(160, 168, 182))
    p.setColor(QtGui.QPalette.Mid,             QtGui.QColor(200, 204, 214))
    p.setColor(QtGui.QPalette.Shadow,          QtGui.QColor(60, 68, 82))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text,       QtGui.QColor(160, 168, 182))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(160, 168, 182))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(160, 168, 182))
    return p


# ── SVGs para botones +/− del SpinBox ─────────────────────────────────────
_arrow_dir: Optional[str] = None

def _spinbox_arrow_dir(color: str, disabled_color: str) -> str:
    """Genera SVGs de + y − con los colores del tema y devuelve el directorio
    (con barras /, que es lo que QSS url() necesita incluso en Windows)."""
    global _arrow_dir
    if _arrow_dir is None:
        _arrow_dir = tempfile.mkdtemp(prefix="pdfcad_arrows_")
    _PLUS = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
             '<line x1="5" y1="2" x2="5" y2="8" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'
             '<line x1="2" y1="5" x2="8" y2="5" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'
             '</svg>')
    _MINUS = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
              '<line x1="2" y1="5" x2="8" y2="5" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'
              '</svg>')
    for name, tmpl, c in [("plus.svg", _PLUS, color), ("minus.svg", _MINUS, color),
                           ("plus_dis.svg", _PLUS, disabled_color),
                           ("minus_dis.svg", _MINUS, disabled_color)]:
        with open(os.path.join(_arrow_dir, name), "w", encoding="utf-8") as f:
            f.write(tmpl.format(c=c))
    return _arrow_dir.replace("\\", "/")


# ── Stylesheet global ──────────────────────────────────────────────────────
def build_stylesheet(t: Theme) -> str:
    """CSS global de QApplication, formateado con los tokens del tema `t`.

    Cubre el 90% de los widgets automáticamente. Componentes con estilos
    manuales (btn_export, header de diálogos, etc.) deben leer `tokens()` y
    re-aplicar cuando llegue `THEME_BUS.changed`."""
    ad = _spinbox_arrow_dir(t.text, t.text_disabled)
    return f"""
        /* ═══════════════════════════════════════════════════════════════════
           Tema {t.name} — generado desde app/theme.py.
           REGLA: si estilas un ::indicator (checkbox/radio), estila TODOS los
           estados o Fusion se lo pierde y desaparece la marca de check.
           ═══════════════════════════════════════════════════════════════════ */

        /* ── Base ── */
        QWidget {{ background-color: {t.window}; color: {t.text}; font-size: 14px; }}
        QToolTip {{ background-color: {t.header}; color: {t.text_on_accent};
                    border: 1px solid {t.border}; padding: 6px; font-size: 14px; }}

        /* ── Contenedores ── */
        QScrollArea, QAbstractScrollArea {{ background: {t.window}; border: none; }}
        QGroupBox {{ background: {t.window}; border: 1px solid {t.border}; border-radius: 5px;
                     margin-top: 14px; padding-top: 10px; font-weight: bold; }}
        QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                            left: 10px; padding: 0 6px; color: {t.text_info}; font-size: 14px; }}

        /* ── Acordeón de Herramientas ── */
        QToolBox::tab {{ background: {t.surface_alt}; color: {t.text}; border: 1px solid {t.border};
                         border-radius: 4px; padding-left: 10px; min-height: 34px; font-weight: bold; }}
        QToolBox::tab:hover {{ background: {t.hover}; color: {t.text}; }}
        QToolBox::tab:selected {{ background: {t.accent}; color: {t.text_on_accent};
                                   border: 1px solid {t.focus}; }}

        /* ── Menús ── */
        QMenu {{ background: {t.menu_bg}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}
        QMenu::item {{ padding: 8px 26px 8px 22px; }}
        QMenu::item:selected {{ background: {t.menu_hover}; color: {t.text_on_accent}; }}
        QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 8px; }}
        QMenuBar {{ background: {t.surface_alt}; color: {t.text}; }}
        QMenuBar::item {{ padding: 6px 11px; }}
        QMenuBar::item:selected {{ background: {t.accent}; color: {t.text_on_accent}; }}
        QStatusBar {{ background: {t.surface_alt}; color: {t.text_muted}; }}

        /* ── Campos de entrada ── */
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit,
        QListWidget, QTreeWidget, QTableWidget, QFontComboBox, QAbstractItemView {{
            background: {t.input_bg}; color: {t.text}; border: 1px solid {t.border};
            border-radius: 4px; selection-background-color: {t.accent};
            selection-color: {t.text_on_accent};
        }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {{
            padding: 6px 8px; min-height: 22px;
        }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
        QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {t.focus}; }}
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
            background: {t.surface_alt}; color: {t.text_disabled}; border: 1px solid {t.border_soft};
        }}
        QComboBox QAbstractItemView {{ background: {t.menu_bg}; color: {t.text};
                                        border: 1px solid {t.border};
                                        selection-background-color: {t.accent};
                                        selection-color: {t.text_on_accent}; outline: none; }}
        QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 4px 8px; }}

        /* ── Botones ── */
        QPushButton {{ background: {t.accent}; color: {t.text_on_accent}; border: 1px solid {t.accent_hover};
                        padding: 8px 14px; border-radius: 4px; font-weight: bold; min-height: 20px; }}
        QPushButton:hover {{ background: {t.accent_hover}; border: 1px solid {t.focus}; }}
        QPushButton:pressed {{ background: {t.accent_pressed}; }}
        QPushButton:disabled {{ background: {t.surface_alt}; color: {t.text_disabled}; border: 1px solid {t.border_soft}; }}
        QPushButton:checked {{ background: {t.success}; border: 2px solid {t.success_hover};
                                color: {t.text_on_accent}; }}
        QPushButton:checked:hover {{ background: {t.success_hover}; }}
        QPushButton[iconOnly="true"] {{ padding: 0; font-size: 17px; font-weight: bold; }}

        /* Acciones destructivas */
        QPushButton[danger="true"] {{ background: {t.danger}; color: {t.text_on_accent};
                                       border: 1px solid {t.danger_hover}; font-weight: bold; }}
        QPushButton[danger="true"]:hover  {{ background: {t.danger_hover}; }}
        QPushButton[danger="true"]:pressed{{ background: {t.danger_hover}; }}

        /* ── Checkboxes / radios ── */
        QCheckBox, QRadioButton {{ background: transparent; color: {t.text};
                                    spacing: 10px; padding: 4px 0; }}
        QCheckBox:disabled, QRadioButton:disabled {{ color: {t.text_disabled}; }}
        QCheckBox::indicator, QRadioButton::indicator {{ width: 20px; height: 20px; }}
        QCheckBox::indicator {{ border: 2px solid {t.border}; border-radius: 4px; background: {t.input_bg}; }}
        QCheckBox::indicator:hover {{ border: 2px solid {t.focus}; }}
        QCheckBox::indicator:checked {{ background: {t.accent}; border: 2px solid {t.focus}; }}
        QCheckBox::indicator:checked:hover {{ background: {t.accent_hover}; }}
        QCheckBox::indicator:disabled {{ border: 2px solid {t.border_soft}; background: {t.surface_alt}; }}
        QCheckBox::indicator:checked:disabled {{ background: {t.accent_pressed}; border: 2px solid {t.border}; }}
        QRadioButton::indicator {{ border: 2px solid {t.border}; border-radius: 11px; background: {t.input_bg}; }}
        QRadioButton::indicator:hover {{ border: 2px solid {t.focus}; }}
        QRadioButton::indicator:checked {{ background: {t.accent}; border: 5px solid {t.input_bg}; }}
        QRadioButton::indicator:disabled {{ border: 2px solid {t.border_soft}; }}

        QListWidget::indicator, QTreeWidget::indicator, QTableWidget::indicator {{
            width: 20px; height: 20px; border: 2px solid {t.border};
            border-radius: 4px; background: {t.input_bg};
        }}
        QListWidget::indicator:checked, QTreeWidget::indicator:checked,
        QTableWidget::indicator:checked {{ background: {t.accent}; border: 2px solid {t.focus}; }}

        /* ── Listas / tablas ── */
        QListWidget::item, QTreeWidget::item {{ padding: 7px 6px; border-radius: 3px; }}
        QListWidget::item:hover, QTreeWidget::item:hover {{ background: {t.hover}; }}
        QListWidget::item:selected, QTreeWidget::item:selected {{ background: {t.accent}; color: {t.text_on_accent}; }}
        QTableWidget {{ gridline-color: {t.border}; }}
        QTableWidget::item {{ padding: 5px; }}
        QTableWidget::item:selected {{ background: {t.accent}; color: {t.text_on_accent}; }}
        QHeaderView::section {{ background: {t.surface_alt}; color: {t.text}; border: none;
                                 border-right: 1px solid {t.border};
                                 border-bottom: 1px solid {t.border};
                                 padding: 7px 6px; font-weight: bold; }}

        /* ── Pestañas ── */
        QTabWidget::pane {{ background: {t.window}; border: 1px solid {t.border}; border-radius: 4px; }}
        QTabBar::tab {{ background: {t.surface_alt}; color: {t.text}; padding: 8px 14px;
                        border: 1px solid {t.border}; border-bottom: none;
                        border-top-left-radius: 4px; border-top-right-radius: 4px; }}
        QTabBar::tab:hover {{ background: {t.hover}; }}
        QTabBar::tab:selected {{ background: {t.accent}; color: {t.text_on_accent}; }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{ background: {t.scrollbar_track}; width: 15px; margin: 0; border: none; }}
        QScrollBar::handle:vertical {{ background: {t.scrollbar_thumb}; min-height: 34px;
                                        border-radius: 7px; margin: 2px; }}
        QScrollBar::handle:vertical:hover {{ background: {t.scrollbar_thumb_hover}; }}
        QScrollBar:horizontal {{ background: {t.scrollbar_track}; height: 15px; margin: 0; border: none; }}
        QScrollBar::handle:horizontal {{ background: {t.scrollbar_thumb}; min-width: 34px;
                                          border-radius: 7px; margin: 2px; }}
        QScrollBar::handle:horizontal:hover {{ background: {t.scrollbar_thumb_hover}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; background: none; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

        /* ── Spinbox: botones +/− visibles ── */
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border; width: 20px;
            background: {t.surface_alt}; border: 1px solid {t.border};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-position: top right; border-top-right-radius: 3px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-position: bottom right; border-bottom-right-radius: 3px;
        }}
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
            background: {t.hover};
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url({ad}/plus.svg); width: 10px; height: 10px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url({ad}/minus.svg); width: 10px; height: 10px;
        }}
        QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {{
            image: url({ad}/plus_dis.svg);
        }}
        QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
            image: url({ad}/minus_dis.svg);
        }}

        /* ── Spinbox dentro de tablas ── */
        QTableWidget QDoubleSpinBox, QTableWidget QSpinBox {{
            padding: 2px 6px; min-height: 0; border-radius: 3px;
        }}
        QTableWidget QLabel {{ padding: 2px 6px; }}

        /* ── Docks ── */
        QDockWidget {{ color: {t.text}; font-weight: bold; }}
        QDockWidget::title {{ background: {t.surface_alt}; padding: 8px 10px;
                               border-bottom: 1px solid {t.border}; }}
        QSplitter::handle {{ background: {t.border}; }}
        QSplitter::handle:horizontal {{ width: 5px; }}
        QSplitter::handle:vertical {{ height: 5px; }}
    """


# ── Aplicación del tema ────────────────────────────────────────────────────
def apply_theme(app: QtWidgets.QApplication, name: ThemeName) -> Theme:
    """Aplica paleta + stylesheet globales y persiste la preferencia.
    Emite THEME_BUS.changed(name) al final para que los QSS custom recompongan."""
    global _current
    t = LIGHT if name == "light" else DARK
    _current = t
    app.setStyle("Fusion")
    app.setPalette(_palette_light() if name == "light" else _palette_dark())
    app.setStyleSheet(build_stylesheet(t))
    save_preference(name)
    THEME_BUS.changed.emit(name)
    return t


def toggle(app: QtWidgets.QApplication) -> ThemeName:
    """Alterna claro↔oscuro. Devuelve el nombre del tema recién aplicado."""
    new = "light" if _current.name == "dark" else "dark"
    apply_theme(app, new)
    return new
