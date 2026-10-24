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
    progreso = QtCore.Signal(str, object, object)        # etapa, i, n (barra de la exportación)

    def __init__(self, pdf, tmp, pages=None):
        super().__init__(); self.pdf, self.tmp, self.pages = pdf, tmp, pages
        self._doc = None

    def tomar_doc(self):
        """El documento ezdxf que se guardó en `tmp` (una sola vez; None si no hay). Usarlo en vez de
        releer el archivo da el mismo DXF final y ahorra ~30 s con un plano de 132 MB (2026-10-19)."""
        doc, self._doc = self._doc, None
        return doc

    def run(self):
        try:
            import digitize
            docs = []
            from exportar import dxf_rapido              # mismo archivo, ~45 % menos tiempo
            from nucleo import avance
            with avance.escuchar(lambda t, i, n: self.progreso.emit(t, i, n)):
                digitize.main(self.pdf, self.tmp, verbose=False, pages=self.pages, doc_out=docs,
                              guardar=dxf_rapido.guardar, avance=avance.avisar)
            self._doc = docs[0] if docs else None
            self.done.emit(self.tmp, "")
        except Exception as e:
            import traceback; self.done.emit("", f"{e}\n\n{traceback.format_exc()}")


class RecognitionWorker(QtCore.QThread):
    """Reconocimiento OCG en segundo plano. `done(result_or_None, error_str)`;
    `progress(i, n, utilidad)` antes de reconocer cada utilidad; `layer(i, n, utilidad, k, m)`
    al empezar cada capa y `partial(utilidad, trazos)` con lo ya reconocido de cada utilidad.

    `start()` lo corre en el PROCESO trabajador (`proceso`, pedido del usuario 2026-10-14: la
    ventana no se traba y la memoria vuelve al sistema); `cancel()` lo corta al instante. Con
    `PDFCAD_PROCESO=0`, o llamando `run()`, corre aquí mismo como siempre
    (`reconocimiento.recognition_trabajo.reconocer_hoja`)."""
    done = QtCore.Signal(object, str)
    progress = QtCore.Signal(int, int, str)
    layer = QtCore.Signal(int, int, str, int, int)
    partial = QtCore.Signal(str, object)
    stage = QtCore.Signal(str, object, object)        # etapa (`nucleo.avance`): texto, i, n

    def __init__(self, pdf_path, page_index, zoom=1.0, utility="ELECTRICO",
                 hidden_ocgs=None, layer_roles=None, join_routes=True,
                 scale_ft_per_pt=None, utilities=None, roles_by_utility=None, letters_off=None,
                 perfiles_de=None):
        super().__init__()
        self.pdf_path = pdf_path
        self.scale_ft_per_pt = scale_ft_per_pt   # hoja compuesta: escala fija
        self.page_index = page_index
        self.zoom = zoom
        from reconocimiento import recognition as rec
        self.utilities = rec.normalize_utilities(utilities if utilities is not None else utility)
        self.hidden_ocgs = list(hidden_ocgs or [])
        self.layer_roles = dict(layer_roles or {})
        self.roles_by_utility = {str(k): dict(v or {})
                                 for k, v in (roles_by_utility or {}).items()}
        self.join_routes = join_routes
        # capas que el usuario decidió NO tomar por las letras de su línea («Capas de la hoja»)
        self.letters_off = set(letters_off or ())
        # hoja compuesta: (pdf, hoja) de origen de cada pieza, por los perfiles de sus laterales
        self.perfiles_de = [tuple(x) for x in (perfiles_de or ())]
        self._tarea = None
        self._tareas = []
        self._partes = None
        self._hechas = 0

    def _kwargs(self):
        return dict(pdf_path=self.pdf_path, page_index=self.page_index, zoom=self.zoom,
                    utilities=tuple(self.utilities), hidden_ocgs=tuple(self.hidden_ocgs),
                    layer_roles=self.layer_roles, roles_by_utility=self.roles_by_utility,
                    join_routes=self.join_routes, scale_ft_per_pt=self.scale_ft_per_pt,
                    letters_off=tuple(sorted(self.letters_off)), perfiles_de=tuple(self.perfiles_de))

    def _avance(self, a):
        if a[0] == "utilidad":
            self.progress.emit(a[1], a[2], a[3])
        elif a[0] == "capa":
            self.layer.emit(a[1], a[2], a[3], a[4], a[5])
        elif a[0] == "hecha":
            self.partial.emit(a[3], a[4])
        elif a[0] == "detalle":
            self.stage.emit(a[1], a[2], a[3])

    def start(self, *args):
        """Al proceso trabajador. Con varias utilidades, cada una en su proceso a la vez
        (`proceso_hijo.paralelos`: la mitad de los núcleos y lo que deje la RAM libre); los
        resultados vuelven en el orden de siempre y son los mismos (cada utilidad se
        reconoce sola, como en la vuelta de siempre)."""
        from ui.comun import proceso, proceso_hijo
        if not proceso.activo():
            return super().start(*args)
        n_par = proceso_hijo.paralelos(len(self.utilities))
        grupos = ([tuple(self.utilities)] if n_par <= 1
                  else [(u,) for u in self.utilities])
        self._partes = [None] * len(grupos)
        self._tareas = []
        self._hechas = 0
        for k, us in enumerate(grupos):
            kw = self._kwargs()
            kw["utilities"] = us
            if len(grupos) > 1 and "DRENAJE" not in us:
                kw["perfiles_de"] = ()                  # los lee solo el proceso del drenaje
            t = proceso.Tarea("reconocimiento.recognition_trabajo:reconocer_hoja", kwargs=kw)
            t.avance.connect(lambda a, k=k, n=len(grupos): self._avance(a) if n == 1 else self._avance_parte(k, a))
            t.terminado.connect(lambda r, e, k=k: self._fin_parte(k, r, e))
            self._tareas.append(t)
            proceso.trabajador("principal" if k % n_par == 0 else f"principal-{k % n_par}").enviar(t)
        self._tarea = self._tareas[0]

    def _avance_parte(self, k, a):
        """Avance de UNA utilidad de las que corren a la vez (su índice es el de la lista)."""
        n = len(self.utilities)
        if a[0] == "utilidad":
            self.progress.emit(self._hechas, n, self.utilities[k])
        elif a[0] == "capa":
            self.layer.emit(k, n, a[3], a[4], a[5])
        elif a[0] == "hecha":
            self.partial.emit(a[3], a[4])
        elif a[0] == "detalle":
            self.stage.emit(a[1], a[2], a[3])

    def _fin_parte(self, k, res, err):
        if self._partes is None:
            return                                    # ya terminó (error o cancelado)
        if err:
            for t in self._tareas:
                if not t.hecha:
                    t.cancelar()
            self._partes = None
            self._fin_proceso(None, err)
            return
        self._partes[k] = res
        self._hechas += 1
        if self._hechas < len(self._partes):
            self.progress.emit(self._hechas, len(self.utilities), self.utilities[min(self._hechas, len(self.utilities) - 1)])
            return
        partes, self._partes = self._partes, None
        todos = [r for parte in partes for r in (parte or [])]
        if len(partes) > 1:
            # cada utilidad vino de su proceso: los cruces de los perfiles, con todas juntas
            from reconocimiento import recognition_grosor_cruces
            recognition_grosor_cruces.aplicar(todos)
        self._fin_proceso(todos, "")

    def _fin_proceso(self, res, err):
        self._tarea = None
        if err == "cancelado":
            self.done.emit(None, "")
        elif err == "memoria":
            from traduccion.i18n import t as _tr
            self.done.emit(None, _tr("La hoja necesita más memoria de la que hay libre en el equipo. "
                                     "Prueba con menos hojas en la composición, menos utilidades a la vez "
                                     "o cerrando otros programas."))
        else:
            self.done.emit(res, err)

    def cancel(self):
        for t in list(getattr(self, "_tareas", None) or ([self._tarea] if self._tarea else [])):
            if t is not None and not t.hecha:
                t.cancelar()

    def run(self):
        try:
            from nucleo import avance
            from reconocimiento import recognition_trabajo
            with avance.escuchar(lambda t, i, n: self._avance(("detalle", t, i, n))):
                results = recognition_trabajo.reconocer_hoja(
                    progreso=lambda *a: self._avance(a), **self._kwargs())
            self.done.emit(results, "")
        except Exception as e:
            import traceback
            self.done.emit(None, f"{e}\n\n{traceback.format_exc()}")


class OrganizedRecognitionWorker(QtCore.QThread):
    """Recognize and render every selected sheet with its source PDF's OCGs."""
    done = QtCore.Signal(object, str)

    def __init__(self, base_path, external_pdfs, sheets, hidden_by_source,
                 zoom=1.0, join_routes=True, crops=None, utility="ELECTRICO",
                 utilities=None):
        super().__init__()
        self.base_path = base_path
        self.external_pdfs = external_pdfs
        self.sheets = sheets
        self.hidden_by_source = hidden_by_source
        self.zoom = zoom
        self.join_routes = join_routes
        self.crops = crops or {}
        from reconocimiento import recognition as rec
        self.utilities = rec.normalize_utilities(utilities if utilities is not None else utility)

    def run(self):
        import fitz
        from hoja import pdf_layers
        from reconocimiento import recognition
        from hoja.sheet_crops import page_rect
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
                letters = recognition.page_letters(doc[sheet["page"]])
                results = [recognition.recognize_page(
                    self.base_path, page_index=sheet["page"], doc=doc,
                    zoom=self.zoom, utility=utility, hidden_ocgs=hidden,
                    join_routes=self.join_routes, crop=crop, letters=letters)
                    for utility in self.utilities]
                pix = doc[sheet["page"]].get_pixmap(
                    matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False,
                    clip=page_rect(doc[sheet["page"]], crop))
                rows.append({"sheet": sheet, "results": results,
                             "result": results[0],
                             "width": pix.width, "height": pix.height,
                             "stride": pix.stride, "samples": bytes(pix.samples)})
            self.done.emit(rows, "")
        except Exception as exc:
            import traceback
            self.done.emit(None, f"{exc}\n\n{traceback.format_exc()}")
        finally:
            for doc in docs:
                doc.close()
