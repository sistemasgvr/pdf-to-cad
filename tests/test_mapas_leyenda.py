"""Mapas SIG aplanados: lo que dice la LEYENDA y el plano (2026-10-14).

Reporte del usuario sobre «QS Water South» h.4: los quiebres de la tubería no eran
precisos, la línea fina que sale hacia los lotes es la acometida, mejorar los buzones con
la leyenda y sacar del plano toda la información posible. Cubre:
  · la tinta como eje a MEDIO GROSOR del trazo (`recognition_ink_lines.simplify_tol`);
  · rol ACOMETIDA y notas del cuadro (`leyenda_mapa`), columnas y símbolos bien leídos
    (`leyenda_mapa_lectura`);
  · acometidas por su bloque de dibujo (`acometidas_mapa`) y su T (`recognition_taps`);
  · buzones-símbolo unidos a su línea (`recognition_map_vaults`);
  · diámetros escritos en el plano (`recognition_diametros`);
  · con los PDF de Phoenix (si están): leyenda, «6"» legible, acometidas y buzones.
"""
import math
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

fitz = pytest.importorskip("fitz")

from hoja import acometidas_mapa, leyenda_mapa as LM, pdf_styles  # noqa: E402
from hoja import leyenda_mapa_lectura as lectura  # noqa: E402
from reconocimiento import recognition_diametros as diam_mod  # noqa: E402
from reconocimiento import recognition_ink_lines as ink  # noqa: E402
from reconocimiento import recognition_map_vaults as map_vaults  # noqa: E402
from reconocimiento import recognition_taps as taps_mod  # noqa: E402

PHOENIX = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND")
WATER_S = PHOENIX / "QS Water_Indian School_South.pdf"
SEWER_N = PHOENIX / "QS Sewer_Indian School_North.pdf"
needs_phoenix = pytest.mark.skipif(not (WATER_S.is_file() and SEWER_N.is_file()),
                                   reason="PDF de Phoenix no disponible")

ESTILO_FINO = pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.19,"[] 0",null,1.0,null]'
ESTILO_RED = pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.38,"[] 0",null,1.0,null]'
SIMBOLO = pdf_styles.symbol_name("Type3 (8 0 R)", ((52, (1.0, 1.0, 1.0)), (58, (0.0, 0.0, 0.0))))


def _pl(pts, kinds=None, layer=ESTILO_RED):
    return SimpleNamespace(layer_ocg=layer, pts_pdf=[tuple(p) for p in pts],
                           kinds=list(kinds or (["end"] + ["bend"] * (len(pts) - 2) + ["end"])),
                           fillets={}, review="", diam_in=None)


# ── leyenda: significado de cada fila y notas del cuadro ────────────────────
@pytest.mark.parametrize("texto, rol", [
    ("As-Built Tap", LM.ACOMETIDA), ("Application Tap", LM.ACOMETIDA), ("Service Line", LM.ACOMETIDA),
    ("Tap Sleeve", LM.ACCESORIO),                       # el manguito de la toma es un accesorio
    ("Application Tap Without Locate", LM.ANOTACION),   # sin ubicación: no se dibuja la tubería
    ("Hydrant Main", LM.LINEA), ("Standard Manhole", LM.ESTRUCTURA), ("As-Built Tics", LM.ANOTACION),
])
def test_rol_de_cada_fila(texto, rol):
    assert LM.rol_de(texto) == rol


def test_notas_del_cuadro_diametro_de_acometidas_y_material():
    corr = [SimpleNamespace(texto=t) for t in (
        "*All water main material is ACP (Asbestos Cement Pipe) unless otherwise noted.",
        '*All water taps are .75" in diameter unless otherwise noted.')]
    assert lectura._notas(corr) == {"material": "ACP (Asbestos Cement Pipe)", "diam_acometida_in": 0.75}
    assert lectura._notas([SimpleNamespace(texto='*All sewer taps are 4" in diameter')]) == {"diam_acometida_in": 4.0}


def test_columna_se_parte_donde_se_corta_el_paso():
    """«Plotted On:» del cajetín, alineado bajo la última fila, no es otra fila."""
    filas = [(10.0, 100.0 + 2.7 * i, None) for i in range(8)] + [(10.0, 100.0 + 2.7 * 7 + 28.0, None)]
    partes = lectura._partir_columna(filas)
    assert [len(p) for p in partes] == [8, 1]


# ── la tinta es el eje, a medio grosor del trazo ────────────────────────────
@pytest.mark.parametrize("ancho, tol", [(0.38, 0.19), (0.73, 0.365), (2.0, ink.SIMPLIFY_PT), (0.1, ink.SIMPLIFY_MIN_PT)])
def test_tolerancia_es_medio_grosor_del_trazo(ancho, tol):
    assert abs(ink.simplify_tol([{"width": ancho}]) - tol) < 1e-9


def test_curva_suave_se_sigue_con_trazo_fino_y_no_con_grueso():
    """Un quiebre de 0.3 pt: dentro de un trazo de 1 pt (tolerancia 0.5) es zigzag; en la
    tubería de agua de 0.38 pt el eje saldría del trazo, así que el vértice se queda."""
    curva = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.3), (30.0, 0.0), (40.0, 0.0)]
    path = lambda w: {"items": [("l", a, b) for a, b in zip(curva, curva[1:])], "width": w}
    fino = ink.ink_reconstruct([path(0.38)]).polylines[0].pts
    grueso = ink.ink_reconstruct([path(1.0)]).polylines[0].pts
    assert (20.0, 0.3) in fino and (20.0, 0.3) not in grueso


# ── acometidas ─────────────────────────────────────────────────────────────
def test_capa_de_acometidas_ida_y_vuelta():
    capa = acometidas_mapa.capa(ESTILO_FINO, "AGUA")
    assert acometidas_mapa.es_capa(capa) and not acometidas_mapa.es_capa(ESTILO_FINO)
    assert acometidas_mapa.estilo_de(capa) == ESTILO_FINO and acometidas_mapa.utilidad_de(capa) == "AGUA"
    assert pdf_styles.style_label(capa) == "Acometidas · Negro 0.19 pt · continuo"


def test_bloques_por_orden_de_dibujo():
    """Un bloque admite hasta `BLOQUE_HUECO` trazos de otros estilos entre dos suyos."""
    trazos = [(i, {}) for i in (1, 2, 3, 20, 21, 80)]
    assert [[i for i, _d in b] for b in acometidas_mapa._bloques(trazos)] == [[1, 2, 3, 20, 21], [80]]


def test_la_acometida_llega_a_su_tuberia_con_una_t():
    red = _pl([(0, 0), (100, 0)])
    tap = _pl([(40, 0.3), (40, 20)], layer=acometidas_mapa.capa(ESTILO_FINO, "AGUA"))
    lejos = _pl([(70, 5), (70, 20)], layer=acometidas_mapa.capa(ESTILO_FINO, "AGUA"))
    got = taps_mod.snap_taps([red, tap, lejos], zoom=1.0)
    assert got == [(40.0, 0.0)] and tap.pts_pdf[0] == (40.0, 0.0) and tap.kinds[0] == "tee"
    assert lejos.kinds == ["end", "end"] and red.pts_pdf == [(0, 0), (100, 0)]     # la tubería no se toca


# ── buzones de la leyenda en su línea ───────────────────────────────────────
def test_buzon_simbolo_en_la_punta_y_atravesado():
    vg = lambda c: {"center": c, "circle": (c[0], c[1], 1.5), "layer": SIMBOLO, "orphan": True,
                    "width_ft": 4.0, "length_ft": 4.0}
    punta = _pl([(0, 0), (50, 0.1)])                 # muere dentro del buzón (50, 0)
    pasa = _pl([(0, 30), (100, 30)])                 # lo atraviesa sin vértice (60, 30.4)
    lejos = _pl([(0, 60), (100, 60)])
    hits = map_vaults.mark_symbol_vaults([punta, pasa, lejos], [vg((50, 0)), vg((60, 30.4)), vg((60, 70))],
                                         zoom=1.0, scale_ft_per_pt=100 / 72)
    assert [h["vault"] for h in hits] == [0, 1]
    assert punta.kinds[-1] == "vault" and pasa.kinds == ["end", "vault", "end"] and pasa.pts_pdf[1] == (60.0, 30.0)
    assert lejos.kinds == ["end", "end"]


def test_buzon_de_otra_capa_no_se_toca():
    pl = _pl([(0, 0), (50, 0)])
    vg = {"center": (50, 0), "circle": (50, 0, 1.5), "layer": "C-SSWR-MANH", "orphan": True}
    assert map_vaults.mark_symbol_vaults([pl], [vg], 1.0, 1.0) == [] and pl.kinds == ["end", "end"]


# ── diámetros escritos en el plano ──────────────────────────────────────────
def test_diametro_del_rotulo_paralelo_y_pegado_a_su_tuberia():
    a = _pl([(0, 0), (100, 0)])
    b = _pl([(0, 20), (100, 20)])
    tap = _pl([(30, 20), (30, 40)], layer=acometidas_mapa.capa(ESTILO_FINO, "AGUA"))
    rot = [((20, -2), (1, 0), 1.7, 8.0, False), ((70, -2), (1, 0), 1.7, 8.0, False),   # a: 8" y 8"
           ((50, 22), (1, 0), 1.7, 6.0, False), ((80, 22), (1, 0), 1.7, 12.0, False),  # b: mezcla
           ((50, -2), (0, 1), 1.7, 4.0, False),                                         # perpendicular: no
           ((32, 30), (0, 1), 1.7, 2.0, True)]                                          # «278' 2"»: acometida
    got = diam_mod.asignar([a, b, tap], rot, taps_mod.is_tap)
    assert (a.diam_in, b.diam_in, tap.diam_in) == (8.0, None, 2.0)
    assert b.review == "diam_mix" and got == {"con": 2, "mezcla": 1, "rotulos": 5}


# ── con los PDF de Phoenix ──────────────────────────────────────────────────
@needs_phoenix
def test_phoenix_leyenda_de_agua_completa():
    doc = fitz.open(str(WATER_S))
    ley = LM.leer(doc, doc[3])
    textos = {f.texto: f for f in ley.filas}
    assert textos["As-Built Tap"].rol == LM.ACOMETIDA and textos["Application Tap"].rol == LM.ACOMETIDA
    assert "Reclaimed Dipped Main" in textos and "Cathodic Protection Conduit" in textos   # 2.ª columna
    assert not any(t.startswith("Plotted On") for t in textos)                             # cajetín
    assert textos["Water Vaults"].simbolo is None          # no el punto gris de la fila de abajo
    assert ley.diam_acometida_in == 0.75 and ley.material.startswith("ACP")


@needs_phoenix
def test_phoenix_seis_pulgadas_se_lee():
    """El «6» de «6"» no se leía: la flecha del «Valve #» se metía en su celda."""
    from hoja import texto_pdf
    doc = fitz.open(str(WATER_S))
    assert '6"' in {c.texto for c in texto_pdf.corridas(doc[3])}


@needs_phoenix
def test_phoenix_agua_con_acometidas_y_diametros():
    from reconocimiento import recognition as rec
    r = rec.recognize_page(str(WATER_S), page_index=3, utility="AGUA", layer_roles=None, zoom=1.0)
    taps = [pl for pl in r.drawable if acometidas_mapa.es_capa(pl.layer_ocg)]
    assert len(taps) >= 380
    assert all(pl.kinds.count("tee") == 1 for pl in taps)          # cada una nace en SU tubería
    assert sum(1 for pl in taps if pl.diam_in == 0.75) >= 0.9 * len(taps)
    red = [pl for pl in r.drawable if not acometidas_mapa.es_capa(pl.layer_ocg)]
    assert sum(1 for pl in red if pl.diam_in in (4.0, 6.0, 8.0, 12.0)) >= 40
    # el eje no sale del trazo de 0.38 pt: la curva de la hoja (N 63RD DR) va a ≤ 0.19 pt
    page = fitz.open(str(WATER_S))[3]
    tinta = [ch for d in pdf_styles.drawings(page) if d.get("layer") == red[0].layer_ocg for ch in ink.chains(d)]
    curva = [p for ch in tinta for p in ch if 484 <= p[0] <= 504 and 485 <= p[1] <= 498]
    segs = [(a, b) for pl in red for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:])]
    assert curva and max(min(ink._seg_dist(p, a, b)[1] for a, b in segs) for p in curva) <= 0.2


@needs_phoenix
def test_phoenix_alcantarillado_buzones_y_acometidas():
    from nucleo import acometidas, model_ops
    from reconocimiento import recognition as rec
    r = rec.recognize_page(str(SEWER_N), page_index=0, utility="ALCANTARILLADO", layer_roles=None, zoom=1.0)
    assert len(r.vault_orphans_px) <= 4                 # antes 33: estaban en la punta de su línea
    assert any(w.startswith("Buzones de la leyenda unidos a su línea") for w in r.warnings)
    # las acometidas también en gravedad (pedido 2026-10-14: solo salía la principal), y
    # al importar sus nodos son NULOS: los buzones visibles son los mismos que sin ellas
    taps = [pl for pl in r.drawable if acometidas_mapa.es_capa(pl.layer_ocg)]
    assert len(taps) >= 50 and sum(pl.kinds.count("tee") for pl in taps) >= 0.9 * len(taps)
    pipes = rec.pipes_from_recognition(r, layer="ALCANTARILLADO", zoom=1.0)
    solo = [dict(p) for p in pipes if not p.get("acometida")]
    s0 = model_ops.rebuild_structures(solo, [])
    model_ops.hide_soft_vertex_structures(solo, s0)
    acometidas.unir_a_principal(pipes, range(len(pipes)), 0.8)
    s1 = model_ops.rebuild_structures(pipes, [])
    model_ops.hide_soft_vertex_structures(pipes, s1)
    vis = lambda ss: sorted((round(s["x"], 3), round(s["y"], 3)) for s in ss if not s.get("hidden"))  # noqa: E731
    assert vis(s1) == vis(s0)
    doc = fitz.open(str(SEWER_N))
    assert any(acometidas_mapa.es_capa(d.get("layer") or "") for d in pdf_styles.drawings(doc[0]))
