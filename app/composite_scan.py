"""composite_scan.py — ayudas PURAS (sin Qt) para componer escaneos a mano.

Lo usan la regla, el transportador y las herramientas de la hoja compuesta
(`alignment_tools.py`, `composite_view.py`, `composite_dialog.py`):

  - `snap_angle`: el ángulo que deja el ratón, con IMÁN a 0°/90°/180°/270°
    (volver a cero con el puntero era casi imposible: reporte del usuario
    2026-10-02, transportador en −0.33°), pasos de 15° con Shift y ajuste fino
    de centésimas con Ctrl.
  - `rotate_piece` / `scale_piece`: girar o escalar una pieza dejando QUIETO un
    punto de la hoja compuesta (el centro, o el medio de la línea medida al
    enderezar: así la línea no se va de su sitio).
  - `calibrated_scale`: escala de origen a partir de una distancia conocida
    (los escaneos rara vez traen la escala impresa exacta).
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import composite as C

CARDINALS = (0.0, 90.0, 180.0, 270.0, 360.0)
MAGNET_DEG = 1.0          # imán a los ejes al arrastrar normal
FINE_MAGNET_DEG = 0.05    # con Ctrl (ajuste fino) el imán casi no se nota
STEP_DEG = 0.1            # resolución al arrastrar normal (1 px ≈ 0.5° en el dial)
FINE_STEP_DEG = 0.01
COARSE_STEP_DEG = 15.0    # con Shift
FINE_DRAG_GAIN = 0.1      # con Ctrl el ratón gira 10 veces menos


def signed_angle(a: float) -> float:
    """Ángulo en (−180, 180]."""
    a = math.fmod(float(a), 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def snap_angle(value: float, fine: bool = False, coarse: bool = False) -> Tuple[float, bool]:
    """(ángulo con imán, ¿quedó en un eje?). `coarse` (Shift) = múltiplos de 15°;
    `fine` (Ctrl) = centésimas con un imán mínimo; normal = décimas con imán de
    1° a 0/90/180/270. El resultado queda en (−180, 180]."""
    if coarse:
        out = round(value / COARSE_STEP_DEG) * COARSE_STEP_DEG
    else:
        tol = FINE_MAGNET_DEG if fine else MAGNET_DEG
        a = value % 360.0
        axis = min(CARDINALS, key=lambda c: abs(a - c))
        if abs(a - axis) <= tol:
            out = value + (axis - a)
        else:
            step = FINE_STEP_DEG if fine else STEP_DEG
            out = round(value / step) * step
    out = signed_angle(round(out, 6))
    return out, any(abs(out % 360.0 - c) < 1e-6 for c in CARDINALS)


def nearest_axis(value: float) -> float:
    """El múltiplo de 90° más cercano (para «volver a 0°» sin perder un giro de 90°)."""
    return signed_angle(round(value / 90.0) * 90.0)


def _center(piece: C.Piece, page_size, target: float) -> C.Pt:
    w, h = C.piece_size(piece, page_size, target)
    return piece.x + w / 2.0, piece.y + h / 2.0


def rotate_piece(piece: C.Piece, page_size, target: float, rotation: float,
                 pivot: Optional[C.Pt] = None) -> None:
    """Gira la pieza a `rotation` (antihorario) sin mover `pivot` (pt de la hoja
    compuesta; por defecto su centro)."""
    if pivot is None:
        pivot = _center(piece, page_size, target)
    src = C.piece_unmap(piece, page_size, target)(*pivot)
    piece.rotation = float(rotation) % 360.0
    x, y = C.piece_map(piece, page_size, target)(*src)
    piece.x += pivot[0] - x
    piece.y += pivot[1] - y


def scale_piece(piece: C.Piece, page_size, target: float, src_scale: float,
                pivot: Optional[C.Pt] = None) -> None:
    """Cambia la escala de origen (pies/pt) sin mover `pivot`."""
    if pivot is None:
        pivot = _center(piece, page_size, target)
    src = C.piece_unmap(piece, page_size, target)(*pivot)
    piece.src_scale = float(src_scale)
    x, y = C.piece_map(piece, page_size, target)(*src)
    piece.x += pivot[0] - x
    piece.y += pivot[1] - y


def calibrated_scale(src_scale: float, measured_ft: float, real_ft: float) -> Optional[float]:
    """Escala de origen corregida para que lo medido mida `real_ft` pies."""
    if measured_ft <= 1e-9 or real_ft <= 1e-9:
        return None
    return float(src_scale) * float(real_ft) / float(measured_ft)

