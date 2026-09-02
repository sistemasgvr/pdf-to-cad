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
from model import ACI_RGB

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
BTN_ON = "background:#2e9e4f;color:white;font-weight:bold;padding:8px;border-radius:4px;"
BTN_OFF = "background:#3c5a99;color:white;padding:8px;border-radius:4px;"


def aci_qcolor(a): return QtGui.QColor(*ACI_RGB.get(a, (235, 235, 235)))
def layer_qcolor(l): return aci_qcolor(C.OUTPUT_LAYERS.get(l, 7))


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
