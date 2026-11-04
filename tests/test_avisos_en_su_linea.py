"""Cada aviso SOBRE la línea que se dibuja y solo si su utilidad está encendida (reporte del usuario 2026-11-03,
DU10: avisos de reconocimiento «fuera de la línea, sin ningún sentido»). Dos causas, medidas en su proyecto:

- la marca seguía a la vista con su capa apagada porque otra línea encendida pasaba a ≤ 2 ft (aviso del eléctrico
  #249 junto a una línea de agua: 91 de 545 con las demás capas apagadas);
- el punto salía de la polilínea de vértices, cuya esquina de una curva no está en el dibujo (el arco pasa lejos
  de ella): 86 de 774 a más de 0.05 ft de su línea, hasta 24.8 ft.
"""
import math
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

AQUI = os.path.dirname(os.path.abspath(__file__))
PRESENTACION = os.path.join(AQUI, "escenarios", "presentacion_1_3_1.digproj")
DU10 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf")
FT = 0.25                           # pies por px del lienzo en las pruebas puras


def _sin_dato(capa, pts, **kw):
    return {"layer": capa, "pts": [tuple(q) for q in pts], "diam_plano": {"estado": "sin_dato"}, **kw}


def _dist(x, y, poli):
    import geometry as G
    return min(G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1]) for a, b in zip(poli, poli[1:]))


def _codo(radio_ft=40.0):
    """Una línea con una curva justo a la mitad del recorrido: la esquina queda LEJOS del arco."""
    pipe = _sin_dato("ELECTRICO", [(0, 0), (400, 0), (400, 400)])
    cv = {"x": 400.0, "y": 0.0, "curve": True, "radius_ft": radio_ft}
    return pipe, cv


# ── el lugar: sobre lo dibujado ─────────────────────────────────────────────
def test_aviso_de_una_linea_con_curva_queda_sobre_el_arco():
    from nucleo import avisos_lugar, diametro_plano, model_ops
    pipe, cv = _codo()
    avisos = diametro_plano.avisos([pipe])
    assert (avisos[0].x, avisos[0].y) == (400.0, 0.0)              # la esquina: el arco no pasa por ella
    avisos_lugar.sobre_lo_dibujado(avisos, [pipe], [cv], FT)
    a = avisos[0]
    assert _dist(a.x, a.y, avisos_lugar.dibujo([pipe], [cv], 0, FT)) < 1e-6
    # en el arco, a medio camino: tangencias a T = r·tan(45°) = 160 px de la esquina
    geo = model_ops.fillet_geo((0, 0), (400, 0), (400, 400), 160.0)
    assert min(math.dist((a.x, a.y), q) for q in geo["arc"]) < 3.0
    assert math.dist((a.x, a.y), (400.0, 0.0)) > 50.0


def test_aviso_en_tramo_recto_no_se_mueve():
    from nucleo import avisos_lugar, diametro_plano
    pipe = _sin_dato("ELECTRICO", [(0, 0), (100, 0), (300, 0)])
    avisos = diametro_plano.avisos([pipe])
    x, y = avisos[0].x, avisos[0].y
    avisos_lugar.sobre_lo_dibujado(avisos, [pipe], [], FT)
    assert (avisos[0].x, avisos[0].y) == (x, y) and avisos[0].lugar is None


def test_aviso_de_un_accesorio_se_queda_en_el_accesorio():
    """La etiqueta del accesorio lo busca en SU punto (`accesorios_view.preparar`): no se corre a otro lado."""
    from nucleo import avisos_lugar
    from nucleo.normas_validar import Aviso
    pipe, cv = _codo()
    a = Aviso(400.0, 0.0, "accesorio", "m", 0)
    avisos_lugar.sobre_lo_dibujado([a], [pipe], [cv], FT)
    assert (a.x, a.y) == (400.0, 0.0)


def test_una_aprobacion_de_antes_sigue_valiendo():
    """La aprobación identifica el aviso por el punto de su regla: si el aviso solo se muestra en otro lugar
    (sobre el arco), lo aprobado en un proyecto guardado no vuelve a quedar pendiente."""
    from nucleo import avisos_lugar, diametro_plano, normas_aprobacion
    pipe, cv = _codo()
    a = diametro_plano.avisos([pipe])[0]
    antes = normas_aprobacion.clave(a, [pipe])
    registro = [{"clave": antes, "utilidad": 0}]
    avisos_lugar.sobre_lo_dibujado([a], [pipe], [cv], FT)
    assert (a.x, a.y) != (400.0, 0.0) and normas_aprobacion.clave(a, [pipe]) == antes
    normas_aprobacion.marcar([a], [pipe], registro)
    assert a.aprobado is registro[0]


# ── lo que muestra la ventana ───────────────────────────────────────────────
@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w._info = lambda *a, **k: None
    w.setAttribute(QtCore.Qt.WA_DontShowOnScreen)
    w.show(); w.resize(1244, 778)
    w._open_project_path(PRESENTACION)
    app.processEvents()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _poner(w, pipes, structures=()):
    w.pipes[:] = pipes
    w.structures[:] = list(structures)
    w.cross_connections = []
    w.duct_banks = []
    w.capas_apagadas = set()
    w.sel_pipe = -1
    w._redraw()


def _px(w, ft):
    return ft * w.zoom / w.scale


def _insignias(w):
    """Las insignias de RECONOCIMIENTO («?») a la vista: {(x, y): marca}. (Dos líneas juntas dan además avisos de
    separación, que son de la normativa de fábrica.)"""
    from ui.comun.avisos_view import InsigniaAviso
    out = {}
    for c in w._marcas.capas.values():
        oc = c._ocultas
        for k, m in enumerate(c.marcas):
            if isinstance(m, InsigniaAviso) and m._letra == "?" and (oc is None or not oc[k]):
                out[(c._xs[k], c._ys[k])] = m
    return out


def _apagar(w, *capas):
    w.capas_apagadas = set(capas)
    w._aplicar_capas()


def test_capa_apagada_oculta_su_aviso_aunque_otra_linea_pase_cerca(win):
    """El caso de la captura: aviso del eléctrico apagado a 1.15 ft de una línea de agua encendida."""
    L, d = 2000.0, _px(win, 1.15)
    agua = {"layer": "AGUA", "pts": [(1000.0, 1000.0 + d), (1000.0 + L, 1000.0 + d)], "diam": 8.0, "diam_elegido": True}
    _poner(win, [_sin_dato("ELECTRICO", [(1000.0, 1000.0), (1000.0 + L, 1000.0)]), agua])
    assert len(_insignias(win)) == 1
    _apagar(win, "ELECTRICO")
    assert not _insignias(win)                                    # antes seguía: el agua «era su dueña» por cercanía
    _apagar(win)
    assert len(_insignias(win)) == 1


def test_avisos_de_dos_capas_juntas_van_cada_uno_en_su_linea(win):
    """Dos avisos muy juntos de dos capas no se funden: con una capa apagada no queda el punto de la otra."""
    L, d = 2000.0, _px(win, 0.4)
    _poner(win, [_sin_dato("ELECTRICO", [(1000.0, 1000.0), (1000.0 + L, 1000.0)]),
                 _sin_dato("AGUA", [(1000.0, 1000.0 + d), (1000.0 + L, 1000.0 + d)])])
    assert len(_insignias(win)) == 2
    _apagar(win, "ELECTRICO")
    (x, y), = _insignias(win)
    assert y == pytest.approx(1000.0 + d)                         # el del agua, sobre el agua


def test_aviso_de_la_ventana_queda_sobre_la_curva_dibujada(win):
    r = 100.0
    pipe = _sin_dato("ELECTRICO", [(1000.0, 1000.0), (2000.0, 1000.0), (2000.0, 2000.0)])
    cv = {"x": 2000.0, "y": 1000.0, "curve": True, "radius_ft": r, "net": "conduit", "cod": "CV-1"}
    _poner(win, [pipe], [cv])
    (x, y), = _insignias(win)
    assert _dist(x, y, win._pipe_display_pts(win.pipes[0])) < 1e-6


def test_dibujo_es_lo_que_pinta_el_lienzo(win):
    from nucleo import avisos_lugar
    pipe = _sin_dato("ELECTRICO", [(1000.0, 1000.0), (2000.0, 1000.0), (2000.0, 2000.0), (2600.0, 2300.0)])
    cvs = [{"x": 2000.0, "y": 1000.0, "curve": True, "radius_ft": 60.0, "net": "conduit", "cod": "CV-1"},
           {"x": 2000.0, "y": 2000.0, "curve": True, "radius_ft": 0.0, "net": "conduit", "cod": "CV-2"}]
    _poner(win, [pipe], cvs)
    ft = win.scale / win.zoom
    puro, lienzo = avisos_lugar.dibujo(win.pipes, win.structures, 0, ft), win._pipe_display_pts(win.pipes[0])
    assert len(puro) == len(lienzo) > 4
    assert all(math.dist(a, b) < 1e-9 for a, b in zip(puro, lienzo))


def test_accesorio_y_conflicto_tambien_siguen_a_su_duena(win):
    """Lo mismo en las otras marcas que saben de quién son: etiqueta de accesorio (por su capa) y C-n."""
    from PySide6 import QtWidgets
    from nucleo.conflictos import Conflicto
    from ui.comun import accesorios_view, conflictos_view
    escena = QtWidgets.QGraphicsScene()
    accs = accesorios_view.dibujar(escena, [], [], 1.0, preparadas=[("Codo 45°", "GAS", None, 5.0, 5.0, "g")])
    assert accs[0]._pdfcad_duenas == frozenset({"GAS"})
    capa_de = {0: "GAS", 1: "AGUA"}.get
    c = conflictos_view.dibujar(escena, [Conflicto("C-1", "cruce", 1.0, 1.0, "m", [0, 1])], capa_de=capa_de)
    assert c[0]._pdfcad_duenas == frozenset({"GAS", "AGUA"})
    # sin saber de quién es (punto sin utilidad): se decide por cercanía, como siempre
    c2 = conflictos_view.dibujar(escena, [Conflicto("C-2", "exceso", 9.0, 9.0, "m")], capa_de=capa_de)
    assert getattr(c2[0], "_pdfcad_duenas", None) is None


def test_cruce_y_alerta_siguen_a_su_duena(win):
    """Dos líneas de gas que chocan con agua a menos de 2 ft: apagado el gas, ni su marca ni su C-n siguen."""
    d = _px(win, 1.0)
    gas_a = {"layer": "GAS", "pts": [(1000.0, 1500.0), (3000.0, 1500.0)], "diam": 8.0, "diam_elegido": True,
             "inv_start": 10.0, "inv_end": 10.0}
    gas_b = {"layer": "ELECTRICO", "pts": [(2000.0, 500.0), (2000.0, 2500.0)], "diam": 8.0, "diam_elegido": True,
             "inv_start": 10.0, "inv_end": 10.0}
    agua = {"layer": "AGUA", "pts": [(1000.0, 1500.0 + d), (3000.0, 1500.0 + d)], "diam": 8.0, "diam_elegido": True}
    _poner(win, [gas_a, gas_b, agua])
    marcas = [m for c in win._marcas.capas.values() for m in c.marcas]
    con_duena = [m for m in marcas if getattr(m, "_pdfcad_duenas", None) == frozenset({"GAS", "ELECTRICO"})]
    assert con_duena, "el choque y su C-n deben saber de quién son"
    _apagar(win, "GAS", "ELECTRICO")
    for c in win._marcas.capas.values():
        for k, m in enumerate(c.marcas):
            if m in con_duena:
                assert c._ocultas is not None and c._ocultas[k]


def test_lineas_de_capa_apagada_siguen_ocultas_al_rehacer_el_dibujo(win):
    """Rehacer la capa de líneas (abrir, editar, deshacer) las volvía a pintar: el filtro se armaba antes de
    agregar las líneas, quedaba vacío y se ignoraba hasta cambiar otra capa."""
    elec = _sin_dato("ELECTRICO", [(1000.0, 1000.0), (3000.0, 1000.0)])
    agua = _sin_dato("AGUA", [(1000.0, 1500.0), (3000.0, 1500.0)])
    _poner(win, [elec, agua])
    _apagar(win, "ELECTRICO")

    def _pintadas():
        capa = win._capa_lineas[1]
        return {i for i, k in capa.de.items() if capa._mascara is None or capa._mascara[k]}
    assert _pintadas() == {1}
    win.pipes[1]["pts"] = [(1000.0, 1600.0), (3000.0, 1600.0)]       # cambia el modelo: capa de líneas nueva
    win._redraw()
    assert _pintadas() == {1}


def test_capa_lineas_filtra_lo_que_se_agrega_despues():
    from PySide6 import QtCore, QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun.capa_lineas import CapaLineas
    capa = CapaLineas(1.0)
    capa.fijar_ocultas({7})                                          # antes de que exista la línea
    pluma = QtGui.QPen()
    capa.agregar([QtCore.QLineF(0, 0, 1, 1)], (0, 0, 1, 1), pluma, clave=7)
    capa.agregar([QtCore.QLineF(0, 0, 2, 2)], (0, 0, 2, 2), pluma, clave=8)
    capa.cerrar()
    assert capa._mascara.tolist() == [False, True]


# ── punta a punta, con un PDF real ──────────────────────────────────────────
@pytest.mark.skipif(not DU10.is_file(), reason="PDF DU10 no disponible")
def test_du10_todos_los_avisos_sobre_su_linea_dibujada(win, monkeypatch):
    """DU10 UR-602 (h. índice 4): cada aviso de utilidad, a ≤ 0.01 ft de lo que se dibuja de ella."""
    from reconocimiento import recognition as rec
    monkeypatch.setattr(type(win), "_run_recognition_wizard", lambda self: None)
    win._open_pdf_path(str(DU10))
    win._load_page(4)
    ruta = win.work_pdf_path or win.pdf_path
    win._import_recognized_pipes([rec.recognize_page(ruta, 4, utility=u, zoom=win.zoom, doc=None)
                                  for u in ("ELECTRICO", "TELECOM", "AGUA")])
    win._redraw()
    ft = win.scale / win.zoom
    assert any(a.clase == "grosor" for a in win._normas_avisos)
    assert any(win._pipe_display_pts(p) != p["pts"] for p in win.pipes), "la hoja debe tener curvas"
    fuera = []
    for a in win._normas_avisos:
        if a.clase == "accesorio" or a.pipe is None or a.pipe < 0:
            continue
        d = _dist(a.x, a.y, win._pipe_display_pts(win.pipes[a.pipe])) * ft
        if d > 0.01:
            fuera.append((a.clase, a.pipe, round(d, 3)))
    assert not fuera, fuera
