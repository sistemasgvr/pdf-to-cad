"""«Exportar DXF» más rápido sin cambiar el resultado (pedido del usuario 2026-10-17, proyecto de
16 761 utilidades): el PDF ya digitalizado se REUSA (`exportar/cache_digitalizado`), leer y guardar el
DXF van en otro hilo (`ui/comun/en_hilo`) y la limpieza de tramos diminutos mira solo las utilidades
cercanas (`limpieza_tramos.cajas_de`, ver también `test_limpieza.py`)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
fitz = pytest.importorskip("fitz")
ezdxf = pytest.importorskip("ezdxf")
from PySide6 import QtWidgets  # noqa: E402


def _pdf(path, texto):
    doc = fitz.open()
    pg = doc.new_page(width=600, height=400)
    pg.insert_text((50, 60), texto)
    pg.draw_line((50, 200), (550, 200))
    doc.save(str(path)); doc.close()
    return str(path)


def test_clave_cambia_con_el_pdf_y_las_hojas(tmp_path):
    from exportar import cache_digitalizado as CD
    a, b = _pdf(tmp_path / "a.pdf", "A"), _pdf(tmp_path / "b.pdf", "B")
    assert CD.clave(a, [0]) == CD.clave(a, [0])
    assert CD.clave(a, [0]) != CD.clave(b, [0])
    assert CD.clave(a, [0]) != CD.clave(a, None)


def test_la_cache_guarda_los_mas_recientes(tmp_path, monkeypatch):
    from exportar import cache_digitalizado as CD
    monkeypatch.setattr(CD, "MAX_ARCHIVOS", 2)
    dxf = tmp_path / "base.dxf"
    dxf.write_text("0\nEOF\n")
    for k in ("uno", "dos", "tres"):
        CD.guardar(k, str(dxf))
        os.utime(CD.buscar(k), (os.path.getmtime(CD.buscar(k)) + {"uno": 0, "dos": 1, "tres": 2}[k],) * 2)
    CD._recortar()
    assert CD.buscar("uno") is None and CD.buscar("dos") and CD.buscar("tres")


class _Senal:
    def __init__(self):
        self.fns = []

    def connect(self, fn):
        self.fns.append(fn)

    def emit(self, *a):
        for fn in self.fns:
            fn(*a)


@pytest.fixture
def win(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda *a, **k: None)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


def test_segunda_exportacion_reusa_el_pdf_digitalizado(win, tmp_path, monkeypatch):
    from ui.ventana import app_window
    pdf = _pdf(tmp_path / "plano.pdf", "Plano")
    win._open_pdf_path(pdf)
    win._load_page(0)                                  # la hoja en el editor (sin el asistente)
    creados = []

    class FakeWorker:                                  # «digitaliza»: una línea en el DXF base
        def __init__(self, src, out, pages=None):
            creados.append(src)
            self.out, self.done = out, _Senal()

        def start(self):
            d = ezdxf.new("R2010")
            d.modelspace().add_line((0, 0), (12.5, 7.25), dxfattribs={"layer": "BASE"})
            d.saveas(self.out)
            self.done.emit(self.out, "")
    monkeypatch.setattr(app_window, "PipelineWorker", FakeWorker)
    salidas = iter([tmp_path / "uno.dxf", tmp_path / "dos.dxf", tmp_path / "tres.dxf"])
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (str(next(salidas)), ""))

    def lineas(ruta):
        return sorted((tuple(e.dxf.start), tuple(e.dxf.end)) for e in ezdxf.readfile(str(ruta)).modelspace()
                      if e.dxftype() == "LINE" and e.dxf.layer == "BASE")
    win.run_pipeline("todo")
    assert len(creados) == 1 and lineas(tmp_path / "uno.dxf")
    win.run_pipeline("todo")                           # mismo PDF: no se digitaliza otra vez
    assert len(creados) == 1
    assert lineas(tmp_path / "dos.dxf") == lineas(tmp_path / "uno.dxf")
    assert not os.path.exists(str(tmp_path / "dos.dxf") + ".base.tmp.dxf")
    win._open_pdf_path(_pdf(tmp_path / "otro.pdf", "Plano cambiado"))   # otro PDF: se digitaliza
    win._load_page(0)
    win.run_pipeline("todo")
    assert len(creados) == 2


def test_en_hilo_devuelve_resultado_y_error(win):
    from ui.comun import en_hilo
    assert en_hilo.ejecutar(win, lambda: 41 + 1, "Probando…") == (42, "", False)
    r, err, cancelado = en_hilo.ejecutar(win, lambda: 1 / 0, "Probando…")
    assert r is None and "ZeroDivisionError" in err and not cancelado


# ── Recuadro del plano base (2026-10-19): encuadrar la vista ya no mide el plano base entero en cada
# exportación; el resultado tiene que ser EXACTAMENTE el de medir todo.

def _vista(ruta):
    d = ezdxf.readfile(str(ruta))
    vp = d.viewports.get("*Active")[0]
    return tuple(vp.dxf.center), vp.dxf.height


def _base_con_texto(n=40):
    d = ezdxf.new("R2010")
    msp = d.modelspace()
    for k in range(n):
        msp.add_line((k * 3.1, -k * 0.7), (k * 3.1 + 5, k * 1.3), dxfattribs={"layer": "BASE"})
        msp.add_text(f"T{k}", height=1.7, dxfattribs={"insert": (k * 2.9, 40 + k), "layer": "TEXTO"})
    msp.add_lwpolyline([(0, 0, 0, 0, 0.4), (60, -30), (90, 10)], format="xyseb")
    return d


def test_recuadro_rapido_igual_al_completo_y_cae_al_completo_si_cambia_el_plano_base(win, tmp_path, monkeypatch):
    from ezdxf import bbox
    from exportar import cache_digitalizado as CD
    ruta = tmp_path / "base.dxf"
    _base_con_texto().saveas(ruta)
    CD.guardar("k_base", str(ruta))
    doc = ezdxf.readfile(CD.buscar("k_base"))
    base = win._recuadro_base(doc, "k_base", False)
    assert CD.leer_recuadro("k_base") == base[0]       # quedó guardado, con los mismos números
    doc.modelspace().add_line((-500.25, 3), (7, 900.125))  # lo que agrega la fusión
    rapido, completo = win._recuadro_rapido(doc, base), bbox.extents(doc.modelspace())
    assert tuple(rapido.extmin) == tuple(completo.extmin) and tuple(rapido.extmax) == tuple(completo.extmax)
    doc2 = ezdxf.readfile(CD.buscar("k_base"))           # 2.ª vez: de la caché, sin medir el plano
    base2 = win._recuadro_base(doc2, "k_base", False)
    assert base2[0] == base[0]
    doc2.modelspace().delete_entity(next(iter(doc2.modelspace().query("TEXT"))))   # texto reemplazado
    assert win._recuadro_rapido(doc2, base2) is None     # → se mide todo, como antes
    monkeypatch.setattr(win.georef, "active", lambda: True)
    assert win._recuadro_rapido(doc, base) is None       # con georreferencia el plano base se transforma


def test_segunda_exportacion_misma_vista_que_la_primera(win, tmp_path, monkeypatch):
    from ui.ventana import app_window
    pdf = _pdf(tmp_path / "plano.pdf", "Plano")
    win._open_pdf_path(pdf)
    win._load_page(0)

    class FakeWorker:
        def __init__(self, src, out, pages=None):
            self.out, self.done = out, _Senal()

        def start(self):
            _base_con_texto().saveas(self.out)
            self.done.emit(self.out, "")
    monkeypatch.setattr(app_window, "PipelineWorker", FakeWorker)
    salidas = iter([tmp_path / "uno.dxf", tmp_path / "dos.dxf"])
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (str(next(salidas)), ""))
    medidas = []
    original = app_window.Main._recuadro_rapido

    def contar(self, doc, base):
        r = original(self, doc, base)
        medidas.append(r is not None)
        return r
    monkeypatch.setattr(app_window.Main, "_recuadro_rapido", contar)
    win.run_pipeline("todo")
    win.run_pipeline("todo")
    assert medidas == [True, True]
    assert _vista(tmp_path / "uno.dxf") == _vista(tmp_path / "dos.dxf")
    from ezdxf import bbox                                # = medir todo el modelspace, como antes
    ext = bbox.extents(ezdxf.readfile(str(tmp_path / "dos.dxf")).modelspace())
    h = (ext.extmax.y - ext.extmin.y) or (ext.extmax.x - ext.extmin.x) or 100.0
    centro = ((ext.extmin.x + ext.extmax.x) / 2.0, (ext.extmin.y + ext.extmax.y) / 2.0)
    c, alto = _vista(tmp_path / "dos.dxf")
    cx, cy = c[0], c[1]
    assert (cx, cy) == centro and alto == h * 1.15
    win._set_plan_view(ezdxf.readfile(str(tmp_path / "dos.dxf")))   # sin recuadro guardado: el de siempre


def test_primera_exportacion_usa_el_documento_en_memoria(win, tmp_path, monkeypatch):
    """La 1.ª exportación usa el documento ezdxf que el digitalizador acaba de guardar (2026-10-19: releer
    un plano de 132 MB tardaba ~30 s) y sale el MISMO DXF que releyéndolo; la 2.ª (caché) lo lee."""
    import re
    import digitize
    from ui.ventana import app_window
    Real = app_window.PipelineWorker
    pdf = _pdf(tmp_path / "plano.pdf", "Plano")
    win._open_pdf_path(pdf)
    win._load_page(0)
    win.pipes.append(dict(layer="AGUA", pts=[(10.0, 10.0), (200.0, 120.0)], ab=False, diam=8.0,
                          inv_start=-6.0, inv_end=-6.5, name=""))
    win._rebuild_structures(); win._refresh_lists()

    class Worker:                                      # el de la app, sin hilo
        def __init__(self, src, out, pages=None):
            self.real = Real(src, out, pages=pages)
            self.done = _Senal()

        def tomar_doc(self):
            return self.real.tomar_doc()

        def start(self):
            self.real.done.connect(lambda *a: self.done.emit(*a))
            self.real.run()
    monkeypatch.setattr(app_window, "PipelineWorker", Worker)
    leidos = []
    original = ezdxf.readfile
    monkeypatch.setattr(ezdxf, "readfile", lambda *a, **k: leidos.append(a[0]) or original(*a, **k))
    salidas = iter([tmp_path / "uno.dxf", tmp_path / "dos.dxf"])
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (str(next(salidas)), ""))
    llamadas = []
    main = digitize.main
    monkeypatch.setattr(digitize, "main", lambda *a, **k: llamadas.append(1) or main(*a, **k))
    win.run_pipeline("todo")
    assert len(llamadas) == 1 and not leidos            # digitalizado y usado en memoria: no se releyó
    win.run_pipeline("todo")
    assert len(llamadas) == 1 and len(leidos) == 1      # 2.ª: de la caché, leído del archivo

    def texto(ruta):                                   # sin hora ni GUID de guardado
        s = open(ruta, encoding="utf-8", errors="replace").read()
        s = re.sub(r"\n  1\n\d+\.\d+\.\d+ @ [^\n]*\n", "\n", s)
        return re.sub(r"\n(\$VERSIONGUID|\$FINGERPRINTGUID|\$TDUPDATE|\$TDUUPDATE|\$TDCREATE|\$TDUCREATE|"
                      r"\$TDINDWG)\n *\d+\n[^\n]*\n", "\n", s)
    assert texto(tmp_path / "uno.dxf") == texto(tmp_path / "dos.dxf")


def test_digitalizar_lee_la_hoja_una_vez_y_guarda_el_mismo_dxf(tmp_path, monkeypatch):
    """`digitize.main` lee los trazos de la hoja UNA vez y guarda con `dxf_rapido` (2026-10-19, mapa de
    ~500 mil trazos: 116 → 82 s): el DXF base y los avisos son los mismos que antes."""
    import re
    import digitize
    from exportar import dxf_rapido
    doc = fitz.open()
    pg = doc.new_page(width=900, height=600)
    pg.insert_text((50, 60), "PLANO DE PRUEBA STA 10+00 MATCH LINE", fontsize=11)
    for k in range(120):
        pg.draw_line((40 + k * 6, 100), (40 + k * 6, 500), color=(0, 0, 1) if k % 2 else (1, 0, 0), width=0.6)
    pdf = str(tmp_path / "vector.pdf")
    doc.save(pdf); doc.close()
    lecturas = []
    original = fitz.Page.get_drawings
    monkeypatch.setattr(fitz.Page, "get_drawings", lambda self, *a, **k: lecturas.append(1) or original(self, *a, **k))
    a, b = str(tmp_path / "viejo.dxf"), str(tmp_path / "nuevo.dxf")
    una = digitize._dibujos_una_vez
    monkeypatch.setattr(digitize, "_dibujos_una_vez", lambda page: None)
    avisos_a = digitize.main(pdf, a, verbose=False, pages=[0])
    antes = len(lecturas)
    monkeypatch.setattr(digitize, "_dibujos_una_vez", una)
    lecturas.clear()
    avisos_b = digitize.main(pdf, b, verbose=False, pages=[0], guardar=dxf_rapido.guardar)
    assert antes > 1 and len(lecturas) == 1

    def texto(ruta):
        s = open(ruta, encoding="utf-8", errors="replace").read()
        s = re.sub(r"\n  1\n\d+\.\d+\.\d+ @ [^\n]*\n", "\n", s)
        return re.sub(r"\n(\$VERSIONGUID|\$FINGERPRINTGUID|\$TDUPDATE|\$TDUUPDATE|\$TDCREATE|\$TDUCREATE|"
                      r"\$TDINDWG)\n *\d+\n[^\n]*\n", "\n", s)
    assert texto(a) == texto(b) and avisos_a == avisos_b
