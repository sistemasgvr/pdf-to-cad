"""La vista previa muestra los quiebres como la CURVA que entrará al importar (pedido del
usuario 2026-10-19, DU06 UD-202: la «—SC—» gira 14° en el hueco de su rótulo y la vista
previa pintaba un punto de quiebre; la regla —no presión: todo quiebre es curva, aunque sea
mínima— ya la aplicaba la importación, `nucleo/quiebres_curvas`)."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from nucleo import model_ops  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from reconocimiento import recognition_quiebres as RQ  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
needs_du06 = pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")

Z = 3.5                 # zoom del editor (px por pt)
ESCALA = 20.0 / 72.0    # 1" = 20'


def _resultado(utility, kinds=("end", "corner", "end"), pts=((0.0, 0.0), (700.0, 0.0), (1400.0, 400.0))):
    kind = rec.utility_line_kind(utility)
    pl = rec.RecognizedPolyline("C-XXXX-UNGD-E", utility, [tuple(p) for p in pts], kind, list(kinds))
    return rec.RecognitionResult(utility, 0, ESCALA, polylines=[pl])


def test_quiebre_de_conduit_es_curva_minima():
    res = _resultado("ELECTRICO")
    got = RQ.curvas_de_quiebres([res], Z)
    curvas = got[id(res)]
    assert list(curvas) == [(700.0, 0.0)]
    g = curvas[(700.0, 0.0)]
    # radio mínimo de la regla: 6 × diámetro (el de la importación), en px del lienzo
    p = rec.pipes_from_recognition(res, layer="ELECTRICO", zoom=Z)[0]
    assert g["r_px"] == pytest.approx(model_ops.radio_auto_ft(p) / (ESCALA / Z), rel=1e-6)
    assert g["quiebre"] and not g["loose"]
    # tangencias sobre las dos rectas, a la misma distancia de la esquina
    assert g["a"][1] == pytest.approx(0.0, abs=1e-9) and g["a"][0] < 700.0
    d2 = (g["b"][0] - 700.0, g["b"][1])
    assert abs(d2[0] * 400.0 - d2[1] * 700.0) < 1e-6 * 700
    assert math.dist(g["a"], (700.0, 0.0)) == pytest.approx(math.hypot(*d2), rel=1e-9)


@pytest.mark.parametrize("utility", ["AGUA", "GAS"])
def test_en_presion_el_quiebre_queda(utility):
    res = _resultado(utility)
    assert RQ.curvas_de_quiebres([res], Z) == {}


def test_codo_reconocido_y_quiebre_casi_recto_no_cambian():
    # casi recto (≤ 2°): el plugin lo endereza, no es curva
    res = _resultado("TELECOM", pts=((0.0, 0.0), (700.0, 0.0), (1400.0, 20.0)))
    assert RQ.curvas_de_quiebres([res], Z) == {}
    # el codo que ya trae el reconocimiento se dibuja como siempre
    res = _resultado("TELECOM")
    f = {"a": (650.0, 0.0), "b": (740.0, 23.0), "center": (650.0, 300.0), "r_px": 300.0}
    res.polylines[0].fillets = {1: f}
    res.polylines[0].kinds[1] = "fillet"
    assert RQ.codos_de(res.polylines[0], RQ.curvas_de_quiebres([res], Z).get(id(res), {})) == {1: f}


def test_codos_de_junta_los_del_reconocimiento_y_los_de_los_quiebres():
    res = _resultado("DRENAJE")
    curvas = RQ.curvas_de_quiebres([res], Z)[id(res)]
    assert set(RQ.codos_de(res.polylines[0], curvas)) == {1}
    assert RQ.codos_de(res.polylines[0], {}) == {}


def test_la_vista_previa_dibuja_la_curva_y_no_la_esquina():
    from PySide6 import QtGui, QtWidgets
    from ui.asistente import recognition_dialog as rd
    from ui.asistente.recognition_preview_draw import _display_runs
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    img = QtGui.QImage(1500, 500, QtGui.QImage.Format_RGB888)
    img.fill(QtGui.QColor("white"))
    res = _resultado("ELECTRICO")
    dlg = rd.RecognitionPreviewDialog(None, img, [res], fondo={"escala": 1.0, "tam": (1500, 500), "zoom": Z,
                                                               "pagina": lambda: None})
    try:
        curvas = dlg._curvas_quiebres().get(id(res), {})
        fil = RQ.codos_de(res.polylines[0], curvas)
        runs = _display_runs(res.polylines[0], fil)
        # la recta llega hasta la tangencia y sigue desde la otra: la esquina no se dibuja
        assert len(runs) == 2 and (700.0, 0.0) not in runs[0] + runs[1]
        # sin el zoom del editor (sin `fondo`) no se simula nada: se ve como antes
        dlg2 = rd.RecognitionPreviewDialog(None, img, [res])
        assert dlg2._curvas_quiebres() == {}
        dlg2.close()
    finally:
        dlg.close()


@needs_du06
def test_du06_h4_la_esquina_bajo_la_sc_entra_como_curva():
    import fitz
    with fitz.open(str(DU06)) as doc:
        res = rec.recognize_page(None, 3, utility="TELECOM", zoom=Z, doc=doc)
    curvas = RQ.curvas_de_quiebres([res], Z).get(id(res), {})
    sc = (1307.2 * Z, 1033.4 * Z)            # la «—SC—» del banco de ductos gira 14° en su rótulo
    near = [g for q, g in curvas.items() if math.dist(q, sc) <= 0.5 * Z]
    assert len(near) == 1
    assert near[0]["r_px"] / Z * ESCALA == pytest.approx(6.0, abs=0.01)     # 6 × 12" (radio mínimo)
