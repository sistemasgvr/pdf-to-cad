"""Tuberías de PRESIÓN siempre circulares (observación de la revisión, 2026-11-13).

El catálogo de Autodesk guarda el DIAMETER_NOMINAL de las familias de hierro dúctil a presión
(bridada, junta mecánica, push-on) como «14 in x 14 in» aunque el tubo es circular (diámetro
interior 14). La app mostraba «14 in x 14 in» en el desplegable y en la Vista 3D las dibujaba
como cajas rectangulares.
"""
from catalogo import civil_catalog as cc
from nucleo import mallas3d as M
from nucleo import modelo3d

FID = "Imperial_AWWA_Flanged|pipe-flanged-ductile iron-250 psi"


def test_etiqueta_de_presion_muestra_el_diametro():
    assert cc.etiqueta_tamano(FID, "14 in x 14 in") == "14 in"
    assert cc.etiqueta_tamano(FID, "16 in x 16 in") == "16 in"
    assert cc.etiqueta_tamano(FID, "12 in") == "12 in"
    assert cc.etiqueta_tamano(FID, "12 in x 8 in") == "12 in x 8 in"     # distintos: tal cual


def test_etiqueta_de_gravedad_no_cambia():
    # una familia de gravedad (fid = archivo, sin «|») rectangular cuadrada sigue «W x H»
    assert cc.etiqueta_tamano("Concrete Rectangular Pipe", "48 x 48 in") == "48 x 48 in"


def _tubo(layer, size):
    return {"layer": layer, "pipe_size": size, "diam": 14.0, "pts": [(0, 0), (100, 0)]}


def test_seccion_3d_de_presion_es_circular():
    perfil, alto = modelo3d.seccion(_tubo("AGUA", "14 in x 14 in"))
    circ, _ = M.perfil_circulo(14 / 24.0, modelo3d.LADOS), None
    assert len(perfil) == len(circ)
    assert abs(alto - 14 / 12.0) < 1e-9


def test_seccion_3d_de_gravedad_rectangular_sigue_igual():
    perfil, alto = modelo3d.seccion(_tubo("DRENAJE", "48 x 36 in"))
    assert len(perfil) == len(M.perfil_rect(4.0, 3.0))
    assert abs(alto - 3.0) < 1e-9


# ── Observación 2: una mala unión en un accesorio no es «Cumple» en ninguna de sus utilidades ──

def test_aviso_de_accesorio_toca_a_todas_las_utilidades_que_une(monkeypatch):
    from nucleo import normas_validar as V
    from nucleo import normas_validar_acc as VA

    def falso(por_util, pipes, todos, a, out, memo=None):
        out.append(V.Aviso(a["x"], a["y"], "accesorio", "Tee: la principal debe ser 12\"; es 24\".", 3))
    monkeypatch.setattr(VA, "_revisar", falso)
    out = [V.Aviso(0, 0, "tipo", "otro", 9)]
    VA.revisar({}, [], [], {"x": 1, "y": 2, "tipo": "tee", "pipes": [3, 7, 5], "tronco": [3, 7], "ramal": 5}, out)
    assert out[0].unidas == () and out[0].toca(9) and not out[0].toca(3)   # los de antes no cambian
    av = out[1]
    assert av.pipe == 3 and av.unidas == (3, 7, 5)                        # sigue siendo de la principal
    assert av.toca(3) and av.toca(7) and av.toca(5) and not av.toca(9)


# ── Observación 4: la Tee empalma con tubos que vienen con pendiente ──

def test_brazos_de_tee_siguen_la_pendiente_de_su_tubo():
    import numpy as np
    from nucleo import accesorios3d as A3
    baja = np.array([1.0, 0.0, -0.05])                          # 5 % de pendiente
    brazos = [A3.Brazo(dir=baja.copy(), d=1.0, eje_z=10.0), A3.Brazo(dir=-baja, d=1.0, eje_z=10.0),
              A3.Brazo(dir=np.array([0.0, 1.0, -0.02]), d=0.5, eje_z=9.75)]
    _malla, c = A3.pieza("tee", np.array([0.0, 0.0, 10.0]), brazos, (1, 1, 1, 1), 1)
    assert c[2] == 10.0                                           # la altura sigue rígida: el eje del tronco
    for b, u in zip(brazos, (baja, -baja, np.array([0.0, 1.0, -0.02]))):
        assert np.allclose(b.dir, u / np.linalg.norm(u))          # ...pero cada brazo va con su tubo
    assert brazos[2].off_z == -0.25                               # el ramal delgado, a la altura de su eje


def test_tee_3d_con_tubos_en_pendiente_quedan_coaxiales():
    from tests.test_vista3d import _p, FT, _obj
    principal = _p(pts=((0, 0), (300, 0), (600, 0)), diam=12)
    principal.update(inv_start=110.0, inv_end=100.0)              # baja de punta a punta
    ramal = _p(pts=((300, 0), (300, 300)), diam=8)
    ramal.update(inv_start=105.0, inv_end=103.0)
    esc = modelo3d.construir([principal, ramal], [], FT)
    assert _obj(esc, "accesorio")[0]["acc_tipo"] == "tee"
    ida = next(k for k, o in esc.objetos.items() if o["tipo"] == "accesorio")
    v = esc.opacos[esc.opacos[:, 10] == ida][:, :3]
    cx = v[:, 0].mean()
    izq, der = v[v[:, 0] < cx - 0.6], v[v[:, 0] > cx + 0.6]
    # el tronco BAJA hacia +x: la boca de la derecha queda más abajo que la de la izquierda
    assert der[:, 2].mean() < izq[:, 2].mean() - 0.05


# ── Observación 5: la domiciliaria que llega a una principal gruesa recibe su Tee ──

def _red(dom_fin_y, diam_principal=36.0, dom_pts=None):
    principal = {"layer": "AGUA", "pts": [(0.0, 0.0), (1000.0, 0.0)], "diam": diam_principal, "diam_elegido": True}
    dom = {"layer": "AGUA", "pts": dom_pts or [(500.0, 300.0), (500.0, dom_fin_y)], "diam": 2.0, "diam_elegido": True}
    return [principal, dom]


def test_domiciliaria_que_termina_dentro_de_la_principal_va_a_su_eje_y_lleva_tee():
    from nucleo import accesorios, limpieza
    FT = 0.1                                                     # 0.1 ft por px
    pipes = _red(12.0)                                           # punta a 1.2 ft del eje: dentro de un 36"
    assert not [a for a in accesorios.accesorios(pipes, None, FT) if a["tipo"] == "tee"]   # (antes: sin Tee)
    res = limpieza.limpiar(pipes, [], FT)
    assert pipes[1]["pts"][-1] == (500.0, 0.0)                   # sobre el eje de la principal
    assert any(c.tipo == "punta" and c.arreglado for c in res.cambios)
    tees = [a for a in accesorios.accesorios(pipes, None, FT) if a["tipo"] == "tee"]
    assert len(tees) == 1 and sorted(tees[0]["pipes"]) == [0, 1]


def test_domiciliaria_en_diagonal_sigue_su_propia_recta_hasta_el_eje():
    from nucleo import limpieza
    pipes = _red(None, dom_pts=[(400.0, 300.0), (488.0, 12.0)])  # baja inclinada, para dentro del 36"
    limpieza.limpiar(pipes, [], 0.1)
    x, y = pipes[1]["pts"][-1]
    assert abs(y) < 1e-9 and abs(x - (400.0 + 88.0 * 300.0 / 288.0)) < 1e-6


def test_punta_fuera_de_la_principal_no_se_mueve():
    from nucleo import limpieza
    pipes = _red(25.0)                                           # 2.5 ft del eje: fuera de un 36" (1.5 ft)
    limpieza.limpiar(pipes, [], 0.1)
    assert pipes[1]["pts"][-1] == (500.0, 25.0)


# ── Observación 6: el cuerpo del accesorio es más grueso que el tubo (y la campana, más) ──

def test_cuerpo_del_codo_mas_grueso_que_el_tubo():
    import numpy as np
    from nucleo import accesorios3d as A3
    for d in (0.5, 1.0, 3.0):                                     # 6", 12", 36"
        assert A3.radio_cuerpo(d) >= d / 2.0 + 0.04 - 1e-12
        assert A3.radio_campana(d) > A3.radio_cuerpo(d)
    b = A3.Brazo(dir=np.array([1.0, 0.0, 0.0]), d=1.0, largo=2.0)
    v = np.asarray(A3.malla_brazo(np.zeros(3), b, (1, 1, 1, 1), 1))[:, :3]
    cuerpo = v[np.abs(v[:, 0]) < 1e-6]                           # anillo del arranque (lejos de la campana)
    r = np.hypot(cuerpo[:, 1], cuerpo[:, 2]).max()
    assert abs(r - A3.radio_cuerpo(1.0)) < 0.01 and r > 0.5 + 0.05   # el tubo mide r = 0.5


# ── Recomendación 2: cota de terreno y cota de fondo del buzón, cada una por su lado ──

def _buzones(**datos):
    from nucleo import model_ops
    from tests.test_vista3d import _p, FT, _obj
    pipes = [_p("DRENAJE", inv=(-6.0, -7.0), diam=18)]
    structs = model_ops.rebuild_structures(pipes, [])
    for s in structs:
        s.update(datos)
    esc = modelo3d.construir(pipes, structs, FT)
    return sorted((round(o["z0"], 2), round(o["z1"], 2)) for o in _obj(esc, "struct"))


def test_buzon_automatico_con_ceros_del_panel():
    # el panel guarda 0.0 = «(automática)»: fondo en la solera, tapa con recubrimiento (antes: 0 → 5)
    assert _buzones(rim=0.0, sump=0.0, height_ft=0.0) == [(-7.0, -2.0), (-6.0, -1.0)]


def test_buzon_de_salto_fondo_mas_profundo_sin_mover_el_terreno():
    assert _buzones(sump=-10.0) == [(-10.0, -2.0), (-10.0, -1.0)]


def test_buzon_con_cota_de_terreno_y_de_fondo():
    assert _buzones(rim=3.0, sump=-12.0) == [(-12.0, 3.0), (-12.0, 3.0)]
    assert _buzones(rim=3.0) == [(-7.0, 3.0), (-6.0, 3.0)]
    # la cota de terreno manda sobre la «Altura» de antes (como en Civil 3D)
    assert _buzones(rim=3.0, height_ft=2.0) == [(-7.0, 3.0), (-6.0, 3.0)]
    assert _buzones(height_ft=2.0) == [(-7.0, -5.0), (-6.0, -4.0)]


from tests.test_vista3d import win  # noqa: E402,F401  (ventana de prueba)


def test_panel_cota_de_terreno_y_de_fondo_en_vez_de_altura(win):
    from nucleo import model_ops
    from ui.ventana import app_window
    win.pipes = [{"layer": "DRENAJE", "pts": [(0.0, 0.0), (500.0, 0.0)], "diam": 18.0,
                  "inv_start": -6.0, "inv_end": -7.0}]
    win.structures = model_ops.rebuild_structures(win.pipes, [])
    win.structures[0]["height_ft"] = 4.0                          # proyecto de antes con «Altura»
    win.tabs.setCurrentIndex(app_window.TAB_BZ)
    win.sel_bz = 0
    win._sync_bz_panel()
    fbz = win._fbz
    assert fbz.isRowVisible(win.bz_rim) and fbz.isRowVisible(win.bz_sump)
    assert fbz.isRowVisible(win.bz_height)                        # se ve porque la tenía
    assert win.bz_rim.text() == win.bz_sump.text() == "(automática)"
    win.bz_sump.setValue(-12.5)
    win.bz_rim.setValue(100.0)
    s = win.structures[0]
    assert (s["rim"], s["sump"], s["height_ft"]) == (100.0, -12.5, 0.0)   # la altura se quita
    assert not fbz.isRowVisible(win.bz_height)
    win.bz_rim.setValue(0.0)
    assert s["rim"] == 0.0 and win.bz_rim.text() == "(automática)"


# ── Recomendación 3: modo ortogonal (F8) y rastreo polar (F10) al dibujar ──

def test_ortogonales_y_imanes_polares():
    from nucleo import trazo_asistido as TA
    assert TA.ortogonales(37.25) == [0.0, 90.0, 180.0, 270.0]            # base en el paso: ejes de la hoja
    assert TA.ortogonales(13.7) == [13.7, 103.7, 193.7, 283.7]           # unión inclinada: sus ejes
    assert TA.imanes(0.0, True) == TA.imanes(0.0, True, 45.0)             # por defecto, lo de siempre
    assert sorted(set(TA.imanes(0.0, False, 30.0))) == [30.0 * k for k in range(12)]


def test_f8_dibuja_solo_horizontal_y_vertical(monkeypatch):
    from tests.test_trazo_asistido import win as _win, _clic
    gen = _win.__wrapped__(monkeypatch) if hasattr(_win, "__wrapped__") else None
    w = next(gen) if gen else None
    if w is None:
        import pytest
        pytest.skip("sin ventana")
    try:
        w.act_orto.setChecked(True)
        assert w._orto and not w.act_polar.isChecked()                    # ORTO apaga POLAR (como AutoCAD)
        w.set_mode("pipe")
        _clic(w, 200, 300)
        _clic(w, 640, 410)              # 14° de la horizontal: con ORTO, horizontal
        _clic(w, 690, 760)              # casi vertical: vertical EXACTA
        _clic(w, 300, 820)              # hacia la izquierda: horizontal
        assert w.cur_pts == [(200, 300), (640, 300), (640, 760), (300, 760)]
        w.act_orto.setChecked(False)
        w.act_polar.setChecked(True)
        w._poner_polar_inc(30.0)
        _clic(w, 300 + 400 * 0.866, 760 - 400 * 0.5 + 3)     # ~30° y a 3 px: imán polar
        a = __import__("nucleo.trazo_asistido", fromlist=["x"]).rumbo(w.cur_pts[-2], w.cur_pts[-1])
        assert abs(a - 330.0) < 1e-6
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


# ── Observación 7: desactivar el buzón de un quiebre de alcantarillado deja una curva ──

def _alcantarillado(win, pts):
    from nucleo import model_ops
    win.scale, win.zoom = 1.0, 10.0                               # 0.1 ft por px
    win.pipes = [{"layer": "ALCANTARILLADO", "pts": pts, "diam": 8.0, "inv_start": -6.0, "inv_end": -7.0}]
    win.structures = model_ops.rebuild_structures(win.pipes, [])
    win._refresh_lists()
    i = next(k for k, s in enumerate(win.structures) if (s["x"], s["y"]) == tuple(pts[1]))
    from ui.ventana import app_window
    win.tabs.setCurrentIndex(app_window.TAB_BZ)
    win.sel_bz = i
    win._sync_bz_panel()
    return tuple(pts[1])


def test_quitar_buzon_en_un_quiebre_lo_vuelve_curva(win):
    q = _alcantarillado(win, [(0.0, 0.0), (1000.0, 0.0), (1600.0, 600.0)])   # gira 45°, tramos largos
    n = len(win._undo)
    win.chk_bz_hidden.setChecked(True)
    s = next(o for o in win.structures if (o["x"], o["y"]) == q)
    assert s.get("curve") and not s.get("hidden") and str(s["cod"]).startswith("CV-")
    assert len(win._undo) == n + 1                                        # Ctrl+Z lo deshace
    win.undo()
    s = next(o for o in win.structures if (o["x"], o["y"]) == q)
    assert not s.get("curve") and not s.get("hidden")


def test_quitar_buzon_donde_no_entra_la_curva_queda_desactivado(win):
    q = _alcantarillado(win, [(0.0, 0.0), (1000.0, 0.0), (1010.0, 10.0)])    # tramo de 1.4 ft
    win.chk_bz_hidden.setChecked(True)
    s = next(o for o in win.structures if (o["x"], o["y"]) == q)
    assert s.get("hidden") and not s.get("curve")


# ── Observación 8: lo dibujado a mano en redes que no son de presión lleva curvas en sus quiebres ──

def _terminar(win, capa, pts):
    win.scale, win.zoom = 1.0, 10.0                               # 0.1 ft por px
    win.pipes, win.structures = [], []
    win.active_layer = lambda: capa
    win.cur_pts = [tuple(q) for q in pts]
    win.finish_pipe()
    return [s for s in win.structures if s.get("curve")]


L = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0)]


def test_electrico_dibujado_a_mano_lleva_curva_en_el_quiebre(win):
    cv = _terminar(win, "ELECTRICO", L)
    assert len(cv) == 1 and (cv[0]["x"], cv[0]["y"]) == (1000.0, 0.0) and not cv[0].get("radius_ft")
    assert "vertex_kinds" not in win.pipes[0]                     # el dato de la utilidad no cambia
    assert win.pipes[0]["pts"] == L


def test_agua_y_gas_no_llevan_curva_y_gravedad_conserva_su_buzon(win):
    assert _terminar(win, "AGUA", L) == []                        # presión: el codo es un accesorio
    assert _terminar(win, "GAS", L) == []
    assert _terminar(win, "ALCANTARILLADO", L) == []              # el vértice lleva su buzón
    assert any(not s.get("hidden") and (s["x"], s["y"]) == (1000.0, 0.0) for s in win.structures)


# ── Observación 9: el codo de una utilidad que pasa por el vértice recorta sus DOS tubos ──

def test_cortar_en_un_vertice_recorta_los_dos_lados():
    from nucleo import accesorios3d as A3
    camino = [(0, 0, 0), (10, 0, 0), (4, 8, 0)]                  # gira más de 90° en (10, 0)
    partes = A3.cortar(camino, [((10, 0), (-1, 0), 2.0), ((10, 0), (-0.6, 0.8), 2.0)])
    tramos = [(round(float(p[0][0]), 3), round(float(p[0][1]), 3), round(float(p[-1][0]), 3), round(float(p[-1][1]), 3))
              for p in partes]
    assert tramos == [(0.0, 0.0, 8.0, 0.0), (8.8, 1.6, 4.0, 8.0)]   # cada tubo muere a 2 ft del vértice


def test_codo_de_gas_ningun_tubo_llega_al_vertice():
    import numpy as np
    from tests.test_vista3d import _p, FT
    for fin in ((300, 300), (120, 260), (300, -300)):            # 90°, cerrado y al otro lado
        p = _p("GAS", pts=((0, 0), (300, 0), fin), diam=12)
        esc = modelo3d.construir([p], [], FT)
        tubo = esc.opacos[esc.opacos[:, 10] == 1][:, :2]
        vert = np.array([300 * FT, 0.0]) - np.array(esc.origen[:2])
        assert np.linalg.norm(tubo - vert, axis=1).min() > 0.6, fin   # el tubo no asoma por el codo
