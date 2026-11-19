"""Bandas «en caja» pegadas → una línea por banda; trocitos finos (contorno de una rejilla) fuera (2026-11-19)."""
import os
import sys

import cv2
import numpy as np

sys.path[:0] = [os.path.join(os.path.dirname(__file__), "..", "app")]

from hoja import imagen_grosores as IG  # noqa: E402
from hoja import imagen_trazos as IT  # noqa: E402


def _bandas_a_cuadros(n_bandas=3, ancho=13, bloque=20, y0=100, x0=40, x1=400):
    """`n_bandas` horizontales pegadas: a cuadros (bloque, hueco, bloque…) desfasados como un tablero, con un
    contorno de 1 px (a puntos en la máscara, como en la imagen) que las une (Phoenix SD «60" RCP» junto a «30" RGRCP»: entre dos bandas, la raya de 1 px
    del contorno; los bloques de una no tocan los de la otra)."""
    m = np.zeros((300, 460), np.uint8)
    for b in range(n_bandas):
        ya, yb = y0 + b * (ancho + 1), y0 + b * (ancho + 1) + ancho
        m[ya, x0:x1:2] = 1                                     # contorno: antialias, en la máscara a puntos
        m[yb, x0 + 1:x1:2] = 1
        for a in range(x0 + (b % 2) * bloque, x1, 2 * bloque):
            m[ya + 1:yb, a:min(a + bloque, x1)] = 1
    m[y0:y0 + n_bandas * (ancho + 1), x0] = 1
    return m.astype(bool)


def test_bandas_pegadas_son_una_linea_recta_por_banda():
    p = IT.trazos(_bandas_a_cuadros(), 4.0)
    assert len(p.lineas) == 3
    ys = sorted(np.mean([v[1] for v in l]) for l in p.lineas)
    for y, esperado in zip(ys, (106.5, 120.5, 134.5)):
        assert abs(y - esperado) <= 1.0
    for l in p.lineas:
        assert max(v[1] for v in l) - min(v[1] for v in l) <= 1.0       # rectas
        assert l[0][0] < 70 and l[-1][0] > 370 or l[-1][0] < 70 and l[0][0] > 370


def test_una_banda_a_cuadros_sola_no_cambia():
    m = _bandas_a_cuadros(n_bandas=1)
    antes = IT.trazos(m, 4.0)
    assert all(len(l) >= 2 for l in antes.lineas)
    # la banda sola no pasa por `imagen_bandas`
    from hoja import imagen_bandas as B
    assert B.bandas(m, 4.0) == ([], None)


def test_trocitos_finos_sueltos_fuera_los_guiones_finos_quedan():
    red = [([(0, 0), (200, 0)], 3.3), ([(0, 50), (0, 250)], 3.3)]
    contorno_rejilla = [([(30, 10), (30, 19)], 0.25), ([(37, 10), (37, 19)], 0.25),
                        # SD North h.4: un lado en dos trozos, el primero con la punta torcida 12°
                        ([(80.4, 11.6), (80.4, 15.1), (81.7, 17.5)], 0.48), ([(81.7, 17.5), (80.2, 20.5)], 0.48),
                        ([(87.1, 11.4), (87.2, 16.3), (87.1, 20.3)], 0.48)]
    guiones = [([(100 + 8 * k, 80), (105 + 8 * k, 80)], 0.25) for k in range(4)]
    paredes = [([(60, 100), (60, 118)], 0.25), ([(61.8, 100), (61.8, 118)], 0.25)]   # tubería chica: dos paredes
    suelto = [([(150, 150), (159, 150)], 0.25)]
    out = IG.sin_trocitos_finos(red + contorno_rejilla + guiones + paredes + suelto)
    colita = [contorno_rejilla[3]]          # (3 pt casi en diagonal: la quita después el enderezado, por trocito)
    assert out == red + colita + guiones + paredes + suelto
    assert IG.sin_trocitos_finos(red) == red


def test_ejes_de_una_hoja_se_guardan_en_disco_y_se_leen_iguales(tmp_path, monkeypatch):
    import fitz
    from hoja import imagen_compuesta as IC
    monkeypatch.setenv("PDFCAD_CACHE_EJES_IMAGEN", str(tmp_path / "ejes"))
    trazos = [{"layer": 'PDF_STYLE:["img","line",[0,77,168]]', "rect": fitz.Rect(0, 0, 10, 2), "width": 3.3,
               "items": [("l", fitz.Point(0, 1), fitz.Point(10, 1))], "seqno": -2, "imagen": True}]
    llamadas = []
    IC._CACHE.clear()
    assert IC.memo("hoja-x", lambda: llamadas.append(1) or trazos) is trazos
    IC._CACHE.clear()                                          # otro proceso / reabrir el proyecto
    leido = IC.memo("hoja-x", lambda: llamadas.append(1) or [])
    assert llamadas == [1]                                     # no se volvió a calcular
    assert leido[0]["items"][0][2] == fitz.Point(10, 1) and leido[0]["rect"] == fitz.Rect(0, 0, 10, 2)
    assert {k: v for k, v in leido[0].items() if k not in ("items", "rect")} == \
        {k: v for k, v in trazos[0].items() if k not in ("items", "rect")}
    IC._CACHE.clear()
    monkeypatch.setenv("PDFCAD_CACHE_EJES_IMAGEN", "")         # sin caché: siempre se calcula
    assert IC.memo("hoja-x", lambda: []) == []
    IC._CACHE.clear()
