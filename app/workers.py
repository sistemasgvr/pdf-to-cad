"""workers.py — Hilos de trabajo en segundo plano de la UI.

- PipelineWorker: corre la digitalización PDF→DXF (digitize.main) fuera del hilo
  de la interfaz para no congelar la ventana; emite `done(tmp, error)` al terminar.

Extraído de app_window.py sin cambios de comportamiento (solo reubicación).
"""
from PySide6 import QtCore


class PipelineWorker(QtCore.QThread):
    done = QtCore.Signal(str, str)

    def __init__(self, pdf, tmp): super().__init__(); self.pdf, self.tmp = pdf, tmp

    def run(self):
        try:
            import digitize
            digitize.main(self.pdf, self.tmp, verbose=False); self.done.emit(self.tmp, "")
        except Exception as e:
            import traceback; self.done.emit("", f"{e}\n\n{traceback.format_exc()}")
