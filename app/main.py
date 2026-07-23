"""main.py — Punto de entrada de la aplicación (QApplication).

Módulos de la app (en esta carpeta app/):
  app_window.py     → la ventana Main (UI y eventos)
  model.py          → estructuras de datos y constantes
  geometry.py       → transformaciones de coordenadas y geometría
  dxf_export.py     → exportación a DXF
  sidecar_export.py → salida JSON de red 3D
Los módulos del pipeline (config, vector_pipeline, digitize, …) están en la raíz
del proyecto (carpeta superior).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # …/app
_ROOT = os.path.dirname(_HERE)                              # …/ (raíz del proyecto)
for _p in (_HERE, _ROOT):                                   # app/ para los módulos, raíz para config/pipeline
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app_window import main

if __name__ == "__main__":
    main()
