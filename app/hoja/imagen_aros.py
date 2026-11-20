"""Buzones dibujados como un ARO FINO con letra («M», «B», «DW») en la imagen de la red (PURO: numpy + cv2, sin Qt).

Pedido del usuario (2026-11-19, Phoenix «QS SD_Indian School»: «los que son buzones se consideran como buzones»).
El aro de esos buzones es una línea de ~1 px casi toda de ANTIALIAS (tonos claros, no el color de la red) y la
tubería se corta justo en él: en la máscara del color solo llegan las patitas de la letra, que salían como dos
rayitas sueltas, y la línea pasaba de largo sin buzón. `imagen_trazos` solo ve el aro cuando es del color
(`imagen_huecos.es_aro`).

`aros(img, tinta, escala)` busca círculos (Hough sobre el gris de la imagen) de radio `RADIO_MIN_PT`–`RADIO_MAX_PT`
y se queda con los que son de verdad un aro con letra de ESE color:

  · aro casi completo: ≥ `ARO_TINTA` de su contorno con tinta (lo que no es blanco) a ±`ARO_ANCHO_PX`;
  · del color: ≥ `ARO_COLOR` de esa tinta es del color o de su antialias (`tinta` = máscara ∪ familia);
  · con letra: el disco interior (0.75 r) tiene entre `LETRA_MIN` y `LETRA_MAX` de tinta del color (ni vacío ni
    macizo: un punto relleno o una banda ancha no es un aro con letra);
  · suelto: fuera del aro (1.3–1.6 r) poca tinta (< `AFUERA_MAX`): dentro de un rayado o de una banda, no.

Devuelve [(cx, cy, r)] en px de la imagen. Mismo resultado para la misma imagen (determinista).
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from hoja.imagen_trazos import Simbolo

RADIO_MIN_PT = 3.5
RADIO_MAX_PT = 8.0
ARO_ANCHO_PX = 1.5
ARO_TINTA = 0.75
ARO_COLOR = 0.5
LETRA_MIN = 0.03
LETRA_MAX = 0.45
AFUERA_MAX = 0.35
BLANCO = 235                  # un canal por debajo de esto = tinta
N_MUESTRAS = 96
REDUCIR = 1                   # Hough a resolución completa (a 1/2 perdía la mitad de los aros de North h.1)
HOUGH_VOTOS = 18              # umbral del acumulador de Hough


def _muestras(cx, cy, r, n=N_MUESTRAS):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return cx + r * np.cos(a), cy + r * np.sin(a)


def _en(m, xs, ys):
    h, w = m.shape[:2]
    xi, yi = np.round(xs).astype(int), np.round(ys).astype(int)
    ok = (xi >= 0) & (yi >= 0) & (xi < w) & (yi < h)
    out = np.zeros(len(xs), bool)
    out[ok] = m[yi[ok], xi[ok]]
    return out


def _aro(m, cx, cy, r):
    """¿Hay `m` sobre el contorno (±`ARO_ANCHO_PX`)? Por muestra."""
    hay = np.zeros(N_MUESTRAS, bool)
    for dr in (-ARO_ANCHO_PX, -ARO_ANCHO_PX / 2, 0.0, ARO_ANCHO_PX / 2, ARO_ANCHO_PX):
        hay |= _en(m, *_muestras(cx, cy, r + dr))
    return hay


def _disco(m, cx, cy, r0, r1):
    h, w = m.shape[:2]
    x0, x1 = max(0, int(cx - r1 - 1)), min(w, int(cx + r1 + 2))
    y0, y1 = max(0, int(cy - r1 - 1)), min(h, int(cy + r1 + 2))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.hypot(xx - cx, yy - cy)
    sel = (d >= r0) & (d <= r1)
    return float(m[y0:y1, x0:x1][sel].mean()) if sel.any() else 0.0


def _ajustar(alguna, cx, cy, r):
    """El candidato de la imagen reducida, al píxel: el centro y radio (±1 px, pasos de 0.5) con más tinta sobre
    el contorno (el primero en caso de empate)."""
    d = np.arange(-1, 1.01, 0.5)
    dx, dy, dr = (v.ravel()[:, None] for v in np.meshgrid(d, d, d, indexing="ij"))
    a = np.linspace(0, 2 * math.pi, N_MUESTRAS, endpoint=False)[None, :]
    xi = np.round(cx + dx + (r + dr) * np.cos(a)).astype(int)
    yi = np.round(cy + dy + (r + dr) * np.sin(a)).astype(int)
    h, w = alguna.shape
    ok = (xi >= 0) & (yi >= 0) & (xi < w) & (yi < h)
    v = np.where(ok, alguna[np.clip(yi, 0, h - 1), np.clip(xi, 0, w - 1)], False).mean(axis=1)
    k = int(np.argmax(v))
    return cx + float(dx[k, 0]), cy + float(dy[k, 0]), r + float(dr[k, 0])


def _validar(img, tinta, nucleo, cx, cy, r):
    """(cx, cy, r) ajustado si es un aro con letra del color; None si no. Todo en una ventanita alrededor."""
    m = int(math.ceil(1.6 * r + 4))
    h, w = img.shape[:2]
    x0, y0 = max(0, int(cx) - m), max(0, int(cy) - m)
    x1, y1 = min(w, int(cx) + m + 1), min(h, int(cy) + m + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    alguna = img[y0:y1, x0:x1].min(axis=2) < BLANCO
    tin, nuc = tinta[y0:y1, x0:x1], nucleo[y0:y1, x0:x1]
    lx, ly = cx - x0, cy - y0
    if _aro(alguna, lx, ly, r).mean() < ARO_TINTA:
        return None                                     # descarte barato antes de ajustar
    lx, ly, r = _ajustar(alguna, lx, ly, r)
    hay = _aro(alguna, lx, ly, r)
    if hay.mean() < ARO_TINTA or (_aro(tin, lx, ly, r) & hay).sum() < ARO_COLOR * hay.sum():
        return None
    if not LETRA_MIN <= _disco(nuc, lx, ly, 0.0, 0.75 * r) <= LETRA_MAX:
        return None
    if _disco(alguna, lx, ly, 1.3 * r, 1.6 * r) >= AFUERA_MAX:
        return None
    return lx + x0, ly + y0, r


def aros(img: np.ndarray, tinta: np.ndarray, nucleo: np.ndarray, escala: float) -> list[tuple[float, float, float]]:
    """Aros con letra de un color (ver el módulo). `tinta` = máscara ∪ familia del color, `nucleo` = su máscara."""
    if not tinta.any():
        return []
    # candidatos con Hough en la imagen reducida a 1/`REDUCIR`; cada uno se ajusta y se valida a resolución completa
    # en una ventanita a su alrededor (la tinta de la tesela entera costaba ~6 s por hoja)
    gris = cv2.resize(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), None, fx=1 / REDUCIR, fy=1 / REDUCIR,
                      interpolation=cv2.INTER_AREA)
    e = escala / REDUCIR
    rmin, rmax = int(RADIO_MIN_PT * e), int(math.ceil(RADIO_MAX_PT * e))
    # en UN hilo: con todos los núcleos, OpenCV pedía su memoria de trabajo por hilo (~2 GB más por hoja con 12
    # núcleos, 2026-11-20). Mismos círculos; el resto de OpenCV sigue con todos los hilos.
    antes = cv2.getNumThreads()
    cv2.setNumThreads(1)
    try:
        cs = cv2.HoughCircles(cv2.GaussianBlur(gris, (3, 3), 0), cv2.HOUGH_GRADIENT, dp=1, minDist=2 * rmin,
                              param1=120, param2=HOUGH_VOTOS, minRadius=rmin, maxRadius=rmax)
    finally:
        cv2.setNumThreads(antes)
    if cs is None:
        return []
    salida = []
    for c0 in sorted((float(a), float(b), float(c)) for a, b, c in cs[0]):
        v = _validar(img, tinta, nucleo, *(x * REDUCIR for x in c0))
        if v is None:
            continue
        cx, cy, r = v
        if any(math.hypot(cx - a, cy - b) < max(r, c) for a, b, c in salida):
            continue
        salida.append((cx, cy, r))
    return salida


def sumar(p, aros, escala) -> None:
    """Los aros que `trazos` no vio pasan a símbolos (círculo de su diámetro) y se van las líneas que quedan
    enteras dentro de ellos (las patitas de su letra)."""
    for cx, cy, r in aros:
        if any(math.hypot(s.cx - cx, s.cy - cy) < r for s in p.simbolos):
            continue                                       # ya era un símbolo
        p.simbolos.append(Simbolo(cx, cy, 2 * r, 2 * r, "círculo {}".format(round(2 * r / escala))))
        dentro = [i for i, pts in enumerate(p.lineas) if all(math.hypot(x - cx, y - cy) <= r for x, y in pts)]
        for i in reversed(dentro):
            del p.lineas[i]
            del p.grosores[i]
