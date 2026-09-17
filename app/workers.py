"""workers.py — Hilos de trabajo en segundo plano de la UI.

- PipelineWorker: corre la digitalización PDF→DXF (digitize.main) fuera del hilo
  de la interfaz para no congelar la ventana; emite `done(tmp, error)` al terminar.
- RecognitionWorker: reconoce OCG de una hoja (recognition.recognize_page);
  emite `done(result, error)` al terminar. No toca el modelo de pipes.

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


class RecognitionWorker(QtCore.QThread):
    """Reconocimiento OCG en segundo plano. `done(result_or_None, error_str)`."""
    done = QtCore.Signal(object, str)

    def __init__(self, pdf_path, page_index, zoom=1.0, utility="ELECTRICO",
                 hidden_ocgs=None, layer_roles=None, join_routes=True):
        super().__init__()
        self.pdf_path = pdf_path
        self.page_index = page_index
        self.zoom = zoom
        self.utility = utility
        self.hidden_ocgs = list(hidden_ocgs or [])
        self.layer_roles = dict(layer_roles or {})
        self.join_routes = join_routes

    def run(self):
        try:
            import recognition as rec
            result = rec.recognize_page(
                self.pdf_path, page_index=self.page_index,
                utility=self.utility, zoom=self.zoom,
                hidden_ocgs=self.hidden_ocgs,
                layer_roles=self.layer_roles or None,
                join_routes=self.join_routes)
            self.done.emit(result, "")
        except Exception as e:
            import traceback
            self.done.emit(None, f"{e}\n\n{traceback.format_exc()}")
