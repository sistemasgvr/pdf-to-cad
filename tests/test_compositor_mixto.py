"""Compositor ÚNICO (2026-11-09): piezas vectoriales y escaneadas en la misma hoja compuesta.

Lo que NO debe cambiar: sin piezas escaneadas, el compositor vectorial devuelve lo mismo y sigue a Capas y
al reconocimiento; el compositor de escaneos (`manual=True`) sigue igual."""
import io
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import fitz
import pytest
from PIL import Image
from PySide6 import QtCore, QtWidgets

from hoja import composite as C
from hoja import pieza_escaneo as PE
from ui.asistente import composite_dialog as CD
from ui.asistente.composite_dialog import CompositeDialog
from ui.ventana.app_window import Main


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _escaneo():
    stream = io.BytesIO()
    # un escaneo de verdad: ≥ PIXELES_ESCANEO (un icono chico no es un escaneo)
    Image.new("RGB", (1500, 1000), "white").save(stream, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_image(page.rect, stream=stream.getvalue())
    return doc


def _vectorial():
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    for k in range(90):
        page.draw_line((10, 10 + 2 * k), (290, 10 + 2 * k))
    page.insert_text((20, 190), "PLAN VIEW - WATER LINE STA 10+00", fontsize=8)
    return doc


def _fuentes(*docs):
    return [{"name": f"d{i}.pdf", "data": d.tobytes()} for i, d in enumerate(docs)]


def _visibles(dlg):
    return [not w.isHidden() for w in dlg.grupo_escaneo]


def test_deteccion_por_hoja():
    assert PE.es_escaneo(_escaneo()[0]) and not PE.es_escaneo(_vectorial()[0])
    traced = os.path.join(os.path.dirname(__file__), "fixtures", "escaneado_vectorizado.pdf")
    with fitz.open(traced) as d:
        assert PE.es_escaneo(d[0])


def test_solo_vectorial_queda_como_antes(app):
    v = _vectorial()
    dlg = CompositeDialog(None, _fuentes(v), None, {}, manual=False)
    try:
        dlg._take_area(True)
        assert len(dlg.comp.pieces) == 1 and not dlg._hay_escaneo()
        assert _visibles(dlg) == [False] * 6                 # sin regla ni transportador
        assert dlg.view.magnet_enabled
        dlg.accept()
        comp = dlg.result_tuple()[0]
        assert not comp.manual                               # sigue a Capas y al reconocimiento
    finally:
        dlg.close_docs()


def test_mezcla_vectorial_y_escaneo_sigue_al_reconocimiento(app, monkeypatch):
    v, s = _vectorial(), _escaneo()
    dlg = CompositeDialog(None, _fuentes(v, s), None, {}, manual=False)
    try:
        dlg._take_area(True)                                 # hoja vectorial
        dlg.cmb_source.setCurrentIndex(1)
        dlg._take_area(True)                                 # hoja escaneada
        assert [dlg._es_escaneo_pieza(i) for i in range(2)] == [False, True]
        assert _visibles(dlg) == [True] * 6                  # aparecen las guías del escaneo
        assert dlg.nolayers_box.isVisibleTo(dlg) and "escaneada" in dlg.lbl_nolayers.text()
        # la escaneada gira sobre su centro (como en el compositor de escaneos); la vectorial, como siempre
        size = dlg.view.page_size(dlg.comp.pieces[1])
        _w, _h, dx, dy = C.sheet_geometry(dlg.comp, dlg.view.page_size)
        fn = C.piece_map(dlg.comp.pieces[1], size, dlg.comp.target_scale())
        antes = fn(size[0] / 2, size[1] / 2)
        dlg.view.select(1)
        dlg._rotate(5.0)
        fn = C.piece_map(dlg.comp.pieces[1], size, dlg.comp.target_scale())
        assert fn(size[0] / 2, size[1] / 2) == pytest.approx(antes, abs=1e-6)
        monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda *_a: pytest.fail("con una vectorial no se pregunta"))
        dlg.accept()
        assert not dlg.result_tuple()[0].manual
    finally:
        dlg.close_docs()


@pytest.mark.parametrize("respuesta, manual", [("Dibujar a mano", True), ("Reconocer de todos modos", False)])
def test_todo_escaneado_pregunta(app, monkeypatch, respuesta, manual):
    s = _escaneo()
    dlg = CompositeDialog(None, _fuentes(s), None, {}, manual=False)
    elegido = {}

    def _exec(box):
        b = next(b for b in box.buttons() if b.text() == respuesta)
        elegido["b"] = b
        return 0
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", _exec)
    monkeypatch.setattr(QtWidgets.QMessageBox, "clickedButton", lambda box: elegido["b"])
    try:
        dlg._take_area(True)
        dlg.accept()
        comp = dlg.result_tuple()[0]
        assert comp.manual is manual and (not manual or not comp.bridges)
    finally:
        dlg.close_docs()


def test_flujo_con_mezcla_va_a_capas(monkeypatch):
    from ui.ventana import app_window
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(1, 0, [0, 0, 1, 1], x=400)])
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", lambda *a, **kw: (comp, [], {}))
    class _Capas(Exception):
        pass

    def _a_capas(*a, **kw):
        raise _Capas()
    win = SimpleNamespace(src_pdfs=[], composite=None, hidden_ocgs_by_source={}, page_idx=0,
                          _apply_composite=lambda: None, _info=lambda msg: None,
                          _firma_compuesta=lambda *a: None, _firma_hoja=lambda i: None, doc=None,
                          _layout_minimapa=_a_capas)       # lo primero que pide el paso «Capas»
    with pytest.raises(_Capas):
        Main._wizard_sheet_flow(win, 0)                      # una hoja con piezas vectoriales no se salta Capas
    assert not getattr(win, "_dirty", False)


def test_panel_hoja_un_solo_componer(qtbot=None):
    from ui.ventana import ventana_panel_hoja as VPH
    src = open(VPH.__file__, encoding="utf-8").read()
    assert '("file-image-outline", "Componer PDF imagen/escaneo…"' not in src


_MUCHOS = r'''
import os, sys, faulthandler
faulthandler.enable()
os.environ["QT_QPA_PLATFORM"] = "offscreen"
for k in ("PDFCAD_SUGERENCIA", "PDFCAD_AREA_SUGERIDA", "PDFCAD_PROCESO"):
    os.environ.setdefault(k, "0")
sys.path[:0] = [sys.argv[1], sys.argv[2]]
import fitz
from PySide6 import QtWidgets
app = QtWidgets.QApplication([])
from ui.asistente.composite_dialog import CompositeDialog
doc = fitz.open(); doc.new_page(width=300, height=200).draw_line((10, 10), (200, 100))
data = doc.tobytes()
for i in range(30):
    dlg = CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, manual=bool(i % 2))
    dlg.close_docs()
print("ok")
'''


def test_muchos_componer_hoja_seguidos_no_cierran_el_programa(tmp_path):
    """Regresión (2026-11-09): mover los botones de «Área a tomar» a su pastilla flotante sin quitarlos antes de
    su fila dañaba la memoria y, cada ~8 diálogos, el programa se cerraba (access violation en `QMenu.addAction`).
    En un proceso aparte: un cierre no debe tumbar a pytest."""
    import subprocess
    import sys
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    guion = tmp_path / "muchos.py"
    guion.write_text(_MUCHOS, encoding="utf-8")
    r = subprocess.run([sys.executable, str(guion), os.path.join(raiz, "app"), raiz], capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-2000:]
