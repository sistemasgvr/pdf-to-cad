"""Constantes del dibujo del perfil longitudinal (las comparten `perfil_vista` y sus mezclas)."""
from __future__ import annotations

PX_POR_PULGADA = 96.0      # respaldo: 1 in de ploteo en pantalla si el widget no da sus ppp (`VistaPerfil._ppp`)
M_IZQ, M_DER, M_ARR, M_ABA = 70, 70, 10, 72      # márgenes del marco (px): cotas, estaciones y título
LETRA_PT = 8
HUECO = 6
RADIO_NODO = 5
VALVULA_MIN_PX = 10.0       # el moño de una válvula nunca más chico que esto en pantalla
CAJA_PX_MIN = 3.0          # media anchura mínima de la caja de la válvula en pantalla
ATRAPAR_PX = 9
