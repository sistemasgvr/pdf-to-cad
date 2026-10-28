"""Capas de marcas del lienzo (pedido del usuario 2026-10-16: con 16 761 utilidades los avisos
trababan la ventana). Las marcas de tamaño fijo (cruces, alertas, accesorios, avisos, C-n) las
pinta una capa por Z en vez de ser ítems sueltos de la escena: se ven IGUAL (salvo el suavizado de
bordes de una fracción de píxel de los SELLOS, 2026-10-17), dan el MISMO tooltip, y un redibujo sin
cambios del modelo reusa los mismos objetos."""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

AQUI = os.path.dirname(os.path.abspath(__file__))
PRESENTACION = os.path.join(AQUI, "escenarios", "presentacion_1_3_1.digproj")


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
    # 1244 × 778 (antes 1200 × 800): el riel (2.0.0) ocupa 44 px de ancho y ya no hay barra de menús;
    # así el plano mide lo mismo que antes y se muestrean los mismos puntos
    w.show(); w.resize(1244, 778)
    w._open_project_path(PRESENTACION)
    app.processEvents()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _vistas(w):
    """(imagen, tooltips) de varias vistas con zoom sobre las marcas."""
    from PySide6 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance()
    puntos = [(w._accesorios[0]["x"], w._accesorios[0]["y"]), w._conflict_hits[0][:2],
              (w._conflictos[0].x, w._conflictos[0].y)]
    out = []
    for x, y in puntos:
        for z in (1.5, 6.0):
            w.canvas.resetTransform(); w.canvas.scale(z, z); w.canvas.centerOn(x, y)
            for _ in range(4):
                app.processEvents()
            img = w.canvas.viewport().grab().toImage().convertToFormat(QtGui.QImage.Format_RGB32)
            px = np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()).copy()
            tips = []
            for vx in range(0, w.canvas.viewport().width(), 9):
                for vy in range(0, w.canvas.viewport().height(), 9):
                    sp = w.canvas.mapToScene(QtCore.QPoint(vx, vy))
                    t = w._marcas.tooltip_en(sp, w.canvas.viewport()) if w._marcas.capas else ""
                    if not t:
                        for it in w.canvas.scene().items(sp, QtCore.Qt.IntersectsItemShape,
                                                         QtCore.Qt.DescendingOrder, w.canvas.viewportTransform()):
                            if it.toolTip():
                                t = it.toolTip()
                                break
                    tips.append(t)
            out.append((px, tips))
    return out


def test_capas_se_ven_igual_y_dan_el_mismo_tooltip(win, monkeypatch):
    from ui.comun import capa_marcas_vista
    from ui.ventana import ventana_dibujo
    monkeypatch.setattr(capa_marcas_vista, "DESPEJAR", False)   # como antes: sin nivel de detalle
    _vistas(win)                                           # el fondo nítido del PDF termina de cargar
    nuevo = _vistas(win)
    assert any(t for _px, tips in nuevo for t in tips)

    def a_la_escena(self, it):                             # como antes: cada marca a la escena
        self.canvas.scene().addItem(it)
        return it
    monkeypatch.setattr(ventana_dibujo.DibujoMixin, "_marca", a_la_escena)
    win._marcas = None                                     # rearmar (si no, se reusan las mismas capas)
    win._redraw()
    viejo = _vistas(win)
    for (pa, ta), (pb, tb) in zip(nuevo, viejo):
        assert _distintos(pa, pb) <= 0.003           # sellos: solo bordes de una fracción de píxel
        assert ta == tb


def _distintos(pa, pb, umbral=60):
    """Fracción de píxeles que cambian más de `umbral` (de 255) en algún canal."""
    d = np.abs(pa.reshape(-1, 4).astype(int) - pb.reshape(-1, 4).astype(int)).max(axis=1)
    return float((d > umbral).mean())


def test_sellos_a_125_por_ciento_se_ven_igual(win, monkeypatch):
    """Con escala de pantalla 125 % (la del usuario) y zooms cualesquiera, el sello copiado se ve
    como la marca dibujada por Qt: solo cambia el suavizado de bordes (≤ ¼ de píxel)."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from ui.comun import capa_marcas_vista
    from ui.ventana import ventana_dibujo
    monkeypatch.setattr(capa_marcas_vista, "DESPEJAR", False)
    app = QtWidgets.QApplication.instance()
    vp = win.canvas.viewport()

    def fotos():
        out = []
        for a in win._accesorios[:2] + [dict(x=h[0], y=h[1]) for h in win._conflict_hits[:2]]:
            for z in (1.3713, 5.1377, 0.4421):
                win.canvas.resetTransform(); win.canvas.scale(z, z)
                win.canvas.centerOn(a["x"] + 0.37, a["y"] + 0.81)
                for _ in range(4):
                    app.processEvents()
                img = QtGui.QImage(int((vp.width() + 306) * 1.25) + 2, int((vp.height() + 71) * 1.25) + 2,
                                   QtGui.QImage.Format_ARGB32_Premultiplied)
                img.setDevicePixelRatio(1.25); img.fill(QtGui.QColor("black"))
                vp.render(img, QtCore.QPoint(306, 71))
                out.append(np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()).copy())
        return out
    fotos()
    nuevo = fotos()
    monkeypatch.setattr(ventana_dibujo.DibujoMixin, "_marca",
                        lambda self, it: (self.canvas.scene().addItem(it), it)[1])
    win._marcas = None
    win._redraw()
    for pa, pb in zip(nuevo, fotos()):
        assert _distintos(pa, pb) <= 0.003


def test_redibujo_sin_cambios_reusa_las_marcas(win):
    from ui.comun.accesorios_view import EtiquetaAccesorio
    antes = [it for it in win._overlay if isinstance(it, EtiquetaAccesorio)]
    win.sel_pipe = 2; win._redraw()                        # elegir: el modelo no cambia
    despues = [it for it in win._overlay if isinstance(it, EtiquetaAccesorio)]
    assert antes and [id(a) for a in antes] == [id(b) for b in despues]
    assert all(a.toolTip() for a in despues)
    p = win.pipes[win._accesorios[0]["pipes"][0]]           # mover una utilidad: lo suyo se rehace
    p["pts"] = [(x, y + 40.0) for x, y in p["pts"]]
    win._redraw()
    otra = [it for it in win._overlay if isinstance(it, EtiquetaAccesorio)]
    assert {id(b) for b in otra} != {id(a) for a in antes}


def test_hover_da_el_tooltip_de_la_marca(win):
    from PySide6 import QtCore, QtWidgets
    capa = next(c for c in win._marcas.capas.values() if c.marcas)
    it = capa.marcas[0]
    win.canvas.resetTransform(); win.canvas.scale(2.0, 2.0); win.canvas.centerOn(it.pos())
    QtWidgets.QApplication.instance().processEvents()
    ev = QtWidgets.QGraphicsSceneHoverEvent(QtCore.QEvent.GraphicsSceneHoverMove)
    ev.setScenePos(it.pos())
    capa.hoverMoveEvent(ev)
    esperado = win._marcas.tooltip_en(it.pos(), win.canvas.viewport())
    assert esperado and capa.toolTip() == esperado
    ev.setScenePos(it.pos() + QtCore.QPointF(5000, 5000))  # lejos de todo: sin tooltip
    capa.hoverMoveEvent(ev)
    assert capa.toolTip() == ""


def test_las_marcas_no_entran_a_la_escena(win):
    sc = win.canvas.scene()
    marcas = [m for c in win._marcas.capas.values() for m in c.marcas]
    assert marcas and all(m.scene() is None for m in marcas)
    assert all(c.scene() is sc for c in win._marcas.capas.values())


def test_repintado_parcial_no_borra_marcas(win):
    """La cruz del cursor repinta solo dos franjas; Qt da esa zona en px FÍSICOS de la ventana
    (desplazamiento de la vista + escala de pantalla). Reporte 2026-10-17: con 125 % la capa
    descartaba marcas que estaban bajo la cruz y las «borraba». Se repinta solo la franja, como
    en la ventana real, y debe quedar igual que el repintado completo."""
    from PySide6 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance()
    vp = win.canvas.viewport()
    dpr, off = 1.25, QtCore.QPoint(306, 71)

    def lienzo():
        img = QtGui.QImage(int((vp.width() + off.x()) * dpr) + 2, int((vp.height() + off.y()) * dpr) + 2,
                           QtGui.QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(QtGui.QColor("magenta"))
        return img
    for a in win._accesorios[:4]:
        win.canvas.resetTransform(); win.canvas.scale(1.5, 1.5); win.canvas.centerOn(a["x"], a["y"])
        for _ in range(4):
            app.processEvents()
        c = vp.rect().center()
        franjas = QtGui.QRegion(0, c.y() - 2, vp.width(), 5) | QtGui.QRegion(c.x() - 2, 0, 5, vp.height())
        completo, parcial = lienzo(), lienzo()
        vp.render(completo, off)
        vp.render(parcial, off, franjas)
        for r in franjas:
            for y in range(int((r.top() + off.y()) * dpr) + 1, int((r.bottom() + off.y()) * dpr)):
                for x in range(int((r.left() + off.x()) * dpr) + 1, int((r.right() + off.x()) * dpr)):
                    assert completo.pixel(x, y) == parcial.pixel(x, y), (x, y)


# ─────────────────────────── nivel de detalle, imagen de la vista, reuso de capas ───────────────────────────

def _tocan(a, b):
    return a[0] + 1 <= b[2] - 1 and a[2] - 1 >= b[0] + 1 and a[1] + 1 <= b[3] - 1 and a[3] - 1 >= b[1] + 1


def test_despejar_por_prioridad_sin_solapes():
    import random
    from ui.comun.despeje_rotulos import despejar
    rng = random.Random(3)
    cajas = []
    for _ in range(400):
        x, y = rng.uniform(0, 600), rng.uniform(0, 400)
        cajas.append((x, y, x + rng.uniform(20, 90), y + 18))
    puestos = despejar(cajas)
    assert puestos[0]                                   # el de más prioridad siempre
    elegidas = [c for c, p in zip(cajas, puestos) if p]
    for i, a in enumerate(elegidas):                    # ninguna toca a otra
        assert not any(_tocan(a, b) for b in elegidas[i + 1:])
    for c, p in zip(cajas, puestos):                    # y cada descartada toca a una elegida
        if not p:
            assert any(_tocan(c, e) for e in elegidas)
    assert despejar([(i * 200.0, 0.0, i * 200.0 + 90, 18.0) for i in range(20)]).all()


def _rotulos_en_pantalla(win):
    """(capa, índice, caja en px de la vista, visible) de cada marca con rótulo."""
    import numpy as np
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance().processEvents()
    W = win.canvas.viewportTransform()
    out = []
    for capa in win._marcas.capas.values():
        if not capa.con_rotulos:
            continue
        vis = win._marcas.rotulos_visibles(capa, win.canvas.viewport())
        capa._puntos()
        for k in np.flatnonzero(~np.isnan(capa._np_rots[:, 0])).tolist():
            p = W.map(capa.marcas[k].pos())
            l, t, r, b = capa._np_rots[k]
            out.append((capa, k, (p.x() + l, p.y() + t, p.x() + r, p.y() + b), vis is None or bool(vis[k])))
    return out


def test_nivel_de_detalle_de_lejos_sin_solapes_y_de_cerca_todos(win):
    win.canvas.resetTransform(); win.canvas.scale(0.05, 0.05)
    a = win._accesorios[0]
    win.canvas.centerOn(a["x"], a["y"])
    ancho, alto = win.canvas.viewport().width(), win.canvas.viewport().height()
    rot = [r for r in _rotulos_en_pantalla(win)
           if r[2][2] > 0 and r[2][0] < ancho and r[2][3] > 0 and r[2][1] < alto]
    vistos = [c for _capa, _k, c, v in rot if v]
    assert len(vistos) < len(rot)                       # de lejos se tapan: no se ven todos
    for i, c in enumerate(vistos):
        assert not any(_tocan(c, d) for d in vistos[i + 1:])
    win.canvas.resetTransform(); win.canvas.scale(60.0, 60.0)    # de cerca: no se tapa ninguno
    win.canvas.centerOn(a["x"], a["y"])
    cerca = [v for _capa, _k, c, v in _rotulos_en_pantalla(win) if c[2] > 0 and c[0] < ancho and c[3] > 0 and c[1] < alto]
    assert cerca and all(cerca)


def test_rotulo_oculto_su_punto_sigue_dando_el_globo(win):
    win.canvas.resetTransform(); win.canvas.scale(0.05, 0.05)
    win.canvas.centerOn(win._accesorios[0]["x"], win._accesorios[0]["y"])
    capa, k, _caja, _v = next(r for r in _rotulos_en_pantalla(win) if not r[3] and r[0].zValue() < 1000)
    it = capa.marcas[k]
    assert win._marcas.tooltip_en(it.pos(), win.canvas.viewport()) == it.toolTip()


def test_imagen_de_la_vista_igual_que_pintar_cada_marca(win, monkeypatch):
    """La imagen guardada de la capa (para que la cruz del cursor solo copie) da los mismos píxeles que
    pintar cada marca, también al repintar solo una franja (escala 125 % y desplazamiento)."""
    import numpy as np
    from PySide6 import QtCore, QtGui, QtWidgets
    from ui.comun import capa_marcas_vista
    app = QtWidgets.QApplication.instance()
    vp = win.canvas.viewport()
    dpr, off = 1.25, QtCore.QPoint(306, 71)
    a = win._accesorios[0]
    win.canvas.resetTransform(); win.canvas.scale(1.7, 1.7); win.canvas.centerOn(a["x"], a["y"])
    for _ in range(4):
        app.processEvents()

    def foto(region=None):
        img = QtGui.QImage(int((vp.width() + off.x()) * dpr) + 2, int((vp.height() + off.y()) * dpr) + 2,
                           QtGui.QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(QtGui.QColor("black"))
        if region is None:
            vp.render(img, off)
        else:
            vp.render(img, off, region)
        return np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()).astype(int).copy()
    monkeypatch.setattr(capa_marcas_vista, "CACHE_MIN", 10 ** 9)
    sin = foto()
    monkeypatch.setattr(capa_marcas_vista, "CACHE_MIN", 1)
    con = foto()
    assert np.abs(con - sin).max() <= 2
    assert any(c._cache is not None for c in win._marcas.capas.values())
    # la cruz: repintar una franja copia de la imagen = lo mismo que la vista entera en esa franja
    def imagen(region=None):
        img = QtGui.QImage(int((vp.width() + off.x()) * dpr) + 2, int((vp.height() + off.y()) * dpr) + 2,
                           QtGui.QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(QtGui.QColor("magenta"))
        if region is None:
            vp.render(img, off)
        else:
            vp.render(img, off, region)
        return img
    cc = vp.rect().center()                            # la cruz del cursor: dos franjas
    franja = QtGui.QRegion(0, cc.y() - 2, vp.width(), 5) | QtGui.QRegion(cc.x() - 2, 0, 5, vp.height())
    completa, parcial = imagen(), imagen(franja)
    for r in franja:                                   # lejos de los bordes de la franja (redondeo de Qt)
        for y in range(int((r.top() + off.y()) * dpr) + 2, int((r.bottom() + off.y()) * dpr) - 1):
            for x in range(int((r.left() + off.x()) * dpr) + 2, int((r.right() + off.x()) * dpr) - 1):
                assert completa.pixel(x, y) == parcial.pixel(x, y), (x, y)


def test_elegir_reusa_las_capas_y_cambiar_el_modelo_las_rehace(win):
    capas = {id(c) for c in win._marcas.capas.values()}
    win.sel_pipe = 1; win._redraw()
    assert {id(c) for c in win._marcas.capas.values()} == capas
    assert all(c.scene() is win.canvas.scene() for c in win._marcas.capas.values())
    p = win.pipes[win._accesorios[0]["pipes"][0]]
    p["pts"] = [(x, y + 40.0) for x, y in p["pts"]]
    win._redraw()
    assert {id(c) for c in win._marcas.capas.values()}.isdisjoint(capas)


@pytest.mark.parametrize("dpr, off", [(1.0, (0, 0)), (1.25, (306, 71))])
def test_desplazar_reusa_piezas_y_se_ve_igual_que_armarla_de_cero(win, monkeypatch, dpr, off):
    """Al DESPLAZAR (2026-10-19, AGUA 2 de lejos: cada paso rehacía la imagen entera de la capa) se reusan
    las piezas ya armadas si la vista se corrió píxeles físicos ENTEROS, y solo se arma la franja que
    entra: los mismos píxeles que armar la imagen de cero en esa vista (pasos enteros y fraccionarios)."""
    import numpy as np
    from PySide6 import QtCore, QtGui, QtWidgets
    from ui.comun import capa_marcas_vista
    app = QtWidgets.QApplication.instance()
    monkeypatch.setattr(capa_marcas_vista, "CACHE_MIN", 1)
    vp = win.canvas.viewport()
    o = QtCore.QPoint(*off)
    win.canvas.resetTransform(); win.canvas.scale(1.3, 1.3)
    a = win._accesorios[0]
    win.canvas.centerOn(a["x"], a["y"])
    for _ in range(4):
        app.processEvents()
    armado = []
    original = capa_marcas_vista.CacheVistaMixin._armar_cache

    def contar(self, painter, W, S, vista, X0, Y0, X1, Y1, *r):
        armado.append((X1 - X0) * (Y1 - Y0))
        return original(self, painter, W, S, vista, X0, Y0, X1, Y1, *r)
    monkeypatch.setattr(capa_marcas_vista.CacheVistaMixin, "_armar_cache", contar)

    def foto():
        img = QtGui.QImage(int((vp.width() + o.x()) * dpr) + 2, int((vp.height() + o.y()) * dpr) + 2,
                           QtGui.QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(QtGui.QColor("magenta"))
        vp.render(img, o)
        return np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()).copy()
    foto()
    completa = (vp.width() * dpr) * (vp.height() * dpr)   # armar la vista entera
    hs, vs = win.canvas.horizontalScrollBar(), win.canvas.verticalScrollBar()
    reusos = 0
    for dx, dy in ((4, 0), (8, 4), (3, 0), (-5, 2), (4, -8), (12, 0)):
        hs.setValue(hs.value() + dx); vs.setValue(vs.value() + dy)
        app.processEvents()
        armado.clear()
        con_piezas = foto()
        if sum(armado) < 0.9 * completa:               # solo la franja que entró (o nada)
            reusos += 1
        assert any(c._cache for c in win._marcas.capas.values())   # sí pintó desde las piezas
        for c in win._marcas.capas.values():             # = armar de cero en esta misma vista
            c._cache = None
            c._ultima = None
        de_cero = foto()
        assert np.array_equal(con_piezas, de_cero), (dx, dy)
    assert reusos >= 2


@pytest.mark.parametrize("en_escena", [False, True])
def test_texto_de_cruce_con_molde_igual_que_un_item_de_texto_por_cruce(win, monkeypatch, en_escena):
    """El texto «!», «↕», «✓» de cada cruce se mide y pinta con un QGraphicsTextItem MOLDE por aspecto
    (`texto_marca`, 2026-10-19): los mismos píxeles —con sellos y pintado por Qt en la escena, al 100 % y
    al 125 %— y los mismos globos que con un QGraphicsTextItem por cruce."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from ui.comun import capa_marcas_vista, texto_marca
    from ui.ventana import ventana_dibujo
    monkeypatch.setattr(capa_marcas_vista, "DESPEJAR", False)
    if en_escena:
        monkeypatch.setattr(ventana_dibujo.DibujoMixin, "_marca",
                            lambda self, it: (self.canvas.scene().addItem(it), it)[1])
    app = QtWidgets.QApplication.instance()
    vp = win.canvas.viewport()

    def rehacer():
        win._marcas = None; win._grupos_previos = None
        win._redraw()

    def fotos():
        out = []
        for h in win._conflict_hits[:3]:
            for z in (1.3713, 5.1377):
                win.canvas.resetTransform(); win.canvas.scale(z, z)
                win.canvas.centerOn(h[0] + 0.37, h[1] + 0.81)
                for _ in range(4):
                    app.processEvents()
                for dpr, off in ((1.0, QtCore.QPoint(0, 0)), (1.25, QtCore.QPoint(306, 71))):
                    img = QtGui.QImage(int((vp.width() + off.x()) * dpr) + 2, int((vp.height() + off.y()) * dpr) + 2,
                                       QtGui.QImage.Format_ARGB32_Premultiplied)
                    img.setDevicePixelRatio(dpr); img.fill(QtGui.QColor("black"))
                    vp.render(img, off)
                    out.append(np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()).copy())
        return out

    rehacer()
    assert any(isinstance(it, texto_marca.TextoMarca) for it in win._overlay)
    fotos()
    nuevo, tips_nuevo = fotos(), _vistas(win)

    def viejo(texto, color, fuente, clave_fuente=None):
        t = QtWidgets.QGraphicsTextItem(texto); t.setDefaultTextColor(color); t.setFont(fuente)
        t.document().setDocumentMargin(0)
        return t
    monkeypatch.setattr(texto_marca, "nuevo", viejo)
    for it in list(win.canvas.scene().items()):
        if isinstance(it, texto_marca.TextoMarca):
            win.canvas.scene().removeItem(it)
    rehacer()
    assert not any(isinstance(it, texto_marca.TextoMarca) for it in win._overlay)
    fotos()
    for pa, pb in zip(nuevo, fotos()):
        assert np.array_equal(pa, pb)
    assert [t for _p, t in tips_nuevo] == [t for _p, t in _vistas(win)]
