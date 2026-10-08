"""conftest.py — configuración común de las pruebas.

Agrega al sys.path la carpeta `app/` y la raíz del proyecto, igual que hace
app/main.py, para que los módulos de la app (model, geo.georef, civil_catalog…)
y del pipeline (config, vector_pipeline…) se importen con nombres planos.

Las pruebas son HEADLESS: ejercitan la lógica pura (georreferenciación, catálogo,
modelo) sin abrir la interfaz Qt ni un bucle de eventos.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_ROOT, "app")
for _p in (_APP, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


import pytest  # noqa: E402


class _AjustesEnMemoria:
    """Sustituto de QSettings para las pruebas (no toca el registro del usuario)."""

    def __init__(self):
        self._d = {}

    def value(self, clave, default=None, type=None):  # noqa: A002 (firma de QSettings)
        v = self._d.get(clave, default)
        if type is bool and isinstance(v, str):
            return v.lower() == "true"
        return type(v) if (type is not None and v is not None) else v

    def setValue(self, clave, valor):  # noqa: N802
        self._d[clave] = valor


@pytest.fixture(autouse=True)
def _paneles_con_ajustes_en_memoria(monkeypatch):
    """Los paneles laterales (side_panels.py) arrancan siempre fijados en las
    pruebas: no leen ni guardan las preferencias reales («ocultar automáticamente»)."""
    try:
        from ui.comun import side_panels
    except Exception:          # pruebas sin Qt disponible
        yield
        return
    mem = _AjustesEnMemoria()
    monkeypatch.setattr(side_panels, "_settings", lambda: mem)
    yield


@pytest.fixture(autouse=True)
def _recuperacion_en_carpeta_temporal(monkeypatch, tmp_path):
    """Las copias automáticas (autoguardado.py) nunca van a %LOCALAPPDATA% en las pruebas."""
    monkeypatch.setenv("PDFCAD_RECUPERACION", str(tmp_path / "recuperacion"))
    yield
