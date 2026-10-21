"""Hoja COMPUESTA de mapas SIG sin capas (reporte del usuario 2026-10-19, Water North + South).

«Hoja por hoja funciona bien», pero al unir los mapas el agua se reconocía solo en algunas piezas y
las tuberías se cortaban en las costuras. Cubre:
  · la leyenda no toma por divisoria una línea del mapa TAPADA por el fondo del cuadro
    (`leyenda_mapa_lectura._divisores`: Water South h.15 quedaba sin tuberías);
  · los roles que puso la leyenda de una hoja no pasan a otra (`leyenda_mapa.roles_de_otra_hoja`,
    `roles_con_leyenda`, «Capas de la hoja» con roles de otra hoja);
  · la misma fila de la leyenda con otro estilo en cada pieza es UNA capa (`leyenda_piezas`);
  · costuras: las puntas de la misma tubería a los dos lados se unen (`recognition_ink_lines`);
  · en un mapa, dos líneas paralelas son dos tuberías (no «paredes» de una);
  · con los PDF de Phoenix (si están): 4 mapas unidos, una sola capa de agua y sin cortes.
"""
import math
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

fitz = pytest.importorskip("fitz")

from hoja import leyenda_mapa as LM, leyenda_piezas, pdf_styles  # noqa: E402
from hoja import leyenda_mapa_lectura as lectura  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from reconocimiento import recognition_ink_lines as ink  # noqa: E402

PHOENIX = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND")
WATER_N = PHOENIX / "QS Water_Indian School_North.pdf"
WATER_S = PHOENIX / "QS Water_Indian School_South.pdf"
needs_phoenix = pytest.mark.skipif(not (WATER_N.is_file() and WATER_S.is_file()),
                                   reason="PDF de Phoenix no disponible")

A = pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.38,"[] 0",null,1.0,null]'
B = pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.3,"[] 0",null,1.0,null]'
P = pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.56,"[] 0",null,1.0,null]'


# ── leyenda: una línea del mapa debajo del cuadro no es divisoria ───────────
def test_linea_tapada_por_el_fondo_del_cuadro_no_es_divisoria():
    marco = lectura._Marco((1.0, 0.0))                 # u = x, w = y
    fondo = {"type": "fs", "fill": (1.0, 1.0, 1.0), "fill_opacity": 1.0, "seqno": 10,
             "rect": fitz.Rect(0, 0, 200, 100), "items": [("re", fitz.Rect(0, 0, 200, 100))]}
    del_mapa = {"type": "s", "fill": None, "seqno": 5, "rect": fitz.Rect(50, -20, 50, 8),
                "items": [("l", fitz.Point(50, -20), fitz.Point(50, 8))]}
    divisoria = {"type": "s", "fill": None, "seqno": 11, "rect": fitz.Rect(80, 0, 80, 100),
                 "items": [("l", fitz.Point(80, 0), fitz.Point(80, 100))]}
    us = lectura._divisores([del_mapa, fondo, divisoria], marco, 0.0, 5.0, 10.0)
    assert 80.0 in us and 50.0 not in us
    # sin el fondo (o dibujada después de él) sí se ve, y cuenta como siempre
    assert 50.0 in lectura._divisores([del_mapa, divisoria], marco, 0.0, 5.0, 10.0)


@needs_phoenix
def test_water_south_h15_sus_tuberias_son_de_agua():
    doc = fitz.open(str(WATER_S))
    ley = LM.leer(doc, doc[14])                       # 16-24: antes, sección «GENERAL» y sin utilidad
    fila = next(f for f in ley.filas if f.texto == "Standard Main" and "WATER" in f.seccion)
    assert fila.utilidad == "AGUA" and fila.rol == LM.LINEA


# ── roles de una hoja usados en otra ────────────────────────────────────────
def test_roles_de_otra_hoja_sin_lo_que_puso_su_leyenda():
    roles = {
        "AGUA": {"lineas": [A, "PDF_STYLE:manual"], "buzones": ["sym"], LM.CLAVE_LEYENDA: [A, "sym"]},
        "GAS": {"lineas": [P], "buzones": [], LM.CLAVE_LEYENDA: [P]},
        "ELECTRICO": {"lineas": ["C-ELEC-UNGD"], "buzones": []},         # CAD: igual en toda hoja
    }
    otra = LM.roles_de_otra_hoja(roles)
    assert otra["AGUA"] == {"lineas": ["PDF_STYLE:manual"], "buzones": [], LM.SUMAR_LEYENDA: True}
    assert "GAS" not in otra                           # nada a mano: decide la leyenda de la hoja
    assert otra["ELECTRICO"] == roles["ELECTRICO"]


def test_roles_con_leyenda_lo_puesto_a_mano_manda():
    asig = {A: ("AGUA", "lineas"), B: ("AGUA", "lineas"), "sym": ("AGUA", "buzones"), P: ("GAS", "lineas")}
    assert LM.roles_con_leyenda(asig, "AGUA") == {"lineas": [A, B], "buzones": ["sym"]}
    a_mano = {"lineas": ["sym", "X"], "buzones": [B], LM.SUMAR_LEYENDA: True}
    assert LM.roles_con_leyenda(asig, "AGUA", a_mano) == {"lineas": [A, "sym", "X"], "buzones": [B]}


# ── la misma línea de la leyenda con otro estilo en cada pieza ──────────────
def _fila(texto, estilo, rol=LM.LINEA, utilidad="AGUA", seccion="WATER INFRASTRUCTURE"):
    return LM.FilaMapa(texto, seccion, utilidad, rol, False, (0, 0, 1, 1), {estilo: 4.0})


def _ley(por_pieza):
    por_hoja = [[_fila(t, e) for t, e in filas] for filas in por_pieza]
    return LM.LeyendaMapa([], "AGUA", None, [], por_hoja=por_hoja, piezas=list(range(len(por_hoja))))


def test_equivalencias_misma_fila_otro_estilo():
    ley = _ley([[("Standard Main", A), ("Fire Main", A), ("Private Main", P)],
                [("Standard Main", A), ("Fire Main", A), ("Private Main", P)],
                [("Standard Main", B), ("Fire Main", B), ("Private Main", P)]])
    assert leyenda_piezas.equivalencias(ley) == {(2, B): A}
    # hoja suelta: nada
    assert leyenda_piezas.equivalencias(_ley([[("Standard Main", A)]])) == {}


def test_equivalencias_no_junta_con_lo_que_en_esa_pieza_es_otra_cosa():
    ley = _ley([[("Standard Main", A), ("Private Main", P)],
                [("Standard Main", A), ("Private Main", P)],
                [("Standard Main", B), ("Private Main", A)]])      # aquí A es la privada
    eq = leyenda_piezas.equivalencias(ley)
    assert (2, B) not in eq


def test_pieza_de_por_orden_de_dibujo():
    assert leyenda_piezas.pieza_de([10, 50, 90], 49) == 0
    assert leyenda_piezas.pieza_de([10, 50, 90], 50) == 1
    assert leyenda_piezas.pieza_de(None, 49) == -1


# ── costuras ────────────────────────────────────────────────────────────────
def _path(pts, pieza, cortes=(), estilo=B):
    caja = ((-1000.0, -1000.0), (100.0, -1000.0), (100.0, 1000.0), (-1000.0, 1000.0)) if pieza == 0 else \
        ((100.0, -1000.0), (1000.0, -1000.0), (1000.0, 1000.0), (100.0, 1000.0))
    return {"items": [("l", fitz.Point(*a), fitz.Point(*b)) for a, b in zip(pts, pts[1:])],
            "layer": estilo, "width": 0.3, "clip_polys": [caja], "cut_pts": list(cortes), "clipped": True,
            "seqno": 10 if pieza == 0 else 60}


PIEZAS = [0, 50]          # orden de dibujo donde empieza cada pieza (`inicios_de_piezas`)


def _rec(paths, inicios=PIEZAS, **kw):
    return ink.ink_reconstruct(paths, inicios=inicios, **kw)


def _puntas(res):
    return sorted((tuple(round(c, 2) for c in pl.pts[j]), pl.kinds[j]) for pl in res.polylines for j in (0, -1))


def test_costura_la_cortada_llega_a_la_punta_de_la_vecina():
    # la hoja de la izquierda termina su tubería 0.9 pt antes de la costura (x = 100); la de la
    # derecha la trae cortada en la costura: la cortada sigue hasta ella
    st = {}
    res = _rec([_path([(0, 0), (99.1, 0)], 0),
                               _path([(100, 0), (200, 0)], 1, cortes=[(100, 0)])], stats=st)
    assert st["costuras"] == 1
    assert ((99.1, 0.0), "junction") in _puntas(res)
    assert sum(1 for _p, k in _puntas(res) if k == "junction") == 2


def test_costura_dos_cortadas_corridas_van_al_medio():
    st = {}
    res = _rec([_path([(0, 0), (100, 1.4)], 0, cortes=[(100, 1.4)]),
                               _path([(100, 0), (200, -1.4)], 1, cortes=[(100, 0)])], stats=st)
    assert st["costuras"] == 1
    assert [k for _p, k in _puntas(res)].count("junction") == 2
    assert ((100.0, 0.7), "junction") in _puntas(res)


def test_costura_ramal_cortado_llega_a_la_principal_de_la_vecina():
    st = {}
    res = _rec([_path([(98.5, -50), (98.5, 50)], 0),
                               _path([(150, 10), (100, 10)], 1, cortes=[(100, 10)])], stats=st)
    assert st["costuras"] == 1
    assert ((98.5, 10.0), "tee") in _puntas(res)


def test_costura_casi_paralela_no_es_t():
    # la línea de la vecina casi alineada con el ramal (2°) no es una T: es la misma línea
    st = {}
    res = _rec([_path([(60, 11.4), (98.9, 10)], 0),
                               _path([(150, 10), (100, 10)], 1, cortes=[(100, 10)])], stats=st)
    assert not any(k == "tee" for _p, k in _puntas(res))
    assert st["costuras"] == 1 and ((98.9, 10.0), "junction") in _puntas(res)     # punta con punta


def test_hoja_suelta_sin_cambios():
    # sin piezas (hoja suelta, aunque sus trazos traigan recortes distintos: el marco de la
    # vista y lo que va fuera): nada se alarga ni se une, la punta en el borde sigue «cut»
    st = {}
    res = _rec([_path([(0, 0), (99.1, 0)], 0), _path([(100, 0), (200, 0)], 1, cortes=[(100, 0)]),
                _path([(40, 5), (70, 5)], 0, cortes=[(40, 5)]), _path([(40, 5), (10, 5)], 0, cortes=[(40, 5)])],
               inicios=None, stats=st)
    assert st["costuras"] == 0
    assert ((100.0, 0.0), "cut") in _puntas(res) and ((40.0, 5.0), "cut") in _puntas(res)


def test_tuberia_pegada_a_la_costura_no_queda_en_trozos():
    # el SIG exporta cada tramo aparte; pegados al borde (≤ 0.25 pt) todos sus vértices son «corte»
    res = _rec([_path([(10, 0), (40, 0)], 0, cortes=[(40, 0)]),
                               _path([(40, 0), (70, 0)], 0, cortes=[(40, 0), (70, 0)]),
                               _path([(150, 0), (170, 0)], 1)])
    assert ((40.0, 0.0), "junction") in _puntas(res)


# ── en un mapa, dos paralelas son dos tuberías ──────────────────────────────
def test_paralelas_de_un_mapa_son_dos_tuberias(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    for y in (100.0, 102.7):
        page.draw_line((60, y), (360, y), width=.57)
    target = tmp_path / "mapa.pdf"
    doc.save(target)
    from hoja import pdf_layers
    capa = next(L["name"] for L in pdf_layers.page_layers(doc, 0) if "0.57 pt" in L["short"])
    res = rec.recognize_page(target, utility="AGUA", layer_roles={rec.ROLE_LINEAS: [capa], rec.ROLE_BUZONES: []},
                             zoom=1, scale_ft_per_pt=1)
    ys = sorted(round(sum(p[1] for p in pl.pts_pdf) / len(pl.pts_pdf), 1) for pl in res.drawable)
    assert ys == [100.0, 102.7]
    assert not any("paredes" in w for w in res.warnings)


# ── con los PDF de Phoenix: 4 mapas unidos (dos grosores distintos) ─────────
@pytest.fixture(scope="module")
def compuesta_4(tmp_path_factory):
    from hoja import composicion_ficha as F, composicion_sugerida as G, composite as C
    docs = [fitz.open(str(WATER_S)), fitz.open(str(WATER_N))]
    paginas = (15, 16)                                  # 16/17-25 (0.57 pt en North) y 16/17-26 (0.71)
    an = G.analizar([[F.ficha(d[i], k) for i in paginas] for k, d in enumerate(docs)])
    g = an.grupos[0]
    assert len(g.nodos) == 4
    comp = G.armar(g, an, docs, lambda di, pi: LM.leer(docs[di], docs[di][pi]).escala_ft_pt or 1.0)
    out = tmp_path_factory.mktemp("compuesta") / "agua4.pdf"
    C.build_document(comp, docs, {}, []).save(str(out))
    return out


@needs_phoenix
def test_phoenix_cuatro_mapas_una_capa_y_sin_cortes(compuesta_4):
    from hoja import acometidas_mapa
    res = rec.recognize_page(str(compuesta_4), utility="AGUA", zoom=1.0)
    red = [pl for pl in res.drawable if not acometidas_mapa.es_capa(pl.layer_ocg)]
    assert len({pl.layer_ocg for pl in red}) == 1          # 0.30 y 0.38 pt: la misma línea
    assert any(w.startswith("Hoja compuesta:") for w in res.warnings)
    assert any(w.startswith("Costuras de la hoja compuesta:") for w in res.warnings)
    assert not any("paredes" in w for w in res.warnings)
    # cada punta «cortada» que tiene enfrente la tubería de la otra hoja quedó unida
    doc = fitz.open(str(compuesta_4))
    page = doc[0]
    from collections import Counter
    ley = LM.leer(doc, page)
    asig, _ = LM.asignaciones(ley, Counter(d.get("layer") for d in pdf_styles.drawings(page)))
    lin = {n for n, (u, r) in asig.items() if u == "AGUA" and r == "lineas" and not acometidas_mapa.es_capa(n)}
    paths, *_ = rec.gather_paths(page, lambda o: "water_ungd" if o in lin else None, set(), None,
                                 legend_regions=ley.zonas)
    tinta = [(tuple(p.get("clip_polys") or ()), a, b) for p in paths for ch in ink.chains(p) for a, b in zip(ch, ch[1:])]
    sueltas = 0
    for pl in red:
        for j in (0, -1):
            if pl.kinds[j] != "cut":
                continue
            q = pl.pts_pdf[j]
            propia = min(tinta, key=lambda t: ink._seg_dist(q, t[1], t[2])[1])[0]
            if any(k != propia and ink._seg_dist(q, a, b)[1] <= 1.0 for k, a, b in tinta):
                sueltas += 1
    assert sueltas <= 1


@needs_phoenix
def test_phoenix_capas_con_roles_de_una_hoja_suelta(compuesta_4):
    """Tras reconocer una hoja suelta, la compuesta abría «Capas» con sus roles y la leyenda no
    se aplicaba: solo las piezas con los mismos grosores quedaban como agua."""
    from PySide6 import QtWidgets
    from ui.asistente import layer_dialog
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    suelta = fitz.open(str(WATER_S))
    d1 = layer_dialog.SheetLayersDialog(None, suelta, 16)
    roles = d1.roles_by_utility()
    d1.close()
    assert LM.CLAVE_LEYENDA in roles["AGUA"]
    comp = fitz.open(str(compuesta_4))
    d2 = layer_dialog.SheetLayersDialog(None, comp, 0, roles_by_utility=LM.roles_de_otra_hoja(roles))
    d3 = layer_dialog.SheetLayersDialog(None, comp, 0)
    agua = lambda d: {n for n, (u, _r) in d._assignments.items() if u == "AGUA"}  # noqa: E731
    assert agua(d2) == agua(d3)
    assert any("0.30 pt" in pdf_styles.style_label(n) for n in agua(d2))
    # volver a «Capas» en la MISMA hoja: lo elegido manda tal cual
    r3 = d3.roles_by_utility()
    r3["AGUA"]["lineas"] = [n for n in r3["AGUA"]["lineas"] if "0.30 pt" not in pdf_styles.style_label(n)]
    d4 = layer_dialog.SheetLayersDialog(None, comp, 0, roles_by_utility=r3)
    assert not any("0.30 pt" in pdf_styles.style_label(n) for n, (u, r) in d4._assignments.items()
                   if u == "AGUA" and r == "lineas")


# ── la leyenda TAPADA de una hoja no quita tuberías de la vecina ────────────
def test_zona_de_leyenda_recortada_a_lo_que_se_ve_de_su_pieza():
    assert lectura._zona_visible((10, 10, 50, 50), None) == (10, 10, 50, 50)      # hoja suelta
    assert lectura._zona_visible((10, 10, 50, 50), (0, 0, 100, 100)) == (10, 10, 50, 50)
    assert lectura._zona_visible((10, 80, 50, 120), (0, 0, 100, 100)) == (10, 80, 50, 100)
    assert lectura._zona_visible((10, 110, 50, 150), (0, 0, 100, 100)) is None   # fuera del recorte


@needs_phoenix
def test_phoenix_leyenda_tapada_no_quita_tuberias_de_la_hoja_de_abajo(tmp_path):
    """Reporte del usuario 2026-10-20 (Water North + South, 36 mapas): la caja de la leyenda de
    cada hoja North queda fuera de su recorte y caía ENCIMA de la hoja South de abajo (16-15):
    sus tuberías se descartaban como «muestras de la leyenda» y quedaban sin reconocer."""
    from hoja import composite as C
    docs = [fitz.open(str(WATER_S)), fitz.open(str(WATER_N))]
    comp = C.Composite(pieces=[        # colocación de la composición sugerida (17-15 sobre 16-15)
        C.Piece(source=1, page=5, clip=[0.13741, 0.14649, 0.86172, 0.74913], x=2368.0, y=0.0,
                src_scale=0.7352124694374402),
        C.Piece(source=0, page=5, clip=[0.14028, 0.19287, 0.86460, 0.75243], x=2368.0, y=505.305,
                src_scale=1.3887246922953445)],
        scale_ft_per_pt=1.3888888888888888, bridges=False)
    out = tmp_path / "norte_sur.pdf"
    C.build_document(comp, docs, {}, []).save(str(out))
    doc = fitz.open(str(out))
    page = doc[0]
    ley = LM.leer(doc, page)
    cajas = lectura.recortes_de_piezas(page)
    assert cajas and len(cajas) == 2
    for z in ley.zonas:                 # cada zona, dentro de lo que se ve de alguna pieza
        assert any(c[0] - 1e-6 <= z[0] and z[2] <= c[2] + 1e-6 and c[1] - 1e-6 <= z[1] and z[3] <= c[3] + 1e-6
                   for c in cajas)
    # bajo la caja de la leyenda de 17-15 (tapada), en 16-15: antes ninguna tubería; ahora 14
    res = rec.recognize_page(str(out), utility="AGUA", zoom=1.0)
    ox, oy = cajas[1][0] - 36.0, cajas[1][1] - 541.306     # (la compuesta lleva 36 pt de margen)
    bajo = [pl for pl in res.drawable
            if any(400 + ox <= x <= 460 + ox and 555 + oy <= y <= 615 + oy for x, y in pl.pts_pdf)]
    assert len(bajo) >= 10
