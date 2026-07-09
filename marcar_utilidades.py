"""
marcar_utilidades.py — Lanzador de compatibilidad (permanece en la raíz).

La app se dividió en módulos dentro de la carpeta app/ (app_window, model, geometry,
ocr, dxf_export, sidecar_export). Este archivo se conserva para no romper la forma
habitual de lanzarla:
    python marcar_utilidades.py        (equivalente a: python app/main.py)
"""
import os
import sys

_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)                # para encontrar app_window y sus módulos

from app_window import main, Main  # noqa: F401  (re-export)

if __name__ == "__main__":
    main()
