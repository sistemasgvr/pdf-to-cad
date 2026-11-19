"""Ronda de corrección 2 de la Tarea 5 (ejes de imagen, plan 2026-11-18): la hoja COMPUESTA de una red en imagen no
inventa buzones en la costura (I-1), la memoria de ejes por huella distingue la CropBox (I-2) y el modo «trazo
continuo» / núcleo se decide por PIEZA en las capas de imagen (I-3). Sintéticas (ayudantes de `test_imagen_capas`)."""

import math

import cv2
import fitz
import pytest

from hoja import composite, imagen_compuesta as IC, imagen_ejes as IE
from test_imagen_capas import AZUL, _ejes, _pdf_tiras


def _red_cruza(idx):
    """Tubería horizontal casi de lado a lado (cruza el centro de la hoja: la costura de dos mitades)."""
    cv2.rectangle(idx, (40, 296), (560, 303), 1, -1)


def _reconocer(doc, capa, utilidad="DRENAJE"):
    from reconocimiento import recognition as rec
    return rec.recognize_page(doc.name, page_index=0, utility=utilidad, doc=doc,
                              layer_roles={rec.ROLE_LINEAS: [capa], rec.ROLE_BUZONES: []}, zoom=1.0)


def _bovedas(r):
    return sum(1 for pl in r.polylines for k in pl.kinds if k == "vault")


def _mitades(tmp_path, doc, nombre="comp.pdf"):
    W = doc[0].rect.width
    comp = composite.Composite(pieces=[
        composite.Piece(source=0, page=0, clip=[0, 0, 0.5, 1], x=0.0, y=0.0, src_scale=1.0),
        composite.Piece(source=0, page=0, clip=[0.5, 0, 1, 1], x=W * 0.5, y=0.0, src_scale=1.0)],
        scale_ft_per_pt=1.0, bridges=False)
    ruta = tmp_path / nombre
    composite.build_document(comp, [doc], {}, []).save(str(ruta))
    return fitz.open(str(ruta))


def test_costura_de_la_compuesta_no_inventa_buzon(tmp_path):
    # I-1: la tubería que cruza la costura da dos trazos (uno por pieza) que terminan en el MISMO punto del corte;
    # `recognition_style_nodes` (red por gravedad: extremo compartido por ≥ 2 trazos = buzón) ponía ahí un «vault»
    # que ninguna hoja suelta tiene.
    marcas = [((x, y), (x + 3, y)) for x in (40, 250) for y in (40, 250)]      # vectores en cada pieza
    doc = _pdf_tiras(tmp_path, _red_cruza, negros=marcas, nombre="origen.pdf")
    capa = IE.nombre("line", AZUL)
    assert len(_ejes(IE.capas(doc[0]))) == 1
    suelta = _reconocer(doc, capa)
    dc = _mitades(tmp_path, doc)
    lineas = _ejes(IE.capas(dc[0]))
    assert len(lineas) == 2 and all(p["cut_pts"] for p in lineas)       # cortada en la costura
    comp = _reconocer(dc, capa)
    assert _bovedas(comp) == _bovedas(suelta) == 0, (comp.polylines, suelta.polylines)


def test_costura_vectorial_sigue_igual():
    # Las capas VECTORIALES por estilo no cambian: dos trazos que terminan en el mismo corte siguen siendo nodo.
    from reconocimiento import recognition_style_nodes as SN
    a = {"items": [("l", (0.0, 0.0), (50.0, 0.0))], "cut_pts": [(50.0, 0.0)]}
    b = {"items": [("l", (50.0, 0.0), (100.0, 0.0))], "cut_pts": [(50.0, 0.0)]}
    assert SN.feature_nodes([a, b]) == [(50.0, 0.0)]
    # …y en una de imagen, un corte compartido con un extremo que NO es corte sigue siendo nodo
    ai = dict(a, imagen=True)
    bi = dict(b, imagen=True)
    assert SN.feature_nodes([ai, bi]) == []
    ci = {"items": [("l", (50.0, 0.0), (50.0, 50.0))], "imagen": True}
    assert SN.feature_nodes([ai, bi, ci]) == [(50.0, 0.0)]


def test_huella_distingue_la_cropbox(tmp_path, monkeypatch):
    # I-2: `get_drawings` va en coordenadas de la CROPBOX. Dos hojas con el mismo contenido y otra CropBox no pueden
    # compartir los ejes memorizados (los de una quedaban corridos en la otra).
    monkeypatch.setattr(IC, "_CACHE", type(IC._CACHE)())
    doc = _pdf_tiras(tmp_path, _red_cruza, nombre="caja.pdf")
    doc.fullcopy_page(0)
    doc[1].set_cropbox(fitz.Rect(20, 30, 280, 290))
    ruta = tmp_path / "caja2.pdf"
    doc.save(str(ruta))
    doc = fitz.open(str(ruta))
    assert doc[0].read_contents() == doc[1].read_contents()
    assert IC.huella_hoja(doc[0]) != IC.huella_hoja(doc[1])
    # sin CropBox propia la huella es la de siempre (la de la `/fullpage` de una compuesta)
    mb = doc[0].mediabox
    assert IC.huella_hoja(doc[0]) == IC._huella(doc, doc[0].read_contents(), (mb.x0, mb.y0, mb.x1, mb.y1), doc[0].xref)
    for orden in ((1, 0), (0, 1)):
        IC._CACHE.clear()
        doc.__dict__.pop(IE._CACHE, None)
        res = {i: _ejes(IE.capas(doc[i])) for i in orden}
        (a,), (b,) = res[0], res[1]
        dx = doc[1].cropbox.x0 - doc[0].cropbox.x0
        dy = doc[1].cropbox.y0 - doc[0].cropbox.y0
        qa = [q for it in a["items"] for q in it[1:]]
        qb = [q for it in b["items"] for q in it[1:]]
        # (las teselas de cada hoja arrancan en otro píxel: las puntas pueden diferir medio píxel; envenenada, la
        # de una quedaba 30 pt corrida)
        assert len(qa) == len(qb)
        assert max(math.dist((p.x - dx, p.y - dy), (q.x, q.y)) for p, q in zip(qa, qb)) <= 1.0
        # la tinta está donde dice cada hoja (la de la CropBox, 30 pt más arriba)
        assert all(abs(q.y - 150.0) <= 0.75 for q in qa) and all(abs(q.y - 120.0) <= 0.75 for q in qb)


def test_modo_por_pieza_solo_en_capas_de_imagen_de_una_compuesta():
    # I-3: en una compuesta, cada pieza decide «continua» / núcleo con SUS trazos (como su hoja suelta); las capas
    # vectoriales y las hojas sueltas (trazos de una sola pieza) no pasan por aquí.
    from reconocimiento import recognition_imagen_piezas as RIP
    img = IE.nombre("line", AZUL)
    ps = [{"items": [], "seqno": s, "k": k} for k, s in enumerate((10, 50, 12, 55, 60))]
    continua = lambda qs: all(q["seqno"] < 40 for q in qs)            # noqa: E731  (pieza 0 continua, 1 no)
    g = RIP.grupos(img, ps, [0, 40], continua)
    assert [(c, [q["k"] for q in qs]) for c, qs in g] == [(True, [0, 2]), (False, [1, 3, 4])]
    assert RIP.grupos('PDF_STYLE:["#000000",0.7,[],null]', ps, [0, 40], continua) is None     # vectorial
    assert RIP.grupos(img, ps[:1] + ps[2:3], [0, 40], continua) is None                       # una sola pieza
    assert RIP.grupos(img, ps, None, continua) is None                                        # hoja suelta
    # los contactos de la capa van al primer trazo de cada grupo (el núcleo los lee de ahí)
    c = RIP.con_contactos(g[1][1], [(1.0, 2.0)])
    assert c[0]["contact_pts"] == [(1.0, 2.0)] and "contact_pts" not in g[1][1][0]
