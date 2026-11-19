"""Ronda de corrección 1 de la Tarea 5 (ejes de imagen, plan 2026-11-18): un color con DOS grosores se parte en dos
capas de línea (`imagen_grosores`) y la hoja COMPUESTA lleva los ejes de cada hoja de origen (`imagen_compuesta`) en vez
de leer su imagen. Sintéticas (los ayudantes son los de `test_imagen_capas`)."""

import math

import cv2
import fitz
import pytest

from hoja import composite, imagen_ejes as IE, pdf_styles
from test_imagen_capas import AZUL, _ejes, _pdf_tiras, _red


def _tramo(x0, y, largo):
    return [(float(x0), float(y)), (float(x0 + largo), float(y))]


def test_un_color_con_dos_grosores_se_parte_en_dos_capas():
    # Phoenix SD h.4/h.7/h.8: el #004DA8 trae las bandas de la red (~3.3 pt) y líneas FINAS a guiones (≤ 1 pt, el
    # canal sobre una banda gris). En una sola capa el núcleo inventaba uniones. Dos grosores claramente distintos,
    # los dos tinta real → dos capas; la fina, con «fino».
    bandas = [(_tramo(0, 10 * k, 40), 3.3) for k in range(30)]
    finas = [(_tramo(100 + 8 * k, 500, 5), 0.4) for k in range(60)]
    gruesas, fin = IE.partir_por_grosor(bandas + finas)
    assert [w for _p, w in gruesas] == [3.3] * 30 and [w for _p, w in fin] == [0.4] * 60
    # un solo grosor, o unos pocos trocitos finos (contornos), o grosores repartidos sin dos grupos: NO se parte
    # trocitos finos SUELTOS (contornos de símbolos y uniones, Phoenix SD h.1/h.3): no forman una línea
    sueltos = [([(100.0 + 9 * k, 600.0), (100.0 + 9 * k, 605.0)], 0.4) for k in range(60)]
    for lineas in (bandas,
                   bandas + finas[:4],
                   bandas + sueltos,
                   [(_tramo(0, 10 * k, 30), 1.0 + 0.1 * k) for k in range(26)]):
        g, f = IE.partir_por_grosor(lineas)
        assert f == [] and g == lineas
    fino = IE.nombre("line", AZUL, IE.FINO)
    assert fino == 'PDF_STYLE:["img","line",[0,77,168],"fino"]'
    assert IE.tipo_imagen(fino) == "line" and IE.rgb_de(fino) == AZUL
    assert pdf_styles.style_label(fino) == "Azul #004DA8 (fino) · imagen"


def _red_y_canal(idx):
    """Tubería azul gruesa (8 px = 4 pt) y, aparte, una línea azul FINA a guiones (2 px = 1 pt)."""
    _red(idx)
    for x in range(60, 540, 16):
        cv2.rectangle(idx, (x, 499), (x + 9, 500), 1, -1)


def test_hoja_con_bandas_y_guiones_finos_del_mismo_color(tmp_path):
    cs = IE.capas(_pdf_tiras(tmp_path, _red_y_canal)[0])
    gruesa = [p for p in _ejes(cs) if p["layer"] == IE.nombre("line", AZUL)]
    fina = [p for p in _ejes(cs) if p["layer"] == IE.nombre("line", AZUL, IE.FINO)]
    assert len(gruesa) == 1 and gruesa[0]["width"] == pytest.approx(4.0, abs=0.6)
    assert len(fina) >= 20 and all(p["width"] <= 1.4 for p in fina)
    assert all(abs(it[1].y - 250.0) <= 0.75 for p in fina for it in p["items"])


def _red_larga(idx):
    """Tubería VERTICAL (en la hoja sin girar; horizontal en la vista de una hoja con /Rotate 90) casi de punta a
    punta, para cortarla con el recorte de una pieza, y un cuadro (símbolo)."""
    cv2.rectangle(idx, (296, 20), (303, 580), 1, -1)
    cv2.rectangle(idx, (440, 440), (459, 459), 1, -1)


def test_compuesta_lleva_los_ejes_de_cada_hoja_de_origen(tmp_path):
    # Diseño §7.2: en una hoja COMPUESTA no se lee su imagen; los ejes de cada hoja de ORIGEN se llevan con
    # `piece_map` de la pieza y se recortan a su recorte. Cada trazo lleva el seqno del inicio de su pieza (para que
    # `recognition_ink_lines` suelde las costuras) y los cortes del recorte en `cut_pts`/`clip_polys`.
    marcas = [((x, y), (x + 3, y)) for x in (40, 250) for y in (40, 250)]      # vectores en cada pieza
    doc = _pdf_tiras(tmp_path, _red_larga, rotar=90, negros=marcas, nombre="origen.pdf")
    suelta = IE.capas(doc[0])
    W, H = doc[0].rect.width, doc[0].rect.height
    comp = composite.Composite(pieces=[
        composite.Piece(source=0, page=0, clip=[0, 0, 0.5, 1], x=0.0, y=0.0, src_scale=1.0),
        composite.Piece(source=0, page=0, clip=[0.5, 0, 1, 1], x=W * 0.5 + 40, y=10.0, src_scale=1.0, rotation=90)],
        scale_ft_per_pt=1.0, bridges=False)
    ruta = tmp_path / "comp.pdf"
    composite.build_document(comp, [doc], {}, []).save(str(ruta))
    dc = fitz.open(str(ruta))
    cs = IE.capas(dc[0])
    _w, _h, dx, dy = composite.sheet_geometry(comp, lambda pz: (W, H))
    from hoja import leyenda_mapa_lectura as LML
    inicios = LML.inicios_de_piezas(dc[0])
    assert inicios and len(inicios) == 2
    der = doc[0].rotation_matrix                      # get_drawings de la hoja de origen → vista
    (eje,) = _ejes(suelta)
    (sim,) = _ejes(suelta, "sym")
    lineas = _ejes(cs)
    assert len(lineas) == 2                           # la tubería, cortada por el recorte de cada pieza
    fns = []
    for k, pz in enumerate(comp.pieces):
        fn0 = composite.piece_map(pz, (W, H), 1.0)

        def fn(x, y, fn0=fn0):
            v = fitz.Point(x, y) * der
            a = fn0(v.x, v.y)
            return a[0] + dx, a[1] + dy
        fns.append(fn)
        mio = [p for p in lineas if p["seqno"] == inicios[k]]
        assert len(mio) == 1
        p = mio[0]
        # sobre la recta del eje de la hoja suelta llevada a la compuesta (a ≤ 1e-3 pt: la matriz de la pieza va
        # escrita en el PDF con 5 decimales y `fitz.Point * Matrix` calcula en float de C)
        a, b = fn(*eje["items"][0][1]), fn(*eje["items"][-1][2])
        for q in [q for it in p["items"] for q in it[1:]]:
            cruz = (b[0] - a[0]) * (q.y - a[1]) - (b[1] - a[1]) * (q.x - a[0])
            assert abs(cruz) / math.dist(a, b) <= 1e-3
        assert p["width"] == pytest.approx(eje["width"], abs=1e-9)
        assert p["layer"] == eje["layer"] and p["clip_polys"] and len(p["cut_pts"]) == 1
        assert p["imagen"] is True
    # el símbolo, solo en la pieza que lo ve, con el centro llevado
    (s2,) = _ejes(cs, "sym")
    k = inicios.index(s2["seqno"])
    c = fitz.Rect(sim["rect"])
    esperado = fns[k]((c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2)
    r2 = fitz.Rect(s2["rect"])
    assert ((r2.x0 + r2.x1) / 2, (r2.y0 + r2.y1) / 2) == pytest.approx(esperado, abs=1e-3)


def test_compuesta_sin_red_en_imagen_no_copia_la_hoja(tmp_path, monkeypatch):
    # Una compuesta de hojas sin red en imagen (solo un logo) da [] sin armar ninguna hoja de origen.
    from hoja import imagen_compuesta as IC
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_line((10, 10), (290, 290), color=(0, 0, 0), width=0.5)
    logo = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
    logo.clear_with(120)
    page.insert_image(fitz.Rect(250, 250, 290, 290), stream=logo.tobytes("png"))
    ruta = tmp_path / "logo.pdf"
    doc.save(str(ruta))
    doc = fitz.open(str(ruta))
    comp = composite.Composite(pieces=[
        composite.Piece(source=0, page=0, clip=[0, 0, 1, 1], x=0.0, y=0.0, src_scale=1.0),
        composite.Piece(source=0, page=0, clip=[0, 0, 1, 1], x=300.0, y=0.0, src_scale=1.0)],
        scale_ft_per_pt=1.0, bridges=False)
    comp_ruta = tmp_path / "comp.pdf"
    composite.build_document(comp, [doc], {}, []).save(str(comp_ruta))
    dc = fitz.open(str(comp_ruta))
    assert IC.piezas(dc[0]) and len(IC.piezas(dc[0])) == 2

    def no(*_a, **_k):
        raise AssertionError("armó una hoja de origen")
    monkeypatch.setattr(IC, "memo", no)
    assert IE.capas(dc[0]) == []
