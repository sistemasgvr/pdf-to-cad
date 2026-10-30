"""theme.py — Tema visual global (claro / oscuro) para toda la app.

Uso:
    from ui.comun.theme import apply_theme, tokens, THEME_BUS

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

    # Botones de color del compositor (pedido del usuario 2026-09-30: «Hoja
    # completa», «Opciones», «Uniones» se confundían con el fondo):
    # acción secundaria destacada = tinte del acento; botón con menú = violeta.
    soft: str
    soft_hover: str
    soft_text: str
    options: str
    options_hover: str
    options_border: str
    options_text: str

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

    # 2.0.0 (rediseño): tercer nivel de texto, estados con fondo suave y sombra de lo flotante
    text3: str
    warning: str
    warning_soft: str
    success_soft: str
    danger_soft: str
    shadow: str

    @property
    def accent_soft(self) -> str:      # fondo de fichas / seleccionado
        return self.soft

    @property
    def accent_text(self) -> str:      # texto sobre accent_soft
        return self.soft_text


# Tema oscuro (2.0.0, rediseño): superficies neutras casi negras, UN acento índigo,
# texto en tres niveles y estados con fondo suave. Mismos NOMBRES de tokens que antes.
DARK = Theme(
    name="dark",
    window="#0f1115", surface="#16191f", surface_alt="#1d2129",
    header="#262b35", input_bg="#16191f",
    text="#eceef2", text_muted="#a6adbb", text_on_accent="#ffffff",
    text_disabled="#5f6776",
    text_info="#b4c0ff",

    accent="#4f6bed", accent_hover="#6b84ff", accent_pressed="#3f59d6",
    danger="#d9363e", danger_hover="#e5484d",
    focus="#6b84ff",
    success="#1a8a4c", success_hover="#21a05a",
    soft="#1d2342", soft_hover="#262e57", soft_text="#b4c0ff",
    options="#1d2129", options_hover="#262b35", options_border="#353b47", options_text="#eceef2",
    border="#353b47", border_soft="#262b35",
    hover="#252a34",
    grid_bg="#101318", grid_line_minor="#1a1e25", grid_line_major="#2a303b",
    envelope_fill="#26304d", envelope_border="#6b84ff",
    conduit_fill="#e5eaf3", conduit_border="#f0f0f0", conduit_text="#1e2531",
    selection="#f0a020", invalid="#f97066",
    menu_bg="#1d2129", menu_hover="#252a34",
    scrollbar_track="#0f1115", scrollbar_thumb="#353b47", scrollbar_thumb_hover="#4a5263",
    text3="#7a8291", warning="#fdb022", warning_soft="#2e2208",
    success_soft="#0f2a1e", danger_soft="#2f1412", shadow="#00000080",
)

# Tema claro (2.0.0): blanco y grises fríos, el mismo acento índigo.
LIGHT = Theme(
    name="light",
    window="#f6f7f9", surface="#ffffff", surface_alt="#f1f3f6",
    header="#1f2633", input_bg="#ffffff",
    text="#101828", text_muted="#475467", text_on_accent="#ffffff",
    text_disabled="#98a2b3",
    text_info="#2f45c7",

    accent="#4361ee", accent_hover="#3651d4", accent_pressed="#2f45c7",
    danger="#b42318", danger_hover="#912018",
    focus="#4361ee",
    success="#067647", success_hover="#05603a",
    soft="#eef1ff", soft_hover="#e0e6ff", soft_text="#2f45c7",
    options="#ffffff", options_hover="#f1f3f6", options_border="#d0d5dd", options_text="#344054",
    border="#d0d5dd", border_soft="#e4e7ec",
    hover="#f1f3f6",
    grid_bg="#fbfbfc", grid_line_minor="#eceef2", grid_line_major="#d0d5dd",
    envelope_fill="#eef1ff", envelope_border="#4361ee",
    conduit_fill="#ffffff", conduit_border="#1e2531", conduit_text="#1e2531",
    selection="#e56b17", invalid="#b42318",
    menu_bg="#ffffff", menu_hover="#f1f3f6",
    scrollbar_track="#f6f7f9", scrollbar_thumb="#d0d5dd", scrollbar_thumb_hover="#98a2b3",
    text3="#6b7485", warning="#b54708", warning_soft="#fffaeb",
    success_soft="#ecfdf3", danger_soft="#fef3f2", shadow="#1018281f",
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


# ── Paletas Qt (de los tokens: lo que no pinta la hoja de estilo usa estos colores) ──
def _palette(t: Theme) -> QtGui.QPalette:
    c = QtGui.QColor
    p = QtGui.QPalette()
    for rol, col in ((QtGui.QPalette.Window, t.window), (QtGui.QPalette.WindowText, t.text),
                     (QtGui.QPalette.Base, t.input_bg), (QtGui.QPalette.AlternateBase, t.surface_alt),
                     (QtGui.QPalette.ToolTipBase, t.header), (QtGui.QPalette.ToolTipText, "#ffffff"),
                     (QtGui.QPalette.Text, t.text), (QtGui.QPalette.Button, t.surface),
                     (QtGui.QPalette.ButtonText, t.text), (QtGui.QPalette.BrightText, t.danger),
                     (QtGui.QPalette.Highlight, t.accent), (QtGui.QPalette.HighlightedText, t.text_on_accent),
                     (QtGui.QPalette.PlaceholderText, t.text3), (QtGui.QPalette.Link, t.text_info),
                     (QtGui.QPalette.Light, t.surface), (QtGui.QPalette.Midlight, t.surface_alt),
                     (QtGui.QPalette.Dark, t.border), (QtGui.QPalette.Mid, t.border_soft),
                     (QtGui.QPalette.Shadow, t.header)):
        p.setColor(rol, c(col))
    for rol in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText, QtGui.QPalette.WindowText):
        p.setColor(QtGui.QPalette.Disabled, rol, c(t.text_disabled))
    return p


def _palette_dark() -> QtGui.QPalette:
    return _palette(DARK)


def _palette_light() -> QtGui.QPalette:
    return _palette(LIGHT)


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


def _menu_chevron(t: Theme) -> str:
    """«▾» de los botones con menú (tono options), con el color del tema. Un
    archivo por tema: Qt guarda en caché la imagen de cada url()."""
    arrow_dir = _spinbox_arrow_dir(t.text, t.text_disabled)
    name = f"chevron_options_{t.name}.svg"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
           '<polyline points="2.5,4.5 6,8 9.5,4.5" fill="none" stroke="{c}" stroke-width="1.8" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>').format(c=t.options_text)
    with open(os.path.join(_arrow_dir, name), "w", encoding="utf-8") as f:
        f.write(svg)
    return f"{arrow_dir}/{name}"


def _svg(t: Theme, nombre: str, cuerpo: str, color: str) -> str:
    """Un SVG de 12×12 teñido para la hoja de estilo (un archivo por tema: Qt cachea cada url())."""
    _spinbox_arrow_dir(t.text, t.text_disabled)
    ruta = os.path.join(_arrow_dir, f"{nombre}_{t.name}.svg")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">' + cuerpo.format(c=color) + "</svg>")
    return ruta.replace("\\", "/")


# ── Stylesheet global ──────────────────────────────────────────────────────
def build_stylesheet(t: Theme) -> str:
    """CSS global de QApplication, formateado con los tokens del tema `t`.

    Cubre el 90% de los widgets automáticamente. Componentes con estilos
    manuales (btn_export, header de diálogos, etc.) deben leer `tokens()` y
    re-aplicar cuando llegue `THEME_BUS.changed`."""
    ad = _spinbox_arrow_dir(t.text, t.text_disabled)
    chevron = _menu_chevron(t)
    chevron_combo = _svg(t, "chevron_combo", '<polyline points="2.5,4.5 6,8 9.5,4.5" fill="none" stroke="{c}" '
                         'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>', t.text3)
    check = _svg(t, "check", '<polyline points="2.5,6.2 5,8.6 9.6,3.6" fill="none" stroke="{c}" '
                 'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>', t.text_on_accent)
    # «»» de una barra que no cabe (2026-10-28): la flecha de Qt es gris oscuro fijo y no se veía en tema oscuro
    _doble = ('<polyline points="{p1}" fill="none" stroke="{{c}}" stroke-width="1.6" stroke-linecap="round" '
              'stroke-linejoin="round"/><polyline points="{p2}" fill="none" stroke="{{c}}" stroke-width="1.6" '
              'stroke-linecap="round" stroke-linejoin="round"/>')
    ext_h = _svg(t, "toolbar_ext_h", _doble.format(p1="2.5,3 5.5,6 2.5,9", p2="6.5,3 9.5,6 6.5,9"), t.text_muted)
    ext_v = _svg(t, "toolbar_ext_v", _doble.format(p1="3,2.5 6,5.5 9,2.5", p2="3,6.5 6,9.5 9,6.5"), t.text_muted)
    return f"""
        /* ═══════════════════════════════════════════════════════════════════
           Tema {t.name} — generado desde ui/comun/theme.py (2.0.0, rediseño).
           Lenguaje: botones NEUTROS (la acción principal de cada pantalla lleva
           el acento: botón por defecto de un diálogo o kind="primary"), esquinas
           de 8–12 px, bordes suaves, texto en tres niveles.
           REGLA: si estilas un ::indicator (checkbox/radio), estila TODOS los
           estados o Fusion se lo pierde y desaparece la marca de check.
           ═══════════════════════════════════════════════════════════════════ */

        /* ── Base ── */
        QWidget {{ background-color: {t.window}; color: {t.text}; font-size: 14px;
                   font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; }}
        QToolTip {{ background-color: {t.header}; color: #ffffff; border: none;
                    padding: 6px 9px; border-radius: 6px; font-size: 13px; }}
        QLabel {{ background: transparent; }}
        QLabel[rol="h1"] {{ font-size: 20px; font-weight: 600; }}
        QLabel[rol="h2"] {{ font-size: 16px; font-weight: 600; }}
        QLabel[rol="h3"] {{ font-weight: 600; }}
        QLabel[rol="sec"] {{ font-size: 11px; font-weight: 600; color: {t.text3}; letter-spacing: 0.6px; }}
        QLabel[rol="t2"] {{ color: {t.text_muted}; }}
        QLabel[rol="t3"] {{ color: {t.text3}; font-size: 12px; }}
        QLabel[rol="mono"] {{ font-family: "Cascadia Mono", Consolas, monospace; color: {t.text_muted}; font-size: 12px; }}

        /* ── Contenedores ── */
        QScrollArea, QAbstractScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QGroupBox {{ background: transparent; border: none; border-top: 1px solid {t.border_soft};
                     margin-top: 18px; padding-top: 12px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                            left: 0px; padding: 0 0 0 0; color: {t.text3}; font-size: 12px;
                            font-weight: 600; letter-spacing: 0.5px; }}
        QFrame#tarjeta {{ background: {t.surface}; border: 1px solid {t.border_soft}; border-radius: 12px; }}
        QFrame#tarjetaSuave {{ background: {t.surface_alt}; border: none; border-radius: 12px; }}
        QFrame#flotante {{ background: {t.surface}; border: 1px solid {t.border_soft}; border-radius: 12px; }}
        QFrame#ia {{ background: {t.soft}; border: none; border-radius: 12px; }}
        QFrame#sep {{ background: {t.border_soft}; max-height: 1px; min-height: 1px; border: none; }}
        QFrame#sepV {{ background: {t.border_soft}; max-width: 1px; min-width: 1px; border: none; }}
        QWidget#panel {{ background: {t.surface}; }}
        QWidget#barraSuperior {{ background: {t.surface}; border-bottom: 1px solid {t.border_soft}; }}
        QWidget#riel {{ background: {t.surface}; border-right: 1px solid {t.border_soft}; }}

        /* ── Acordeón de Herramientas (secciones plegables) ── */
        QToolBox {{ background: transparent; }}
        QToolBox::tab {{ background: transparent; color: {t.text_muted}; border: none;
                         border-radius: 8px; padding-left: 8px; min-height: 34px; font-weight: 600; }}
        QToolBox::tab:hover {{ background: {t.hover}; color: {t.text}; }}
        QToolBox::tab:selected {{ background: {t.soft}; color: {t.soft_text}; }}

        /* ── Menús ── */
        QMenu {{ background: {t.menu_bg}; color: {t.text}; border: 1px solid {t.border_soft};
                 border-radius: 10px; padding: 6px; }}
        QMenu::item {{ padding: 7px 30px 7px 12px; border-radius: 6px; background: transparent; }}
        QMenu::item:selected {{ background: {t.hover}; color: {t.text}; }}
        QMenu::item:disabled {{ color: {t.text_disabled}; }}
        QMenu::separator {{ height: 1px; background: {t.border_soft}; margin: 5px 8px; }}
        QMenu::icon {{ padding-left: 8px; }}
        QMenuBar {{ background: {t.surface}; color: {t.text}; }}
        QMenuBar::item {{ padding: 6px 11px; border-radius: 6px; }}
        QMenuBar::item:selected {{ background: {t.hover}; color: {t.text}; }}
        QStatusBar {{ background: {t.surface}; color: {t.text3}; border-top: 1px solid {t.border_soft}; }}
        QStatusBar QLabel {{ color: {t.text3}; font-size: 12px; padding: 0 6px; }}
        QStatusBar::item {{ border: none; }}

        /* ── Campos de entrada ── */
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit,
        QListWidget, QTreeWidget, QTableWidget, QFontComboBox, QAbstractItemView {{
            background: {t.input_bg}; color: {t.text}; border: 1px solid {t.border};
            border-radius: 8px; selection-background-color: {t.accent};
            selection-color: {t.text_on_accent};
        }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {{
            padding: 6px 10px; min-height: 22px;
        }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
        QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {t.focus}; }}
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
            background: {t.surface_alt}; color: {t.text_disabled}; border: 1px solid {t.border_soft};
        }}
        QLineEdit[kind="buscar"] {{ background: {t.surface_alt}; border: 1px solid transparent; padding-left: 32px; }}
        QLineEdit[kind="buscar"]:focus {{ background: {t.input_bg}; border: 1px solid {t.focus}; }}
        QComboBox::drop-down {{ border: none; width: 26px; }}
        QComboBox::down-arrow {{ image: url({chevron_combo}); width: 12px; height: 12px; }}
        QComboBox QAbstractItemView {{ background: {t.menu_bg}; color: {t.text};
                                        border: 1px solid {t.border_soft}; border-radius: 8px; padding: 4px;
                                        selection-background-color: {t.soft};
                                        selection-color: {t.soft_text}; outline: none; }}
        QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 4px 8px; border-radius: 6px; }}

        /* ── Botones: NEUTROS por defecto ── */
        QPushButton {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
                        padding: 7px 14px; border-radius: 8px; font-weight: 500; min-height: 20px; }}
        QPushButton:hover {{ background: {t.hover}; }}
        QPushButton:pressed {{ background: {t.border_soft}; }}
        QPushButton:disabled {{ background: {t.surface_alt}; color: {t.text_disabled}; border: 1px solid {t.border_soft}; }}
        /* la acción principal: botón por defecto de un diálogo o kind="primary" */
        QPushButton:default, QPushButton[kind="primary"] {{ background: {t.accent}; color: {t.text_on_accent};
                        border: 1px solid {t.accent}; font-weight: 600; }}
        QPushButton:default:hover, QPushButton[kind="primary"]:hover {{ background: {t.accent_hover};
                        border: 1px solid {t.accent_hover}; }}
        QPushButton:default:pressed, QPushButton[kind="primary"]:pressed {{ background: {t.accent_pressed}; }}
        QPushButton[kind="primary"]:disabled {{ background: {t.surface_alt}; color: {t.text_disabled};
                        border: 1px solid {t.border_soft}; }}
        QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {t.text_muted}; }}
        QPushButton[kind="ghost"]:hover {{ background: {t.hover}; color: {t.text}; }}
        QPushButton[kind="chip"] {{ background: {t.surface}; border: 1px solid {t.border_soft}; border-radius: 13px;
                                    padding: 4px 11px; color: {t.text_muted}; font-weight: 400; min-height: 16px; }}
        QPushButton[kind="chip"]:hover {{ border: 1px solid {t.border}; color: {t.text}; }}
        QPushButton[kind="chip"]:checked {{ background: {t.soft}; border: 1px solid {t.soft};
                                            color: {t.soft_text}; font-weight: 500; }}
        QPushButton[kind="seg"] {{ background: transparent; border: none; border-radius: 6px; padding: 5px 12px;
                                   color: {t.text_muted}; min-height: 18px; }}
        QPushButton[kind="seg"]:checked {{ background: {t.surface}; color: {t.text}; font-weight: 600; }}
        QFrame#segmentado {{ background: {t.surface_alt}; border-radius: 8px; }}
        /* conmutables (modo activo, «Dibujar utilidad»…): tinte del acento, inequívoco */
        QPushButton:checked {{ background: {t.soft}; border: 1px solid {t.accent}; color: {t.soft_text};
                                font-weight: 600; }}
        QPushButton:checked:hover {{ background: {t.soft_hover}; }}
        QPushButton[iconOnly="true"] {{ padding: 0; font-size: 17px; font-weight: 600; }}
        /* Botones de herramienta conmutables (compositor): activo = acento lleno */
        QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px; }}
        QToolButton:hover {{ background: {t.hover}; }}
        QToolButton:checked {{ background: {t.soft}; color: {t.soft_text}; }}
        QToolButton[kind="rail"] {{ padding: 9px; border-radius: 10px; }}
        QToolButton[kind="rail"]:checked {{ background: {t.soft}; }}
        QToolBarExtension {{ qproperty-icon: url({ext_h}); }}
        QToolBar#riel QToolBarExtension {{ qproperty-icon: url({ext_v}); }}
        QToolButton[toggleTool="true"] {{ background: {t.surface}; color: {t.text};
                                          border: 1px solid {t.border}; border-radius: 8px; padding: 4px 9px; }}
        QToolButton[toggleTool="true"]:hover {{ background: {t.hover}; }}
        QToolButton[toggleTool="true"]:checked {{ background: {t.accent}; color: {t.text_on_accent};
                                                  border: 1px solid {t.accent}; font-weight: 600; }}
        QToolButton[toggleTool="true"]:checked:hover {{ background: {t.accent_hover}; }}
        /* …con menú de opciones a la derecha (botón dividido «Regla ▾») */
        QToolButton[toggleTool="true"][popupMode="1"] {{ padding-right: 32px; }}
        QToolButton[toggleTool="true"]::menu-button {{ background: transparent;
            border-left: 1px solid {t.border}; width: 26px;
            border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
        QToolButton[toggleTool="true"]::menu-button:hover {{ background: {t.hover}; }}
        QToolButton[toggleTool="true"]::menu-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}

        /* Acciones secundarias (junto a una primaria): neutras */
        QPushButton[secondary="true"] {{ background: {t.surface}; color: {t.text};
                                          border: 1px solid {t.border}; font-weight: 500; }}
        QPushButton[secondary="true"]:hover {{ background: {t.hover}; }}
        QPushButton[secondary="true"]:pressed {{ background: {t.border_soft}; }}
        QPushButton[secondary="true"]:disabled {{ background: {t.surface_alt}; color: {t.text_disabled};
                                                   border: 1px solid {t.border_soft}; }}

        /* Acción secundaria destacada (tinte del acento: «Hoja completa») y botones
           con menú de opciones («Opciones», «Uniones», «Ajustes»): neutros con ▾ */
        QPushButton[soft="true"] {{ background: {t.soft}; color: {t.soft_text}; border: 1px solid transparent; }}
        QPushButton[soft="true"]:hover {{ background: {t.soft_hover}; border: 1px solid {t.accent}; }}
        QPushButton[soft="true"]:pressed {{ background: {t.soft}; }}
        QPushButton[options="true"] {{ background: {t.options}; color: {t.options_text};
                                        border: 1px solid {t.options_border}; padding-right: 30px; }}
        QPushButton[options="true"]:hover, QPushButton[options="true"]:open {{
            background: {t.options_hover}; border: 1px solid {t.options_border}; }}
        QPushButton[options="true"]::menu-indicator {{ image: url({chevron}); width: 12px; height: 12px;
            subcontrol-origin: padding; subcontrol-position: center right; right: 10px; }}
        QPushButton[soft="true"]:disabled, QPushButton[options="true"]:disabled {{
            background: {t.surface_alt}; color: {t.text_disabled}; border: 1px solid {t.border_soft}; }}

        /* Acción de consulta («Ver datos extendidos»): verde suave */
        QPushButton[success="true"] {{ background: {t.success_soft}; color: {t.success};
                                        border: 1px solid transparent; font-weight: 600; }}
        QPushButton[success="true"]:hover  {{ border: 1px solid {t.success}; }}
        QPushButton[success="true"]:pressed{{ background: {t.success_soft}; }}

        /* Acciones destructivas: rojo suave; lleno solo al pasar el ratón */
        QPushButton[danger="true"] {{ background: {t.danger_soft}; color: {t.danger};
                                       border: 1px solid transparent; font-weight: 600; }}
        QPushButton[danger="true"]:hover  {{ background: {t.danger}; color: {t.text_on_accent}; }}
        QPushButton[danger="true"]:pressed{{ background: {t.danger_hover}; color: {t.text_on_accent}; }}

        /* ── Checkboxes / radios ── */
        QCheckBox, QRadioButton {{ background: transparent; color: {t.text};
                                    spacing: 10px; padding: 4px 0; }}
        QCheckBox:disabled, QRadioButton:disabled {{ color: {t.text_disabled}; }}
        QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; }}
        QCheckBox::indicator {{ border: 1px solid {t.border}; border-radius: 5px; background: {t.input_bg}; }}
        QCheckBox::indicator:hover {{ border: 1px solid {t.focus}; }}
        QCheckBox::indicator:checked {{ background: {t.accent}; border: 1px solid {t.accent};
                                         image: url({check}); }}
        QCheckBox::indicator:checked:hover {{ background: {t.accent_hover}; }}
        QCheckBox::indicator:indeterminate {{ background: {t.soft}; border: 1px solid {t.accent}; }}
        QCheckBox::indicator:disabled {{ border: 1px solid {t.border_soft}; background: {t.surface_alt}; }}
        QCheckBox::indicator:checked:disabled {{ background: {t.text_disabled}; border: 1px solid {t.border}; }}
        QRadioButton::indicator {{ border: 1px solid {t.border}; border-radius: 10px; background: {t.input_bg}; }}
        QRadioButton::indicator:hover {{ border: 1px solid {t.focus}; }}
        QRadioButton::indicator:checked {{ background: {t.accent}; border: 5px solid {t.input_bg};
                                            outline: none; }}
        QRadioButton::indicator:disabled {{ border: 1px solid {t.border_soft}; }}

        QListWidget::indicator, QTreeWidget::indicator, QTableWidget::indicator {{
            width: 18px; height: 18px; border: 1px solid {t.border};
            border-radius: 5px; background: {t.input_bg};
        }}
        QListWidget::indicator:checked, QTreeWidget::indicator:checked,
        QTableWidget::indicator:checked {{ background: {t.accent}; border: 1px solid {t.accent};
                                           image: url({check}); }}

        /* ── Listas / tablas ── */
        QListWidget, QTreeWidget {{ outline: none; }}
        QListWidget::item, QTreeWidget::item {{ padding: 7px 6px; border-radius: 6px; }}
        QListWidget::item:hover, QTreeWidget::item:hover {{ background: {t.hover}; }}
        QListWidget::item:selected, QTreeWidget::item:selected {{ background: {t.soft}; color: {t.text}; }}
        QTableWidget, QTableView {{ gridline-color: {t.border_soft}; alternate-background-color: {t.surface_alt}; }}
        QTableWidget::item {{ padding: 5px; }}
        QTableWidget::item:selected, QTableView::item:selected {{ background: {t.soft}; color: {t.text}; }}
        QHeaderView::section {{ background: {t.surface}; color: {t.text3}; border: none;
                                 border-bottom: 1px solid {t.border_soft};
                                 padding: 8px 8px; font-size: 12px; font-weight: 600; }}
        QTableCornerButton::section {{ background: {t.surface}; border: none; }}

        /* ── Pestañas (subrayado, sin cajas) ── */
        QTabWidget::pane {{ background: transparent; border: none; border-top: 1px solid {t.border_soft}; top: -1px; }}
        QTabBar {{ background: transparent; }}
        QTabBar::tab {{ background: transparent; color: {t.text_muted}; padding: 8px 12px;
                        border: none; border-bottom: 2px solid transparent; }}
        QTabBar::tab:hover {{ color: {t.text}; }}
        QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; font-weight: 600; }}

        /* ── Scrollbars finas ── */
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; border: none; }}
        QScrollBar::handle:vertical {{ background: {t.scrollbar_thumb}; min-height: 34px;
                                        border-radius: 3px; margin: 0 2px; }}
        QScrollBar::handle:vertical:hover {{ background: {t.scrollbar_thumb_hover}; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; border: none; }}
        QScrollBar::handle:horizontal {{ background: {t.scrollbar_thumb}; min-width: 34px;
                                          border-radius: 3px; margin: 2px 0; }}
        QScrollBar::handle:horizontal:hover {{ background: {t.scrollbar_thumb_hover}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; background: none; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
        /* Lienzo del plano: barras el TRIPLE de gruesas y del color del acento (pedido 2026-10-29: las
           finas no se distinguían sobre el plano). */
        QGraphicsView#lienzoPlano QScrollBar:vertical {{ width: 16px; margin: 2px; }}
        QGraphicsView#lienzoPlano QScrollBar:horizontal {{ height: 16px; margin: 2px; }}
        QGraphicsView#lienzoPlano QScrollBar::handle:vertical {{ background: {t.accent}; min-height: 48px;
                                        border-radius: 9px; margin: 0 4px; }}
        QGraphicsView#lienzoPlano QScrollBar::handle:horizontal {{ background: {t.accent}; min-width: 48px;
                                          border-radius: 9px; margin: 4px 0; }}
        QGraphicsView#lienzoPlano QScrollBar::handle:hover {{ background: {t.accent_hover}; }}
        QGraphicsView#lienzoPlano QAbstractScrollArea::corner, QGraphicsView#lienzoPlano::corner {{
            background: {t.scrollbar_track}; border: none; }}

        /* ── Spinbox: botones +/− visibles ── */
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border; width: 20px;
            background: transparent; border: none; border-left: 1px solid {t.border_soft};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-position: top right; border-top-right-radius: 8px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-position: bottom right; border-bottom-right-radius: 8px;
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
            padding: 2px 6px; min-height: 0; border-radius: 6px;
        }}
        QTableWidget QLabel {{ padding: 2px 6px; }}

        /* ── Deslizadores ── */
        QSlider::groove:horizontal {{ height: 4px; background: {t.border_soft}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: {"#ffffff" if t.name == "dark" else t.surface};
                                       border: 1px solid {t.border};
                                       width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }}
        QProgressBar {{ background: {t.surface_alt}; border: none; border-radius: 4px; text-align: center;
                        color: {t.text_muted}; min-height: 8px; }}
        QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}

        /* ── Docks y paneles laterales ── */
        QDockWidget {{ color: {t.text}; font-weight: 600; }}
        QDockWidget::title {{ background: {t.surface}; padding: 8px 10px;
                               border-bottom: 1px solid {t.border_soft}; }}
        QDockWidget > QWidget {{ background: {t.surface}; }}
        QMainWindow::separator {{ background: {t.border_soft}; width: 1px; height: 1px; }}
        QMainWindow::separator:hover {{ background: {t.accent}; width: 3px; height: 3px; }}
        /* Paneles laterales que se ocultan solos (side_panels.py): cabecera con chincheta
           y panel desplegado encima del plano */
        QWidget#panelHeader {{ background: {t.surface}; border-bottom: none; }}
        QLabel#panelHeaderTitle {{ background: transparent; color: {t.text}; font-size: 16px; font-weight: 600; }}
        QToolButton#panelPin {{ background: transparent; border: 1px solid transparent; border-radius: 8px; }}
        QToolButton#panelPin:hover {{ background: {t.hover}; }}
        QFrame#panelOverlay {{ background: {t.surface}; border: 1px solid {t.border_soft}; border-radius: 12px; }}
        QSplitter::handle {{ background: {t.border_soft}; }}
        QSplitter::handle:horizontal {{ width: 1px; }}
        QSplitter::handle:vertical {{ height: 1px; }}
        QSplitter::handle:hover {{ background: {t.accent}; }}
    """


# ── Aplicación del tema ────────────────────────────────────────────────────
def apply_theme(app: QtWidgets.QApplication, name: ThemeName) -> Theme:
    """Aplica paleta + stylesheet globales y persiste la preferencia.
    Emite THEME_BUS.changed(name) al final para que los QSS custom recompongan."""
    global _current
    t = LIGHT if name == "light" else DARK
    _current = t
    # Cambio al instante (pedido 2026-10-28): «Fusion» solo la primera vez (volver a ponerlo re-pule TODOS los
    # widgets) y las ventanas sin repintar hasta tener paleta + hoja + estilos propios: se pintan UNA vez.
    if getattr(app, "_pdfcad_fusion", None) is not app.style():
        app.setStyle("Fusion")
        app._pdfcad_fusion = app.style()
    ventanas = [w for w in app.topLevelWidgets() if w.isVisible() and w.updatesEnabled()]
    for w in ventanas:
        w.setUpdatesEnabled(False)
    try:
        app.setPalette(_palette_light() if name == "light" else _palette_dark())
        app.setStyleSheet(build_stylesheet(t))
        save_preference(name)
        THEME_BUS.changed.emit(name)
    finally:
        for w in ventanas:
            w.setUpdatesEnabled(True)
    return t


def toggle(app: QtWidgets.QApplication) -> ThemeName:
    """Alterna claro↔oscuro. Devuelve el nombre del tema recién aplicado."""
    new = "light" if _current.name == "dark" else "dark"
    apply_theme(app, new)
    return new
