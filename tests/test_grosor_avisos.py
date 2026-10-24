"""Diámetro del plano: solo lo SEGURO se pone; lo dudoso o sin dato queda con el diámetro por
defecto y un AVISO en el editor (pedido del usuario 2026-10-22). Rótulos girados 90°, la utilidad
por el código del rótulo y por la tinta donde cae la guía, y los perfiles de los laterales."""
import copy
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

fitz = pytest.importorskip("fitz")

from nucleo import diametro_plano  # noqa: E402
from reconocimiento import recognition_grosor as G  # noqa: E402
from reconocimiento import recognition_grosor_cruces as C  # noqa: E402
from reconocimiento import recognition_grosor_marcos as M  # noqa: E402
from reconocimiento import recognition_grosor_tinta as TI  # noqa: E402
from reconocimiento.recognition_grosor_guias import Guias  # noqa: E402
from reconocimiento.recognition_grosor_texto import utilidad_de  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
ESC = os.path.join(ROOT, "tests", "escenarios", "cruces", "escenarios_prueba.digproj")
FT = 20.0 / 72.0
PPI = 1.0 / (FT * 12.0)


def _rot(v, util="DRENAJE", mat="RCP", **kw):
    return G.Rotulo(f'{v}" {mat} SD', float(v), (0, 0, 1, 1), 12.6, util, mat, **kw)


# ── solo lo seguro ───────────────────────────────────────────────────────
def test_solo_lo_seguro_se_pone():
    """Rótulo: sí. Paredes solas: solo si la hoja confirma si son las de adentro o las de afuera.
    Rótulos distintos o rótulo ≠ paredes: no se pone (dudosa, con lo que dice el plano)."""
    assert G.seguro(G.combinar([_rot(18)], None)) and G.seguro(G.combinar([_rot(18)], 24.0))
    sola = G.combinar([], 24.0)
    assert not G.seguro(sola) and G.candidatos(sola) == [24.0]
    gs = [G.combinar([_rot(24)], 24.0), G.combinar([], 24.0)]
    G.calibrar(gs)
    assert G.seguro(gs[1]) and gs[1].paredes == "interior"            # un rótulo junto a paredes de 24" por dentro
    g = G.combinar([_rot(33)], 24.0)
    assert not G.seguro(g) and G.candidatos(g) == [24.0, 33.0]
    assert G.candidatos(G.combinar([_rot(18), _rot(33)], None)) == [18.0, 33.0]


def test_aplicar_deja_el_estado_de_cada_linea():
    m = 24 * PPI / 2
    linea = lambda y: SimpleNamespace(pts_pdf=[(0, y), (600, y)], kinds=["end", "end"], diam_in=None, grosor={})  # noqa: E731
    con, sola, nada = linea(100), linea(300), linea(500)
    muros = [((0, 300 - m), (600, 300 - m)), ((0, 300 + m), (600, 300 + m))]
    r = _rot(18)
    hoja = G.Hoja([r], [(r, [], (300.0, 100.0))], muros)
    cuenta = G.aplicar([con, sola, nada], hoja, "DRENAJE", 1.0, FT)
    assert (con.grosor["estado"], con.diam_in) == ("leido", 18.0)
    assert (sola.grosor["estado"], sola.diam_in, sola.grosor["candidatos"]) == ("dudoso", None, [24.0])
    assert (nada.grosor, nada.diam_in) == ({"estado": "sin_dato"}, None)
    assert (cuenta["con"], cuenta["revisar"], cuenta["sin"]) == (1, 1, 1)
    # sin rótulos ni paredes en la hoja: todas sin dato
    otra = linea(700)
    assert G.aplicar([otra], G.Hoja([], [], []), "DRENAJE", 1.0, FT)["sin"] == 1 and otra.grosor["estado"] == "sin_dato"


# ── rótulos girados, código y tinta ──────────────────────────────────────
def test_rotulo_vertical_con_su_guia():
    """«8" C.I., 20'W CL, W139C» de abajo arriba (DU10): la guía nace en el comienzo del texto y
    baja hasta la tubería."""
    lineas = [('8" C.I., 20\'W CL, W139C', (100.0, 200.0, 112.0, 330.0), 12.0, (0.0, -1.0))]
    # la raya a lo largo del texto y la guía que baja, con su flecha rellena, hasta la tubería
    flecha = [(127.5, 428.4), (122.5, 419.5), (125.5, 418.5)]
    gs = Guias([((106.0, 330.0), (106.0, 370.0)), ((106.0, 370.0), (124.0, 419.0))], [flecha], 1.0)
    rots, puntas = M.leer(lineas, gs, 1.0)
    assert len(rots) == 1 and rots[0].utilidad == "AGUA" and rots[0].pulg == 8.0
    assert rots[0].bbox == pytest.approx((100.0, 200.0, 112.0, 330.0))   # su caja, de vuelta en la hoja
    (r, _cad, p), = puntas
    assert r is rots[0] and p == pytest.approx((127.5, 428.4))
    # de ida y vuelta al marco del texto, en las cuatro direcciones
    for d in M.DIRECCIONES:
        assert M.de_marco(d, M.al_marco(d, (3.5, -7.25))) == pytest.approx((3.5, -7.25))


def test_utilidad_por_el_codigo_del_rotulo():
    assert utilidad_de('8" C.I., 20\'W CL, W139C') == "AGUA"
    assert utilidad_de('6-5" 2-4", 19\'W CL, E168') == "ELECTRICO"
    assert utilidad_de('4" PE, 27\'N CL, G053') == "GAS"
    assert utilidad_de('1-4" PVC, 49\'W CL, C087') == "TELECOM"
    assert utilidad_de('8" VCP, 25\'E CL, S144') == "ALCANTARILLADO"
    assert utilidad_de('PROP FTR 2-4" PVC, 224.5\'N CL') == "TELECOM"
    assert utilidad_de('PROP METRO 8" HDPE') == ""                     # el código no está: no se adivina
    assert utilidad_de('DWPPS G9026, 12-4", 39\'E CL, E461') == "ELECTRICO"   # las palabras primero


def _dibujo(capa, a, b):
    return {"layer": capa, "items": [("l", fitz.Point(*a), fitz.Point(*b))]}


def test_la_tinta_donde_cae_la_guia_dice_la_utilidad():
    dib = [_dibujo("X|C-WATR-UNGD-E", (0, 100), (500, 100)), _dibujo("X|C-NGAS-E", (0, 200), (500, 200)),
           _dibujo("X|C-NGAS-E", (250, 0), (250, 300)), _dibujo("X|C-WATR-ANNO", (0, 101), (500, 101))]
    u = TI.utilidades_en_puntas(dib, lambda p: (float(p[0]), float(p[1])), 1.0,
                                [(100.0, 101.0), (100.0, 199.0), (250.0, 100.0), (100.0, 400.0)])
    assert u == ["AGUA", "GAS", None, None]       # la anotación no cuenta; en el cruce no se sabe; lejos, nada
    # un rótulo que solo dice su material (HDPE: agua, gas, drenaje…) no va a la línea de agua si su
    # guía cae sobre la tinta del drenaje
    r = G.Rotulo('PROP METRO 8" HDPE', 8.0, (0, 0, 1, 1), 12.6, "", "HDPE")
    agua = [(0, 100), (500, 100)]
    puntas = [(r, [], (200.0, 100.0))]
    assert G.asignar_rotulos([agua], puntas, "AGUA", PPI, 1.0, tinta=["DRENAJE"]) == {}
    assert G.asignar_rotulos([agua], puntas, "AGUA", PPI, 1.0, tinta=[None])[0] == [r]
    con_util = G.Rotulo('8" C.I. W139', 8.0, (0, 0, 1, 1), 12.6, "AGUA", "CI")
    assert G.asignar_rotulos([agua], [(con_util, [], (200.0, 100.0))], "AGUA", PPI, 1.0, tinta=["GAS"])[0] == [con_util]


# ── perfiles de los laterales ────────────────────────────────────────────
def test_desfase_de_las_estaciones():
    # dos cruces corridos lo mismo (+4.2 ft: el lateral nace en otro sumidero): se aceptan
    assert C._desfase([[21.08, 15.75], [37.42]], [16.85, 33.25])[1] == 2
    # un solo cruce corrido: no se sabe si es el corrimiento u otra tubería
    assert C._desfase([[21.08]], [16.85]) is None
    assert C._desfase([[17.5]], [16.85]) is not None                # sin corrimiento, a ≤1.5 ft


@pytest.mark.skipif(not DU06.is_file(), reason="DU06 no disponible")
def test_du06_h5_los_perfiles_dicen_el_diametro_de_lo_que_cruza_el_lateral():
    """DU06 h.5: el perfil del lateral CB-208 dice «EX. 4" GAS, SCG» a 41.4 ft de la principal; el
    de CB-211 «EX. 15" SEWER» y «EX 8" WL». Esas tuberías de la planta (sin rótulo) los toman, y
    los laterales confirman su 18" con «L=…, 18" RCP SD»."""
    from reconocimiento import recognition_trabajo as RT
    res = RT.reconocer_hoja(str(DU06), 4, zoom=1.0, utilities=("DRENAJE", "AGUA", "ALCANTARILLADO", "GAS"))
    assert {p.nombre for p in res[0].perfiles} >= {"CB-208", "CB-209", "CB-211"}
    del_perfil = {(r.utility, p.grosor.get("diam_in"), p.grosor.get("fuente")) for r in res for p in r.polylines
                  if (p.grosor or {}).get("perfil_in")}
    assert ("GAS", 4.0, "perfil") in del_perfil
    assert ("ALCANTARILLADO", 15.0, "perfil") in del_perfil
    assert ("AGUA", 8.0, "perfil") in del_perfil
    assert ("DRENAJE", 18.0, "rotulo+paredes") in del_perfil                # confirmado por el perfil
    gas = next(r for r in res if r.utility == "GAS")
    assert any(w.startswith("Diámetros del plano") for w in gas.warnings)    # recontado tras los perfiles


# ── en el editor ─────────────────────────────────────────────────────────
def test_aviso_de_diametro_del_plano():
    base = dict(layer="AGUA", pts=[(0, 0), (100, 0)], diam=12.0)
    sin = dict(base, diam_plano={"estado": "sin_dato"})
    duda = dict(base, diam_plano={"estado": "dudoso", "fuente": "rotulo≠paredes", "candidatos": [24.0, 33.0],
                                  "paredes_in": 24.0, "textos": ['EX 33" RCP']})
    elegido = dict(sin, diam=12.0, diam_elegido=True)
    leido = dict(base, diam=8.0, diam_elegido=True, diam_plano={"estado": "leido"})
    av = diametro_plano.avisos([sin, duda, elegido, leido, base])
    assert [a.pipe for a in av] == [0, 1] and all(a.clase == "grosor" and not a.info for a in av)
    assert (av[0].x, av[0].y) == (50.0, 0.0)
    assert "no encontrado" in av[0].mensaje and '33"' in av[1].mensaje and '24"' in av[1].mensaje
    assert "«EX 33\" RCP»" in av[1].mensaje
    # lo que se guarda al importar
    assert diametro_plano.de_grosor({"estado": "dudoso", "fuente": "mezcla", "candidatos": [8, 6],
                                     "textos": list("abcdef")}) == {
        "estado": "dudoso", "fuente": "mezcla", "candidatos": [8.0, 6.0], "textos": list("abcd")}
    assert diametro_plano.de_grosor({}) == {}


def test_al_importar_la_utilidad_guarda_lo_que_dijo_el_plano():
    from reconocimiento import recognition as R
    pl = R.RecognizedPolyline("C-WATR-UNGD-E", "AGUA", [(0, 0), (100, 0)], "water_ungd", kinds=["end", "end"])
    pl.grosor = {"estado": "sin_dato"}
    pl2 = R.RecognizedPolyline("C-WATR-UNGD-E", "AGUA", [(0, 50), (100, 50)], "water_ungd", kinds=["end", "end"])
    pl2.diam_in, pl2.grosor = 8.0, {"estado": "leido", "diam_in": 8.0, "fuente": "rotulo", "textos": ['8" W']}
    res = R.RecognitionResult(utility="AGUA", page_index=0, scale_ft_per_pt=FT, polylines=[pl, pl2])
    a, b = R.pipes_from_recognition(res, layer="AGUA")
    assert (a["diam_plano"], a["diam"], a["diam_elegido"]) == ({"estado": "sin_dato"}, 12.0, False)
    assert (b["diam_plano"]["estado"], b["diam"], b["diam_elegido"]) == ("leido", 8.0, True)


@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def test_en_el_editor_el_aviso_se_marca_y_se_va_al_elegir_el_diametro(win):
    p = copy.deepcopy(win.pipes[0])
    for k in ("pipe_size", "pipe_family", "diam_elegido"):
        p.pop(k, None)
    p.update(diam=12.0, diam_plano={"estado": "sin_dato"})
    win.pipes.append(p)
    i = len(win.pipes) - 1
    win._redraw()
    suyos = [a for a in win._normas_avisos if a.clase == "grosor" and a.pipe == i]
    assert len(suyos) == 1 and "no encontrado" in suyos[0].mensaje
    # va con su propia opción de Ver → Avisos, no con la de normativa
    from ui.comun.avisos_view import InsigniaAviso

    def marcados():
        return [it for it in win._overlay if isinstance(it, InsigniaAviso) and "no encontrado" in it.toolTip()]
    assert marcados() and "reconocimiento" in win.btn_normas.text()
    for act, ver in ((win.act_show_normas, False), (win.act_show_reconocimiento, True)):
        act.blockSignals(True); act.setChecked(ver); act.blockSignals(False)
    win._redraw()
    assert marcados()
    for act, ver in ((win.act_show_normas, True), (win.act_show_reconocimiento, False)):
        act.blockSignals(True); act.setChecked(ver); act.blockSignals(False)
    win._redraw()
    assert not marcados()
    win.act_show_reconocimiento.blockSignals(True); win.act_show_reconocimiento.setChecked(True)
    win.act_show_reconocimiento.blockSignals(False)
    # elige un diámetro (o un tamaño): el aviso ya no está
    win.pipes[i].update(diam=8.0, diam_elegido=True)
    win._redraw()
    assert not [a for a in win._normas_avisos if a.clase == "grosor" and a.pipe == i]
