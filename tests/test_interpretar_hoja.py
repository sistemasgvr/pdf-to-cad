"""Interpretar la hoja (plan 2026-11-16, «reconocimiento desde el editor»): el trabajo PURO que reemplaza al paso
«Capas de la hoja» del asistente. Lo que «Capas» calcula (mismos resultados que `capas_trabajo.leer`) + las letras
del linetype + las fuentes de válvulas + cuántos rótulos + la escala."""
import os

import pytest

fitz = pytest.importorskip("pymupdf")

from hoja import capas_trabajo, interpretar_trabajo as IT          # noqa: E402
from reconocimiento import recognition as rec                    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DU06 = os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "docs prueba",
                    "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
PHOENIX = os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "DOCS DE PRUEBA IND",
                       "QS Water_Indian School_South.pdf")
CLAVES = {"firma", "layers", "leyenda", "visibles", "sugeridos", "letras", "simbolos", "rotulos_n", "escala"}


def _o_saltar(ruta):
    if not os.path.exists(ruta):
        pytest.skip(f"no está {os.path.basename(ruta)}")
    return ruta


@pytest.mark.parametrize("ruta,hoja", [(DU06, 3), (PHOENIX, 4)])
def test_igual_que_capas_de_la_hoja(ruta, hoja):
    _o_saltar(ruta)
    capas = capas_trabajo.leer(ruta, hoja)
    it = IT.interpretar(ruta, hoja, firma="f1", escala=0.1)
    assert set(it) == CLAVES and it["firma"] == "f1"
    assert it["layers"] == capas["layers"]
    assert it["leyenda"] == capas["leyenda"]
    assert it["visibles"] == capas["visibles"]
    assert it["sugeridos"] == capas.get("sugeridos")
    assert isinstance(it["simbolos"], list) and isinstance(it["rotulos_n"], int)


def test_letras_iguales():
    _o_saltar(DU06)
    it = IT.interpretar(DU06, 3, escala=0.1)
    rec._LETRAS_MEMO.clear()                                     # que la comparación las lea de nuevo
    with fitz.open(DU06) as doc:
        letras = rec.page_letters(doc[3])
    assert it["letras"] and set(it["letras"]) == set(letras)
    for nombre, lt in letras.items():
        mia = it["letras"][nombre]
        assert (mia.codes, mia.utilities, mia.sites, mia.raw, mia.noisy) ==             (lt.codes, lt.utilities, lt.sites, lt.raw, lt.noisy)
        assert (mia.by_path, mia.coverage) == (lt.by_path, lt.coverage)


def test_viaja_por_la_tuberia_del_proceso():
    """El resultado vuelve del trabajador por pickle: nada de funciones dentro."""
    import pickle
    _o_saltar(DU06)
    it = IT.interpretar(DU06, 3, escala=0.1)
    vuelta = pickle.loads(pickle.dumps(it))
    assert vuelta["layers"] == it["layers"] and set(vuelta["letras"]) == set(it["letras"])
    assert all(v.by_path == it["letras"][k].by_path for k, v in vuelta["letras"].items())


def test_du06_fuentes_de_valvulas_y_rotulos():
    _o_saltar(DU06)
    it = IT.interpretar(DU06, 3, escala=0.1)
    capas_valv = [L["name"] for L in it["layers"] if L["path_count"]
                  and __import__("reconocimiento.recognition_valvulas", fromlist=["x"]).es_capa_valvula(L["name"])]
    assert sorted(s["nombre"] for s in it["simbolos"] if s["fuente"] == "capa") == sorted(capas_valv)
    assert it["rotulos_n"] > 0                                   # DU06 h.3 trae multileaders


def _hoja_sin_capas(ruta):
    import test_estilos_sugeridos as TES
    doc = fitz.open()
    TES._hoja(doc)
    doc.save(ruta)


def test_hoja_sin_capas_ni_leyenda_trae_sugeridos(tmp_path):
    ruta = str(tmp_path / "sin_capas.pdf")
    _hoja_sin_capas(ruta)
    it = IT.interpretar(ruta, 0, escala=0.1)
    assert it["sugeridos"] == capas_trabajo.leer(ruta, 0)["sugeridos"]
    assert it["sugeridos"].utilidad == "GAS"
    assert it["rotulos_n"] > 0                                   # «3/4" STL '56» junto a las acometidas
    assert {"fuente": "forma", "nombre": "moño"} in it["simbolos"]   # sin capas ni leyenda: el moño del plano


def test_escala_dada_no_se_detecta(tmp_path, monkeypatch):
    ruta = str(tmp_path / "sin_capas.pdf")
    _hoja_sin_capas(ruta)
    import vector_pipeline

    def no(*_a, **_k):
        raise AssertionError("no debía leer la escala")
    monkeypatch.setattr(vector_pipeline, "detect_scale", no)
    assert IT.interpretar(ruta, 0, escala=0.25)["escala"] == 0.25


def test_escala_sin_dar_se_detecta(tmp_path, monkeypatch):
    ruta = str(tmp_path / "sin_capas.pdf")
    _hoja_sin_capas(ruta)
    import vector_pipeline
    monkeypatch.setattr(vector_pipeline, "detect_scale", lambda page: 0.5)
    assert IT.interpretar(ruta, 0)["escala"] == 0.5


def test_avisa_cada_etapa(tmp_path, monkeypatch):
    ruta = str(tmp_path / "sin_capas.pdf")
    _hoja_sin_capas(ruta)
    import vector_pipeline
    monkeypatch.setattr(vector_pipeline, "detect_scale", lambda page: 0.5)
    textos = []
    IT.interpretar(ruta, 0, progreso=lambda t, i=None, n=None: textos.append(t))
    for etapa in IT.ETAPAS:
        assert etapa in textos


def test_trabajo_en_el_spec():
    with open(os.path.join(RAIZ, "PDF-a-CAD.spec"), encoding="utf-8") as f:
        assert '"hoja.interpretar_trabajo"' in f.read()
    import autoprueba
    assert "hoja.interpretar_trabajo" in autoprueba.MODULOS_POR_NOMBRE
