"""Hojas ENCIMADAS en «Componer hoja» (reporte 2026-11-13, cliente en fase beta): sin composición
sugerida el usuario tomó las hojas una por una sin ordenarlas y quedaron una encima de otra; al
reconocer, la leyenda de una tapaba a la otra. Ahora se avisa antes de continuar."""
from hoja import composite_checks as CK
from tests.test_composite_dialog import _two_sheet_pdf, app, composite_dialog, C, QtWidgets  # noqa: F401


def test_encimadas_solo_cuando_comparten_buena_parte():
    borde = [(0, 0, 300, 200), (300, 0, 600, 200)]                     # borde con borde
    costura = [(0, 0, 300, 200), (290, 0, 590, 200)]                   # solape angosto (fundir bordes)
    encima = [(0, 0, 300, 200), (60, 20, 360, 220), (900, 0, 1200, 200)]
    assert CK.encimadas(borde) == [] and CK.encimadas(costura) == []
    (par,) = CK.encimadas(encima)
    assert par[:2] == (0, 1) and 0.6 < par[2] < 0.75


def _dialogo(piezas):
    comp = C.Composite([C.Piece(0, h, [0, 0, 1, 1], x=x, y=y) for h, x, y in piezas], bridges=False)
    return composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": _two_sheet_pdf()}], comp, {}, 0)


def _responder(monkeypatch, texto_boton, vistos):
    def exec_(box):
        vistos.append(box.text())
        box_b = next(b for b in box.buttons() if b.text() == texto_boton)
        box_b.click()
        return 0
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", exec_)


def test_continuar_con_hojas_encimadas_pregunta(app, monkeypatch):
    dlg = _dialogo([(0, 0, 0), (1, 40, 20)])
    try:
        vistos = []
        _responder(monkeypatch, "Volver a acomodarlas", vistos)
        assert dlg._revisar_encimadas() == "back" and len(vistos) == 1
        _responder(monkeypatch, "Continuar así", vistos)
        assert dlg._revisar_encimadas() == "ok"
    finally:
        dlg.close_docs()


def test_hojas_borde_con_borde_no_preguntan(app, monkeypatch):
    dlg = _dialogo([(0, 0, 0), (1, 300, 0)])
    try:
        vistos = []
        _responder(monkeypatch, "Continuar así", vistos)
        assert dlg._revisar_encimadas() == "ok" and vistos == []
    finally:
        dlg.close_docs()


def test_compilar_exige_el_mismo_entorno_que_desarrollo():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import verificar_entorno_build as V
    py, paq = V.leer()
    assert py and paq.get("pymupdf") and paq.get("numpy") and paq.get("PySide6")
    # el .exe del cliente: Python 3.11.9 y otras bibliotecas → no se compila
    probs = V.revisar("3.14", {"numpy": "2.5.3", "pymupdf": "1.28.2", "shapely": "2.1.2"}, "3.11.9",
                      lambda n: {"numpy": "1.26.4", "pymupdf": "1.28.2"}.get(n))
    assert len(probs) == 3 and probs[0].startswith("Python 3.11.9")
    assert V.revisar("3.14", {"numpy": "2.5.3"}, "3.14.7", lambda n: "2.5.3") == []
