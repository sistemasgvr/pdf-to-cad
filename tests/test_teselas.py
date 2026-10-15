"""La hoja nítida al acercarse, en TESELAS dibujadas en otro proceso (`ui.comun.teselas*`).

Reporte del usuario (2026-10-15): con la hoja compuesta de 36 mapas (o su reconocimiento) la
ventana se trababa cada vez que el zoom se detenía: el recorte nítido se dibujaba en el hilo de
la interfaz (0.3–1.3 s; la primera vez ~7 s) y PyMuPDF no suelta el GIL. Ahora la hoja se parte
en teselas por nivel de zoom, se dibujan en procesos aparte y se guardan en caché. Estas pruebas
cuidan que las teselas sean los MISMOS píxeles de MuPDF, que caigan exactas sobre la hoja, que
mientras falta una se vea la de otro nivel y que el proceso real funcione (PDF por ruta, por
bytes y con capas apagadas).
"""
import math
import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from ui.comun import fondo_pdf, recorte_nitido as R, teselas as T  # noqa: E402
from ui.comun import teselas_servidor as TS  # noqa: E402


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _pdf(w=900, h=700, ocg=False):
    doc = fitz.open()
    pg = doc.new_page(width=w, height=h)
    oc = doc.add_ocg("RED", on=True) if ocg else 0
    for i in range(12):
        pg.draw_line((20 + 70.3 * i, 15), (35 + 70.3 * i, h - 15), width=0.35, oc=oc)
        pg.draw_line((15, 20 + 55.7 * i), (w - 15, 30 + 55.7 * i), width=0.6)
    pg.draw_circle((w / 2, h / 2), 33.3, width=0.8, oc=oc)
    pg.insert_text((60, 80), "TESELAS 1234", fontsize=9)
    return fitz.open("pdf", doc.tobytes())


def _type3(n=300):
    from test_nitidez_zoom import _pdf_type3
    return _pdf_type3(n=n)


def _igual(pix, ref):
    return ((pix.x, pix.y, pix.width, pix.height) == (ref.x, ref.y, ref.width, ref.height)
            and pix.samples == ref.samples)


# ── cálculo (sin Qt) ─────────────────────────────────────────────────────────
def test_nivel_nunca_agranda_la_tesela_y_a_lo_sumo_raiz_de_dos():
    for ppp in np.exp(np.linspace(math.log(0.07), math.log(60), 300)):
        n = T.nivel_para(ppp)
        s = T.escala_nivel(n)
        assert s >= ppp * (1 - 1e-9) and (n == T.NIVEL_MIN or T.escala_nivel(n - 1) < ppp)
        assert s < ppp * math.sqrt(2) * (1 + 1e-9) or n == T.NIVEL_MIN
    assert T.escala_nivel(T.NIVEL_MAX) == R.MAX_ESCALA and T.nivel_para(1e6) == T.NIVEL_MAX
    assert T.escala_nivel(0) == 1.0 and T.escala_nivel(1) == pytest.approx(math.sqrt(2))
    # a 1:1 (o alejada) basta la imagen base; un paso de rueda (×1.25) ya pide teselas
    assert not T.hace_falta(3.5, 3.5) and not T.hace_falta(2.0, 3.5) and T.hace_falta(3.5 * 1.25, 3.5)


def test_teselas_del_centro_primero_y_el_anillo_al_final():
    lst = T.teselas_en((1000, 800, 1400, 1000), 4, 5000, 4000, margen=1)
    vis = [e for e in lst if e[3]]
    anillo = [e for e in lst if not e[3]]
    assert vis and anillo and lst[:len(vis)] == vis
    assert [e[0] for e in vis] == sorted(e[0] for e in vis)
    lado = T.TAM / T.escala_nivel(4)
    cx, cy = 1200, 900
    assert vis[0][1] == int(cx // lado) and vis[0][2] == int(cy // lado)
    # nunca fuera de la hoja
    assert all(T.rect_tesela(4, tx, ty, 5000, 4000) is not None for _d, tx, ty, _v in lst)
    assert T.teselas_en((6000, 0, 7000, 10), 4, 5000, 4000) == []


def test_otro_nivel_cubre_el_cuadro():
    w, h = 3000.0, 2000.0
    for nivel in (2, 3, 6):
        for tx, ty in ((0, 0), (3, 2), (5, 1)):
            r = T.rect_tesela(nivel, tx, ty, w, h)
            if r is None:
                continue
            for otro in (nivel - 2, nivel - 1, nivel + 1):
                cajas = [T.rect_tesela(otro, x, y, w, h) for x, y in T.de_otro_nivel(nivel, tx, ty, otro, w, h)]
                assert cajas and all(c is not None for c in cajas)
                # juntas cubren el cuadro entero y cada una lo toca
                assert min(c[0] for c in cajas) <= r[0] + 1e-9 and max(c[2] for c in cajas) >= r[2] - 1e-9
                assert min(c[1] for c in cajas) <= r[1] + 1e-9 and max(c[3] for c in cajas) >= r[3] - 1e-9
                assert all(c[0] < r[2] and c[2] > r[0] and c[1] < r[3] and c[3] > r[1] for c in cajas)


@pytest.mark.parametrize("nivel", [-1, 0, 3, 4, 7])
def test_tesela_mismos_pixeles_que_mupdf_y_vecinas_exactas(nivel):
    doc = _pdf()
    page = doc[0]
    hojas = R.Hojas()
    s = T.escala_nivel(nivel)
    lado = T.TAM / s
    nx = math.ceil(page.rect.width / lado)
    ty = 0
    prev = None
    for tx in range(min(nx, 3)):
        pix = T.dibujar(hojas, page, nivel, tx, ty)
        r = T.rect_tesela(nivel, tx, ty, page.rect.width, page.rect.height)
        ref = page.get_pixmap(matrix=fitz.Matrix(s, s), clip=fitz.Rect(*r), alpha=False)
        assert _igual(pix, ref)
        assert abs(pix.x - tx * T.TAM) <= 1                   # en la rejilla de la hoja
        if prev is not None:
            assert prev.x + prev.width >= pix.x                # vecinas: sin hueco
        prev = pix


@pytest.mark.parametrize("rotate", [0, 90])
def test_tesela_type3_mismos_pixeles(rotate):
    from test_nitidez_zoom import _pdf_type3
    page = _pdf_type3(rotate)[0]
    hojas = R.Hojas()
    assert hojas.cajas(page) is not None                       # va por el recorte sin letras de fuera
    for nivel in (3, 6, 9):
        s = T.escala_nivel(nivel)
        for tx, ty in ((0, 0), (1, 1)):
            r = T.rect_tesela(nivel, tx, ty, page.rect.width, page.rect.height)
            if r is None:
                continue
            ref = page.get_pixmap(matrix=fitz.Matrix(s, s), clip=fitz.Rect(*r), alpha=False)
            assert _igual(T.dibujar(hojas, page, nivel, tx, ty), ref), (nivel, tx, ty)


# ── en la vista (Qt, dibujando aquí mismo: PDFCAD_PROCESO=0) ─────────────────
def _escena_con_fondo(page, zoom=3.0):
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    item = fondo_pdf.nuevo_item(QtGui.QPixmap.fromImage(fondo_pdf.qimage(pix)), 1.0)
    sc = QtWidgets.QGraphicsScene()
    sc.addItem(item)
    return sc, item


def _render(scene, src: QtCore.QRectF, w: int, h: int) -> np.ndarray:
    img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB888)
    img.fill(QtGui.QColor("white"))
    p = QtGui.QPainter(img)
    scene.render(p, QtCore.QRectF(0, 0, w, h), src)
    p.end()
    return np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[:, :w * 3].copy()


def test_en_pantalla_son_los_pixeles_de_mupdf(app):
    """A 1:1 con la tesela, lo que se pinta es EXACTAMENTE cada tesela de MuPDF en su lugar
    (vecinas sin costura ni corrimiento). Ojo: MuPDF suaviza los bordes distinto según el
    recorte que se le pide (hasta 20/255 en ~1 % de los píxeles de una línea), así que la
    referencia es la de cada tesela, no un recorte grande."""
    doc = _pdf()
    page = doc[0]
    zoom = 3.0
    sc, item = _escena_con_fondo(page, zoom)
    sup = item.superficie
    sup.fijar(page, k=zoom, base=zoom)
    nivel = 7
    s = T.escala_nivel(nivel)                                   # 11.31 px/pt
    rect = (300.0, 200.0, 300.0 + 1500 / s, 200.0 + 1500 / s)  # varias teselas
    sup.pedir_region(rect, s * 0.99)
    assert sup.nivel == nivel and len(sup.listas()) >= 4
    x0, y0 = math.floor(rect[0] * s), math.floor(rect[1] * s)
    w, h = 1400, 1400
    src = QtCore.QRectF(x0 / s * zoom, y0 / s * zoom, w / s * zoom, h / s * zoom)
    got = _render(sc, src, w, h).reshape(h, w, 3)
    want = np.full((h, w, 3), -1, int)
    W, H = page.rect.width, page.rect.height
    r = T.rango((x0 / s, y0 / s, (x0 + w) / s, (y0 + h) / s), nivel, W, H)
    for ty in range(r[1], r[3] + 1):
        for tx in range(r[0], r[2] + 1):
            ref = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False,
                                  clip=fitz.Rect(*T.rect_tesela(nivel, tx, ty, W, H)))
            a = np.frombuffer(ref.samples, np.uint8).reshape(ref.height, ref.stride)[:, :ref.width * 3]
            a = a.reshape(ref.height, ref.width, 3)
            ax0, ay0 = ref.x - x0, ref.y - y0
            bx0, by0 = max(0, ax0), max(0, ay0)
            bx1, by1 = min(w, ax0 + ref.width), min(h, ay0 + ref.height)
            want[by0:by1, bx0:bx1] = a[by0 - ay0:by1 - ay0, bx0 - ax0:bx1 - ax0]
    assert (want >= 0).all()                                     # las teselas cubren la vista
    assert np.array_equal(got, want)


def test_mientras_falta_se_ve_la_de_otro_nivel(app, monkeypatch):
    doc = _pdf()
    page = doc[0]
    sc, item = _escena_con_fondo(page)
    sup = item.superficie
    sup.fijar(page, k=3.0, base=3.0)
    rect = (200.0, 150.0, 330.0, 230.0)
    sup.pedir_region(rect, T.escala_nivel(6))                   # nivel 6 en la caché
    assert sup.nivel == 6 and sup.listas()
    srv = TS.servidor()
    monkeypatch.setattr(srv, "_dibujar_aqui", lambda *a: None)  # el siguiente nivel no llega
    sup.pedir_region(rect, T.escala_nivel(7))
    assert sup.nivel == 7 and not sup.listas()
    img = QtGui.QImage(400, 300, QtGui.QImage.Format_RGB888)
    p = QtGui.QPainter(img)
    p.scale(T.escala_nivel(7) / 3.0, T.escala_nivel(7) / 3.0)
    p.translate(-rect[0] * 3.0, -rect[1] * 3.0)
    dibujos, cubierto = sup._plan(p)
    p.end()
    assert dibujos and all(t.nivel == 6 for t, _c in dibujos) and cubierto
    assert all(c is not None for _t, c in dibujos)              # recortadas al cuadro de la nueva
    # y de vuelta al 6: están todas, sin pedir nada
    sup.pedir_region(rect, T.escala_nivel(6))
    assert sup.listas()


def test_opacidad_la_imagen_no_se_suma_bajo_la_tesela(app):
    """Con el PDF al 50 %, donde hay tesela no se pinta también la imagen de la hoja: la
    tinta no queda más oscura que con la imagen sola."""
    doc = _pdf()
    page = doc[0]
    zoom = 3.0
    sc, item = _escena_con_fondo(page, zoom)
    item.setOpacity(0.5)
    src = QtCore.QRectF(250 * zoom, 120 * zoom, 30 * zoom, 30 * zoom)
    solo = _render(sc, src, 90, 90)                              # a 1:1 con la imagen: sin teselas
    sup = item.superficie
    sup.fijar(page, k=zoom, base=zoom)
    sup.pedir_region((240, 110, 290, 160), 12.0)
    assert sup.listas()
    con = _render(sc, src, 90, 90)
    assert con.min() >= solo.min() - 8                          # nunca la tinta doble
    assert con.min() >= 100                                      # 50 %: lo más oscuro es gris


def test_capas_apagadas_otras_teselas(app):
    doc = _pdf(ocg=True)
    page = doc[0]
    sc, item = _escena_con_fondo(page)
    sup = item.superficie
    sup.fijar(page, k=3.0, base=3.0)
    sup.pedir_region((400, 300, 500, 400), 10.0)
    antes = {c: t for c, t in sup.listas()}
    assert antes
    doc.set_layer_ui_config(0, 2)                                # apagar la capa
    sup.invalidar()
    sup.pedir_region((400, 300, 500, 400), 10.0)
    despues = {c: t for c, t in sup.listas()}
    assert despues and not set(antes) & set(despues)             # otra firma: otras claves
    a = next(iter(antes.values())).pm.toImage()
    b = next(iter(despues.values())).pm.toImage()
    assert a != b


# ── el proceso real ─────────────────────────────────────────────────────────
def _esperar(app, cond, seg=40.0):
    fin = time.time() + seg
    while time.time() < fin:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.mark.parametrize("por_ruta", [True, False])
def test_proceso_dibuja_las_mismas_teselas_sin_trabar(app, tmp_path, monkeypatch, por_ruta):
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    monkeypatch.setattr(TS, "cuantos", lambda: 2)
    srv = TS.servidor()
    assert not srv.local
    try:
        if por_ruta:
            ruta = tmp_path / "plano.pdf"
            _pdf(ocg=True).save(str(ruta))
            doc = fitz.open(str(ruta))
        else:
            doc = fitz.open(stream=_pdf(ocg=True).tobytes(), filetype="pdf")
        doc.set_layer_ui_config(0, 2)                            # capa apagada: el proceso la apaga igual
        page = doc[0]
        sc, item = _escena_con_fondo(page)
        sup = item.superficie
        sup.fijar(page, k=3.0, base=3.0)
        t0 = time.perf_counter()
        sup.pedir_region((100, 100, 500, 400), 9.0)
        assert time.perf_counter() - t0 < 0.5                    # pedir no espera al dibujo
        quiero = [c for _p, c, v in srv._duenos[id(sup)][2] if v]
        assert len(quiero) >= 2
        assert _esperar(app, lambda: all(c in srv._cache for c in quiero))
        s = T.escala_nivel(sup.nivel)
        for c, t in sup.listas():
            r = T.rect_tesela(c[3], c[4], c[5], page.rect.width, page.rect.height)
            ref = page.get_pixmap(matrix=fitz.Matrix(s, s), clip=fitz.Rect(*r), alpha=False)
            img = t.pm.toImage().convertToFormat(QtGui.QImage.Format_RGB888)
            got = np.frombuffer(img.constBits(), np.uint8).reshape(t.h, img.bytesPerLine())[:, :t.w * 3]
            want = np.frombuffer(ref.samples, np.uint8).reshape(ref.height, ref.stride)[:, :ref.width * 3]
            assert (t.x, t.y, t.w, t.h) == (ref.x, ref.y, ref.width, ref.height)
            assert np.array_equal(got, want)
        doc.close()
    finally:
        srv.parar()
