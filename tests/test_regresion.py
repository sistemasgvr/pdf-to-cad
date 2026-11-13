"""Regresión con casos dorados (`scripts/regresion.py`): el toml es válido y la comparación de fotos
dice lo que cambió. No corre el reconocimiento (eso lo hace el script)."""
import copy
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("regresion", RAIZ / "scripts" / "regresion.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def _util(**cambios):
    base = {"polilineas": 3, "abandonadas": 0, "vertices": 12, "largo_pt": 512.3,
            "huellas": ["aa01", "bb02", "cc03"], "kinds": {"end": 6, "bend": 6},
            "codos": 2, "radios_pt": [14.4, 20.1], "codos_aproximados": 0,
            "bovedas": 1, "bovedas_importables": 1, "diametros": {'18"': 2, "sin dato": 1},
            "grosor_estados": {"leido": 2, "sin_dato": 1}, "cobertura": 0.998,
            "avisos": ["fillets", "orphans"], "avisos_texto": ["Bóvedas sin línea cercana: 1.", "Codos…: 2"]}
    base.update(cambios)
    return base


def _foto(**util):
    return {"version": 1, "id": "x", "archivo": "a.pdf", "sha1": "s", "zoom": 3.5, "utilidades": ["DRENAJE"],
            "hojas": {"3": {"utilidades": {"DRENAJE": _util(**util)}, "valvulas": 0, "anotaciones": 5}}}


def test_toml_valido():
    cfg = R.leer_config()
    assert R.validar_config(cfg) == []
    ids = [c["id"] for c in cfg["caso"]]
    assert len(ids) == len(set(ids))
    for c in cfg["caso"]:
        assert set(c["utilidades"]) <= set(R.UTILIDADES)
        assert not Path(c["archivo"]).is_absolute()


def test_validar_detecta_errores():
    cfg = {"caso": [{"id": "a", "archivo": "x.pdf", "hojas": [0], "utilidades": ["AGUA", "VAPOR"],
                     "zoom": 3.5, "descripcion": "d"},
                    {"id": "a", "archivo": "y.pdf", "hojas": [], "utilidades": ["GAS"], "zoom": 0}]}
    errores = R.validar_config(cfg)
    assert any("VAPOR" in e for e in errores)
    assert any("repetido" in e for e in errores)
    assert any("hojas" in e for e in errores)
    assert any("zoom" in e for e in errores)
    assert any("descripcion" in e for e in errores)
    assert R.validar_config({}) == ["no hay ningún [[caso]]"]


def test_carpeta_por_variable_de_entorno(monkeypatch, tmp_path):
    cfg = {"config": {"carpeta": "C:/otra"}}
    monkeypatch.setenv("PDFCAD_DORADOS", str(tmp_path))
    assert R.ruta_pdf(cfg, {"archivo": "a.pdf"}) == tmp_path / "a.pdf"
    monkeypatch.delenv("PDFCAD_DORADOS")
    assert R.ruta_pdf(cfg, {"archivo": "a.pdf"}) == Path("C:/otra") / "a.pdf"
    assert R.ruta_pdf(cfg, {"archivo": "@repo/tests/x.pdf"}) == RAIZ / "tests" / "x.pdf"


def test_fotos_iguales_no_dan_diferencias():
    assert R.comparar_foto(_foto(), copy.deepcopy(_foto())) == []
    # el redondeo del largo y la cobertura no cuenta como cambio
    assert R.comparar_foto(_foto(), _foto(largo_pt=512.33, cobertura=0.99801)) == []


def test_diferencias_legibles():
    nueva = _foto(polilineas=2, codos=3, radios_pt=[14.4, 20.1, 9.0], huellas=["aa01", "bb02", "dd04"],
                  kinds={"end": 4, "bend": 6, "tee": 1}, diametros={'18"': 1, "sin dato": 1},
                  avisos=["fillets", "orphans", "walls"])
    difs = R.comparar_foto(_foto(), nueva)
    texto = "\n".join(difs)
    assert all(d.startswith("h.4 · DRENAJE:") for d in difs)
    assert "polilíneas 3 → 2" in texto and "codos 2 → 3" in texto
    assert "1 ya no están, 1 nuevas" in texto               # huellas de vértices
    assert "end 6 → 4" in texto and "tee 0 → 1" in texto
    assert 'diámetros: 18" 2 → 1' in texto
    assert "nuevos 9.0" in texto
    assert "nuevos walls" in texto


def test_cambios_de_hoja_utilidad_y_pdf():
    vieja = _foto()
    nueva = copy.deepcopy(vieja)
    nueva["sha1"] = "otro"
    nueva["hojas"]["3"]["utilidades"]["AGUA"] = _util()
    nueva["hojas"]["3"]["anotaciones"] = 6
    nueva["hojas"]["7"] = copy.deepcopy(vieja["hojas"]["3"])
    difs = R.comparar_foto(vieja, nueva)
    assert any("PDF no es el mismo" in d for d in difs)
    assert "h.4 · AGUA: nueva (sin foto)" in difs
    assert "h.8: nueva (sin foto)" in difs
    assert "h.4: rótulos del plano 5 → 6" in difs
    del nueva["hojas"]["3"]["utilidades"]["DRENAJE"]
    assert "h.4 · DRENAJE: ya no se reconoce" in R.comparar_foto(vieja, nueva)


def test_avisos_con_mismas_claves_y_otro_texto():
    difs = R.comparar_foto(_foto(), _foto(avisos_texto=["Bóvedas sin línea cercana: 2.", "Codos…: 2"]))
    assert difs == ["h.4 · DRENAJE: avisos: mismos tipos, cambia su texto/cifras"]
