"""El editor no rehace todo en cada clic (reporte del usuario 2026-11-14: «selecciono una línea y tarda mucho»).

Medido con 16 761 utilidades + 2 000 válvulas: cada redibujo ubicaba TODAS las válvulas otra vez (44 ms cada una:
88 s por clic). Ahora los lugares se reusan mientras el modelo y las válvulas no cambien, sus ítems se quedan en la
escena, y elegir una línea con un clic es UN redibujo. Siempre el MISMO resultado que calculándolo todo.
"""
import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import valvulas as V  # noqa: E402


def _agua(pts, diam=8.0, **k):
    return dict(layer="AGUA", pts=[tuple(p) for p in pts], diam=diam, diam_elegido=True, **k)


def _red_al_azar(semilla=7, n=60):
    """Tuberías de agua en rejilla con ramales (T, cruces, codos) y válvulas a mano y «del plano» sobre ellas."""
    rnd = random.Random(semilla)
    pipes, vs = [], []
    for k in range(n):
        x, y = rnd.randrange(0, 4000, 200), rnd.randrange(0, 4000, 200)
        largo = rnd.choice((300, 600, 900, 1500))
        if rnd.random() < 0.5:
            pts = [(x, y), (x + largo, y)]
        else:
            pts = [(x, y), (x, y + largo)]
        if rnd.random() < 0.3:                          # con un codo
            pts.append((pts[-1][0] + rnd.choice((-400, 400)), pts[-1][1] + rnd.choice((0, 300))))
        pipes.append(_agua(pts, diam=rnd.choice((6.0, 8.0, 12.0))))
        for _ in range(rnd.randrange(0, 4)):            # varias en el mismo tramo: se estorban entre sí
            t = rnd.random()
            vx, vy = pts[0][0] + t * (pts[1][0] - pts[0][0]), pts[0][1] + t * (pts[1][1] - pts[0][1])
            v = V.nueva(vx, vy, utilidad="AGUA" if rnd.random() < 0.5 else "")
            if rnd.random() < 0.5:
                v["origen"] = "usuario"                 # puesta a mano: las reglas de siempre
            else:
                v.update(x_pdf=vx, y_pdf=vy, sim_w=12.0, sim_h=8.0)
            vs.append(v)
    return pipes, vs


def _foto(lugares):
    return [(l.ok, l.motivo, l.pipe, l.tramo, round(l.x, 9), round(l.y, 9), l.ux, l.uy, l.diam_in, l.bloque,
             l.union, l.largo_ft, l.movida, l.exporta) for l in lugares]


def test_ubicar_todas_con_celdas_da_lo_mismo_que_recorrer_todas(monkeypatch):
    from nucleo.indice_plano import IndiceUtilidades
    pipes, vs = _red_al_azar()
    assert len(vs) > 60
    ft = 0.1
    nuevo = V.ubicar_todas(pipes, [], vs, ft, cerca=IndiceUtilidades(pipes).cerca)
    monkeypatch.setattr(V, "Ubicadas", list)            # como antes: una lista y todas las utilidades
    viejo = V.ubicar_todas(pipes, [], vs, ft)
    assert _foto(nuevo) == _foto(viejo)
    assert sum(l.ok for l in nuevo) > 20 and any(not l.ok for l in nuevo)


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w.aviso_breve = lambda *a, **k: None
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0              # 0.1 ft por px
    w.pipes = [_agua([(100, 300), (900, 300), (900, 800)], inv_start=-4.0, inv_end=-4.0),
               _agua([(100, 600), (800, 600)], inv_start=-4.0, inv_end=-4.0)]
    w.valvulas = [V.nueva(400, 300), V.nueva(500, 600)]
    for v in w.valvulas:
        v["origen"] = "usuario"
    w._refresh_lists(); w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _contar(monkeypatch, obj, nombre):
    veces = []
    original = getattr(obj, nombre)

    def envuelto(*a, **k):
        veces.append(1)
        return original(*a, **k)
    monkeypatch.setattr(obj, nombre, envuelto)
    return veces


def test_los_lugares_de_las_valvulas_se_reusan_hasta_que_algo_cambia(win, monkeypatch):
    antes = _foto(win._lugares_valvulas())
    assert all(l[0] for l in antes) and len(antes) == 2
    veces = _contar(monkeypatch, V, "ubicar_todas")
    win.sel_pipe = 1; win._redraw()                     # elegir, Esc, otra pestaña: nada del modelo cambia
    win.sel_pipe = -1; win._redraw()
    assert _foto(win._lugares_valvulas()) == antes
    assert not veces
    # cambia la tubería: se ubican otra vez y la válvula que ya no cabe lo dice
    win.pipes[1]["pts"] = [(100, 600), (505, 600)]
    win._redraw()
    assert veces
    despues = _foto(win._lugares_valvulas())
    assert despues[0] == antes[0] and not despues[1][0]
    # cambia una válvula (sin tocar el modelo): también
    n = len(veces)
    win.valvulas[0]["x"] = 450.0
    assert win._lugares_valvulas()[0].x == pytest.approx(450.0)
    assert len(veces) > n
    # quien recibe la lista puede cambiarla sin estropear lo guardado
    win._lugares_valvulas().clear()
    assert len(win._lugares_valvulas()) == 2


def test_los_items_de_las_valvulas_se_quedan_y_se_rehacen_si_cambia_algo(win):
    sc = win.canvas.scene()
    items = list(win._valv_items)
    assert len(items) == 4 and all(it.scene() is sc for it in items)
    win.sel_pipe = 0; win._redraw()
    assert [id(it) for it in win._valv_items] == [id(it) for it in items]
    assert all(it.scene() is sc for it in items) and all(it in win._overlay for it in items)
    assert len(win._valv_lugares) == 2 and len(win._valv_vistas) == 2
    # «Capas»: apagar sus válvulas las oculta sin redibujar, y vuelven
    win.capas_apagadas = {"AGUA/valvulas"}; win._aplicar_capas()
    assert not any(it.isVisible() for it in items)
    win.capas_apagadas = set(); win._aplicar_capas()
    assert all(it.isVisible() for it in items)
    # otra válvula: ítems nuevos y los viejos fuera de la escena
    v = V.nueva(700, 600); v["origen"] = "usuario"
    win.valvulas.append(v); win._redraw()
    assert len(win._valv_items) == 6 and not any(it.scene() is sc for it in items)
    # el modelo cambia: también se rehacen (otro lugar)
    otros = list(win._valv_items)
    win.pipes[0]["pts"] = [(100, 300), (900, 300), (900, 900)]; win._redraw()
    assert len(win._valv_items) == 6 and not any(it.scene() is sc for it in otros)
    # sin válvulas no queda ninguna
    win.valvulas = []; win._redraw()
    assert not win._valv_items and not any(it.scene() is sc for it in otros)


def test_la_valvula_se_ve_igual_con_sus_partes_guardadas(win):
    """El moño pintado con las partes guardadas (pluma, relleno, triángulos) = el de `_moño` de siempre."""
    from PySide6 import QtGui
    from ui.comun import valvula_item as VI

    def pinta(fn):
        img = QtGui.QImage(80, 60, QtGui.QImage.Format_ARGB32); img.fill(QtGui.QColor(255, 255, 255))
        p = QtGui.QPainter(img); p.translate(40, 30); fn(p); p.end()
        return bytes(img.constBits())
    for ok, hueca in ((True, False), (True, True), (False, False)):
        color = QtGui.QColor(30, 120, 220)
        it = VI.ValvulaItem(0, 0, 1, 0, 40, 22, color, ok, False, hueca)
        partes = VI._partes(40, 22, color, ok, hueca)
        assert pinta(lambda p: VI._pintar_partes(p, partes)) == pinta(lambda p: VI._moño(p, 40, 22, color, ok, hueca))
        assert it.boundingRect() == it.boundingRect() and it.boundingRect().width() == 44.0


def test_elegir_una_linea_con_un_clic_es_un_solo_redibujo(win, monkeypatch):
    veces = _contar(monkeypatch, win, "_redraw_todo")
    assert win._pick(500, 600)                          # sobre la segunda tubería (lejos de su válvula)… o su válvula
    if win.sel_pipe != 1:                               # (si el clic cayó en la válvula, se elige la línea aparte)
        veces.clear()
        assert win._pick(300, 600)
    assert win.sel_pipe == 1 and len(veces) == 1
    assert [win.pipe_list.row(i) for i in win.pipe_list.selectedItems()] == [1]
    veces.clear()
    assert win._pick(250, 300)                          # la otra: de nuevo uno, y queda solo ella elegida
    assert win.sel_pipe == 0 and len(veces) == 1
    assert [win.pipe_list.row(i) for i in win.pipe_list.selectedItems()] == [0]
    # la capa de líneas resalta la elegida (pluma gruesa) y no la otra
    capa = win._capa_lineas[1]
    assert capa.entradas[capa.de[0]][1].widthF() == 4.0 and capa.entradas[capa.de[1]][1].widthF() == 2.0


def test_el_filtro_del_inventario_no_se_rehace_en_cada_clic_y_si_cuando_cambia(win, monkeypatch):
    veces = _contar(monkeypatch, win, "_filtrar_inventario")
    win.sel_pipe = 1; win._redraw()
    win.sel_pipe = 0; win._redraw()
    assert not veces                                    # mismo modelo, misma pestaña, mismo buscador
    win.buscar_inventario.setText("zzz")                # el buscador filtra ya (como siempre)
    assert veces and all(win.pipe_list.item(r).isHidden() for r in range(win.pipe_list.count()))
    win.buscar_inventario.setText("")
    assert not any(win.pipe_list.item(r).isHidden() for r in range(win.pipe_list.count()))
    veces.clear()
    win.pipes.append(_agua([(100, 900), (700, 900)])); win._refresh_lists(); win._redraw()
    assert veces                                        # otro modelo: se rehace


def test_las_marcas_vigentes_no_se_tocan_y_lo_demas_se_quita(win):
    """El bloque de marcas de las capas se salta al limpiar; los ítems propios de la escena sí se quitan."""
    sc = win.canvas.scene()
    win.pipes.append(_agua([(500, 100), (500, 500)], inv_start=-4.0, inv_end=-4.0))   # cruza: hay marcas
    win._refresh_lists(); win._redraw()
    marcas = win._marcas.todas()
    assert marcas
    win.sel_pipe = 0; win.mode = "move"; win._redraw()  # asas de la elegida: ítems de la escena
    asas = [it for it in win._overlay if it.scene() is sc and it not in win._valv_items
            and it is not win._capa_lineas[1] and it not in win._marcas.capas.values()]
    assert asas and win._overlay_marcas is not None
    win.sel_pipe = -1; win.mode = "idle"; win._redraw()
    assert win._marcas.todas() == marcas and all(m in win._overlay for m in marcas)
    quedan = [it for it in asas if it.scene() is sc]
    assert len(quedan) < len(asas)                      # las asas se fueron de la escena


def test_el_dxf_ubica_las_valvulas_con_el_indice_y_da_lo_mismo(win, monkeypatch):
    """Exportar (2026-11-15, Southwest: 1 564 válvulas × 14 mil utilidades = más de 15 minutos): las válvulas del DXF
    se ubican con el índice de utilidades, sobre las MISMAS tuberías que se exportan; el DXF es el mismo que
    recorriendo todas."""
    import ezdxf
    from exportar import dxf_export
    pipes, vs = _red_al_azar(semilla=3)
    win.pipes, win.valvulas = pipes, vs
    win._refresh_lists()

    def puntos():
        doc = ezdxf.new("R2010")
        dxf_export._export_valvulas(win, doc, doc.modelspace())
        return sorted((tuple(round(c, 9) for c in e.dxf.location), tuple(str(v) for _c, v in e.get_xdata("PDFCAD")))
                      for e in doc.modelspace() if e.dxf.layer == "PDFCAD_VALVULA")
    usados = []
    original = V.ubicar_todas
    monkeypatch.setattr(V, "ubicar_todas", lambda *a, **k: usados.append(k.get("cerca")) or original(*a, **k))
    nuevo = puntos()
    assert usados and usados[-1] is not None and len(nuevo) > 20
    monkeypatch.setattr(type(win), "_cerca_valv_al_dia", None, raising=False)       # como antes: sin índice
    assert puntos() == nuevo and usados[-1] is None
