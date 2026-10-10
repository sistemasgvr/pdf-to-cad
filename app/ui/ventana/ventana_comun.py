"""Nombres compartidos por app_window.py y sus clases mezcla (ventana_*.py).

Las MISMAS importaciones que app_window.py: los métodos movidos a ventana_*.py
ven exactamente los mismos nombres que veían en app_window.
"""
import sys, os, copy, math, json, zipfile
import fitz
import numpy as np
import ezdxf
from PySide6 import QtCore, QtGui, QtWidgets

import config as C
import vector_pipeline as VP
import geometry as G
from exportar import dxf_export
from geo import georef as georef_mod
from geometry import qimage_to_gray
from nucleo import model_ops
# Clases de UI extraídas a módulos propios (mismo comportamiento, ver plan de
# arquitectura). El lienzo, los widgets reutilizables y el worker de fondo.
from ui.comun.canvas import Canvas
from ui.comun.widgets import InlineEdit, _SegInvSpinBox, _NoWheelFilter
from ui.comun import busy as _busy_mod
from ui.comun.workers import PipelineWorker, RecognitionWorker, OrganizedRecognitionWorker
from ui.dialogos import dialogs
from ui.asistente import recognition_dialog
from ui.asistente import sheet_layout_dialog
from ui.asistente import organized_layer_dialog
from ui.asistente import organized_recognition_dialog
from hoja.organized_layers import selected_sheets
from hoja.sheet_layout import normalize as normalize_sheet_layout, normalize_rotations
from hoja.sheet_crops import normalize as normalize_sheet_crops
from ui.asistente import layer_dialog
from reconocimiento import recognition as _recognition
from reconocimiento import recognition_cache
from ui.ventana import respaldo_editor
from hoja import composite as composite_mod
from ui.asistente import composite_dialog
import project_io
from nucleo import model_ops
from nucleo import quiebres_curvas
from ui.comun.responsive import WrapButton, WrapCheckBox, ResponsiveGroupBox, GridAdaptable  # noqa: E402
from ui.comun import side_panels  # noqa: E402
from ui.ventana import autoguardado  # noqa: E402
from nucleo import normas_catalogo, normas_validar
from nucleo.model import (VERSION, TIPOS, ACI_RGB, LEADER_TEXT_FT, LEADER_ORIENT,
                   Z_PDF, Z_ERASE, Z_MARK, Z_HANDLE, GRAVITY_LAYERS,
                   TAB_PIPE, TAB_LEADER, TAB_TEXT, TAB_REGION, TAB_BZ, TAB_CURVE, TAB_CL,
                   TAB_DB,
                   WORK_UNITS, DEFAULT_WORK_UNIT, CHANGELOG,
                   PIPE_DIAMETERS_IN, PIPE_MATERIALS, DEFAULT_PIPE_MATERIAL, NETWORK_KIND)

# Constantes y helpers de UI compartidos (antes definidos aquí) → ui_common.py.
from ui.comun.ui_common import (DOWNLOADS, btn_on_style, btn_off_style, aci_qcolor, layer_qcolor,
                       _extract_diam_from_size, swatch_icon, tooltip_bloque)
from ui.comun import theme as _theme
from traduccion import i18n as _i18n
from traduccion.i18n import t as _tr, bind as _bind, bind_item as _bind_item, N_
from ui.comun.icons import icon as _icon

# Cuánto más cerca tiene que estar el tramo que un vértice para ganarle en el
# snap suave (ver `_pipe_soft_snap`). Junto a un vértice, la perpendicular a un
# segmento oblicuo cae un pelo más cerca; sin este margen el punto se deslizaba
# sobre el tramo y las utilidades no empalmaban en el vértice.
PRIORIDAD_VERTICE = 0.55

__all__ = [n for n in dir() if not n.startswith("__")]
