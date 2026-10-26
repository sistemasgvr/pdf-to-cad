"""Marcas del lienzo por TANDAS en planos gigantes (pedido del usuario 2026-10-26: «cuando el plano es
gigante y se intentan cargar todos los avisos de golpe, se lajea el programa»).

Con `UMBRAL` marcas o más, los dibujantes (cruces, alertas, C-n, etiquetas de accesorios, insignias de
avisos) se recorren por tandas (`ui.comun.marcas_por_tandas`). Aquí el umbral se baja para usar un
plano chico: al terminar, cada capa tiene las MISMAS marcas en el MISMO orden, con los mismos globos y
se ve igual que cargadas de golpe; si el modelo cambia a medias, la carga se cancela.
"""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from test_rendimiento_plano import _azar, _cargar, _estrellas, win  # noqa: E402,F401  (fixture)


def _capas(w):
    """[(z, [(tipo, x, y, globo, visible)…])] de cada capa de marcas, en su orden."""
    out = []
    for z, capa in sorted(w._marcas.capas.items()):
        out.append((z, [(type(m).__name__, round(m.pos().x(), 6), round(m.pos().y(), 6), m.toolTip(),
                         m.isVisible()) for m in capa.marcas]))
    return out


def _imagen(w):
    """La escena entera dibujada como la ve la vista (las marcas se pintan a tamaño fijo en pantalla)."""
    sc = w.canvas.scene()
    img = QtGui.QImage(1200, 800, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(255, 255, 255))
    p = QtGui.QPainter(img)
    sc.render(p, QtCore.QRectF(img.rect()), sc.sceneRect())
    p.end()
    return np.frombuffer(img.constBits(), np.uint8).reshape(800, img.bytesPerLine()).copy()


def _esperar(w, seg=30.0):
    import time
    app = QtWidgets.QApplication.instance()
    fin = time.time() + seg
    while getattr(w, "_tandas", None) is not None and time.time() < fin:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
    return getattr(w, "_tandas", None) is None


def _de_nuevo(w):
    """Otro redibujo que arma las marcas desde cero (como al llegar los resultados del cálculo)."""
    w._marcas.firma = None
    w._memo_redibujo = None
    w._redraw()


def _plano(w):
    tol = 0.5 / w.scale * w.zoom
    _cargar(w, _azar(3, 90) + _estrellas(4, tol)[:120])


def test_por_tandas_queda_igual_que_de_golpe(win, monkeypatch):
    from ui.comun import marcas_por_tandas as MT
    _plano(win)
    win._redraw()
    assert win._tandas is None                          # pocas marcas: de golpe, como siempre
    de_golpe, img_golpe = _capas(win), _imagen(win)
    assert sum(len(m) for _z, m in de_golpe) > 100
    monkeypatch.setattr(MT, "UMBRAL", 1)
    _de_nuevo(win)
    t = win._tandas
    assert t is not None and not t.terminada and win._marcas.cargando
    assert all(not c.isVisible() for c in win._marcas.capas.values())   # aparecen todas juntas al final
    assert _esperar(win) and t.terminada and win._marcas.firma is not None
    assert all(c.isVisible() for c in win._marcas.capas.values())
    assert _capas(win) == de_golpe
    assert np.array_equal(_imagen(win), img_golpe)
    win._marcas.cargar(True)                            # (la imagen sí lleva las marcas)
    assert not np.array_equal(_imagen(win), img_golpe)
    win._marcas.cargar(False)


def test_cambiar_el_modelo_cancela_la_carga(win, monkeypatch):
    from ui.comun import marcas_por_tandas as MT
    _plano(win)
    win._redraw()
    monkeypatch.setattr(MT, "UMBRAL", 1)
    monkeypatch.setattr(MT, "TANDA_MS", 0)              # una tanda mínima por vuelta: queda a medias
    _de_nuevo(win)
    vieja, grupo_viejo = win._tandas, win._marcas
    QtWidgets.QApplication.instance().processEvents()
    assert not vieja.terminada
    win.pipes.append(dict(layer="AGUA", pts=[(50.0, 50.0), (1900.0, 1400.0)], inv_start=-6.0, inv_end=-6.0,
                          diam=8.0))
    win._redraw()                                       # otro modelo: la carga a medias no sirve
    assert vieja.terminada and grupo_viejo.firma is None and win._marcas is not grupo_viejo
    monkeypatch.setattr(MT, "TANDA_MS", 30)
    assert _esperar(win)
    final = _capas(win)
    monkeypatch.setattr(MT, "UMBRAL", 10 ** 9)
    _de_nuevo(win)
    assert _capas(win) == final                         # = cargarlo todo de golpe


def test_mismo_modelo_sigue_cargando_y_marcas_al_dia(win, monkeypatch):
    from ui.comun import marcas_por_tandas as MT
    _plano(win)
    win._redraw()
    de_golpe = _capas(win)
    monkeypatch.setattr(MT, "UMBRAL", 1)
    monkeypatch.setattr(MT, "TANDA_MS", 0)
    _de_nuevo(win)
    t, grupo = win._tandas, win._marcas
    win._redraw()                                       # elegir / Esc: mismo modelo, misma carga
    assert win._tandas is t and win._marcas is grupo and not t.terminada
    win._marcas_al_dia()                                # (capturas del informe: todas ya)
    assert t.terminada and win._tandas is None
    assert _capas(win) == de_golpe
