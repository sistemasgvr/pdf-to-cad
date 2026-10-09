"""Revisar y limpiar el dibujo antes de exportar (limpieza.py + limpieza_tramos.py) y
la ventana real (Herramientas → «Revisar y limpiar el dibujo…», y al exportar)."""
import copy
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import limpieza, limpieza_tramos as LT  # noqa: E402

FT = 0.1                                    # pies por px: 1 ft = 10 px


def _p(pts, layer="ELECTRICO", **k):
    d = dict(layer=layer, pts=[tuple(q) for q in pts], name="", diam=12.0)
    d.update(k)
    return d


def _cv(x, y, r_ft, net="conduit"):
    return {"cod": "CV-1", "x": float(x), "y": float(y), "curve": True, "radius_ft": r_ft,
            "net": net, "world": False, "hidden": False, "rim": None, "sump": None, "part": "", "part_size": ""}


# ─────────────────────────── tramos diminutos ───────────────────────────

def test_tramo_diminuto_entre_dos_quiebres_se_quita_un_vertice():
    pipes = [_p([(0, 0), (100, 0), (101, 0.5), (200, 0.5)], vertex_kinds=["end", "bend", "bend", "end"],
                vertex_inv_out={1: 9.0, 2: 8.9}, vertex_inv_in={1: 9.1, 2: 9.0})]
    res = limpieza.limpiar(pipes, [], FT)
    assert [(c.tipo, c.arreglado, c.como) for c in res.cambios] == [("tramo", True, "vertice")]
    p = pipes[0]
    assert len(p["pts"]) == 3 and len(p["vertex_kinds"]) == 3
    assert set(p["vertex_inv_out"]) == {1} and set(p["vertex_inv_in"]) == {1}   # datos por vértice corridos
    assert not LT.diminutos(pipes, [], 0, FT)


def test_la_curva_se_estira_hasta_la_T_que_no_se_puede_quitar():
    # La utilidad nace en una T (vértice de otra) y su curva arranca 0.1 ft después.
    pipes = [_p([(0, 0), (50, 0), (50, 50)]), _p([(0, -30), (0, 30)])]
    cv = _cv(50, 0, 4.9)                                    # T = 49 px → recto de 1 px = 0.1 ft
    res = limpieza.limpiar(pipes, [cv], FT)
    assert [(c.tipo, c.como) for c in res.arreglos] == [("tramo", "curva")]
    assert cv["radius_ft"] == pytest.approx(5.0)
    assert pipes[0]["pts"][0] == (0, 0)                     # la T no se mueve
    _cv_, geos = LT.curvas(pipes, [cv], 0, FT)
    assert math.dist(geos[1]["t1"], (0, 0)) * FT < 0.005 and not geos[1]["clamped"]


def _cv_n(cod, x, y, r_ft):
    s = _cv(x, y, r_ft)
    s["cod"] = cod
    return s


def _electrico_47():
    """La utilidad #52 del proyecto de prueba (red ELECTRICO-47 en Civil 3D, coordenadas
    reales): nace en una T de la #50 y sigue una curva compuesta. Salían dos tuberías
    diminutas: «(19)», 0.07 ft entre la T y el ancla de la 1.ª curva, y «(20)», 0.31 ft
    rectos entre la 1.ª curva y la curva pequeña (r = 1.42 ft)."""
    ft = 0.07937
    pasa = _p([(1000.0, 1928.6), (1040.32, 1928.6), (1080.0, 1928.6)])
    ramal = _p([(1040.32, 1928.6), (1040.34, 1929.48), (1039.68, 1937.8), (1040.76, 1946.07),
                (1041.81, 1949.85), (1043.28, 1953.6), (1046.22, 1956.36), (1101.24, 2011.38)],
               vertex_kinds=["tee", "bend", "fillet", "bend", "bend", "fillet", "bend", "end"],
               fillets={"2": 6.291, "5": 1.419})
    return ft, [pasa, ramal], [_cv_n("CV-45", 1039.68, 1937.8, 6.291), _cv_n("CV-46", 1043.28, 1953.6, 1.419)]


def _dibujo(pipes, structs, i, ft):
    """Lo que se dibuja (y construye el plugin): rectas y el arco de cada curva."""
    pts = pipes[i]["pts"]
    _cv_, geos = LT.curvas(pipes, structs, i, ft)
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        out.extend(geos[k]["arc"] if k in geos else [pts[k]])
    return out + [pts[-1]]


def _lejos(a, b):
    """Lo más que se aparta un punto de a de la polilínea b (px)."""
    return max(min(math.dist(q, LT.proyeccion(q, u, v)[0]) for u, v in zip(b, b[1:])) for q in a)


def test_curva_compuesta_sin_tuberias_diminutas_y_sin_cambiar_el_dibujo():
    ft, pipes, structs = _electrico_47()
    antes = _dibujo(pipes, structs, 1, ft)
    assert [round(L, 2) for *_x, L in LT.diminutos(pipes, structs, 1, ft)] == [0.07, 0.31]
    res = limpieza.limpiar(pipes, structs, ft)
    assert [(c.tipo, c.como) for c in res.arreglos] == [("tramo", "ancla"), ("tramo", "ancla")]
    ramal = pipes[1]
    assert not LT.diminutos(pipes, structs, 1, ft)
    assert ramal["pts"][0] == (1040.32, 1928.6) and len(ramal["pts"]) == 6      # se fueron las dos anclas
    assert ramal["vertex_kinds"] == ["tee", "fillet", "bend", "fillet", "bend", "end"]
    assert ramal["fillets"] == {1: structs[0]["radius_ft"], 3: structs[1]["radius_ft"]}
    _cv1, g1 = LT.curvas(pipes, structs, 1, ft)
    assert math.dist(g1[1]["t1"], ramal["pts"][0]) * ft < 0.005                  # la 1.ª curva arranca en la T
    assert math.dist(g1[1]["t2"], g1[3]["t1"]) * ft < 0.005                      # y la 2.ª, donde termina la 1.ª
    assert not g1[1]["clamped"] and not g1[3]["clamped"]
    for s, (x, y) in zip(structs, [(1039.68, 1937.8), (1043.28, 1953.6)]):
        assert math.dist((s["x"], s["y"]), (x, y)) * ft <= LT.ESQUINA_MAX_FT
    despues = _dibujo(pipes, structs, 1, ft)
    assert _lejos(despues, antes) * ft < 0.05 and _lejos(antes, despues) * ft < 0.05   # el dibujo no cambia
    assert pipes[0]["pts"] == [(1000.0, 1928.6), (1040.32, 1928.6), (1080.0, 1928.6)]   # la otra no se toca


def _esquina_sobre_otra(otra):
    # Curva de 90° que nace en una T: su inicio quedó 0.2 ft después de la T; la otra
    # tangencia ya cae en el vértice siguiente. La esquina (100, 0) está sobre `otra`.
    pipes = [_p([(0, 0), (100, 0), (100, 98)]), _p([(0, -30), (0, 30)]), otra]
    cv = _cv(100, 0, 9.8)
    return pipes, [cv], cv


def test_esquina_sobre_otra_utilidad_se_corre_si_sigue_sobre_ella():
    pipes, structs, cv = _esquina_sobre_otra(_p([(100, -50), (100, 200)], layer="AGUA"))
    res = limpieza.limpiar(pipes, structs, FT, tipos=["tramo"])
    assert [(c.tipo, c.como) for c in res.arreglos] == [("tramo", "esquina")]
    assert cv["x"] == pytest.approx(100.0) and -3 < cv["y"] < 0                # sobre la recta de la otra
    assert pipes[0]["pts"][1] == (cv["x"], cv["y"])
    assert not LT.diminutos(pipes, structs, 0, FT)


def test_esquina_que_se_saldria_de_otra_utilidad_queda_como_aviso():
    pipes, structs, cv = _esquina_sobre_otra(_p([(80, -50), (120, 50)], layer="AGUA"))
    res = limpieza.limpiar(pipes, structs, FT, tipos=["tramo"])
    assert [(c.tipo, c.arreglado) for c in res.cambios] == [("tramo", False)]
    assert (cv["x"], cv["y"]) == (100.0, 0.0)


def test_buzon_visible_no_se_quita_queda_como_aviso():
    bz = lambda x, y: {"cod": "BZ-1", "x": x, "y": y, "net": "gravity", "hidden": False, "world": False}  # noqa: E731
    pipes = [_p([(0, 0), (50, 0), (51, 0.6), (100, 0.6)], layer="DRENAJE")]
    res = limpieza.limpiar(pipes, [bz(50, 0), bz(51, 0.6)], FT)
    assert [(c.tipo, c.arreglado) for c in res.cambios] == [("tramo", False)]
    assert len(pipes[0]["pts"]) == 4


def test_segunda_pasada_no_encuentra_nada():
    ft, pipes, structs = _electrico_47()
    pipes.append(_p([(0, 0), (100, 0), (101, 0.5), (200, 0.5)]))
    limpieza.limpiar(pipes, structs, ft)
    assert not limpieza.limpiar(pipes, structs, ft).arreglos


# ─────────────────────────── puntas ───────────────────────────

def test_punta_que_no_llega_a_la_T_se_une_a_la_linea():
    pipes = [_p([(0, 0), (100, 0)]), _p([(50, 6), (50, 100)])]          # 0.6 ft corta
    res = limpieza.limpiar(pipes, [], FT, tipos=["punta"])
    assert [(c.tipo, c.pipe, c.arreglado) for c in res.cambios] == [("punta", 1, True)]
    assert pipes[1]["pts"][0] == (50.0, 0.0)


def test_punta_se_une_al_vertice_mas_cercano():
    pipes = [_p([(0, 0), (100, 0), (100, 100)]), _p([(105, 2), (200, 2)])]
    limpieza.limpiar(pipes, [], FT, tipos=["punta"])
    assert pipes[1]["pts"][0] == (100.0, 0.0)


@pytest.mark.parametrize("otra", [
    _p([(0, 26), (100, 26)]),                                # paralela de al lado (banco de líneas)
    _p([(100, 26), (200, 26)]),                              # paralela corrida
    _p([(50, 6), (50, 100)], layer="AGUA"),                  # otro tipo
    _p([(50, 6), (50, 100)], ab=True),                       # abandonada contra activa
    _p([(50, 5), (50, -100)]),                               # a 1.5 ft: no es «casi»
])
def test_puntas_que_no_se_tocan(otra):
    base = _p([(0, 20), (100, 20)])
    pipes = [base, otra]
    antes = copy.deepcopy(pipes)
    limpieza.limpiar(pipes, [], FT, tipos=["punta"])
    assert pipes == antes


def test_punta_lleva_su_caja():
    caja = {"cod": "CAJA-1", "x": 50.0, "y": 6.0, "net": "conduit", "hidden": False, "world": False}
    pipes = [_p([(0, 0), (100, 0)]), _p([(50, 6), (50, 100)])]
    limpieza.limpiar(pipes, [caja], FT, tipos=["punta"])
    assert (caja["x"], caja["y"]) == (50.0, 0.0)


# ─────────────────────────── sobrantes y avisos ───────────────────────────

def test_utilidad_corta_se_borra_salvo_protegida():
    pipes = [_p([(0, 0), (300, 0)]), _p([(500, 0), (505, 0)]), _p([(700, 0), (705, 0)])]
    res = limpieza.limpiar(pipes, [], FT, protegidas={2})
    assert res.borrar == [1]
    assert [c.pipe for c in res.de("corta")] == [1]


def test_repetida_se_queda_la_que_tiene_datos():
    a = _p([(0, 0), (100, 0), (100, 80)])
    b = _p([(100, 80), (100, 0), (0, 0)], pipe_family="fam", pipe_size="8 in")   # al revés
    res = limpieza.limpiar([a, b, _p([(0, 0), (100, 0), (100, 80)], layer="AGUA")], [], FT)
    assert res.borrar == [0]                                 # la de otro tipo no es repetida


def test_suelta_corta_es_solo_aviso():
    pipes = [_p([(0, 0), (300, 0)]), _p([(0, 100), (30, 100)])]
    res = limpieza.limpiar(pipes, [], FT)
    assert [(c.tipo, c.pipe, c.arreglado) for c in res.cambios] == [("suelta", 1, False)]
    assert not res.borrar


def test_sin_escala_no_hace_nada():
    pipes = [_p([(0, 0), (1, 0)])]
    assert not limpieza.limpiar(pipes, [], 0.0).cambios


# ─────────────────────────── ventana ───────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    from traduccion import i18n, i18n_core
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 0.35, 3.5                              # 0.1 ft por px
    w.avisos = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda _p, _t, msg, *a: w.avisos.append(msg))
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _dialogo_falso(monkeypatch, accion, abiertos):
    from ui.dialogos import limpieza_dialog

    class Falso(limpieza_dialog.LimpiezaDialog):
        def exec(self):
            abiertos.append([self.arbol.topLevelItem(k).text(0) for k in range(self.arbol.topLevelItemCount())])
            self._cerrar(accion) if accion != "cancelar" else self.reject()
            return 1
    monkeypatch.setattr(limpieza_dialog, "LimpiezaDialog", Falso)


def test_ventana_arregla_y_se_deshace(win, monkeypatch):
    abiertos = []
    _dialogo_falso(monkeypatch, "arreglar", abiertos)
    win.pipes = [_p([(100, 100), (400, 100), (401, 100.5), (600, 100.5)]), _p([(300, 106), (300, 300)]),
                 _p([(900, 900), (905, 900)])]
    win._refresh_lists()
    assert win.revisar_dibujo() is True
    assert abiertos and any("diminutos" in t for t in abiertos[0])
    assert len(win.pipes) == 2                               # la corta se borró
    assert len(win.pipes[0]["pts"]) == 3 and win.pipes[1]["pts"][0] == (300.0, 100.0)
    win.undo()
    assert len(win.pipes) == 3 and len(win.pipes[0]["pts"]) == 4


def test_al_exportar_solo_pregunta_si_hay_algo_que_arreglar(win, monkeypatch):
    abiertos = []
    _dialogo_falso(monkeypatch, "cancelar", abiertos)
    win.pipes = [_p([(100, 100), (400, 100)])]
    assert win.revisar_dibujo(exportando=True) is True and not abiertos
    win.pipes.append(_p([(250, 106), (250, 300)]))           # punta casi unida
    assert win.revisar_dibujo(exportando=True) is False and abiertos   # «Cancelar» = no exporta
    assert win.pipes[1]["pts"][0] == (250, 106)              # sin arreglar no cambia nada
