"""Leer la imagen de la hoja más rápido, con el MISMO resultado (pedido del usuario 2026-11-19: «Leyendo la imagen de
la hoja…» tardaba ~35 s por hoja y una compuesta de 36 mapas las leía de a una, ~20 min).

· `imagen_paleta.familia`/`mascara` dentro de `misma_imagen` buscan solo los píxeles que no son blanco.
· `imagen_compuesta.ejes_de_piezas(en_proceso=)` reparte las hojas de origen en varios procesos.
"""
import os
import pickle
import sys

import numpy as np
import pytest

from hoja import imagen_paleta as IP

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _imagen():
    rng = np.random.default_rng(7)
    img = np.full((300, 400, 3), 255, np.uint8)
    azul, claro = np.array([0, 77, 168], np.uint8), np.array([128, 166, 212], np.uint8)
    img[100:110, 20:380] = azul
    img[99, 20:380] = claro                       # borde de la banda (tinte del azul)
    img[200:260, 50:150][rng.random((60, 100)) < 0.3] = claro      # un rayado del tinte
    img[rng.integers(0, 300, 50), rng.integers(0, 400, 50)] = rng.integers(0, 255, (50, 3))
    return img


def test_familia_y_mascara_dan_lo_mismo_mirando_solo_lo_que_no_es_blanco():
    img = _imagen()
    pal = IP.paleta([img], True)
    for c in pal:
        otros = [o for o in pal if o is not c]
        sin = (IP.mascara(img, c), IP.familia(img, c, otros))
        with IP.misma_imagen(img):
            con = (IP.mascara(img, c), IP.familia(img, c, otros))
        assert all(np.array_equal(a, b) for a, b in zip(sin, con))


SD = os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "DOCS DE PRUEBA IND",
                  "QS SD_Indian School_North.pdf")


@pytest.mark.skipif(not os.path.exists(SD), reason="falta el PDF QS SD de Phoenix")
def test_compuesta_repartida_en_procesos_da_lo_mismo_que_de_a_una(monkeypatch):
    sys.path.insert(0, os.path.join(RAIZ, "scripts"))
    import fitz
    import audit_ejes_imagen as A
    from hoja import imagen_compuesta as IC
    from hoja import imagen_ejes as IE
    from ui.comun import proceso_hijo
    if proceso_hijo.paralelos(2, IC.MB_POR_HOJA) < 2:
        pytest.skip("sin RAM o núcleos para dos procesos")

    def leer(repartir):
        IC._CACHE.clear()
        llamadas = []
        original = IC._repartir
        monkeypatch.setattr(IC, "_repartir", (lambda *a: (llamadas.append(1), original(*a))) if repartir
                            else (lambda *a: None))
        comp = A.compuesta(fitz.open(SD), [3, 4])
        cs = IE.capas(comp[0])
        return llamadas, [(p["layer"], p.get("width"), tuple(p["rect"]), p.get("seqno"),
                           [(it[0],) + tuple(tuple(q) for q in it[1:]) for it in p["items"]]) for p in cs]

    llamadas, en_procesos = leer(True)
    _, de_a_una = leer(False)
    assert llamadas and en_procesos
    assert pickle.dumps(en_procesos) == pickle.dumps(de_a_una)


def test_en_una_compuesta_cada_pieza_del_nucleo_va_sola_con_sus_bovedas():
    # 2026-11-19: las piezas que van al núcleo se juntaban en un lote con TODAS las bóvedas de la hoja y
    # `resolve_nodes` (todos con todos) pasaba horas con 36 mapas; sola, cada pieza da lo de su hoja suelta
    from reconocimiento import recognition_imagen_piezas as P
    capa = 'PDF_STYLE:["img","line",[0,77,168]]'
    trazos = [{"seqno": s, "rect": (x, 0, x + 10, 10)} for s, x in ((1, 0), (5, 500), (2, 5), (9, 1000), (6, 505))]
    g = P.grupos(capa, trazos, [0, 4, 8], lambda ps: ps[0]["seqno"] >= 8)      # pieza 2 continua, 0 y 1 al núcleo
    assert [(c, [t["seqno"] for t in ps]) for c, ps in g] == [(True, [9]), (False, [1, 2]), (False, [5, 6])]
    bovedas = [{"rect": (0, 0, 4, 4)}, {"rect": (700, 0, 704, 4)}, {"rect": (515, 0, 519, 4)}]
    assert P.bovedas_cerca(g[2][1], bovedas, 100.0) == [bovedas[2]]
    # (reporte 2026-11-19: los trazos RECORTADOS traen `recognition_geom._Rect`, sin índices → TypeError)
    from reconocimiento.recognition_geom import _Rect
    recortados = [dict(t, rect=_Rect(*t["rect"])) for t in g[2][1]]
    assert P.bovedas_cerca(recortados, [dict(b, rect=_Rect(*b["rect"])) for b in bovedas], 100.0)[0]["rect"].x0 == 515
