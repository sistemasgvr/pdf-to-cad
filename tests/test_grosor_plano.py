"""Grosor (diámetro) de cada tubería en un PDF CAD bien ploteado (pedido del usuario 2026-10-21,
DU06): por su rótulo con guía y por sus paredes dibujadas, como COMPLEMENTO — la geometría
reconocida no cambia (`recognition_grosor`)."""
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")

from reconocimiento import recognition_grosor as G  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
FT = 20.0 / 72.0                    # 1" = 20' → pies por pt
PPI = 1.0 / (FT * 12.0)             # pt por pulgada de tubería
ident = lambda p: (float(p[0]), float(p[1]))  # noqa: E731


def test_rotulos_solo_diametros_de_tuberia():
    assert G.diametros_de('EX. 84" RCP SD') == [84.0]
    assert G.diametros_de("L=29.77', 18\" RCP SD") == [18.0]
    # el punto de «EX.» pegado al número (46 rótulos de DU06 se perdían) y la estación con el
    # nombre del alineamiento entre comillas en la misma línea
    assert G.diametros_de('EX.18" RCP SD') == [18.0] and G.diametros_de('JOIN TO EX.78" RCP SD,') == [78.0]
    assert G.diametros_de('EX. 84" RCP SD 552+56.35 "VN"') == [84.0]
    for nada in ('1" = 20\'', 'N89°47\'33"W', 'S85° 00\' 56.07"E', '#4 @ 6" BOTH WAYS', '12" MIN',
                 '552+56.35 "VN"', 'STA 557+47.29 "VN"'):
        assert G.diametros_de(nada) == [], nada
    assert G.utilidad_de('PROP 8" WATER') == "AGUA" and G.utilidad_de('EX 15" SSWR,') == "ALCANTARILLADO"
    assert G.utilidad_de('18" RCP, LACFCD') == "DRENAJE" and G.material_de('JOIN EX. 18" RCP') == "RCP"
    # el dueño de la red cuando es de una sola utilidad
    assert G.utilidad_de('PROP 2" SCG') == "GAS" and G.utilidad_de('EX 8" WL, DWPWS') == "AGUA"
    assert G.utilidad_de('EX 18" SWR,') == "ALCANTARILLADO"
    # DU08: bancos de conductos («2-6"» = dos de 6": el diámetro es el de cada uno; con tamaños
    # mezclados no hay uno), fracciones de pulgada y materiales con puntos
    assert G.lecturas('PROP DWPPS 2-6"P CONDUIT,') == [(6.0, 2)] and G.diametros_de('2-24" DBL RCP') == [24.0]
    assert G.diametros_de('FRONTIER (GTE) 1-4" PVC,') == [4.0]
    assert G.diametros_de('12-4", 2-5", 1-3",') == [4.0, 5.0, 3.0]
    assert G.diametros_de('1-1/2" WS') == [1.5] and G.diametros_de('3/4" GS') == [0.75]
    assert G.diametros_de('1/2" P, 92\'E CL GS') == [0.5]
    assert G.material_de('PROP DWPWS 12" D.I.,') == "DI" and G.material_de('12" C.I., 23\'S CL') == "CI"
    r = G.Rotulo('JOIN EX. 18" RCP', 18.0, (0, 0, 1, 1), 10, "", "RCP")
    assert G.es_de(r, "DRENAJE") and not G.es_de(r, "TELECOM")


def test_dos_rotulos_apilados_son_dos_bloques():
    """«LAT CB-226 / 18" RCP SD,LACFCD» y justo debajo, alineado, «CB-226, LACFCD / V=… /
    STA 69+17.24»: el paso entre líneas cambia → dos MText; el de 18" no hereda la estación."""
    L = lambda t, y: (t, (1136.0, y, 1260.0, y + 12.6), 12.57, (1.0, 0.0))  # noqa: E731
    lineas = [L("LAT CB-226", 1423.3), L('18" RCP SD,LACFCD', 1438.4), L("CB-226, LACFCD", 1459.2),
              L("V=6.76', W=7.0',", 1474.2), L('STA 69+17.24 "VICTORY BLVD"', 1489.4)]
    rots, cajas = G.rotulos(lineas)
    assert [r.pulg for r in rots] == [18.0] and not rots[0].estacion
    assert len(cajas) == 2
    # un rótulo de unión sí lleva su estación (mismo paso)
    lineas = [L('JOIN TO EX.78" RCP SD,', 849.9), L("LACFCD", 862.8), L('30+52.27 "VN" STA', 875.7)]
    rots, _c = G.rotulos(lineas)
    assert rots[0].estacion and rots[0].union
    # con estación pero no de unión (DU08 h.38): es de la tubería a la que apunta
    lineas = [L('EXIST 18" VCP SEWER', 100.0), L("STA 0+44.33", 112.9), L("ENCASEMENT END", 125.8)]
    rots, _c = G.rotulos(lineas)
    assert rots[0].estacion and not rots[0].union
    # columna de rótulos de DU08 h.25 (alineados a la derecha, dos líneas cada uno, paso irregular
    # entre rótulos): el dueño en la 1.ª línea da la utilidad del diámetro de la 2.ª
    R = lambda t, y: (t, (843.0 - 9.0 * len(t), y, 843.0, y + 12.9), 12.57, (1.0, 0.0))  # noqa: E731
    lineas = [R("SCG AM-17,", 206.4), R('2" STL, 17\'N CL, G092', 219.2), R("DWPWS W200-150,", 230.1),
              R('12" C.I., 23\'S CL, W154', 243.0), R("*UNK, VAR CL", 255.0)]
    rots, cajas = G.rotulos(lineas)
    assert [(r.pulg, r.utilidad, r.material) for r in rots] == [(2.0, "GAS", "STL"), (12.0, "AGUA", "CI")]
    assert len(cajas) == 3 and rots[0].bloque != rots[1].bloque
    # banco de conductos de tamaños distintos en un MText: ningún diámetro
    lineas = [L('PROP DWPPS 6-6" &', 1000.0), L('1-4"P CONDUIT,', 1015.1)]
    assert G.rotulos(lineas)[0] == []
    rots, _c = G.rotulos([L('PROP DWPPS 2-6"P CONDUIT,', 1000.0)])
    assert [(r.pulg, r.varios, r.utilidad) for r in rots] == [(6.0, 2, "ELECTRICO")]
    # una columna de rótulos de una línea al mismo paso (DU08 h.46) no es un banco mezclado
    lineas = [L('PROP 24" SD,', 900.0), L("SEE DRAINAGE PLAN", 915.1), L('8" GAS', 930.2), L('10-4" ELEC', 945.3)]
    rots, _c = G.rotulos(lineas)
    assert [(r.pulg, r.utilidad) for r in rots] == [(24.0, "DRENAJE"), (8.0, "GAS"), (4.0, "ELECTRICO")]


def _hoja_con_rotulo(sin_raya=False, flecha_abierta=False):
    """Dos tuberías horizontales (y=300 e y=400) y un rótulo «EX 18" RCP SD» cuya guía llega a
    la de abajo; la de arriba con un rótulo de 24" que no tiene guía."""
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    page.insert_text((100, 200), 'EX 18" RCP SD', fontsize=12.6)
    page.insert_text((100, 214), "LACFCD", fontsize=12.6)
    page.insert_text((500, 200), '24" RCP SD', fontsize=12.6)
    sh = page.new_shape()
    raya_y = 202.0
    fin = 192.0
    if sin_raya:
        sh.draw_polyline([(fin + 1, 198), (300, 397)])
    else:
        sh.draw_polyline([(100, raya_y), (fin, raya_y), (fin + 4, raya_y), (300, 397)])
    sh.finish(color=(0, 0, 0), width=0.72, closePath=False)
    if flecha_abierta:
        sh.draw_line((300, 397), (296, 390)); sh.draw_line((300, 397), (302, 389))
        sh.finish(color=(0, 0, 0), width=0.72)
    else:
        sh.draw_polyline([(298, 393), (300.5, 400), (303, 392), (298, 393)])
        sh.finish(color=(0, 0, 0), fill=(0, 0, 0), width=0)
    sh.commit()
    return doc, page


@pytest.mark.parametrize("sin_raya,abierta", [(False, False), (True, False), (False, True)])
def test_la_guia_lleva_el_rotulo_a_su_tuberia(sin_raya, abierta):
    _doc, page = _hoja_con_rotulo(sin_raya, abierta)
    rots, cajas = G.rotulos(G.lineas_texto(page, ident, 1.0))
    assert sorted(r.pulg for r in rots) == [18.0, 24.0]
    puntas = G.puntas_de_rotulos(rots, cajas, G.guias(page, ident))
    assert [r.pulg for r, _c, _p in puntas] == [18.0]
    arriba, abajo = [(50, 300), (750, 300)], [(50, 400), (750, 400)]
    asig = G.asignar_rotulos([arriba, abajo], puntas, "DRENAJE", PPI, 1.0)
    assert set(asig) == {1} and asig[1][0].pulg == 18.0


def test_dos_guias_que_llegan_al_mismo_punto_no_se_encadenan():
    """Dos rótulos cuyas flechas llegan a la misma unión (DU06 h.6): cada guía termina en SU
    flecha, no sigue por la del otro hasta su raya."""
    tramos = [((0, 0), (40, 0)), ((40, 0), (100, 60)),        # rótulo A: raya + guía
              ((200, 0), (160, 0)), ((160, 0), (100, 60))]     # rótulo B: raya + guía
    flechas = [[(100, 60), (95, 52), (102, 53)], [(100, 60), (105, 52), (98, 53)]]
    caminos = G.Guias(tramos, flechas, 1.0).seguir(0, (0, 0))
    assert len(caminos) == 1 and len(caminos[0][0]) == 3


def test_flecha_pasada_de_largo_y_tuberia_dibujada_dos_veces():
    r = G.Rotulo('EX.18" RCP SD, LACFCD', 18.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")
    lateral = [(100, 0), (100, 300)]
    # la guía cruza el lateral 3 pt antes de la base de la flecha y la punta queda 11 pt más allá
    cadena = [(0, 150), (103, 150)]
    asig = G.asignar_rotulos([lateral], [(r, cadena, (111.0, 150.0))], "DRENAJE", PPI, 1.0)
    assert asig[0] == [r]
    # existente y propuesta una junto a la otra (1.6 pt): el rótulo es de las dos; la de al lado
    # que ya dice 18" no lo pierde
    existente, propuesta = [(98.4, 0), (98.4, 300)], [(100, 100), (100, 200)]
    otro = G.Rotulo('18" RCP SD LACFCD', 18.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")
    puntas = [(otro, [], (98.4, 20.0)), (r, [], (102.7, 150.0))]
    asig = G.asignar_rotulos([existente, propuesta], puntas, "DRENAJE", PPI, 1.0)
    assert r in asig[0] and r in asig[1]


def test_rotulo_de_union_solo_confirma():
    """«JOIN TO EX.78" RCP SD / STA 40+63.38» con la flecha en la punta del lateral (DU06 h.14):
    no le da 78" al lateral que ya dice 18" ni a una línea que no dice nada."""
    lateral, propuesta = [(400, 300), (400, 100)], [(400, 100), (402, 40)]
    union = (400.0, 100.0)
    r78 = G.Rotulo('JOIN TO EX.78" RCP SD,', 78.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP", estacion=True, union=True)
    r18 = G.Rotulo('18" RCP SD LACFCD', 18.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")
    asig = G.asignar_rotulos([lateral, propuesta], [(r18, [], (400.0, 200.0)), (r78, [], union)],
                             "DRENAJE", PPI, 1.0)
    assert asig[0] == [r18] and not asig.get(1)


def test_paredes_dan_el_diametro_interior():
    centro = [(0.0, 100.0), (600.0, 100.0)]
    m = 18 * PPI / 2                                   # medio diámetro interior en pt
    muros = [((0, 100 - m), (600, 100 - m)), ((0, 100 + m), (600, 100 + m)),
             ((0, 100 - m - 3), (600, 100 - m - 3)), ((0, 100 + m + 3), (600, 100 + m + 3))]  # exterior
    assert G.paredes(centro, muros, PPI, 1.0) == 18.0
    assert G.paredes(centro, muros[:1], PPI, 1.0) is None          # una sola pared: nada


def test_en_la_union_cada_rotulo_va_a_su_tuberia():
    """La punta cae donde el lateral (18") llega a la principal (84", con paredes)."""
    principal, lateral = [(0, 100), (800, 100)], [(400, 100), (400, 300)]
    union = (400.0, 100.0)
    r84 = G.Rotulo('EX. 84" RCP SD', 84.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")
    r18 = G.Rotulo('JOIN EX. 18" RCP SD', 18.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")
    puntas = [(r84, [], union), (r18, [], union)]
    asig = G.asignar_rotulos([principal, lateral], puntas, "DRENAJE", PPI, 1.0, [84.0, None])
    assert asig[0] == [r84] and asig[1] == [r18]
    # sin paredes ni otro dato: la unión no decide sola
    assert not G.asignar_rotulos([principal, lateral], [(r18, [], union)], "DRENAJE", PPI, 1.0)


def test_en_la_union_cuenta_la_principal_que_dice_varios_diametros():
    """Antes de partirla, la principal que pasa de 84" a 81" dice los dos: el rótulo de 84" que
    cae en la unión con un lateral sin datos es de la principal, no del lateral (compuesta DU06)."""
    principal, lateral = [(0, 100), (800, 100)], [(400, 100), (400, 300)]
    rot = lambda v, t="": G.Rotulo(f'EX. {v}" RCP SD{t}', float(v), (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")  # noqa: E731
    r84, r81, r84u = rot(84), rot(81), rot(84, ", LACFCD")
    puntas = [(r84, [], (100.0, 100.0)), (r81, [], (700.0, 100.0)), (r84u, [], (400.0, 100.0))]
    asig = G.asignar_rotulos([principal, lateral], puntas, "DRENAJE", PPI, 1.0)
    assert asig[0] == [r84, r81, r84u] and not asig.get(1)


def test_combinar_manda_el_rotulo_y_marca_lo_que_no_cuadra():
    r = lambda v: G.Rotulo(f'{v}" RCP SD', float(v), (0, 0, 1, 1), 12, "DRENAJE", "RCP")  # noqa: E731
    assert G.combinar([r(18)], 18.0).fuente == "rotulo+paredes"
    g = G.combinar([r(33)], 24.0)
    assert (g.diam_in, g.fuente) == (33.0, "rotulo≠paredes")
    g = G.combinar([r(18), r(33)], None)
    assert (g.diam_in, g.fuente) == (None, "mezcla")
    assert G.combinar([], 24.0).fuente == "paredes"


def test_paredes_al_diametro_exterior():
    """DU06 dibuja laterales de 18" con las paredes a 24" (pared de 3"): coincide con el rótulo; y
    en la hoja, una línea solo con paredes de 24" es de 18" si así lo dicen las rotuladas."""
    r = lambda v: G.Rotulo(f'{v}" RCP SD', float(v), (0, 0, 1, 1), 12, "DRENAJE", "RCP")  # noqa: E731
    g = G.combinar([r(18)], 24.0)
    assert (g.diam_in, g.fuente, g.paredes) == (18.0, "rotulo+paredes", "exterior")
    assert G.combinar([r(18)], 18.0).paredes == "interior"
    assert G.combinar([r(18)], 33.0).fuente == "rotulo≠paredes"
    gs = [G.combinar([r(18)], 24.0), G.combinar([], 24.0), G.combinar([], 18.0)]
    assert G.calibrar(gs) == 1 and (gs[1].diam_in, gs[1].paredes) == (18.0, "exterior")
    assert gs[2].diam_in == 18.0
    # si en la hoja hay paredes de 24" que SÍ son un 24", no se toca
    gs = [G.combinar([r(18)], 24.0), G.combinar([r(24)], 24.0), G.combinar([], 24.0)]
    assert G.calibrar(gs) == 0 and gs[2].diam_in == 24.0


def test_ruta_con_dos_diametros_se_parte_en_el_pozo():
    """DU06 h.5: la principal dice 84" hasta el pozo y 81" después (una sola polilínea)."""
    from reconocimiento import recognition_grosor_partir as P
    from reconocimiento.recognition import RecognizedPolyline
    pts = [(0, 100), (300, 100), (315, 100), (330, 100), (700, 100)]
    kinds = ["cut", "edge", "vault", "edge", "cut"]
    assert P.vertices_de_corte(pts, kinds, [(100, 84.0), (310, 84.0), (600, 81.0)], 1.0) == [2]
    # un diámetro que vuelve, o sin nodo entre las zonas: no se entiende, no se parte
    assert P.vertices_de_corte(pts, kinds, [(100, 84.0), (600, 81.0), (650, 84.0)], 1.0) is None
    assert P.vertices_de_corte(pts, ["cut", "edge", "edge", "edge", "cut"], [(100, 84.0), (600, 81.0)], 1.0) is None
    pl = RecognizedPolyline("C-STRM-UNGD-E", "DRENAJE", pts, "drain_ungd", kinds=kinds)
    r84 = G.Rotulo('EX. 84" RCP SD', 84.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")
    r81 = G.Rotulo('81" RCP SD', 81.0, (0, 0, 1, 1), 12.6, "DRENAJE", "RCP")
    hoja = G.Hoja([r84, r81], [(r84, [], (100.0, 100.0)), (r81, [], (600.0, 100.0))], [])
    cuenta = G.aplicar([pl], hoja, "DRENAJE", 1.0, FT)
    a, b = cuenta["piezas"][id(pl)]
    assert (a.pts_pdf, a.kinds, a.diam_in) == (pts[:3], kinds[:3], 84.0)
    assert (b.pts_pdf, b.kinds, b.diam_in) == (pts[2:], kinds[2:], 81.0)
    assert cuenta["partidas"] == 1 and a.grosor["partida"] and not pl.grosor


def test_aplicar_no_pisa_un_diametro_ya_leido():
    pl = SimpleNamespace(pts_pdf=[(0, 100), (600, 100)], diam_in=8.0, grosor={})
    m = 18 * PPI / 2
    hoja = G.Hoja([], [], [((0, 100 - m), (600, 100 - m)), ((0, 100 + m), (600, 100 + m))])
    cuenta = G.aplicar([pl], hoja, "DRENAJE", 1.0, FT)
    assert pl.diam_in == 8.0 and pl.grosor["paredes_in"] == 18.0 and cuenta["con"] == 0


# ── con el PDF del reporte ──────────────────────────────────────────────
def _foto(res):
    return [(p.layer_ocg, p.kind, [tuple(q) for q in p.pts_pdf], list(p.kinds), sorted(p.fillets), p.abandoned)
            for p in res.polylines]


@pytest.mark.skipif(not DU06.is_file(), reason="DU06 no disponible")
def test_du06_h4_drenaje_grosor_sin_cambiar_la_geometria(monkeypatch):
    from reconocimiento import recognition as R
    con = R.recognize_page(str(DU06), 3, "DRENAJE", zoom=3.5)
    # agua: «PROP 8" WATER» con su guía (la raya a 11 pt del texto)
    agua = R.recognize_page(str(DU06), 3, "AGUA", zoom=3.5)
    assert any(p.diam_in == 8.0 for p in agua.drawable)
    monkeypatch.setattr(G, "aplicar", lambda *a, **k: {"con": 0, "revisar": 0})
    sin = R.recognize_page(str(DU06), 3, "DRENAJE", zoom=3.5)
    # todo igual salvo la ruta que une dos laterales distintos (18" y 33") por una esquina sobre
    # la principal: va en dos piezas partidas en esa esquina, sin mover vértices (≤0.5 px: los
    # ángulos a pasos de 0.25° se ajustan por pieza)
    fc, fs = _foto(con), _foto(sin)
    viejas, nuevas = [f for f in fs if f not in fc], [f for f in fc if f not in fs]
    assert len(viejas) == 1 and len(nuevas) == 2
    ruta = viejas[0][2]
    a, b = nuevas
    assert len(a[2]) + len(b[2]) == len(ruta) + 1
    assert all(math.dist(p, q) <= 0.5 for p, q in zip(a[2] + b[2][1:], ruta))
    piezas = [p for p in con.drawable if p.grosor.get("partida")]
    assert sorted(p.diam_in for p in piezas) == [18.0, 33.0]
    assert not any(p.grosor or p.diam_in for p in sin.drawable)
    principal = max(con.drawable, key=lambda p: len(p.pts_pdf) and abs(p.pts_pdf[-1][0] - p.pts_pdf[0][0]))
    assert principal.diam_in == 84.0 and principal.grosor["fuente"] == "rotulo+paredes"
    assert sum(1 for p in con.drawable if p.diam_in == 18.0) >= 2
    assert any(w.startswith("Diámetros del plano") for w in con.warnings)
    assert any(w.startswith("Tuberías partidas donde el plano cambia de diámetro") for w in con.warnings)


@pytest.mark.skipif(not DU06.is_file(), reason="DU06 no disponible")
@pytest.mark.parametrize("hoja,diams", [(4, (84.0, 81.0)), (10, (81.0, 78.0))])
def test_du06_la_principal_cambia_de_diametro_en_un_pozo(hoja, diams):
    """h.5: 84" hasta el pozo de x≈1095 y 81" después; h.11: 81" hasta el pozo de x≈426 y 78"."""
    from reconocimiento import recognition as R
    res = R.recognize_page(str(DU06), hoja, "DRENAJE", zoom=1.0)
    piezas = sorted((p for p in res.drawable if p.grosor.get("partida")), key=lambda p: min(q[0] for q in p.pts_pdf))
    assert len(piezas) == 2
    izq, der = piezas
    assert {izq.diam_in, der.diam_in} == set(diams)
    comun = [q for q in izq.pts_pdf if any(math.dist(q, w) < 1e-6 for w in der.pts_pdf)]
    assert len(comun) == 1
    k = next(i for i, q in enumerate(izq.pts_pdf) if q == comun[0])
    assert izq.kinds[k] == "vault"                 # se parte en el pozo, no en otro vértice
