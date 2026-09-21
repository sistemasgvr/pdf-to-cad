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
                 hidden_ocgs=None, layer_roles=None, join_routes=True,
                 scale_ft_per_pt=None):
        super().__init__()
        self.pdf_path = pdf_path
        self.scale_ft_per_pt = scale_ft_per_pt   # hoja compuesta: escala fija
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
                join_routes=self.join_routes,
                scale_ft_per_pt=self.scale_ft_per_pt)
            self.done.emit(result, "")
        except Exception as e:
            import traceback
            self.done.emit(None, f"{e}\n\n{traceback.format_exc()}")


class OrganizedRecognitionWorker(QtCore.QThread):
    """Recognize and render every selected sheet with its source PDF's OCGs."""
    done = QtCore.Signal(object, str)

    def __init__(self, base_path, external_pdfs, sheets, hidden_by_source,
                 zoom=1.0, join_routes=True, crops=None):
        super().__init__()
        self.base_path = base_path
        self.external_pdfs = external_pdfs
        self.sheets = sheets
        self.hidden_by_source = hidden_by_source
        self.zoom = zoom
        self.join_routes = join_routes
        self.crops = crops or {}

    def run(self):
        import fitz
        import pdf_layers
        import recognition
        from sheet_crops import page_rect
        docs = []
        try:
            docs.append(fitz.open(self.base_path))
            for source in self.external_pdfs:
                docs.append(fitz.open(stream=source["data"], filetype="pdf"))
            rows = []
            for sheet in self.sheets:
                source = sheet["source"]
                doc = docs[source]
                hidden = list(self.hidden_by_source.get(str(source), ()))
                crop = self.crops.get(sheet["slot"])
                pdf_layers.set_hidden(doc, hidden)
                result = recognition.recognize_page(
                    self.base_path, page_index=sheet["page"], doc=doc,
                    zoom=self.zoom, utility="ELECTRICO", hidden_ocgs=hidden,
                    join_routes=self.join_routes, crop=crop)
                pix = doc[sheet["page"]].get_pixmap(
                    matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False,
                    clip=page_rect(doc[sheet["page"]], crop))
                rows.append({"sheet": sheet, "result": result,
                             "width": pix.width, "height": pix.height,
                             "stride": pix.stride, "samples": bytes(pix.samples)})
            self.done.emit(rows, "")
        except Exception as exc:
            import traceback
            self.done.emit(None, f"{exc}\n\n{traceback.format_exc()}")
        finally:
            for doc in docs:
                doc.close()
