"""«Agregar utilidad»: ubicar las hojas por imagen más rápido, con el MISMO resultado (2026-11-21).

Reporte (vigilante del usuario): agregar SD North + South sobre agua + alcantarillado tardaba ~2 min, casi todo
en `calcado_completar._por_imagen` (dibujar cada hoja y correlacionarla con la hoja del editor). Tres cambios, cada
uno comparado aquí con el camino de antes:
  · la transformada de la zona del editor se hace una vez por tamaño (`encaje_imagen.Espectros`);
  · la lista de dibujo de cada hoja del editor se arma una vez (`Lienzo._lista`; `get_pixmap` armaba una por dibujo);
  · cuando la escala y la referencia ya no cambian, las hojas que faltan se ubican en otros procesos y se toman en
    orden (`encaje_imagen_lote`).
"""
import random

import numpy as np
import pytest

fitz = pytest.importorskip("fitz")
pytest.importorskip("cv2")

from hoja import calcado_completar as CC  # noqa: E402
from hoja import composite as C  # noqa: E402
from hoja import encaje_imagen as EI  # noqa: E402
from hoja import encaje_imagen_lote as LOTE  # noqa: E402
from hoja import hoja_calcada as H  # noqa: E402
from test_agregar_utilidad import AGUA, LADO_FT, _mapa_base, TUBO  # noqa: E402


# ─────────────────────────── piezas sueltas ───────────────────────────
def test_espectro_reusado_da_la_misma_correlacion():
    rnd = np.random.default_rng(3)
    A = (rnd.random((157, 233)) - 0.5).astype(np.float32)
    esp = EI.Espectros(A)
    for forma in ((90, 120), (91, 121), (92, 119), (90, 120), (60, 200)):
        B = (rnd.random(forma) - 0.5).astype(np.float32)
        assert np.array_equal(EI._corr(A, B), EI._corr(A, B, esp))


def _hoja_con_tinta(tmp_path):
    doc = fitz.open()
    pg = doc.new_page(width=600, height=500)
    sh = pg.new_shape()
    rnd = random.Random(5)
    for _ in range(300):
        x, y = rnd.uniform(10, 580), rnd.uniform(10, 480)
        sh.draw_line((x, y), (x + rnd.uniform(-60, 60), y + rnd.uniform(-60, 60)))
    sh.finish(color=(0.2, 0.2, 0.2), width=0.4)
    sh.commit()
    pg.insert_text((50, 60), "17-10 LOTES", fontsize=14)
    img = np.random.default_rng(1).integers(0, 255, (40, 80), dtype=np.uint8)
    pix = fitz.Pixmap(fitz.csGRAY, 80, 40, img.tobytes(), False)
    pg.insert_image(fitz.Rect(300, 300, 460, 380), pixmap=pix)
    ruta = tmp_path / "tinta.pdf"
    doc.save(str(ruta))
    return fitz.open(str(ruta))


def test_tinta_con_la_lista_de_dibujo_da_los_mismos_pixeles(tmp_path):
    doc = _hoja_con_tinta(tmp_path)
    pg = doc[0]
    dl = pg.get_displaylist(annots=True)
    for zoom, clip in ((0.25, None), (0.53, fitz.Rect(12.3, 40.7, 333.1, 410.9)), (1.7, fitz.Rect(250, 280, 470.5, 399)),
                       (0.9, fitz.Rect(0.1, 0.2, 599.9, 499.7))):
        assert np.array_equal(EI.tinta(pg, zoom, clip), EI.tinta(pg, zoom, clip, dl))


def test_lienzo_con_y_sin_listas_guardadas_dibuja_lo_mismo(tmp_path, monkeypatch):
    doc = _hoja_con_tinta(tmp_path)
    piezas = [(doc[0], fitz.Rect(0, 0, 300, 250), (0.0, 0.0, 150.0, 125.0)),
              (doc[0], fitz.Rect(300, 250, 600, 500), (150.0, 0.0, 300.0, 125.0)),
              (doc[0], fitz.Rect(100, 100, 400, 350), (0.0, 125.0, 150.0, 250.0))]
    zonas = [(0, 0, 300, 250), (20.5, 33.3, 260.1, 200.7), (140, 100, 160, 140), (-50, -50, 90, 400)]
    monkeypatch.setattr(EI, "LISTAS_MAX", 2)          # (también cuando suelta las más viejas)
    con = EI.Lienzo(piezas)
    monkeypatch.setattr(EI, "LISTAS_MAX", 0)
    sin = EI.Lienzo(piezas)
    assert np.array_equal(con.img, sin.img) and not sin._listas
    for r in (1.0, 2.0, 6.0):
        for z in zonas:
            monkeypatch.setattr(EI, "LISTAS_MAX", 2)
            a = con.dibujar(r, z)
            monkeypatch.setattr(EI, "LISTAS_MAX", 0)
            assert np.array_equal(a, sin.dibujar(r, z))
    assert len(con._listas) <= 2


# ─────────────────────────── el calcado entero, en procesos y de a una ───────────────────────────
def _mundo(n):
    out = []
    for c in range(n):
        out += [(x0 + c * LADO_FT, y0, x1 + c * LADO_FT, y1) for x0, y0, x1, y1 in _mapa_base(c)]
    return out


def _agua(path, n):
    """El PDF del editor: una hoja por celda (como `test_agregar_utilidad._pdf`, sin girar)."""
    doc = fitz.open()
    for c in range(n):
        pg = doc.new_page(width=AGUA["tam"][0], height=AGUA["tam"][1])
        sh = pg.new_shape()
        for x0, y0, x1, y1 in _mapa_base(c):
            sh.draw_line((AGUA["off"][0] + AGUA["escala"] * x0, AGUA["off"][1] + AGUA["escala"] * y0),
                         (AGUA["off"][0] + AGUA["escala"] * x1, AGUA["off"][1] + AGUA["escala"] * y1))
        sh.finish(color=(0.4, 0.4, 0.4), width=0.3)
        (a, b) = TUBO["agua"]
        sh.draw_line((AGUA["off"][0] + AGUA["escala"] * a[0], AGUA["off"][1] + AGUA["escala"] * a[1]),
                     (AGUA["off"][0] + AGUA["escala"] * b[0], AGUA["off"][1] + AGUA["escala"] * b[1]))
        sh.finish(color=(0, 0, 1), width=2.5)
        sh.commit()
    doc.save(str(path))
    return fitz.open(str(path))


def _sd(path, n, celdas: bool, escala=0.8, off=(40.0, 40.0), tam=(900.0, 900.0)):
    """El PDF «drenaje»: una hoja por celda, a otra escala y con cada trazo partido en otro punto (ningún trazo
    idéntico: va por imagen). Con `celdas`, cada hoja dice la suya («Q17-1n», como los cuartos de sección)."""
    rnd = random.Random(7)
    mundo = _mundo(n)
    doc = fitz.open()
    for c in (list(range(n))[1:] + [0]):              # (otro orden de hojas)
        wx0, wx1 = c * LADO_FT, (c + 1) * LADO_FT
        pg = doc.new_page(width=tam[0], height=tam[1])
        sh = pg.new_shape()

        def p(x, y):
            return fitz.Point(off[0] + escala * (x - wx0), off[1] + escala * y)
        for x0, y0, x1, y1 in mundo:
            if not (wx0 <= min(x0, x1) and max(x0, x1) <= wx1):
                continue
            k = rnd.uniform(0.3, 0.7)
            xm, ym = x0 + k * (x1 - x0), y0 + k * (y1 - y0)
            sh.draw_line(p(x0, y0), p(xm, ym))
            sh.draw_line(p(xm, ym), p(x1, y1))
        sh.finish(color=(0, 0, 0), width=0.5)
        sh.draw_rect(fitz.Rect(5, 5, tam[0] - 5, tam[1] - 5))
        sh.finish(color=(0, 0, 0), width=0.5)
        sh.commit()
        if celdas:
            pg.insert_text((tam[0] - 150, tam[1] - 15), "Q17-%d" % (10 + c), fontsize=11)
    doc.save(str(path))
    return fitz.open(str(path))


def _editor(agua, n, con_celda: bool):
    w0 = agua[0].rect
    clip = [AGUA["off"][0] / w0.width, AGUA["off"][1] / w0.height,
            (AGUA["off"][0] + LADO_FT * AGUA["escala"]) / w0.width,
            (AGUA["off"][1] + LADO_FT * AGUA["escala"]) / w0.height]
    lado = LADO_FT * AGUA["escala"]
    piezas = [C.Piece(0, c, clip, x=c * lado, y=0.0, src_scale=1.0 / AGUA["escala"],
                      label=("agua.pdf · %d · 17-%d" % (c + 1, 10 + c)) if con_celda else "agua.pdf · %d" % (c + 1))
              for c in range(n)]
    return C.Composite(piezas, bridges=False)


def _foto(cal):
    return (cal.comp.to_dict() if cal.comp else None, [u.to_dict() for u in cal.ubicaciones], list(cal.sin_pareja))


def _calcar_dos_veces(monkeypatch, editor, agua, sd):
    enviados = []
    original = LOTE.Lote._enviar

    def contar(self, fn, *a):
        enviados.append(fn.__name__)
        return original(self, fn, *a)
    monkeypatch.setattr(LOTE.Lote, "_enviar", contar)
    monkeypatch.setattr(LOTE, "MIN_HOJAS", 2)
    import ui.comun.proceso_hijo as PH
    monkeypatch.setattr(PH, "paralelos", lambda n, mb=0, maximo=4: 2)
    en_procesos = H.calcar(editor, [agua], [sd], ["sd.pdf"])
    monkeypatch.setattr(LOTE, "PARALELO", False)
    de_a_una = H.calcar(editor, [agua], [sd], ["sd.pdf"])
    return en_procesos, de_a_una, enviados


@pytest.mark.parametrize("celdas", [False, True])
def test_hojas_por_imagen_en_procesos_igual_que_de_a_una(tmp_path, monkeypatch, celdas):
    n = 4
    agua = _agua(tmp_path / "agua.pdf", n)
    sd = _sd(tmp_path / "sd.pdf", n, celdas)
    editor = _editor(agua, n, celdas)
    a, b, enviados = _calcar_dos_veces(monkeypatch, editor, agua, sd)
    fa, fb = _foto(a), _foto(b)
    assert fb[0] is not None and len(fb[1]) >= 3          # (la 1.ª se busca aquí; las demás en los procesos)
    assert fa == fb
    assert "_ubicar" in enviados                           # (de verdad se repartió)
    if celdas:
        assert "_celda" in enviados


def test_si_el_grupo_no_recibe_encargos_lo_calcula_aqui_igual(tmp_path, monkeypatch):
    n = 4
    agua = _agua(tmp_path / "agua.pdf", n)
    sd = _sd(tmp_path / "sd.pdf", n, True)
    editor = _editor(agua, n, True)
    monkeypatch.setattr(LOTE.Lote, "_enviar", lambda self, fn, *a: None)
    monkeypatch.setattr(LOTE, "MIN_HOJAS", 2)
    import ui.comun.proceso_hijo as PH
    monkeypatch.setattr(PH, "paralelos", lambda n, mb=0, maximo=4: 2)
    a = H.calcar(editor, [agua], [sd], ["sd.pdf"])
    monkeypatch.setattr(LOTE, "PARALELO", False)
    b = H.calcar(editor, [agua], [sd], ["sd.pdf"])
    fa, fb = _foto(a), _foto(b)
    assert fa == fb and fb[0] is not None


def test_sin_bytes_del_pdf_no_hay_lote(tmp_path):
    agua = _agua(tmp_path / "agua.pdf", 2)
    en_memoria = fitz.open()
    en_memoria.new_page()
    datos = open(tmp_path / "agua.pdf", "rb").read()
    assert LOTE.bytes_de(agua) == datos                                   # (abierto de un archivo)
    assert LOTE.bytes_de(fitz.open(stream=datos, filetype="pdf")) == datos   # (abierto de sus bytes: la app)
    assert LOTE.bytes_de(en_memoria) is None                              # (armado en memoria: de a una, aquí)
