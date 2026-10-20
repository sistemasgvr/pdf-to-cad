"""leyenda_piezas.py — Hoja COMPUESTA de mapas: la MISMA tubería con otro estilo en cada pieza (PURO).

Reporte del usuario (2026-10-19, Water North + South de Phoenix, 10 mapas unidos): cada mapa del SIG
trae sus grosores (17-24 y 17-25 dibujan «Standard Main» a 0.57 pt, los demás a 0.71) y cada pieza
se escala a la hoja compuesta (North × 0.53): la MISMA red quedaba en tres capas por estilo (0.30,
0.37 y 0.38 pt) y, como cada capa se reconoce sola, la tubería se cortaba en cada costura.

La leyenda de CADA pieza (`leyenda_mapa_lectura`, `LeyendaMapa.por_hoja` + `piezas`) dice qué es cada
estilo en esa pieza: los estilos que en sus piezas son la misma fila de LÍNEA («Standard Main» de
«WATER INFRASTRUCTURE») se reconocen como UNA capa (`equivalencias`). Hojas sueltas: nada cambia.
"""
from __future__ import annotations

import bisect
import re
from collections import Counter
from typing import Dict, Optional, Sequence, Tuple

from hoja.leyenda_mapa import LINEA, LeyendaMapa, _trazo_principal


def _clave(fila) -> Tuple:
    """Lo que hace que dos filas de dos leyendas sean la misma línea."""
    return (fila.utilidad, re.sub(r"\s+", " ", fila.texto.strip().upper()), fila.seccion.strip().upper())


def equivalencias(ley: LeyendaMapa) -> Dict[Tuple[int, str], str]:
    """{(pieza, estilo): estilo común} de una hoja compuesta (vacío en una hoja suelta).

    Nodos = (pieza, estilo de la muestra de una fila de LÍNEA con utilidad). Dos nodos van juntos
    si son la misma fila en dos piezas, o la misma pieza y el mismo estilo (dos filas que esa pieza
    dibuja igual ya se reconocen juntas en ella). El estilo común de cada grupo es el nombre que más
    nodos tienen (empate: el menor, para no depender del orden). Un estilo de una pieza no va a un
    común que en esa pieza es de OTRO grupo."""
    if len(ley.por_hoja) <= 1 or len(ley.piezas) != len(ley.por_hoja):
        return {}
    padre: Dict[Tuple[int, str], Tuple[int, str]] = {}

    def raiz(n):
        while padre[n] != n:
            padre[n] = padre[padre[n]]
            n = padre[n]
        return n

    def unir(a, b):
        padre.setdefault(a, a)
        padre.setdefault(b, b)
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)

    primera: Dict[Tuple, Tuple[int, str]] = {}          # fila → su primer nodo
    for filas, pieza in zip(ley.por_hoja, ley.piezas):
        if pieza is None:
            continue
        for f in filas:
            if f.rol != LINEA or not f.utilidad:
                continue
            estilo = _trazo_principal(f)
            if not estilo:
                continue
            nodo = (pieza, estilo)
            unir(nodo, primera.setdefault(_clave(f), nodo))
    grupos: Dict[Tuple[int, str], list] = {}
    for n in padre:
        grupos.setdefault(raiz(n), []).append(n)
    out: Dict[Tuple[int, str], str] = {}
    for nodos in grupos.values():
        estilos = {e for _p, e in nodos}
        if len(estilos) <= 1:
            continue
        cuenta = Counter(e for _p, e in nodos)
        comun = min(cuenta.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        for pieza, estilo in nodos:
            if estilo == comun:
                continue
            otro = (pieza, comun)
            if otro in padre and raiz(otro) != raiz((pieza, estilo)):
                continue                      # en esa pieza el común ya es otra cosa
            out[(pieza, estilo)] = comun
    return out


def pieza_de(inicios: Optional[Sequence[int]], seqno) -> int:
    """Pieza de un trazo por su orden de dibujo (`inicios_de_piezas`); -1 si no se sabe."""
    if not inicios or seqno is None:
        return -1
    return bisect.bisect_right(inicios, int(seqno)) - 1
