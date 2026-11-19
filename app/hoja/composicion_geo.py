"""Uniones de la composición sugerida por la GEORREFERENCIA de cada hoja (PURO: sin Qt ni fitz).

Pedido del usuario (2026-11-19, «QS SD_Indian School» North + South: la sugerencia salía en 8 grupos cuando es UNA
sola composición): «ubicarlos, georreferenciarlos y armar la composición en base a la georreferenciación». En esos
mapas la red es una imagen y los lotes vectoriales casi no se repiten en la franja común, así que el dibujo confirma
pocas uniones (11 de 52).

Cada hoja de un mapa en cuadrícula sabe dónde está en el mundo (`Ficha.geo`: el centroide de su celda en el índice
de mapas, confirmada por el texto de la hoja, `geo.auto.fuentes.celda_en_mundo`). Todas las hojas de un PDF salen de
la misma plantilla (el mapa centrado en su celda), así que entre dos hojas el desplazamiento en pt es el de sus
centroides en el mundo dividido por `k` = pies del mundo por pt (con la «y» al revés: el norte va arriba):

    B = s·A + t,   s = k_A / k_B,   t = (Δx / k_B, −Δy / k_B),   Δ = centroide(A) − centroide(B)

`k` de cada PDF se CALIBRA con las uniones que el dibujo ya confirmó (|Δ| / |t|; mediana): no se adivina con la
escala del cajetín ni con un ancho de recuadro supuesto (medido: los mapas SD van a 1"=100', 1.389 ft/pt, y el ancho
de recuadro del índice suponía 1.04). Sin ninguna unión confirmada en un PDF, se usa la mediana de los demás; sin
ninguna en absoluto, no hay uniones por georreferencia (todo queda como antes).

Medido en SD North + South: la predicción cae a ≤ ~1.5 pt de las 11 uniones que el dibujo confirmó."""
from __future__ import annotations

import math
import statistics
from typing import Dict, Optional, Sequence, Tuple

K_DISPERSION_MAX = 0.01       # las uniones de un PDF deben dar la misma escala (±1 %) para calibrarlo
ACUERDO_PT = 3.0              # una unión confirmada solo calibra si su dirección es la de los centroides


def _delta(fa, fb) -> Optional[Tuple[float, float]]:
    if fa.geo is None or fb.geo is None or fa.geo[0] != fb.geo[0]:
        return None
    return fa.geo[2] - fb.geo[2], fa.geo[3] - fb.geo[3]


def calibrar(costuras: Sequence, fichas: Dict) -> Dict[int, float]:
    """{pdf: k} con las uniones confirmadas ENTRE hojas del mismo PDF (s = 1) cuyas dos hojas tienen `geo`."""
    por_doc: Dict[int, list] = {}
    for c in costuras:
        fa, fb = fichas.get(c.a), fichas.get(c.b)
        if fa is None or fb is None or c.a[0] != c.b[0] or abs(c.escala - 1.0) > 0.002:
            continue
        d = _delta(fa, fb)
        nt = math.hypot(*c.t)
        if d is None or nt < 1.0:
            continue
        k = math.hypot(*d) / nt
        # la dirección también debe cuadrar (t ≈ Δ/k con la «y» al revés)
        if math.hypot(c.t[0] - d[0] / k, c.t[1] + d[1] / k) > ACUERDO_PT:
            continue
        por_doc.setdefault(c.a[0], []).append(k)
    out = {}
    for doc, ks in por_doc.items():
        m = statistics.median(ks)
        if all(abs(k / m - 1.0) <= K_DISPERSION_MAX for k in ks) or len(ks) >= 3:
            out[doc] = m
    return out


def k_de(doc: int, ks: Dict[int, float]) -> Optional[float]:
    if doc in ks:
        return ks[doc]
    return statistics.median(ks.values()) if ks else None


def prediccion(fa, fb, ks: Dict[int, float]) -> Optional[Tuple[float, Tuple[float, float]]]:
    """(s, t) de B = s·A + t por la georreferencia, o None si alguna hoja no se sabe dónde está o no hay escala."""
    d = _delta(fa, fb)
    ka, kb = k_de(fa.doc, ks), k_de(fb.doc, ks)
    if d is None or not ka or not kb:
        return None
    return ka / kb, (d[0] / kb, -d[1] / kb)
