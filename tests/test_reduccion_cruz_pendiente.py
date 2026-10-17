"""Pedidos del usuario 2026-10-16: cruz en un cruce en X a mitad de tramo (también con diámetros
distintos), reducción en 3D (recta y codo reductor como `ReduccionSolida.cs`), pendiente de la
utilidad en el panel (una, o la de cada tramo si cambia) y rótulos de pendientes/ángulos en 3D."""
import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import accesorios as acc  # noqa: E402
from nucleo import modelo3d, reducciones3d as R3, rotulos3d  # noqa: E402

FT = 0.25


def _p(pts, d, z=-4.0, z1=None, capa="AGUA"):
    return dict(layer=capa, pts=pts, ab=False, diam=d, inv_start=z, inv_end=z if z1 is None else z1, name="")


def _z(pipes):
    return lambda i, k, x, y: pipes[i]["inv_start"]


def test_cruz_en_x_a_mitad_de_tramo_con_diametros_distintos():
    pipes = [_p([(0, 100), (400, 100)], 12.0), _p([(200, 0), (200, 400)], 8.0)]
    nodos = acc.accesorios(pipes, _z(pipes), FT)
    assert [(n["tipo"], round(n["angulo"], 3), n["pipes"]) for n in nodos] == [("cruz", 90.0, [0, 1])]
    pipes[1]["inv_start"] = pipes[1]["inv_end"] = -6.0            # a otra cota: se cruzan sin unirse
    assert acc.accesorios(pipes, _z(pipes), FT) == []
    pipes = [_p([(0, 100), (400, 100)], 12.0), _p([(200, 0), (200, 100), (300, 400)], 8.0)]
    assert all(n["tipo"] != "cruz" for n in acc.accesorios(pipes, _z(pipes), FT))   # vértice de una sola


def test_uniones_rectas_para_la_reduccion():
    pipes = [_p([(0, 0), (300, 0)], 12.0), _p([(300, 0), (600, 0)], 8.0)]
    rectos = []
    assert acc.accesorios(pipes, _z(pipes), FT, rectos=rectos) == []
    assert rectos == [{"x": 300.0, "y": 0.0, "red": "AGUA", "capa": "AGUA", "pipes": [0, 1]}]
    assert acc.accesorios(pipes, _z(pipes), FT) == []            # sin la lista, lo de siempre


def test_reduccion_como_el_plugin():
    u = np.array([1.0, 0.0, 0.0])
    d1, d2 = 1.0, 8 / 12.0
    malla, recorte = R3.reduccion((0.5, 0.0, 0.0), (0.0, 0.0, -1 / 12.0), u, d1, d2, 50.0, (1, 1, 1, 1), 7)
    assert len(malla)
    # ReduccionSolida.cs: r1 = cerca + u·(s0 + 1.25·d1); punta = r1 + u·(0.45·d2·0.75 − 0.12)
    assert recorte == pytest.approx(0.5 + 1.25 + 0.45 * d2 * 0.75 - 0.12)
    assert R3.reduccion((0.5, 0, 0), (0, 0, 0), u, d1, d2, 1.0, (1, 1, 1, 1), 7) is None   # tubo chico corto


def _escena(pipes):
    return modelo3d.construir(pipes, [], FT)


def test_vista3d_reduccion_recta_codo_reductor_y_cruz():
    a45 = math.radians(45)
    pipes = [_p([(0, 0), (400, 0)], 12.0), _p([(400, 0), (800, 0)], 8.0),
             _p([(0, 600), (400, 600)], 12.0), _p([(400, 600), (400 + 400 * math.cos(a45), 600 - 400 * math.sin(a45))], 8.0),
             _p([(1200, 0), (1200, 600)], 12.0), _p([(900, 300), (1500, 300)], 8.0)]
    esc = _escena(pipes)
    accs = sorted((o["acc_tipo"], tuple(o["pipes"])) for o in esc.objetos.values() if o["tipo"] == "accesorio")
    assert accs == [("codo", (2, 3)), ("cruz", (4, 5)), ("reduccion", (0, 1))]
    # el codo reductor suma la reducción (cono: triángulos, no instancias); el codo de un solo
    # diámetro no lleva nada fuera de las instancias
    codo = lambda d: _escena([pipes[2], dict(pipes[3], diam=d)])   # noqa: E731
    assert len(codo(8.0).base) and not len(codo(12.0).base)


def test_rotulos_de_pendientes_y_angulos():
    pipes = [_p([(0, 0), (400, 0), (600, 200)], 12.0, z=-4.0, z1=-6.0, capa="DRENAJE")]
    esc = modelo3d.construir(pipes, [], FT, ver=dict(rotulos=True))
    textos = [t for _i, _p3, t in esc.rotulos]
    largo = (400 + math.hypot(200, 200)) * FT
    assert textos == [f"{-2 / largo * 100:.2f} %"] * 2 + ["45°"]
    assert modelo3d.construir(pipes, [], FT).rotulos == []        # apagado por defecto
    assert rotulos3d.GIRO_MIN_DEG > 0


# ─────────────────────────── ventana real ───────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    hoja = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=20.0, scale_ft_per_pt=20 / 72.0,
                unit="in", landscape=True)
    w.blank_canvas = True
    w.paper = dict(hoja)
    w._load_blank_page(hoja)
    w._info = lambda *a, **k: None
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_panel_muestra_la_pendiente(win):
    win.pipes += [_p([(300, 800), (1000, 800)], 8.0, z=-3.0, z1=-3.5),
                  dict(_p([(300, 300), (700, 300), (900, 500), (1300, 500)], 12.0, z=-4.0, z1=-6.0, capa="DRENAJE"),
                       vertex_inv_out={2: -4.5}, vertex_inv_in={2: -4.5})]
    win._rebuild_structures(); win._refresh_lists(); win._redraw()
    win._show_tab(0)
    win.pipe_list.setCurrentRow(0)
    assert win.lbl_pendiente.text().startswith("Pendiente: -") and win.lbl_pendiente.text().endswith(" %")
    win.pipe_list.setCurrentRow(1)
    texto = win.lbl_pendiente.text()
    assert texto.startswith("Pendiente por tramo:") and "T1" in texto and "T3" in texto


def test_plano_cruce_en_x_es_una_cruz(win):
    win.pipes += [_p([(300, 300), (900, 300)], 12.0), _p([(600, 0), (600, 600)], 8.0)]
    win._rebuild_structures(); win._refresh_lists(); win._redraw()
    assert [a["tipo"] for a in win._accesorios] == ["cruz"]
    assert not getattr(win, "_conflictos", [])                    # ya no es un choque
