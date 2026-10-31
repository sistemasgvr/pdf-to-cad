"""Perfil longitudinal en la app (pedido del usuario 2026-10-31): recorrido como el plugin (CREAR_PERFIL_RED),
estaciones, rótulos y cruces."""
import pytest

from nucleo import perfil_datos as PD, perfil_recorrido as PR, perfil_textos as T

FT = 0.1                                   # 0.1 ft por px


def _agua():
    # principal oeste→este en 3 utilidades con un quiebre suave (20°) y un ramal en T a 90°
    return [dict(layer="AGUA", pts=[(1000, 500), (2000, 500)], diam=8.0, inv_start=-4.0, inv_end=-4.5),
            dict(layer="AGUA", pts=[(2000, 500), (3000, 864)], diam=8.0, inv_start=-4.5, inv_end=-5.0),
            dict(layer="AGUA", pts=[(1500, 500), (1500, 1200)], diam=6.0, inv_start=-4.2, inv_end=-4.2),
            dict(layer="GAS", pts=[(2500, 100), (2500, 1000)], diam=4.0, inv_start=-2.0, inv_end=-2.0)]


def test_textos_iguales_al_plugin():
    assert T.estacion(105.144) == "1+05.14" and T.estacion(99.999) == "1+00.00"
    assert T.cota(745.436) == "745.44'" and T.cota(-3.2) == "-3.20'"
    assert T.diametro(7.97) == '8"' and T.diametro(0.75) == '1"'
    assert T.angulo(44.6) == "45°" and T.angulo(22.3) == "22.5°" and T.angulo(30.0) == "30°"
    assert T.longitud(49.6) == "50" and T.longitud(0.3) == "1"
    assert T.abreviar_material("Fundición dúctil") == "DI" and T.abreviar_material("Material sin definir") == ""
    assert T.lineas_tramo("gravity", False, 50, 8, "PVC", 0.005) == ["INSTALL 50 LF OF", 'NEW 8" PVC PIPE', "@ 0.50%"]


def test_recorrido_sigue_de_frente_y_no_toma_el_ramal():
    pipes = _agua()
    rec = PR.desde(pipes, 0, 1200, 500, FT)
    assert rec is not None
    usados = {rec.grafo.aristas[p.arista].pipe for p in rec.pasos}
    assert usados == {0, 1}                                    # el ramal (2) y el gas (3) no
    # presión: empieza al OESTE
    assert rec.grafo.nodos[rec.nodos[0]][0] == pytest.approx(1000)
    perfil = PD.armar(pipes, [], [], rec, FT)
    assert perfil.e_ini == pytest.approx(100.0)
    assert perfil.e_fin == pytest.approx(100 + 100 + ((1000 ** 2 + 364 ** 2) ** 0.5) * FT)
    assert perfil.pasos[0].z0 == pytest.approx(-4.0)
    # el ramal del agua parte la principal en 1500 (T)
    assert any(abs(n.x - 1500) < 1e-6 for n in perfil.nodos)
    # el gas cruza el recorrido: un cruce, por encima, con el claro entre paredes
    assert len(perfil.cruces) == 1 and perfil.cruces[0].encima
    c = perfil.cruces[0]
    assert c.claro > 0 and "TOP ELEV" in c.lineas[-1]
    # quiebre de 20° a presión = deflexión
    assert any(n.tipo == "deflexion" for n in perfil.nodos)
    assert perfil.titulo[0].startswith('PROFILE 1 - 8 INCH MAIN')


def test_gravedad_empieza_en_la_solera_mas_baja():
    pipes = [dict(layer="ALCANTARILLADO", pts=[(0, 0), (1000, 0)], diam=8.0, inv_start=-10.0, inv_end=-9.0)]
    rec = PR.desde(pipes, 0, 500, 0, FT)
    assert rec.grafo.nodos[rec.nodos[0]][0] == pytest.approx(0)
    pipes[0].update(inv_start=-8.0, inv_end=-9.0)
    rec = PR.desde(pipes, 0, 500, 0, FT)
    assert rec.grafo.nodos[rec.nodos[0]][0] == pytest.approx(1000)
    perfil = PD.armar(pipes, [], [], rec, FT)
    assert perfil.celdas[0].lineas[-1] == "@ 1.00%"
    # la cota de cada punta se puede editar (inicio/fin de la utilidad)
    assert perfil.nodos[0].editable == [(0, 0, "fin")] and perfil.nodos[-1].editable == [(0, 0, "inicio")]


def test_entre_dos_tramos_y_extender():
    pipes = _agua()
    g = PR.marcar_soleras(PR.construir_grafo(pipes, 0, FT), pipes)
    e0 = PR.arista_cerca(g, 1200, 500, 0)
    e1 = PR.arista_cerca(g, 1500, 1000, 2)
    rec = PR.entre(g, e0, e1)
    assert {g.aristas[p.arista].pipe for p in rec.pasos} == {0, 2}
    corto = PR.acortar(rec)
    assert corto is not None and len(corto.pasos) == len(rec.pasos) - 1


@pytest.fixture
def win(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    img = QtGui.QImage(3500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0
    w.pipes = _agua()
    w._refresh_lists(); w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_panel_clic_editar_y_guardar(win):
    import project_io
    dock = win.abrir_perfil()
    assert not dock.isHidden() and win._perfil_rec is None
    win._pick(1200, 500)                                   # clic en la principal de agua
    win._redraw()
    d = win._perfil_datos
    assert d is not None and {p.pipe for p in d.pasos} == {0, 1}
    assert win._perfil_resalte                             # el tramo se resalta en el plano
    win.perfil_vista.resize(900, 320)
    img = win.perfil_vista.grab()                          # se dibuja sin errores
    assert not img.isNull()
    # la unión 0→1 (x=2000) mueve el fin de la 0 y el inicio de la 1 juntos, en UN paso de deshacer
    k = next(k for k, n in enumerate(d.nodos) if abs(n.x - 2000) < 1e-6)
    pasos = len(win._undo)
    assert win._perfil_cota(k, -6.0)
    assert len(win._undo) == pasos + 1
    assert win.pipes[0]["inv_end"] == pytest.approx(-6.0) and win.pipes[1]["inv_start"] == pytest.approx(-6.0)
    assert win._perfil_datos.pasos[k - 1].z1 == pytest.approx(-6.0)   # el perfil ya está al día
    win.undo()
    assert win.pipes[0]["inv_end"] == pytest.approx(-4.5)
    # acortar / extender
    n0 = len(win._perfil_datos.pasos)
    win.perfil_acortar(True)
    assert len(win._perfil_datos.pasos) == n0 - 1
    win.perfil_extender(True)
    assert len(win._perfil_datos.pasos) == n0
    # guardar con nombre → .digproj → abrir
    assert win.perfil_guardar("Principal") == "Principal"
    assert project_io.parse_model(project_io.build_model_dict(win))["perfiles"][0]["nombre"] == "Principal"
    win._pick(1500, 1000); win._redraw()                   # otro tramo: el ramal
    assert {p.pipe for p in win._perfil_datos.pasos} != {0, 1}
    assert win.perfil_abrir(0) and {p.pipe for p in win._perfil_datos.pasos} == {0, 1}
    assert win._perfil_datos.titulo[0].startswith("PROFILE 1")
    win.cerrar_perfil()
    assert not win._perfil_resalte


def test_perfil_guardado_va_al_dxf(win):
    import ezdxf
    import config as C
    from exportar import dxf_export
    win.abrir_perfil()
    win._pick(1200, 500); win._redraw()
    win.perfil_guardar("Principal")
    doc = ezdxf.new("R2010", setup=True); C.apply_imperial_header(doc)
    dxf_export.merge_into(win, doc, marks=True)
    pts = [e for e in doc.modelspace().query("POINT") if e.dxf.layer == "PDFCAD_PERFIL"]
    assert len(pts) == 1
    xd = [v for _c, v in pts[0].get_xdata("PDFCAD")]
    assert xd[0] == "PDFCAD_PERFIL" and "NAME=Principal" in xd
    ini = win.perfiles[0]["ini"]
    x, y = win._to_cad(ini[1], ini[2])
    assert pts[0].dxf.location[0] == pytest.approx(x) and pts[0].dxf.location[1] == pytest.approx(y)


def test_ux_sincronia_detalle_barra_y_corte(win):
    import math
    from PySide6 import QtCore, QtGui, QtWidgets
    win.abrir_perfil()
    v = win.perfil_vista
    v.resize(900, 320)
    assert v.grab() is not None                            # estado vacío guiado, sin errores
    win._pick(1200, 500); win._redraw()
    d = win._perfil_datos
    v.grab()
    # plano → perfil: el ratón sobre la tubería marca su estación
    win._perfil_raton(1200, 501)
    assert v._cursor_e == pytest.approx(100 + 200 * FT)
    win._perfil_raton(1200, 900)
    assert v._cursor_e is None
    # perfil → plano: un punto en el plano
    win._perfil_marcar_estacion(150.0)
    assert win._perfil_marca.isVisible() and win._perfil_marca.pos().x() == pytest.approx(1500)
    win._perfil_marcar_estacion(float("nan"))
    assert not win._perfil_marca.isVisible()
    # nivel de detalle: básico = una línea por callout
    n = next(n for n in d.nodos if len(n.lineas) > 1)
    v.set_detalle("basico")
    assert len(v.lineas(n.lineas)) == 1 and v.lineas(n.lineas)[0] == n.lineas[1]
    v.grab()
    # barra de datos y teclado (Inicio / Fin / ← →)
    QtWidgets.QApplication.sendEvent(v, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_End,
                                                        QtCore.Qt.NoModifier))
    assert v._sel_nodo == len(d.nodos) - 1
    assert "solera" in win.lbl_perfil_datos.text()
    # menú ⋯: guardar desde ahí y aparece marcado
    win.perfil_guardar("A")
    textos = [a.text() for a in win.menu_perfil.actions()]
    assert "A" in textos and any(a.isChecked() for a in win.menu_perfil.actions() if a.text() == "A")
    # el aviso de corte aparece si el recorrido se detuvo por un empate
    win._perfil_rec.ambiguo_fin = True
    win._perfil_corte()
    assert not win.lbl_perfil_corte.isHidden() and "final" in win.lbl_perfil_corte.text()


def test_alertas_recubrimiento_y_contrapendiente():
    from nucleo import perfil_validar as PV
    pipes = [dict(layer="ALCANTARILLADO", pts=[(0, 0), (1000, 0)], diam=8.0, inv_start=-10.0, inv_end=-9.0),
             dict(layer="ALCANTARILLADO", pts=[(1000, 0), (2000, 0)], diam=8.0, inv_start=-9.0, inv_end=-9.5)]
    estructuras = [dict(x=1000.0, y=0.0, rim=-7.0, cod="BZ-2", net="gravity")]
    rec = PR.desde(pipes, 0, 500, 0, FT)
    perfil = PD.armar(pipes, estructuras, [], rec, FT)
    al = PV.validar(perfil, [], 3.0, 3.0)
    clases = {a.clase for a in al}
    assert "recubrimiento" in clases and "contrapendiente" in clases
    rc = next(a for a in al if a.clase == "recubrimiento")
    assert perfil.nodos[rc.nodo].cod == "BZ-2"
    # un aviso de normativa del plano se lleva a su estación
    from nucleo.normas_validar import Aviso
    al = PV.validar(perfil, [Aviso(500.0, 0.0, "pendiente", "Pendiente menor que la mínima", 0)], None, 3.0)
    assert len(al) >= 1 and any(a.mensaje.startswith("Pendiente menor") for a in al)


def test_edicion_precisa_y_alertas_en_la_ventana(win):
    win.abrir_perfil()
    win._pick(1200, 500); win._redraw()
    v = win.perfil_vista
    d = win._perfil_datos
    k = next(k for k, n in enumerate(d.nodos) if abs(n.x - 2000) < 1e-6)
    assert v.editar_cota_nodo(k, -7.25)                    # escribir la cota
    assert win.pipes[0]["inv_end"] == pytest.approx(-7.25) and win.pipes[1]["inv_start"] == pytest.approx(-7.25)
    d = win._perfil_datos
    i = len(d.pasos) - 1                                   # fijar la pendiente del último tramo: mueve su final
    assert v.fijar_pendiente(i, 1.0)
    d = win._perfil_datos
    assert d.pasos[i].pendiente == pytest.approx(0.01, abs=1e-3)
    # alerta: la botonera la cuenta y «siguiente» elige su punto
    from nucleo.normas_validar import Aviso
    win._normas_avisos = [Aviso(1200.0, 500.0, "diametro", "Diámetro fuera de norma", 0)]
    win._perfil_alertas()
    assert not win.btn_perfil_alertas.isHidden() and v.alertas
    a = win.perfil_siguiente_alerta()
    assert a is not None and "Diámetro" in win.lbl_perfil_datos.text()
    v.resize(900, 320); v.grab()


def test_dxf_lleva_inicio_y_fin(win):
    import ezdxf
    import config as C
    from exportar import dxf_export
    win.abrir_perfil()
    win._pick(1200, 500); win._redraw()
    win.perfil_acortar(True)
    win.perfil_guardar("Corto")
    doc = ezdxf.new("R2010", setup=True); C.apply_imperial_header(doc)
    dxf_export.merge_into(win, doc, marks=True)
    pt = next(e for e in doc.modelspace().query("POINT") if e.dxf.layer == "PDFCAD_PERFIL")
    xd = dict(v.split("=", 1) for _c, v in pt.get_xdata("PDFCAD") if "=" in v)
    fin = win.perfiles[0]["fin"]
    x, y = win._to_cad(fin[1], fin[2])
    assert float(xd["FIN_X"]) == pytest.approx(x, abs=1e-5) and float(xd["FIN_Y"]) == pytest.approx(y, abs=1e-5)


def test_ramal_desde_el_rotulo_de_la_t_y_volver(win):
    win.abrir_perfil()
    win._pick(1200, 500); win._redraw()
    v = win.perfil_vista
    d = win._perfil_datos
    k = next(k for k, n in enumerate(d.nodos) if abs(n.x - 1500) < 1e-6)   # la T del ramal de agua
    assert k in v.con_ramal
    v.resize(900, 320); v.grab()                           # el rótulo de la T queda como enlace
    assert any(nodo == k for _r, nodo in v._zonas)
    r = next(r for r, nodo in v._zonas if nodo == k)
    v.ramalPedido.emit(v.ramal_en(r.center()))             # clic en el rótulo
    assert {p.pipe for p in win._perfil_datos.pasos} == {2}
    assert not win.btn_perfil_volver.isHidden() and "Volver" in win.btn_perfil_volver.text()
    assert win.perfil_volver()
    assert {p.pipe for p in win._perfil_datos.pasos} == {0, 1} and win.btn_perfil_volver.isHidden()


def test_en_el_ramal_la_t_dice_el_principal_y_vuelve(win):
    win.abrir_perfil()
    win._pick(1200, 500); win._redraw()
    d = win._perfil_datos
    k = next(k for k, n in enumerate(d.nodos) if abs(n.x - 1500) < 1e-6)
    win.perfil_ramal(k)
    d = win._perfil_datos
    kt = next(k for k, n in enumerate(d.nodos) if abs(n.x - 1500) < 1e-6 and abs(n.y - 500) < 1e-6)
    assert any('8" X 6" TEE' in s for s in d.nodos[kt].lineas)
    assert kt in win.perfil_vista.con_ramal and "Ramal de" in win.lbl_perfil.text()
    win.perfil_ramal(kt)                                   # clic en la T de origen = volver
    assert {p.pipe for p in win._perfil_datos.pasos} == {0, 1}
