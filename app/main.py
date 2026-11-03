"""main.py — Punto de entrada de la aplicación (QApplication).

Paquetes de la app (en esta carpeta app/):
  ui/             → interfaz Qt: ventana Main (ui/ventana/app_window.py), asistente, diálogos, comunes
  nucleo/         → modelo y lógica pura del dominio (model, model_ops, normativas…)
  reconocimiento/ → lectura del PDF vectorial
  hoja/           → hoja compuesta, capas y leyenda del PDF
  catalogo/       → catálogo de piezas de Civil 3D
  exportar/       → exportación a DXF
  geo/            → georreferenciación
Los módulos del pipeline (config, vector_pipeline, digitize, …) están en la raíz
del proyecto (carpeta superior).
"""
import os
import sys

# numpy (OpenBLAS) reserva búferes para un hilo de cálculo por núcleo al importarse: +361 MB
# de memoria en un equipo de 12 núcleos, en la ventana y en cada proceso trabajador. La app
# solo multiplica matrices chicas (letras de los mapas): con un hilo, +8 MB (medido 2026-10-14).
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

# Sin consola (el .exe, pythonw) `sys.stdout` y `sys.stderr` son None y el primer `flush` o `write` de cualquier
# librería lanza un error; en un proceso hijo, además, PyInstaller lo muestra como «Unhandled exception in script».
# También corre en los hijos: importan este módulo, o lo arrancan (.exe), antes de empezar a trabajar.
for _v in ("stdout", "stderr"):
    if getattr(sys, _v) is None:
        setattr(sys, _v, open(os.devnull, "w", encoding="utf-8"))

_HERE = os.path.dirname(os.path.abspath(__file__))          # …/app
_ROOT = os.path.dirname(_HERE)                              # …/ (raíz del proyecto)
for _p in (_HERE, _ROOT):                                   # app/ para los módulos, raíz para config/pipeline
    if _p not in sys.path:
        sys.path.insert(0, _p)

if __name__ == "__main__":
    # El trabajo pesado va a un proceso aparte (`ui.comun.proceso`): en el .exe el hijo arranca
    # este mismo programa y `freeze_support` lo desvía antes de abrir la ventana; la interfaz se
    # importa solo aquí, así el hijo (que importa este módulo como `__mp_main__`) no la carga.
    import multiprocessing
    multiprocessing.freeze_support()
    from nucleo import diagnostico
    diagnostico.activar()
    from ui.ventana.app_window import main
    if not getattr(sys, "frozen", False):        # SOLO desarrollo: F5 recarga módulos (por nombre: no va al .exe)
        import importlib
        importlib.import_module("dev_recarga").activar()
    main()
