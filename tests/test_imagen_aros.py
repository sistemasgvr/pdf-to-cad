"""Buzones de aro fino con letra en la imagen de la red (`hoja/imagen_aros`, sin Qt).

Reporte del usuario (2026-11-19, Phoenix «QS SD_Indian School»): el buzón «M» de aro fino no salía como buzón; el aro
es casi todo antialias claro y en la máscara del azul solo quedaban las patitas de la letra (dos rayitas sueltas).
"""
import cv2
import numpy as np

from hoja import imagen_aros as IA
from hoja import imagen_trazos as IT

AZUL = (0, 77, 168)
CLARO = (150, 175, 215)        # el aro: antialias del azul, no el azul
ESC = 4.17                     # px/pt de los mapas de Phoenix


def _hoja(con_letra=True, relleno=False):
    img = np.full((200, 300, 3), 255, np.uint8)
    cx, cy, r = 150, 100, 21
    cv2.rectangle(img, (0, 93), (cx - r - 1, 107), AZUL, -1)            # la tubería, cortada en el aro
    cv2.rectangle(img, (cx + r + 1, 93), (299, 107), AZUL, -1)
    if relleno:
        cv2.circle(img, (cx, cy), r, AZUL, -1)
    else:
        cv2.circle(img, (cx, cy), r, CLARO, 1, cv2.LINE_AA)
    if con_letra:                                                       # las patitas de la «M»
        cv2.line(img, (cx - 8, cy - 12), (cx - 8, cy + 12), AZUL, 2)
        cv2.line(img, (cx + 8, cy - 12), (cx + 8, cy + 12), AZUL, 2)
    nucleo = np.all(img == AZUL, axis=2)
    tinta = nucleo | (img.min(axis=2) < 235) & (img[:, :, 2] > img[:, :, 0])
    return img, tinta, nucleo


def test_aro_fino_con_letra_es_un_buzon():
    img, tinta, nucleo = _hoja()
    aros = IA.aros(img, tinta, nucleo, ESC)
    assert len(aros) == 1
    cx, cy, r = aros[0]
    assert abs(cx - 150) <= 1 and abs(cy - 100) <= 1 and abs(r - 21) <= 1.5


def test_sin_letra_o_macizo_no_es_un_aro_con_letra():
    for kw in ({"con_letra": False}, {"relleno": True}):
        img, tinta, nucleo = _hoja(**kw)
        assert IA.aros(img, tinta, nucleo, ESC) == []


def test_las_patitas_de_la_letra_dejan_de_ser_lineas():
    img, tinta, nucleo = _hoja()
    p = IT.trazos(nucleo, ESC)
    IA.sumar(p, IA.aros(img, tinta, nucleo, ESC), ESC)
    assert any(abs(s.cx - 150) <= 1.5 and abs(s.cy - 100) <= 1.5 for s in p.simbolos)
    assert not any(all(abs(x - 150) < 21 and abs(y - 100) < 21 for x, y in pts) for pts in p.lineas)
    assert len(p.lineas) == len(p.grosores)
