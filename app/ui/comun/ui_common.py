"""ui_common.py — Constantes y helpers de UI compartidos.

Piezas de nivel módulo (sin estado, sin `self`) que usan varias partes de la app:
carpeta de descargas, estilos de botón on/off, colores por capa y un icono de
muestra (swatch). Antes vivían al inicio de app_window.py y `DOWNLOADS` estaba
duplicado en dialogs.py; centralizarlas aquí evita la duplicación y les da un
hogar para los módulos que se vayan extrayendo.
"""
import os

from PySide6 import QtCore, QtGui

import config as C
from nucleo.model import ACI_RGB

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")

def fila_lista(lista, texto="", icono=None):
    """Agrega una fila a un QListWidget y devuelve su ítem. Siempre así, nunca creando el ítem desde Python: esos
    ítems llevan un envoltorio de Shiboken que se destruye junto con el de C++, y ahí se cerraba la app (reporte
    2026-11-02, al importar; volcados: `QListWidget.clear` → `Object::destroy` → `releaseWrapper` con el envoltorio ya
    muerto). Creada por Qt, la fila no pasa por Shiboken al borrarse y además vaciar la lista es mucho más rápido.
    El ítem devuelto es un acceso temporal: no guardarlo más allá de la función que lo usa."""
    lista.addItem(texto)
    it = lista.item(lista.count() - 1)
    if icono is not None:
        it.setIcon(icono)
    return it


def filas_lista(lista, textos, iconos=None):
    """Agrega MUCHAS filas de una vez (2026-11-14, proyecto de 29 000 utilidades: fila por fila eran ~49 000
    inserciones, cada una avisando a la vista; juntas es una sola). `iconos` = uno por fila (None = sin icono).
    Las filas las crea Qt, como en `fila_lista`. Deja anotado que la lista quedó sin filas ocultas ni en gris
    (`_pdfcad_limpia`): quien las recorre para ocultar/atenuar puede saltarse el recorrido si no hay nada que hacer."""
    textos = list(textos)
    base = lista.count()
    lista.addItems(textos)
    if iconos is not None:
        item = lista.item
        for k, ic in enumerate(iconos):
            if ic is not None:
                item(base + k).setIcon(ic)
    if base == 0:
        lista._pdfcad_limpia = True
        lista._pdfcad_ocultas = lista._pdfcad_tenues = False
    return base


class GloboDeFila(QtCore.QObject):
    """El texto completo de la fila como globo, calculado AL PEDIRLO (antes se copiaba a cada fila al llenar la
    lista: decenas de miles de llamadas). Una fila con su propio globo lo conserva."""

    def __init__(self, lista):
        super().__init__(lista)
        self.lista = lista
        lista.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.ToolTip:
            it = self.lista.itemAt(ev.pos())
            if it is not None and not it.toolTip():
                from PySide6 import QtWidgets
                QtWidgets.QToolTip.showText(ev.globalPos(), it.text(), self.lista.viewport(),
                                            self.lista.visualItemRect(it))
                return True
        return False


ICON_SM = 18
ICON_MD = 22
ICON_LG = 28


# Estilos de botón on/off — recalculados desde el tema activo. Antes eran strings
# constantes (verdes/azules crudos) que no seguían el modo claro. Ahora son
# funciones que se llaman cada vez (baratas) para tomar el tema actual.
def btn_on_style() -> str:
    from ui.comun.theme import tokens
    t = tokens()
    # 2.0.0: la herramienta activa va con el acento lleno (inequívoco)
    return (f"background:{t.accent};color:{t.text_on_accent};border:1px solid {t.accent};"
            f"font-weight:600;padding:8px;border-radius:8px;")


def btn_off_style() -> str:
    from ui.comun.theme import tokens
    t = tokens()
    # 2.0.0: inactiva = botón neutro
    return (f"background:{t.surface};color:{t.text};border:1px solid {t.border};"
            f"padding:8px;border-radius:8px;")


def aci_qcolor(a): return QtGui.QColor(*ACI_RGB.get(a, (235, 235, 235)))
def layer_qcolor(l): return aci_qcolor(C.OUTPUT_LAYERS.get(l, 7))


# Colores del control de calidad que se pintan SOBRE la hoja (vista previa del
# reconocimiento). Ninguno es tono de utilidad (rojo, naranja, amarillo, verde,
# azul, blanco): «sin cubrir» era naranja, igual que telecom, y el violeta de
# «fuera de patrón» rozaba el azul del agua (pedido del usuario 2026-10-03).
# Además cada uno tiene su FORMA (línea gruesa, anillo, puntos): no solo color.
QA_UNCOVERED = "#ff2bd6"     # magenta: guion sin cubrir (línea gruesa) y bóveda sin línea (anillo)
QA_OFFPATTERN = "#16b8c9"    # turquesa a puntos: trazos fuera de patrón (leaders/flechas)


def _extract_diam_from_size(size_str):
    """Extrae el primer número de un tamaño del catálogo, p.ej. '24 in' → 24.0,
    '12 in x 8 in' → 12.0. Retorna 0.0 si no encuentra número."""
    import re as _re
    if not size_str: return 0.0
    m = _re.match(r"\s*(\d+(?:\.\d+)?)", str(size_str))
    return float(m.group(1)) if m else 0.0


def swatch_icon(color, size=14):
    pm = QtGui.QPixmap(size, size); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setBrush(color); p.setPen(QtGui.QPen(QtGui.QColor(70, 70, 70)))
    p.drawRect(0, 0, size - 1, size - 1); p.end(); return QtGui.QIcon(pm)


# Ancho del texto de los tooltips del lienzo (alertas y marcadores). Un mensaje
# largo en una sola línea cruzaba media pantalla; así sale en un bloque de
# ancho medio, casi cuadrado, y respeta los saltos de párrafo.
TOOLTIP_ANCHO_PX = 340


def tooltip_bloque(texto):
    """Texto de tooltip envuelto a `TOOLTIP_ANCHO_PX` (Qt solo ajusta el ancho
    de un tooltip si es texto enriquecido)."""
    import html as _html
    cuerpo = _html.escape(texto or "").replace("\n", "<br>")
    return f'<table width="{TOOLTIP_ANCHO_PX}"><tr><td>{cuerpo}</td></tr></table>'
