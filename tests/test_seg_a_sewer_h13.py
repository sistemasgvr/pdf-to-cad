"""Reporte del usuario 2026-11-10, «25_06-13 - Seg A Sewer 100%_DR.pdf» hoja 13 (índice 12).

1. La línea eléctrica que llega a la caja abandonada por la izquierda salía DOBLE: su último
   guión quedaba aparte y la línea se estiraba sin tinta hasta el borde (dos llegadas).
2. El buzón eléctrico redondo dibujado DENTRO de esa caja (V-ELEC-MANH, círculo de Béziers
   aplanado por el recorte de la vista) se leía como cuadrado y, al importar, la caja grande le
   pisaba la geometría: el buzón desaparecía.
3. Los buzones redondos (182+00) se importaban bien pero el editor solo dibujaba el punto:
   ahora guardan su anillo (`anillo`) y se dibuja el círculo.
"""
import copy
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")
from reconocimiento import recognition as rec  # noqa: E402
from nucleo import model_ops  # noqa: E402
from nucleo.model import NETWORK_KIND  # noqa: E402

PDF = Path(r"C:/Users/bernu/Downloads/25_06-13 - Seg A Sewer 100%_DR.pdf")
pytestmark = pytest.mark.skipif(not PDF.is_file(), reason="PDF Seg A Sewer no disponible")
HOJA = 12
CAJA_IZQ_X = 633.9                 # borde izquierdo de la caja abandonada (pt)


@pytest.fixture(scope="module")
def doc():
    d = fitz.open(str(PDF))
    yield d
    d.close()


def test_una_sola_llegada_a_la_caja(doc):
    r = rec.recognize_page(str(PDF), HOJA, "ELECTRICO", doc=doc)
    llegan = [pl for pl in r.polylines
              if any(abs(x - CAJA_IZQ_X) < 1.0 and 853 < y < 860 for x, y in pl.pts_pdf)]
    assert len(llegan) == 1, [pl.pts_pdf for pl in llegan]


def test_buzon_redondo_dentro_de_la_caja(doc):
    r = rec.recognize_page(str(PDF), HOJA, "ELECTRICO", doc=doc)
    dentro = [v for v in r.vaults_geo if math.hypot(v["center"][0] - 662.1, v["center"][1] - 852.5) < 2]
    assert len(dentro) == 1 and dentro[0]["shape"] == "circle"
    assert 2.5 < dentro[0]["width_ft"] < 2.9
    grande = [v for v in r.vaults_geo if v["shape"] == "rect" and v["length_ft"] > 15]
    assert len(grande) == 1

    # importación: los DOS quedan como estructura, cada uno con su forma
    z = 3.5
    r = rec.recognize_page(str(PDF), HOJA, "ELECTRICO", zoom=z, doc=doc)
    pipes = rec.pipes_from_recognition(r, layer="ELECTRICO", zoom=z)
    st = model_ops.rebuild_structures(pipes, [])
    model_ops.attach_vault_geometry(st, copy.deepcopy(r.vaults_geo), net=NETWORK_KIND["ELECTRICO"],
                                    utility="ELECTRICO", pipes=pipes)
    redondo = [s for s in st if s.get("shape") == "circle"
               and math.hypot(s["x"] / z - 662.1, s["y"] / z - 852.5) < 2]
    caja = [s for s in st if s.get("shape") == "rect" and float(s.get("length_ft") or 0) > 15]
    assert len(redondo) == 1 and redondo[0].get("anillo")
    assert len(caja) == 1 and caja[0] is not redondo[0]


def test_buzon_redondo_lleva_su_anillo(doc):
    z = 3.5
    r = rec.recognize_page(str(PDF), HOJA, "ALCANTARILLADO", zoom=z, doc=doc)
    pipes = rec.pipes_from_recognition(r, layer="ALCANTARILLADO", zoom=z)
    st = model_ops.rebuild_structures(pipes, [])
    model_ops.attach_vault_geometry(st, copy.deepcopy(r.vaults_geo), net=NETWORK_KIND["ALCANTARILLADO"],
                                    utility="ALCANTARILLADO", pipes=pipes)
    bz = [s for s in st if s.get("anillo") and abs(s["x"] / z - 1114.9) < 2 and abs(s["y"] / z - 740.7) < 2]
    assert len(bz) == 1
    cx, cy, rr = bz[0]["anillo"]
    assert abs(rr / z - 10.8) < 0.3
    # moverlo lleva el anillo
    model_ops.translate_structure(bz[0], 5.0, -3.0)
    assert bz[0]["anillo"][:2] == pytest.approx((cx + 5.0, cy - 3.0))
