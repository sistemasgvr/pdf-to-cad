"""Perfil longitudinal con decenas de miles de utilidades (estrés del 2026-11-18, proyecto de 29 mil): el grafo de
la red comparaba cada tramo con TODAS las puntas (4–7 min con el perfil abierto, en cada deshacer o cambio de
cota) y los datos buscaban cruces, buzones y accesorios recorriendo todo. Ahora por celdas y recuadros: el MISMO
grafo y los MISMOS datos que sin ellos (`CELDAS` / `RECUADROS` = False es el recorrido de antes)."""
import random

import pytest

from nucleo import perfil_datos as PD, perfil_recorrido as PR

FT = 0.1


def _red(semilla):
    """Principal en zigzag con ramales que nacen a mitad de sus tramos (T), ramales de ramales, otra red que la
    cruza a distintos ángulos y cosas lejos (que nada deben cambiar)."""
    rnd = random.Random(semilla)
    pipes = []
    x, y, pts = 0.0, 0.0, [(0.0, 0.0)]
    for _ in range(25):
        x += rnd.uniform(150, 400); y += rnd.uniform(-120, 120); pts.append((x, y))
    capa = rnd.choice(["AGUA", "ALCANTARILLADO"])
    for k in range(len(pts) - 1):              # la principal partida en varias utilidades
        pipes.append(dict(layer=capa, pts=[pts[k], pts[k + 1]], diam=8.0, inv_start=-4.0 - k * 0.1,
                          inv_end=-4.1 - k * 0.1))
    for k in range(0, len(pts) - 1, 2):        # ramales en T a mitad del tramo
        a, b = pts[k], pts[k + 1]
        t = rnd.uniform(0.3, 0.7)
        q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        fin = (q[0] + rnd.uniform(-60, 60), q[1] + rnd.choice([-1, 1]) * rnd.uniform(150, 400))
        pipes.append(dict(layer=capa, pts=[q, fin], diam=6.0, inv_start=-3.5, inv_end=-3.2))
        if rnd.random() < 0.5:                 # ramal del ramal
            m = ((q[0] + fin[0]) / 2, (q[1] + fin[1]) / 2)
            pipes.append(dict(layer=capa, pts=[m, (m[0] + 200, m[1] + 30)], diam=4.0, inv_start=-3.0, inv_end=-3.0))
    for _ in range(30):                        # otra red que cruza (y a veces solo toca un nodo)
        cx = rnd.uniform(0, x); cy = rnd.uniform(-300, 300); ang = rnd.uniform(0, 3.14)
        import math
        d = (math.cos(ang) * 500, math.sin(ang) * 500)
        pipes.append(dict(layer="GAS", pts=[(cx - d[0], cy - d[1]), (cx + d[0], cy + d[1])], diam=4.0,
                          inv_start=-2.0, inv_end=-2.5))
    for _ in range(40):                        # lejos
        cx, cy = rnd.uniform(50000, 60000), rnd.uniform(50000, 60000)
        pipes.append(dict(layer="GAS", pts=[(cx, cy), (cx + 100, cy + 50)], diam=4.0, inv_start=-2.0, inv_end=-2.0))
    estructuras = [dict(x=q[0], y=q[1], cod=f"BZ-{k}", rim=1.0, net="gravity") for k, q in enumerate(pts)]
    estructuras += [dict(x=rnd.uniform(50000, 60000), y=rnd.uniform(50000, 60000), cod="L") for _ in range(50)]
    accs = []
    for p in pipes:
        if p["diam"] == 6.0:
            accs.append(dict(x=p["pts"][0][0], y=p["pts"][0][1], tipo="tee", tronco=[0], ramal=None))
    accs += [dict(x=q[0], y=q[1], tipo="codo", angulo=12.0) for q in pts[1:-1:3]]
    accs += [dict(x=rnd.uniform(50000, 60000), y=rnd.uniform(50000, 60000), tipo="codo", angulo=5.0)
             for _ in range(50)]
    return pipes, estructuras, accs


def _grafo(g):
    return (g.nodos, [(a.pipe, a.tramo, a.t0, a.t1, a.a, a.b, a.pa, a.pb, a.largo_px) for a in g.aristas], g.de_nodo)


@pytest.mark.parametrize("semilla", range(12))
def test_grafo_con_celdas_igual_que_contra_todas_las_puntas(semilla, monkeypatch):
    pipes, _e, _a = _red(semilla)
    con = PR.construir_grafo(pipes, 0, FT)
    assert any(len(v) >= 3 for v in con.de_nodo.values())         # hay T
    monkeypatch.setattr(PR, "CELDAS", False)
    assert _grafo(con) == _grafo(PR.construir_grafo(pipes, 0, FT))


@pytest.mark.parametrize("semilla", range(12))
def test_datos_con_recuadros_iguales_que_recorriendo_todo(semilla, monkeypatch):
    pipes, estructuras, accs = _red(semilla)
    g = PR.marcar_soleras(PR.construir_grafo(pipes, 0, FT), pipes)
    rec = PR.entre(g, PR.arista_cerca(g, *pipes[0]["pts"][0], 0), PR.arista_cerca(g, *pipes[24]["pts"][1], 24))
    assert rec is not None and len(rec.pasos) > 20                # la principal entera
    con = PD.armar(pipes, estructuras, accs, rec, FT)
    monkeypatch.setattr(PD, "RECUADROS", False)
    sin = PD.armar(pipes, estructuras, accs, rec, FT)
    assert repr(con) == repr(sin)
    if semilla == 0:
        assert con.cruces                                         # la prueba sí tiene cruces


def test_la_ventana_reusa_el_grafo_si_solo_cambian_cotas(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    w = Main()
    img = QtGui.QImage(3000, 3000, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0
    w.pipes, _e, _a = _red(1)
    w._refresh_lists(); w._redraw()
    w.abrir_perfil()
    hechos = []
    real = PR.construir_grafo
    monkeypatch.setattr(PR, "construir_grafo", lambda *a, **k: hechos.append(1) or real(*a, **k))
    rec = w.perfil_desde(0, *w.pipes[0]["pts"][0])
    assert rec is not None and hechos == [1]
    w.pipes[0]["inv_start"] = -9.0                                  # solo una cota
    assert w._rec_de_anclas(*w._perfil_anclas) is not None and hechos == [1]
    assert w._perfil_grafo(0, w._ft())._z_punta                    # las soleras sí se recalculan
    x, y = w.pipes[3]["pts"][1]
    w.pipes[3]["pts"][1] = (x + 5.0, y)                             # la geometría cambió
    w._rec_de_anclas(*w._perfil_anclas)
    assert hechos == [1, 1]
    w._dirty = False; w.close()
