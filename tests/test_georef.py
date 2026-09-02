"""Pruebas de humo del ajuste de georreferenciación (geo/georef.py `fit`).

Verifican las propiedades que motivaron el cambio de afín → similaridad:
  1. La similaridad reproduce EXACTO una transformación píxel(Y abajo)→mundo(Y
     arriba) que necesita reflexión (det<0), y generaliza a un punto nuevo.
  2. La similaridad NO deforma (un cuadrado sigue siendo cuadrado).
  3. Con 3 puntos + ruido, el RMSE de la similaridad es HONESTO (>0), mientras el
     afín da 0 (engañoso).
"""
import math

import numpy as np

from geo import georef


def _true_map(x, y, theta=math.radians(20), s=2.5, tx=6_444_000.0, ty=1_883_000.0):
    """píxel (Y hacia abajo) → mundo (Y arriba): invierte Y, rota, escala, traslada."""
    yv = -y
    e = s * (math.cos(theta) * x - math.sin(theta) * yv) + tx
    n = s * (math.sin(theta) * x + math.cos(theta) * yv) + ty
    return e, n


SRC = [(100, 50), (800, 60), (400, 700)]           # triángulo amplio
DST = [_true_map(*p) for p in SRC]


def test_similaridad_reproduce_transformacion_con_reflexion():
    M, rms, ttype = georef.fit(SRC, DST, kind="similarity")
    assert ttype == "similarity"
    assert rms < 1e-3                               # dato perfecto → RMS ≈ 0
    det = M[0][0] * M[1][1] - M[0][1] * M[1][0]
    assert det < 0                                  # incluye el volteo Y píxel↔mundo
    # Generaliza a un punto NUEVO fuera del ajuste
    g = georef.Georef(matrix=M, epsg=2229, kind=ttype)
    ex, ny = _true_map(555, 321)
    gx, gy = g.to_world(555, 321)
    assert math.hypot(gx - ex, gy - ny) < 1e-3


def test_similaridad_no_deforma_un_cuadrado():
    M, _, _ = georef.fit(SRC, DST, kind="similarity")
    sq = [(0, 0), (100, 0), (100, 100), (0, 100)]
    w = [(M[0][0] * x + M[0][1] * y + M[0][2],
          M[1][0] * x + M[1][1] * y + M[1][2]) for (x, y) in sq]

    def ang(a, b, c):
        v1 = (a[0] - b[0], a[1] - b[1]); v2 = (c[0] - b[0], c[1] - b[1])
        d = (v1[0] * v2[0] + v1[1] * v2[1]) / (math.hypot(*v1) * math.hypot(*v2))
        return math.degrees(math.acos(max(-1, min(1, d))))

    for i in range(4):
        assert abs(ang(w[(i - 1) % 4], w[i], w[(i + 1) % 4]) - 90.0) < 1e-6
    lados = [math.hypot(w[i][0] - w[(i + 1) % 4][0], w[i][1] - w[(i + 1) % 4][1]) for i in range(4)]
    assert max(lados) - min(lados) < 1e-6


def test_rmse_similaridad_es_honesto_con_ruido_y_afin_es_cero():
    rng = np.random.default_rng(42)
    dst_noisy = [(e + rng.normal(0, 1.5), n + rng.normal(0, 1.5)) for (e, n) in DST]
    _, rms_sim, _ = georef.fit(SRC, dst_noisy, kind="similarity")
    _, rms_aff, _ = georef.fit(SRC, dst_noisy, kind="affine")
    assert rms_sim > 0.1        # similaridad: revela el error real de los clics
    assert rms_aff < 1e-6       # afín con 3 puntos: exacto siempre → cero engañoso
