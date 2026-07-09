"""
geometry.py — Transformaciones de coordenadas y utilidades geométricas puras.

Sin dependencia de la ventana: las funciones reciben los parámetros que necesitan.
`to_cad` reproduce exactamente la conversión píxel-de-vista → coordenada de mundo CAD
(pies) que usa la app, para que DXF y JSON queden en las mismas coordenadas.
"""
import math
import fitz
import numpy as np
from PySide6 import QtGui


def point_in_poly(x, y, poly):
    n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def pt_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def qimage_to_gray(qimg):
    qimg = qimg.convertToFormat(QtGui.QImage.Format_Grayscale8)
    w, h = qimg.width(), qimg.height(); ptr = qimg.constBits()
    arr = np.frombuffer(ptr, np.uint8).reshape(h, qimg.bytesPerLine())[:, :w]
    return arr.copy()


def to_cad(x, y, scale, rot, W, H, derot, zoom):
    """Píxel de la vista (a zoom actual) → coordenada de mundo CAD en pies."""
    mp = fitz.Point(x / zoom, y / zoom) * derot
    px, py = mp.x, mp.y; s = scale
    if rot == 0: return (px * s, (H - py) * s)
    if rot == 90: return (py * s, px * s)
    if rot == 180: return ((W - px) * s, py * s)
    return (py * s, px * s)


def snap_point(gray, x, y, r):
    """Ajusta (x,y) al centroide de píxeles oscuros en una ventana de radio r."""
    if gray is None:
        return (x, y)
    h, w = gray.shape; xi, yi = int(x), int(y)
    win = gray[max(0, yi - r):min(h, yi + r + 1), max(0, xi - r):min(w, xi + r + 1)] < 128
    if not win.any():
        return (x, y)
    ys, xs = np.nonzero(win)
    return (max(0, xi - r) + xs.mean(), max(0, yi - r) + ys.mean())
