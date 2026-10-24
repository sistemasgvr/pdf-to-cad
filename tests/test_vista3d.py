"""Vista 3D: el modelo (modelo3d.py + mallas3d.py, puros) sigue las reglas del plugin,
elegir con el ratón, y la ventana real (abrir, seguir la selección, clic → plano)."""
import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import accesorios3d as A3  # noqa: E402
from nucleo import mallas3d as M  # noqa: E402
from nucleo import model_ops  # noqa: E402
from nucleo import modelo3d as M3  # noqa: E402

FT = 0.1                                    # pies por px: 1 ft = 10 px


def _p(layer="AGUA", pts=((0, 0), (500, 0)), diam=12, inv=(-4.0, -4.0), **k):
    d = dict(layer=layer, pts=[tuple(q) for q in pts], name="", diam=float(diam),
             pipe_size=f"{diam:g} in", inv_start=inv[0], inv_end=inv[1])
    d.update(k)
    return d


def _obj(esc, tipo):
    return [o for o in esc.objetos.values() if o["tipo"] == tipo]


def test_eje_en_solera_mas_medio_diametro_y_suelo_automatico():
    esc = M3.construir([_p(diam=24, inv=(-6.0, -6.0))], [], FT)
    o = _obj(esc, "pipe")[0]
    assert o["z0"] == pytest.approx(-6.0) and o["z1"] == pytest.approx(-6.0)
    # sin buzones: suelo 3 ft sobre el tope de la tubería (-6 + 2 + 3)
    assert esc.suelo_z == pytest.approx(-1.0)
    z = esc.opacos[:, 2] + esc.suelo_z                       # coordenadas del dibujo
    assert z.min() == pytest.approx(-6.0, abs=1e-3) and z.max() == pytest.approx(-4.0, abs=1e-3)


def test_cotas_por_tramo_igual_que_el_lienzo():
    p = _p(pts=((0, 0), (100, 0), (200, 0)), inv=(-4.0, -6.0), vertex_inv_out={1: -5.5}, vertex_inv_in={1: -5.0})
    camino = M3.recorrido([p], [], 0, FT)
    assert [round(q[2], 3) for q in camino] == [-4.0, -5.0, -5.5, -6.0]      # escalón en el vértice
    assert model_ops.z_en_tramo(p, 0, 50, 0) == pytest.approx(-4.5)


def test_curva_con_su_arco_real():
    p = _p("ELECTRICO", pts=((0, 0), (300, 0), (300, 300)), diam=4)
    cv = {"cod": "CV-1", "x": 300.0, "y": 0.0, "curve": True, "radius_ft": 10.0, "net": "conduit"}
    camino = M3.recorrido([p], [cv], 0, FT)
    assert len(camino) > 10                                   # el arco, no la esquina
    assert all(abs(q[0] - 300) > 1e-6 or abs(q[1]) > 1e-6 for q in camino[1:-1])   # la esquina C no está
    tang = [q for q in camino if abs(q[1]) < 1e-6 and q[0] > 0]
    assert tang and max(q[0] for q in tang) == pytest.approx(200.0, abs=0.5)     # T = r = 10 ft = 100 px


def test_bancoducto_reemplaza_a_su_utilidad_con_el_fondo_en_la_cota():
    p = _p("TELECOM", diam=4, inv=(-5.0, -5.0))
    db = dict(name="DB", width_in=24, height_in=16, conduits=[dict(cx=6, cy=8, diam=4)], pipes=[0])
    esc = M3.construir([p], [], FT, duct_banks=[db])
    o = _obj(esc, "pipe")
    assert len(o) == 1 and o[0]["bancoducto"] == "DB" and o[0]["z0"] == pytest.approx(-5.0)
    z = esc.transparentes[:, 2] + esc.suelo_z
    assert z.min() == pytest.approx(-5.0, abs=1e-3) and z.max() == pytest.approx(-5.0 + 16 / 12, abs=1e-3)


def test_buzon_fondo_en_la_solera_y_tapa_con_recubrimiento():
    pipes = [_p("DRENAJE", inv=(-6.0, -7.0), diam=18)]
    structs = model_ops.rebuild_structures(pipes, [])
    esc = M3.construir(pipes, structs, FT)
    bz = sorted(_obj(esc, "struct"), key=lambda o: o["z0"])
    assert [(round(o["z0"], 2), round(o["z1"], 2)) for o in bz] == [(-7.0, -2.0), (-6.0, -1.0)]
    assert esc.suelo_z == pytest.approx(-1.0)                 # la tapa más alta


def test_solido_con_cota_superior_automatica_y_del_usuario():
    p = _p("TELECOM", diam=4, inv=(-4.0, -4.0))
    s = {"cod": "", "x": 500.0, "y": 0.0, "net": "conduit", "shape": "rect", "width_ft": 6.0, "length_ft": 10.0,
         "outline": [(450, -30), (550, -30), (550, 30), (450, 30)], "rot_deg": 0.0}
    structs = model_ops.normalize_solids([s])
    o = _obj(M3.construir([p], structs, FT), "struct")[0]
    alto = model_ops.SOLID_DEFAULT_H_FT
    assert o["z1"] == pytest.approx(model_ops.solid_top_centrado(-4.0, 4 / 12, alto))
    assert o["z1"] - o["z0"] == pytest.approx(alto)
    structs[0]["solid_top_z"] = 2.0
    o = _obj(M3.construir([p], structs, FT), "struct")[0]
    assert (o["z0"], o["z1"]) == (pytest.approx(2.0 - alto), pytest.approx(2.0))


def test_accesorios_y_marcas_de_aviso():
    pipes = [_p(pts=((0, 0), (300, 0), (600, 0)), diam=12), _p(pts=((300, 0), (300, 300)), diam=8)]
    avisos = [dict(x=450, y=0, clase="diametro", mensaje="m", pipe=0, info=False),
              dict(x=150, y=0, clase="tipo", mensaje="sin tipo", pipe=0, info=False)]
    esc = M3.construir(pipes, [], FT, avisos=avisos)
    acc = _obj(esc, "accesorio")
    assert len(acc) == 1 and acc[0]["acc_tipo"] == "tee"
    assert [o["mensaje"] for o in _obj(esc, "aviso")] == ["m"]          # «sin tipo» no se marca
    esc = M3.construir(pipes, [], FT, avisos=avisos, ver=dict(accesorios=False, avisos=False))
    assert not _obj(esc, "accesorio") and not _obj(esc, "aviso")


def test_capas_ocultas_y_abandonadas_a_trazos():
    pipes = [_p(), _p("GAS", pts=((0, 100), (500, 100)), ab=True)]
    esc = M3.construir(pipes, [], FT, ocultas=["AGUA"])
    assert [o["capa"] for o in _obj(esc, "pipe")] == ["GAS"]
    # 50 ft a trazos de 4 ft (4·D) con huecos de 2.4 ft: varios tramos, no un tubo entero
    x = esc.opacos[:, 0] + esc.origen[0]
    trazo, hueco = M3.trazos_abandonada(1.0)
    assert (trazo, hueco) == (pytest.approx(4.0), pytest.approx(2.4))
    hay = np.zeros(500, bool)
    hay[np.clip(x.round().astype(int), 0, 49)] = True
    assert not hay[:50].all()                                   # quedan huecos
    assert len(M.trozos([(0, 0, 0), (50, 0, 0)], trazo, hueco)) == 8


def test_escena_vacia():
    assert M3.construir([], [], FT).vacia and M3.construir([_p()], [], 0).vacia


def test_elegir_con_el_rayo():
    esc = M3.construir([_p(), _p("GAS", pts=((0, 300), (500, 300)), inv=(-8.0, -8.0))], [], FT)
    gas = next(k for k, o in esc.objetos.items() if o.get("capa") == "GAS")
    lo, hi = esc.objetos[gas]["caja"]
    c = (lo + hi) / 2
    assert M.elegir(esc.picks, (c[0], c[1], 50.0), (0, 0, -1)) == gas
    assert M.elegir(esc.picks, (c[0] + 5, c[1] + 5, 50.0), (0, 0, -1)) == 0
    # de costado, a la cota de la tubería (y 5 ft más arriba no la toca)
    assert M.elegir(esc.picks, (c[0], c[1] - 100, c[2]), (0, 1, 0)) == gas
    assert M.elegir(esc.picks, (c[0], c[1] - 100, c[2] + 5), (0, 1, 0)) != gas
    assert M3.objeto_de(gas) == ("pipe", 1)


# ─────────────────────────── ventana ───────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from PySide6 import QtCore
    monkeypatch.setattr("ui.dialogos.vista3d_dialog._ajustes",
                        lambda: QtCore.QSettings(os.path.join(os.environ["PDFCAD_RECUPERACION"], "v3d.ini"),
                                                 QtCore.QSettings.IniFormat))
    from ui.ventana.app_window import Main
    from PySide6 import QtGui
    w = Main()
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0
    w.pipes = [_p(pts=((100, 100), (600, 100)), diam=8), _p("GAS", pts=((100, 400), (600, 400)), diam=6)]
    w._refresh_lists(); w._redraw()
    yield w
    dlg = getattr(w, "_vista3d_dlg", None)
    if dlg is not None:
        dlg.close()
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _esperar(dlg):
    from PySide6 import QtWidgets
    t = time.time()
    while (dlg._trabajo is not None or dlg._t.isActive()) and time.time() - t < 20:
        QtWidgets.QApplication.processEvents(); time.sleep(0.01)
    QtWidgets.QApplication.processEvents()


def test_ventana_abre_y_sigue_al_plano(win):
    dlg = win.abrir_vista3d()
    _esperar(dlg)
    assert dlg.escena.cuentas["utilidades"] == 2 and dlg.pila.currentIndex() == 0
    assert set(dlg._capas) == {"AGUA", "GAS"}
    win._show_tab(0); win.pipe_list.setCurrentRow(1); win._redraw()
    assert dlg.visor.sel_id == 2
    assert dlg.texto_de(2).startswith("#2 ") and 'Ø6"' in dlg.texto_de(2)
    antes = dlg._firma
    win.pipes[0]["inv_end"] = -9.0; win._redraw(); _esperar(dlg)
    assert dlg._firma != antes                                # se actualiza sola al editar
    dlg._elegido(1)                                           # clic en 3D → elige en el plano
    assert win.sel_pipe == 0


def test_capa_apagada_y_ver_en_3d(win):
    dlg = win.abrir_vista3d(); _esperar(dlg)
    dlg._capas["GAS"].setChecked(False); _esperar(dlg)
    assert [o["capa"] for o in dlg.escena.objetos.values() if o["tipo"] == "pipe"] == ["AGUA"]
    dlg._capas["GAS"].setChecked(True); _esperar(dlg)
    win._show_tab(0); win.pipe_list.setCurrentRow(1)
    win.ver_en_3d(); _esperar(dlg)
    assert dlg.visor.sel_id == 2


def test_acceso_por_menu_barra_y_atajo(win):
    acciones = {a.shortcut().toString(): a for a in win.findChildren(type(win._act_3d))}
    assert "F3" in acciones and win._act_3d.toolTip().startswith("Vista 3D")


def test_restablecer_suelo_y_flechas_desde_la_automatica(win):
    dlg = win.abrir_vista3d(); _esperar(dlg)
    auto = dlg.escena.suelo_z
    assert dlg.spn_suelo.value() <= -100000.0                  # «Automática»
    dlg.spn_suelo.stepBy(1)                                     # las flechas arrancan en la automática
    assert dlg.spn_suelo.value() == pytest.approx(round(auto, 2))
    dlg.spn_suelo.setValue(-50.0); dlg.actualizar(forzar=True); _esperar(dlg)
    dlg.chk_suelo.setChecked(False); dlg.sld_suelo.setValue(70)
    assert dlg.escena.suelo_z == pytest.approx(-50.0)
    dlg.restablecer_suelo(); _esperar(dlg)
    assert dlg.spn_suelo.value() <= -100000.0 and dlg.chk_suelo.isChecked()
    assert dlg.sld_suelo.value() == 18 and dlg.escena.suelo_z == pytest.approx(auto)


# ─────────────────────────── accesorios como el plugin ───────────────────────────

def test_espejo_de_wyesolido():
    """Las constantes de accesorios3d tienen que ser las de WyeSolido.cs."""
    import re
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "API-CIVIL", "proyecto1", "proyecto1", "WyeSolido.cs"), encoding="utf-8") as f:
        cs = dict(re.findall(r"(?:private|internal) const double (\w+) = ([\d.]+);", f.read()))
    assert cs, "no se leyeron constantes del .cs"
    distintas = {k: (v, getattr(A3, k, None)) for k, v in cs.items() if getattr(A3, k, None) != float(v)}
    assert not distintas, f"WyeSolido.cs cambió: actualizar accesorios3d {distintas}"


def test_codo_curvo_con_campanas_y_tubo_recortado():
    p = _p(pts=((0, 0), (300, 0), (300, 300)), diam=12)          # codo de 90° en (300, 0)
    esc = M3.construir([p], [], FT)
    acc = _obj(esc, "accesorio")
    assert len(acc) == 1 and acc[0]["acc_tipo"] == "codo"
    ida = next(k for k, o in esc.objetos.items() if o["tipo"] == "accesorio")
    pieza = esc.opacos[esc.opacos[:, 10] == ida]
    R, T, _c = A3.curva_codo(1.0, np.pi / 2)
    assert (R, T) == (pytest.approx(1.0), pytest.approx(1.0))
    # sin pelota: nada de la pieza pasa del radio de la campana alrededor de su eje curvo
    c = pieza[:, :3].mean(axis=0)
    assert np.abs(pieza[:, 2] - c[2]).max() <= 0.5 + A3.HOLGURA_FT + A3.PARED_FT + 1e-3
    # el tubo NO llega al vértice: muere dentro de la campana (alcance del plugin)
    tubo = esc.opacos[esc.opacos[:, 10] == 1]
    vert = np.array([300 * FT, 0.0]) - np.array(esc.origen[:2])
    alcance = T + 1.0 * A3.COLLAR_CODO_D + 1.0 * A3.LARGO_CAMPANA_D * A3.CALADO_EN_CAMPANA - A3.SOLAPE_EXTRA_FT
    dist = np.linalg.norm(tubo[:, :2] - vert, axis=1)
    assert dist.min() >= alcance - 0.5 - 1e-3                    # (radio del tubo de margen)


def test_tee_con_brazos_y_campanas_y_wye_con_tronco_engrosado():
    pipes = [_p(pts=((0, 0), (300, 0), (600, 0)), diam=12), _p(pts=((300, 0), (300, 300)), diam=8)]
    esc = M3.construir(pipes, [], FT)
    acc = _obj(esc, "accesorio")[0]
    assert acc["acc_tipo"] == "tee"
    brazos = [A3.Brazo(dir=np.array(u, float), d=1.0) for u in ((1, 0, 0), (-1, 0, 0), (0.7071, 0.7071, 0))]
    A3.pieza("wye", np.zeros(3), brazos, (1, 1, 1, 1), 1)
    assert sorted(b.engrose for b in brazos) == [0.0, A3.ENGROSE_TRONCO_Y_FT, A3.ENGROSE_TRONCO_Y_FT]
    assert all(b.largo >= 1.25 - 1e-9 for b in brazos)           # Wye: 1.25·D (o más si chocan)
    tee = [A3.Brazo(dir=np.array(u, float), d=1.0) for u in ((1, 0, 0), (-1, 0, 0), (0, 1, 0))]
    A3.pieza("tee", np.zeros(3), tee, (1, 1, 1, 1), 1)
    assert [round(b.largo, 2) for b in tee] == [0.75, 0.75, 0.75]


def test_cortar_tubo_en_el_accesorio():
    camino = [(0, 0, 0), (10, 0, 0), (20, 0, 0)]
    partes = A3.cortar(camino, [((10, 0), (1, 0), 2.0), ((10, 0), (-1, 0), 3.0)])
    assert [(round(p[0][0], 3), round(p[-1][0], 3)) for p in partes] == [(0.0, 7.0), (12.0, 20.0)]
    assert len(A3.cortar(camino, [((20, 0), (-1, 0), 4.0)])) == 1


def test_zoom_de_cerca_no_atraviesa_y_doble_clic_central_encuadra_todo(win):
    from PySide6 import QtCore, QtGui
    from ui.comun import visor3d as V
    dlg = win.abrir_vista3d(); _esperar(dlg)
    v = dlg.visor
    v.resize(800, 600)
    # sobre una tubería: el zoom va a SU superficie y se detiene a DIST_MIN_FT, sin atravesarla
    lo, hi = dlg.escena.objetos[1]["caja"]
    v.cam.objetivo = (np.asarray(lo) + np.asarray(hi)) / 2
    for _ in range(300):                                       # mucho más allá del zoom máximo
        v.zoom(1, 400, 300)
        p, _d = v._punto_bajo(400, 300)
        assert np.linalg.norm(p - v.cam.ojo()) >= V.DIST_MIN_FT - 1e-6
    assert np.isfinite(v.cam.objetivo).all() and v.cam.dist >= V.DIST_MIN_FT - 1e-6
    cerca = v.cam.dist
    v.zoom(-3, 400, 300)
    assert v.cam.dist > cerca                                    # y se vuelve a alejar
    # desplazar: lo agarrado sigue al ratón a SU profundidad (de cerca no se dispara)
    k = v._pies_por_px(2.0)
    assert k == pytest.approx(V.DESPLAZAR * 2.0 * np.tan(np.radians(v.cam.fov) / 2) * 2 / 600)
    assert v._pies_por_px(0.0) > 0                               # nunca se traba
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonDblClick, QtCore.QPointF(10, 10), QtCore.QPointF(10, 10),
                           QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier)
    v.mouseDoubleClickEvent(ev)
    lo, hi = dlg.escena.caja
    assert v.cam.objetivo == pytest.approx((np.asarray(lo) + np.asarray(hi)) / 2)


def test_al_reabrir_la_camara_arranca_de_cero(win):
    dlg = win.abrir_vista3d(); _esperar(dlg)
    inicial = (dlg.visor.cam.yaw, dlg.visor.cam.pitch, dlg.visor.cam.dist)
    dlg.visor.vista("arriba"); dlg.visor.zoom(5)
    dlg.close()
    dlg = win.abrir_vista3d(); _esperar(dlg)
    assert (dlg.visor.cam.yaw, dlg.visor.cam.pitch, dlg.visor.cam.dist) == pytest.approx(inicial)


# ─────────────────────────── cubo de vistas ───────────────────────────

def _cubo_dibujado(yaw=-55.0, pitch=30.0):
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun.cubo_vistas import CuboVistas
    from ui.comun.visor3d import Camara
    cam = Camara(); cam.yaw, cam.pitch = yaw, pitch
    cubo = CuboVistas()
    img = QtGui.QImage(800, 600, QtGui.QImage.Format_ARGB32)
    p = QtGui.QPainter(img); cubo.dibujar(p, 800, cam); p.end()
    return cubo


def test_cubo_muestra_las_caras_que_miran_a_la_camara():
    cubo = _cubo_dibujado()                                     # isométrica desde el suroeste... (yaw -55)
    caras = {c for c, _p in cubo._caras}
    assert caras == {"superior", "frontal", "derecha"}
    cubo = _cubo_dibujado(yaw=90.0, pitch=20.0)                 # desde el norte
    assert {c for c, _p in cubo._caras} == {"superior", "posterior"}


def test_clic_en_cara_y_en_punto_cardinal():
    cubo = _cubo_dibujado()
    for clave, poli in cubo._caras:
        assert cubo.que_hay(poli.boundingRect().center()) == ("cara", clave)
    assert cubo.vista_de(("cara", "superior"), 30.0) == (-90.0, 89.5)       # planta con el norte arriba
    assert cubo.vista_de(("cara", "frontal"), 30.0) == (-90.0, 0.0)
    e = next(q for c, q, _d, _t in cubo._letras if c == "E")
    assert cubo.que_hay(e) == ("cardinal", "E")
    assert cubo.vista_de(("cardinal", "E"), 25.0) == (0.0, 25.0)             # desde el este, misma inclinación


def test_animar_llega_a_la_vista_por_el_camino_corto(win):
    from ui.comun import visor3d as V
    dlg = win.abrir_vista3d(); _esperar(dlg)
    v = dlg.visor
    v.cam.yaw, v.cam.pitch = 170.0, 10.0
    v.animar(-170.0, 89.5)                                       # 20° por el camino corto, no 340°
    for _ in range(V.ANIM_PASOS):
        v._animar_paso()
    assert ((v.cam.yaw - -170.0 + 180) % 360 - 180) == pytest.approx(0.0, abs=1e-6)
    assert v.cam.pitch == pytest.approx(89.5)
    assert abs(v.cam.yaw - 170.0) <= 20.0 + 1e-6                 # nunca dio la vuelta larga


def test_solo_las_tuberias_llevan_grosor_minimo_en_pantalla():
    pipes = [_p(pts=((0, 0), (300, 0), (600, 0)), diam=12), _p(pts=((300, 0), (300, 300)), diam=8)]
    esc = M3.construir(pipes, [], FT)
    ids = esc.opacos[:, 10]
    tubos = esc.opacos[ids <= len(pipes)]
    assert (tubos[:, 14] > 0).all()                                    # radio de la sección
    # el eje guardado está a un radio del vértice (anillo) o en el centro (tapa)
    dist = np.linalg.norm(tubos[:, :3] - tubos[:, 11:14], axis=1)
    assert dist.max() <= tubos[:, 14].max() * 1.05 + 1e-6
    assert (esc.opacos[ids > M3.ID_ACCESORIO, 14] == 0).all()         # accesorios a tamaño real


def test_al_abrir_la_vista_3d_se_guarda_el_proyecto(win, monkeypatch, tmp_path):
    escritos, como = [], []
    monkeypatch.setattr(win, "_write_project", lambda ruta: escritos.append(ruta))
    monkeypatch.setattr(win, "save_project_as", lambda: como.append(1))
    monkeypatch.setattr(win, "_has_real_changes", lambda: True)
    win.project_path = str(tmp_path / "p.digproj")
    win.abrir_vista3d()
    assert escritos == [win.project_path]                      # con archivo y cambios: se guarda
    monkeypatch.setattr(win, "_has_real_changes", lambda: False)
    win.abrir_vista3d()
    assert len(escritos) == 1                                    # sin cambios: no reescribe
    monkeypatch.setattr(win, "_has_real_changes", lambda: True)
    win.project_path = None
    assert win._guardar_antes_de_3d() == ""                      # sin archivo y sin autoguardado activo
    assert not como                                              # nunca abre «Guardar como»
    monkeypatch.setattr(win, "_has_real_changes", lambda: False)   # que el cierre no pregunte


# ─────────────────────────── ficha, Esc y vista inicial ───────────────────────────

def test_ficha_de_utilidad_y_de_accesorio(win):
    from nucleo import ficha3d
    dlg = win.abrir_vista3d(); _esperar(dlg)
    titulo, filas = ficha3d.de_utilidad(win._tablas_de_datos(), win.pipes, [], 0)
    campos = dict(filas)
    assert titulo.startswith("#1") and campos["Diámetro (in)"] == "8" and "Largo (ft)" in campos
    assert "Inicio X" not in campos                               # sin coordenadas: ficha corta
    obj = {"acc_tipo": "tee", "angulo": 90.0, "capa": "AGUA", "pipes": [0, 1], "eje_z": -3.5, "x": 0, "y": 0}
    titulo, filas = ficha3d.de_accesorio(obj, win.pipes, [], win._tipo)
    campos = dict(filas)
    assert titulo == "Tee 90°" and campos["Une las utilidades"] == "#1, #2" and campos["Diámetros"] == '8" × 6"'


def test_clic_muestra_la_ficha_y_esc_deselecciona_sin_cerrar(win):
    from PySide6 import QtCore, QtGui
    dlg = win.abrir_vista3d(); _esperar(dlg)
    dlg._elegido(1)                                              # clic en la utilidad #1
    assert dlg.ficha.tabla.rowCount() > 3 and dlg.ficha.lbl_titulo.text().startswith("#1")
    assert win.sel_pipe == 0
    esc = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier)
    dlg.keyPressEvent(esc)
    assert dlg.isVisible()                                       # Esc no cierra
    assert dlg.visor.sel_id == 0 and win.sel_pipe == -1 and dlg.ficha.tabla.rowCount() == 0
    dlg.keyPressEvent(esc)                                       # sin selección: no hace nada
    assert dlg.isVisible()


def test_la_vista_arranca_en_planta():
    from ui.comun.visor3d import VISTAS, Camara
    assert (Camara().yaw, Camara().pitch) == VISTAS["arriba"]


def test_tuberias_encimadas_no_hacen_brazos_gigantes_ni_desaparecen():
    # Caso real (santos_proyecto_prueba, utilidad #8 de agua): en cada punta de la #1 otra
    # tubería sale ENCIMA, en la misma dirección (Wye a 0.01°). Antes los brazos medían miles
    # de pies y el tubo se recortaba entero: en 3D solo quedaban sus codos.
    brazos = [A3.Brazo(dir=np.array(u, float), d=1.0) for u in ((1, 0, 0), (1, 0.0002, 0), (-1, 0, 0))]
    A3.pieza("wye", np.zeros(3), brazos, (1, 1, 1, 1), 1)
    assert max(b.largo for b in brazos) < 5.0
    pipes = [_p(pts=((0, 0), (300, 0), (300, 200), (600, 200)), diam=12),
             _p(pts=((0, 0), (200, 0)), diam=12), _p(pts=((0, 0), (-200, 0)), diam=12)]
    esc = M3.construir(pipes, [], FT)
    assert all((esc.opacos[:, 10] == i + 1).any() for i in range(3))     # todas se dibujan
    x = esc.opacos[esc.opacos[:, 10] == 1, 0] + esc.origen[0]
    assert x.max() - x.min() > 40                                          # la #1 sigue entera (60 ft)


# ───────────── conexiones verticales CON sus accesorios (2026-10-14) ─────────────

def test_conexiones_verticales_con_codos_tee_y_wye_como_el_plugin():
    """Cada conexión aprobada lleva las piezas del plugin: Tee si la utilidad pasa, codo 90°
    si termina, y en un quiebre (la que pasa ya lleva codo) Wye + codos; con poco desnivel,
    solo la Wye (ramal inclinado)."""
    import math
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from nucleo import modelo3d
    from ui.dialogos import vista3d_dialog
    from ui.ventana.app_window import Main
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escenarios", "cruces", "escenarios_prueba.digproj")
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ruta); w._redraw()
    dlg = vista3d_dialog.Vista3DDialog(w)
    esc = modelo3d.construir(**dlg._datos())
    ft = w.scale / w.zoom
    piezas = {}
    for c in w.cross_connections:
        piezas[(c["pipe_a"] + 1, c["pipe_b"] + 1)] = sorted(
            (o["acc_tipo"], bool(o.get("vertical"))) for o in esc.objetos.values()
            if o["tipo"] == "accesorio" and math.dist((o["x"], o["y"]), (c["x"], c["y"])) * ft < 12)
    T, C, W = ("tee", True), ("codo", True), ("wye", False)
    assert piezas[(50, 51)] == [T, T]                   # las dos pasan
    assert piezas[(52, 53)] == [C, T]                   # una pasa, la otra termina
    assert piezas[(56, 57)] == [C, C]                   # las dos terminan
    assert piezas[(54, 55)] == [C, C, W]                # quiebre: Wye + codo arriba + codo abajo
    assert piezas[(58, 59)] == [W]                      # 2 ft de desnivel: no caben dos codos
    dlg.close(); w._dirty = False


def test_armar_avisa_un_avance_que_sigue_al_trabajo_y_no_cambia_la_escena():
    """`construir` avisa su avance en milésimas (`nucleo/avance3d`, pedido del usuario 2026-10-20: con
    miles de utilidades parecía colgada): nunca retrocede, pasa por cada parte y termina cerca del final;
    la escena es la misma que sin nadie escuchando."""
    from nucleo import avance
    pipes = [_p(pts=((0, 100 * k), (300, 100 * k), (300, 100 * k + 60)), diam=8) for k in range(30)]
    pipes += [_p(pts=((300, 100 * k + 60), (500, 100 * k + 60))) for k in range(30)]
    avisos = []
    with avance.escuchar(lambda texto, i, n: avisos.append((texto, i, n))):
        esc = M3.construir(pipes, [], FT)
    sin = M3.construir(pipes, [], FT)
    mil = [i for _t, i, n in avisos]
    assert all(n == 1000 for _t, _i, n in avisos) and mil == sorted(mil)
    textos = " ".join(t for t, _i, _n in avisos)
    assert "Buscando los accesorios" in textos and "Armando los accesorios" in textos
    assert "Armando las utilidades" in textos and avisos[-1][0] == "Terminando la escena…"
    assert 900 <= mil[-1] <= 1000
    assert np.array_equal(esc.opacos, sin.opacos) and esc.cuentas == sin.cuentas


def test_al_abrir_la_vista_3d_muestra_la_capa_de_carga_con_su_barra(win):
    """Mientras se arma la primera escena, el visor queda tapado por «Armando la vista 3D…» con la barra
    (sin reloj de arena en toda la app); al terminar se quita. Una actualización después de editar no lo
    tapa: el avance va en la línea de estado."""
    from PySide6 import QtWidgets
    from ui.comun import busy
    dlg = win.abrir_vista3d()
    ov = busy.overlay_for(dlg.pila)
    assert ov.active and ov.text() == "Armando la vista 3D…"
    assert QtWidgets.QApplication.overrideCursor() is None
    dlg._avance("Armando las utilidades: 1 de 2", 470)
    assert ov._stack[-1]["done"] == 470 and ov._stack[-1]["total"] == 1000 and "47 %" in ov.detail()
    _esperar(dlg)
    assert not ov.active and dlg.escena.cuentas["utilidades"] == 2
    win.pipes[0]["inv_end"] = -9.0; win._redraw(); dlg.actualizar()
    assert not ov.active
    _esperar(dlg)


def test_rotulos_3d_nivel_de_detalle_sin_taparse_y_memorizados():
    """Pendientes y ángulos (pedido del usuario 2026-10-20: AGUA 2 dibujaba 35 766 rótulos por cuadro):
    de lejos un tramo más corto en pantalla que su rótulo no lo muestra; los que se tapan, uno solo (el de
    lo elegido primero); la misma cámara no recalcula; y el sello pinta igual que dibujar directo."""
    import math
    from PySide6 import QtCore, QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import etiquetas3d as E, rotulos3d_lod as LOD
    from ui.comun.visor3d import Camara, _np
    # 40 rótulos en fila cada 30 ft (tramos de 30 ft) y dos encimados de utilidades distintas
    rot = [(1, (30.0 * k, 0.0, 0.0), f"{k}.00 %") for k in range(40)]
    rot += [(7, (600.0, 0.0, 0.0), "9.99 %"), (8, (600.0, 0.0, 0.0), "8.88 %")]
    largos = [30.0] * len(rot)
    capa = E.Capa(rot, largos, rotulo=True)
    W, H = 800, 600
    k_px = (H / 2) / math.tan(math.radians(40.0) / 2)

    def ver(dist, sel=0):
        cam = Camara(); cam.objetivo = np.array([600.0, 0, 0]); cam.dist = dist
        return capa.visibles(_np(cam.matriz(W / H, 700)), W, H, k_px, sel)[0].tolist()
    assert ver(20000) == []                                       # de lejos: 30 ft son pocos px
    cerca = ver(200)
    assert cerca and len(cerca) < len(rot)
    assert not ({40, 41} <= set(cerca))                           # los dos encimados: uno solo
    assert 41 in ver(200, sel=8) and 40 not in ver(200, sel=8)    # el de lo elegido gana
    clave = capa._clave
    ver(200, sel=8)
    assert capa._clave is clave                                    # misma cámara: no recalcula
    # cada caja visible no toca a otra
    idx, xs, ys = capa._elegidos
    cajas = [(x - capa.anchos[i] / 2, y - 8, x + capa.anchos[i] / 2, y + 8) for i, x, y in zip(idx, xs, ys)]
    for a in range(len(cajas)):
        for b in range(a + 1, len(cajas)):
            A, B = cajas[a], cajas[b]
            assert A[2] - 1 <= B[0] + 1 or B[2] - 1 <= A[0] + 1 or A[3] - 1 <= B[1] + 1 or B[3] - 1 <= A[1] + 1
    # sello = dibujo directo (posición entera)
    img1 = QtGui.QImage(120, 40, QtGui.QImage.Format_ARGB32_Premultiplied); img1.fill(0)
    img2 = QtGui.QImage(img1); img2.fill(0)
    p = QtGui.QPainter(img1); p.setRenderHint(QtGui.QPainter.Antialiasing, True); p.setFont(E._fuente(p))
    E._pintar(p, QtCore.QRectF(10, 10, 60, 16), "1.23 %", 1, 0, 0, True); p.end()
    p = QtGui.QPainter(img2)
    p.drawImage(QtCore.QPointF(8, 8), capa._sello("1.23 %", 60.0, 1.0)); p.end()
    assert img1 == img2
    assert LOD.MAXIMO >= len(cerca)


def test_casilla_de_rotulos_no_rehace_la_escena(win):
    """La escena trae siempre los rótulos; la casilla solo los muestra (antes rehacía toda la escena)."""
    dlg = win.abrir_vista3d(); _esperar(dlg)
    win.pipes[0]["pts"] = [(100, 100), (350, 100), (600, 160)]; win._redraw(); dlg.actualizar(); _esperar(dlg)
    esc = dlg.escena
    assert esc.rotulos and len(esc.rotulos_largos) == len(esc.rotulos)
    dlg.chk["rotulos"].setChecked(True)
    assert dlg.visor.ver_rotulos and dlg._trabajo is None and dlg.escena is esc
    dlg.chk["rotulos"].setChecked(False)
    assert not dlg.visor.ver_rotulos and dlg.escena is esc


def test_zoom_alcanza_una_tuberia_fina_y_en_el_vacio_avanza(win):
    """Una tubería fina vista de lejos SÍ es el destino del zoom (se toca con el radio de señalar) y sin
    nada bajo el cursor la cámara no se traba en el plano del objetivo: avanza (pedido 2026-10-20)."""
    from ui.comun import visor3d as V
    dlg = win.abrir_vista3d(); _esperar(dlg)
    v = dlg.visor
    v.resize(800, 600)
    v.encuadrar()
    lo, hi = dlg.escena.objetos[1]["caja"]
    centro = (np.asarray(lo) + np.asarray(hi)) / 2
    m = V._np(v.cam.matriz(800 / 600, v.radio()))
    c = m @ np.r_[centro, 1.0]
    x, y = (c[0] / c[3] + 1) / 2 * 800, (1 - c[1] / c[3]) / 2 * 600
    _p, _d, toca = v._punto_bajo(x + 3, y + 3, v.cam.dist * V.R_ELEGIR, con_choque=True)
    assert toca                                                   # a 3 px de una tubería de 8"
    # vacío: muy lejos de todo, 300 clics de rueda siguen moviendo la cámara
    v.cam.objetivo = np.array([0.0, 5000.0, 0.0]); v.cam.dist = 50.0
    antes = v.cam.ojo().copy()
    for _ in range(300):
        v.zoom(1, 400, 300)
    assert np.linalg.norm(v.cam.ojo() - antes) > 300 * V.AVANCE_MIN_FT * 0.9
