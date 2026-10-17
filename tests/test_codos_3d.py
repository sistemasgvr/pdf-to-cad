"""Codos en 3D y conexión vertical con pendiente (reporte del usuario 2026-10-16, proyecto
«00.proyecto»): (1) dos tramos de agua casi rectos en planta pero uno subiendo 6 ft en ~3 ft
no llevaban codo en la app (el giro se medía solo en planta) y Civil 3D sí lo pone (mide
en 3D); (2) el codo de una conexión vertical se armaba a nivel aunque la utilidad que
termina ahí subiera 17°: entraba torcida en la campana."""
import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import accesorios as ACC  # noqa: E402
from nucleo import modelo3d  # noqa: E402

FT = 0.08          # pies por px


def _p(pts, inv, layer="AGUA", diam=12.0):
    return dict(layer=layer, pts=[tuple(q) for q in pts], name="", diam=diam, pipe_size=f"{diam:g} in",
                inv_start=inv[0], inv_end=inv[1])


def _z(pipes):
    from nucleo import model_ops
    return lambda i, k, x, y: model_ops.z_en_tramo(pipes[i], k, x, y)


def test_codo_por_cambio_de_pendiente_aunque_en_planta_sea_recto():
    # tres tramos en línea (0.3° en planta); el del medio sube 6 ft en 3.4 ft
    a, b, c, d = (0.0, 0.0), (0.0, -1600.0), (0.2, -1642.5), (0.2, -2400.0)
    pipes = [_p([a, b], (-6.0, -6.0)), _p([b, c], (-6.0, 0.0)), _p([c, d], (0.0, 0.0))]
    nodos = ACC.accesorios(pipes, _z(pipes), FT)
    codos = sorted((round(n["angulo"], 1), n["pipes"]) for n in nodos if n["tipo"] == "codo")
    sube = math.degrees(math.atan2(6.0, math.dist(b, c) * FT))
    assert [p for _a, p in codos] == [[0, 1], [1, 2]]
    assert all(ang == pytest.approx(sube, abs=0.5) for ang, _p_ in codos)
    # a nivel, el mismo dibujo no lleva codos (como siempre: menos de 1° en planta)
    planos = [_p([a, b], (-6.0, -6.0)), _p([b, c], (-6.0, -6.0)), _p([c, d], (-6.0, -6.0))]
    assert not [n for n in ACC.accesorios(planos, _z(planos), FT) if n["tipo"] == "codo"]


def test_el_angulo_de_un_codo_a_nivel_no_cambia():
    pipes = [_p([(0, 0), (500, 0)], (-4.0, -4.0)), _p([(500, 0), (500 + 500 * math.cos(math.radians(45)),
                                                              500 * math.sin(math.radians(45)))], (-4.0, -4.0))]
    (n,) = ACC.accesorios(pipes, _z(pipes), FT)
    assert n["tipo"] == "codo" and n["angulo"] == pytest.approx(45.0, abs=1e-9)


def test_codos_en_3d_visibles_y_tubo_recortado_en_planta():
    a, b, c, d = (0.0, 0.0), (0.0, -1600.0), (0.2, -1642.5), (0.2, -2400.0)
    pipes = [_p([a, b], (-6.0, -6.0)), _p([b, c], (-6.0, 0.0)), _p([c, d], (0.0, 0.0))]
    esc = modelo3d.construir(pipes, [], FT)
    codos = [o for o in esc.objetos.values() if o["tipo"] == "accesorio" and o.get("acc_tipo") == "codo"]
    assert len(codos) == 2
    # el tramo empinado sigue existiendo entre las dos campanas (el recorte se mide en planta)
    tubo = esc.objetos[2]
    assert tubo["tipo"] == "pipe"


def test_codo_de_la_conexion_vertical_sigue_la_pendiente():
    from nucleo import verticales3d as V
    # la 2 TERMINA en el cruce a -7 y sube a 0 en 22 ft; la 1 pasa a nivel (0)
    pipes = [_p([(0, 0), (200, 0)], (0.0, 0.0)), _p([(100, 0), (100, -278.5)], (-7.0, 0.0))]
    cruce = dict(x=100.0, y=0.0, pipe_a=0, pipe_b=1, z_a=0.0, z_b=-7.0, valve=True)
    esc = modelo3d.construir(pipes, [], FT, cruces=[cruce])
    piezas = [o for o in esc.objetos.values() if o["tipo"] == "accesorio" and o.get("vertical")]
    assert sorted(o["acc_tipo"] for o in piezas) == ["codo", "tee"]
    # el brazo del codo hacia la utilidad 2 sube con ella (antes iba a nivel)
    ar = modelo3d._Armado(FT, None)
    dib = V._Dibujo(ar, pipes, 0, modelo3d.diametro_ft, z_eje=lambda i, x, y: modelo3d._z_eje(pipes, i, x, y))
    u = dib.brazo_3d(1, 100.0, 0.0, (0.0, -1.0))
    pendiente = 7.0 / (278.5 * FT)
    assert u[2] / math.hypot(u[0], u[1]) == pytest.approx(pendiente, rel=1e-6)
    assert np.linalg.norm(u) == pytest.approx(1.0)
    # sin cotas: a nivel, como antes
    plano = V._Dibujo(ar, pipes, 0, modelo3d.diametro_ft).brazo_3d(1, 100.0, 0.0, (0.0, -1.0))
    assert tuple(plano) == (0.0, 1.0, 0.0)
