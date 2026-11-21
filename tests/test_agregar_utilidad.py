"""«Agregar utilidad desde otro PDF…»: la utilidad nueva cae sobre la hoja del editor.

Pedido del usuario 2026-10-23: los mapas llegan en un PDF por utilidad (Phoenix: agua,
alcantarillado y drenaje, dos PDF cada una). Con una utilidad ya importada, la siguiente se
agrega a la MISMA hoja: sus hojas se ubican solas por el mapa base que comparten
(`hoja.encaje_mapa_base`), la hoja nueva se arma calcada sobre la del editor
(`hoja.hoja_calcada`) y al importar la hoja del editor pasa a tener las dos utilidades sin
mover nada de lo que ya había (`ui.ventana.ventana_agregar`).

Los PDF son sintéticos: el mismo mapa base (calles + lotes + diagonales) de dos cuadrículas,
dibujado por cada «utilidad» a otra escala, en otro lugar de la hoja, en otro orden de hojas
y una hoja con /Rotate 90 (como los de alcantarillado de Phoenix).
"""
import math
import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")

from hoja import composite as C  # noqa: E402
from hoja import encaje_mapa_base as E  # noqa: E402
from hoja import hoja_calcada as H  # noqa: E402

# utilidad «agua»: 0.6 pt por pie desde (50, 60); «alcantarillado»: 0.65 desde (80, 30)
AGUA = dict(escala=0.6, off=(50.0, 60.0), tam=(700.0, 720.0), color=(0, 0, 1))
CLOACA = dict(escala=0.65, off=(80.0, 30.0), tam=(900.0, 760.0), color=(1, 0, 0))
LADO_FT = 1000.0


def _mapa_base(celda: int):
    """Trazos del mapa base de una cuadrícula (pies): calles, lotes y algunas diagonales."""
    rnd = random.Random(1000 + celda)
    out = []
    for k in range(1, 6):                                  # calles (largas)
        y = k * LADO_FT / 6 + rnd.uniform(-20, 20)
        out.append((0.0, y, LADO_FT, y + rnd.uniform(-3, 3)))
        x = k * LADO_FT / 6 + rnd.uniform(-20, 20)
        out.append((x, 0.0, x + rnd.uniform(-3, 3), LADO_FT))
    for _ in range(140):                                   # lotes (cortos, a lo largo de las calles)
        x, y = rnd.uniform(20, LADO_FT - 80), rnd.uniform(20, LADO_FT - 80)
        if rnd.random() < 0.5:
            out.append((x, y, x + rnd.uniform(35, 70), y))
        else:
            out.append((x, y, x, y + rnd.uniform(35, 70)))
    for _ in range(25):                                    # rumbos cualesquiera
        x, y = rnd.uniform(50, LADO_FT - 150), rnd.uniform(50, LADO_FT - 150)
        a = rnd.uniform(0, math.pi)
        largo = rnd.uniform(60, 140)
        out.append((x, y, x + largo * math.cos(a), y + largo * math.sin(a)))
    return out


def _a_hoja(u, x, y):
    return u["off"][0] + u["escala"] * x, u["off"][1] + u["escala"] * y


# la tubería de cada utilidad, en pies (en las dos cuadrículas)
TUBO = {"agua": [(100.0, 150.0), (900.0, 150.0)], "cloaca": [(120.0, 820.0), (880.0, 840.0)]}


def _pdf(path, u, celdas, tubo, girar=()):
    """Un PDF de una utilidad: una hoja por cuadrícula, con marco, cajetín, mapa base y su
    tubería. `girar` = hojas con /Rotate 90 (lo visible sigue al norte)."""
    doc = fitz.open()
    for i, c in enumerate(celdas):
        pg = doc.new_page(width=u["tam"][0], height=u["tam"][1])
        if i in girar:
            pg.set_rotation(90)
        m = pg.derotation_matrix                           # visible → sin girar

        def p(x, y):
            return fitz.Point(x, y) * m
        sh = pg.new_shape()
        for x0, y0, x1, y1 in _mapa_base(c):
            sh.draw_line(p(*_a_hoja(u, x0, y0)), p(*_a_hoja(u, x1, y1)))
        sh.finish(color=(0.4, 0.4, 0.4), width=0.3)
        W, H = (u["tam"][1], u["tam"][0]) if i in girar else u["tam"]
        sh.draw_rect(fitz.Rect(p(10, 10), p(W - 10, H - 10)))            # marco de la hoja
        sh.draw_rect(fitz.Rect(p(W - 200, H - 80), p(W - 20, H - 20)))   # cajetín
        sh.finish(color=(0, 0, 0), width=1.0)
        a, b = tubo
        sh.draw_line(p(*_a_hoja(u, *a)), p(*_a_hoja(u, *b)))
        sh.finish(color=u["color"], width=2.5)
        sh.commit()
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def pdfs(tmp_path):
    agua = _pdf(tmp_path / "QS Water_Prueba.pdf", AGUA, [0, 1], TUBO["agua"])
    # otra plantilla: hojas en otro orden y la primera girada 90°
    cloaca = _pdf(tmp_path / "QS Sewer_Prueba.pdf", CLOACA, [1, 0], TUBO["cloaca"], girar=(0,))
    return agua, cloaca


def _editor(agua_doc):
    """La hoja del editor como la deja «Componer hoja»: las dos cuadrículas lado a lado."""
    w0 = agua_doc[0].rect
    clip = [AGUA["off"][0] / w0.width, AGUA["off"][1] / w0.height,
            (AGUA["off"][0] + LADO_FT * AGUA["escala"]) / w0.width,
            (AGUA["off"][1] + LADO_FT * AGUA["escala"]) / w0.height]
    s = 1.0 / AGUA["escala"]                                # pies por pt
    lado = LADO_FT * AGUA["escala"]
    return C.Composite([C.Piece(0, 0, clip, x=0.0, y=0.0, src_scale=s, label="QS Water_Prueba.pdf · 1 · 17-10"),
                        C.Piece(0, 1, clip, x=lado, y=0.0, src_scale=s, label="QS Water_Prueba.pdf · 2 · 17-11")],
                       bridges=False)


def _mundo_a_compuesta(comp, celda, docs, x, y):
    """Un punto del terreno (pies) en la hoja compuesta del editor, por la pieza de esa celda."""
    p = comp.pieces[celda]
    page = docs[p.source][p.page]
    return C.piece_map(p, (page.rect.width, page.rect.height), comp.target_scale())(*_a_hoja(AGUA, x, y))


# ─────────────────────────── encaje ───────────────────────────
def test_encaje_halla_la_escala_y_el_lugar_exactos(pdfs):
    agua, cloaca = (fitz.open(p) for p in pdfs)
    A = E.trazos(agua[1])            # celda 1 en agua
    B = E.trazos(cloaca[0])          # celda 1 en alcantarillado (hoja girada /Rotate 90)
    e = E.encajar(B, A)
    assert e is not None and e.votos >= 100 and e.rms < 0.01
    k = AGUA["escala"] / CLOACA["escala"]
    assert e.escala == pytest.approx(k, rel=1e-5)
    assert abs(e.giro_deg) < 1e-6
    for x, y in ((0, 0), (1000, 0), (500, 700)):          # cualquier punto del terreno
        q = e.mapa(*_a_hoja(CLOACA, x, y))
        assert q == pytest.approx(_a_hoja(AGUA, x, y), abs=0.01)


def test_hoja_de_otra_cuadricula_no_encaja(pdfs):
    agua, cloaca = (fitz.open(p) for p in pdfs)
    A = E.trazos(agua[0])            # celda 0
    B = E.trazos(cloaca[0])          # celda 1
    assert E.encajar(B, A) is None
    e = E.encajar(E.trazos(cloaca[1]), A)
    assert e is not None
    assert E.verificar(B, A, e) is None                    # el encaje de la otra hoja no vale aquí
    assert E.verificar(E.trazos(cloaca[1]), A, e).votos >= 100


# ─────────────────────────── hoja calcada ───────────────────────────
def test_hoja_calcada_cae_sobre_la_del_editor(pdfs):
    agua, cloaca = (fitz.open(p) for p in pdfs)
    comp = _editor(agua)
    cal = H.calcar(comp, [agua], [cloaca], ["QS Sewer_Prueba.pdf"])
    assert cal.comp is not None and not cal.sin_pareja
    assert [(u.pieza, u.hoja) for u in cal.ubicaciones] == [(0, 1), (1, 0)]   # por el dibujo, no por el orden
    sizes = lambda p: (cloaca[p.page].rect.width, cloaca[p.page].rect.height)  # noqa: E731
    for celda, p in zip((0, 1), cal.comp.pieces):
        fn = C.piece_map(p, sizes(p), cal.comp.target_scale())
        for x, y in ((200, 300), (950, 50), (500, 999)):
            esperado = _mundo_a_compuesta(comp, celda, [agua], x, y)
            assert fn(*_a_hoja(CLOACA, x, y)) == pytest.approx(esperado, abs=0.02)
    # misma hoja (tamaño y coordenadas) que la del editor
    e_sizes = lambda p: (agua[p.page].rect.width, agua[p.page].rect.height)    # noqa: E731
    assert C.sheet_geometry(cal.comp, sizes) == pytest.approx(C.sheet_geometry(comp, e_sizes))
    assert cal.comp.pieces[0].label.startswith("QS Sewer_Prueba.pdf · 2 · 17-10")


def test_combinar_no_mueve_la_hoja_del_editor(pdfs):
    agua, cloaca = (fitz.open(p) for p in pdfs)
    comp = _editor(agua)
    cal = H.calcar(comp, [agua], [cloaca], ["QS Sewer_Prueba.pdf"])
    e_sizes = lambda p: (agua[p.page].rect.width, agua[p.page].rect.height)    # noqa: E731
    marco = H.marco_de(comp, e_sizes)
    comb = H.combinar(comp, cal.comp, 1, marco)
    assert [p.to_dict() for p in comb.pieces[:2]] == [p.to_dict() for p in comp.pieces]
    assert {p.grupo for p in comb.pieces[2:]} == {1} and {p.source for p in comb.pieces[2:]} == {1}
    docs = [agua, cloaca]
    sizes = lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height)  # noqa: E731
    assert C.sheet_geometry(comb, sizes) == pytest.approx(C.sheet_geometry(comp, e_sizes))
    assert comb.blends()
    # en la hoja armada se ven las DOS tuberías donde dice el terreno
    hoja = C.build_document(comb, docs)[0]
    _w, _h, dx, dy = C.sheet_geometry(comb, sizes)
    pix = hoja.get_pixmap(matrix=fitz.Matrix(2, 2))

    def color(celda, x, y):
        X, Y = _mundo_a_compuesta(comp, celda, docs, x, y)
        return pix.pixel(int((X + dx) * 2), int((Y + dy) * 2))
    for celda in (0, 1):
        r, g, b = color(celda, 500.0, 150.0)                 # tubería de agua: azul
        assert b > 150 and r < 120, (celda, r, g, b)
        r, g, b = color(celda, 500.0, 830.0)                 # alcantarillado: rojo, sobre su mapa
        assert r > 150 and b < 120, (celda, r, g, b)


def test_una_hoja_suelta_del_editor_conserva_sus_coordenadas(pdfs):
    """Editor con una hoja ENTERA (sin materializar): la combinada mide lo mismo y sus
    coordenadas son las de la hoja visible."""
    agua, cloaca = (fitz.open(p) for p in pdfs)
    w = agua[1].rect
    comp = C.Composite([C.Piece(0, 1, [0, 0, 1, 1], src_scale=1 / AGUA["escala"])])
    assert comp.is_single_full_page()
    cal = H.calcar(comp, [agua], [cloaca], ["x.pdf"])
    assert cal.comp is not None and len(cal.comp.pieces) == 1
    sizes = lambda p: (cloaca[p.page].rect.width, cloaca[p.page].rect.height)   # noqa: E731
    W, Hh, dx, dy = C.sheet_geometry(cal.comp, sizes)
    assert (W, Hh) == pytest.approx((w.width, w.height))
    fn = C.piece_map(cal.comp.pieces[0], sizes(cal.comp.pieces[0]), cal.comp.target_scale())
    X, Y = fn(*_a_hoja(CLOACA, 300, 400))
    assert (X + dx, Y + dy) == pytest.approx(_a_hoja(AGUA, 300, 400), abs=0.02)


def test_recolocar_devuelve_cada_pieza_a_su_lugar(pdfs):
    agua, cloaca = (fitz.open(p) for p in pdfs)
    comp = _editor(agua)
    cal = H.calcar(comp, [agua], [cloaca], ["x.pdf"])
    movida = C.Composite.from_dict(cal.comp.to_dict())
    movida.pieces[0].x += 37.0                              # el usuario la corrió en «Componer hoja»
    movida.pieces[1].clip = [0.2, 0.2, 0.5, 0.5]            # …y achicó el área de la otra
    movida.pieces.append(C.Piece(0, 5, [0, 0, 1, 1]))       # …y sumó una hoja que no está
    sizes = lambda p: (cloaca[min(p.page, 1)].rect.width, cloaca[min(p.page, 1)].rect.height)  # noqa: E731
    nuevo, quitadas = H.recolocar(movida, cal.ubicaciones, cal.comp.marco, cal.comp.target_scale(), sizes)
    assert len(quitadas) == 1 and len(nuevo.pieces) == 2
    assert (nuevo.pieces[0].x, nuevo.pieces[0].y) == pytest.approx((cal.comp.pieces[0].x, cal.comp.pieces[0].y))
    fn = C.piece_map(nuevo.pieces[1], sizes(nuevo.pieces[1]), nuevo.target_scale())   # celda 1, área chica
    assert fn(*_a_hoja(CLOACA, 400, 400)) == pytest.approx(_mundo_a_compuesta(comp, 1, [agua], 400, 400), abs=0.02)
    assert nuevo.marco == cal.comp.marco


def test_composicion_sin_marco_ni_grupo_es_la_de_siempre():
    """Las hojas compuestas de siempre: mismo dict (cachés, .digproj) y misma geometría."""
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1]), C.Piece(0, 1, [0, 0, 0.5, 1], x=700)])
    d = comp.to_dict()
    assert "marco" not in d and all("grupo" not in p for p in d["pieces"])
    assert C.Composite.from_dict(d).to_dict() == d
    sizes = lambda p: (600.0, 400.0)                       # noqa: E731
    assert C.sheet_geometry(comp, sizes) == (1000.0 + 72, 400.0 + 72, 36.0, 36.0)
    uno = C.Composite([C.Piece(0, 0, [0, 0, 1, 1])])
    assert uno.is_single_full_page()
    uno.marco = [0.0, 0.0, 600.0, 400.0]
    assert not uno.is_single_full_page()                   # con marco se materializa
    assert C.sheet_geometry(uno, sizes) == (600.0, 400.0, 0.0, 0.0)
    assert C.Composite.from_dict(uno.to_dict()).marco == [0.0, 0.0, 600.0, 400.0]


# ─────────────────────────── en la ventana ───────────────────────────
from PySide6 import QtCore, QtWidgets  # noqa: E402

from reconocimiento import recognition as rec  # noqa: E402


class _Reconocer(QtCore.QObject):
    """Reemplaza a `RecognitionWorker`: devuelve `_Reconocer.lineas` (px del lienzo) al instante."""
    done = QtCore.Signal(object, str)
    progress = QtCore.Signal(int, int, str)
    lineas = []

    def __init__(self, pdf_path, page_index, **kw):
        super().__init__()
        self.page_index = page_index

    def start(self):
        pls = [rec.RecognizedPolyline("Estilo Rojo 2.5 pt", "ALCANTARILLADO", list(pts), "sewer_ungd",
                                      kinds=["end"] + ["bend"] * (len(pts) - 2) + ["end"])
               for pts in _Reconocer.lineas]
        res = rec.RecognitionResult("ALCANTARILLADO", self.page_index, 1 / AGUA["escala"], polylines=pls,
                                    polylines_joined=pls, polylines_raw=pls)
        self.done.emit([res], "")


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app, monkeypatch):
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.No)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def _px(win, celda, x, y):
    """Punto del terreno (pies) → px del lienzo del editor."""
    docs = [fitz.open(stream=e["data"], filetype="pdf") for e in win.src_pdfs[:1]]
    X, Y = _mundo_a_compuesta(win.composite, celda, docs, x, y)
    sizes = lambda p: (docs[0][p.page].rect.width, docs[0][p.page].rect.height)   # noqa: E731
    _w, _h, dx, dy = C.sheet_geometry(win.composite, sizes)
    return (X + dx) * win.zoom, (Y + dy) * win.zoom


def _color(doc, zoom, px):
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(1, 1))
    return pix.pixel(int(px[0] / zoom), int(px[1] / zoom))


def _editor_con_agua(win, agua):
    win._open_pdf_path(agua)
    win.composite = _editor(fitz.open(agua))
    win._apply_composite()
    QtWidgets.QApplication.instance().processEvents()
    win._push()
    win.pipes.append({"layer": "AGUA", "pts": [_px(win, 0, *TUBO["agua"][0]), _px(win, 0, *TUBO["agua"][1])],
                      "diam": 8.0, "name": ""})
    win._refresh_lists(); win._update_ui(); win._redraw()


_px_esperado = [None]


class _Trabajador:
    """Reemplaza al trabajador «reconocer» (▶ del panel): devuelve `_Reconocer.lineas` en la hoja pedida."""

    def __init__(self, vio, win):
        self.vio, self.win, self.tareas = vio, win, []

    def enviar(self, t):
        from PySide6 import QtCore
        self.tareas.append(t)
        ruta, hoja = t.args[0], int(t.args[1])
        with fitz.open(ruta) as doc:                       # la hoja que se reconoce
            self.vio["tam"] = (doc[hoja].rect.width, doc[hoja].rect.height)
            self.vio["rojo"] = _color(doc, self.win.zoom, _px_esperado[0])
        pls = [rec.RecognizedPolyline("Estilo Rojo 2.5 pt", "ALCANTARILLADO", list(pts), "sewer_ungd",
                                      kinds=["end"] + ["bend"] * (len(pts) - 2) + ["end"])
               for pts in _Reconocer.lineas]
        res = [rec.RecognitionResult("ALCANTARILLADO", hoja, 1 / AGUA["escala"], polylines=pls,
                                     polylines_joined=pls, polylines_raw=pls)]
        t._dueno = self
        QtCore.QTimer.singleShot(0, lambda: t._fin(res, ""))
        return t

    def cancelar(self, t):
        t._fin(None, "cancelado")


def componer_ubicadas(parent, sources, comp, hidden, **kw):
    """«Componer hoja» al agregar una utilidad (2026-11-18): el usuario espera la búsqueda y pulsa «Marcar las N»."""
    b = kw["agregar"]
    b.esperar()
    piezas = [C.Piece.from_dict(d) for k in b.ubicadas() for d in b.piezas[k]]
    return (C.Composite(piezas, scale_ft_per_pt=b.escala), sources, hidden) if piezas else None


def _stubs(monkeypatch, win, cloaca, vista_previa):
    """«Agregar utilidad» con el flujo desde el editor (plan 2026-11-16, Tarea 9): «Componer hoja» acepta las
    hojas ubicadas, la hoja calcada queda «interpretada» (fila ALCANTARILLADO pendiente; la interpretación tiene sus
    pruebas en `test_flujo_abrir_interpretar`) y, con `vista_previa` == "import", el usuario pulsa su ▶."""
    from ui.comun import proceso
    from ui.ventana import app_window
    vio = {}
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileNames", lambda *a, **k: ([cloaca], ""))
    falso = _Trabajador(vio, win)
    real = proceso.trabajador
    monkeypatch.setattr(proceso, "trabajador",
                        lambda nombre="principal": falso if nombre == proceso.RETENEDOR else real(nombre))

    def interpretar():
        e = win._rec_estado()
        e.filas["ALCANTARILLADO"].estado = "pendiente"
        e.filas["ALCANTARILLADO"].motivo = None
        if vista_previa != "import":
            return
        win.reconocer_parte("ALCANTARILLADO")
        app = QtWidgets.QApplication.instance()
        for _ in range(200):
            if win._rec_actual is None:
                break
            app.processEvents()
        assert win._rec_actual is None
    monkeypatch.setattr(win, "_interpretar_hoja", interpretar)

    def componer(parent, sources, comp, hidden, **kw):
        # «Componer hoja» (2026-11-18: se abre al instante, sin nada elegido; la búsqueda corre aparte): el
        # usuario espera la tarjeta y pulsa «Marcar las N» (las piezas calcadas, en su lugar)
        b = kw["agregar"]
        vio["al_abrir"] = (comp.to_dict() if comp is not None else None, b.terminada)
        b.esperar()
        piezas = [C.Piece.from_dict(d) for k in b.ubicadas() for d in b.piezas[k]]
        vio["componer"] = [(p.source, p.page) for p in piezas]
        if vista_previa == "componer" or not piezas:
            return None
        if vista_previa == "enteras":                     # marcó las hojas enteras antes de que se ubicaran
            piezas = [C.Piece(s, h, [0.0, 0.0, 1.0, 1.0]) for s, h in dict.fromkeys(vio["componer"])]
        return C.Composite(piezas, scale_ft_per_pt=b.escala), sources, hidden
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", componer)
    vio["trabajador"] = falso
    return vio


def test_agregar_utilidad_queda_sobre_la_hoja_del_editor(win, pdfs, monkeypatch):
    agua, cloaca = pdfs
    _editor_con_agua(win, agua)
    antes = dict(pipes=[dict(p) for p in win.pipes], tam=win.canvas.tam_hoja(), undo=len(win._undo),
                 hoja=(win.doc[0].rect.width, win.doc[0].rect.height))
    tubo = [_px(win, 0, *TUBO["cloaca"][0]), _px(win, 0, *TUBO["cloaca"][1])]
    _px_esperado[0] = ((tubo[0][0] + tubo[1][0]) / 2, (tubo[0][1] + tubo[1][1]) / 2)
    _Reconocer.lineas = [tubo]
    vio = _stubs(monkeypatch, win, cloaca, "import")
    win.agregar_utilidad()
    assert vio["al_abrir"][0] is None                      # el compositor abre sin nada elegido, sin esperar
    # la hoja reconocida era la del alcantarillado, del tamaño de la del editor y su tubería en su lugar
    assert vio["tam"] == pytest.approx(antes["hoja"])
    r, _g, b = vio["rojo"]
    assert r > 150 and b < 120
    assert [t.args[0] for t in vio["trabajador"].tareas] == [win._rec_hoja["ruta"]]   # la hoja calcada
    # el editor: lo de antes intacto + lo nuevo encima, en la hoja con las dos utilidades
    assert win.pipes[0] == antes["pipes"][0]
    assert [p["layer"] for p in win.pipes] == ["AGUA", "ALCANTARILLADO"]
    assert win.pipes[1]["pts"] == pytest.approx([tuple(p) for p in tubo])
    assert "QS Sewer_Prueba.pdf" in str(win.pipes[1].get("xdata"))
    assert win.canvas.tam_hoja() == pytest.approx(antes["tam"])
    assert [e["name"] for e in win.src_pdfs] == ["QS Water_Prueba.pdf", "QS Sewer_Prueba.pdf"]
    assert [(p.source, p.grupo) for p in win.composite.pieces] == [(0, 0), (0, 0), (1, 1), (1, 1)]
    r, _g, b = _color(win.doc, win.zoom, _px_esperado[0])
    assert r > 150 and b < 120                             # el fondo ya tiene el alcantarillado…
    agua_px = _px(win, 0, 500.0, TUBO["agua"][0][1])
    r, _g, b = _color(win.doc, win.zoom, agua_px)
    assert b > 150 and r < 120                             # …y sigue teniendo el agua
    assert win._agregando is None and win._respaldo is None and win._dirty
    assert len(win._undo) == antes["undo"] + 1
    win.undo()                                             # deshacer quita lo importado
    assert [p["layer"] for p in win.pipes] == ["AGUA"]


def test_cancelar_deja_el_editor_como_estaba(win, pdfs, monkeypatch):
    agua, cloaca = pdfs
    _editor_con_agua(win, agua)
    pm = win.canvas.pixmap_item.pixmap()
    antes = dict(pipes=[dict(p) for p in win.pipes], doc=win.doc, comp=win.composite.to_dict(),
                 fuentes=[e["name"] for e in win.src_pdfs], imagen=pm.cacheKey(), undo=len(win._undo))
    tubo = [_px(win, 0, *TUBO["cloaca"][0]), _px(win, 0, *TUBO["cloaca"][1])]
    _px_esperado[0] = tubo[0]
    _Reconocer.lineas = [tubo]
    _stubs(monkeypatch, win, cloaca, "componer")         # Cancelar en «Componer hoja»
    win.agregar_utilidad()
    assert win.pipes == antes["pipes"] and win.doc is antes["doc"]
    assert win.composite.to_dict() == antes["comp"]
    assert [e["name"] for e in win.src_pdfs] == antes["fuentes"]
    assert win.canvas.pixmap_item.pixmap().cacheKey() == antes["imagen"]
    assert len(win._undo) == antes["undo"] and win._agregando is None and win._respaldo is None


def test_pdf_que_no_coincide_no_toca_el_editor(win, pdfs, tmp_path, monkeypatch):
    agua, _cloaca = pdfs
    _editor_con_agua(win, agua)
    otro = fitz.open()
    pg = otro.new_page(width=600, height=400)
    pg.draw_line((50, 50), (550, 350))
    otro.save(str(tmp_path / "otro.pdf"))
    antes = (win.doc, win.composite.to_dict(), [dict(p) for p in win.pipes])
    _stubs(monkeypatch, win, str(tmp_path / "otro.pdf"), "import")
    win.agregar_utilidad()
    assert (win.doc, win.composite.to_dict(), win.pipes) == (antes[0], antes[1], antes[2])
    assert win._agregando is None and win._respaldo is None


def test_proyecto_con_la_utilidad_agregada_se_guarda_y_se_reabre(win, pdfs, monkeypatch, tmp_path, app):
    agua, cloaca = pdfs
    _editor_con_agua(win, agua)
    tubo = [_px(win, 0, *TUBO["cloaca"][0]), _px(win, 0, *TUBO["cloaca"][1])]
    _px_esperado[0] = tubo[0]
    _Reconocer.lineas = [tubo]
    _stubs(monkeypatch, win, cloaca, "import")
    win.agregar_utilidad()
    ruta = tmp_path / "dos utilidades.digproj"
    win._write_project(str(ruta))
    from ui.ventana import app_window
    w2 = app_window.Main()
    try:
        w2._open_project_path(str(ruta))
        assert w2.composite.to_dict() == win.composite.to_dict()          # marco y grupos incluidos
        assert [e["name"] for e in w2.src_pdfs] == ["QS Water_Prueba.pdf", "QS Sewer_Prueba.pdf"]
        assert [p["layer"] for p in w2.pipes] == ["AGUA", "ALCANTARILLADO"]
        assert [tuple(q) for q in w2.pipes[1]["pts"]] == pytest.approx([tuple(q) for q in win.pipes[1]["pts"]])
        assert w2.canvas.tam_hoja() == pytest.approx(win.canvas.tam_hoja())
    finally:
        w2._dirty = False
        w2.close()
        app.processEvents()


def test_hoja_combinada_que_crece_deja_su_marco():
    comp = C.Composite([C.Piece(0, 0, [0, 0, 1, 1])], marco=[-36.0, -36.0, 636.0, 436.0])
    sizes = lambda p: (600.0, 400.0)                       # noqa: E731
    assert C.cabe_en_marco(comp, sizes)
    comp.pieces.append(C.Piece(0, 1, [0, 0, 1, 1], x=650.0))
    assert not C.cabe_en_marco(comp, sizes)


def test_el_plano_anterior_conserva_su_panel_reconocer(win, pdfs, monkeypatch):
    """Reporte 2026-11-17: tras agregar una utilidad, el panel «Reconocer» solo tenía las filas de la hoja agregada.
    Cada plano conserva su estado; el selector del panel cambia de uno a otro (cada uno en SU hoja)."""
    from nucleo import reconocer_estado as RE
    import project_io
    agua, cloaca = pdfs
    _editor_con_agua(win, agua)
    win.reconocer_estado = RE.nuevo()
    win.reconocer_estado.firma_hoja = "firma-del-agua"
    win.reconocer_estado.filas["AGUA"].estado = "reconocida"
    win._interpretacion = {"layers": [], "marca": "agua"}
    tubo = [_px(win, 0, *TUBO["cloaca"][0]), _px(win, 0, *TUBO["cloaca"][1])]
    _px_esperado[0] = tubo[0]
    _Reconocer.lineas = [tubo]
    _stubs(monkeypatch, win, cloaca, "import")
    win.agregar_utilidad()
    assert [g for g, _n in win.rec_planos()] == [0, 1] and win._rec_grupo() == 1
    assert win.reconocer_estado.filas["ALCANTARILLADO"].estado == "reconocida"
    assert win.reconocer_estado.filas["AGUA"].estado != "reconocida"
    assert win.panel_reconocer.caja_plano.isVisibleTo(win.panel_reconocer)
    leidas = []
    monkeypatch.setattr(win, "_interpretar_hoja", lambda: leidas.append(win._rec_grupo()))
    win.rec_cambiar_plano(0)                                # el agua, como estaba: sin volver a interpretar
    assert win._rec_grupo() == 0 and leidas == []
    assert win.reconocer_estado.filas["AGUA"].estado == "reconocida"
    assert win._interpretacion["marca"] == "agua"
    assert win._rec_hoja["firma"] == "firma-del-agua" and win._firma_hoja_actual() == "firma-del-agua"
    # el proyecto guarda los dos planos
    rec = project_io.reconocer_de_model({"reconocer": project_io.reconocer_a_dict(win)}, win.pipes)
    assert rec["planos"][1]["estado"].filas["ALCANTARILLADO"].estado == "reconocida"
    win.rec_cambiar_plano(1)                                # y de vuelta el alcantarillado
    assert win._rec_grupo() == 1
    assert win.reconocer_estado.filas["ALCANTARILLADO"].estado == "reconocida"
    assert win._rec_planos[0]["estado"].filas["AGUA"].estado == "reconocida"


# ───────── 2026-11-18: compositor al instante, búsqueda de fondo, una capa del mapa base ─────────
def test_busqueda_con_dos_planos_usa_una_sola_capa(pdfs):
    """Con una utilidad ya agregada la hoja trae un plano por grupo, uno ENCIMA del otro: se busca con uno."""
    agua, cloaca = pdfs
    da, dc = fitz.open(agua), fitz.open(cloaca)
    ed = _editor(da)
    cal = H.calcar(ed, [da], [dc], ["QS Sewer_Prueba.pdf"])
    tam = lambda p: (da[p.page].rect.width, da[p.page].rect.height)   # noqa: E731
    comb = H.combinar(ed, cal.comp, 1, H.marco_de(ed, tam))
    docs = [da, dc]
    sizes = lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height)   # noqa: E731
    assert H.referencia(comb, sizes, comb.target_scale()) == [0, 1]       # solo el plano 0
    # y calcar sobre la hoja de dos planos da lo mismo que sobre la del editor sola
    otra = H.calcar(comb, docs, [dc], ["QS Sewer_Prueba.pdf"])
    assert [(u.fuente, u.hoja) for u in otra.ubicaciones] == [(u.fuente, u.hoja) for u in cal.ubicaciones]
    for a, b in zip(otra.comp.pieces, cal.comp.pieces):
        assert (a.source, a.page) == (b.source, b.page) and a.clip == pytest.approx(b.clip)


def test_calcar_solo_las_hojas_pedidas_y_avisa_cada_una(pdfs):
    agua, cloaca = pdfs
    da, dc = fitz.open(agua), fitz.open(cloaca)
    vistas = []
    cal = H.calcar(_editor(da), [da], [dc], ["QS Sewer_Prueba.pdf"], solo=[(0, 1)],
                   al_ubicar=lambda f, h, q, m: vistas.append((f, h, q.page)))
    assert {(u.fuente, u.hoja) for u in cal.ubicaciones} == {(0, 1)}
    assert vistas == [(0, 1, 1)]


def test_marco_hojas_enteras_antes_de_que_se_ubiquen(win, pdfs, monkeypatch):
    """El usuario marca hojas en el compositor antes de que la búsqueda de fondo las ubique: al continuar se
    ubican AHORA (solo esas) y entra su área calcada, no la hoja entera con su cajetín."""
    from ui.ventana import agregar_busqueda, app_window
    agua, cloaca = pdfs
    _editor_con_agua(win, agua)
    tubo = [_px(win, 0, *TUBO["cloaca"][0]), _px(win, 0, *TUBO["cloaca"][1])]
    _px_esperado[0] = tubo[0]
    _Reconocer.lineas = [tubo]
    vio = _stubs(monkeypatch, win, cloaca, "import")
    monkeypatch.setattr(agregar_busqueda.BusquedaAgregar, "iniciar", lambda self: None)   # aún no encontró nada

    def componer(parent, sources, comp, hidden, **kw):
        vio["busqueda"] = kw["agregar"]
        return C.Composite([C.Piece(0, 1, [0.0, 0.0, 1.0, 1.0])]), sources, hidden    # solo la hoja 2, entera
    monkeypatch.setattr(app_window.composite_dialog, "compose_sheet", componer)
    win.agregar_utilidad()
    nuevas = [p for p in win.composite.pieces if p.grupo == 1]
    assert [(p.source, p.page) for p in nuevas] == [(1, 1)]               # la hoja 2 del alcantarillado
    assert nuevas[0].clip != [0.0, 0.0, 1.0, 1.0]                          # su área calcada
    assert list(vio["busqueda"].m) == [(0, 1)]                            # se buscó solo esa
    assert [p["layer"] for p in win.pipes] == ["AGUA", "ALCANTARILLADO"]


def test_compositor_dice_donde_cae_cada_hoja_y_marca_las_ubicadas(app, pdfs):
    from ui.asistente.composite_dialog import CompositeDialog
    from ui.ventana.agregar_busqueda import BusquedaAgregar
    agua, cloaca = pdfs
    da = fitz.open(agua)
    ed = _editor(da)
    nuevas = [{"name": "QS Sewer_Prueba.pdf", "data": open(cloaca, "rb").read(), "path": cloaca}]
    b = BusquedaAgregar(ed.to_dict(), [open(agua, "rb").read()], nuevas, 1.0 / AGUA["escala"], ["QS Water_Prueba.pdf"])
    b.iniciar()
    dlg = CompositeDialog(None, nuevas, None, {}, 0, sugerencia=False, agregar=b)
    try:
        assert not dlg.comp.pieces
        assert dlg.agr_card.isVisibleTo(dlg)
        assert b.esperar()
        app.processEvents()
        textos = [dlg.lst_pages.item(i).text() for i in range(dlg.lst_pages.count())]
        assert all("Cae en la hoja del editor" in t for t in textos)
        assert dlg.btn_agr_marcar.isVisibleTo(dlg) and "2" in dlg.btn_agr_marcar.text()
        dlg.btn_agr_marcar.click()
        assert sorted((p.source, p.page) for p in dlg.comp.pieces) == [(0, 0), (0, 1)]
        assert sorted(p.to_dict()["clip"] for p in dlg.comp.pieces) == sorted(
            d["clip"] for v in b.piezas.values() for d in v)
        assert not dlg.btn_agr_marcar.isVisibleTo(dlg)
    finally:
        dlg.close_docs()
        dlg.deleteLater()


def test_agregar_utilidad_exige_reconocer_todo_antes():
    """2026-11-21: agregar sobre una hoja a medio reconocer daba errores; se exige reconocer todo primero."""
    from nucleo import reconocer_estado as RE
    assert RE.faltan_para_agregar(None) == []
    e = RE.nuevo()
    for p in RE.PARTES:
        e.filas[p].estado = "bloqueada"
    assert RE.faltan_para_agregar(e) == []
    e.filas["AGUA"].estado = "pendiente"
    e.filas["ROTULOS"].estado = "desactualizada"
    assert RE.faltan_para_agregar(e) == ["AGUA", "ROTULOS"]
    e.filas["AGUA"].estado = e.filas["ROTULOS"].estado = "reconocida"
    assert RE.faltan_para_agregar(e) == []
