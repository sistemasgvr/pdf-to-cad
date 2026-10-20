"""Las utilidades del lienzo en UNA capa (`ui/comun/capa_lineas`, pedido del usuario 2026-10-18: con
16 761 utilidades eran ~27 mil ítems de la escena). Se ven IGUAL, píxel a píxel, que un
`QGraphicsLineItem` por segmento en el mismo lugar del orden de dibujo, también al repintar solo las
franjas de la cruz del cursor."""
import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_capa_marcas import win  # noqa: E402,F401  (misma ventana con el proyecto de presentación)


def _foto(win, dpr, off, region=None):
    from PySide6 import QtGui
    vp = win.canvas.viewport()
    img = QtGui.QImage(int((vp.width() + off.x()) * dpr) + 2, int((vp.height() + off.y()) * dpr) + 2,
                       QtGui.QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(QtGui.QColor("magenta"))
    if region is None:
        vp.render(img, off)
    else:
        vp.render(img, off, region)
    return img


def _fotos(win):
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance()
    out = []
    for a in win._accesorios[:2]:
        for z in (0.3, 1.3713, 5.1377):
            win.canvas.resetTransform(); win.canvas.scale(z, z)
            win.canvas.centerOn(a["x"] + 0.37, a["y"] + 0.81)
            for _ in range(4):
                app.processEvents()
            for dpr, off in ((1.0, QtCore.QPoint(0, 0)), (1.25, QtCore.QPoint(306, 71))):
                img = _foto(win, dpr, off)
                out.append(np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()).copy())
    return out


def test_una_capa_se_ve_igual_que_un_item_por_segmento(win, monkeypatch):
    from PySide6 import QtCore, QtWidgets
    from ui.comun import capa_lineas
    win.sel_pipe = 3; win._redraw()                      # con una seleccionada (pluma de 4 px)
    _fotos(win)
    nuevo = _fotos(win)

    class UnItemPorSegmento(capa_lineas.CapaLineas):     # lo de antes, en el mismo lugar del orden
        def agregar(self, lineas, caja, pluma, clave=None):
            for linea in lineas:
                QtWidgets.QGraphicsLineItem(linea, self).setPen(pluma)

        def cerrar(self):
            pass

        def boundingRect(self):
            return QtCore.QRectF()

        def paint(self, *a):
            pass
    monkeypatch.setattr(capa_lineas, "CapaLineas", UnItemPorSegmento)
    win._redraw()
    for a, b in zip(nuevo, _fotos(win)):
        assert np.array_equal(a, b)


def test_la_cruz_no_borra_utilidades(win):
    """Repintar solo las dos franjas de la cruz (px físicos, escala 125 %) = la vista entera ahí."""
    from PySide6 import QtCore, QtGui, QtWidgets
    vp = win.canvas.viewport()
    a = win._accesorios[0]
    win.canvas.resetTransform(); win.canvas.scale(1.7, 1.7); win.canvas.centerOn(a["x"], a["y"])
    for _ in range(4):
        QtWidgets.QApplication.instance().processEvents()
    dpr, off = 1.25, QtCore.QPoint(306, 71)
    c = vp.rect().center()
    cruz = QtGui.QRegion(0, c.y() - 2, vp.width(), 5) | QtGui.QRegion(c.x() - 2, 0, 5, vp.height())
    completa, parcial = _foto(win, dpr, off), _foto(win, dpr, off, cruz)
    for r in cruz:
        for y in range(int((r.top() + off.y()) * dpr) + 2, int((r.bottom() + off.y()) * dpr) - 1):
            for x in range(int((r.left() + off.x()) * dpr) + 2, int((r.right() + off.x()) * dpr) - 1):
                assert completa.pixel(x, y) == parcial.pixel(x, y), (x, y)


def test_redibujo_reusa_los_segmentos_si_la_utilidad_no_cambia(win):
    win._redraw()
    antes = {i: v[1] for i, v in win._lineas_cache.items()}
    win.sel_pipe = 2; win._redraw()                      # elegir: la geometría no cambia
    assert all(win._lineas_cache[i][1] is lineas for i, lineas in antes.items())
    p = win.pipes[0]
    p["pts"] = [(x, y + 25.0) for x, y in p["pts"]]
    win._redraw()
    assert win._lineas_cache[0][1] is not antes[0]



def test_con_el_mismo_modelo_la_capa_se_reusa_y_se_ve_igual(win):
    """Esc, elegir o cambiar de modo con el modelo igual: la MISMA capa, solo con otra pluma en las
    utilidades que se eligen o se sueltan; se ve igual que rehecha de cero (2026-10-19)."""
    from PySide6 import QtWidgets
    win.sel_pipe = 3; win._redraw()
    capa = win._capa_lineas[1]
    for sel in (5, 3, -1, 7):
        win.sel_pipe = sel; win._redraw()
        assert win._capa_lineas[1] is capa and capa.scene() is win.canvas.scene()
        _fotos(win); reusada = _fotos(win)               # (la 2.ª vez, con las imágenes de las capas de marcas)
        win._capa_lineas = None; win._marcas = None; win._redraw()   # = todo de cero
        assert win._capa_lineas[1] is not capa
        _fotos(win)
        for a, b in zip(reusada, _fotos(win)):
            assert np.array_equal(a, b)
        capa = win._capa_lineas[1]
    win.pipes[0]["pts"] = [(x + 9.0, y) for x, y in win.pipes[0]["pts"]]
    win._redraw()                                        # el modelo cambió: se rehace
    assert win._capa_lineas[1] is not capa
    assert sum(1 for it in win._overlay if type(it).__name__ == "CapaLineas") == 1
    assert sum(1 for it in win.canvas.scene().items() if type(it).__name__ == "CapaLineas") == 1
    QtWidgets.QApplication.instance().processEvents()


def test_deshacer_revive_el_dibujo_anterior_y_se_ve_igual(win):
    """Deshacer / rehacer vuelve a un modelo ya dibujado: la MISMA capa de líneas y las MISMAS capas de
    marcas (con sus globos), y se ve igual, píxel a píxel, que dibujado de cero (2026-10-19)."""
    def globos():
        return sorted((type(it).__name__, round(it.pos().x(), 6), round(it.pos().y(), 6), it.toolTip())
                      for it in win._marcas.todas())

    def de_cero():
        win._capa_lineas = None; win._marcas = None; win._memo_redibujo = None
        win._grupos_previos = None; win._capas_lineas_previas = None
        win._redraw()

    win._redraw()
    capa, grupo = win._capa_lineas[1], win._marcas
    antes = globos()
    win._push()
    p = next(p for p in win.pipes if len(p["pts"]) >= 3)
    x, y = p["pts"][1]
    p["pts"][1] = (x + 23.0, y - 17.0)
    win._refresh_lists(); win._redraw()
    capa2, grupo2 = win._capa_lineas[1], win._marcas
    assert capa2 is not capa and grupo2 is not grupo
    despues = globos()
    win.undo()
    assert win._capa_lineas[1] is capa and win._marcas is grupo      # revividos, no rehechos
    assert globos() == antes
    _fotos(win); revivido = _fotos(win)
    de_cero()
    assert globos() == antes
    _fotos(win)
    for a, b in zip(revivido, _fotos(win)):
        assert np.array_equal(a, b)
    win.redo()
    assert globos() == despues
    _fotos(win); revivido = _fotos(win)
    de_cero()
    _fotos(win)
    for a, b in zip(revivido, _fotos(win)):
        assert np.array_equal(a, b)
    assert sum(1 for it in win.canvas.scene().items() if type(it).__name__ == "CapaLineas") == 1
