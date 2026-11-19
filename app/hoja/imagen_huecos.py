"""Huecos que la tinta encierra (PURO: numpy + cv2, sin Qt). Lo usa `imagen_trazos`.

- `rellenar`: rellena los huecos chicos y rectangulares (cajitas de la tubería «en caja», cuadros
  de una rejilla) y devuelve las cajas de las REJILLAS (≥ `MALLA_HUECOS` huecos parecidos juntos).
- `cerrar_con_familia`: lo mismo sobre la FAMILIA (antialias) de un color, solo en componentes con
  núcleo; los huecos y los píxeles de familia que los tocan pasan al núcleo.
- `huecos` / `grosor_aro` / `es_aro`: el aro con letra (M, B, DW, F) como símbolo.
- `juntar`: une cajas que se tocan.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

HUECO_W_MIN = 2.5      # solo en trazos de este grosor (px) o más un hueco chico es símbolo
HUECO_MAX_W = 6.0      # hueco de un símbolo: lado ≤ esto·w
HUECO_MAX_PT = 4.0     # hueco encerrado por la tinta con lado corto ≤ esto (pt) se rellena …
HUECO_MIN_PX = 3       # … y lado corto ≥ esto (px): la rendija de 1–2 px entre los dos bordes de
                       # antialias de una línea de OTRO color (la trama) no es una cajita
HUECO_RECTANGULAR = 0.75   # … si es rectangular (área / rectángulo mínimo); una letra no lo es
HUECO_ALARGADO = 4.0   # … y no más largo que esto·lado corto
ARO_MAX_PT = 12.0      # aro de símbolo: lado ≤ esto (pt) …
ARO_HUECO = 0.4        # … con un hueco que cubre al menos esto de su caja
NUCLEO_MIN_FRAC = 0.2  # componente de familia con menos núcleo que esto no se usa para cerrar
MALLA_HUECOS = 4       # huecos parecidos pegados a partir de cuántos son una rejilla (símbolo)


def grosor_aro(sub, cx, cy, w) -> float:
    """Grosor del aro alrededor de un hueco: mediana, en 16 rumbos desde su centro, de la tinta que
    se cruza al salir (donde se pega una línea el cruce es largo; la mediana no lo ve)."""
    grosores = []
    for k in range(16):
        d = (math.cos(k * math.pi / 8), math.sin(k * math.pi / 8))
        t, dentro, ini = 0.0, False, None
        while t < 8 * w + 20:
            x, y = math.floor(cx + d[0] * t + 0.5), math.floor(cy + d[1] * t + 0.5)
            tinta = 0 <= y < sub.shape[0] and 0 <= x < sub.shape[1] and bool(sub[y, x])
            if tinta and not dentro:
                dentro, ini = True, t
            elif dentro and not tinta:
                grosores.append(t - ini)
                break
            t += 0.5
    return float(np.median(grosores)) if grosores else w


def huecos(sub, w) -> list[list[int]]:
    """Cajas de los huecos chicos de una componente gruesa (el aro de un buzón con su letra)."""
    if w < HUECO_W_MIN:
        return []
    cont, jer = cv2.findContours(sub.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    cajas = []
    for c, h in zip(cont, jer[0] if jer is not None else []):
        if h[3] < 0:                                   # contorno exterior, no hueco
            continue
        x, y, cw, ch = cv2.boundingRect(c)
        if cw * ch < 4 or max(cw, ch) > HUECO_MAX_W * w or max(cw, ch) > 2.5 * min(cw, ch):
            continue
        g = int(math.ceil(grosor_aro(sub, x + cw / 2, y + ch / 2, w))) + 1
        cajas.append([x - g, y - g, x + cw - 1 + g, y + ch - 1 + g])
    return cajas


def juntar(cajas) -> list[list[int]]:
    """Une las cajas que se tocan (una zona de símbolo = una caja), hasta que ninguna se toque."""
    c = np.array(sorted(cajas), float).reshape(-1, 4)
    while len(c) > 1:
        toca = ((c[:, None, 0] <= c[None, :, 2]) & (c[None, :, 0] <= c[:, None, 2])
                & (c[:, None, 1] <= c[None, :, 3]) & (c[None, :, 1] <= c[:, None, 3]))
        etiqueta = np.arange(len(c))
        cambio = True
        while cambio:                                     # cierre transitivo por etiquetas mínimas
            nueva = np.where(toca, etiqueta[None, :], len(c)).min(axis=1)
            cambio = bool((nueva != etiqueta).any())
            etiqueta = nueva[nueva]
        if len(np.unique(etiqueta)) == len(c):
            break
        c = np.array([[c[etiqueta == e, 0].min(), c[etiqueta == e, 1].min(),
                       c[etiqueta == e, 2].max(), c[etiqueta == e, 3].max()]
                      for e in np.unique(etiqueta)])
    return [[int(v) for v in fila] for fila in c]


def rellenar(sub: np.ndarray, escala: float, minimo: float = 1.0):
    """Rellena los huecos que la PROPIA tinta encierra si son chicos y rectangulares (lado corto ≤
    `HUECO_MAX_PT`): las cajitas blancas de la tubería «en caja» y los cuadros de una rejilla. No
    une nada que la tinta no una ya. Devuelve (máscara rellena, cajas de rejillas): ≥ `MALLA_HUECOS`
    huecos parecidos pegados unos a otros = rejilla (símbolo), antes de que el relleno la borre.
    `minimo` = lado corto mínimo (px) de un hueco que se rellena."""
    cont, jer = cv2.findContours(sub.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if jer is None:
        return sub, []
    huecos = []
    for c, h in zip(cont, jer[0]):
        if h[3] < 0:
            continue
        (cx, cy), (rw, rh), _a = cv2.minAreaRect(c)
        corto, largo = min(rw, rh) + 1, max(rw, rh) + 1
        rect = (cv2.contourArea(c) + cv2.arcLength(c, True) / 2) / (corto * largo)
        if (minimo <= corto <= HUECO_MAX_PT * escala and rect >= HUECO_RECTANGULAR
                and largo <= HUECO_ALARGADO * corto):     # una franja de rayado no se rellena
            huecos.append((c, cx, cy, largo))
    if not huecos:
        return sub, []
    lleno = sub.astype(np.uint8).copy()
    cv2.drawContours(lleno, [h[0] for h in huecos], -1, 1, -1)
    c = np.array([(h[1], h[2]) for h in huecos])
    lg = np.array([h[3] for h in huecos])
    dist = np.hypot(c[:, None, 0] - c[None, :, 0], c[:, None, 1] - c[None, :, 1])
    mayor = np.maximum(lg[:, None], lg[None, :])
    junto = (dist <= 1.6 * mayor) & (np.abs(lg[:, None] - lg[None, :]) <= 0.5 * mayor)
    malla = np.nonzero((junto.sum(axis=1) - 1) >= MALLA_HUECOS - 1)[0]
    if not len(malla):
        return lleno > 0, []
    g = int(math.ceil(float(lg[malla].mean())))            # una línea que cruza la rejilla no la parte
    cajas = []
    for i in malla:
        x, y, w, h = cv2.boundingRect(huecos[int(i)][0])
        cajas.append([x - 2 - g, y - 2 - g, x + w + 1 + g, y + h + 1 + g])
    return lleno > 0, [[a + g, b + g, c - g, d - g] for a, b, c, d in juntar(cajas)]


def cerrar_con_familia(nucleo: np.ndarray, familia: np.ndarray, escala: float, ruido: int):
    """Cierra con la FAMILIA (antialias del color) lo que el núcleo no ve: en cada componente de
    familia con ≥ `NUCLEO_MIN_FRAC` de núcleo se rellenan los huecos chicos que la familia encierra
    (`_rellenar`); esos huecos y los píxeles de familia que los tocan pasan al núcleo. Las
    componentes casi sin núcleo (restos de una trama, otros tonos) no cuentan. Devuelve (núcleo
    cerrado, cajas de rejillas en px de la máscara)."""
    fam = (familia | nucleo).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fam, connectivity=8)
    salida, cajas = nucleo.copy(), []
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in st[k])
        if area < ruido:
            continue
        sl = np.zeros((h + 2, w + 2), bool)
        sl[1:-1, 1:-1] = lab[y:y + h, x:x + w] == k
        nuc = np.zeros_like(sl)
        nuc[1:-1, 1:-1] = nucleo[y:y + h, x:x + w] & sl[1:-1, 1:-1]
        if int(nuc.sum()) < NUCLEO_MIN_FRAC * area:
            continue
        lleno, cj = rellenar(sl, escala, HUECO_MIN_PX)
        nuevo = lleno & ~sl
        if nuevo.any():
            toca = cv2.dilate(nuevo.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            agrega = (nuevo | (toca & sl))[1:-1, 1:-1]
            salida[y:y + h, x:x + w] |= agrega
        cajas += [[a + x - 1, b + y - 1, c + x - 1, d + y - 1] for a, b, c, d in cj]
    return salida, cajas


def es_aro(sub: np.ndarray, escala: float) -> bool:
    """¿Componente chica (≤ `ARO_MAX_PT`) que es un aro: un hueco que ocupa casi toda su caja?
    (el círculo con letra «M», «B», «DW» de Phoenix, de trazo fino)."""
    ys, xs = np.nonzero(sub)
    alto, ancho = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    if max(alto, ancho) > ARO_MAX_PT * escala:
        return False
    cont, jer = cv2.findContours(sub.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    for c, h in zip(cont, jer[0] if jer is not None else []):
        if h[3] >= 0:
            _x, _y, cw, ch = cv2.boundingRect(c)
            if cw * ch >= ARO_HUECO * alto * ancho:
                return True
    return False
