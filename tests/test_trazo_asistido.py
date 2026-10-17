"""Dibujo a mano con ángulos en pasos de 0.25° y lo que vino con él (pedidos 2026-10-15/16):
la línea elástica con imanes para seguir recto / 45° / 90°, la validación (en el lienzo no hay
ángulos como 45.684°), el vértice movido en el paso y con su ángulo, Enter dos veces sale del
modo, el vértice de eléctrico/telecom elegido con un clic → «Cambiar a curva», las etiquetas
T1/T2 que no se solapan, más zoom y la Vista 3D que no recrea la ventana principal."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import angulos, trazo_asistido as TA  # noqa: E402


def _en_paso(pts):
    """Cada quiebre de la polilínea es múltiplo de 0.25° (± 1e-6°)."""
    for a, v, b in zip(pts, pts[1:], pts[2:]):
        giro = (TA.rumbo(v, b) - TA.rumbo(a, v)) % 360.0
        assert TA.en_paso(giro), (a, v, b, giro)
    return True


# ─────────────────────────── núcleo puro ───────────────────────────

def test_cuantizar_en_pasos_de_un_cuarto_de_grado():
    assert TA.cuantizar(45.684) == pytest.approx(45.75)
    assert TA.cuantizar(30.1) == pytest.approx(30.0)
    assert TA.cuantizar(359.95) == pytest.approx(0.0)
    assert TA.cuantizar(12.4, base=0.1) == pytest.approx(12.35)        # contando desde otra utilidad
    assert TA.en_paso(22.5) and not TA.en_paso(22.6)
    assert TA.unitario(90.0) == (0.0, 1.0) and TA.unitario(180.0) == (-1.0, 0.0)


def test_restringir_con_y_sin_imanes():
    q, a = TA.restringir((0.0, 0.0), (100.0, 3.0))                      # sin imanes: 1.75°
    assert a == pytest.approx(1.75) and TA.en_paso(TA.rumbo((0, 0), q))
    q, a = TA.restringir((0.0, 0.0), (100.0, 3.0), 0.0, TA.imanes(0.0), tol=4.0)
    assert q == (100.0, 0.0) and a == 0.0                               # imán: horizontal EXACTA
    q, a = TA.restringir((0.0, 0.0), (100.0, 9.0), 0.0, TA.imanes(0.0), tol=4.0)
    assert a == pytest.approx(5.25)                                     # lejos del imán: el paso


def test_deslizar_el_punto_anterior_para_llegar_exacto():
    prev, p0, T = (0.0, 0.0), (100.0, 0.0), (180.0, 61.3)
    p0n = TA.deslizar_inicio(prev, p0, T, 0.0)
    assert p0n[1] == 0.0 and abs(p0n[0] - 100.0) < 2.0                 # por su recta, unas décimas
    assert TA.en_paso(TA.rumbo(p0n, T))
    assert TA.deslizar_inicio(prev, p0, (200.0, 100.0), 0.0) is None    # ya a 45°: no hace falta


def test_arrastre_en_paso():
    pts = [(0.0, 0.0), (100.0, 0.0), (200.0, 37.0), (300.0, 37.0)]
    v = TA.arrastre_en_paso(pts, 1, (103.0, 1.7), tol=20.0)
    assert _en_paso([pts[0], v, pts[2], pts[3]])
    assert math.hypot(v[0] - 103.0, v[1] - 1.7) < 2.0
    punta = TA.arrastre_en_paso(pts, 3, (310.0, 39.0), tol=20.0)
    assert _en_paso([pts[1], pts[2], punta])


def test_validacion_encuentra_quiebres_y_uniones_fuera_del_paso():
    a = math.radians(45.684)
    torcida = dict(layer="AGUA", pts=[(0, 0), (100, 0), (100 + 100 * math.cos(a), 100 * math.sin(a))])
    buena = dict(layer="AGUA", pts=[(0, 200), (100, 200), (100 + 100 * math.cos(math.radians(45.75)),
                                                        200 + 100 * math.sin(math.radians(45.75)))])
    f = angulos.quiebres([torcida, buena])
    assert len(f) == 1 and f[0].pipe == 0 and f[0].vertice == 1
    assert f[0].angulo == pytest.approx(45.684, abs=1e-6) and f[0].cercano == pytest.approx(45.75)
    b = math.radians(80.3)                                              # punta a mitad de otra a 80.3°
    rama = dict(layer="AGUA", pts=[(50 - 100 * math.cos(b), 200 + 100 * math.sin(b)), (50, 200)])
    u = angulos.uniones([buena, rama], ft_per_px=0.1)
    assert len(u) == 1 and u[0].otra == 0 and u[0].angulo == pytest.approx(99.7, abs=1e-6)
    assert angulos.texto(45.684) == "45.684°" and angulos.texto(45.0) == "45°"
    av = angulos.avisos([torcida], 0.1)
    assert av[0].clase == "angulo" and "45.684°" in av[0].mensaje and "45.75°" in av[0].mensaje


def test_etiquetas_de_tramo_no_se_solapan():
    from ui.comun import etiquetas_tramo as ET
    # tramos cortos y juntos: antes las etiquetas de 24 px se montaban
    pts = [(0, 0), (30, 0), (30, 12), (60, 12), (60, 20), (300, 20)]
    tramos = [(f"T{i + 1}", pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    puestas = ET.ubicar(tramos)
    assert [p[0] for p in puestas] == ["T1", "T2", "T3", "T4", "T5"]
    rects = []
    for texto, mx, my, dx, dy, px in puestas:
        w, h = len(texto) * ET.ANCHO_LETRA * px, px
        rects.append(ET._rect(mx + dx, my + dy, w, h))
    assert all(ET._solape(r, s) == 0 for i, r in enumerate(rects) for s in rects[i + 1:])
    assert puestas[1][5] < ET.PX_MAX and puestas[4][5] == ET.PX_MAX     # el chico, chico; el largo, como antes
    # en pantalla no pasa de TOPE_PX
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    it = ET.EtiquetaTramo("T1", "#ff0000", 24, 0, -20)
    assert it.factor(1.0) == pytest.approx(ET.TOPE_PX / 24) and it.factor(0.5) == 1.0


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
    w.resize(1400, 900)
    hoja = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=40.0, scale_ft_per_pt=40 / 72.0,
                unit="in", landscape=True)
    w.blank_canvas = True
    w.paper = dict(hoja)
    w._load_blank_page(hoja)
    w.snap = False                      # hoja en blanco: sin imán a la tinta
    w.canvas.resetTransform()           # 1 px de pantalla = 1 px de la hoja (imanes de 8 px)
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _clic(w, x, y, boton=None):
    from PySide6 import QtCore
    w.on_click(x, y, boton or QtCore.Qt.LeftButton)


def test_dibujo_en_pasos_y_con_imanes_sin_anillo(win):
    win.set_mode("pipe")
    n_undo = len(win._undo)
    _clic(win, 200, 300)
    assert not hasattr(win, "_anillo")                                  # ya no hay anillo
    _clic(win, 603, 297.5)            # a 2.5 px de la horizontal: imán → horizontal EXACTA
    _clic(win, 601, 704)              # casi vertical
    _clic(win, 1000, 1000)            # 36.6° del tramo anterior → en el paso
    pts = win.cur_pts
    assert pts[1] == (603, 300) and pts[2][0] == 603
    assert _en_paso(pts)
    assert not TA.en_paso(TA.rumbo(pts[2], pts[3]), paso=45.0)          # no lo obliga a 45°
    assert "0.25°" in win.lbl_mode.text()
    _clic(win, 1100, 900, __import__("PySide6").QtCore.Qt.RightButton)  # clic derecho: termina, como antes
    assert len(win.pipes) == 1 and len(win.pipes[0]["pts"]) == 4
    assert len(win._undo) == n_undo + 5                                 # 4 puntos + terminar
    assert not win._angulos_fuera                                       # nada fuera del paso


def test_enter_termina_y_otro_enter_sale_del_modo(win):
    win.set_mode("pipe")
    _clic(win, 200, 300); _clic(win, 500, 300)
    win._on_enter()
    assert len(win.pipes) == 1 and win.mode == "pipe"                   # termina la utilidad
    win._on_enter()
    assert win.mode == "idle"                                           # otro Enter: sale del modo
    win.toggle_erase()
    win._on_enter()
    assert win.mode == "idle"


def test_linea_elastica_con_giro_validado(win):
    win.set_mode("pipe")
    _clic(win, 200, 300)
    win._update_coords(500, 360)
    l = win._trazo_items[0].line()
    assert (l.x1(), l.y1()) == (200, 300) and TA.en_paso(TA.rumbo((200, 300), (l.x2(), l.y2())))
    _clic(win, 500, 360)
    assert win._trazo_items == []
    win._update_coords(700, 500)
    texto = win._trazo_items[1].childItems()[0].text()
    assert "giro" in texto and "✓" in texto


def test_llega_exacto_a_otra_utilidad_sin_romper_el_paso(win):
    win.pipes.append(dict(layer=win.active_layer(), pts=[(600.0, 100.0), (640.0, 700.0)], ab=False, diam=12.0))
    win._refresh_lists(); win._redraw()
    win.set_mode("pipe")
    _clic(win, 200, 300)
    _clic(win, 400, 302)
    _clic(win, 642, 704)                                                 # extremo de la otra: EXACTO
    pts = win.cur_pts
    assert pts[-1] == (640.0, 700.0)
    assert pts[1][1] == 300 and abs(pts[1][0] - 400) < 8                 # el anterior se corrió por su recta
    assert _en_paso(pts)
    win.finish_pipe()
    _clic(win, 200, 500)                                                 # sobre un TRAMO: el cruce
    x_tramo = 600 + 40 * (500 - 100) / 600
    _clic(win, x_tramo + 3, 503)
    assert win.cur_pts[-1][1] == 500 and win.cur_pts[-1][0] == pytest.approx(x_tramo)


def test_extender_desde_un_vertice_cuenta_desde_la_utilidad(win):
    a = math.radians(30.1)                                                # utilidad «girada» 30.1°
    win.pipes.append(dict(layer="ELECTRICO", pts=[(100.0, 100.0), (100 + 300 * math.cos(a), 100 + 300 * math.sin(a))],
                          ab=False, diam=4.0))
    win._refresh_lists(); win._show_tab(0); win.pipe_list.setCurrentRow(0)
    win.chk_ext_same.setChecked(True)
    win._start_extension(0, 1)
    assert win.mode == "pipe"
    fin = win.pipes[0]["pts"][1]
    _clic(win, fin[0] + 150, fin[1] + 3)
    win.finish_pipe()
    assert _en_paso(win.pipes[0]["pts"])


def test_mover_un_vertice_queda_en_el_paso_y_muestra_su_angulo(win):
    win.pipes.append(dict(layer="AGUA", pts=[(100.0, 100.0), (400.0, 100.0), (400.0, 400.0), (700.0, 400.0)],
                          ab=False, diam=8.0))
    win._refresh_lists(); win._show_tab(0); win.pipe_list.setCurrentRow(0)
    win.set_mode("move")
    win.begin_move(400.0, 100.0)
    win.do_move(431.0, 87.3)
    texto = win._trazo_items[0].childItems()[0].text()
    assert texto.startswith("giro") and "✓" in texto and " / " in texto
    win.end_move()
    assert win._trazo_items == []
    assert _en_paso(win.pipes[0]["pts"])
    assert not win._angulos_fuera


def test_los_angulos_fuera_del_paso_se_validan_sin_mostrarse(win):
    a = math.radians(45.684)
    win.pipes.append(dict(layer="AGUA", pts=[(100.0, 100.0), (400.0, 100.0),
                                             (400 + 200 * math.cos(a), 100 + 200 * math.sin(a))],
                          ab=False, diam=8.0))
    win._refresh_lists(); win._redraw()
    assert len(win._angulos_fuera) == 1 and "45.684°" in win._angulos_fuera[0].mensaje
    assert not [a for a in win._normas_avisos if a.clase == "angulo"]     # ni insignia ni contador


def test_clic_en_un_vertice_electrico_y_cambiar_a_curva(win):
    win.pipes.append(dict(layer="ELECTRICO", pts=[(100.0, 100.0), (600.0, 100.0), (600.0, 600.0)],
                          ab=False, diam=4.0))
    win._rebuild_structures(); win._refresh_lists(); win._redraw()
    assert not win.structures
    _clic(win, 602, 98)                                                  # clic sobre el vértice
    assert win.sel_pipe == 0 and win._vertice_elegido() == (0, 1)
    assert win.box_vertice.isVisibleTo(win.gprop) and win.btn_vertice_curva.text().strip() == "Cambiar a curva"
    _clic(win, 300, 101)                                                 # clic en la línea: lo suelta
    assert win._vertice_elegido() is None and not win.box_vertice.isVisibleTo(win.gprop)
    _clic(win, 602, 98)
    win.btn_vertice_curva.click()
    cv = [s for s in win.structures if s.get("curve")]
    assert len(cv) == 1 and (cv[0]["x"], cv[0]["y"]) == (600.0, 100.0)


def test_se_puede_acercar_mas():
    from ui.comun import canvas
    assert canvas._ZOOM_MAX >= 400


def test_vista3d_no_es_hija_de_la_ventana_principal(win):
    from ui.dialogos import vista3d_dialog
    win.pipes.append(dict(layer="AGUA", pts=[(100.0, 100.0), (500.0, 100.0)], ab=False, diam=8.0,
                          inv_start=-4.0, inv_end=-4.0))
    win._refresh_lists()
    dlg = vista3d_dialog.abrir(win)
    try:
        assert dlg.parent() is None and dlg.win is win      # sin padre Qt: no recrea la principal
    finally:
        dlg.close()
