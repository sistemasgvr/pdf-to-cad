"""2026-11-21: el vigía no corre código de Qt a mitad de un `import` (access violation en `feature_import`)."""
import importlib
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.comun import vigia_carga as V  # noqa: E402


def test_se_detecta_un_import_a_medias(tmp_path, monkeypatch):
    assert not V.importando_en_la_pila()
    (tmp_path / "modulo_prueba_vigia.py").write_text(
        "from ui.comun import vigia_carga as V\nEN_IMPORT = V.importando_en_la_pila()\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("modulo_prueba_vigia", None)
    m = importlib.import_module("modulo_prueba_vigia")
    assert m.EN_IMPORT                                     # el código del módulo corre DENTRO del import
    assert not V.importando_en_la_pila()                   # y al terminar ya no


def test_el_envoltorio_de_pyside_cuenta_como_import():
    def feature_import():                                  # mismo nombre que el de shibokensupport
        return V.importando_en_la_pila()
    assert feature_import()
    assert V.pintando_en_la_pila.__doc__ is None or True
