"""Rótulos del plano con su guía (MLeader) y MText (pedido del usuario 2026-11-03): el reconocimiento los lee
(`recognition_anotaciones`), el proyecto los guarda (`project_io`, deshacer), el DXF los exporta como MULTILEADER /
MTEXT con XDATA (`exportar/dxf_anotaciones`) y la IA lee los ilegibles (`ia/anotaciones_ia`)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from nucleo import anotaciones as AN  # noqa: E402
from reconocimiento import recognition_anotaciones as RA  # noqa: E402
from reconocimiento import recognition_grosor_guias as GG  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


def _lineas(*filas):
    """[(texto, bbox, tamaño, dirección)] horizontales, una debajo de otra a paso constante."""
    out = []
    for k, (t, x, y) in enumerate(filas):
        out.append((t, (x, y, x + 6.0 * len(t), y + 8.0), 8.0, (1.0, 0.0)))
    return out


def test_mleader_con_raya_y_flecha():
    lin = _lineas(("LAT CB-208", 100.0, 100.0), ('18" RCP SD', 100.0, 110.0))
    # raya bajo el texto, guía en diagonal, flecha rellena en la punta
    tramos = [((100.0, 119.5), (170.0, 119.5)), ((100.0, 119.5), (60.0, 170.0))]
    flecha = [[(60.0, 170.0), (63.0, 163.0), (67.0, 166.0)]]
    out = RA.leer(lin, GG.Guias(tramos, flecha, 1.0), 1.0)
    assert len(out) == 1
    a = out[0]
    assert a["tipo"] == "multileader" and a["texto"] == 'LAT CB-208\n18" RCP SD'
    assert a["diam_in"] == 18.0 and a["utilidad"] == "DRENAJE" and a["estado"] == "leido"
    assert len(a["puntas"]) == 1 and abs(a["puntas"][0][0] - 60.0) < 4 and abs(a["puntas"][0][1] - 170.0) < 4


def test_texto_sin_guia_no_es_multileader_salvo_que_se_pida():
    lin = _lineas(("NOTA GENERAL", 400.0, 400.0))
    assert RA.leer(lin, GG.Guias([], [], 1.0), 1.0) == []
    out = RA.leer(lin, GG.Guias([], [], 1.0), 1.0, con_mtext=True)
    assert out and out[0]["tipo"] == "mtext"


def test_raya_con_flecha_sin_texto_es_ilegible():
    tramos = [((300.0, 300.0), (360.0, 300.0)), ((300.0, 300.0), (260.0, 350.0))]
    flecha = [[(260.0, 350.0), (263.0, 343.0), (267.0, 346.0)]]
    out = RA.leer([], GG.Guias(tramos, flecha, 1.0), 1.0)
    assert len(out) == 1 and out[0]["estado"] == "ilegible" and out[0]["texto"] == ""
    assert out[0]["caja"][1] < 300.0 < out[0]["caja"][3] + 1          # la zona del texto, sobre la raya


def test_juntar_senala_y_releer():
    a = dict(tipo="multileader", texto='8" VCP SS', caja=[0, 0, 40, 8], puntas=[(50.0, 52.0)], guias=[[(0, 8), (50, 52)]],
             estado="leido", fuente="pdf")
    b = dict(a, texto="", estado="ilegible", caja=[100, 100, 140, 108])
    lista = AN.juntar([], [a, b])
    assert len(AN.juntar(lista, [dict(a), dict(b)])) == 2            # sin repetir
    pipes = [{"pts": [(0.0, 50.0), (200.0, 50.0)]}, {"pts": [(0.0, 300.0), (200.0, 300.0)]}]
    assert AN.senala(a, pipes) == 0
    leida = AN.releer(b, '12" DIP\nWATER', "ia", "alta")
    assert leida["estado"] == "leido" and leida["diam_in"] == 12.0 and leida["utilidad"] == "AGUA"
    assert AN.ilegibles([a, b]) == [1] and AN.resumen([a, leida])["ia"] == 1


def test_guardar_y_abrir_el_proyecto():
    import project_io
    a = dict(tipo="multileader", texto="X", caja=[0, 0, 1, 1], guias=[[(0, 0), (5, 5)]], puntas=[(5, 5)])
    modelo = json.loads(json.dumps({"tf": dict(scale=1, zoom=1, rot=0, W=1, H=1, derot=[1, 0, 0, 1, 0, 0]),
                                    "anotaciones": [a]}))
    got = project_io.parse_model(modelo)["anotaciones"]
    assert got[0]["puntas"] == [(5, 5)] and got[0]["guias"] == [[(0, 0), (5, 5)]]
    assert project_io.parse_model({"tf": modelo["tf"]})["anotaciones"] == []      # proyecto viejo


def test_dxf_exporta_multileader_y_mtext_con_xdata(tmp_path):
    import ezdxf
    from exportar import dxf_anotaciones

    class Win:
        pipes = [{"pts": [(0.0, 50.0), (200.0, 50.0)]}]
        anotaciones = [dict(tipo="multileader", texto='EX 8" VCP\nSEWER', caja=[10, 10, 60, 28], tam=8.0,
                            angulo=0.0, guias=[[(10, 28), (60, 28), (40, 50)]], puntas=[(40.0, 50.0)],
                            estado="leido", utilidad="ALCANTARILLADO", diam_in=8.0, material="VCP", fuente="pdf"),
                       dict(tipo="mtext", texto='12" DIP', caja=[100, 100, 130, 106], tam=6.0, angulo=90.0,
                            guias=[], puntas=[], estado="leido", utilidad="", diam_in=12.0, material="DIP",
                            fuente="pdf")]

        def _to_cad(self, x, y):
            return (x * 0.5, -y * 0.5)
    doc = ezdxf.new("R2018")
    assert dxf_anotaciones.exportar(Win(), doc, doc.modelspace()) == 2
    ruta = tmp_path / "a.dxf"
    doc.saveas(ruta)
    msp = ezdxf.readfile(ruta).modelspace()
    ml = msp.query("MULTILEADER")[0]
    xd = [v for _c, v in ml.get_xdata("PDFCAD")]
    assert ml.dxf.layer == dxf_anotaciones.CAPA and "SEWER" in ml.get_mtext_content()
    assert "PDFCAD_ANOT" in xd and "DIAMETER=8" in xd and "PIPE_IDX=0" in xd
    mt = msp.query("MTEXT")[0]
    assert "TIPO=mtext" in [v for _c, v in mt.get_xdata("PDFCAD")] and abs(mt.dxf.rotation - 90.0) < 0.5


def test_ia_lee_el_ilegible():
    from ia import anotaciones_ia as AI
    from ia import proveedor as PV
    from tests.ollama_falso import OllamaFalso
    resp = json.dumps({"texto": 'EX 8" VCP\\nSEWER', "confianza": "alta", "nota": "se lee bien"})
    with OllamaFalso(lambda c: resp, capacidades=("completion", "vision")) as f:
        prov = PV.crear({"proveedor": "ollama", "url": f.url, "modelo": "qwen3-vl:8b"})
        r = AI.leer(prov, "QUJD")
        assert r["texto"] == 'EX 8" VCP\nSEWER' and f.pedidos[-1]["messages"][-1]["images"] == ["QUJD"]
    with OllamaFalso(lambda c: json.dumps({"texto": "algo", "confianza": "baja"}),
                     capacidades=("completion", "vision")) as f:
        prov = PV.crear({"proveedor": "ollama", "url": f.url, "modelo": "qwen3-vl:8b"})
        assert AI.leer(prov, "QUJD")["texto"] is None                  # baja confianza: no se usa
    with OllamaFalso(lambda c: resp, capacidades=("completion",)) as f:
        prov = PV.crear({"proveedor": "ollama", "url": f.url, "modelo": "x"})
        assert AI.leer(prov, "QUJD")["texto"] is None and f.pedidos == []   # sin visión no pregunta


@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_du06_lee_los_rotulos_con_guia_sin_cambiar_el_reconocimiento():
    from reconocimiento import recognition as rec
    r = rec.recognize_page(str(DU06), page_index=3, utility="DRENAJE", zoom=1.0)
    ml = [a for a in r.anotaciones if a["tipo"] == "multileader" and a["estado"] == "leido"]
    assert len(ml) >= 40
    textos = " ".join(a["texto"] for a in ml)
    assert "LAT CB-205" in textos and '24" RCP SD' in textos
    assert all(a["puntas"] for a in ml)


def test_ventana_guarda_deshace_y_lee_con_ia(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    w = Main()
    img = QtGui.QImage(600, 600, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.informar = lambda *a, **k: setattr(w, "_informado", a)

    class R:
        anotaciones = [dict(tipo="multileader", texto="", caja=[10, 10, 60, 24], tam=0.0, angulo=0.0,
                            guias=[[(10, 24), (60, 24), (80, 60)]], puntas=[(80.0, 60.0)], estado="ilegible",
                            utilidad="", diam_in=None, material="", fuente="pdf")]
    w._push()
    assert w._guardar_anotaciones([R()]) == 1 and w._guardar_anotaciones([R()]) == 0
    w.undo()
    assert w.anotaciones == []
    w.redo()
    assert len(w.anotaciones) == 1
    # la IA lee el ilegible (proveedor y lectura simulados): queda leído, con deshacer
    from ia import anotaciones_ia as AI, proveedor as P

    class Prov:
        def vision(self):
            return True
    monkeypatch.setattr(P, "crear", lambda cfg: Prov())
    monkeypatch.setattr(P.Config, "de", classmethod(lambda cls, d: type("C", (), {"con_ia": True})()))
    monkeypatch.setattr(AI, "leer", lambda *a, **k: {"texto": '8" VCP SS', "confianza": "alta", "nota": ""})
    monkeypatch.setattr(w, "_anot_imagen", lambda a: "QUJD")
    w.leer_anotaciones_con_ia()
    import time
    t0 = time.time()
    while getattr(w, "_anot_tok", None) is not None and time.time() - t0 < 5:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert w.anotaciones[0]["texto"] == '8" VCP SS' and w.anotaciones[0]["fuente"] == "ia"
    assert w.anotaciones[0]["diam_in"] == 8.0
    w.undo()
    assert w.anotaciones[0]["estado"] == "ilegible"
