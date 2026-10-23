"""recognition_grosor_marcos.py — rótulos de diámetro GIRADOS (PURO; ver `recognition_grosor`).

Pedido del usuario 2026-10-22 («toda la información posible del PDF»): en DU08, DU10 y LABOE la
mayoría de los rótulos de las utilidades va en VERTICAL junto a una tubería que corre de norte a
sur («COLA-SS D-8032, / 15" VCP, 24'W CL, SS117», 782 en DU08, 938 en DU10, 289 en LABOE) y solo
se leían los horizontales. Es el mismo MLeader girado 90°: la raya (o el arranque de la guía en
el borde del bloque) va a lo largo del texto. Para cada dirección de texto de los ejes se pasa
TODO —cajas de las líneas, tramos y flechas— a un marco donde ese texto es horizontal
(`al_marco`: x a lo largo del texto, y hacia «abajo» del texto) y se usa la misma lógica de
bloques, rayas y guías; las puntas, las cadenas y las cajas de los rótulos vuelven a la hoja.
El texto horizontal sigue exactamente el camino de siempre (sin transformar nada).
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from reconocimiento.recognition_grosor_guias import Guias, puntas_de_rotulos
from reconocimiento.recognition_grosor_texto import diametros_de, rotulos

Pt = Tuple[float, float]

# direcciones de lectura del texto (px de la vista, y hacia abajo): horizontal, de abajo arriba,
# de arriba abajo y cabeza abajo. El texto oblicuo no: su caja de MuPDF no es la del texto.
DIRECCIONES = ((1.0, 0.0), (0.0, -1.0), (0.0, 1.0), (-1.0, 0.0))
TOL_DIR = 0.05


def al_marco(d: Pt, p: Pt) -> Pt:
    """De la hoja al marco del texto que se lee en la dirección d: (a lo largo, hacia abajo)."""
    return (p[0] * d[0] + p[1] * d[1], p[1] * d[0] - p[0] * d[1])


def de_marco(d: Pt, q: Pt) -> Pt:
    return (q[0] * d[0] - q[1] * d[1], q[0] * d[1] + q[1] * d[0])


def _caja(f: Callable[[Pt], Pt], bb) -> Tuple[float, float, float, float]:
    cs = [f((bb[0], bb[1])), f((bb[2], bb[1])), f((bb[2], bb[3])), f((bb[0], bb[3]))]
    return (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))


def _en_direccion(dd: Pt, d: Pt) -> bool:
    return abs(dd[0] - d[0]) < TOL_DIR and abs(dd[1] - d[1]) < TOL_DIR


def leer(lineas: Sequence, gs: Optional[Guias], zoom: float,
         fuera: Optional[Callable[[Pt], bool]] = None):
    """(rótulos, puntas) de los rótulos de TODAS las direcciones de los ejes. `lineas` =
    `lineas_texto` (px de la vista); `gs` = las guías de la hoja; `fuera(punto)` = True para los
    rótulos que no cuentan (vistas de perfil). Las cajas de los rótulos girados quedan en la hoja."""
    rots_out: List = []
    puntas_out: List = []
    for d in DIRECCIONES:
        if d == DIRECCIONES[0]:
            lin = lineas
            todos, cajas = rotulos(lin)
            centro = lambda r: ((r.bbox[0] + r.bbox[2]) / 2.0, (r.bbox[1] + r.bbox[3]) / 2.0)  # noqa: E731
        else:
            if not any(_en_direccion(l[3], d) and diametros_de(l[0]) for l in lineas):
                continue
            f = (lambda p, d=d: al_marco(d, p))
            lin = [(t, _caja(f, bb), tam, al_marco(d, dd)) for t, bb, tam, dd in lineas]
            todos, cajas = rotulos(lin)
            centro = (lambda r, d=d: de_marco(d, ((r.bbox[0] + r.bbox[2]) / 2.0, (r.bbox[1] + r.bbox[3]) / 2.0)))
        quedan = [r for r in todos if fuera is None or not fuera(centro(r))]
        if not quedan:
            continue
        if d == DIRECCIONES[0]:
            puntas = puntas_de_rotulos(quedan, cajas, gs) if gs is not None else []
        else:
            g = None
            if gs is not None:
                g = Guias([(al_marco(d, a), al_marco(d, b)) for a, b in gs.tramos],
                          [[al_marco(d, v) for v in fl] for fl in gs.flechas], zoom)
            puntas = puntas_de_rotulos(quedan, cajas, g) if g is not None else []
            puntas = [(r, [de_marco(d, p) for p in cad], de_marco(d, pt)) for r, cad, pt in puntas]
            for r in quedan:                      # la caja del rótulo, en la hoja
                r.bbox = _caja(lambda q, d=d: de_marco(d, q), r.bbox)
        rots_out += quedan
        puntas_out += puntas
    return rots_out, puntas_out
