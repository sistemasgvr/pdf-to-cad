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
