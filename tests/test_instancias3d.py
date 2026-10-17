"""Vista 3D con INSTANCING (pedido del usuario 2026-10-16: «los mismos resultados con menos
recursos de PC»): los círculos barridos y las esferas van a la GPU como filas de
`instancias3d`; `expandir` rehace en la CPU los MISMOS triángulos de siempre (respaldo sin
OpenGL 3.3 y prueba de que el resultado no cambia)."""
import contextlib
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import instancias3d as I3  # noqa: E402
from nucleo import mallas3d as M  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESC = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")


def _instancias(fn):
    col = I3.Instancias()
    with M.instanciar(col):
        assert len(fn()) == 0                       # con el colector, ningún triángulo
    return col.arreglos()


def test_mismos_triangulos_bit_a_bit():
    rng = np.random.default_rng(3)
    for prueba in range(200):
        n = int(rng.integers(2, 9))
        P = np.cumsum(rng.normal(0, 20, size=(n, 3)), axis=0) + rng.uniform(-5000, 5000, 3)
        if prueba % 7 == 0:
            P[:, 2] = 3.0
        perfil = M.perfil_circulo(float(rng.uniform(0.1, 2.0)), int(rng.choice([12, 16, 20])))
        args = (P, perfil, tuple(rng.uniform(0, 1, 4)), int(rng.integers(1, 9999)),
                (bool(rng.integers(0, 2)), bool(rng.integers(0, 2))), bool(rng.integers(0, 2)))
        viejo = M.barrido_camino(*args)
        inst = _instancias(lambda: M.barrido_camino(*args))
        nuevo = np.concatenate([I3.expandir(k, inst[k]) for k in sorted(inst, key=lambda k: k[0] != I3.SEG)])
        assert np.array_equal(nuevo, viejo)
        lo, hi = I3.extremos(inst)
        assert np.array_equal(lo, viejo[:, :3].min(axis=0)) and np.array_equal(hi, viejo[:, :3].max(axis=0))
    for _ in range(20):
        c, r = rng.uniform(-3000, 3000, 3), float(rng.uniform(0.2, 3))
        inst = _instancias(lambda: M.esfera(c, r, (1, 0, 0, 1), 7))
        assert np.array_equal(I3.expandir(*next(iter(inst.items()))), M.esfera(c, r, (1, 0, 0, 1), 7))


def test_lo_que_no_es_circulo_sigue_en_triangulos():
    rect = M.perfil_rect(2.0, 1.0)
    inst = I3.Instancias()
    with M.instanciar(inst):
        tri = M.barrido_camino([(0, 0, 0), (10, 0, 0)], rect, (1, 1, 1, 1), 1)
        pts, nor, s = M.perfil_circulo(0.5, 12)
        corrido = M.barrido_camino([(0, 0, 0), (10, 0, 0)], (pts + [0.2, 0.0], nor, s), (1, 1, 1, 1), 1)
    assert len(tri) and len(corrido) and not inst.arreglos()
    assert len(M.barrido_camino([(0, 0, 0), (10, 0, 0)], M.perfil_circulo(0.5, 12), (1, 1, 1, 1), 1))   # fuera: triángulos


def test_mallas_unidad():
    assert I3.malla_unidad(I3.SEG, 12).shape == (72, 3)
    assert I3.malla_unidad(I3.TAPA, 16).shape == (48, 3)
    assert I3.malla_unidad(I3.ESFERA, (6, 10)).shape == (360, 3)
    assert I3.malla_unidad(I3.SEG, 12).dtype == np.float32


def _escena(instanciar=True):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from nucleo import modelo3d
    from ui.dialogos import vista3d_dialog
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ESC); w._redraw()
    dlg = vista3d_dialog.Vista3DDialog(w)
    datos = dlg._datos()
    if instanciar:
        esc = modelo3d.construir(**datos)
    else:                                             # el camino de antes: todo en triángulos
        sin = contextlib.nullcontext
        viejo = M.instanciar
        M.instanciar = lambda col: sin(col)
        try:
            esc = modelo3d.construir(**datos)
        finally:
            M.instanciar = viejo
    dlg.close(); w._dirty = False
    return esc


def test_misma_escena_con_mucha_menos_memoria():
    from scipy.spatial import cKDTree
    nueva, vieja = _escena(True), _escena(False)
    assert not vieja.instancias and nueva.instancias
    assert np.array_equal(nueva.origen, vieja.origen) and np.array_equal(np.asarray(nueva.caja), np.asarray(vieja.caja))
    assert np.array_equal(nueva.suelo, vieja.suelo) and np.array_equal(nueva.transparentes, vieja.transparentes)
    assert nueva.cuentas == vieja.cuentas and nueva.objetos.keys() == vieja.objetos.keys()
    A = vieja.opacos.reshape(-1, 45).astype(float)
    B = nueva.opacos.reshape(-1, 45).astype(float)
    assert A.shape == B.shape
    clave = lambda T: np.column_stack([T[:, [0, 1, 2, 15, 16, 17, 30, 31, 32, 3, 4, 5]], T[:, 10] * 1e6])  # noqa: E731
    _d, j = cKDTree(clave(B)).query(clave(A))
    assert (np.bincount(j, minlength=len(B)) == 1).all()                # cada triángulo, su par
    dif = np.abs(A - B[j]).reshape(-1, 3, 15)
    assert dif[:, :, 0:3].max() < 1e-3                                  # posición (redondeo float32)
    assert dif[:, :, 6:11].max() == 0                                   # color e id idénticos
    assert nueva.bytes_gpu * 10 < vieja.bytes_gpu                       # ≥ 10 veces menos memoria


def test_sin_instancing_se_puede_forzar(monkeypatch):
    from ui.comun import visor3d_instancias as VI
    monkeypatch.setenv("PDFCAD_SIN_INSTANCING", "1")
    assert VI.soportado(object()) is False


def test_cotas_memorizadas_y_buzones_por_celdas_dan_lo_mismo():
    import random
    from nucleo import model_ops, modelo3d
    random.seed(5)
    pipes = []
    for i in range(40):
        x, y = random.uniform(0, 600), random.uniform(0, 600)
        pts = [(x, y)]
        for _k in range(random.randint(1, 8)):
            x += random.uniform(-80, 80); y += random.uniform(-80, 80)
            pts.append((round(x), round(y)))           # vértices compartidos entre utilidades
        p = dict(layer="DRENAJE", pts=pts, inv_start=random.uniform(-9, -3), inv_end=random.uniform(-9, -3))
        if i % 3 == 0 and len(pts) > 2:
            p["vertex_inv_out"] = {1: -4.5}; p["vertex_inv_in"] = {1: -4.0}
        pipes.append(p)
    sin = [[model_ops.cotas_tramo(p, k) for k in range(len(p["pts"]) - 1)] for p in pipes]
    with model_ops.memo_cotas():
        con = [[model_ops.cotas_tramo(p, k) for k in range(len(p["pts"]) - 1)] for p in pipes]
        con2 = [[model_ops.cotas_tramo(p, k) for k in range(len(p["pts"]) - 1)] for p in pipes]
    assert sin == con == con2
    tol = 3.0
    indice = modelo3d._IndiceVertices(pipes, tol)
    for p in pipes:
        for x, y in p["pts"]:
            assert modelo3d._soleras_en(pipes, x, y, tol, indice) == modelo3d._soleras_en(pipes, x, y, tol)
