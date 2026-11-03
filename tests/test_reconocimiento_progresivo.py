import copy
import dataclasses
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from test_agregar_utilidad import app, pdfs, win  # noqa: F401
from ui.comun.progreso_reconocimiento import ProgresoReconocimiento
from ui.comun.trazado_progresivo import TrazadoProgresivo
from reconocimiento.recognition_trabajo import FlujoTrazos


def test_card_is_in_corner_without_veil_and_restores_controls(win, app):
    image = QtGui.QImage(1800, 1000, QtGui.QImage.Format_RGB32)
    image.fill(QtCore.Qt.white)
    win.canvas.set_image(image)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    disabled = QtGui.QAction("disabled", win)
    disabled.setEnabled(False)
    enabled = QtGui.QAction("enabled", win)
    card = ProgresoReconocimiento(win)
    card.begin("Reconociendo Agua…", "Leyendo las líneas", cancel=lambda: None)
    QtTest.QTest.qWait(30)  # Qt settles dock/toolbar layout after showing the tool window.
    viewport = win.canvas.viewport()
    origin = viewport.mapToGlobal(QtCore.QPoint(0, 0))
    assert card.isVisible() and card.isWindow() and card.width() <= 340
    assert card.x() >= origin.x() + viewport.width() - card.width() - 15
    assert origin.y() <= card.y() <= origin.y() + viewport.height() - card.height() - 14
    assert not card.geometry().intersects(win._flot_barra_win.geometry())
    assert win.canvas.isEnabled() and win.canvas._recognition_readonly
    assert not enabled.isEnabled() and not disabled.isEnabled()
    assert QtWidgets.QApplication.overrideCursor() is None
    card.step(detail="Capa 2 de 4", done=2, total=4)
    assert card.bar.value() == 500
    assert card.detail() == "Capa 2 de 4"
    card.end()
    assert not card.active and not card.isVisible()
    assert not win.canvas._recognition_readonly and enabled.isEnabled() and not disabled.isEnabled()


def test_cancel_once_and_readonly_canvas_allows_zoom(win, app, monkeypatch):
    image = QtGui.QImage(1800, 1000, QtGui.QImage.Format_RGB32)
    win.canvas.set_image(image)
    cancel, clicks = [], []
    win.canvas.clicked.connect(lambda *a: clicks.append(a))
    card = ProgresoReconocimiento(win)
    card.begin("Reconociendo…", cancel=lambda: cancel.append(1))
    scale = win.canvas.transform().m11()
    assert win.canvas.apply_zoom(1.25) and win.canvas.transform().m11() != scale
    QtTest.QTest.mouseClick(win.canvas.viewport(), QtCore.Qt.LeftButton, pos=QtCore.QPoint(20, 20))
    assert not clicks
    card.cancel_button.click()
    card.cancel_button.click()
    app.processEvents()
    assert cancel == [1]
    card.end()


def _segments(drawing):
    out = []
    for group in drawing.items.values():
        for item in group:
            path, prev = item.path(), None
            for index in range(path.elementCount()):
                point = path.elementAt(index)
                xy = (point.x, point.y)
                if point.isLineTo():
                    out.append((prev, xy))
                prev = xy
    return out


def test_long_line_is_drawn_in_bounded_ticks_without_missing_segments(win, monkeypatch):
    from ui.comun import trazado_progresivo as TP
    monkeypatch.setattr(TP, "MS_POR_TANDA", 10000)
    drawing = TrazadoProgresivo(win.canvas)
    points = [(float(i), float(i % 7)) for i in range(10001)]
    drawing.agregar("AGUA", [points])
    assert not drawing.items and drawing.queue
    drawing._tick()
    assert drawing.queue and len(_segments(drawing)) == TP.SEGMENTOS_POR_TICK
    while drawing.queue:
        drawing._tick()
    assert _segments(drawing) == list(zip(points, points[1:]))
    drawing.cerrar()
    assert not drawing.items and not drawing.queue


def test_final_snapshot_replaces_only_its_utility(win):
    drawing = TrazadoProgresivo(win.canvas)
    drawing.agregar("AGUA", [[(0, 0), (1, 0)]])
    drawing.agregar("GAS", [[(0, 1), (1, 1)]])
    drawing._tick()
    gas = list(drawing.items["GAS"])
    drawing.agregar("AGUA", [[(2, 0), (3, 0)]])
    drawing.reemplazar("AGUA", [[(10, 0), (20, 0)]])
    while drawing.queue:
        drawing._tick()
    assert drawing.items["GAS"] == gas
    assert set(_segments(drawing)) == {((10., 0.), (20., 0.)), ((0., 1.), (1., 1.))}
    drawing.cerrar()


def test_stroke_messages_are_bounded_snapshots():
    batches = []
    flow = FlujoTrazos(batches.append)
    points = [[float(i), 0.] for i in range(10001)]
    flow.agregar(points)
    for _ in range(150):
        flow.agregar([(0, 1), (1, 1)])
    flow.vaciar()
    assert batches
    assert all(len(batch) <= flow.MAX_LINEAS and sum(map(len, batch)) <= flow.MAX_PUNTOS for batch in batches)
    points[0][0] = -999
    assert batches[0][0][0] == (0., 0.)
    first = [p for batch in batches for p in batch if p[0][1] == 0.]
    assert [edge for piece in first for edge in zip(piece, piece[1:])] == [
        ((float(i), 0.), (float(i + 1), 0.)) for i in range(10000)]


@pytest.mark.parametrize("separate_process", [False, True])
def test_real_recognition_streams_before_utility_finishes_and_result_is_identical(
        tmp_path, app, monkeypatch, separate_process):
    from reconocimiento import recognition_trabajo as RT
    path = tmp_path / "water.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=800, height=800)
        oc = doc.add_ocg("LINES")
        for y in range(40, 500, 40):
            page.draw_line((40, y), (600, y), color=(0, 0, 1), oc=oc)
        doc.save(path)
    kw = dict(utilities=("AGUA",), layer_roles={"lineas": ["LINES"]}, scale_ft_per_pt=1.)
    baseline = RT.reconocer_hoja(str(path), 0, **kw)
    events = []
    if separate_process:
        from ui.comun import proceso
        from test_planos_fondo import _esperar
        monkeypatch.setenv("PDFCAD_PROCESO", "1")
        task = proceso.Tarea("reconocimiento.recognition_trabajo:reconocer_hoja",
                             kwargs=dict(pdf_path=str(path), page_index=0, **kw))
        task.avance.connect(events.append)
        completed, ticks = [], []
        task.terminado.connect(lambda r, e: completed.append((r, e)))
        timer = QtCore.QTimer(interval=10, timeout=lambda: ticks.append(1))
        timer.start()
        try:
            proceso.trabajador("test-reconocimiento").enviar(task)
            assert _esperar(app, lambda: bool(completed), seg=30)
            live, error = completed[0]
            assert not error and ticks
        finally:
            timer.stop()
            proceso.trabajador("test-reconocimiento").parar()
    else:
        live = RT.reconocer_hoja(str(path), 0, progreso=lambda *a: events.append(a), **kw)
    kinds = [event[0] for event in events]
    assert "trazos" in kinds and kinds.index("trazos") < kinds.index("hecha")
    assert json.dumps([dataclasses.asdict(r) for r in live], sort_keys=True) == json.dumps(
        [dataclasses.asdict(r) for r in baseline], sort_keys=True)
    assert baseline[0].drawable


class _Worker(QtCore.QObject):
    done = QtCore.Signal(object, str)
    progress = QtCore.Signal(int, int, str)
    layer = QtCore.Signal(int, int, str, int, int)
    partial = QtCore.Signal(str, object)
    strokes = QtCore.Signal(str, object)
    stage = QtCore.Signal(str, object, object)

    def __init__(self, pdf, page, **kw):
        super().__init__()
        self.page_index = page

    def start(self):
        pass

    def cancel(self):
        self.done.emit(None, "")


def test_main_ignores_strokes_from_previous_session_and_never_imports_preview(win, pdfs, monkeypatch):
    import test_agregar_utilidad as TA
    from ui.ventana import app_window
    TA._editor_con_agua(win, pdfs[0])
    monkeypatch.setattr(app_window, "RecognitionWorker", _Worker)
    completed = []
    monkeypatch.setattr(win, "_recognition_done", lambda *a: completed.append(a))
    before = copy.deepcopy(win.pipes)
    win._start_recognition(0)
    old = win._recog_worker
    old.strokes.emit("AGUA", [[(0, 0), (1, 0)]])
    assert win._recog_dibujo.queue
    win._end_recognition_busy()
    win._start_recognition(0)
    new = win._recog_worker
    old.strokes.emit("AGUA", [[(10, 0), (20, 0)]])
    old.done.emit([], "")
    assert not win._recog_dibujo.queue and not completed
    new.strokes.emit("AGUA", [[(30, 0), (40, 0)]])
    win._recog_dibujo._tick()
    assert _segments(win._recog_dibujo) == [((30., 0.), (40., 0.))]
    assert win.pipes == before
    win._end_recognition_busy()


def test_thread_worker_delivers_strokes_on_gui_thread(win, pdfs, app, monkeypatch):
    import test_agregar_utilidad as TA
    from ui.ventana import app_window
    from ui.comun.workers import RecognitionWorker

    class ThreadWorker(RecognitionWorker):
        def start(self):
            QtCore.QThread.start(self)

        def run(self):
            self.strokes.emit("AGUA", [[(0, 0), (1, 0)]])

    TA._editor_con_agua(win, pdfs[0])
    monkeypatch.setattr(app_window, "RecognitionWorker", ThreadWorker)
    threads = []
    monkeypatch.setattr(win, "_recognition_strokes", lambda *a: threads.append(QtCore.QThread.currentThread()))
    win._start_recognition(0)
    assert win._recog_worker.wait(5000)
    app.processEvents()
    assert threads == [app.thread()]
    win._end_recognition_busy()


class _Arrastre:
    """Lo que `dragEnterEvent`/`dropEvent` de la ventana le piden a su evento."""

    def __init__(self):
        self.aceptado = False

    def mimeData(self):
        datos = QtCore.QMimeData()
        datos.setUrls([QtCore.QUrl.fromLocalFile("otro.pdf")])
        return datos

    def acceptProposedAction(self):
        self.aceptado = True

    def ignore(self):
        self.aceptado = False


def test_soltar_un_pdf_en_la_ventana_queda_pausado_mientras_reconoce(win, monkeypatch):
    """Fuera del lienzo el arrastre llega a la ventana: abriría otro PDF con el reconocimiento en marcha."""
    abiertos = []
    monkeypatch.setattr(win, "open_path", abiertos.append)
    card = ProgresoReconocimiento(win)
    card.begin("Reconociendo…")
    entrada = _Arrastre()
    win.dragEnterEvent(entrada)
    win.dropEvent(_Arrastre())
    assert not entrada.aceptado and not abiertos
    card.end()
    entrada = _Arrastre()
    win.dragEnterEvent(entrada)
    win.dropEvent(_Arrastre())
    assert entrada.aceptado and len(abiertos) == 1


def test_el_filtro_de_eventos_solo_vive_mientras_reconoce(win, app):
    """Un filtro en Python sobre el lienzo pasaría por cada movimiento del ratón, también sin reconocer."""
    class Espia(ProgresoReconocimiento):
        vistos = 0

        def eventFilter(self, obj, event):
            type(self).vistos += 1
            return super().eventFilter(obj, event)

    card = Espia(win)
    app.sendEvent(win.canvas.viewport(), QtCore.QEvent(QtCore.QEvent.User))
    assert Espia.vistos == 0
    card.begin("Reconociendo…")
    app.sendEvent(win.canvas.viewport(), QtCore.QEvent(QtCore.QEvent.User))
    assert Espia.vistos == 1
    card.end()
    app.sendEvent(win.canvas.viewport(), QtCore.QEvent(QtCore.QEvent.User))
    assert Espia.vistos == 1


def test_escape_muestra_que_se_esta_cancelando(win, monkeypatch):
    llamadas = []

    class Trabajo:
        def cancel(self):
            llamadas.append(1)

    card = win._recog_busy = ProgresoReconocimiento(win)
    win._recog_worker = Trabajo()
    card.begin("Reconociendo…", cancel=win._cancel_recognition)
    win._cancel_recognition()                            # lo que hace Esc en el lienzo
    assert llamadas == [1]
    assert not card.cancel_button.isEnabled() and card.cancel_button.text() == "Cancelando…"
    card.end()
    win._recog_busy = None


def test_la_tarjeta_se_traduce_al_volver_a_empezar(win, monkeypatch):
    from traduccion import i18n_core
    card = ProgresoReconocimiento(win)
    assert card.note.text() == "Vista provisional"
    monkeypatch.setattr(i18n_core, "_current_lang", "en")
    card.begin("Recognizing…")
    assert card.note.text() == "Provisional preview"
    card.end()


def test_la_tarjeta_va_con_el_texto_arriba_y_el_boton_debajo(win, app):
    image = QtGui.QImage(1800, 1000, QtGui.QImage.Format_RGB32)
    win.canvas.set_image(image)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    card = ProgresoReconocimiento(win)
    card.begin("Reconociendo agua, drenaje, eléctrico, telecom, gas y alcantarillado…", "Hoja 1", cancel=lambda: None)
    QtTest.QTest.qWait(30)
    assert card.isVisible()
    assert card.title.geometry().bottom() < card.cancel_button.geometry().top()
    card.end()


def test_todas_las_utilidades_van_a_un_solo_proceso(app, monkeypatch):
    """Comparten la lectura de la hoja: repartirlas la leía en cada proceso y era más lento (medido 2026-11-02)."""
    from ui.comun import proceso
    from ui.comun.workers import RecognitionWorker
    enviadas = []
    monkeypatch.setattr(proceso, "activo", lambda: True)
    monkeypatch.setattr(proceso, "trabajador", lambda nombre="principal": type(
        "T", (), {"enviar": lambda self, t: enviadas.append((nombre, t))})())
    w = RecognitionWorker("x.pdf", 0, utilities=("AGUA", "DRENAJE", "GAS", "TELECOM"))
    w.start()
    assert [n for n, _t in enviadas] == ["principal"]
    assert enviadas[0][1].kwargs["utilities"] == tuple(w.utilities)
