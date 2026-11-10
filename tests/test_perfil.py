"""Perfil longitudinal en la app (pedido del usuario 2026-10-31): recorrido como el plugin (CREAR_PERFIL_RED),
estaciones, rótulos y cruces."""
import math

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
    assert perfil.e_ini == pytest.approx(0.0)                 # 0+00: la estación real del inicio del eje
    assert perfil.e_fin == pytest.approx(100 + ((1000 ** 2 + 364 ** 2) ** 0.5) * FT)
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
    assert v._cursor_e == pytest.approx(200 * FT)            # desde 0+00
    win._perfil_raton(1200, 900)
    assert v._cursor_e is None
    # perfil → plano: un punto en el plano
    win._perfil_marcar_estacion(50.0)                       # 0+50 = 500 px desde el inicio (1000)
    assert win._perfil_marca.isVisible() and win._perfil_marca.pos().x() == pytest.approx(1500)
    win._perfil_marcar_estacion(float("nan"))
    assert not win._perfil_marca.isVisible()
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
    v.grab()                                               # a su tamaño natural
    # pasar el ratón por todo el perfil (nodos y alertas con su globo): antes, sobre un nodo con texto,
    # «'float' object has no attribute 'globalPosition'» (la estación pisaba al evento)
    from PySide6 import QtCore, QtGui
    globos = []
    for x in range(0, v.width(), 4):
        for y in range(0, v.height(), 8):
            p = QtCore.QPointF(x, y)
            ev = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, p, v.mapToGlobal(p), QtCore.Qt.NoButton,
                                   QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
            v.mouseMoveEvent(ev)
            if v._hover >= 0:
                globos.append(v._hover)
    assert globos                                          # pasó por algún nodo
    # globo con PRIORIDAD: sobre el «!» solo el texto de su alerta; justo encima de él (misma estación), no la alerta
    c, lst = v._marcas_alerta()[0]
    assert v._texto_globo(c) == "\n".join("• " + x.mensaje for x in lst)
    assert "Diámetro" not in v._texto_globo(QtCore.QPointF(c.x(), c.y() - 60))
    ev = QtGui.QHelpEvent(QtCore.QEvent.ToolTip, c.toPoint(), v.mapToGlobal(c.toPoint()))
    assert v.event(ev)                                     # el globo de Qt también lo resuelve la vista


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


def test_inicio_a_y_fin_b_con_dos_clics(win):
    """Elegir el tramo: «① clic donde EMPIEZA (A)» → «② clic donde TERMINA (B)»; el perfil va de A a B, con
    banderas A/B en el plano; «⇄» lo invierte; Esc deja el de ahora (pedido del usuario 2026-11-06)."""
    from PySide6 import QtWidgets
    win.abrir_perfil()
    assert win._perfil_paso == "a" and not win.lbl_perfil_guia.isHidden()
    win._pick(2500, 682); win._redraw()                    # A: en la 2.ª utilidad de la principal (al este)
    assert win._perfil_paso == "b" and win._perfil_rec is not None   # vista previa automática mientras tanto
    win._pick(1200, 500); win._redraw()                    # B: al oeste
    d = win._perfil_datos
    assert win._perfil_paso is None and win.lbl_perfil_guia.isHidden()
    assert d.pasos[0].pipe == 1 and d.pasos[-1].pipe == 0  # las estaciones empiezan en A
    assert win.btn_perfil_ab["a"].text().startswith("A") and win.btn_perfil_ab["b"].text().startswith("B")
    banderas = [it for it in win._perfil_resalte if isinstance(it, QtWidgets.QGraphicsItemGroup)]
    assert len(banderas) == 2
    assert banderas[0].pos().x() > banderas[1].pos().x()   # A al este, B al oeste
    assert win.perfil_invertir() and win._perfil_datos.pasos[0].pipe == 0
    win._perfil_refrescar()                                # rehacer desde las anclas respeta el sentido
    assert win._perfil_datos.pasos[0].pipe == 0
    win.perfil_elegir("mover_b")
    win._on_escape()
    assert win._perfil_paso is None and win._perfil_datos.pasos[0].pipe == 0


def test_pista_con_iman_nuevo_y_limpiar(win):
    """Eligiendo A o B, el ratón muestra dónde caerá el clic (imán a la tubería, verde; otra red, roja);
    «Nuevo perfil» y «Limpiar» dejan el panel en blanco pidiendo A (pedido del usuario 2026-11-06)."""
    win.abrir_perfil()
    assert win.perfil_area.widget() is win.perfil_vista              # el perfil va en un área con barras
    r = win._perfil_pista(1200, 503)                                  # 3 px al lado de la principal
    assert r is not None and r[0] == 0 and r[1][1] == pytest.approx(500)
    assert win._perfil_pista_items and win._perfil_pista_items[0].pos().y() == pytest.approx(500)
    assert win._perfil_pista(1200, 900) is None and not win._perfil_pista_items   # lejos: nada
    win._pick(1200, 500); win._redraw()                               # A
    r = win._perfil_pista(2500, 300)                                  # la línea de GAS: otra red
    assert r is not None and r[0] == 3
    win.perfil_elegir(None)
    assert win._perfil_pista(1200, 503) is None                       # sin elegir A/B no hay pista
    win.perfil_limpiar()
    assert win._perfil_rec is None and win._perfil_datos is None and win._perfil_paso == "a"
    win._pick(1200, 500); win._redraw(); win._pick(2500, 682); win._redraw()
    assert win._perfil_datos is not None
    win.perfil_guardar("X")
    win.perfil_nuevo()
    assert win._perfil_rec is None and win._perfil_paso == "a" and win._perfil_nombre is None
    assert [p["nombre"] for p in win.perfiles] == ["X"]                # los guardados no se tocan


def test_perfil_guardado_abre_desde_su_inicio_a(win):
    """Un perfil guardado vuelve a empezar en su A (`ini`), igual que en Civil 3D, aunque la regla automática
    (oeste/sur) diga lo contrario (reporte 2026-11-07: «Agua-1-pp» salía al revés en Civil 3D)."""
    win.abrir_perfil()
    win._pick(2500, 682); win._redraw()                    # A al este
    win._pick(1200, 500); win._redraw()                    # B al oeste
    assert win._perfil_datos.pasos[0].pipe == 1
    win.perfil_guardar("E-O")
    win.perfil_nuevo()
    assert win.perfil_abrir(0)
    assert win._perfil_datos.pasos[0].pipe == 1 and win._perfil_datos.pasos[-1].pipe == 0


def test_arrastrar_la_bandera_b_cambia_solo_el_fin(win):
    """Las banderas A/B del plano se arrastran (pedido del usuario 2026-11-08): soltar B sobre otro tramo de la
    red corta el perfil ahí; A no se mueve. Soltarla fuera de una tubería no cambia nada."""
    win.abrir_perfil()
    win._pick(2500, 682); win._redraw(); win._pick(1200, 500); win._redraw()
    d = win._perfil_datos
    n0, largo0, a0 = len(d.pasos), d.e_fin - d.e_ini, d.pasos[0].p0
    b = d.pasos[-1].p1
    assert not win._perfil_agarra_bandera(b[0] + 500, b[1])           # lejos de la bandera: no agarra
    assert win._perfil_agarra_bandera(b[0] + 0.5, b[1]) and win._perfil_paso == "mover_b"
    assert not win._perfil_soltar_bandera(1700, 900)                   # fuera de una tubería: nada cambia
    assert win._perfil_paso is None and len(win._perfil_datos.pasos) == n0
    assert win._perfil_agarra_bandera(b[0], b[1])
    assert win._perfil_soltar_bandera(1700, 501)                       # sobre el tramo 1500–2000 de la principal
    d = win._perfil_datos
    assert len(d.pasos) == n0 - 1 and d.e_fin - d.e_ini < largo0
    assert d.pasos[0].p0 == pytest.approx(a0)                           # A sigue donde estaba



def test_iman_de_a_y_b_pega_a_vertices_y_el_perfil_empieza_en_el_nodo(win):
    """Pedido 2026-11-08: el imán de A/B también pega a los vértices (y buzones, válvulas); A en un nodo = el perfil
    empieza AHÍ (sin el tramo del otro lado)."""
    win.abrir_perfil()
    win._pick(1200, 500); win._redraw()
    win.perfil_elegir("a")
    j, q, que = win._perfil_snap(2003, 502)                 # junto al vértice (2000, 500)
    assert que == "vertice" and q == pytest.approx((2000, 500))
    j, q, que = win._perfil_snap(1800, 503)                 # en medio del tramo: sobre la tubería
    assert que == "tuberia" and q[1] == pytest.approx(500)
    win.perfil_elegir(None)
    con_nodo = win._rec_de_anclas([0, 2000.0, 500.0], [1, 2500.0, 682.0])
    en_medio = win._rec_de_anclas([0, 1800.0, 500.0], [1, 2500.0, 682.0])
    assert len(con_nodo.pasos) == len(en_medio.pasos) - 1  # A en el vértice: sin el tramo 1500–2000


def _alcantarillado():
    # baja de oeste a este: -9 → -10 → -11 (el fluido va al ESTE), con buzones en los vértices
    return [dict(layer="ALCANTARILLADO", pts=[(200, 500), (1200, 500)], diam=8.0, inv_start=-9.0, inv_end=-10.0),
            dict(layer="ALCANTARILLADO", pts=[(1200, 500), (2200, 500)], diam=8.0, inv_start=-10.0, inv_end=-11.0)]


def test_clic_de_a_sobre_un_buzon_se_aplica_al_instante(win):
    """Reporte 2026-11-09: con el imán, A caía en un BUZÓN; el clic elegía el buzón y el nuevo A quedaba pendiente
    hasta otro redibujo (p. ej. cambiar una cota). Ahora el clic va directo al perfil."""
    from PySide6 import QtCore
    win.pipes = _alcantarillado()
    win._refresh_lists(); win._redraw()
    assert any(abs(s["x"] - 1200) < 1e-6 for s in win.structures)
    win.abrir_perfil()
    win.on_click(1700, 500, QtCore.Qt.LeftButton)              # A en la 2.ª utilidad
    win.on_click(2100, 500, QtCore.Qt.LeftButton)              # B
    assert win._perfil_paso is None and len(win._perfil_datos.pasos) == 1
    win.btn_perfil_ab["a"].click()                            # nuevo A…
    win.on_click(1205, 503, QtCore.Qt.LeftButton)              # …sobre el buzón de (1200, 500)
    d = win._perfil_datos
    assert win._perfil_paso is None and d.pasos[0].p0 == pytest.approx((1200, 500))
    win.btn_perfil_ab["a"].click()
    win.on_click(205, 500, QtCore.Qt.LeftButton)               # y en la punta oeste: dos tramos, sin otro redibujo
    assert len(win._perfil_datos.pasos) == 2 and win._perfil_datos.pasos[0].p0 == pytest.approx((200, 500))


def test_flujo_contrapendiente_no_depende_de_donde_esta_a():
    """Pedido 2026-11-09: con A en la punta ALTA cada tramo salía «contrapendiente». El sentido del fluido es el de
    la utilidad (`pipe["flujo"]`) o, automático, hacia el extremo más bajo del recorrido."""
    from nucleo import flujo as FL, perfil_validar as PV
    pipes = _alcantarillado()
    rec = PR.desde(pipes, 0, 700, 500, FT)
    for r in (rec, PR.invertir(rec)):                          # A abajo (este) o arriba (oeste): igual
        perfil = PD.armar(pipes, [], [], r, FT)
        assert all(p.flujo and not p.flujo_fijo for p in perfil.pasos)
        assert not [a for a in PV.validar(perfil, [], None, 3.0) if a.clase == "contrapendiente"]
    # el usuario dice que la 2.ª utilidad va al revés (del fin al inicio): ese tramo sube hacia donde va el fluido
    FL.poner(pipes[1], FL.ATRAS)
    perfil = PD.armar(pipes, [], [], PR.invertir(rec), FT)
    paso = next(p for p in perfil.pasos if p.pipe == 1)
    assert paso.flujo_fijo
    al = [a for a in PV.validar(perfil, [], None, 3.0) if a.clase == "contrapendiente"]
    assert len(al) == 1 and perfil.pasos[al[0].paso].pipe == 1
    assert FL.poner(pipes[1], FL.AUTO) and "flujo" not in pipes[1]


def test_flujo_al_unir_utilidades_sigue_igual():
    from nucleo import flujo as FL, unir_utilidades as UU
    p = dict(layer="DRENAJE", pts=[(0, 0), (10, 0)], flujo=FL.ADELANTE)
    q = UU.invertir(p)
    assert q["pts"][0] == (10, 0) and q["flujo"] == FL.ATRAS
    assert FL.flechas_plano(q["pts"], q["flujo"])[0][2] == pytest.approx(0.0)   # sigue apuntando al este


def test_flujo_en_propiedades_plano_y_perfil(win):
    """La fila «Flujo» (solo gravedad) cambia el sentido con un paso de deshacer y pone flechas en el plano; en el
    perfil, clic en la flecha = invertir esa utilidad y el menú lo hace con todo el perfil."""
    from PySide6 import QtCore, QtWidgets
    from nucleo import flujo as FL
    win.pipes = _alcantarillado() + [dict(layer="AGUA", pts=[(200, 900), (1200, 900)], diam=8.0),
                                     dict(layer="ELECTRICO", pts=[(200, 1200), (1200, 1200)], diam=4.0)]
    win._refresh_lists(); win._redraw()
    form = win.gprop.layout()
    win.pipe_list.setCurrentRow(3)
    assert not form.isRowVisible(win.box_flujo)                # eléctrico (conductos): no
    assert not win.poner_flujo([3], FL.ADELANTE) and "flujo" not in win.pipes[3]
    win.pipe_list.setCurrentRow(2)
    assert form.isRowVisible(win.box_flujo)                    # agua (presión): sí
    assert "presión" in win.btn_flujo[FL.AUTO].toolTip()
    win.pipe_list.setCurrentRow(0)
    assert form.isRowVisible(win.box_flujo) and win.btn_flujo[FL.AUTO].isChecked()
    win.btn_flujo[FL.ATRAS].click()
    assert win.pipes[0]["flujo"] == FL.ATRAS and win.btn_flujo[FL.ATRAS].isChecked()
    flechas = [it for it in win._overlay if isinstance(it, QtWidgets.QGraphicsPathItem)
               and it.flags() & QtWidgets.QGraphicsItem.ItemIgnoresTransformations]
    assert len(flechas) == 2 and all(f.rotation() == pytest.approx(180.0) for f in flechas)   # círculo + flecha,
    #                                                                              hacia el oeste
    win.undo()
    assert "flujo" not in win.pipes[0]
    # perfil: A al oeste (punta alta), B al este
    win.abrir_perfil()
    win.perfil_nuevo()
    win.on_click(300, 500, QtCore.Qt.LeftButton)
    win.on_click(2100, 500, QtCore.Qt.LeftButton)
    d = win._perfil_datos
    assert [p.flujo for p in d.pasos] == [1, 1] and not win.perfil_vista.alertas
    v = win.perfil_vista
    v.resize(1200, 500); v._calcular()
    (i, c, _a), = [f for f in v._flechas_flujo() if f[0] == 0]
    assert "hacia B" in v._texto_globo(c)
    v._clic_flujo(c)                                           # invertir la 1.ª utilidad
    assert win.pipes[0]["flujo"] == FL.ATRAS and win._perfil_datos.pasos[0].flujo == -1
    assert any(a.clase == "contrapendiente" for a in win.perfil_vista.alertas)
    v.flujoCambiado.emit(0, 0, True)                           # «Todo el perfil: automático»
    assert all("flujo" not in p for p in win.pipes)
    v.flujoCambiado.emit(0, 1, True)                           # «Todo el perfil: hacia B»
    assert [win.pipes[j].get("flujo") for j in (0, 1)] == [FL.ADELANTE, FL.ADELANTE]


def test_menu_del_perfil_sin_extender_ni_acortar(win):
    win.abrir_perfil()
    win._pick(1200, 500); win._redraw()
    win._perfil_lista()
    textos = [a.text() for a in win.menu_perfil.actions()]
    assert not any("Extender" in s or "Acortar" in s for s in textos)


def test_flujo_en_presion_sin_indicar_y_con_un_clic(win):
    """Pedido 2026-11-09: el sentido del flujo también en presión (agua, gas). Sin pendiente que lo diga, el
    automático es «sin indicar» (doble flecha) y no hay contrapendiente; un clic lo pone hacia B."""
    from PySide6 import QtCore
    from nucleo import flujo as FL
    win.pipes = [dict(layer="AGUA", pts=[(200, 500), (1200, 500)], diam=8.0, inv_start=-4.0, inv_end=-3.0),
                 dict(layer="AGUA", pts=[(1200, 500), (2200, 500)], diam=8.0, inv_start=-3.0, inv_end=-2.0)]
    win._refresh_lists(); win._redraw()
    win.abrir_perfil()
    win.perfil_nuevo()
    win.on_click(300, 500, QtCore.Qt.LeftButton)
    win.on_click(2100, 500, QtCore.Qt.LeftButton)
    d = win._perfil_datos
    assert d.tipo == "pressure" and [p.flujo for p in d.pasos] == [0, 0]
    assert not any(a.clase == "contrapendiente" for a in win.perfil_vista.alertas)
    v = win.perfil_vista
    v.resize(1200, 500); v._calcular()
    (i, c, _a), = [f for f in v._flechas_flujo() if f[0] == 0]
    assert "sin indicar" in v._texto_globo(c)
    v._clic_flujo(c)                                           # sin indicar → hacia B
    paso = win._perfil_datos.pasos[0]
    assert paso.flujo == 1 and paso.flujo_fijo
    assert win.pipes[0]["flujo"] == FL.de_paso(1, paso.invertida)
    v.flujoCambiado.emit(0, 0, True)                           # «Todo el perfil: sin indicar»
    assert all("flujo" not in p for p in win.pipes)


def _con_curva(x0=0.0, y0=0.0):
    """Eléctrico en «L» (1000 px al este y 1000 px al sur) con una curva de 30 ft (300 px a 0.1 ft/px) en la esquina."""
    pipes = [dict(layer="ELECTRICO", pts=[(x0, y0), (x0 + 1000, y0), (x0 + 1000, y0 + 1000)], diam=4.0,
                  inv_start=-4.0, inv_end=-5.0)]
    cv = {"x": x0 + 1000, "y": y0, "curve": True, "radius_ft": 30.0, "net": "conduit", "cod": "CV-1"}
    centro = (x0 + 700, y0 + 300)
    medio = (centro[0] + 300 * math.cos(-math.pi / 4), centro[1] + 300 * math.sin(-math.pi / 4))
    return pipes, cv, centro, medio


def test_perfil_sigue_la_curva_de_la_utilidad():
    """Reporte 2026-11-10: el recorrido A→B iba por la ESQUINA de una curva. Ahora la traza en planta es la que se
    dibuja (recto + arco + recto) y las estaciones se miden por la curva, como el eje de Civil 3D."""
    pipes, cv, centro, medio = _con_curva()
    g = PR.marcar_soleras(PR.construir_grafo(pipes, 0, FT), pipes)
    rec = PR.entre(g, PR.arista_cerca(g, 500, 0, 0), PR.arista_cerca(g, 1000, 500, 0))   # de A a B por la curva
    assert rec.grafo.nodos[rec.nodos[0]] == pytest.approx((0, 0))
    sin = PD.armar(pipes, [], [], rec, FT)                     # sin curva: por la esquina, como siempre
    assert sin.e_fin - sin.e_ini == pytest.approx(200.0) and not sin.pasos[0].traza
    perfil = PD.armar(pipes, [cv], [], rec, FT)
    real = (700 + 700 + math.pi / 2 * 300) * FT
    assert perfil.e_fin - perfil.e_ini == pytest.approx(real)
    e_medio = (700 + math.pi / 4 * 300) * FT
    assert perfil.nodos[1].e == pytest.approx(e_medio)          # el nodo de la curva = el punto medio del arco
    a, b = perfil.pasos
    assert a.puntos[0] == pytest.approx((0, 0)) and a.puntos[-1] == pytest.approx(medio)
    assert b.puntos[0] == pytest.approx(medio) and b.puntos[-1] == pytest.approx((1000, 1000))
    for q in a.puntos + b.puntos:                               # sobre las rectas o sobre el arco, nunca la esquina
        sobre_recta = abs(q[1]) < 1e-6 and q[0] <= 700 + 1e-6 or abs(q[0] - 1000) < 1e-6 and q[1] >= 300 - 1e-6
        assert sobre_recta or math.dist(q, centro) == pytest.approx(300)
    # plano ↔ perfil por la curva
    assert a.proyectar(*medio)[1] == pytest.approx(e_medio) and a.punto_en(e_medio) == pytest.approx(medio)
    assert a.e_en(0.5) == pytest.approx(50.0)                  # el recto, como antes
    assert b.e_en(1.0) == pytest.approx(perfil.e_fin)


def test_resalte_del_perfil_en_el_plano_sigue_la_curva(win):
    from PySide6 import QtWidgets
    pipes, cv, _centro, medio = _con_curva(200, 300)
    win.pipes = pipes
    win._refresh_lists()
    win.structures.append(cv)
    win._redraw()
    from PySide6 import QtCore
    win.abrir_perfil()
    win.on_click(600, 300, QtCore.Qt.LeftButton)               # A antes de la curva
    win.on_click(1200, 1000, QtCore.Qt.LeftButton)             # B después
    d = win._perfil_datos
    assert d is not None and len(d.pasos) == 2
    camino = next(it for it in win._perfil_resalte if isinstance(it, QtWidgets.QGraphicsPathItem)).path()
    pts = [(camino.elementAt(i).x, camino.elementAt(i).y) for i in range(camino.elementCount())]
    assert any(math.dist(q, medio) < 1e-6 for q in pts)
    assert all(math.dist(q, (1200, 300)) > 50 for q in pts)    # no pasa por la esquina
    assert win._perfil_punto_nodo(d, 1) == pytest.approx(medio)
    win._perfil_marcar_estacion(d.nodos[1].e)
    assert (win._perfil_marca.pos().x(), win._perfil_marca.pos().y()) == pytest.approx(medio)
